from __future__ import annotations

from typing import Any

import stripe
from django.conf import settings

from apps.billing.domain.contracts import BillingServiceError


def _configure_stripe() -> None:
    stripe.api_key = str(getattr(settings, "STRIPE_SECRET_KEY", "") or "")


def create_checkout_session(
    *,
    price_id: str,
    success_url: str,
    cancel_url: str,
    customer_email: str,
    account_id: int,
    plan: str,
    stripe_customer_id: str = "",
    customer_name: str = "",
) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not price_id:
        raise BillingServiceError("Price ID do plano não configurado.")

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(account_id),
        "metadata": {"account_id": str(account_id), "plan": plan},
        "subscription_data": {"metadata": {"account_id": str(account_id), "plan": plan}},
        "allow_promotion_codes": True,
    }
    if stripe_customer_id:
        params["customer"] = stripe_customer_id
    else:
        params["customer_email"] = customer_email
        if customer_name:
            params["customer_creation"] = "always"

    try:
        session = stripe.checkout.Session.create(**params)
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    return {"id": session.id, "url": session.url or ""}


def create_billing_portal_session(*, stripe_customer_id: str, return_url: str) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not stripe_customer_id:
        raise BillingServiceError("Cliente Stripe não encontrado para esta conta.")

    try:
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    return {"url": session.url}


def construct_webhook_event(*, payload: bytes, signature_header: str) -> dict[str, Any]:
    _configure_stripe()
    webhook_secret = str(getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or "")
    if not webhook_secret:
        raise BillingServiceError("Stripe webhook secret não configurado.")

    try:
        event = stripe.Webhook.construct_event(payload, signature_header, webhook_secret)
    except ValueError as exc:
        raise BillingServiceError("Payload inválido.") from exc
    except stripe.SignatureVerificationError as exc:
        raise BillingServiceError("Assinatura do webhook inválida.") from exc

    return {
        "id": event["id"],
        "type": event["type"],
        "data": event["data"]["object"],
    }
