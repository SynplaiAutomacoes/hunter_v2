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
    CancelSubscriptionRequest,
    CancelSubscriptionResult,
    CheckoutSessionRequest,
    CheckoutSessionResult,
    CouponPreviewResult,
    CustomerSetupIntentResult,
    IBillingService,
    IncompleteSubscriptionRequest,
    IncompleteSubscriptionResult,
    InvoiceSummary,
    PaymentMethodSummary,
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

    def cancel_subscription(self, request: CancelSubscriptionRequest) -> CancelSubscriptionResult:
        if not request.stripe_subscription_id:
            raise BillingServiceError("Assinatura Stripe não encontrada.")
        result = stripe_gateway.cancel_subscription(
            stripe_subscription_id=request.stripe_subscription_id,
            at_period_end=request.at_period_end,
        )
        return CancelSubscriptionResult(
            stripe_subscription_id=str(result["id"]),
            status=str(result.get("status") or ""),
            cancel_at_period_end=bool(result.get("cancel_at_period_end")),
        )

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
            requires_payment=bool(result.get("requires_payment", True)),
            confirmation_mode=str(result.get("confirmation_mode") or "payment"),
        )

    def preview_plan_coupon(self, *, plan: str, code: str) -> CouponPreviewResult:
        if plan not in (Plan.BASIC, Plan.FULL):
            raise BillingServiceError("Plano inválido.")
        card = next((item for item in self.list_public_plans() if item.key == plan), None)
        if card is None or card.unit_amount is None:
            raise BillingServiceError("Não foi possível carregar o valor do plano.")

        discount = stripe_gateway.preview_discount(code=code)
        original = int(card.unit_amount)
        currency = card.currency or str(discount.get("currency") or "brl")
        percent_off = discount.get("percent_off")
        amount_off = discount.get("amount_off")

        if percent_off is not None:
            final = int(round(original * (100.0 - float(percent_off)) / 100.0))
            discount_label = f"{float(percent_off):g}%"
        elif amount_off is not None:
            final = max(0, original - int(amount_off))
            discount_label = format_money_label(unit_amount=int(amount_off), currency=currency)
        else:
            raise BillingServiceError("Cupom sem desconto configurado.")

        return CouponPreviewResult(
            original_amount=original,
            final_amount=final,
            original_label=format_money_label(unit_amount=original, currency=currency),
            final_label=format_money_label(unit_amount=final, currency=currency),
            interval_label=card.interval_label,
            discount_label=discount_label,
            currency=currency,
        )

    def finalize_setup_intent(
        self,
        *,
        setup_intent_id: str,
        customer_id: str,
        subscription_id: str,
    ) -> dict[str, str]:
        result = stripe_gateway.finalize_setup_intent(
            setup_intent_id=setup_intent_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
        )
        return {
            "customer_id": str(result["customer_id"]),
            "subscription_id": str(result["subscription_id"]),
            "payment_method_id": str(result["payment_method_id"]),
            "setup_intent_id": str(result["setup_intent_id"]),
        }

    def list_customer_invoices(self, *, stripe_customer_id: str, limit: int = 24) -> list[InvoiceSummary]:
        rows = stripe_gateway.list_customer_invoices(stripe_customer_id=stripe_customer_id, limit=limit)
        return [
            InvoiceSummary(
                id=str(row.get("id") or ""),
                number=str(row.get("number") or ""),
                status=str(row.get("status") or ""),
                amount=int(row.get("amount") or 0),
                currency=str(row.get("currency") or "BRL"),
                created=row.get("created") if isinstance(row.get("created"), int) else None,
                hosted_invoice_url=str(row.get("hosted_invoice_url") or ""),
                invoice_pdf=str(row.get("invoice_pdf") or ""),
            )
            for row in rows
        ]

    def get_default_payment_method(
        self,
        *,
        stripe_customer_id: str,
        stripe_subscription_id: str = "",
    ) -> PaymentMethodSummary | None:
        row = stripe_gateway.get_default_payment_method(
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
        )
        if not row:
            return None
        return PaymentMethodSummary(
            id=str(row.get("id") or ""),
            brand=str(row.get("brand") or ""),
            last4=str(row.get("last4") or ""),
            label=str(row.get("label") or ""),
            exp_label=str(row.get("exp_label") or ""),
        )

    def create_customer_setup_intent(self, *, stripe_customer_id: str) -> CustomerSetupIntentResult:
        result = stripe_gateway.create_customer_setup_intent(stripe_customer_id=stripe_customer_id)
        return CustomerSetupIntentResult(
            setup_intent_id=str(result["setup_intent_id"]),
            client_secret=str(result["client_secret"]),
            customer_id=str(result["customer_id"]),
        )

    def set_default_payment_method(
        self,
        *,
        stripe_customer_id: str,
        payment_method_id: str,
        stripe_subscription_id: str = "",
    ) -> PaymentMethodSummary:
        row = stripe_gateway.set_default_payment_method(
            stripe_customer_id=stripe_customer_id,
            payment_method_id=payment_method_id,
            stripe_subscription_id=stripe_subscription_id,
        )
        return PaymentMethodSummary(
            id=str(row.get("id") or payment_method_id),
            brand=str(row.get("brand") or ""),
            last4=str(row.get("last4") or ""),
            label=str(row.get("label") or payment_method_id),
            exp_label=str(row.get("exp_label") or ""),
        )
