const STORAGE_KEY = "criador.conversations";

const els = {
  messages: document.getElementById("messages"),
  welcome: document.getElementById("welcome"),
  history: document.getElementById("history"),
  form: document.getElementById("composer"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  newChat: document.getElementById("new-chat"),
  contentType: document.getElementById("content-type"),
  tone: document.getElementById("tone"),
  language: document.getElementById("language"),
  banner: document.getElementById("banner"),
  modelInfo: document.getElementById("model-info"),
};

let conversations = loadConversations();
let currentId = null;
let controller = null;

function loadConversations() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

function saveConversations() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
}

function currentConversation() {
  return conversations.find((c) => c.id === currentId) || null;
}

function renderHistory() {
  els.history.innerHTML = "";
  for (const conv of conversations) {
    const item = document.createElement("div");
    item.className = "history-item" + (conv.id === currentId ? " active" : "");
    const title = document.createElement("span");
    title.textContent = conv.title;
    const del = document.createElement("button");
    del.textContent = "×";
    del.title = "Apagar conversa";
    del.onclick = (e) => {
      e.stopPropagation();
      conversations = conversations.filter((c) => c.id !== conv.id);
      saveConversations();
      if (conv.id === currentId) startNewChat();
      else renderHistory();
    };
    item.append(title, del);
    item.onclick = () => openConversation(conv.id);
    els.history.append(item);
  }
}

function addMessageElement(role, content, { error = false } = {}) {
  els.welcome.classList.add("hidden");
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "V" : "✦";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const body = document.createElement("div");
  body.className = "content" + (error ? " error" : "");
  bubble.append(body);
  msg.append(avatar, bubble);
  els.messages.append(msg);
  setContent(body, role, content);
  if (role === "assistant" && !error) addActions(bubble, body);
  scrollToBottom();
  return body;
}

function setContent(body, role, content) {
  if (role === "user") body.textContent = content;
  else body.innerHTML = renderMarkdown(content);
}

function addActions(bubble, body) {
  const actions = document.createElement("div");
  actions.className = "actions";
  const copy = document.createElement("button");
  copy.textContent = "Copiar";
  copy.onclick = async () => {
    await navigator.clipboard.writeText(body.dataset.raw || body.innerText);
    copy.textContent = "Copiado!";
    setTimeout(() => (copy.textContent = "Copiar"), 1500);
  };
  const regen = document.createElement("button");
  regen.textContent = "Gerar de novo";
  regen.onclick = regenerate;
  actions.append(copy, regen);
  bubble.append(actions);
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function clearMessages() {
  els.messages.querySelectorAll(".msg").forEach((m) => m.remove());
}

function openConversation(id) {
  if (controller) return;
  currentId = id;
  const conv = currentConversation();
  clearMessages();
  els.welcome.classList.toggle("hidden", conv.messages.length > 0);
  els.contentType.value = conv.contentType;
  els.tone.value = conv.tone;
  els.language.value = conv.language;
  for (const m of conv.messages) {
    const body = addMessageElement(m.role, m.content);
    body.dataset.raw = m.content;
  }
  renderHistory();
}

function startNewChat() {
  if (controller) return;
  currentId = null;
  clearMessages();
  els.welcome.classList.remove("hidden");
  renderHistory();
  els.input.focus();
}

function ensureConversation(firstPrompt) {
  let conv = currentConversation();
  if (!conv) {
    conv = {
      id: crypto.randomUUID(),
      title: firstPrompt.slice(0, 60),
      messages: [],
      contentType: els.contentType.value,
      tone: els.tone.value,
      language: els.language.value,
    };
    conversations.unshift(conv);
    currentId = conv.id;
  }
  conv.contentType = els.contentType.value;
  conv.tone = els.tone.value;
  conv.language = els.language.value;
  return conv;
}

function setBusy(busy) {
  els.send.classList.toggle("hidden", busy);
  els.stop.classList.toggle("hidden", !busy);
  els.input.disabled = busy;
}

async function streamReply(conv) {
  const body = addMessageElement("assistant", "");
  body.classList.add("cursor");
  let text = "";
  controller = new AbortController();
  setBusy(true);
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: conv.messages,
        content_type: conv.contentType,
        tone: conv.tone,
        language: conv.language,
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Erro ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      text += decoder.decode(value, { stream: true });
      body.innerHTML = renderMarkdown(text);
      scrollToBottom();
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      body.classList.remove("cursor");
      body.closest(".msg").remove();
      addMessageElement("assistant", `⚠️ ${err.message}`, { error: true });
    }
  } finally {
    body.classList.remove("cursor");
    body.dataset.raw = text;
    controller = null;
    setBusy(false);
    els.input.focus();
  }
  if (text) {
    conv.messages.push({ role: "assistant", content: text });
  } else if (conv.messages.at(-1)?.role === "user") {
    conv.messages.pop();
  }
  saveConversations();
  renderHistory();
}

async function sendPrompt(prompt) {
  prompt = prompt.trim();
  if (!prompt || controller) return;
  const conv = ensureConversation(prompt);
  conv.messages.push({ role: "user", content: prompt });
  saveConversations();
  renderHistory();
  addMessageElement("user", prompt);
  els.input.value = "";
  autoresize();
  await streamReply(conv);
}

async function regenerate() {
  const conv = currentConversation();
  if (!conv || controller) return;
  if (conv.messages.at(-1)?.role === "assistant") conv.messages.pop();
  const last = [...els.messages.querySelectorAll(".msg.assistant")].at(-1);
  if (last) last.remove();
  conv.contentType = els.contentType.value;
  conv.tone = els.tone.value;
  conv.language = els.language.value;
  await streamReply(conv);
}

function autoresize() {
  els.input.style.height = "auto";
  els.input.style.height = `${els.input.scrollHeight}px`;
}

async function loadConfig() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    if (cfg.configured) {
      els.modelInfo.textContent = `Modelo: ${cfg.model} (${cfg.provider})`;
    } else {
      els.banner.textContent =
        "Nenhuma chave de API configurada. Crie um arquivo .env com OPENAI_API_KEY ou ANTHROPIC_API_KEY e reinicie o servidor.";
      els.banner.classList.remove("hidden");
    }
  } catch {
    els.banner.textContent = "Não foi possível falar com o servidor.";
    els.banner.classList.remove("hidden");
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  sendPrompt(els.input.value);
});
els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendPrompt(els.input.value);
  }
});
els.input.addEventListener("input", autoresize);
els.stop.addEventListener("click", () => controller?.abort());
els.newChat.addEventListener("click", startNewChat);
document.querySelectorAll(".examples button").forEach((btn) => {
  btn.addEventListener("click", () => {
    els.contentType.value = btn.dataset.type;
    sendPrompt(btn.dataset.prompt);
  });
});

renderHistory();
loadConfig();
els.input.focus();
