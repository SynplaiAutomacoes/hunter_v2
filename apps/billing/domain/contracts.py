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


class IBillingService(ABC):
    @abstractmethod
    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResult: ...

    @abstractmethod
    def create_billing_portal_session(self, request: BillingPortalRequest) -> BillingPortalResult: ...

    @abstractmethod
    def construct_webhook_event(self, *, payload: bytes, signature_header: str) -> StripeWebhookEventPayload: ...
