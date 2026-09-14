from __future__ import annotations

from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404

from apps.billing.access import (
    account_has_active_subscription,
    get_subscription_snapshot,
    route_allowed_for_subscription,
)
from apps.billing.domain.plans import Plan


class SubscriptionAccessMiddleware:
    allowed_routes = frozenset(
        {
            "accounts:login",
            "accounts:register",
            "accounts:logout",
            "accounts:password_reset",
            "accounts:password_reset_resend",
            "accounts:login_code",
            "accounts:login_code_resend",
            "billing:plans",
            "billing:checkout",
            "billing:checkout_success",
            "billing:portal",
            "billing:upgrade_required",
            "billing:webhook",
            "billing:webhook_ping",
            "billing:subscriber_list",
        }
    )

    billing_namespace = "billing"

    def __init__(self, get_response):
        self.get_response = get_response

    @classmethod
    def _get_current_route(cls, request) -> tuple[str, str]:
        cached = getattr(request, "_subscription_access_route", None)
        if isinstance(cached, tuple) and len(cached) == 2:
            return str(cached[0]), str(cached[1])

        try:
            match = resolve(request.path_info)
        except Resolver404:
            result = ("", "")
            setattr(request, "_subscription_access_route", result)
            return result

        namespace = match.namespace or ""
        url_name = match.url_name or ""
        route = f"{namespace}:{url_name}" if namespace else url_name
        result = (namespace, route)
        setattr(request, "_subscription_access_route", result)
        return result

    def __call__(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return self.get_response(request)

        if request.path.startswith("/admin/"):
            return self.get_response(request)

        namespace, route = self._get_current_route(request)
        if namespace == self.billing_namespace or route in self.allowed_routes:
            return self.get_response(request)

        if not getattr(request.user, "account_id", None):
            return self.get_response(request)

        if not account_has_active_subscription(request):
            return redirect(reverse("billing:plans"))

        snapshot = get_subscription_snapshot(request) or {}
        plan = str(snapshot.get("plan") or Plan.BASIC)
        is_active = bool(snapshot.get("is_active"))

        if not route_allowed_for_subscription(namespace=namespace, route=route, plan=plan, is_active=is_active):
            if getattr(request, "htmx", False):
                from django.template.response import TemplateResponse

                return TemplateResponse(request, "billing/upgrade_required.html", status=403)
            return redirect(reverse("billing:upgrade_required"))

        return self.get_response(request)
