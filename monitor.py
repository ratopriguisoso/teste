import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

import seo_audit

log = logging.getLogger("uvicorn.error")

MAX_HISTORY = 30
MAX_ALERTS = 30


def interval_minutes() -> int:
    try:
        return max(5, int(os.environ.get("MONITOR_INTERVAL_MINUTES", "360")))
    except ValueError:
        return 360


def max_sites() -> int:
    try:
        return int(os.environ.get("MONITOR_MAX_SITES", "20"))
    except ValueError:
        return 20


class MonitorError(Exception):
    pass


class Monitor:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = asyncio.Lock()
        self.sites: dict[str, dict] = {}
        if path.exists():
            try:
                self.sites = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Monitor: não foi possível ler %s: %s", path, exc)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.sites, ensure_ascii=False, indent=2))
        tmp.replace(self.path)

    def snapshot(self) -> dict:
        return {
            "interval_minutes": interval_minutes(),
            "webhook": bool(os.environ.get("MONITOR_WEBHOOK_URL", "").strip()),
            "max_sites": max_sites(),
            "sites": sorted(self.sites.values(), key=lambda s: s["added_at"]),
        }

    async def add(self, raw_url: str, keyword: str = "") -> dict:
        url = seo_audit.normalize_url(raw_url)
        if url not in self.sites and len(self.sites) >= max_sites():
            raise MonitorError(
                f"Limite de {max_sites()} sites monitorados atingido. Remova um site antes."
            )
        report = await seo_audit.audit(url, keyword)
        async with self.lock:
            site = self.sites.setdefault(
                url,
                {
                    "url": url,
                    "keyword": "",
                    "added_at": int(time.time()),
                    "history": [],
                    "alerts": [],
                },
            )
            site["keyword"] = " ".join(keyword.split())[:80]
            alerts = self.apply(site, report, None)
            self.save()
        await self.notify(site, alerts)
        return site

    async def remove(self, raw_url: str) -> None:
        url = seo_audit.normalize_url(raw_url)
        async with self.lock:
            if self.sites.pop(url, None) is None:
                raise MonitorError("Esse site não está sendo monitorado.")
            self.save()

    async def check(self, url: str) -> dict:
        site = self.sites.get(url)
        if site is None:
            raise MonitorError("Esse site não está sendo monitorado.")
        report: dict | None = None
        error: str | None = None
        try:
            report = await seo_audit.audit(url, site.get("keyword", ""))
        except seo_audit.AuditError as exc:
            error = str(exc)
        async with self.lock:
            if url not in self.sites:
                return site
            alerts = self.apply(site, report, error)
            self.save()
        await self.notify(site, alerts)
        return site

    def apply(self, site: dict, report: dict | None, error: str | None) -> list[dict]:
        now = int(time.time())
        first = "last_scan_at" not in site
        previous_error = site.get("error")
        previous_problems: dict[str, str] = site.get("problems", {})
        previous_score = site.get("score")
        site["last_scan_at"] = now
        alerts: list[dict] = []

        def alert(level: str, message: str) -> None:
            alerts.append({"at": now, "level": level, "message": message})

        if report is None:
            site["error"] = error
            if not previous_error:
                alert("erro", f"Site inacessível: {error}")
        else:
            problems = {
                c["id"]: c["label"] for c in report["checks"] if c["status"] != "ok"
            }
            site.update(
                error=None,
                final_url=report["url"],
                score=report["score"],
                problems=problems,
                history=[
                    *site["history"],
                    {"at": now, "score": report["score"], "problems": len(problems)},
                ][-MAX_HISTORY:],
            )
            if first:
                alert(
                    "info",
                    f"Monitoramento iniciado: nota {report['score']}/100, "
                    f"{len(problems)} problema(s).",
                )
            else:
                if previous_error:
                    alert("ok", "O site voltou a responder.")
                for pid, label in problems.items():
                    if pid not in previous_problems:
                        alert("aviso", f"Novo problema: {label}")
                for pid, label in previous_problems.items():
                    if pid not in problems:
                        alert("ok", f"Problema resolvido: {label}")
                if previous_score is not None and report["score"] <= previous_score - 5:
                    alert(
                        "aviso",
                        f"A nota caiu de {previous_score} para {report['score']}.",
                    )
        site["alerts"] = [*alerts[::-1], *site["alerts"]][:MAX_ALERTS]
        return alerts

    async def notify(self, site: dict, alerts: list[dict]) -> None:
        webhook = os.environ.get("MONITOR_WEBHOOK_URL", "").strip()
        important = [a for a in alerts if a["level"] in {"erro", "aviso"}]
        if not webhook or not important:
            return
        text = "\n".join(
            f"🔎 Analisador de SEO — {site['url']}: {a['message']}" for a in important
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook, json={"content": text, "text": text})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Monitor: falha ao enviar alerta para o webhook: %s", exc)

    def due(self) -> list[str]:
        limit = time.time() - interval_minutes() * 60
        return [
            url
            for url, site in self.sites.items()
            if site.get("last_scan_at", 0) <= limit
        ]

    async def run_forever(self) -> None:
        while True:
            for url in self.due():
                try:
                    await self.check(url)
                except Exception:
                    log.exception("Monitor: falha ao verificar %s", url)
            await asyncio.sleep(60)
