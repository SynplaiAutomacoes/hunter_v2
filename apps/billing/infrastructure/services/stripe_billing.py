from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

from apps.billing.catalog import (
    PLAN_CATALOG,
    description_for_plan_card,
    features_from_stripe_product,
    format_money_label,
    interval_label_for,
)
from apps.billing.domain.contracts import (
    BillingPortalRequest,
    BillingPortalResult,
    BillingServiceError,
    CheckoutSessionRequest,
    CheckoutSessionResult,
    IBillingService,
    IncompleteSubscriptionRequest,
    IncompleteSubscriptionResult,
    PublicPlanCard,
    StripeWebhookEventPayload,
)
from apps.billing.domain.plans import Plan
from apps.billing.infrastructure.gateways import stripe as stripe_gateway

logger = logging.getLogger(__name__)

PUBLIC_PLANS_CACHE_KEY = "billing:public_plans:v3"
PUBLIC_PLANS_CACHE_TTL_SECONDS = 300


class StripeBillingService(IBillingService):
    def _product_id_for_plan(self, plan: str) -> str:
        if plan == Plan.FULL:
            return str(getattr(settings, "STRIPE_PRODUCT_ID_FULL", "") or "")
        return str(getattr(settings, "STRIPE_PRODUCT_ID_BASIC", "") or "")

    def _legacy_price_id_for_plan(self, plan: str) -> str:
        if plan == Plan.FULL:
            return str(getattr(settings, "STRIPE_PRICE_ID_FULL", "") or "")
        return str(getattr(settings, "STRIPE_PRICE_ID_BASIC", "") or "")

    def _resolve_price_id(self, plan: str) -> str:
        for card in self.list_public_plans():
            if card.key == plan and card.stripe_price_id:
                return card.stripe_price_id
        return self._legacy_price_id_for_plan(plan)

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResult:
        if request.plan not in (Plan.BASIC, Plan.FULL):
            raise BillingServiceError("Plano inválido.")

        result = stripe_gateway.create_checkout_session(
            price_id=self._resolve_price_id(request.plan),
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
        data = event.get("data") or {}
        if not isinstance(data, dict):
            data = data.to_dict() if hasattr(data, "to_dict") else {}
        return StripeWebhookEventPayload(
            event_id=str(event["id"]),
            event_type=str(event["type"]),
            data=data,
        )

    def list_public_plans(self) -> list[PublicPlanCard]:
        cached = cache.get(PUBLIC_PLANS_CACHE_KEY)
        if isinstance(cached, list) and cached:
            return cached

        plans = [self._build_plan_card(entry) for entry in PLAN_CATALOG]
        cache.set(PUBLIC_PLANS_CACHE_KEY, plans, PUBLIC_PLANS_CACHE_TTL_SECONDS)
        return plans

    def _apply_stripe_plan_payload(
        self,
        *,
        payload: dict[str, Any],
        fallback_name: str,
        fallback_description: str,
        fallback_features: tuple[str, ...],
    ) -> tuple[str, str, tuple[str, ...], str, str, str, int | None, str]:
        name = str(payload.get("product_name") or fallback_name)
        description = fallback_description
        features = fallback_features
        marketing_features = [str(item) for item in payload.get("marketing_features") or []]
        product_description = str(payload.get("product_description") or "")
        stripe_features = features_from_stripe_product(
            description=product_description,
            marketing_features=marketing_features,
        )
        if stripe_features:
            features = stripe_features
            description = description_for_plan_card(
                description=product_description,
                features=stripe_features,
                used_marketing_features=bool(marketing_features),
            )
        unit_amount = payload.get("unit_amount")
        currency = str(payload.get("currency") or "")
        price_label = format_money_label(
            unit_amount=unit_amount if isinstance(unit_amount, int) else None,
            currency=currency,
        )
        interval_label = interval_label_for(str(payload.get("interval") or ""))
        price_id = str(payload.get("id") or "")
        return (
            name,
            description,
            features,
            price_label,
            interval_label,
            currency,
            unit_amount if isinstance(unit_amount, int) else None,
            price_id,
        )

    def _build_plan_card(self, entry: dict[str, Any]) -> PublicPlanCard:
        key = str(entry["key"])
        fallback_name = str(entry["fallback_name"])
        fallback_description = str(entry["fallback_description"])
        fallback_features = tuple(str(item) for item in entry["features"])  # type: ignore[index]
        product_id = self._product_id_for_plan(key)
        legacy_price_id = self._legacy_price_id_for_plan(key)

        name = fallback_name
        description = fallback_description
        features = fallback_features
        price_label = "Consulte"
        interval_label = ""
        currency = ""
        unit_amount: int | None = None
        price_id = legacy_price_id

        try:
            if product_id:
                payload = stripe_gateway.retrieve_product_plan(product_id=product_id)
                name, description, features, price_label, interval_label, currency, unit_amount, price_id = self._apply_stripe_plan_payload(
                    payload=payload,
                    fallback_name=fallback_name,
                    fallback_description=fallback_description,
                    fallback_features=fallback_features,
                )
            elif legacy_price_id:
                payload = stripe_gateway.retrieve_price(price_id=legacy_price_id)
                name, description, features, price_label, interval_label, currency, unit_amount, price_id = self._apply_stripe_plan_payload(
                    payload=payload,
                    fallback_name=fallback_name,
                    fallback_description=fallback_description,
                    fallback_features=fallback_features,
                )
        except BillingServiceError as exc:
            logger.warning("Falha ao carregar plano Stripe %s: %s", key, exc)

        return PublicPlanCard(
            key=key,
            name=name,
            description=description,
            features=features,
            price_label=price_label,
            interval_label=interval_label,
            currency=currency,
            unit_amount=unit_amount,
            stripe_price_id=price_id,
        )

    def create_incomplete_subscription(self, request: IncompleteSubscriptionRequest) -> IncompleteSubscriptionResult:
        if request.plan not in (Plan.BASIC, Plan.FULL):
            raise BillingServiceError("Plano inválido.")
        price_id = request.price_id or self._resolve_price_id(request.plan)
        result = stripe_gateway.create_incomplete_subscription(
            email=request.email,
            customer_name=request.customer_name,
            plan=request.plan,
            price_id=price_id,
            pending_signup_id=request.pending_signup_id,
            promotion_code=request.promotion_code,
        )
        return IncompleteSubscriptionResult(
            customer_id=result["customer_id"],
            subscription_id=result["subscription_id"],
            client_secret=result["client_secret"],
            payment_intent_id=result["payment_intent_id"],
        )
