(() => {
  const SUGGESTIONS = [
    "Quantos clientes eu tenho?",
    "Qual foi meu faturamento este mês?",
    "Quais produtos estão com estoque abaixo do mínimo?",
    "Como o sistema calcula a receita bruta do DRE?",
  ];
  const root = document.getElementById("support-chat-root");
  if (!root) return;
  const fab = document.getElementById("support-chat-fab");
  const panel = document.getElementById("support-chat-panel");
  const backBtn = document.getElementById("support-chat-back");
  const closeBtn = document.getElementById("support-chat-close");
  const viewHome = document.getElementById("support-chat-view-home");
  const viewSession = document.getElementById("support-chat-view-session");
  const viewMessages = document.getElementById("support-chat-view-messages");
  const messagesEl = document.getElementById("support-chat-messages");
  const form = document.getElementById("support-chat-form");
  const input = document.getElementById("support-chat-input");
  const sendBtn = document.getElementById("support-chat-send");
  const cancelBtn = document.getElementById("support-chat-cancel");
  const chipsEl = document.getElementById("support-chat-chips");
  const startBtn = document.getElementById("support-chat-start-btn");
  const startBtn2 = document.getElementById("support-chat-start-btn-2");
  const navHome = document.getElementById("support-chat-nav-home");
  const navMessages = document.getElementById("support-chat-nav-messages");
  const titlesEl = document.getElementById("support-chat-titles");

  let sessionId = "";
  let opened = false;
  let sending = false;
  let controller = null;

  function csrfToken() {
    const el = document.querySelector("#support-chat-form input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }
  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function renderMarkdown(text) {
    try {
      if (window.marked && window.DOMPurify) {
        return window.DOMPurify.sanitize(window.marked.parse(text));
      }
    } catch (e) { /* fallback */ }
    return escapeHtml(text).replace(/\n/g, "<br>");
  }
  function showView(name) {
    viewHome.classList.toggle("hidden", name !== "home");
    viewHome.classList.toggle("flex", name === "home");
    viewSession.classList.toggle("hidden", name !== "session");
    viewSession.classList.toggle("flex", name === "session");
    viewMessages.classList.toggle("hidden", name !== "messages");
    viewMessages.classList.toggle("flex", name === "messages");
    backBtn.classList.toggle("hidden", name !== "session");
    navHome.classList.toggle("btn-active", name === "home");
    navMessages.classList.toggle("btn-active", name === "messages");
    navHome.classList.toggle("text-primary", name === "home");
    navMessages.classList.toggle("text-primary", name === "messages");
    if (name === "session") input.focus();
  }
  function addMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = role === "user" ? "chat chat-end" : "chat chat-start";
    const bubble = document.createElement("div");
    bubble.className = role === "user" ? "chat-bubble chat-bubble-primary" : "chat-bubble";
    bubble.innerHTML = renderMarkdown(text);
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  function addTyping() {
    const el = document.createElement("div");
    el.id = "support-chat-typing";
    el.className = "chat chat-start";
    el.innerHTML = '<div class="chat-bubble"><span class="loading loading-dots loading-sm"></span></div>';
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  function removeTyping() {
    document.getElementById("support-chat-typing")?.remove();
  }
  function renderChips() {
    chipsEl.innerHTML = "";
    if (messagesEl.children.length > 0) return;
    SUGGESTIONS.forEach((s) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn btn-outline btn-xs";
      b.textContent = s;
      b.addEventListener("click", () => { input.value = s; input.focus(); });
      chipsEl.appendChild(b);
    });
  }
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Erro ${res.status}`);
    return data;
  }
  async function startNewSession() {
    try {
      startBtn.disabled = true;
      startBtn2.disabled = true;
      const data = await api("/support-chat/sessions/new/", { method: "POST", body: "{}" });
      sessionId = data.session_id || "";
      messagesEl.innerHTML = "";
      renderChips();
      showView("session");
    } catch (e) {
      messagesEl.innerHTML = "";
      addMessage("assistant", e.message || "Não foi possível abrir o chat.");
      showView("session");
    } finally {
      startBtn.disabled = false;
      startBtn2.disabled = false;
    }
  }
  async function loadTitles() {
    titlesEl.innerHTML = '<div class="p-3 text-base-content/60">Carregando conversas...</div>';
    try {
      const data = await api("/support-chat/titles/");
      const items = data.titulos || [];
      titlesEl.innerHTML = "";
      if (items.length === 0) {
        titlesEl.innerHTML = '<div class="p-3 text-base-content/60">Nenhuma conversa ainda.</div>';
        return;
      }
      items.forEach((t) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn-ghost w-full justify-start h-auto py-2 px-3";
        const date = t.atualizado_em ? new Date(t.atualizado_em) : null;
        const dateStr = date && !isNaN(date) ? date.toLocaleString("pt-BR") : "";
        b.innerHTML = `<span class="flex flex-col items-start gap-0.5 min-w-0">
          <span class="font-medium truncate max-w-full">${escapeHtml(t.titulo)}</span>
          ${dateStr ? `<span class="text-xs opacity-60">${escapeHtml(dateStr)}</span>` : ""}
        </span>`;
        b.addEventListener("click", () => loadHistory(t.session_id));
        titlesEl.appendChild(b);
      });
    } catch (e) {
      titlesEl.innerHTML = `<div class="p-3">Não foi possível carregar. ${escapeHtml(e.message || "")}</div>`;
    }
  }
  async function loadHistory(sid) {
    try {
      const data = await api(`/support-chat/history/?session_id=${encodeURIComponent(sid)}`);
      sessionId = data.session_id;
      messagesEl.innerHTML = "";
      (data.messages || []).forEach((m) => addMessage(m.role, m.text));
      renderChips();
      showView("session");
    } catch (e) {
      messagesEl.innerHTML = "";
      addMessage("assistant", e.message || "Não foi possível abrir a conversa.");
      showView("session");
    }
  }
  async function send(text) {
    if (sending) return;
    sending = true;
    sendBtn.disabled = true;
    cancelBtn.classList.remove("hidden");
    controller = new AbortController();
    addMessage("user", text);
    chipsEl.innerHTML = "";
    addTyping();
    try {
      const data = await api("/support-chat/ask/", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ pergunta: text, session_id: sessionId }),
      });
      sessionId = data.session_id || sessionId;
      removeTyping();
      addMessage("assistant", data.resposta || "Sem resposta.");
    } catch (e) {
      removeTyping();
      if (e.name === "AbortError") addMessage("assistant", "Envio cancelado.");
      else addMessage("assistant", e.message || "Não foi possível responder agora. Tente novamente.");
    } finally {
      sending = false;
      sendBtn.disabled = false;
      cancelBtn.classList.add("hidden");
      controller = null;
    }
  }

  fab.addEventListener("click", () => {
    opened = !opened;
    panel.classList.toggle("hidden", !opened);
    panel.classList.toggle("flex", opened);
    if (opened) showView("home");
  });
  closeBtn.addEventListener("click", () => {
    opened = false;
    controller?.abort();
    panel.classList.add("hidden");
    panel.classList.remove("flex");
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && opened) closeBtn.click();
  });
  backBtn.addEventListener("click", () => showView("home"));
  navHome.addEventListener("click", () => showView("home"));
  navMessages.addEventListener("click", () => { showView("messages"); loadTitles(); });
  startBtn.addEventListener("click", startNewSession);
  startBtn2.addEventListener("click", startNewSession);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || sending) return;
    input.value = "";
    send(text);
  });
  cancelBtn.addEventListener("click", () => controller?.abort());
})();
