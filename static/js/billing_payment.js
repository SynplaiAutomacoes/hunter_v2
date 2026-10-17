document.addEventListener("DOMContentLoaded", () => {
  const config = window.BILLING_PAYMENT_CONFIG || {};
  const toggleButton = document.getElementById("toggle-update-card");
  const form = document.getElementById("payment-update-form");
  const cancelButton = document.getElementById("payment-update-cancel");
  const submitButton = document.getElementById("payment-update-submit");
  const errorBox = document.getElementById("payment-update-error");
  const mount = document.getElementById("payment-update-element");
  const cardLabel = document.getElementById("current-card-label");
  const cardExp = document.getElementById("current-card-exp");

  if (!toggleButton || !form || !config.publishableKey) {
    return;
  }

  const stripe = window.Stripe(config.publishableKey);
  let elements = null;
  let paymentElement = null;
  let clientSecret = null;

  function showError(message) {
    if (!errorBox) return;
    errorBox.hidden = false;
    errorBox.textContent = message;
  }

  function clearError() {
    if (!errorBox) return;
    errorBox.hidden = true;
    errorBox.textContent = "";
  }

  function setLoading(isLoading) {
    if (!submitButton) return;
    submitButton.disabled = isLoading;
    submitButton.textContent = isLoading ? "Salvando…" : "Salvar cartão";
  }

  function ensurePaymentMountStructure() {
    if (!mount) return null;
    let host = mount.querySelector(".payment-element-host");
    if (!host || !mount.querySelector(".payment-element-loading")) {
      mount.innerHTML = `
        <div class="payment-element-loading" role="status" aria-live="polite">
          <span class="payment-element-spinner" aria-hidden="true"></span>
          <span class="payment-element-loading-text">Carregando formulário do cartão…</span>
        </div>
        <div class="payment-element-host"></div>
      `;
      host = mount.querySelector(".payment-element-host");
    }
    return host;
  }

  function showPaymentLoading(message) {
    if (!mount) return;
    ensurePaymentMountStructure();
    const text = mount.querySelector(".payment-element-loading-text");
    if (text) {
      text.textContent = message || "Carregando formulário do cartão…";
    }
    mount.classList.add("is-loading", "payment-element");
  }

  function clearPaymentLoading() {
    if (!mount) return;
    mount.classList.remove("is-loading");
  }

  function waitForPaymentElementReady(element) {
    return new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearPaymentLoading();
        resolve();
      };
      element.on("ready", finish);
      window.setTimeout(finish, 8000);
    });
  }

  async function postForm(url, fields) {
    const body = new FormData();
    body.append("csrfmiddlewaretoken", config.csrfToken || "");
    Object.entries(fields || {}).forEach(([key, value]) => {
      body.append(key, value);
    });
    const response = await fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": config.csrfToken || "" },
      body,
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      throw new Error(data.message || "Não foi possível concluir a operação.");
    }
    return data;
  }

  async function openUpdateForm() {
    clearError();
    form.hidden = false;
    toggleButton.disabled = true;
    setLoading(true);
    showPaymentLoading("Preparando formulário do cartão…");
    try {
      const data = await postForm(config.setupIntentUrl, {});
      clientSecret = data.client_secret;
      if (paymentElement) {
        paymentElement.unmount();
        paymentElement = null;
      }
      elements = stripe.elements({
        clientSecret,
        appearance: { theme: "stripe" },
      });
      const host = ensurePaymentMountStructure();
      showPaymentLoading("Carregando formulário do cartão…");
      paymentElement = elements.create("payment");
      paymentElement.mount(host);
      await waitForPaymentElementReady(paymentElement);
    } catch (err) {
      clearPaymentLoading();
      if (mount) mount.innerHTML = "";
      showError(err.message || "Falha ao iniciar a troca de cartão.");
      form.hidden = true;
      toggleButton.disabled = false;
    } finally {
      setLoading(false);
    }
  }

  function closeUpdateForm() {
    clearError();
    form.hidden = true;
    toggleButton.disabled = false;
    if (paymentElement) {
      paymentElement.unmount();
      paymentElement = null;
    }
    elements = null;
    clientSecret = null;
    clearPaymentLoading();
    if (mount) mount.innerHTML = "";
  }

  toggleButton.addEventListener("click", () => {
    if (form.hidden) {
      openUpdateForm();
    } else {
      closeUpdateForm();
    }
  });

  if (cancelButton) {
    cancelButton.addEventListener("click", closeUpdateForm);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!elements || !clientSecret) {
      showError("Formulário de cartão ainda não está pronto.");
      return;
    }
    clearError();
    setLoading(true);
    try {
      const { error, setupIntent } = await stripe.confirmSetup({
        elements,
        redirect: "if_required",
        confirmParams: {
          return_url: window.location.href,
        },
      });
      if (error) {
        throw new Error(error.message || "Não foi possível confirmar o cartão.");
      }
      const paymentMethodId =
        typeof setupIntent.payment_method === "string"
          ? setupIntent.payment_method
          : setupIntent.payment_method && setupIntent.payment_method.id;
      if (!paymentMethodId) {
        throw new Error("A Stripe não retornou o método de pagamento.");
      }
      const confirmed = await postForm(config.confirmUrl, {
        payment_method_id: paymentMethodId,
      });
      if (cardLabel && confirmed.payment_method) {
        cardLabel.textContent = confirmed.payment_method.label || "Cartão atualizado";
      }
      if (cardExp && confirmed.payment_method) {
        cardExp.textContent = confirmed.payment_method.exp_label
          ? `Validade ${confirmed.payment_method.exp_label}`
          : "";
      }
      closeUpdateForm();
    } catch (err) {
      showError(err.message || "Falha ao salvar o cartão.");
    } finally {
      setLoading(false);
    }
  });
});
