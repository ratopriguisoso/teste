"""Verifica o SEO do site publicado e cadastra ele nos buscadores.

O servidor já faz isso sozinho ao iniciar quando SITE_URL está definido;
use este comando para repetir o envio ou conferir o resultado.

Uso:
    python indexar.py                 # usa SITE_URL do .env
    python indexar.py https://meusite.com.br
"""

import asyncio
import os
import sys
import xml.etree.ElementTree as ET

import httpx

import seo
from app import BASE_DIR, load_dotenv

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def check(label: str, ok: bool, hint: str = "") -> bool:
    print(
        f"[{'OK' if ok else 'ERRO'}] {label}"
        + (f" — {hint}" if hint and not ok else "")
    )
    return ok


async def audit(client: httpx.AsyncClient, site: str) -> list[str]:
    home = await client.get(f"{site}/")
    check(
        "Página inicial responde 200",
        home.status_code == 200,
        f"status {home.status_code}",
    )
    page = home.text
    check("Tem <title>", "<title>" in page)
    check("Tem meta description", 'name="description"' in page)
    check(
        "Link canônico aponta para o site",
        f'rel="canonical" href="{site}/"' in page,
        "defina SITE_URL no servidor com o endereço público do site",
    )
    check("Página não bloqueia indexação", "noindex" not in page)

    robots = await client.get(f"{site}/robots.txt")
    check(
        "robots.txt aponta para o sitemap",
        robots.status_code == 200 and f"Sitemap: {site}/sitemap.xml" in robots.text,
    )

    sitemap = await client.get(f"{site}/sitemap.xml")
    if not check(
        "sitemap.xml disponível",
        sitemap.status_code == 200,
        f"status {sitemap.status_code}",
    ):
        return []
    root = ET.fromstring(sitemap.content)
    urls = [
        loc.text.strip()
        for loc in root.findall("sm:url/sm:loc", SITEMAP_NS)
        if loc.text
    ]
    check(f"sitemap.xml lista {len(urls)} URL(s)", bool(urls))
    return urls


async def run(site: str) -> None:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        urls = await audit(client, site)
        if not urls:
            return

        key = seo.indexnow_key(site)
        key_file = await client.get(f"{site}/{key}.txt")
        if check(
            "Chave IndexNow publicada",
            key_file.status_code == 200 and key_file.text.strip() == key,
            "o servidor precisa estar com a versão nova e o mesmo SITE_URL",
        ):
            resp = await seo.submit_indexnow(client, site, urls)
            check(
                f"IndexNow (Bing, Yandex, Seznam, Naver...) recebeu {len(urls)} URL(s)",
                resp.status_code in (200, 202),
                f"status {resp.status_code}: {resp.text[:200]}",
            )

        account = seo.load_service_account()
        if account is None:
            print(
                "[AVISO] GOOGLE_SERVICE_ACCOUNT_JSON não definido — cadastro no "
                "Google pulado (veja o README)."
            )
            return
        try:
            token = await seo.google_access_token(client, account)
            for step in await seo.register_google(client, token, site):
                check(step, True)
        except httpx.HTTPStatusError as exc:
            check(
                "Cadastro no Google",
                False,
                f"status {exc.response.status_code}: {exc.response.text[:300]}",
            )


def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    site = (
        (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SITE_URL", ""))
        .strip()
        .rstrip("/")
    )
    if not site.startswith(("http://", "https://")):
        sys.exit(
            "Informe o endereço público do site: python indexar.py https://meusite.com.br"
        )
    asyncio.run(run(site))


if __name__ == "__main__":
    main()
