from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.billing.domain.plans import Plan, route_requires_full_plan
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus

SESSION_CACHE_KEY = "billing_subscription_access"


def invalidate_subscription_cache(request: HttpRequest) -> None:
    request.session.pop(SESSION_CACHE_KEY, None)
    if hasattr(request, "_billing_subscription"):
        delattr(request, "_billing_subscription")


def _cache_subscription_snapshot(request: HttpRequest, *, account_id: int, plan: str, status: str, is_active: bool) -> None:
    request.session[SESSION_CACHE_KEY] = {
        "account_id": account_id,
        "plan": plan,
        "status": status,
        "is_active": is_active,
    }


def get_account_subscription(request: HttpRequest) -> AccountSubscription | None:
    cached = getattr(request, "_billing_subscription", None)
    if cached is not None:
        return cached if cached is not False else None

    account_id = getattr(request.user, "account_id", None)
    if not account_id:
        setattr(request, "_billing_subscription", False)
        return None

    subscription = AccountSubscription.objects.filter(account_id=account_id).first()
    setattr(request, "_billing_subscription", subscription if subscription is not None else False)
    if subscription is not None:
        _cache_subscription_snapshot(
            request,
            account_id=account_id,
            plan=subscription.plan,
            status=subscription.status,
            is_active=subscription.is_active,
        )
    return subscription


def get_subscription_snapshot(request: HttpRequest) -> dict[str, Any] | None:
    account_id = getattr(request.user, "account_id", None)
    if not account_id:
        return None

    cached = request.session.get(SESSION_CACHE_KEY)
    if isinstance(cached, dict) and cached.get("account_id") == account_id:
        return cached

    subscription = get_account_subscription(request)
    if subscription is None:
        return None

    return {
        "account_id": account_id,
        "plan": subscription.plan,
        "status": subscription.status,
        "is_active": subscription.is_active,
    }


def account_has_active_subscription(request: HttpRequest) -> bool:
    snapshot = get_subscription_snapshot(request)
    return bool(snapshot and snapshot.get("is_active"))


def account_has_full_plan(request: HttpRequest) -> bool:
    snapshot = get_subscription_snapshot(request)
    if not snapshot or not snapshot.get("is_active"):
        return False
    return snapshot.get("plan") == Plan.FULL


def account_has_plan(request: HttpRequest, *, plan: str) -> bool:
    snapshot = get_subscription_snapshot(request)
    if not snapshot or not snapshot.get("is_active"):
        return False
    return snapshot.get("plan") == plan


def feature_for_route(*, namespace: str, route: str) -> str:
    if route_requires_full_plan(namespace=namespace, route=route):
        return Plan.FULL
    return Plan.BASIC


def route_allowed_for_subscription(*, namespace: str, route: str, plan: str, is_active: bool) -> bool:
    if not is_active:
        return False
    required = feature_for_route(namespace=namespace, route=route)
    if required == Plan.FULL:
        return plan == Plan.FULL
    return plan in (Plan.BASIC, Plan.FULL)


def get_post_login_url(request: HttpRequest) -> str:
    from django.urls import reverse

    if account_has_full_plan(request):
        return reverse("core:dashboard")
    if account_has_active_subscription(request):
        return reverse("budget:budget_list")
    return reverse("billing:plans")


def sync_subscription_from_stripe(
    *,
    account_id: int,
    plan: str,
    status: str,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    stripe_price_id: str = "",
    current_period_end=None,
    cancel_at_period_end: bool = False,
) -> AccountSubscription:
    if plan not in SubscriptionPlan.values:
        plan = SubscriptionPlan.BASIC
    if status not in SubscriptionStatus.values:
        status = SubscriptionStatus.INCOMPLETE

    subscription, _created = AccountSubscription.objects.update_or_create(
        account_id=account_id,
        defaults={
            "plan": plan,
            "status": status,
            "stripe_customer_id": stripe_customer_id or "",
            "stripe_subscription_id": stripe_subscription_id or "",
            "stripe_price_id": stripe_price_id or "",
            "current_period_end": current_period_end,
            "cancel_at_period_end": cancel_at_period_end,
        },
    )
    return subscription
