from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.infrastructure.models.abstract import TimeStampedModel


class SubscriptionPlan(models.TextChoices):
    BASIC = "basic", "Orçamento"
    FULL = "full", "Completo"


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Ativa"
    PAST_DUE = "past_due", "Pagamento atrasado"
    CANCELED = "canceled", "Cancelada"
    INCOMPLETE = "incomplete", "Aguardando pagamento"
    GRANDFATHERED = "grandfathered", "Cortesia (conta antiga)"


class AccountSubscription(TimeStampedModel):
    account = models.OneToOneField(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="subscription",
        verbose_name="Conta",
    )
    plan = models.CharField(
        max_length=20,
        choices=SubscriptionPlan.choices,
        default=SubscriptionPlan.BASIC,
        verbose_name="Plano",
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.INCOMPLETE,
        verbose_name="Status",
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="", verbose_name="Cliente Stripe")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="", verbose_name="Assinatura Stripe")
    stripe_price_id = models.CharField(max_length=255, blank=True, default="", verbose_name="Preço Stripe")
    current_period_end = models.DateTimeField(null=True, blank=True, verbose_name="Renova em")
    cancel_at_period_end = models.BooleanField(default=False, verbose_name="Cancela no fim do período")

    class Meta:
        verbose_name = "Assinatura da Conta"
        verbose_name_plural = "Assinaturas das Contas"

    def __str__(self) -> str:
        return f"{self.account} — {self.get_plan_display()} ({self.get_status_display()})"

    @property
    def is_active(self) -> bool:
        if self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.GRANDFATHERED):
            return True
        if self.status == SubscriptionStatus.PAST_DUE:
            grace_days = int(getattr(settings, "STRIPE_PAST_DUE_GRACE_DAYS", 3))
            if self.current_period_end is None:
                return True
            grace_deadline = self.current_period_end + timezone.timedelta(days=grace_days)
            return bool(timezone.now() <= grace_deadline)
        return False

    @property
    def is_full_plan(self) -> bool:
        return self.plan == SubscriptionPlan.FULL and self.is_active


class StripeWebhookEvent(TimeStampedModel):
    event_id = models.CharField(max_length=255, unique=True, verbose_name="ID do evento")
    event_type = models.CharField(max_length=255, verbose_name="Tipo")
    payload = models.JSONField(default=dict, blank=True, verbose_name="Payload")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Processado em")

    class Meta:
        verbose_name = "Evento Webhook Stripe"
        verbose_name_plural = "Eventos Webhook Stripe"

    def __str__(self) -> str:
        return f"{self.event_type} ({self.event_id})"


class PendingSignupStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    PAID = "paid", "Pago"
    EXPIRED = "expired", "Expirado"
    FAILED = "failed", "Falhou"


class PendingSignup(TimeStampedModel):
    email = models.EmailField(verbose_name="E-mail")
    username = models.CharField(max_length=150, verbose_name="Usuário")
    password_hash = models.CharField(max_length=128, verbose_name="Hash da senha")
    first_name = models.CharField(max_length=150, blank=True, default="", verbose_name="Nome")
    last_name = models.CharField(max_length=150, blank=True, default="", verbose_name="Sobrenome")
    cpf = models.CharField(max_length=14, verbose_name="CPF")
    plan = models.CharField(max_length=20, choices=SubscriptionPlan.choices, verbose_name="Plano")
    status = models.CharField(
        max_length=20,
        choices=PendingSignupStatus.choices,
        default=PendingSignupStatus.PENDING,
        verbose_name="Status",
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="", verbose_name="Cliente Stripe")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="", verbose_name="Assinatura Stripe")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="", verbose_name="PaymentIntent Stripe")
    expires_at = models.DateTimeField(verbose_name="Expira em")
    created_account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_signups",
        verbose_name="Conta criada",
    )
    login_token = models.CharField(max_length=64, blank=True, default="", verbose_name="Token de login")
    login_token_used_at = models.DateTimeField(null=True, blank=True, verbose_name="Token usado em")

    class Meta:
        verbose_name = "Cadastro pendente de assinatura"
        verbose_name_plural = "Cadastros pendentes de assinatura"
        indexes = [
            models.Index(fields=["email", "status"]),
            models.Index(fields=["stripe_subscription_id"]),
            models.Index(fields=["login_token"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=models.Q(status="pending"),
                name="unique_pending_signup_email",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_status_display()})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at
