import asyncio
import ipaddress
import json
import socket
import time
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (compatible; CriadorSEO/1.0; +https://github.com/ratopriguisoso/teste)"
)
MAX_HTML_BYTES = 3_000_000

Status = Literal["ok", "aviso", "erro"]
TEXT_TAGS = {"title", "h1", "script", "style", "noscript"}
HIDDEN_TAGS = {"title", "script", "style", "noscript"}


class AuditError(Exception):
    pass


@dataclass
class Check:
    id: str
    label: str
    status: Status
    detail: str
    hint: str
    weight: int


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.title = ""
        self.metas: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.h1: list[str] = []
        self.h2_count = 0
        self.images = 0
        self.images_without_alt = 0
        self.json_ld: list[str] = []
        self.hrefs: list[str] = []
        self.words = 0
        self._stack: list[tuple[str, str]] = []
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "").strip() for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key and key not in self.metas:
                self.metas[key] = a.get("content", "")
        elif tag == "link":
            for rel in a.get("rel", "").lower().split():
                self.links.setdefault(rel, a.get("href", ""))
        elif tag == "img":
            self.images += 1
            if not a.get("alt"):
                self.images_without_alt += 1
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        elif tag == "h2":
            self.h2_count += 1
        if tag in TEXT_TAGS:
            kind = (
                "json_ld"
                if tag == "script" and a.get("type") == "application/ld+json"
                else tag
            )
            self._stack.append((tag, kind))
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if not self._stack or self._stack[-1][0] != tag:
            return
        _, kind = self._stack.pop()
        text = " ".join("".join(self._buffer).split())
        if kind == "title" and not self.title:
            self.title = text
        elif kind == "h1":
            self.h1.append(text)
        elif kind == "json_ld":
            self.json_ld.append("".join(self._buffer))
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._buffer.append(data)
            if self._stack[-1][0] in HIDDEN_TAGS:
                return
        self.words += len(data.split())


def normalize_url(raw: str) -> str:
    url = raw.strip()
    if not url:
        raise AuditError("Informe o endereço do site.")
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AuditError("Endereço inválido. Exemplo: https://meusite.com.br")
    return url


async def ensure_public_host(host: str) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, None, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise AuditError(f"Não encontrei o domínio {host}.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise AuditError("Só é possível analisar sites públicos na internet.")


async def guard_request(request: httpx.Request) -> None:
    await ensure_public_host(request.url.host)


def check(
    id: str, label: str, status: Status, detail: str, hint: str = "", weight: int = 5
) -> Check:
    return Check(id, label, status, detail, hint if status != "ok" else "", weight)


def length_check(
    id: str, label: str, text: str, good: tuple[int, int], hint: str, weight: int
) -> Check:
    if not text:
        return check(id, label, "erro", "Não encontrado.", hint, weight)
    size = len(text)
    lo, hi = good
    status: Status = "ok" if lo <= size <= hi else "aviso"
    return check(
        id,
        label,
        status,
        f"{size} caracteres: “{text[:200]}”",
        f"O ideal é entre {lo} e {hi} caracteres. {hint}",
        weight,
    )


def valid_json_ld(blocks: list[str]) -> list[str]:
    types: list[str] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if isinstance(item, dict) and item.get("@type"):
                kind = item["@type"]
                types.extend(kind if isinstance(kind, list) else [str(kind)])
    return types


def analyze_page(
    page: PageParser, final_url: str, resp: httpx.Response, elapsed: float
) -> list[Check]:
    host = urlparse(final_url).netloc
    checks: list[Check] = []

    checks.append(
        check(
            "https",
            "Site seguro (HTTPS)",
            "ok" if final_url.startswith("https://") else "erro",
            final_url,
            "Ative HTTPS (certificado grátis com Let's Encrypt ou Cloudflare). O Google prioriza sites seguros.",
            10,
        )
    )
    redirects = len(resp.history)
    checks.append(
        check(
            "status",
            "Página responde normalmente",
            "ok"
            if resp.status_code == 200 and redirects <= 1
            else "aviso"
            if resp.status_code == 200
            else "erro",
            f"Status {resp.status_code}"
            + (f" após {redirects} redirecionamento(s)" if redirects else ""),
            "A página precisa responder 200 com no máximo um redirecionamento.",
            10,
        )
    )
    checks.append(
        check(
            "speed",
            "Tempo de resposta do servidor",
            "ok" if elapsed < 1.0 else "aviso" if elapsed < 3.0 else "erro",
            f"{elapsed:.2f} s",
            "Use cache, CDN e uma hospedagem mais rápida. Sites lentos perdem posição e visitantes.",
            6,
        )
    )
    size_kb = len(resp.content) / 1024
    checks.append(
        check(
            "size",
            "Tamanho do HTML",
            "ok" if size_kb < 300 else "aviso",
            f"{size_kb:.0f} KB",
            "Reduza o HTML (remova código embutido desnecessário) para carregar mais rápido.",
            3,
        )
    )

    robots_meta = (
        page.metas.get("robots", "") + " " + resp.headers.get("x-robots-tag", "")
    ).lower()
    checks.append(
        check(
            "indexable",
            "Página liberada para o Google",
            "erro" if "noindex" in robots_meta else "ok",
            "Bloqueada por noindex."
            if "noindex" in robots_meta
            else "Sem bloqueio de indexação.",
            "Remova o “noindex” da meta robots ou do cabeçalho X-Robots-Tag.",
            10,
        )
    )
    checks.append(
        length_check(
            "title",
            "Título da página (<title>)",
            page.title,
            (30, 60),
            "Coloque a palavra-chave principal no começo e o nome da marca no fim.",
            10,
        )
    )
    checks.append(
        length_check(
            "description",
            "Meta description",
            page.metas.get("description", ""),
            (70, 160),
            "É o texto que aparece no Google abaixo do título: resuma a página e convide ao clique.",
            8,
        )
    )
    h1_count = len(page.h1)
    checks.append(
        check(
            "h1",
            "Título principal (H1)",
            "ok" if h1_count == 1 else "aviso" if h1_count > 1 else "erro",
            f"{h1_count} H1" + (f": “{page.h1[0][:120]}”" if page.h1 else ""),
            "Use exatamente um <h1> por página, com a palavra-chave principal.",
            7,
        )
    )
    checks.append(
        check(
            "headings",
            "Subtítulos (H2)",
            "ok" if page.h2_count else "aviso",
            f"{page.h2_count} H2",
            "Organize o conteúdo em seções com <h2> — ajuda o Google a entender os tópicos.",
            3,
        )
    )
    checks.append(
        check(
            "content",
            "Quantidade de texto",
            "ok" if page.words >= 300 else "aviso",
            f"{page.words} palavras",
            "Páginas com pouco texto costumam ranquear mal. Escreva ao menos 300 palavras úteis.",
            5,
        )
    )
    missing_alt = page.images_without_alt
    checks.append(
        check(
            "alt",
            "Imagens com texto alternativo (alt)",
            "ok"
            if missing_alt == 0
            else "aviso"
            if missing_alt <= page.images / 2
            else "erro",
            f"{page.images - missing_alt} de {page.images} imagens com alt"
            if page.images
            else "Nenhuma imagem.",
            "Descreva cada imagem no atributo alt — conta para o Google Imagens e acessibilidade.",
            4,
        )
    )
    checks.append(
        check(
            "viewport",
            "Adaptado para celular (viewport)",
            "ok" if "width=device-width" in page.metas.get("viewport", "") else "erro",
            page.metas.get("viewport", "") or "Não encontrado.",
            'Adicione <meta name="viewport" content="width=device-width, initial-scale=1">. O Google indexa a versão mobile.',
            8,
        )
    )
    checks.append(
        check(
            "lang",
            "Idioma declarado",
            "ok" if page.lang else "aviso",
            page.lang or "Não encontrado.",
            'Adicione lang="pt-BR" na tag <html>.',
            2,
        )
    )
    canonical = page.links.get("canonical", "")
    canonical_abs = urljoin(final_url, canonical) if canonical else ""
    checks.append(
        check(
            "canonical",
            "Link canônico",
            "ok"
            if canonical_abs and urlparse(canonical_abs).netloc == host
            else "aviso",
            canonical_abs or "Não encontrado.",
            'Adicione <link rel="canonical" href="..."> apontando para o endereço oficial da página.',
            4,
        )
    )
    og = [k for k in ("og:title", "og:description", "og:image") if page.metas.get(k)]
    checks.append(
        check(
            "og",
            "Prévia ao compartilhar (Open Graph)",
            "ok" if len(og) == 3 else "aviso" if og else "erro",
            f"{len(og)} de 3 tags (og:title, og:description, og:image)",
            "Com essas tags o link aparece com imagem e título no WhatsApp, Facebook e LinkedIn.",
            4,
        )
    )
    types = valid_json_ld(page.json_ld)
    checks.append(
        check(
            "schema",
            "Dados estruturados (schema.org)",
            "ok" if types else "aviso",
            ", ".join(dict.fromkeys(types)) if types else "Nenhum JSON-LD válido.",
            "Adicione JSON-LD (Organization, LocalBusiness, Product, Article...) para ganhar destaques no Google.",
            4,
        )
    )
    checks.append(
        check(
            "favicon",
            "Ícone do site (favicon)",
            "ok" if page.links.get("icon") or page.links.get("shortcut") else "aviso",
            page.links.get("icon") or page.links.get("shortcut") or "Não declarado.",
            "O favicon aparece ao lado do seu site nos resultados do Google.",
            2,
        )
    )
    internal = {
        urljoin(final_url, href).split("#")[0]
        for href in page.hrefs
        if urlparse(urljoin(final_url, href)).netloc == host
    }
    checks.append(
        check(
            "links",
            "Links internos",
            "ok" if len(internal) >= 3 else "aviso",
            f"{len(internal)} links para outras páginas do site",
            "Ligue suas páginas entre si (menu, rodapé, textos) para o Google descobrir todo o site.",
            3,
        )
    )
    return checks


async def analyze_robots(
    client: httpx.AsyncClient, origin: str
) -> tuple[list[Check], list[str]]:
    try:
        resp = await client.get(f"{origin}/robots.txt")
    except httpx.HTTPError:
        resp = None
    sitemaps: list[str] = []
    blocked = False
    if resp is not None and resp.status_code == 200:
        agent_all = False
        for line in resp.text.splitlines():
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "sitemap" and value:
                sitemaps.append(value)
            elif key == "user-agent":
                agent_all = value == "*"
            elif key == "disallow" and agent_all and value == "/":
                blocked = True
    found = resp is not None and resp.status_code == 200
    status: Status = "erro" if blocked else "ok" if found else "aviso"
    detail = (
        "Bloqueia o site inteiro (Disallow: /)."
        if blocked
        else "Encontrado."
        if found
        else "Não encontrado."
    )
    return [
        check(
            "robots",
            "robots.txt",
            status,
            detail,
            "Crie /robots.txt liberando o site e indicando o sitemap: “User-agent: *”, “Allow: /”, “Sitemap: …/sitemap.xml”.",
            5,
        )
    ], sitemaps


async def analyze_sitemap(
    client: httpx.AsyncClient, origin: str, sitemaps: list[str]
) -> Check:
    candidates = list(dict.fromkeys([*sitemaps, f"{origin}/sitemap.xml"]))[:3]
    for candidate in candidates:
        try:
            resp = await client.get(candidate)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200 and "<loc>" in resp.text:
            count = resp.text.count("<loc>")
            return check(
                "sitemap",
                "Sitemap (sitemap.xml)",
                "ok" if candidate in sitemaps else "aviso",
                f"{candidate} com {count} endereço(s)",
                "Informe o sitemap no robots.txt e envie no Google Search Console e Bing Webmaster Tools.",
                6,
            )
    return check(
        "sitemap",
        "Sitemap (sitemap.xml)",
        "erro",
        "Não encontrado.",
        "Crie um sitemap.xml com todas as páginas e envie no Google Search Console.",
        6,
    )


def score(checks: list[Check]) -> int:
    total = sum(c.weight for c in checks)
    earned = sum(
        c.weight if c.status == "ok" else c.weight / 2 if c.status == "aviso" else 0
        for c in checks
    )
    return round(100 * earned / total) if total else 0


async def audit(raw_url: str) -> dict:
    url = normalize_url(raw_url)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=8.0),
        follow_redirects=True,
        max_redirects=5,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
        },
        event_hooks={"request": [guard_request]},
    ) as client:
        started = time.perf_counter()
        try:
            resp = await client.get(url)
        except AuditError:
            raise
        except httpx.HTTPError as exc:
            raise AuditError(f"Não consegui acessar {url}: {exc}") from exc
        elapsed = time.perf_counter() - started
        if "html" not in resp.headers.get("content-type", "html"):
            raise AuditError("O endereço não retornou uma página HTML.")
        final_url = str(resp.url)
        parsed = urlparse(final_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        page = PageParser()
        page.feed(resp.text[:MAX_HTML_BYTES])
        checks = analyze_page(page, final_url, resp, elapsed)
        robots_checks, sitemaps = await analyze_robots(client, origin)
        checks += robots_checks
        checks.append(await analyze_sitemap(client, origin, sitemaps))

    return {
        "url": final_url,
        "score": score(checks),
        "title": page.title,
        "description": page.metas.get("description", ""),
        "h1": page.h1[:3],
        "checks": [asdict(c) for c in checks],
    }
