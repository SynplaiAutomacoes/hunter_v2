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
    pending_signup_id: int


@dataclass(frozen=True, slots=True)
class IncompleteSubscriptionResult:
    customer_id: str
    subscription_id: str
    client_secret: str
    payment_intent_id: str


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
