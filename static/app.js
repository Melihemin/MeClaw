"use strict";

const $ = (id) => document.getElementById(id);

const els = {
  app: $("app"),
  main: $("main"),
  newChat: $("new-chat"),
  newChatTop: $("new-chat-top"),
  convList: $("conv-list"),
  openSidebar: $("open-sidebar"),
  closeSidebar: $("close-sidebar"),
  scrim: $("scrim"),
  modelButton: $("model-button"),
  modelLabel: $("model-label"),
  modelMenu: $("model-menu"),
  banner: $("banner"),
  bannerText: $("banner-text"),
  bannerSettings: $("banner-settings"),
  thread: $("thread"),
  messages: $("messages"),
  composer: $("composer"),
  input: $("input"),
  send: $("send"),
  openSettings: $("open-settings"),
  dialog: $("settings"),
  settingsForm: $("settings-form"),
  settingsClose: $("settings-close"),
  settingsCancel: $("settings-cancel"),
  settingsSave: $("settings-save"),
  settingsStatus: $("settings-status"),
  setTheme: $("set-theme"),
  setOllama: $("set-ollama"),
  setKey: $("set-key"),
  keyStatus: $("key-status"),
  clearKey: $("clear-key"),
  setDefaultProvider: $("set-default-provider"),
  setDefaultModel: $("set-default-model"),
  knownModels: $("known-models"),
  setPrompt: $("set-prompt"),
  resetPrompt: $("reset-prompt"),
  setWorkspace: $("set-workspace"),
  resetWorkspace: $("reset-workspace"),
  toolsSection: $("tools-section"),
  setInternet: $("set-internet"),
  setMemory: $("set-memory"),
  memorySection: $("memory-section"),
  memoryOffNote: $("memory-off-note"),
  memoryList: $("memory-list"),
  memoryNew: $("memory-new"),
  memoryAdd: $("memory-add"),
  memoryClear: $("memory-clear"),
  openFiles: $("open-files"),
  files: $("files"),
  filesUpload: $("files-upload"),
  filesOpen: $("files-open"),
  filesRefresh: $("files-refresh"),
  filesClose: $("files-close"),
  filesCrumbs: $("files-crumbs"),
  filesList: $("files-list"),
  filesStatus: $("files-status"),
  preview: $("files-preview"),
  previewBack: $("preview-back"),
  previewName: $("preview-name"),
  previewDownload: $("preview-download"),
  previewBody: $("preview-body"),
};

const state = {
  conversationId: null,
  busy: false,
  providers: [],      // [{name, ready, reason}]
  models: {},         // provider name -> [model]
  modelErrors: {},    // provider name -> message
  provider: "",
  model: "",
  settings: null,     // GET /api/settings payload, or null when unavailable
  clearKey: false,
  filesPath: "",      // folder shown in the Files panel, relative to the workspace
  memories: [],       // [{id, content, created_at, updated_at}]
  editingMemory: null, // id of the memory row being edited inline
};

// ---------- storage helpers ----------

function storeGet(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function storeSet(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
}

// ---------- theme ----------

function currentTheme() {
  const t = storeGet("meclaw.theme");
  return t === "light" || t === "dark" ? t : "system";
}

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") document.documentElement.setAttribute("data-theme", theme);
  else document.documentElement.removeAttribute("data-theme");
}

// ---------- markdown ----------

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(escaped) {
  // Odd segments between backticks are inline code; the rest gets bold.
  return escaped.split("`").map((seg, i, arr) => {
    if (i % 2 === 1 && i < arr.length - 1) return "<code>" + seg + "</code>";
    const text = i % 2 === 1 ? "`" + seg : seg;
    return text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  }).join("");
}

function renderBlockText(escaped) {
  const lines = escaped.split("\n");
  const out = [];
  let list = null;
  let listTag = "ul";
  let para = [];
  const flushPara = () => {
    if (para.length) { out.push("<p>" + para.join("<br>") + "</p>"); para = []; }
  };
  const flushList = () => {
    if (list) { out.push("<" + listTag + ">" + list.join("") + "</" + listTag + ">"); list = null; }
  };
  for (const line of lines) {
    const m = /^\s*(?:([-*])|(\d+\.)) (.*)$/.exec(line);
    if (m) {
      flushPara();
      const tag = m[1] ? "ul" : "ol";
      if (list && listTag !== tag) flushList();
      listTag = tag;
      (list = list || []).push("<li>" + renderInline(m[3]) + "</li>");
    } else if (!line.trim()) {
      flushList();
      flushPara();
    } else {
      flushList();
      para.push(renderInline(line));
    }
  }
  flushList();
  flushPara();
  return out.join("");
}

function renderMarkdown(text) {
  const escaped = escapeHtml(text);
  const parts = escaped.split("```");
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      const code = part.replace(/^[^\n]*\n/, "");
      return "<pre><code>" + code.replace(/\n$/, "") + "</code></pre>";
    }
    return renderBlockText(part);
  }).join("");
}

// ---------- message rendering ----------

function scrollToBottom() {
  els.thread.scrollTop = els.thread.scrollHeight;
}

function setEmpty(empty) {
  els.main.classList.toggle("is-empty", empty);
}

function showEmpty() {
  els.messages.textContent = "";
  setEmpty(true);
}

function addUserBubble(text) {
  setEmpty(false);
  const d = document.createElement("div");
  d.className = "msg user";
  d.textContent = text;
  els.messages.appendChild(d);
  scrollToBottom();
  return d;
}

function addAssistantBubble(text) {
  setEmpty(false);
  const d = document.createElement("div");
  d.className = "msg assistant";
  d._raw = text || "";
  d.innerHTML = renderMarkdown(d._raw);
  els.messages.appendChild(d);
  scrollToBottom();
  return d;
}

function appendAssistantText(bubble, text) {
  bubble._raw += text;
  bubble.innerHTML = renderMarkdown(bubble._raw);
  scrollToBottom();
}

const DENIED_PREFIX = "Denied by the user:";

// One label for a tool call, used for live events and for history alike.
function toolLabel(name, result) {
  const n = name || "araç";
  if (n === "remember" && typeof result === "string" && result.startsWith("Saved memory")) return "📝 Hafıza güncellendi";
  if (n === "forget" && typeof result === "string" && result.startsWith("Forgot memory")) return "📝 Hafızadan silindi";
  if (typeof result === "string" && result.startsWith(DENIED_PREFIX)) return "🚫 " + n;
  if (n === "fetch_url" || n === "web_search") return "🌐 " + n;
  return "🛠 " + n;
}

function addToolTag(name, result) {
  setEmpty(false);
  const det = document.createElement("details");
  det.className = "tool";
  const sum = document.createElement("summary");
  sum.textContent = toolLabel(name, result);
  const pre = document.createElement("pre");
  pre.textContent = result == null ? "" : String(result);
  det.appendChild(sum);
  det.appendChild(pre);
  els.messages.appendChild(det);
  scrollToBottom();
}

// ---------- confirmation cards ----------

const confirmCards = new Map();  // confirm id -> card element (this stream only)

function setConfirmState(card, text, cls) {
  card._final = true;
  card.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  const st = card.querySelector(".confirm-state");
  st.textContent = text;
  st.className = "confirm-state" + (cls ? " " + cls : "");
}

async function answerConfirm(card, id, approved) {
  card.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  const st = card.querySelector(".confirm-state");
  st.textContent = "Gönderiliyor…";
  try {
    await api("/api/chat/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-MeClaw": "1" },
      body: JSON.stringify({ confirm_id: id, approved }),
    });
  } catch (e) {
    if (card._final) return;  // confirm_result already settled it
    if (e.status === 404) setConfirmState(card, "⌛ Süresi doldu", "expired");
    else {
      st.textContent = "Gönderilemedi: " + e.message;
      st.className = "confirm-state error";
      card.querySelectorAll("button").forEach((b) => { b.disabled = false; });
    }
  }
}

function addConfirmCard(data) {
  setEmpty(false);
  const card = document.createElement("div");
  card.className = "confirm-card";
  card.setAttribute("role", "group");
  card.setAttribute("aria-label", "Onay gerekiyor");
  const title = document.createElement("div");
  title.className = "confirm-title";
  title.textContent = "🛡 Onay gerekiyor";
  const desc = document.createElement("div");
  desc.className = "confirm-desc";
  desc.textContent = data.description || data.name || "";
  card.appendChild(title);
  card.appendChild(desc);
  if (data.preview) {
    const pre = document.createElement("pre");
    pre.textContent = data.preview;
    card.appendChild(pre);
  }
  const actions = document.createElement("div");
  actions.className = "confirm-actions";
  const allow = document.createElement("button");
  allow.type = "button";
  allow.className = "btn primary";
  allow.textContent = "İzin ver";
  const deny = document.createElement("button");
  deny.type = "button";
  deny.className = "btn";
  deny.textContent = "Reddet";
  const st = document.createElement("span");
  st.className = "confirm-state";
  st.setAttribute("role", "status");
  allow.addEventListener("click", () => answerConfirm(card, data.id, true));
  deny.addEventListener("click", () => answerConfirm(card, data.id, false));
  actions.appendChild(allow);
  actions.appendChild(deny);
  actions.appendChild(st);
  card.appendChild(actions);
  confirmCards.set(data.id, card);
  els.messages.appendChild(card);
  scrollToBottom();
  return card;
}

function resolveConfirmCard(data) {
  const card = confirmCards.get(data.id);
  if (!card) return;
  if (data.approved) setConfirmState(card, "✓ İzin verildi", "ok");
  else setConfirmState(card, "✗ Reddedildi", "denied");
}

// When the stream ends, a card that never got an answer can no longer be answered.
function expireOpenConfirmCards() {
  for (const card of confirmCards.values()) {
    if (!card._final) setConfirmState(card, "⌛ Süresi doldu", "expired");
  }
  confirmCards.clear();
}

function addErrorLine(message) {
  setEmpty(false);
  const d = document.createElement("div");
  d.className = "error-line";
  d.textContent = message;
  els.messages.appendChild(d);
  scrollToBottom();
}

function renderHistory(messages) {
  els.messages.textContent = "";
  if (!messages || !messages.length) { showEmpty(); return; }
  setEmpty(false);
  for (const m of messages) {
    if (m.role === "user") addUserBubble(m.content || "");
    else if (m.role === "assistant") {
      if (m.content) addAssistantBubble(m.content);
    } else if (m.role === "tool") addToolTag(m.name, m.content);
  }
}

// ---------- api ----------

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch (e) { /* ignore */ }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

// ---------- providers / models ----------

function isUsable(provider, model) {
  return Boolean(provider && model && (state.models[provider] || []).includes(model));
}

function firstUsable() {
  for (const p of state.providers) {
    const list = state.models[p.name] || [];
    if (list.length) return { provider: p.name, model: list[0] };
  }
  return null;
}

function defaultSelection() {
  const s = state.settings;
  if (s && s.default_provider) {
    const list = state.models[s.default_provider] || [];
    if (isUsable(s.default_provider, s.default_model)) return { provider: s.default_provider, model: s.default_model };
    if (!s.default_model && list.length) return { provider: s.default_provider, model: list[0] };
  }
  const p = storeGet("meclaw.provider");
  const m = storeGet("meclaw.model");
  if (isUsable(p, m)) return { provider: p, model: m };
  return firstUsable();
}

function setSelection(provider, model) {
  state.provider = provider || "";
  state.model = model || "";
  els.modelLabel.textContent = state.model ? state.model : "Model seçin";
  els.modelButton.title = state.provider ? state.provider + " · " + state.model : "";
  if (state.provider && state.model) {
    storeSet("meclaw.provider", state.provider);
    storeSet("meclaw.model", state.model);
  }
}

function applyDefaultSelection() {
  const pick = defaultSelection();
  setSelection(pick ? pick.provider : "", pick ? pick.model : "");
}

async function loadProviders() {
  let providers = [];
  try {
    providers = await api("/api/providers");
  } catch (e) {
    state.providers = [];
    renderBanner("Sağlayıcılar yüklenemedi: " + e.message);
    return;
  }
  state.providers = providers;
  state.models = {};
  state.modelErrors = {};
  await Promise.all(providers.filter((p) => p.ready).map(async (p) => {
    try {
      const data = await api("/api/models?provider=" + encodeURIComponent(p.name));
      state.models[p.name] = data.models || [];
      if (!state.models[p.name].length) state.modelErrors[p.name] = "Yüklü model yok.";
    } catch (e) {
      state.modelErrors[p.name] = e.message;
    }
  }));
  renderBanner();
}

function providerReason(p) {
  if (!p.ready) return p.reason || "Kullanılamıyor.";
  return state.modelErrors[p.name] || "";
}

function renderBanner(text) {
  let message = text || "";
  if (!message && state.providers.length && !firstUsable()) {
    message = "Kullanılabilir model yok. " + state.providers
      .map((p) => p.name + ": " + providerReason(p))
      .join(" · ");
  }
  els.bannerText.textContent = message;
  els.banner.hidden = !message;
}

function renderModelMenu() {
  const menu = els.modelMenu;
  menu.textContent = "";
  state.providers.forEach((p, index) => {
    if (index) {
      const sep = document.createElement("div");
      sep.className = "menu-sep";
      menu.appendChild(sep);
    }
    const head = document.createElement("div");
    head.className = "menu-head";
    head.textContent = p.name;
    menu.appendChild(head);
    const models = state.models[p.name] || [];
    for (const m of models) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "menu-item";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("aria-checked", String(p.name === state.provider && m === state.model));
      const label = document.createElement("span");
      label.textContent = m;
      const check = document.createElement("span");
      check.className = "check";
      check.textContent = "✓";
      item.appendChild(label);
      item.appendChild(check);
      item.addEventListener("click", () => {
        setSelection(p.name, m);
        closeModelMenu();
      });
      menu.appendChild(item);
    }
    const reason = providerReason(p);
    if (reason) {
      const r = document.createElement("div");
      r.className = "menu-reason";
      r.textContent = reason;
      menu.appendChild(r);
    }
  });
  const sep = document.createElement("div");
  sep.className = "menu-sep";
  menu.appendChild(sep);
  const settings = document.createElement("button");
  settings.type = "button";
  settings.className = "menu-item";
  settings.textContent = "Sağlayıcı ayarları…";
  settings.addEventListener("click", () => { closeModelMenu(); openSettings(); });
  menu.appendChild(settings);
}

function openModelMenu() {
  renderModelMenu();
  els.modelMenu.hidden = false;
  els.modelButton.setAttribute("aria-expanded", "true");
}

function closeModelMenu() {
  els.modelMenu.hidden = true;
  els.modelButton.setAttribute("aria-expanded", "false");
}

els.modelButton.addEventListener("click", (ev) => {
  ev.stopPropagation();
  if (els.modelMenu.hidden) openModelMenu(); else closeModelMenu();
});

document.addEventListener("click", (ev) => {
  if (!els.modelMenu.hidden && !els.modelMenu.contains(ev.target)) closeModelMenu();
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !els.modelMenu.hidden) closeModelMenu();
});

// ---------- sidebar ----------

const mobile = window.matchMedia("(max-width: 767px)");

function toggleSidebar(open) {
  if (mobile.matches) els.app.classList.toggle("sidebar-open", open);
  else els.app.classList.toggle("sidebar-collapsed", !open);
}

els.openSidebar.addEventListener("click", () => toggleSidebar(true));
els.closeSidebar.addEventListener("click", () => toggleSidebar(false));
els.scrim.addEventListener("click", () => toggleSidebar(false));

function closeSidebarOnMobile() {
  if (mobile.matches) els.app.classList.remove("sidebar-open");
}

// ---------- conversations ----------

async function refreshConversations() {
  let list = [];
  try { list = await api("/api/conversations"); } catch (e) { return; }
  els.convList.textContent = "";
  for (const c of list) {
    const li = document.createElement("li");
    li.className = "conv-item" + (c.id === state.conversationId ? " active" : "");
    const title = document.createElement("span");
    title.className = "conv-title";
    title.textContent = c.title;
    title.title = c.title;
    const del = document.createElement("button");
    del.type = "button";
    del.className = "conv-delete";
    del.textContent = "×";
    del.title = "Sohbeti sil";
    del.setAttribute("aria-label", "Sohbeti sil");
    del.addEventListener("click", (ev) => { ev.stopPropagation(); deleteConversation(c); });
    li.appendChild(title);
    li.appendChild(del);
    li.addEventListener("click", () => openConversation(c.id));
    els.convList.appendChild(li);
  }
}

function newChat() {
  if (state.busy) return;
  state.conversationId = null;
  showEmpty();
  applyDefaultSelection();
  refreshConversations();
  closeSidebarOnMobile();
  els.input.focus();
}

async function openConversation(id) {
  if (state.busy) return;
  let conv;
  try { conv = await api("/api/conversations/" + encodeURIComponent(id)); }
  catch (e) { addErrorLine(e.message); return; }
  state.conversationId = conv.id;
  renderHistory(conv.messages);
  if (isUsable(conv.provider, conv.model)) setSelection(conv.provider, conv.model);
  refreshConversations();
  closeSidebarOnMobile();
}

async function deleteConversation(c) {
  if (state.busy) return;
  if (!confirm("“" + c.title + "” sohbeti silinsin mi?")) return;
  try { await api("/api/conversations/" + encodeURIComponent(c.id), { method: "DELETE" }); }
  catch (e) { addErrorLine(e.message); return; }
  if (c.id === state.conversationId) {
    state.conversationId = null;
    showEmpty();
  }
  refreshConversations();
}

// ---------- chat ----------

function updateSendState() {
  els.send.disabled = state.busy || !els.input.value.trim();
}

function setBusy(busy) {
  state.busy = busy;
  updateSendState();
}

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
}

function parseSse(block) {
  let name = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!data.length) return null;
  try { return { name, data: JSON.parse(data.join("\n")) }; } catch (e) { return null; }
}

async function sendMessage() {
  if (state.busy) return;
  const text = els.input.value;
  if (!text.trim()) return;
  if (!state.provider || !state.model) {
    addErrorLine("Önce bir model seçin. Model yoksa Ayarlar'dan OpenAI anahtarı ekleyin ya da Ollama'yı başlatın.");
    return;
  }
  const provider = state.provider;
  const model = state.model;

  setBusy(true);
  let bubble = null;
  try {
    if (!state.conversationId) {
      const conv = await api("/api/conversations", { method: "POST" });
      state.conversationId = conv.id;
    }
    els.input.value = "";
    autosize();
    addUserBubble(text);
    bubble = addAssistantBubble("");
    bubble.classList.add("typing");

    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: state.conversationId, provider, model, message: text }),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch (e) { /* ignore */ }
      addErrorLine(typeof detail === "string" ? detail : JSON.stringify(detail));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const settle = () => {
      // Drop an empty "typing" placeholder; keep a bubble that already has text.
      if (bubble) {
        bubble.classList.remove("typing");
        if (!bubble._raw) bubble.remove();
      }
      bubble = null;
    };
    const handle = (ev) => {
      if (!ev) return;
      if (ev.name === "text") {
        if (!bubble) { bubble = addAssistantBubble(""); bubble.classList.add("typing"); }
        appendAssistantText(bubble, ev.data.text || "");
      } else if (ev.name === "confirm") {
        settle();
        addConfirmCard(ev.data);
      } else if (ev.name === "confirm_result") {
        resolveConfirmCard(ev.data);
      } else if (ev.name === "tool") {
        settle();
        addToolTag(ev.data.name, ev.data.result);
        refreshFilesSoon();
      } else if (ev.name === "error") {
        settle();
        addErrorLine(ev.data.message || "Bilinmeyen hata");
      } else if (ev.name === "done") {
        settle();
        refreshConversations();
      }
    };
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        handle(parseSse(block));
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) handle(parseSse(buffer));
    settle();
  } catch (e) {
    addErrorLine(e.message);
  } finally {
    expireOpenConfirmCards();
    if (bubble) {
      bubble.classList.remove("typing");
      if (!bubble._raw) bubble.remove();
    }
    setBusy(false);
    refreshConversations();
    els.input.focus();
  }
}

els.composer.addEventListener("submit", (ev) => { ev.preventDefault(); sendMessage(); });

els.input.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
    ev.preventDefault();
    if (!state.busy) sendMessage();
  }
});

els.input.addEventListener("input", () => { autosize(); updateSendState(); });

els.newChat.addEventListener("click", newChat);
els.newChatTop.addEventListener("click", newChat);

// ---------- settings ----------

function setSettingsStatus(text, isError) {
  els.settingsStatus.textContent = text || "";
  els.settingsStatus.classList.toggle("error", Boolean(isError));
}

function renderKeyStatus() {
  const s = state.settings;
  if (state.clearKey) {
    els.keyStatus.textContent = "Anahtar kaydedince silinecek.";
    els.clearKey.textContent = "Vazgeç";
  } else {
    els.keyStatus.textContent = s && s.openai_key_set
      ? "Tanımlı (" + (s.openai_key_hint || "gizli") + "). Değiştirmek için yeni anahtar girin."
      : "Tanımlı değil.";
    els.clearKey.textContent = "Anahtarı sil";
  }
  els.clearKey.hidden = !(s && s.openai_key_set);
  els.setKey.placeholder = s && s.openai_key_set ? "•••••••• (değiştirmek için yazın)" : "sk-...";
}

function fillSettingsForm() {
  const s = state.settings;
  els.setTheme.value = currentTheme();
  els.setKey.value = "";
  state.clearKey = false;
  const serverFields = [els.setOllama, els.setKey, els.setDefaultProvider, els.setDefaultModel, els.setPrompt,
    els.clearKey, els.resetPrompt, els.setWorkspace, els.resetWorkspace, els.setInternet, els.setMemory];
  serverFields.forEach((el) => { el.disabled = !s; });
  els.toolsSection.hidden = !s;
  els.memorySection.hidden = !s;
  if (!s) {
    setSettingsStatus("Sunucu ayarları bu ortamda düzenlenemiyor.", true);
    return;
  }
  els.setOllama.value = s.ollama_host || "";
  renderKeyStatus();

  els.setDefaultProvider.textContent = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "Son kullanılan";
  els.setDefaultProvider.appendChild(none);
  for (const name of s.providers || []) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    els.setDefaultProvider.appendChild(opt);
  }
  els.setDefaultProvider.value = s.default_provider || "";
  els.setDefaultModel.value = s.default_model || "";
  fillKnownModels();

  els.setPrompt.value = s.system_prompt || s.system_prompt_default || "";
  els.setWorkspace.value = s.workspace || "";
  els.setWorkspace.placeholder = s.workspace_default || "";
  els.setInternet.checked = Boolean(s.internet_enabled);
  els.setMemory.checked = Boolean(s.memory_enabled);
  renderMemories();
}

// ---------- memory (settings) ----------

function renderMemories() {
  const list = els.memoryList;
  list.textContent = "";
  els.memoryOffNote.hidden = els.setMemory.checked;
  els.memoryClear.hidden = !state.memories.length;
  if (!state.memories.length) {
    const li = document.createElement("li");
    li.className = "memory-empty muted";
    li.textContent = "Henüz not yok.";
    list.appendChild(li);
    return;
  }
  for (const m of state.memories) {
    const li = document.createElement("li");
    li.className = "memory-item";
    if (state.editingMemory === m.id) {
      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 500;
      input.value = m.content;
      input.setAttribute("aria-label", "Notu düzenle");
      const save = document.createElement("button");
      save.type = "button";
      save.className = "btn";
      save.textContent = "Kaydet";
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "btn";
      cancel.textContent = "İptal";
      save.addEventListener("click", () => saveMemory(m.id, input.value));
      cancel.addEventListener("click", () => { state.editingMemory = null; renderMemories(); });
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") { ev.preventDefault(); saveMemory(m.id, input.value); }
        else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); state.editingMemory = null; renderMemories(); }
      });
      li.appendChild(input);
      li.appendChild(save);
      li.appendChild(cancel);
      setTimeout(() => input.focus(), 0);
    } else {
      const text = document.createElement("span");
      text.className = "memory-text";
      text.textContent = m.content;
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "icon-btn";
      edit.textContent = "✎";
      edit.title = "Düzenle";
      edit.setAttribute("aria-label", "Notu düzenle");
      edit.addEventListener("click", () => { state.editingMemory = m.id; renderMemories(); });
      const del = document.createElement("button");
      del.type = "button";
      del.className = "icon-btn";
      del.textContent = "🗑";
      del.title = "Sil";
      del.setAttribute("aria-label", "Notu sil");
      del.addEventListener("click", () => deleteMemory(m.id));
      li.appendChild(text);
      li.appendChild(edit);
      li.appendChild(del);
    }
    list.appendChild(li);
  }
}

async function loadMemories() {
  try { state.memories = await api("/api/memories"); }
  catch (e) { state.memories = []; setSettingsStatus("Hafıza yüklenemedi: " + e.message, true); }
  state.editingMemory = null;
  renderMemories();
}

const MEMORY_WRITE = { "Content-Type": "application/json", "X-MeClaw": "1" };

async function addMemory() {
  const content = els.memoryNew.value.trim();
  if (!content) return;
  els.memoryAdd.disabled = true;
  try {
    const m = await api("/api/memories", { method: "POST", headers: MEMORY_WRITE, body: JSON.stringify({ content }) });
    state.memories.push(m);
    els.memoryNew.value = "";
    setSettingsStatus("");
    renderMemories();
  } catch (e) { setSettingsStatus(e.message, true); }
  finally { els.memoryAdd.disabled = false; }
}

async function saveMemory(id, value) {
  const content = value.trim();
  if (!content) { setSettingsStatus("Not boş olamaz.", true); return; }
  try {
    const m = await api("/api/memories/" + encodeURIComponent(id), {
      method: "PUT", headers: MEMORY_WRITE, body: JSON.stringify({ content }),
    });
    state.memories = state.memories.map((x) => (x.id === id ? m : x));
    state.editingMemory = null;
    setSettingsStatus("");
    renderMemories();
  } catch (e) {
    setSettingsStatus(e.message, true);
    if (e.status === 404) await loadMemories();
  }
}

async function deleteMemory(id) {
  try {
    await api("/api/memories/" + encodeURIComponent(id), { method: "DELETE", headers: { "X-MeClaw": "1" } });
    state.memories = state.memories.filter((x) => x.id !== id);
    setSettingsStatus("");
    renderMemories();
  } catch (e) {
    setSettingsStatus(e.message, true);
    if (e.status === 404) await loadMemories();
  }
}

async function clearMemories() {
  if (!state.memories.length) return;
  if (!confirm("Tüm hafıza notları silinsin mi?")) return;
  try {
    await api("/api/memories", { method: "DELETE", headers: { "X-MeClaw": "1" } });
    state.memories = [];
    setSettingsStatus("");
    renderMemories();
  } catch (e) { setSettingsStatus(e.message, true); }
}

els.memoryAdd.addEventListener("click", addMemory);
els.memoryClear.addEventListener("click", clearMemories);
els.memoryNew.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") { ev.preventDefault(); addMemory(); }
});
// The checkbox is saved with Kaydet; here it only toggles the "memory off" note.
els.setMemory.addEventListener("change", () => { els.memoryOffNote.hidden = els.setMemory.checked; });

function fillKnownModels() {
  els.knownModels.textContent = "";
  const provider = els.setDefaultProvider.value;
  const names = provider ? [provider] : Object.keys(state.models);
  for (const name of names) {
    for (const m of state.models[name] || []) {
      const opt = document.createElement("option");
      opt.value = m;
      els.knownModels.appendChild(opt);
    }
  }
}

async function openSettings() {
  closeSidebarOnMobile();
  setSettingsStatus("");
  try { state.settings = await api("/api/settings"); }
  catch (e) { state.settings = null; }
  fillSettingsForm();
  state.memories = [];
  state.editingMemory = null;
  if (typeof els.dialog.showModal === "function") els.dialog.showModal();
  else els.dialog.setAttribute("open", "");
  if (state.settings) loadMemories();
}

function closeSettings() {
  applyTheme(currentTheme());  // undo an unsaved theme preview
  els.dialog.close();
}

els.openSettings.addEventListener("click", openSettings);
els.bannerSettings.addEventListener("click", openSettings);
els.settingsClose.addEventListener("click", closeSettings);
els.settingsCancel.addEventListener("click", closeSettings);
els.dialog.addEventListener("cancel", (ev) => { ev.preventDefault(); closeSettings(); });
els.setTheme.addEventListener("change", () => applyTheme(els.setTheme.value));
els.setDefaultProvider.addEventListener("change", fillKnownModels);

els.clearKey.addEventListener("click", () => {
  state.clearKey = !state.clearKey;
  if (state.clearKey) els.setKey.value = "";
  renderKeyStatus();
});

els.resetPrompt.addEventListener("click", () => {
  if (state.settings) els.setPrompt.value = state.settings.system_prompt_default || "";
});

els.resetWorkspace.addEventListener("click", () => {
  if (state.settings) els.setWorkspace.value = state.settings.workspace_default || "";
});

els.settingsForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const theme = els.setTheme.value;
  storeSet("meclaw.theme", theme);
  applyTheme(theme);
  if (!state.settings) { els.dialog.close(); return; }

  const payload = {
    ollama_host: els.setOllama.value,
    default_provider: els.setDefaultProvider.value,
    default_model: els.setDefaultModel.value,
    system_prompt: els.setPrompt.value,
    internet_enabled: els.setInternet.checked,
    memory_enabled: els.setMemory.checked,
    clear_openai_api_key: state.clearKey,
  };
  const workspaceBefore = state.settings.workspace;
  // Leave the workspace alone unless it was edited, so saving never rewrites it needlessly.
  if (els.setWorkspace.value.trim() !== (workspaceBefore || "")) payload.workspace = els.setWorkspace.value;
  if (!state.clearKey && els.setKey.value.trim()) payload.openai_api_key = els.setKey.value.trim();

  els.settingsSave.disabled = true;
  setSettingsStatus("Kaydediliyor…");
  try {
    state.settings = await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    setSettingsStatus(e.message, true);
    return;
  } finally {
    els.settingsSave.disabled = false;
    els.setKey.value = "";
  }
  els.dialog.close();
  if (state.settings.workspace !== workspaceBefore) {
    state.filesPath = "";
    if (!els.files.hidden) loadFiles("");
  }
  await loadProviders();
  if (!isUsable(state.provider, state.model) || !state.conversationId) applyDefaultSelection();
});

// ---------- files panel ----------

const FILE_ICONS = [
  [/\.(png|jpe?g|gif|webp|bmp|ico|svg)$/i, "🖼️"],
  [/\.(docx?|odt|rtf)$/i, "📝"],
  [/\.(zip|rar|7z|tar|gz)$/i, "🗜️"],
  [/\.(pdf)$/i, "📕"],
  [/\.(xlsx?|csv)$/i, "📊"],
  [/\.(py|js|ts|json|html|css|md|txt|yml|yaml|toml|ini|bat|sh)$/i, "📄"],
];

function fileIcon(entry) {
  if (entry.type === "dir") return "📁";
  for (const [re, icon] of FILE_ICONS) if (re.test(entry.name)) return icon;
  return "📄";
}

function formatSize(bytes) {
  if (bytes == null) return "";
  if (bytes < 1024) return bytes + " B";
  const units = ["KB", "MB", "GB"];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return (v < 10 ? v.toFixed(1) : Math.round(v)) + " " + units[i];
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay
    ? d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}

function setFilesStatus(text, isError) {
  els.filesStatus.textContent = text || "";
  els.filesStatus.classList.toggle("error", Boolean(isError));
}

function filesUrl(endpoint, params) {
  return endpoint + "?" + new URLSearchParams(params).toString();
}

function renderCrumbs(path) {
  els.filesCrumbs.textContent = "";
  const parts = path ? path.split("/") : [];
  const add = (label, target) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.addEventListener("click", () => loadFiles(target));
    els.filesCrumbs.appendChild(b);
  };
  add("Çalışma alanı", "");
  parts.forEach((part, i) => {
    const sep = document.createElement("span");
    sep.className = "sep";
    sep.textContent = "›";
    els.filesCrumbs.appendChild(sep);
    add(part, parts.slice(0, i + 1).join("/"));
  });
}

function renderFileList(entries) {
  els.filesList.textContent = "";
  if (!entries.length) {
    const li = document.createElement("li");
    li.className = "files-empty";
    li.textContent = "Bu klasör boş. Dosya sürükleyip bırakabilirsiniz.";
    els.filesList.appendChild(li);
    return;
  }
  for (const entry of entries) {
    const li = document.createElement("li");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "file-row";
    row.title = entry.name;
    const icon = document.createElement("span");
    icon.className = "icon";
    icon.textContent = fileIcon(entry);
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = entry.name;
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = entry.type === "dir" ? formatDate(entry.modified)
      : formatSize(entry.size) + " · " + formatDate(entry.modified);
    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(meta);
    row.addEventListener("click", () => {
      if (entry.type === "dir") loadFiles(entry.path); else openPreview(entry.path);
    });
    li.appendChild(row);
    els.filesList.appendChild(li);
  }
}

async function loadFiles(path) {
  let data;
  try {
    data = await api(filesUrl("/api/files", { path: path || "" }));
  } catch (e) {
    if (path && e.status === 404) return loadFiles("");  // folder vanished: go back to the root
    setFilesStatus(e.message, true);
    return;
  }
  state.filesPath = data.path;
  renderCrumbs(data.path);
  renderFileList(data.entries);
  const count = data.entries.length;
  setFilesStatus(count ? count + " öğe" : "");
}

let refreshTimer = null;
function refreshFilesSoon() {
  if (els.files.hidden) return;
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => loadFiles(state.filesPath), 250);
}

function toggleFiles(open) {
  els.files.hidden = !open;
  els.openFiles.setAttribute("aria-expanded", String(open));
  if (open) {
    closePreview();
    loadFiles(state.filesPath);
  }
}

function closePreview() {
  els.preview.hidden = true;
  els.previewBody.textContent = "";
}

async function openPreview(path) {
  let info;
  try { info = await api(filesUrl("/api/files/preview", { path })); }
  catch (e) { setFilesStatus(e.message, true); return; }
  els.previewName.textContent = info.name;
  els.previewName.title = info.path;
  els.previewDownload.href = filesUrl("/api/files/download", { path: info.path });
  els.previewBody.textContent = "";
  if (info.kind === "text") {
    const pre = document.createElement("pre");
    pre.textContent = info.content;
    els.previewBody.appendChild(pre);
  } else if (info.kind === "docx") {
    const div = document.createElement("div");
    div.className = "doc";
    div.textContent = info.content;
    els.previewBody.appendChild(div);
  } else if (info.kind === "image") {
    const img = document.createElement("img");
    img.alt = info.name;
    img.src = filesUrl("/api/files/download", { path: info.path, inline: "1" });
    els.previewBody.appendChild(img);
  } else {
    const p = document.createElement("p");
    p.className = "preview-note";
    p.textContent = (info.kind === "too_large" ? "Önizleme için çok büyük" : "Bu dosya önizlenemiyor")
      + " (" + formatSize(info.size) + "). İndirmek için sağ üstteki düğmeyi kullanın.";
    els.previewBody.appendChild(p);
  }
  els.preview.hidden = false;
}

async function uploadFiles(fileList) {
  const filesToSend = Array.from(fileList || []);
  if (!filesToSend.length) return;
  const target = state.filesPath;
  let done = 0;
  for (const file of filesToSend) {
    setFilesStatus("Yükleniyor: " + file.name + " (" + (done + 1) + "/" + filesToSend.length + ")");
    try {
      await api(filesUrl("/api/files/upload", { path: target, name: file.name }), {
        method: "POST",
        headers: { "X-MeClaw": "1" },
        body: file,
      });
      done++;
    } catch (e) {
      setFilesStatus(file.name + ": " + e.message, true);
      await loadFiles(target);
      return;
    }
  }
  await loadFiles(target);
  setFilesStatus(done + " dosya yüklendi.");
}

els.openFiles.addEventListener("click", () => toggleFiles(els.files.hidden));
els.filesClose.addEventListener("click", () => toggleFiles(false));
els.filesRefresh.addEventListener("click", () => loadFiles(state.filesPath));
els.previewBack.addEventListener("click", closePreview);
els.filesUpload.addEventListener("change", () => {
  uploadFiles(els.filesUpload.files);
  els.filesUpload.value = "";
});

els.filesOpen.addEventListener("click", async () => {
  try {
    await api(filesUrl("/api/workspace/open", { path: state.filesPath }), {
      method: "POST",
      headers: { "X-MeClaw": "1" },
    });
  } catch (e) {
    setFilesStatus(e.message, true);
  }
});

let dragDepth = 0;
els.files.addEventListener("dragenter", (ev) => {
  if (!ev.dataTransfer || !Array.from(ev.dataTransfer.types).includes("Files")) return;
  ev.preventDefault();
  dragDepth++;
  els.files.classList.add("dragging");
});
els.files.addEventListener("dragover", (ev) => {
  if (els.files.classList.contains("dragging")) ev.preventDefault();
});
els.files.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) els.files.classList.remove("dragging");
});
els.files.addEventListener("drop", (ev) => {
  ev.preventDefault();
  dragDepth = 0;
  els.files.classList.remove("dragging");
  closePreview();
  uploadFiles(ev.dataTransfer && ev.dataTransfer.files);
});

// ---------- init ----------

async function init() {
  applyTheme(currentTheme());
  showEmpty();
  updateSendState();
  try { state.settings = await api("/api/settings"); } catch (e) { state.settings = null; }
  await loadProviders();
  applyDefaultSelection();
  await refreshConversations();
}

init();
