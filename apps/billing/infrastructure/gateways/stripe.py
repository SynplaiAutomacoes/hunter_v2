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


def _marketing_features_from_product(product_data: dict[str, Any]) -> list[str]:
    marketing_features: list[str] = []
    raw_features = product_data.get("marketing_features") or []
    if not isinstance(raw_features, list):
        return marketing_features
    for feature in raw_features:
        if isinstance(feature, dict):
            name = str(feature.get("name") or "").strip()
        else:
            name = str(feature or "").strip()
        if name:
            marketing_features.append(name)
    return marketing_features


def _plan_payload_from_price_and_product(*, price: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
    recurring_data = _stripe_mapping(price.get("recurring"))
    unit_amount = price.get("unit_amount")
    return {
        "id": str(price.get("id") or ""),
        "unit_amount": int(unit_amount) if unit_amount is not None else None,
        "currency": str(price.get("currency") or ""),
        "interval": str(recurring_data.get("interval") or ""),
        "product_id": str(product.get("id") or ""),
        "product_name": str(product.get("name") or ""),
        "product_description": str(product.get("description") or ""),
        "marketing_features": _marketing_features_from_product(product),
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

    price = _stripe_mapping(price_resource)
    product_data = _stripe_mapping(price.get("product"))
    return _plan_payload_from_price_and_product(price=price, product=product_data)


def _active_default_price(product_data: dict[str, Any]) -> dict[str, Any] | None:
    default_price = product_data.get("default_price")
    if isinstance(default_price, str) and default_price:
        try:
            price_resource = stripe.Price.retrieve(default_price)
        except stripe.StripeError as exc:
            raise BillingServiceError(str(exc)) from exc
        price_data = _stripe_mapping(price_resource)
        if price_data.get("active", True):
            return price_data
        return None

    price_data = _stripe_mapping(default_price)
    if not price_data:
        return None
    if price_data.get("active", True) is False:
        return None
    return price_data


def _latest_active_recurring_price(*, product_id: str) -> dict[str, Any] | None:
    try:
        listed = stripe.Price.list(product=product_id, active=True, type="recurring", limit=100)
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    items = listed.data if hasattr(listed, "data") else (listed.get("data") if isinstance(listed, dict) else [])
    prices: list[dict[str, Any]] = []
    for item in items or []:
        mapped = _stripe_mapping(item)
        if mapped:
            prices.append(mapped)
    if not prices:
        return None
    prices.sort(key=lambda item: int(item.get("created") or 0), reverse=True)
    return prices[0]


def retrieve_product_plan(*, product_id: str) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not product_id:
        raise BillingServiceError("Product ID do plano não configurado.")

    try:
        product_resource = stripe.Product.retrieve(product_id, expand=["default_price"])
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    product_data = _stripe_mapping(product_resource)
    price_data = _active_default_price(product_data)
    if price_data is None:
        price_data = _latest_active_recurring_price(product_id=str(product_data.get("id") or product_id))
    if price_data is None:
        raise BillingServiceError("Produto Stripe sem preço recorrente ativo.")

    return _plan_payload_from_price_and_product(price=price_data, product=product_data)


def resolve_promotion_code(code: str) -> str:
    """Return Stripe promotion_code id for an active user-facing code."""
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    normalized = code.strip()
    if not normalized:
        raise BillingServiceError("Informe um cupom válido.")
    try:
        result = stripe.PromotionCode.list(code=normalized, active=True, limit=1)
    except stripe.StripeError as exc:
        logger.exception("Falha ao consultar cupom Stripe")
        raise BillingServiceError("Não foi possível validar o cupom. Tente novamente.") from exc

    data = result.data if hasattr(result, "data") else (result.get("data") if isinstance(result, dict) else [])
    if not data:
        raise BillingServiceError("Cupom inválido ou expirado.")
    first = data[0]
    promo_id = getattr(first, "id", None) or (first.get("id") if isinstance(first, dict) else None)
    if not promo_id:
        raise BillingServiceError("Cupom inválido ou expirado.")
    return str(promo_id)


def _payments_client_secret(payments: dict[str, Any]) -> str:
    data = payments.get("data")
    if not isinstance(data, list):
        return ""
    for entry in data:
        if not isinstance(entry, dict):
            continue
        for key in ("client_secret",):
            value = entry.get(key)
            if value:
                return str(value)
        payment = entry.get("payment")
        if isinstance(payment, dict):
            for key in ("client_secret",):
                value = payment.get(key)
                if value:
                    return str(value)
            nested = payment.get("payment_intent")
            if isinstance(nested, dict) and nested.get("client_secret"):
                return str(nested.get("client_secret"))
    return ""


def _payments_payment_intent_id(payments: dict[str, Any]) -> str:
    data = payments.get("data")
    if not isinstance(data, list):
        return ""
    for entry in data:
        if not isinstance(entry, dict):
            continue
        payment = entry.get("payment")
        if isinstance(payment, dict):
            pi = payment.get("payment_intent")
            if isinstance(pi, str) and pi:
                return pi
            if isinstance(pi, dict) and pi.get("id"):
                return str(pi.get("id"))
    return ""


def create_incomplete_subscription(
    *,
    email: str,
    customer_name: str,
    plan: str,
    price_id: str,
    pending_signup_id: int,
    promotion_code: str = "",
) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not price_id:
        raise BillingServiceError("Price ID do plano não configurado.")

    metadata = {"pending_signup_id": str(pending_signup_id), "plan": plan}
    discounts: list[dict[str, str]] = []
    if promotion_code.strip():
        promo_id = resolve_promotion_code(promotion_code)
        discounts.append({"promotion_code": promo_id})

    try:
        customer = stripe.Customer.create(
            email=email,
            name=customer_name or None,
            metadata=metadata,
        )
        create_kwargs: dict[str, Any] = {
            "customer": customer.id,
            "items": [{"price": price_id}],
            "payment_behavior": "default_incomplete",
            "payment_settings": {"save_default_payment_method": "on_subscription"},
            "expand": [
                "latest_invoice",
                "latest_invoice.confirmation_secret",
                "latest_invoice.payments",
            ],
            "metadata": metadata,
        }
        if discounts:
            create_kwargs["discounts"] = discounts
        subscription = stripe.Subscription.create(**create_kwargs)
    except BillingServiceError:
        raise
    except stripe.StripeError as exc:
        logger.exception("Falha ao criar assinatura incompleta na Stripe")
        raise BillingServiceError(str(exc)) from exc

    subscription_data = subscription.to_dict() if hasattr(subscription, "to_dict") else dict(subscription)
    latest_invoice = _stripe_mapping(subscription_data.get("latest_invoice"))
    confirmation_secret = _stripe_mapping(latest_invoice.get("confirmation_secret"))
    payment_intent = _stripe_mapping(latest_invoice.get("payment_intent"))
    payments = _stripe_mapping(latest_invoice.get("payments"))

    client_secret = str(
        confirmation_secret.get("client_secret")
        or payment_intent.get("client_secret")
        or _payments_client_secret(payments)
        or ""
    )
    payment_intent_id = str(
        payment_intent.get("id")
        or _payments_payment_intent_id(payments)
        or ""
    )
    if client_secret:
        customer_data = customer.to_dict() if hasattr(customer, "to_dict") else (dict(customer) if isinstance(customer, dict) else {})
        return {
            "customer_id": str(customer_data.get("id") or getattr(customer, "id", "") or ""),
            "subscription_id": str(subscription_data.get("id") or ""),
            "client_secret": client_secret,
            "payment_intent_id": payment_intent_id,
            "requires_payment": True,
        }

    # Sem client_secret: pode ser fatura gratuita (cupom 100% / valor zerado).
    # Nesse caso não há nada a cobrar — a conta deve ser criada sem Payment Element.
    amount_due = latest_invoice.get("amount_due")
    total = latest_invoice.get("total")
    invoice_status = str(latest_invoice.get("status") or "")
    subscription_status = str(subscription_data.get("status") or "")
    try:
        amount_due_int = int(amount_due) if amount_due is not None else None
    except (TypeError, ValueError):
        amount_due_int = None
    try:
        total_int = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_int = None
    is_free_invoice = (
        (amount_due_int is not None and amount_due_int <= 0)
        or (total_int is not None and total_int <= 0)
        or (invoice_status == "paid" and (amount_due_int is None or amount_due_int <= 0))
    )
    if is_free_invoice:
        logger.info(
            "Assinatura sem cobrança inicial (gratuita). subscription=%s invoice=%s status=%s sub_status=%s amount_due=%s total=%s price=%s",
            subscription_data.get("id"),
            latest_invoice.get("id"),
            invoice_status,
            subscription_status,
            amount_due,
            total,
            price_id,
        )
        customer_data = customer.to_dict() if hasattr(customer, "to_dict") else (dict(customer) if isinstance(customer, dict) else {})
        return {
            "customer_id": str(customer_data.get("id") or getattr(customer, "id", "") or ""),
            "subscription_id": str(subscription_data.get("id") or ""),
            "client_secret": "",
            "payment_intent_id": payment_intent_id,
            "requires_payment": False,
        }

    logger.error(
        "Stripe não retornou client_secret. subscription=%s invoice=%s invoice_status=%s sub_status=%s amount_due=%s total=%s confirmation_secret=%s price=%s invoice_keys=%s",
        subscription_data.get("id"),
        latest_invoice.get("id"),
        invoice_status,
        subscription_status,
        amount_due,
        total,
        bool(confirmation_secret),
        price_id,
        sorted(latest_invoice.keys()),
    )
    raise BillingServiceError("A Stripe não retornou o client_secret do pagamento.")
