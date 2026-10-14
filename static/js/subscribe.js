document.addEventListener("DOMContentLoaded", () => {
  const config = window.SUBSCRIBE_CONFIG || {};
  const form = document.getElementById("subscribe-form");
  const submitButton = document.getElementById("subscribe-submit");
  const errorBox = document.getElementById("subscribe-error");
  const paymentMount = document.getElementById("payment-element");
  const accountFields = form ? form.querySelector(".subscribe-grid") : null;

  if (!form || !config.publishableKey) {
    showError("Stripe não configurado (STRIPE_PUBLISHABLE_KEY ausente).");
    return;
  }

  const cpfInput = document.getElementById("subscribe-cpf");
  if (cpfInput) {
    const formatCpf = (value) => {
      const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
      if (digits.length <= 3) return digits;
      if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
      if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
      return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
    };
    cpfInput.addEventListener("input", () => {
      cpfInput.value = formatCpf(cpfInput.value);
    });
  }

  const stripe = window.Stripe(config.publishableKey);
  let elements = null;
  let paymentElement = null;
  let pendingSignupId = null;
  let clientSecret = null;
  let paymentReady = false;

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

  function setLoading(isLoading, label) {
    if (!submitButton) return;
    submitButton.disabled = isLoading;
    submitButton.textContent = label || (isLoading ? "Processando..." : "Pagar e criar conta");
  }

  async function pollUntilPaid(pendingId) {
    const url = config.statusUrlTemplate.replace("{id}", String(pendingId));
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (payload.paid && payload.login_token) {
        return payload.login_token;
      }
      if (payload.failed) {
        throw new Error("Pagamento não concluído. Tente novamente.");
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error("Ainda estamos confirmando o pagamento. Atualize a página em instantes.");
  }

  async function preparePayment() {
    const formData = new FormData(form);
    const startResponse = await fetch(config.startUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": config.csrfToken,
        Accept: "application/json",
      },
      body: formData,
    });
    const startPayload = await startResponse.json();
    if (startResponse.status >= 500) {
      throw new Error("Não foi possível iniciar o pagamento. Tente novamente.");
    }
    if (!startResponse.ok || !startPayload.ok) {
      const firstError =
        startPayload.message ||
        (startPayload.errors && Object.values(startPayload.errors).flat().join(" ")) ||
        "Não foi possível iniciar o pagamento.";
      throw new Error(firstError);
    }

    pendingSignupId = startPayload.pending_signup_id;
    clientSecret = startPayload.client_secret;
    elements = stripe.elements({
      clientSecret,
      appearance: {
        theme: "night",
        variables: {
          colorPrimary: "#05c4ed",
          colorBackground: "#0a121c",
          colorText: "#ffffff",
        },
      },
    });

    if (paymentElement) {
      paymentElement.unmount();
    }
    paymentElement = elements.create("payment");
    paymentElement.mount(paymentMount);
    paymentReady = true;

    if (accountFields) {
      accountFields.querySelectorAll("input").forEach((input) => {
        input.readOnly = true;
      });
    }
    setLoading(false, "Confirmar pagamento");
  }

  async function confirmAndFinish() {
    const { error, paymentIntent } = await stripe.confirmPayment({
      elements,
      redirect: "if_required",
      confirmParams: {
        return_url: window.location.href,
      },
    });

    if (error) {
      throw new Error(error.message || "Falha ao confirmar o pagamento.");
    }
    if (paymentIntent && !["succeeded", "processing"].includes(paymentIntent.status)) {
      throw new Error("Pagamento não confirmado.");
    }

    const loginToken = await pollUntilPaid(pendingSignupId);
    const completeData = new FormData();
    completeData.append("pending_signup_id", String(pendingSignupId));
    completeData.append("login_token", loginToken);

    const completeResponse = await fetch(config.completeUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": config.csrfToken,
        Accept: "application/json",
      },
      body: completeData,
    });
    const completePayload = await completeResponse.json();
    if (!completeResponse.ok || !completePayload.ok) {
      throw new Error(completePayload.message || "Pagamento ok, mas o login automático falhou.");
    }

    window.location.href = completePayload.redirect_url;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    setLoading(true, paymentReady ? "Confirmando pagamento..." : "Preparando pagamento...");

    try {
      if (!paymentReady) {
        await preparePayment();
        return;
      }
      await confirmAndFinish();
    } catch (error) {
      showError(error.message || "Erro inesperado.");
      setLoading(false, paymentReady ? "Confirmar pagamento" : "Pagar e criar conta");
    }
  });
});
