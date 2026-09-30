import asyncio
import html
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import seo

BASE_DIR = Path(__file__).parent


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


load_dotenv(BASE_DIR / ".env")

CONTENT_TYPES: dict[str, str] = {
    "livre": "Conteúdo livre: siga exatamente o pedido do usuário.",
    "instagram": (
        "Post para Instagram: comece com um gancho forte na primeira linha, "
        "desenvolva em parágrafos curtos com emojis moderados, termine com uma "
        "chamada para ação e 5 a 10 hashtags relevantes."
    ),
    "linkedin": (
        "Post para LinkedIn: gancho na primeira linha, parágrafos de 1-2 frases, "
        "uma lição ou insight prático, e uma pergunta no final para gerar comentários."
    ),
    "thread": (
        "Thread para X/Twitter: numere cada tweet (1/, 2/...), máximo de 280 "
        "caracteres por tweet, o primeiro deve prender a atenção e o último deve ter CTA."
    ),
    "video_curto": (
        "Roteiro de vídeo curto (Reels/TikTok/Shorts, até 60s): gancho nos 3 primeiros "
        "segundos, divida em cenas com FALA e TEXTO NA TELA, e finalize com CTA. "
        "Inclua sugestão de legenda."
    ),
    "youtube": (
        "Roteiro para YouTube: sugira 3 títulos, uma ideia de thumbnail, e escreva o "
        "roteiro com introdução (gancho), tópicos com timestamps estimados e encerramento com CTA."
    ),
    "blog": (
        "Artigo de blog otimizado para SEO: título, meta description (até 155 caracteres), "
        "introdução, seções com subtítulos (##), conclusão e palavras-chave sugeridas."
    ),
    "email": (
        "E-mail marketing: 3 opções de assunto, pré-cabeçalho, corpo persuasivo e "
        "escaneável, e um botão/CTA claro."
    ),
    "ideias": (
        "Brainstorm de pautas: gere 10 ideias de conteúdo numeradas, cada uma com título, "
        "formato sugerido e por que vai engajar."
    ),
}

TONES = {
    "profissional",
    "descontraído",
    "divertido",
    "inspirador",
    "persuasivo",
    "educativo",
}
LANGUAGES = {"Português (Brasil)", "English", "Español"}


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    content_type: str = "livre"
    tone: str = "profissional"
    language: str = "Português (Brasil)"


def build_system_prompt(req: ChatRequest) -> str:
    content_rule = CONTENT_TYPES.get(req.content_type, CONTENT_TYPES["livre"])
    tone = req.tone if req.tone in TONES else "profissional"
    language = req.language if req.language in LANGUAGES else "Português (Brasil)"
    return (
        "Você é o Criador, um assistente especialista em criação de conteúdo para redes "
        "sociais, blogs e marketing. Escreva textos originais, prontos para publicar, "
        "com linguagem natural e foco em engajamento. Use Markdown para organizar a resposta. "
        "Se faltar informação essencial (público, produto, objetivo), faça no máximo "
        "duas perguntas curtas antes de escrever.\n\n"
        f"Formato: {content_rule}\n"
        f"Tom de voz: {tone}.\n"
        f"Idioma da resposta: {language}."
    )


def provider() -> tuple[str, str] | None:
    model = os.environ.get("MODEL", "").strip()
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", model or "gpt-6-luna"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", model or "claude-sonnet-4-5"
    return None


def build_upstream_request(
    client: httpx.AsyncClient, req: ChatRequest
) -> tuple[str, httpx.Request]:
    selected = provider()
    if selected is None:
        raise HTTPException(
            status_code=503,
            detail="Nenhuma chave de API configurada. Defina OPENAI_API_KEY ou ANTHROPIC_API_KEY no arquivo .env.",
        )
    name, model = selected
    system = build_system_prompt(req)
    history = [m.model_dump() for m in req.messages[-20:]]
    if name == "openai":
        return name, client.build_request(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={
                "model": model,
                "stream": True,
                "messages": [{"role": "system", "content": system}, *history],
            },
        )
    return name, client.build_request(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "stream": True,
            "max_tokens": 4096,
            "system": system,
            "messages": history,
        },
    )


def extract_text(name: str, payload: dict) -> str:
    if name == "openai":
        choices = payload.get("choices") or []
        if choices:
            return choices[0].get("delta", {}).get("content") or ""
        return ""
    if payload.get("type") == "content_block_delta":
        return payload.get("delta", {}).get("text", "")
    return ""


background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    site = seo.configured_site_url()
    if site:
        task = asyncio.create_task(seo.auto_register(site))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
    yield


app = FastAPI(title="Criador - IA para criação de conteúdo", lifespan=lifespan)


@app.get("/api/config")
def config() -> dict:
    selected = provider()
    return {
        "configured": selected is not None,
        "provider": selected[0] if selected else None,
        "model": selected[1] if selected else None,
        "content_types": list(CONTENT_TYPES),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(
            status_code=400, detail="A última mensagem precisa ser do usuário."
        )

    client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    try:
        name, upstream_req = build_upstream_request(client, req)
        upstream = await client.send(upstream_req, stream=True)
    except HTTPException:
        await client.aclose()
        raise
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502, detail=f"Falha ao conectar no provedor: {exc}"
        ) from exc

    if upstream.status_code != 200:
        body = (await upstream.aread()).decode(errors="replace")
        await upstream.aclose()
        await client.aclose()
        try:
            message = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            message = body
        raise HTTPException(
            status_code=502,
            detail=f"Erro do provedor ({upstream.status_code}): {message}",
        )

    async def stream() -> AsyncIterator[str]:
        try:
            async for line in upstream.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                text = extract_text(name, json.loads(data))
                if text:
                    yield text
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(stream(), media_type="text/plain; charset=utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = (BASE_DIR / "static" / "index.html").read_text()
    site = seo.configured_site_url() or ""
    return page.replace("{{SITE_URL}}", html.escape(site)).replace(
        "<!-- SEO_VERIFICATION -->", seo.verification_meta_tags()
    )


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    site = seo.configured_site_url()
    rules = "User-agent: *\nAllow: /\nDisallow: /api/\n"
    return rules + (f"\nSitemap: {site}/sitemap.xml\n" if site else "")


@app.get("/sitemap.xml")
def sitemap() -> Response:
    site = seo.configured_site_url()
    if site is None:
        raise HTTPException(status_code=404, detail="Defina SITE_URL.")
    lastmod = datetime.fromtimestamp(
        (BASE_DIR / "static" / "index.html").stat().st_mtime, tz=timezone.utc
    ).date()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        f"    <loc>{html.escape(site)}/</loc>\n"
        f"    <lastmod>{lastmod.isoformat()}</lastmod>\n"
        "    <changefreq>weekly</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "favicon.svg", media_type="image/svg+xml")


@app.get("/{key}.txt", response_class=PlainTextResponse)
def indexnow_key_file(key: str, request: Request) -> str:
    expected = seo.indexnow_key(
        seo.configured_site_url() or str(request.base_url).rstrip("/")
    )
    if key != expected:
        raise HTTPException(status_code=404)
    return expected


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
