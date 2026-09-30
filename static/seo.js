const seo = {
  form: document.getElementById("seo-form"),
  url: document.getElementById("seo-url"),
  keyword: document.getElementById("seo-keyword"),
  submit: document.getElementById("seo-submit"),
  error: document.getElementById("seo-error"),
  report: document.getElementById("seo-report"),
  score: document.getElementById("seo-score"),
  finalUrl: document.getElementById("seo-final-url"),
  counts: document.getElementById("seo-counts"),
  checks: document.getElementById("seo-checks"),
  suggest: document.getElementById("seo-suggest"),
  plan: document.getElementById("seo-plan"),
};

const ICONS = { ok: "✓", aviso: "!", erro: "✕" };
let lastReport = null;

function showError(message) {
  seo.error.textContent = message;
  seo.error.classList.toggle("hidden", !message);
}

async function errorMessage(res) {
  const data = await res.json().catch(() => ({}));
  const detail = Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail;
  return detail || `Erro ${res.status}`;
}

function renderReport(report) {
  const grade = report.score >= 80 ? "good" : report.score >= 50 ? "mid" : "bad";
  seo.score.className = `score ${grade}`;
  seo.score.querySelector("span").textContent = report.score;
  seo.finalUrl.textContent = report.url;
  const total = (status) => report.checks.filter((c) => c.status === status).length;
  seo.counts.textContent = `${total("ok")} ok · ${total("aviso")} avisos · ${total("erro")} erros`;

  const order = { erro: 0, aviso: 1, ok: 2 };
  const sorted = [...report.checks].sort((a, b) => order[a.status] - order[b.status] || b.weight - a.weight);
  seo.checks.innerHTML = "";
  for (const c of sorted) {
    const li = document.createElement("li");
    li.className = `check ${c.status}`;
    const icon = document.createElement("span");
    icon.className = "icon";
    icon.textContent = ICONS[c.status];
    const body = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = c.label;
    const detail = document.createElement("div");
    detail.className = "muted";
    detail.textContent = c.detail;
    body.append(label, detail);
    if (c.hint) {
      const hint = document.createElement("div");
      hint.className = "hint";
      hint.textContent = c.hint;
      body.append(hint);
    }
    li.append(icon, body);
    seo.checks.append(li);
  }
  seo.plan.innerHTML = "";
  seo.report.classList.remove("hidden");
}

async function runAudit(e) {
  e.preventDefault();
  showError("");
  seo.submit.disabled = true;
  seo.submit.textContent = "Analisando…";
  try {
    const res = await fetch("/api/seo/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: seo.url.value }),
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    lastReport = await res.json();
    renderReport(lastReport);
  } catch (err) {
    seo.report.classList.add("hidden");
    showError(err.message);
  } finally {
    seo.submit.disabled = false;
    seo.submit.textContent = "Analisar";
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

seo.form.addEventListener("submit", runAudit);
seo.suggest.addEventListener("click", generatePlan);
const initial = new URLSearchParams(location.search).get("url");
if (initial) {
  seo.url.value = initial;
  seo.form.requestSubmit();
} else {
  seo.url.focus();
}
