from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class BillingServiceError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CheckoutSessionRequest:
    account_id: int
    plan: str
    customer_email: str
    success_url: str
    cancel_url: str
    stripe_customer_id: str = ""
    customer_name: str = ""


@dataclass(frozen=True, slots=True)
class CheckoutSessionResult:
    session_id: str
    url: str


@dataclass(frozen=True, slots=True)
class BillingPortalRequest:
    stripe_customer_id: str
    return_url: str


@dataclass(frozen=True, slots=True)
class BillingPortalResult:
    url: str


@dataclass(frozen=True, slots=True)
class StripeWebhookEventPayload:
    event_id: str
    event_type: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PublicPlanCard:
    key: str
    name: str
    description: str
    features: tuple[str, ...]
    price_label: str
    interval_label: str
    currency: str
    unit_amount: int | None
    stripe_price_id: str


@dataclass(frozen=True, slots=True)
class IncompleteSubscriptionRequest:
    email: str
    customer_name: str
    plan: str
    price_id: str
    pending_signup_id: int = 0
    account_id: int | None = None
    stripe_customer_id: str = ""
    promotion_code: str = ""


@dataclass(frozen=True, slots=True)
class IncompleteSubscriptionResult:
    customer_id: str
    subscription_id: str
    client_secret: str
    payment_intent_id: str
    requires_payment: bool = True
    confirmation_mode: str = "payment"  # "payment" | "setup"


@dataclass(frozen=True, slots=True)
class CouponPreviewResult:
    original_amount: int
    final_amount: int
    original_label: str
    final_label: str
    interval_label: str
    discount_label: str
    currency: str


@dataclass(frozen=True, slots=True)
class CancelSubscriptionRequest:
    stripe_subscription_id: str
    at_period_end: bool


@dataclass(frozen=True, slots=True)
class CancelSubscriptionResult:
    stripe_subscription_id: str
    status: str
    cancel_at_period_end: bool


@dataclass(frozen=True, slots=True)
class PaymentMethodSummary:
    id: str
    brand: str
    last4: str
    label: str
    exp_label: str


@dataclass(frozen=True, slots=True)
class InvoiceSummary:
    id: str
    number: str
    status: str
    amount: int
    currency: str
    created: int | None
    hosted_invoice_url: str
    invoice_pdf: str


@dataclass(frozen=True, slots=True)
class CustomerSetupIntentResult:
    setup_intent_id: str
    client_secret: str
    customer_id: str


class IBillingService(ABC):
    @abstractmethod
    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResult: ...

    @abstractmethod
    def create_billing_portal_session(self, request: BillingPortalRequest) -> BillingPortalResult: ...

    @abstractmethod
    def construct_webhook_event(self, *, payload: bytes, signature_header: str) -> StripeWebhookEventPayload: ...

    @abstractmethod
    def list_public_plans(self) -> list[PublicPlanCard]: ...

    @abstractmethod
    def create_incomplete_subscription(self, request: IncompleteSubscriptionRequest) -> IncompleteSubscriptionResult: ...

    @abstractmethod
    def cancel_subscription(self, request: CancelSubscriptionRequest) -> CancelSubscriptionResult: ...

    @abstractmethod
    def list_customer_invoices(self, *, stripe_customer_id: str, limit: int = 24) -> list[InvoiceSummary]: ...

    @abstractmethod
    def get_default_payment_method(
        self,
        *,
        stripe_customer_id: str,
        stripe_subscription_id: str = "",
    ) -> PaymentMethodSummary | None: ...

    @abstractmethod
    def create_customer_setup_intent(self, *, stripe_customer_id: str) -> CustomerSetupIntentResult: ...

    @abstractmethod
    def set_default_payment_method(
        self,
        *,
        stripe_customer_id: str,
        payment_method_id: str,
        stripe_subscription_id: str = "",
    ) -> PaymentMethodSummary: ...
