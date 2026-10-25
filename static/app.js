"use strict";

const els = {
  newChat: document.getElementById("new-chat"),
  convList: document.getElementById("conv-list"),
  provider: document.getElementById("provider"),
  model: document.getElementById("model"),
  note: document.getElementById("model-note"),
  messages: document.getElementById("messages"),
  composer: document.getElementById("composer"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
};

const state = { conversationId: null, busy: false, modelsToken: 0, unavailable: [] };

// ---------- storage helpers ----------

function storeGet(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function storeSet(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
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
    if (para.length) { out.push(para.join("<br>")); para = []; }
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
  els.messages.scrollTop = els.messages.scrollHeight;
}

function clearMessages() {
  els.messages.textContent = "";
}

function showEmpty() {
  clearMessages();
  const d = document.createElement("div");
  d.className = "empty";
  d.textContent = "Bir sohbet başlatın.";
  els.messages.appendChild(d);
}

function removeEmpty() {
  const e = els.messages.querySelector(".empty");
  if (e) e.remove();
}

function addUserBubble(text) {
  removeEmpty();
  const d = document.createElement("div");
  d.className = "msg user";
  d.textContent = text;
  els.messages.appendChild(d);
  scrollToBottom();
  return d;
}

function addAssistantBubble(text) {
  removeEmpty();
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
  removeEmpty();
  const det = document.createElement("details");
  det.className = "tool";
  const sum = document.createElement("summary");
  sum.textContent = "Araç: " + (name || "?");
  const pre = document.createElement("pre");
  pre.textContent = result == null ? "" : String(result);
  det.appendChild(sum);
  det.appendChild(pre);
  els.messages.appendChild(det);
  scrollToBottom();
}

function addErrorLine(message) {
  removeEmpty();
  const d = document.createElement("div");
  d.className = "error-line";
  d.textContent = "Hata: " + message;
  els.messages.appendChild(d);
  scrollToBottom();
}

function renderHistory(messages) {
  clearMessages();
  if (!messages || !messages.length) { showEmpty(); return; }
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

async function loadProviders() {
  let providers = [];
  try {
    providers = await api("/api/providers");
  } catch (e) {
    addErrorLine("Sağlayıcılar yüklenemedi: " + e.message);
  }
  els.provider.textContent = "";
  state.unavailable = providers
    .filter((p) => !p.ready && p.reason)
    .map((p) => p.name + ": " + p.reason);
  for (const p of providers) {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.ready ? p.name : p.name + " (kullanılamıyor)";
    opt.disabled = !p.ready;
    if (!p.ready && p.reason) opt.title = p.reason;
    els.provider.appendChild(opt);
  }
  const stored = storeGet("meclaw.provider");
  const usable = (n) => providers.find((p) => p.name === n && p.ready);
  const first = providers.find((p) => p.ready);
  const pick = usable(stored) ? stored : first ? first.name : providers.length ? providers[0].name : "";
  if (pick) els.provider.value = pick;
  await loadModels(pick === stored ? storeGet("meclaw.model") : null);
}

function setNote(text) {
  // Reasons for unavailable providers are not visible on disabled <option>s, so show them here.
  const full = [text].concat(state.unavailable).filter(Boolean).join(" · ");
  els.note.textContent = full;
  els.note.hidden = !full;
}

async function loadModels(preferModel) {
  const token = ++state.modelsToken;
  const provider = els.provider.value;
  els.model.textContent = "";
  setNote("");
  if (!provider) return;
  let models;
  try {
    const data = await api("/api/models?provider=" + encodeURIComponent(provider));
    models = data.models || [];
  } catch (e) {
    if (token === state.modelsToken) setNote(e.message);
    return;
  }
  if (token !== state.modelsToken) return;
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    els.model.appendChild(opt);
  }
  if (preferModel && models.includes(preferModel)) els.model.value = preferModel;
  else if (models.length) els.model.value = models[0];
  setNote("");
}

els.provider.addEventListener("change", async () => {
  storeSet("meclaw.provider", els.provider.value);
  await loadModels(null);
  if (els.model.value) storeSet("meclaw.model", els.model.value);
});

els.model.addEventListener("change", () => {
  if (els.model.value) storeSet("meclaw.model", els.model.value);
});

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
  refreshConversations();
  els.input.focus();
}

async function openConversation(id) {
  if (state.busy) return;
  let conv;
  try { conv = await api("/api/conversations/" + encodeURIComponent(id)); }
  catch (e) { addErrorLine(e.message); return; }
  state.conversationId = conv.id;
  renderHistory(conv.messages);
  if (conv.provider) {
    const opt = Array.from(els.provider.options).find((o) => o.value === conv.provider && !o.disabled);
    if (opt) {
      els.provider.value = conv.provider;
      await loadModels(conv.model || null);
    }
  } else if (conv.model && Array.from(els.model.options).some((o) => o.value === conv.model)) {
    els.model.value = conv.model;
  }
  refreshConversations();
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

function setBusy(busy) {
  state.busy = busy;
  els.send.disabled = busy;
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
  const provider = els.provider.value;
  const model = els.model.value;
  if (!provider || !model) { addErrorLine("Önce bir sağlayıcı ve model seçin."); return; }

  setBusy(true);
  try {
    if (!state.conversationId) {
      const conv = await api("/api/conversations", { method: "POST" });
      state.conversationId = conv.id;
    }
    els.input.value = "";
    addUserBubble(text);

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
    let bubble = null;
    const handle = (ev) => {
      if (!ev) return;
      if (ev.name === "text") {
        if (!bubble) bubble = addAssistantBubble("");
        appendAssistantText(bubble, ev.data.text || "");
      } else if (ev.name === "tool") {
        bubble = null;
        addToolTag(ev.data.name, ev.data.result);
      } else if (ev.name === "error") {
        bubble = null;
        addErrorLine(ev.data.message || "Bilinmeyen hata");
      } else if (ev.name === "done") {
        refreshConversations();
      }
    };
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        handle(parseSse(block));
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) handle(parseSse(buffer));
  } catch (e) {
    addErrorLine(e.message);
  } finally {
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

els.newChat.addEventListener("click", newChat);

// ---------- init ----------

showEmpty();
loadProviders().then(refreshConversations);
