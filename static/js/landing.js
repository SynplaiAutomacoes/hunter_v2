document.addEventListener("DOMContentLoaded", () => {
  const config = window.LANDING_CONFIG || {};
  const modal = document.getElementById("lead-modal");
  const form = document.getElementById("lead-form");
  const successBox = document.getElementById("lead-success");
  const errorBox = document.getElementById("lead-error");
  const submitButton = document.getElementById("lead-submit");
  const submissionIdInput = document.getElementById("lead-submission-id");
  const whatsappInput = document.getElementById("lead-whatsapp");
  const menuToggle = document.getElementById("menu-toggle");
  const mobileNav = document.getElementById("mobile-nav");
  let busy = false;

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function maskWhatsApp(value) {
    const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
    if (digits.length <= 2) return digits;
    if (digits.length <= 7) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  }

  function openLead() {
    if (!modal) return;
    if (submissionIdInput && !submissionIdInput.value) submissionIdInput.value = uuid();
    modal.hidden = false;
    modal.dataset.open = "true";
    document.body.style.overflow = "hidden";
  }

  function closeLead() {
    if (!modal || busy) return;
    modal.dataset.open = "false";
    modal.hidden = true;
    document.body.style.overflow = "";
  }

  document.querySelectorAll("[data-open-lead]").forEach((el) => {
    el.addEventListener("click", openLead);
  });
  document.querySelectorAll("[data-close-lead]").forEach((el) => {
    el.addEventListener("click", closeLead);
  });
  if (modal) {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeLead();
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeLead();
  });

  if (whatsappInput) {
    whatsappInput.addEventListener("input", () => {
      whatsappInput.value = maskWhatsApp(whatsappInput.value);
    });
  }

  if (menuToggle && mobileNav) {
    menuToggle.addEventListener("click", () => {
      const open = mobileNav.dataset.open === "true";
      mobileNav.dataset.open = open ? "false" : "true";
      menuToggle.setAttribute("aria-expanded", open ? "false" : "true");
    });
    mobileNav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileNav.dataset.open = "false";
        menuToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  const tabs = Array.isArray(config.productTabs) ? config.productTabs : [];
  const tabButtons = document.querySelectorAll(".product-tab");
  const productImage = document.getElementById("product-image");
  const productTitle = document.getElementById("product-title");
  const productDescription = document.getElementById("product-description");

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.tab || 0);
      const tab = tabs[index];
      if (!tab) return;
      tabButtons.forEach((item) => item.setAttribute("aria-selected", item === button ? "true" : "false"));
      if (productImage) {
        productImage.src = tab.imageUrl;
        productImage.alt = `Tela real do Hunter Auto: ${tab.label}`;
      }
      if (productTitle) productTitle.textContent = tab.title;
      if (productDescription) productDescription.textContent = tab.description;
    });
  });

  document.querySelectorAll(".faq-question").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.getAttribute("aria-controls");
      const answer = id ? document.getElementById(id) : null;
      const expanded = button.getAttribute("aria-expanded") === "true";
      document.querySelectorAll(".faq-question").forEach((other) => {
        other.setAttribute("aria-expanded", "false");
        const otherId = other.getAttribute("aria-controls");
        const otherAnswer = otherId ? document.getElementById(otherId) : null;
        if (otherAnswer) otherAnswer.classList.add("hidden");
      });
      if (!expanded && answer) {
        button.setAttribute("aria-expanded", "true");
        answer.classList.remove("hidden");
      }
    });
  });

  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (busy) return;
      busy = true;
      if (errorBox) {
        errorBox.classList.add("hidden");
        errorBox.textContent = "";
      }
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Enviando...";
      }

      const formData = new FormData(form);
      const params = new URLSearchParams(window.location.search);
      ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"].forEach((key) => {
        const value = params.get(key);
        if (value) formData.set(key, value.slice(0, 500));
      });
      formData.set("source", window.location.origin + window.location.pathname);
      if (!formData.get("submission_id")) formData.set("submission_id", uuid());

      try {
        const response = await fetch(config.leadUrl, {
          method: "POST",
          headers: {
            "X-CSRFToken": config.csrfToken,
            Accept: "application/json",
          },
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "Não foi possível enviar. Tente novamente.");
        }
        form.classList.add("hidden");
        if (successBox) successBox.classList.remove("hidden");
      } catch (error) {
        if (errorBox) {
          errorBox.textContent = error.message || "Não foi possível enviar. Confira sua conexão e tente novamente.";
          errorBox.classList.remove("hidden");
        }
      } finally {
        busy = false;
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Quero conhecer o Hunter Auto";
        }
      }
    });
  }
});
