const seo = {
  form: document.getElementById("seo-form"),
  url: document.getElementById("seo-url"),
  keyword: document.getElementById("seo-keyword"),
  ring: document.getElementById("scan-ring"),
  scanBtn: document.getElementById("scan-btn"),
  scanBtnLabel: document.getElementById("scan-btn-label"),
  scanTitle: document.getElementById("scan-title"),
  scanSubtitle: document.getElementById("scan-subtitle"),
  progress: document.getElementById("progress"),
  progressBar: document.getElementById("progress-bar"),
  step: document.getElementById("scan-step"),
  error: document.getElementById("seo-error"),
  report: document.getElementById("seo-report"),
  score: document.getElementById("seo-score"),
  resultTitle: document.getElementById("result-title"),
  finalUrl: document.getElementById("seo-final-url"),
  fixAll: document.getElementById("fix-all"),
  monitorThis: document.getElementById("monitor-this"),
  rescan: document.getElementById("rescan"),
  fixPanel: document.getElementById("fix-panel"),
  fixList: document.getElementById("fix-list"),
  problemsTitle: document.getElementById("problems-title"),
  problemList: document.getElementById("problem-list"),
  okSummary: document.getElementById("ok-summary"),
  okList: document.getElementById("ok-list"),
  suggest: document.getElementById("seo-suggest"),
  plan: document.getElementById("seo-plan"),
  monitorInfo: document.getElementById("monitor-info"),
  monitorSites: document.getElementById("monitor-sites"),
  monitorAlerts: document.getElementById("monitor-alerts"),
  enableAlerts: document.getElementById("enable-alerts"),
};

const ICONS = { ok: "✓", aviso: "!", erro: "✕", info: "i" };
const LAST_ALERT_KEY = "seo.lastAlertAt";
let lastReport = null;
let scanning = false;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showError(message) {
  seo.error.textContent = message;
  seo.error.classList.toggle("hidden", !message);
}

async function errorMessage(res) {
  const data = await res.json().catch(() => ({}));
  const detail = Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail;
  return detail || `Erro ${res.status}`;
}

function grade(score) {
  return score >= 80 ? "good" : score >= 50 ? "mid" : "bad";
}

function setProgress(value, label) {
  seo.ring.style.setProperty("--p", value);
  seo.progressBar.style.width = `${value}%`;
  seo.scanBtnLabel.textContent = `${value}%`;
  if (label) seo.step.textContent = label;
}

function setScanning(active) {
  scanning = active;
  seo.ring.classList.toggle("scanning", active);
  seo.scanBtn.disabled = active;
  seo.rescan.disabled = active;
  seo.progress.classList.toggle("hidden", !active);
  if (active) {
    seo.scanTitle.textContent = "Escaneando…";
    seo.scanSubtitle.textContent = "Verificando tudo o que o Google avalia no seu site.";
  } else {
    seo.scanBtnLabel.textContent = lastReport ? "ESCANEAR DE NOVO" : "ESCANEAR";
    seo.ring.style.setProperty("--p", 0);
    seo.step.textContent = "";
  }
}

function copyButton(text) {
  const btn = el("button", "copy", "Copiar");
  btn.type = "button";
  btn.onclick = async () => {
    await navigator.clipboard.writeText(text);
    btn.textContent = "Copiado!";
    setTimeout(() => (btn.textContent = "Copiar"), 1500);
  };
  return btn;
}

function fixBlock(check) {
  const block = el("div", "fix-block");
  const pre = el("pre");
  pre.append(el("code", "", check.fix));
  block.append(pre, copyButton(check.fix));
  return block;
}

function checkItem(c) {
  const li = el("li", `check ${c.status}`);
  const body = el("div", "check-body");
  body.append(el("strong", "", c.label), el("div", "muted", c.detail));
  if (c.hint) body.append(el("div", "hint", c.hint));
  if (c.fix) {
    const toggle = el("button", "fix-toggle", "🛠 Corrigir");
    toggle.type = "button";
    let block = null;
    toggle.onclick = () => {
      if (block) {
        block.remove();
        block = null;
        toggle.textContent = "🛠 Corrigir";
      } else {
        block = fixBlock(c);
        body.append(block);
        toggle.textContent = "Fechar";
      }
    };
    body.append(toggle);
  }
  li.append(el("span", "icon", ICONS[c.status]), body);
  return li;
}

function renderReport(report) {
  const order = { erro: 0, aviso: 1 };
  const problems = report.checks
    .filter((c) => c.status !== "ok")
    .sort((a, b) => order[a.status] - order[b.status] || b.weight - a.weight);
  const ok = report.checks.filter((c) => c.status === "ok");

  seo.score.className = `shield ${grade(report.score)}`;
  seo.score.querySelector("span").textContent = report.score;
  seo.resultTitle.textContent = problems.length
    ? `${problems.length} problema${problems.length > 1 ? "s" : ""} encontrado${problems.length > 1 ? "s" : ""}`
    : "Nenhum problema encontrado";
  seo.finalUrl.textContent = report.url;
  seo.fixAll.classList.toggle("hidden", !problems.length);
  seo.problemsTitle.classList.toggle("hidden", !problems.length);
  seo.scanTitle.textContent = problems.length ? "Seu site precisa de atenção" : "Seu site está protegido";
  seo.scanSubtitle.textContent = `Nota de SEO ${report.score}/100 · ${ok.length} de ${report.checks.length} itens sem problema.`;

  seo.problemList.replaceChildren(...problems.map(checkItem));
  seo.okList.replaceChildren(...ok.map(checkItem));
  seo.okSummary.textContent = `✓ ${ok.length} itens sem problema`;

  seo.fixList.replaceChildren(
    ...problems
      .filter((c) => c.fix)
      .map((c) => {
        const item = el("div", `fix-item ${c.status}`);
        item.append(el("strong", "", c.label), el("div", "hint", c.hint), fixBlock(c));
        return item;
      }),
  );
  seo.fixPanel.classList.add("hidden");
  seo.plan.innerHTML = "";
  seo.report.classList.remove("hidden");
}

async function readNdjson(res, onEvent) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

async function runScan(e) {
  e?.preventDefault();
  if (scanning) return;
  if (!seo.url.value.trim()) {
    seo.url.focus();
    return;
  }
  showError("");
  setScanning(true);
  setProgress(1, "Iniciando…");
  let report = null;
  try {
    const res = await fetch("/api/seo/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: seo.url.value, keyword: seo.keyword.value }),
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    await readNdjson(res, (event) => {
      if (event.type === "step") setProgress(event.progress, event.label);
      else if (event.type === "error") throw new Error(event.message);
      else if (event.type === "report") report = event.report;
    });
    if (!report) throw new Error("A análise terminou sem resultado.");
    setProgress(100, "Concluído");
    lastReport = report;
    renderReport(report);
    const params = new URLSearchParams({ url: seo.url.value.trim() });
    history.replaceState(null, "", `?${params}`);
  } catch (err) {
    seo.report.classList.add("hidden");
    seo.scanTitle.textContent = "Não foi possível escanear";
    seo.scanSubtitle.textContent = "Confira o endereço e tente de novo.";
    lastReport = null;
    showError(err.message);
  } finally {
    setScanning(false);
  }
}

async function generatePlan() {
  if (!lastReport) return;
  seo.suggest.disabled = true;
  seo.plan.classList.add("cursor");
  seo.plan.innerHTML = "";
  let text = "";
  try {
    const res = await fetch("/api/seo/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: lastReport.url,
        score: lastReport.score,
        checks: lastReport.checks,
        keyword: seo.keyword.value,
      }),
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      text += decoder.decode(value, { stream: true });
      seo.plan.innerHTML = renderMarkdown(text);
    }
  } catch (err) {
    seo.plan.innerHTML = `<p class="error">⚠️ ${escapeHtml(err.message)}</p>`;
  } finally {
    seo.plan.classList.remove("cursor");
    seo.suggest.disabled = false;
  }
}

function timeAgo(seconds) {
  const diff = Math.max(0, Date.now() / 1000 - seconds);
  if (diff < 60) return "agora";
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return `há ${Math.floor(diff / 86400)} dia(s)`;
}

function formatInterval(minutes) {
  return minutes % 60 === 0 ? `${minutes / 60} h` : `${minutes} min`;
}

async function monitorAction(path, url, button) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "Aguarde…";
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, keyword: path === "/api/monitor" ? seo.keyword.value : "" }),
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    showError("");
  } catch (err) {
    showError(err.message);
  } finally {
    button.disabled = false;
    button.textContent = original;
    await loadMonitor();
  }
}

function siteRow(site) {
  const problems = Object.values(site.problems || {});
  const status = site.error ? "erro" : problems.length ? "aviso" : "ok";
  const row = el("div", `monitor-site ${status}`);
  const badge = el("div", `shield small ${site.error ? "bad" : grade(site.score ?? 0)}`);
  badge.append(el("span", "", site.error ? "!" : String(site.score ?? "–")));
  const info = el("div", "monitor-site-info");
  info.append(el("strong", "", site.url));
  const summary = site.error
    ? `Inacessível: ${site.error}`
    : problems.length
      ? `${problems.length} problema(s): ${problems.slice(0, 3).join(", ")}${problems.length > 3 ? "…" : ""}`
      : "Protegido — nenhum problema";
  info.append(el("div", "muted", summary));
  info.append(el("div", "muted small", `Última verificação ${site.last_scan_at ? timeAgo(site.last_scan_at) : "pendente"}`));
  const actions = el("div", "monitor-site-actions");
  const open = el("button", "", "Ver");
  open.type = "button";
  open.onclick = () => {
    seo.url.value = site.url;
    seo.keyword.value = site.keyword || "";
    window.scrollTo({ top: 0, behavior: "smooth" });
    runScan();
  };
  const check = el("button", "", "Escanear agora");
  check.type = "button";
  check.onclick = () => monitorAction("/api/monitor/check", site.url, check);
  const remove = el("button", "danger", "Remover");
  remove.type = "button";
  remove.onclick = () => monitorAction("/api/monitor/remove", site.url, remove);
  actions.append(open, check, remove);
  row.append(badge, info, actions);
  return row;
}

function notifyNewAlerts(alerts) {
  const last = Number(localStorage.getItem(LAST_ALERT_KEY) || 0);
  const newest = alerts.reduce((max, a) => Math.max(max, a.at), last);
  if (last && "Notification" in window && Notification.permission === "granted") {
    for (const a of alerts.filter((a) => a.at > last && (a.level === "erro" || a.level === "aviso"))) {
      new Notification(`Analisador de SEO: ${a.site}`, { body: a.message, icon: "/static/favicon.svg" });
    }
  }
  localStorage.setItem(LAST_ALERT_KEY, String(newest));
}

async function loadMonitor() {
  try {
    const data = await (await fetch("/api/monitor")).json();
    seo.monitorInfo.textContent =
      `Vigiamos seus sites a cada ${formatInterval(data.interval_minutes)} e avisamos quando surgir um problema de SEO` +
      (data.webhook ? " (alertas também enviados pelo webhook configurado)." : ".");
    seo.monitorSites.replaceChildren(
      ...(data.sites.length
        ? data.sites.map(siteRow)
        : [el("p", "muted", "Nenhum site monitorado ainda. Escaneie um site e clique em “Monitorar este site”.")]),
    );
    const alerts = data.sites
      .flatMap((s) => s.alerts.map((a) => ({ ...a, site: s.url })))
      .sort((a, b) => b.at - a.at);
    seo.monitorAlerts.replaceChildren(
      ...(alerts.length
        ? alerts.slice(0, 15).map((a) => {
            const li = el("li", `alert ${a.level}`);
            li.append(el("span", "icon", ICONS[a.level] || "i"));
            const text = el("div");
            text.append(el("strong", "", a.message), el("div", "muted small", `${a.site} · ${timeAgo(a.at)}`));
            li.append(text);
            return li;
          })
        : [el("li", "muted", "Nenhum alerta.")]),
    );
    notifyNewAlerts(alerts);
  } catch {
    seo.monitorInfo.textContent = "Não foi possível carregar o monitoramento.";
  }
}

function updateAlertButton() {
  if (!("Notification" in window)) {
    seo.enableAlerts.classList.add("hidden");
  } else if (Notification.permission === "granted") {
    seo.enableAlerts.textContent = "🔔 Alertas ativados";
    seo.enableAlerts.disabled = true;
  } else if (Notification.permission === "denied") {
    seo.enableAlerts.textContent = "🔕 Alertas bloqueados no navegador";
    seo.enableAlerts.disabled = true;
  }
}

seo.form.addEventListener("submit", runScan);
seo.rescan.addEventListener("click", () => runScan());
seo.suggest.addEventListener("click", generatePlan);
seo.fixAll.addEventListener("click", () => {
  seo.fixPanel.classList.remove("hidden");
  seo.fixPanel.scrollIntoView({ behavior: "smooth" });
});
seo.monitorThis.addEventListener("click", async () => {
  await monitorAction("/api/monitor", seo.url.value, seo.monitorThis);
  document.querySelector(".monitor").scrollIntoView({ behavior: "smooth" });
});
seo.enableAlerts.addEventListener("click", async () => {
  await Notification.requestPermission();
  updateAlertButton();
});

updateAlertButton();
loadMonitor();
setInterval(loadMonitor, 60000);
const initial = new URLSearchParams(location.search).get("url");
if (initial) {
  seo.url.value = initial;
  runScan();
} else {
  seo.url.focus();
}
