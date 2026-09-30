"""Verifica o SEO do site publicado e avisa os buscadores sobre as páginas.

Uso:
    python indexar.py                 # usa SITE_URL e INDEXNOW_KEY do .env
    python indexar.py https://meusite.com.br
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

import httpx

from app import BASE_DIR, indexnow_key, load_dotenv

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def check(label: str, ok: bool, hint: str = "") -> bool:
    print(
        f"[{'OK' if ok else 'ERRO'}] {label}"
        + (f" — {hint}" if hint and not ok else "")
    )
    return ok


def audit(client: httpx.Client, site: str) -> list[str]:
    home = client.get(f"{site}/")
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
        "defina SITE_URL no .env com o endereço público do site",
    )
    check("Página não bloqueia indexação", "noindex" not in page)

    robots = client.get(f"{site}/robots.txt")
    check(
        "robots.txt disponível",
        robots.status_code == 200,
        f"status {robots.status_code}",
    )
    check(
        "robots.txt aponta para o sitemap",
        f"Sitemap: {site}/sitemap.xml" in robots.text,
    )

    sitemap = client.get(f"{site}/sitemap.xml")
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


def submit_indexnow(client: httpx.Client, site: str, key: str, urls: list[str]) -> None:
    key_file = client.get(f"{site}/{key}.txt")
    if not check(
        "Arquivo de chave IndexNow publicado",
        key_file.status_code == 200 and key_file.text.strip() == key,
        "publique o site com INDEXNOW_KEY configurado antes de enviar",
    ):
        return
    host = re.sub(r"^https?://", "", site).split("/")[0]
    resp = client.post(
        INDEXNOW_ENDPOINT,
        json={
            "host": host,
            "key": key,
            "keyLocation": f"{site}/{key}.txt",
            "urlList": urls,
        },
    )
    check(
        f"IndexNow (Bing, Yandex, Seznam, Naver...) recebeu {len(urls)} URL(s)",
        resp.status_code in (200, 202),
        f"status {resp.status_code}: {resp.text[:200]}",
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

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        urls = audit(client, site)
        key = indexnow_key()
        if urls and key:
            submit_indexnow(client, site, key, urls)
        elif not key:
            print("[AVISO] INDEXNOW_KEY não definido — envio ao Bing/Yandex pulado.")

    print(
        "\nGoogle: adicione o site em https://search.google.com/search-console, "
        "confirme com GOOGLE_SITE_VERIFICATION e envie "
        f"{site}/sitemap.xml em 'Sitemaps'."
    )


if __name__ == "__main__":
    main()
