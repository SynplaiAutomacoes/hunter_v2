from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.billing.access import sync_subscription_from_stripe
from apps.billing.domain.plans import Plan
from apps.billing.infrastructure.services.pending_signup import (
    mark_pending_signup_failed,
    materialize_account_from_pending_signup,
)
from apps.billing.models import (
    AccountSubscription,
    PendingSignup,
    PendingSignupStatus,
    StripeWebhookEvent,
    SubscriptionPlan,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)

STRIPE_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELED,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "incomplete": SubscriptionStatus.INCOMPLETE,
    "incomplete_expired": SubscriptionStatus.CANCELED,
    "trialing": SubscriptionStatus.ACTIVE,
    "paused": SubscriptionStatus.PAST_DUE,
}


def _parse_unix_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OSError):
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if parsed is not None and timezone.is_naive(parsed):
                return timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed
        return None


def _price_id_to_plan(price_id: str) -> str:
    from django.conf import settings

    if price_id and price_id == str(getattr(settings, "STRIPE_PRICE_ID_FULL", "") or ""):
        return Plan.FULL
    if price_id and price_id == str(getattr(settings, "STRIPE_PRICE_ID_BASIC", "") or ""):
        return Plan.BASIC
    return ""


def _extract_account_id(data: dict[str, Any]) -> int | None:
    metadata = data.get("metadata") or {}
    raw = metadata.get("account_id") or data.get("client_reference_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _extract_current_period_end(data: dict[str, Any]) -> datetime | None:
    parsed = _parse_unix_timestamp(data.get("current_period_end"))
    if parsed is not None:
        return parsed

    items = data.get("items") or {}
    item_data = items.get("data") if isinstance(items, dict) else None
    if isinstance(item_data, list):
        for item in item_data:
            if not isinstance(item, dict):
                continue
            parsed = _parse_unix_timestamp(item.get("current_period_end"))
            if parsed is not None:
                return parsed

    lines = data.get("lines") or {}
    line_data = lines.get("data") if isinstance(lines, dict) else None
    if isinstance(line_data, list):
        for line in line_data:
            if not isinstance(line, dict):
                continue
            period = line.get("period") or {}
            if not isinstance(period, dict):
                continue
            parsed = _parse_unix_timestamp(period.get("end"))
            if parsed is not None:
                return parsed

    return _parse_unix_timestamp(data.get("period_end"))


def _extract_price_id(data: dict[str, Any]) -> str:
    items = data.get("items") or {}
    item_data = items.get("data") if isinstance(items, dict) else None
    if isinstance(item_data, list) and item_data:
        price = item_data[0].get("price") or {}
        if isinstance(price, dict):
            return str(price.get("id") or "")
        return str(price or "")
    return str(data.get("stripe_price_id") or "")


def _plan_from_data(data: dict[str, Any]) -> str:
    metadata = data.get("metadata") or {}
    plan = str(metadata.get("plan") or "")
    if plan in (Plan.BASIC, Plan.FULL):
        return plan
    price_id = _extract_price_id(data)
    mapped = _price_id_to_plan(price_id)
    return mapped or Plan.BASIC


def claim_webhook_event(*, event_id: str, event_type: str, payload: dict[str, Any]) -> StripeWebhookEvent | None:
    try:
        with transaction.atomic():
            return StripeWebhookEvent.objects.create(
                event_id=event_id,
                event_type=event_type,
                payload=payload,
            )
    except IntegrityError:
        return None


def mark_webhook_processed(event: StripeWebhookEvent) -> None:
    event.processed_at = timezone.now()
    event.save(update_fields=["processed_at", "atualizado_em"])


def process_checkout_session_completed(data: dict[str, Any]) -> AccountSubscription | None:
    account_id = _extract_account_id(data)
    if account_id is None:
        logger.warning("checkout.session.completed sem account_id")
        return None

    plan = _plan_from_data(data)
    customer_id = str(data.get("customer") or "")
    subscription_id = str(data.get("subscription") or "")

    return sync_subscription_from_stripe(
        account_id=account_id,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        stripe_price_id=_extract_price_id(data),
    )


def _extract_pending_signup_id(data: dict[str, Any]) -> int | None:
    metadata = data.get("metadata") or {}
    raw = metadata.get("pending_signup_id")
    if raw is None:
        parent = data.get("subscription_details") or data.get("parent") or {}
        if isinstance(parent, dict):
            nested_meta = parent.get("metadata") or {}
            raw = nested_meta.get("pending_signup_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _find_pending_signup(data: dict[str, Any]) -> PendingSignup | None:
    pending_id = _extract_pending_signup_id(data)
    if pending_id is not None:
        pending = PendingSignup.objects.filter(pk=pending_id).first()
        if pending is not None:
            return pending

    subscription_id = str(data.get("id") or data.get("subscription") or "")
    customer_id = str(data.get("customer") or "")
    if subscription_id:
        pending = PendingSignup.objects.filter(stripe_subscription_id=subscription_id).first()
        if pending is not None:
            return pending
    if customer_id:
        return PendingSignup.objects.filter(stripe_customer_id=customer_id, status=PendingSignupStatus.PENDING).first()
    return None


def process_pending_signup_paid(data: dict[str, Any]) -> AccountSubscription | None:
    pending = _find_pending_signup(data)
    if pending is None:
        return None

    customer_id = str(data.get("customer") or pending.stripe_customer_id or "")
    subscription_id = str(data.get("id") or data.get("subscription") or pending.stripe_subscription_id or "")
    period_end = _extract_current_period_end(data)
    try:
        materialized = materialize_account_from_pending_signup(
            pending=pending,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            stripe_price_id=_extract_price_id(data),
            current_period_end=period_end,
        )
    except ValueError as exc:
        logger.warning("Falha ao materializar PendingSignup %s: %s", pending.pk, exc)
        return None

    if materialized.created_account_id is None:
        return None

    subscription = AccountSubscription.objects.filter(account_id=materialized.created_account_id).first()
    if subscription is not None and period_end is not None and subscription.current_period_end != period_end:
        subscription.current_period_end = period_end
        subscription.save(update_fields=["current_period_end", "atualizado_em"])
    return subscription


def process_subscription_event(data: dict[str, Any], *, deleted: bool = False) -> AccountSubscription | None:
    pending = _find_pending_signup(data)
    stripe_status = str(data.get("status") or "")
    if pending is not None and not deleted and stripe_status in ("active", "trialing"):
        return process_pending_signup_paid(data)
    if pending is not None and (deleted or stripe_status in ("incomplete_expired", "canceled")):
        mark_pending_signup_failed(pending)
        return None

    account_id = _extract_account_id(data)
    customer_id = str(data.get("customer") or "")
    subscription_id = str(data.get("id") or "")

    if account_id is None and subscription_id:
        existing = AccountSubscription.objects.filter(stripe_subscription_id=subscription_id).first()
        if existing is None and customer_id:
            existing = AccountSubscription.objects.filter(stripe_customer_id=customer_id).first()
        if existing is not None:
            account_id = existing.account_id

    if account_id is None:
        logger.warning("subscription event sem account_id: %s", subscription_id)
        return None

    status = SubscriptionStatus.CANCELED if deleted else STRIPE_STATUS_MAP.get(stripe_status, SubscriptionStatus.INCOMPLETE)
    plan = _plan_from_data(data)
    price_id = _extract_price_id(data)

    return sync_subscription_from_stripe(
        account_id=account_id,
        plan=plan or SubscriptionPlan.BASIC,
        status=status,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        stripe_price_id=price_id,
        current_period_end=_extract_current_period_end(data),
        cancel_at_period_end=bool(data.get("cancel_at_period_end")),
    )


def process_invoice_paid(data: dict[str, Any]) -> AccountSubscription | None:
    pending = _find_pending_signup(data)
    if pending is None:
        subscription_id = str(data.get("subscription") or "")
        if subscription_id:
            pending = PendingSignup.objects.filter(stripe_subscription_id=subscription_id).first()
    if pending is None:
        return None
    return process_pending_signup_paid(
        {
            **data,
            "id": str(data.get("subscription") or pending.stripe_subscription_id or ""),
            "metadata": {
                **(data.get("metadata") or {}),
                "pending_signup_id": str(pending.pk),
                "plan": pending.plan,
            },
            "status": "active",
        }
    )


def process_invoice_payment_failed(data: dict[str, Any]) -> AccountSubscription | None:
    pending = _find_pending_signup(data)
    if pending is not None and pending.status == PendingSignupStatus.PENDING:
        mark_pending_signup_failed(pending)
        return None

    subscription_id = str(data.get("subscription") or "")
    customer_id = str(data.get("customer") or "")
    existing = None
    if subscription_id:
        existing = AccountSubscription.objects.filter(stripe_subscription_id=subscription_id).first()
    if existing is None and customer_id:
        existing = AccountSubscription.objects.filter(stripe_customer_id=customer_id).first()
    if existing is None:
        return None

    if existing.status == SubscriptionStatus.GRANDFATHERED:
        return existing

    existing.status = SubscriptionStatus.PAST_DUE
    existing.save(update_fields=["status", "atualizado_em"])
    return existing


def process_stripe_event(*, event_type: str, data: dict[str, Any]) -> AccountSubscription | None:
    if event_type == "checkout.session.completed":
        return process_checkout_session_completed(data)
    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        return process_subscription_event(data)
    if event_type == "customer.subscription.deleted":
        return process_subscription_event(data, deleted=True)
    if event_type == "invoice.paid":
        return process_invoice_paid(data)
    if event_type == "invoice.payment_failed":
        return process_invoice_payment_failed(data)
    logger.info("Evento Stripe ignorado: %s", event_type)
    return None
