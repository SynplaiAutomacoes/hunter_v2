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
        "subscription_data": {
            "metadata": {"account_id": str(account_id), "plan": plan},
        },
        "payment_method_collection": "always",
        "saved_payment_method_options": {
            "payment_method_save": "enabled",
            "allow_redisplay_filters": ["always"],
        },
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


def _payment_method_summary(payment_method: Any) -> dict[str, Any] | None:
    data = payment_method.to_dict() if hasattr(payment_method, "to_dict") else _stripe_mapping(payment_method)
    if not data:
        return None
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    brand = str(card.get("brand") or data.get("type") or "cartão")
    last4 = str(card.get("last4") or "")
    exp_month = card.get("exp_month")
    exp_year = card.get("exp_year")
    label = brand.upper() if brand else "CARTÃO"
    if last4:
        label = f"{label} •••• {last4}"
    exp_label = ""
    if exp_month and exp_year:
        exp_label = f"{int(exp_month):02d}/{str(exp_year)[-2:]}"
    return {
        "id": str(data.get("id") or ""),
        "brand": brand,
        "last4": last4,
        "exp_month": exp_month,
        "exp_year": exp_year,
        "label": label,
        "exp_label": exp_label,
    }


def list_customer_invoices(*, stripe_customer_id: str, limit: int = 24) -> list[dict[str, Any]]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not stripe_customer_id:
        return []

    try:
        result = stripe.Invoice.list(customer=stripe_customer_id, limit=max(1, min(limit, 100)))
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    rows: list[dict[str, Any]] = []
    data = result.get("data") if isinstance(result, dict) else getattr(result, "data", None)
    if not isinstance(data, list):
        mapped = result.to_dict() if hasattr(result, "to_dict") else {}
        data = mapped.get("data") if isinstance(mapped, dict) else []
    for invoice in data or []:
        item = invoice.to_dict() if hasattr(invoice, "to_dict") else _stripe_mapping(invoice)
        if not item:
            continue
        amount = item.get("amount_paid")
        if amount is None:
            amount = item.get("total") or item.get("amount_due") or 0
        currency = str(item.get("currency") or "brl").upper()
        created = item.get("created")
        status = str(item.get("status") or "")
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "number": str(item.get("number") or item.get("id") or ""),
                "status": status,
                "amount": int(amount or 0),
                "currency": currency,
                "created": int(created) if created is not None else None,
                "hosted_invoice_url": str(item.get("hosted_invoice_url") or ""),
                "invoice_pdf": str(item.get("invoice_pdf") or ""),
            }
        )
    return rows


def get_default_payment_method(
    *,
    stripe_customer_id: str,
    stripe_subscription_id: str = "",
) -> dict[str, Any] | None:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not stripe_customer_id:
        return None

    payment_method_id = ""
    try:
        if stripe_subscription_id:
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            sub_data = subscription.to_dict() if hasattr(subscription, "to_dict") else _stripe_mapping(subscription)
            raw_pm = sub_data.get("default_payment_method")
            if isinstance(raw_pm, dict):
                payment_method_id = str(raw_pm.get("id") or "")
            else:
                payment_method_id = str(raw_pm or "")

        if not payment_method_id:
            customer = stripe.Customer.retrieve(stripe_customer_id)
            customer_data = customer.to_dict() if hasattr(customer, "to_dict") else _stripe_mapping(customer)
            invoice_settings = customer_data.get("invoice_settings") or {}
            if isinstance(invoice_settings, dict):
                raw_pm = invoice_settings.get("default_payment_method")
                if isinstance(raw_pm, dict):
                    payment_method_id = str(raw_pm.get("id") or "")
                else:
                    payment_method_id = str(raw_pm or "")

        if not payment_method_id:
            return None

        payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    return _payment_method_summary(payment_method)


def create_customer_setup_intent(*, stripe_customer_id: str) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not stripe_customer_id:
        raise BillingServiceError("Cliente Stripe não encontrado para esta conta.")

    try:
        setup_intent = stripe.SetupIntent.create(
            customer=stripe_customer_id,
            usage="off_session",
            payment_method_types=["card"],
            metadata={"purpose": "update_default_payment_method"},
        )
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    data = setup_intent.to_dict() if hasattr(setup_intent, "to_dict") else _stripe_mapping(setup_intent)
    client_secret = str(data.get("client_secret") or "")
    if not client_secret:
        raise BillingServiceError("A Stripe não retornou o client_secret do SetupIntent.")
    return {
        "setup_intent_id": str(data.get("id") or ""),
        "client_secret": client_secret,
        "customer_id": stripe_customer_id,
    }


def set_default_payment_method(
    *,
    stripe_customer_id: str,
    payment_method_id: str,
    stripe_subscription_id: str = "",
) -> dict[str, Any]:
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not stripe_customer_id or not payment_method_id:
        raise BillingServiceError("Dados incompletos para atualizar o cartão.")

    try:
        stripe.PaymentMethod.attach(payment_method_id, customer=stripe_customer_id)
    except stripe.InvalidRequestError as exc:
        # Já anexado ao customer — segue.
        if "already been attached" not in str(exc).lower():
            raise BillingServiceError(str(exc)) from exc
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    try:
        stripe.Customer.modify(
            stripe_customer_id,
            invoice_settings={"default_payment_method": payment_method_id},
        )
        if stripe_subscription_id:
            try:
                stripe.Subscription.modify(
                    stripe_subscription_id,
                    default_payment_method=payment_method_id,
                )
            except stripe.InvalidRequestError as exc:
                if getattr(exc, "code", None) != "invalid_canceled_subscription_fields":
                    raise
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    summary = get_default_payment_method(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    return summary or {"id": payment_method_id, "label": payment_method_id}


def _subscription_cancel_payload(data: dict[str, Any], *, stripe_subscription_id: str) -> dict[str, Any]:
    return {
        "id": str(data.get("id") or stripe_subscription_id),
        "status": str(data.get("status") or ""),
        "cancel_at_period_end": bool(data.get("cancel_at_period_end")),
        "current_period_end": data.get("current_period_end"),
        "customer": str(data.get("customer") or ""),
    }


def cancel_subscription(*, stripe_subscription_id: str, at_period_end: bool) -> dict[str, Any]:
    """Cancel immediately or schedule cancel at period end (Stripe parity).

    Idempotent when Stripe already shows ``canceled`` (local can lag after panel
    cancel or a stale webhook). Stripe rejects ``modify`` on canceled subs with
    ``invalid_canceled_subscription_fields``.
    """
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not stripe_subscription_id:
        raise BillingServiceError("Assinatura Stripe não encontrada.")

    try:
        current = stripe.Subscription.retrieve(stripe_subscription_id)
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    current_data = current.to_dict() if hasattr(current, "to_dict") else _stripe_mapping(current)
    if str(current_data.get("status") or "") == "canceled":
        logger.info(
            "Assinatura Stripe %s já cancelada — sync local sem novo modify/cancel",
            stripe_subscription_id,
        )
        return _subscription_cancel_payload(current_data, stripe_subscription_id=stripe_subscription_id)

    if at_period_end and bool(current_data.get("cancel_at_period_end")):
        return _subscription_cancel_payload(current_data, stripe_subscription_id=stripe_subscription_id)

    try:
        if at_period_end:
            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True,
            )
        else:
            subscription = stripe.Subscription.cancel(stripe_subscription_id)
    except stripe.InvalidRequestError as exc:
        # Race: canceled between retrieve and modify/cancel.
        code = getattr(exc, "code", None) or ""
        if code == "invalid_canceled_subscription_fields" or "canceled subscription" in str(exc).lower():
            logger.info(
                "Assinatura Stripe %s cancelada durante a operação — tratando como já cancelada",
                stripe_subscription_id,
            )
            try:
                refreshed = stripe.Subscription.retrieve(stripe_subscription_id)
            except stripe.StripeError:
                raise BillingServiceError(str(exc)) from exc
            refreshed_data = refreshed.to_dict() if hasattr(refreshed, "to_dict") else _stripe_mapping(refreshed)
            return _subscription_cancel_payload(refreshed_data, stripe_subscription_id=stripe_subscription_id)
        raise BillingServiceError(str(exc)) from exc
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    data = subscription.to_dict() if hasattr(subscription, "to_dict") else _stripe_mapping(subscription)
    return _subscription_cancel_payload(data, stripe_subscription_id=stripe_subscription_id)


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


def _active_promotion_code_id(code: str) -> str:
    try:
        result = stripe.PromotionCode.list(code=code, active=True, limit=1)
    except stripe.StripeError as exc:
        logger.exception("Falha ao consultar promotion code Stripe")
        raise BillingServiceError("Não foi possível validar o cupom. Tente novamente.") from exc

    data = result.data if hasattr(result, "data") else (result.get("data") if isinstance(result, dict) else [])
    if not data:
        return ""
    first = data[0]
    promo_id = getattr(first, "id", None) or (first.get("id") if isinstance(first, dict) else None)
    return str(promo_id or "")


def _active_coupon_id(code: str) -> str:
    """Find an active coupon by id or by its name (user-facing code).

    Coupons created directly in the Stripe Dashboard have no promotion code,
    so we also accept the coupon id/name as the code typed by the customer.
    """
    coupon = None
    try:
        coupon = stripe.Coupon.retrieve(code)
    except stripe.InvalidRequestError:
        coupon = None
    except stripe.StripeError as exc:
        logger.warning("Falha ao consultar cupom por id %s: %s", code, exc)
        coupon = None
    if coupon is not None:
        data = _stripe_mapping(coupon)
        if data.get("valid", True) and data.get("id"):
            return str(data.get("id"))

    normalized = code.strip().casefold()
    try:
        listed = stripe.Coupon.list(limit=100)
    except stripe.StripeError as exc:
        logger.exception("Falha ao listar cupons Stripe")
        raise BillingServiceError("Não foi possível validar o cupom. Tente novamente.") from exc

    items = listed.data if hasattr(listed, "data") else (listed.get("data") if isinstance(listed, dict) else [])
    for item in items or []:
        data = _stripe_mapping(item)
        if data.get("valid", True) is False:
            continue
        coupon_id = str(data.get("id") or "")
        name = str(data.get("name") or "").strip().casefold()
        if coupon_id and (coupon_id.casefold() == normalized or name == normalized):
            return coupon_id
    return ""


def resolve_discount(promotion_code: str) -> dict[str, str]:
    """Resolve a user-facing code into a Stripe discount entry.

    Accepts an active promotion code first, then falls back to an active coupon
    (matched by id or name) so coupons created without a promotion code work.
    """
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    normalized = promotion_code.strip()
    if not normalized:
        raise BillingServiceError("Informe um cupom válido.")

    promo_id = _active_promotion_code_id(normalized)
    if promo_id:
        return {"promotion_code": promo_id}

    coupon_id = _active_coupon_id(normalized)
    if coupon_id:
        return {"coupon": coupon_id}

    raise BillingServiceError("Cupom inválido ou expirado.")


def _coupon_payload_from_resource(coupon: Any) -> dict[str, Any]:
    data = _stripe_mapping(coupon)
    percent_off = data.get("percent_off")
    amount_off = data.get("amount_off")
    return {
        "coupon_id": str(data.get("id") or ""),
        "percent_off": float(percent_off) if percent_off is not None else None,
        "amount_off": int(amount_off) if amount_off is not None else None,
        "currency": str(data.get("currency") or ""),
        "name": str(data.get("name") or ""),
    }


def preview_discount(*, code: str) -> dict[str, Any]:
    """Resolve a user-facing code and return coupon discount fields for preview."""
    discount = resolve_discount(code)
    _configure_stripe()

    if "promotion_code" in discount:
        try:
            promo = stripe.PromotionCode.retrieve(discount["promotion_code"], expand=["coupon"])
        except stripe.StripeError as exc:
            raise BillingServiceError("Não foi possível validar o cupom. Tente novamente.") from exc
        promo_data = _stripe_mapping(promo)
        coupon = promo_data.get("coupon")
        coupon_payload = _coupon_payload_from_resource(coupon)
        coupon_payload["promotion_code_id"] = str(promo_data.get("id") or discount["promotion_code"])
        return coupon_payload

    try:
        coupon = stripe.Coupon.retrieve(discount["coupon"])
    except stripe.StripeError as exc:
        raise BillingServiceError("Não foi possível validar o cupom. Tente novamente.") from exc
    coupon_payload = _coupon_payload_from_resource(coupon)
    coupon_payload["promotion_code_id"] = ""
    return coupon_payload


def resolve_promotion_code(code: str) -> str:
    """Return Stripe promotion_code id for an active user-facing code."""
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    normalized = code.strip()
    if not normalized:
        raise BillingServiceError("Informe um cupom válido.")
    promo_id = _active_promotion_code_id(normalized)
    if not promo_id:
        raise BillingServiceError("Cupom inválido ou expirado.")
    return promo_id


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
        discounts.append(resolve_discount(promotion_code))

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
    customer_data = customer.to_dict() if hasattr(customer, "to_dict") else (dict(customer) if isinstance(customer, dict) else {})
    customer_id = str(customer_data.get("id") or getattr(customer, "id", "") or "")
    subscription_id = str(subscription_data.get("id") or "")

    if client_secret:
        return {
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "client_secret": client_secret,
            "payment_intent_id": payment_intent_id,
            "requires_payment": True,
            "confirmation_mode": "payment",
        }

    # Sem client_secret: fatura gratuita (cupom 100% / valor zerado).
    # Ainda assim coletamos cartão via SetupIntent para renovação futura.
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
            "Assinatura sem cobrança inicial; criando SetupIntent. subscription=%s invoice=%s amount_due=%s total=%s",
            subscription_id,
            latest_invoice.get("id"),
            amount_due,
            total,
        )
        try:
            setup_intent = stripe.SetupIntent.create(
                customer=customer_id,
                usage="off_session",
                payment_method_types=["card"],
                metadata={
                    **metadata,
                    "stripe_subscription_id": subscription_id,
                },
            )
        except stripe.StripeError as exc:
            logger.exception("Falha ao criar SetupIntent para assinatura gratuita %s", subscription_id)
            raise BillingServiceError(str(exc)) from exc

        setup_data = setup_intent.to_dict() if hasattr(setup_intent, "to_dict") else _stripe_mapping(setup_intent)
        setup_secret = str(setup_data.get("client_secret") or "")
        setup_id = str(setup_data.get("id") or "")
        if not setup_secret:
            raise BillingServiceError("A Stripe não retornou o client_secret do cartão.")
        return {
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "client_secret": setup_secret,
            "payment_intent_id": setup_id,
            "requires_payment": True,
            "confirmation_mode": "setup",
        }

    logger.error(
        "Stripe não retornou client_secret. subscription=%s invoice=%s invoice_status=%s sub_status=%s amount_due=%s total=%s confirmation_secret=%s price=%s invoice_keys=%s",
        subscription_id,
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


def finalize_setup_intent(*, setup_intent_id: str, customer_id: str, subscription_id: str) -> dict[str, Any]:
    """Attach the SetupIntent payment method as default on customer and subscription."""
    _configure_stripe()
    if not stripe.api_key:
        raise BillingServiceError("Stripe não configurado (STRIPE_SECRET_KEY ausente).")
    if not setup_intent_id or not customer_id or not subscription_id:
        raise BillingServiceError("Dados incompletos para confirmar o cartão.")

    try:
        setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
    except stripe.StripeError as exc:
        raise BillingServiceError(str(exc)) from exc

    setup_data = setup_intent.to_dict() if hasattr(setup_intent, "to_dict") else _stripe_mapping(setup_intent)
    if str(setup_data.get("status") or "") != "succeeded":
        raise BillingServiceError("Cartão ainda não confirmado. Conclua o formulário de pagamento.")
    if str(setup_data.get("customer") or "") != customer_id:
        raise BillingServiceError("Cartão não corresponde ao cliente da assinatura.")

    payment_method = setup_data.get("payment_method")
    if isinstance(payment_method, dict):
        payment_method_id = str(payment_method.get("id") or "")
    else:
        payment_method_id = str(payment_method or "")
    if not payment_method_id:
        raise BillingServiceError("Nenhum método de pagamento encontrado no SetupIntent.")

    try:
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": payment_method_id},
        )
        stripe.Subscription.modify(
            subscription_id,
            default_payment_method=payment_method_id,
        )
    except stripe.StripeError as exc:
        logger.exception("Falha ao anexar método de pagamento à assinatura %s", subscription_id)
        raise BillingServiceError(str(exc)) from exc

    return {
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "payment_method_id": payment_method_id,
        "setup_intent_id": setup_intent_id,
    }
