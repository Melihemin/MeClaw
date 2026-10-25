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

function addToolTag(name, result) {
  setEmpty(false);
  const det = document.createElement("details");
  det.className = "tool";
  const sum = document.createElement("summary");
  sum.textContent = "🛠 " + (name || "araç");
  const pre = document.createElement("pre");
  pre.textContent = result == null ? "" : String(result);
  det.appendChild(sum);
  det.appendChild(pre);
  els.messages.appendChild(det);
  scrollToBottom();
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
      } else if (ev.name === "tool") {
        settle();
        addToolTag(ev.data.name, ev.data.result);
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
    els.clearKey, els.resetPrompt];
  serverFields.forEach((el) => { el.disabled = !s; });
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
}

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
  if (typeof els.dialog.showModal === "function") els.dialog.showModal();
  else els.dialog.setAttribute("open", "");
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
    clear_openai_api_key: state.clearKey,
  };
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
  await loadProviders();
  if (!isUsable(state.provider, state.model) || !state.conversationId) applyDefaultSelection();
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
