from __future__ import annotations

from django.conf import settings

from apps.billing.domain.contracts import (
    BillingPortalRequest,
    BillingPortalResult,
    BillingServiceError,
    CheckoutSessionRequest,
    CheckoutSessionResult,
    IBillingService,
    StripeWebhookEventPayload,
)
from apps.billing.domain.plans import Plan
from apps.billing.infrastructure.gateways import stripe as stripe_gateway


class StripeBillingService(IBillingService):
    def _price_id_for_plan(self, plan: str) -> str:
        if plan == Plan.FULL:
            return str(getattr(settings, "STRIPE_PRICE_ID_FULL", "") or "")
        return str(getattr(settings, "STRIPE_PRICE_ID_BASIC", "") or "")

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResult:
        if request.plan not in (Plan.BASIC, Plan.FULL):
            raise BillingServiceError("Plano inválido.")

        result = stripe_gateway.create_checkout_session(
            price_id=self._price_id_for_plan(request.plan),
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            customer_email=request.customer_email,
            account_id=request.account_id,
            plan=request.plan,
            stripe_customer_id=request.stripe_customer_id,
            customer_name=request.customer_name,
        )
        return CheckoutSessionResult(session_id=result["id"], url=result["url"])

    def create_billing_portal_session(self, request: BillingPortalRequest) -> BillingPortalResult:
        result = stripe_gateway.create_billing_portal_session(
            stripe_customer_id=request.stripe_customer_id,
            return_url=request.return_url,
        )
        return BillingPortalResult(url=result["url"])

    def construct_webhook_event(self, *, payload: bytes, signature_header: str) -> StripeWebhookEventPayload:
        event = stripe_gateway.construct_webhook_event(payload=payload, signature_header=signature_header)
        return StripeWebhookEventPayload(
            event_id=str(event["id"]),
            event_type=str(event["type"]),
            data=dict(event["data"] or {}),
        )
