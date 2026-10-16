document.addEventListener("DOMContentLoaded", () => {
  const config = window.SUBSCRIBE_CONFIG || {};
  const form = document.getElementById("subscribe-form");
  const submitButton = document.getElementById("subscribe-submit");
  const errorBox = document.getElementById("subscribe-error");
  const paymentMount = document.getElementById("payment-element");
  const accountFields = form ? form.querySelector(".subscribe-grid") : null;
  const sendCodeButton = document.getElementById("subscribe-send-code");
  const verifyCodeButton = document.getElementById("subscribe-verify-code");
  const codeStep = document.getElementById("subscribe-code-step");
  const codeInput = document.getElementById("subscribe-email-code");
  const verifyStatus = document.getElementById("subscribe-verify-status");
  const couponInput = document.getElementById("subscribe-coupon");
  const validateCouponButton = document.getElementById("subscribe-validate-coupon");
  const couponStatus = document.getElementById("subscribe-coupon-status");
  const priceValue = document.getElementById("subscribe-price-value");
  const priceInterval = document.getElementById("subscribe-price-interval");
  const priceNote = document.getElementById("subscribe-price-note");

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
  let confirmationMode = "payment";
  let paymentReady = false;
  let emailVerified = false;

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
    submitButton.disabled = isLoading || !emailVerified;
    submitButton.textContent = label || (isLoading ? "Processando..." : "Pagar e criar conta");
  }

  function setVerifyStatus(message) {
    if (!verifyStatus) return;
    const hasMessage = Boolean(message);
    verifyStatus.hidden = !hasMessage;
    verifyStatus.classList.toggle("hidden", !hasMessage);
    verifyStatus.textContent = message || "";
  }

  function setCouponStatus(message, isError) {
    if (!couponStatus) return;
    const hasMessage = Boolean(message);
    couponStatus.hidden = !hasMessage;
    couponStatus.classList.toggle("is-error", Boolean(isError));
    couponStatus.textContent = message || "";
  }

  function resetPriceDisplay() {
    if (!priceValue) return;
    const original = priceValue.dataset.originalLabel || priceValue.textContent;
    priceValue.textContent = original;
    if (priceNote) {
      priceNote.hidden = true;
      priceNote.textContent = "";
    }
  }

  function applyCouponPrice(payload) {
    if (!priceValue) return;
    priceValue.textContent = payload.final_label;
    if (priceInterval && payload.interval_label) {
      priceInterval.textContent = payload.interval_label;
    }
    if (priceNote) {
      priceNote.hidden = false;
      priceNote.innerHTML = `<s>${payload.original_label}</s> Com cupom (${payload.discount_label}): ${payload.final_label}`;
    }
  }

  function revealCodeStep() {
    if (!codeStep) return;
    codeStep.hidden = false;
    codeStep.classList.remove("hidden");
    if (codeInput) codeInput.focus();
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

  async function finishWithToken(pendingId, loginToken) {
    const completeData = new FormData();
    completeData.append("pending_signup_id", String(pendingId));
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

  async function finishLogin(pendingId) {
    const loginToken = await pollUntilPaid(pendingId);
    await finishWithToken(pendingId, loginToken);
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
    confirmationMode = startPayload.confirmation_mode === "setup" ? "setup" : "payment";
    if (!clientSecret) {
      throw new Error("Não foi possível iniciar o pagamento. Tente novamente.");
    }
    elements = stripe.elements({
      clientSecret,
      appearance: {
        theme: "stripe",
        variables: {
          colorPrimary: "#3b5bdb",
          colorBackground: "#ffffff",
          colorText: "#1c2438",
          colorDanger: "#c23b2e",
          fontFamily: "Manrope, sans-serif",
          borderRadius: "5px",
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
    if (couponInput) couponInput.readOnly = true;
    if (validateCouponButton) validateCouponButton.disabled = true;
    if (sendCodeButton) sendCodeButton.disabled = true;
    if (verifyCodeButton) verifyCodeButton.disabled = true;
    setLoading(false, confirmationMode === "setup" ? "Confirmar cartão" : "Confirmar pagamento");
  }

  async function confirmAndFinish() {
    if (confirmationMode === "setup") {
      const { error, setupIntent } = await stripe.confirmSetup({
        elements,
        redirect: "if_required",
        confirmParams: {
          return_url: window.location.href,
        },
      });
      if (error) {
        throw new Error(error.message || "Falha ao confirmar o cartão.");
      }
      if (!setupIntent || setupIntent.status !== "succeeded") {
        throw new Error("Cartão não confirmado.");
      }

      const setupData = new FormData();
      setupData.append("pending_signup_id", String(pendingSignupId));
      setupData.append("setup_intent_id", setupIntent.id);
      const setupResponse = await fetch(config.confirmSetupUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": config.csrfToken,
          Accept: "application/json",
        },
        body: setupData,
      });
      const setupPayload = await setupResponse.json();
      if (!setupResponse.ok || !setupPayload.ok || !setupPayload.login_token) {
        throw new Error(setupPayload.message || "Não foi possível concluir o cadastro com o cartão.");
      }
      await finishWithToken(pendingSignupId, setupPayload.login_token);
      return;
    }

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

    await finishLogin(pendingSignupId);
  }

  if (validateCouponButton) {
    validateCouponButton.addEventListener("click", async () => {
      clearError();
      setCouponStatus("", false);
      const code = couponInput ? couponInput.value.trim() : "";
      if (!code) {
        setCouponStatus("Informe um cupom para validar.", true);
        resetPriceDisplay();
        return;
      }
      const planInput = form.querySelector('input[name="plan"]');
      validateCouponButton.disabled = true;
      validateCouponButton.textContent = "Validando...";
      try {
        const data = new FormData();
        data.append("plan", planInput ? planInput.value : "");
        data.append("promotion_code", code);
        const response = await fetch(config.validateCouponUrl, {
          method: "POST",
          headers: { "X-CSRFToken": config.csrfToken, Accept: "application/json" },
          body: data,
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          resetPriceDisplay();
          throw new Error(payload.message || "Cupom inválido ou expirado.");
        }
        applyCouponPrice(payload);
        setCouponStatus(`Cupom aplicado: ${payload.discount_label} de desconto.`, false);
      } catch (error) {
        setCouponStatus(error.message || "Não foi possível validar o cupom.", true);
      } finally {
        validateCouponButton.disabled = false;
        validateCouponButton.textContent = "Validar cupom";
      }
    });
  }

  if (couponInput) {
    couponInput.addEventListener("input", () => {
      setCouponStatus("", false);
      resetPriceDisplay();
    });
  }

  if (sendCodeButton) {
    sendCodeButton.addEventListener("click", async () => {
      clearError();
      const email = form.querySelector('input[name="email"]');
      if (!email || !email.value) {
        showError("Informe o e-mail antes de solicitar o código.");
        return;
      }
      sendCodeButton.disabled = true;
      sendCodeButton.textContent = "Enviando...";
      try {
        const data = new FormData();
        data.append("email", email.value);
        const firstName = form.querySelector('input[name="first_name"]');
        if (firstName && firstName.value) {
          data.append("first_name", firstName.value);
        }
        const response = await fetch(config.sendCodeUrl, {
          method: "POST",
          headers: { "X-CSRFToken": config.csrfToken, Accept: "application/json" },
          body: data,
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "Não foi possível enviar o código.");
        }
        revealCodeStep();
        setVerifyStatus(`Código enviado para ${payload.masked_email || "seu e-mail"}.`);
      } catch (error) {
        showError(error.message || "Erro ao enviar o código.");
      } finally {
        sendCodeButton.disabled = false;
        sendCodeButton.textContent = "Enviar código";
      }
    });
  }

  if (verifyCodeButton) {
    verifyCodeButton.addEventListener("click", async () => {
      clearError();
      const email = form.querySelector('input[name="email"]');
      if (!email || !email.value || !codeInput || !codeInput.value) {
        showError("Informe o e-mail e o código recebido.");
        return;
      }
      verifyCodeButton.disabled = true;
      verifyCodeButton.textContent = "Confirmando...";
      try {
        const data = new FormData();
        data.append("email", email.value);
        data.append("code", codeInput.value.trim());
        const response = await fetch(config.verifyCodeUrl, {
          method: "POST",
          headers: { "X-CSRFToken": config.csrfToken, Accept: "application/json" },
          body: data,
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "Código inválido.");
        }
        emailVerified = true;
        setVerifyStatus("E-mail confirmado. Você já pode continuar para o pagamento.");
        if (submitButton) submitButton.disabled = false;
        if (email) email.readOnly = true;
        if (codeInput) codeInput.readOnly = true;
      } catch (error) {
        emailVerified = false;
        if (submitButton) submitButton.disabled = true;
        showError(error.message || "Não foi possível confirmar o código.");
      } finally {
        verifyCodeButton.disabled = false;
        verifyCodeButton.textContent = "Confirmar código";
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    if (!emailVerified) {
      showError("Confirme seu e-mail com o código enviado antes de continuar.");
      return;
    }
    setLoading(
      true,
      paymentReady
        ? confirmationMode === "setup"
          ? "Confirmando cartão..."
          : "Confirmando pagamento..."
        : "Preparando pagamento..."
    );

    try {
      if (!paymentReady) {
        await preparePayment();
        return;
      }
      await confirmAndFinish();
    } catch (error) {
      showError(error.message || "Erro inesperado.");
      setLoading(
        false,
        paymentReady
          ? confirmationMode === "setup"
            ? "Confirmar cartão"
            : "Confirmar pagamento"
          : "Pagar e criar conta"
      );
    }
  });
});
