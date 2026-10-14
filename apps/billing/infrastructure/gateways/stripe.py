from __future__ import annotations

import logging
from typing import Any

import stripe
from django.conf import settings

from apps.billing.domain.contracts import BillingServiceError

logger = logging.getLogger(__name__)


def _configure_stripe() -> None:
    stripe.api_key = str(getattr(settings, "STRIPE_SECRET_KEY", "") or "")


def _stripe_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is not None and hasattr(value, "to_dict"):
        mapped = value.to_dict()
        return mapped if isinstance(mapped, dict) else {}
    return {}


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
        "data": _stripe_mapping(event["data"]["object"]),
    }


def retrieve_price(*, price_id: str) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not price_id:
        raise BillingServiceError("Price ID do plano não configurado.")

    try:
        price_resource = stripe.Price.retrieve(price_id, expand=["product"])
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    price = price_resource.to_dict()
    product = price.get("product") or {}
    if not isinstance(product, dict) and hasattr(product, "to_dict"):
        product = product.to_dict()
    product_data = product if isinstance(product, dict) else {}

    recurring = price.get("recurring") or {}
    if not isinstance(recurring, dict) and hasattr(recurring, "to_dict"):
        recurring = recurring.to_dict()
    recurring_data = recurring if isinstance(recurring, dict) else {}

    marketing_features: list[str] = []
    raw_features = product_data.get("marketing_features") or []
    if isinstance(raw_features, list):
        for feature in raw_features:
            if isinstance(feature, dict):
                name = str(feature.get("name") or "").strip()
            else:
                name = str(feature or "").strip()
            if name:
                marketing_features.append(name)

    unit_amount = price.get("unit_amount")
    return {
        "id": str(price.get("id") or ""),
        "unit_amount": int(unit_amount) if unit_amount is not None else None,
        "currency": str(price.get("currency") or ""),
        "interval": str(recurring_data.get("interval") or ""),
        "product_name": str(product_data.get("name") or ""),
        "product_description": str(product_data.get("description") or ""),
        "marketing_features": marketing_features,
    }


def create_incomplete_subscription(
    *,
    email: str,
    customer_name: str,
    plan: str,
    price_id: str,
    pending_signup_id: int,
) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not price_id:
        raise BillingServiceError("Price ID do plano não configurado.")

    metadata = {"pending_signup_id": str(pending_signup_id), "plan": plan}

    try:
        customer = stripe.Customer.create(
            email=email,
            name=customer_name or None,
            metadata=metadata,
        )
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
            payment_behavior="default_incomplete",
            payment_settings={"save_default_payment_method": "on_subscription"},
            expand=["latest_invoice.confirmation_secret"],
            metadata=metadata,
        )
    except stripe.StripeError as exc:
        logger.exception("Falha ao criar assinatura incompleta na Stripe")
        raise BillingServiceError(str(exc)) from exc

    subscription_data = subscription.to_dict() if hasattr(subscription, "to_dict") else dict(subscription)
    latest_invoice = _stripe_mapping(subscription_data.get("latest_invoice"))
    confirmation_secret = _stripe_mapping(latest_invoice.get("confirmation_secret"))
    payment_intent = _stripe_mapping(latest_invoice.get("payment_intent"))

    client_secret = str(confirmation_secret.get("client_secret") or payment_intent.get("client_secret") or "")
    payment_intent_id = str(payment_intent.get("id") or "")
    if not client_secret:
        logger.error(
            "Stripe não retornou client_secret. subscription=%s invoice=%s invoice_keys=%s",
            subscription_data.get("id"),
            latest_invoice.get("id"),
            sorted(latest_invoice.keys()),
        )
        raise BillingServiceError("A Stripe não retornou o client_secret do pagamento.")

    customer_data = customer.to_dict() if hasattr(customer, "to_dict") else (dict(customer) if isinstance(customer, dict) else {})
    return {
        "customer_id": str(customer_data.get("id") or getattr(customer, "id", "") or ""),
        "subscription_id": str(subscription_data.get("id") or ""),
        "client_secret": client_secret,
        "payment_intent_id": payment_intent_id,
    }
