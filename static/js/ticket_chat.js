(function () {
  function buildWsUrl(baseUrl, ticketId, token) {
    if (baseUrl) {
      const normalized = baseUrl.replace(/\/$/, "");
      return `${normalized}/ws/tickets/${ticketId}/chat/?token=${encodeURIComponent(token)}`;
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws/tickets/${ticketId}/chat/?token=${encodeURIComponent(token)}`;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  window.ticketChat = function ticketChat(options) {
    return {
      draft: "",
      connectionLabel: "Conectando ao chat...",
      socket: null,
      ticketId: options.ticketId,
      token: options.token,
      baseUrl: options.baseUrl || "",
      currentUserId: options.currentUserId,

      init() {
        this.connect();
      },

      connect() {
        const url = buildWsUrl(this.baseUrl, this.ticketId, this.token);
        this.socket = new WebSocket(url);
        this.socket.addEventListener("open", () => {
          this.connectionLabel = "Chat em tempo real conectado.";
        });
        this.socket.addEventListener("close", () => {
          this.connectionLabel = "Chat desconectado. Recarregue a página para reconectar.";
        });
        this.socket.addEventListener("message", (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === "chat.snapshot" && Array.isArray(payload.messages)) {
              this.renderSnapshot(payload.messages);
            } else if (payload.type === "chat.message") {
              this.appendMessage(payload);
            }
          } catch (_err) {
            // ignore malformed
          }
        });
      },

      renderSnapshot(messages) {
        const container = this.$refs.messages;
        if (!container) return;
        if (!messages.length) {
          container.innerHTML = '<p class="text-sm text-base-content/60">Nenhuma mensagem ainda.</p>';
          return;
        }
        container.innerHTML = messages.map((message) => this.messageHtml(message)).join("");
        container.scrollTop = container.scrollHeight;
      },

      appendMessage(message) {
        const container = this.$refs.messages;
        if (!container) return;
        const empty = container.querySelector("p.text-sm");
        if (empty) empty.remove();
        container.insertAdjacentHTML("beforeend", this.messageHtml(message));
        container.scrollTop = container.scrollHeight;
      },

      messageHtml(message) {
        const mine = Number(message.author_id) === Number(this.currentUserId);
        const side = mine ? "chat-end" : "chat-start";
        const created = message.created_at ? new Date(message.created_at).toLocaleString("pt-BR") : "";
        return `
          <div class="chat ${side}">
            <div class="chat-header text-xs opacity-70">
              ${escapeHtml(message.author_username || "")}
              <time class="ml-1">${escapeHtml(created)}</time>
            </div>
            <div class="chat-bubble whitespace-pre-wrap">${escapeHtml(message.body || "")}</div>
          </div>
        `;
      },

      onSubmit(event) {
        // Let the form POST persist the message; WS broadcast updates peers.
        // Keep draft until server redirects/reloads.
        if (!this.draft.trim()) {
          event.preventDefault();
        }
      },
    };
  };
})();
