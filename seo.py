import asyncio
import hashlib
import html
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from google.auth import crypt, jwt

log = logging.getLogger("uvicorn.error")

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SITE_VERIFICATION_API = "https://www.googleapis.com/siteVerification/v1"
SEARCH_CONSOLE_API = "https://searchconsole.googleapis.com/webmasters/v3"
GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/siteverification "
    "https://www.googleapis.com/auth/webmasters"
)

google_meta_content: str | None = None


def configured_site_url() -> str | None:
    site = os.environ.get("SITE_URL", "").strip().rstrip("/")
    return site if site.startswith(("http://", "https://")) else None


def indexnow_key(site: str) -> str:
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if re.fullmatch(r"[a-zA-Z0-9-]{8,128}", key):
        return key
    host = urlparse(site).netloc.lower()
    return hashlib.sha256(f"indexnow:{host}".encode()).hexdigest()[:32]


def verification_meta_tags() -> str:
    tags = [
        ("google-site-verification", os.environ.get("GOOGLE_SITE_VERIFICATION", "")),
        ("google-site-verification", google_meta_content or ""),
        ("msvalidate.01", os.environ.get("BING_SITE_VERIFICATION", "")),
        ("yandex-verification", os.environ.get("YANDEX_SITE_VERIFICATION", "")),
    ]
    unique = dict.fromkeys((name, value.strip()) for name, value in tags)
    return "\n  ".join(
        f'<meta name="{name}" content="{html.escape(value)}" />'
        for name, value in unique
        if value
    )


def load_service_account() -> dict | None:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    try:
        if not raw and path:
            raw = Path(path).read_text()
        return json.loads(raw) if raw else None
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("SEO: conta de serviço do Google inválida: %s", exc)
        return None


async def google_access_token(client: httpx.AsyncClient, account: dict) -> str:
    now = int(time.time())
    assertion = jwt.encode(
        crypt.RSASigner.from_service_account_info(account),
        {
            "iss": account["client_email"],
            "scope": GOOGLE_SCOPES,
            "aud": GOOGLE_TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        },
    )
    resp = await client.post(
        GOOGLE_TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion.decode(),
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def fetch_google_meta_content(
    client: httpx.AsyncClient, token: str, site: str
) -> str:
    resp = await client.post(
        f"{SITE_VERIFICATION_API}/token",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "site": {"type": "SITE", "identifier": f"{site}/"},
            "verificationMethod": "META",
        },
    )
    resp.raise_for_status()
    match = re.search(r'content="([^"]+)"', resp.json()["token"])
    if not match:
        raise RuntimeError(f"Token de verificação inesperado: {resp.text}")
    return match.group(1)


async def register_google(
    client: httpx.AsyncClient, token: str, site: str
) -> list[str]:
    auth = {"Authorization": f"Bearer {token}"}
    home = f"{site}/"
    resp = await client.post(
        f"{SITE_VERIFICATION_API}/webResource",
        params={"verificationMethod": "META"},
        headers=auth,
        json={"site": {"type": "SITE", "identifier": home}},
    )
    resp.raise_for_status()
    resource = resp.json()
    done = ["site verificado no Google"]

    owner = os.environ.get("GOOGLE_OWNER_EMAIL", "").strip()
    if owner and owner not in resource.get("owners", []):
        resource["owners"] = [*resource.get("owners", []), owner]
        resp = await client.put(
            f"{SITE_VERIFICATION_API}/webResource/{quote(resource['id'], safe='')}",
            headers=auth,
            json=resource,
        )
        resp.raise_for_status()
        done.append(f"{owner} adicionado como proprietário")

    encoded_site = quote(home, safe="")
    resp = await client.put(f"{SEARCH_CONSOLE_API}/sites/{encoded_site}", headers=auth)
    resp.raise_for_status()
    sitemap = quote(f"{site}/sitemap.xml", safe="")
    resp = await client.put(
        f"{SEARCH_CONSOLE_API}/sites/{encoded_site}/sitemaps/{sitemap}", headers=auth
    )
    resp.raise_for_status()
    done.append("sitemap enviado ao Google Search Console")
    return done


async def submit_indexnow(
    client: httpx.AsyncClient, site: str, urls: list[str]
) -> httpx.Response:
    key = indexnow_key(site)
    return await client.post(
        INDEXNOW_ENDPOINT,
        json={
            "host": urlparse(site).netloc,
            "key": key,
            "keyLocation": f"{site}/{key}.txt",
            "urlList": urls,
        },
    )


async def wait_until_live(client: httpx.AsyncClient, site: str) -> bool:
    key = indexnow_key(site)
    for _ in range(30):
        try:
            resp = await client.get(f"{site}/{key}.txt")
            if resp.status_code == 200 and resp.text.strip() == key:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(10)
    return False


async def prepare_google(site: str) -> dict | None:
    global google_meta_content
    account = load_service_account()
    if account is None:
        return None
    async with httpx.AsyncClient(timeout=20.0) as client:
        token = await google_access_token(client, account)
        google_meta_content = await fetch_google_meta_content(client, token, site)
    return account


async def auto_register(site: str) -> None:
    try:
        account = await prepare_google(site)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("SEO: não foi possível preparar o Google: %s", exc)
        account = None
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        if not await wait_until_live(client, site):
            log.warning("SEO: %s não respondeu; indexação automática cancelada.", site)
            return
        try:
            resp = await submit_indexnow(client, site, [f"{site}/"])
            log.info("SEO: IndexNow respondeu %s", resp.status_code)
        except httpx.HTTPError as exc:
            log.warning("SEO: falha no IndexNow: %s", exc)
        if account is None:
            log.info(
                "SEO: defina GOOGLE_SERVICE_ACCOUNT_JSON para cadastrar no Google."
            )
            return
        try:
            token = await google_access_token(client, account)
            for step in await register_google(client, token, site):
                log.info("SEO: %s", step)
        except httpx.HTTPStatusError as exc:
            log.warning(
                "SEO: falha no Google (%s): %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("SEO: falha no Google: %s", exc)
