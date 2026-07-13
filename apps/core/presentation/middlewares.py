from __future__ import annotations

import logging
import time
import uuid
from contextlib import ExitStack
from typing import Any

from django.conf import settings
from django.db import connections
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404

from apps.core.logging_filters import (
    clear_request_context,
    get_dependency_timing,
    reset_dependency_timing,
    set_request_context,
)
from apps.core.observability import (
    SqlTimingWrapper,
    annotate_current_span,
    build_http_metric_attributes,
    change_active_requests,
    record_http_request,
)


logger = logging.getLogger("performance.request")


def _resolve_route(request: Any) -> str:
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is not None:
        view_name = getattr(resolver_match, "view_name", None)
        if view_name:
            return str(view_name)
        route = getattr(resolver_match, "route", None)
        if route:
            return str(route)

    try:
        match = resolve(request.path_info)
    except Resolver404:
        return request.path

    if match.namespace and match.url_name:
        return f"{match.namespace}:{match.url_name}"
    if match.url_name:
        return str(match.url_name)
    return request.path


def _resolve_workshop_id(request: Any) -> int | None:
    workshop = getattr(request, "workshop", None)
    workshop_id = getattr(workshop, "id", None) or getattr(workshop, "pk", None)
    if workshop_id is not None:
        return int(workshop_id)

    cached_workshop = getattr(request, "_active_workshop_obj", None)
    cached_id = getattr(cached_workshop, "id", None) or getattr(cached_workshop, "pk", None)
    if cached_id is not None:
        return int(cached_id)

    session = getattr(request, "session", None)
    if session is None:
        return None
    session_workshop_id = session.get("active_workshop_id")
    if session_workshop_id is None:
        return None
    try:
        return int(session_workshop_id)
    except (TypeError, ValueError):
        return None


def _resolve_target_group(route: str) -> str:
    if ":" in route:
        return route.split(":", 1)[0]
    if "/" in route:
        return route.split("/", 1)[0]
    return route or "unknown"


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.request_id = request_id

        user = getattr(request, "user", None)
        user_id = getattr(user, "id", None) if user is not None else None
        account_id = getattr(user, "account_id", None) if user is not None else None

        reset_dependency_timing()
        set_request_context(request_id, None, user_id, account_id)

        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            clear_request_context()


class RequestPerformanceLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "PERF_LOGGING_ENABLED", False):
            return self.get_response(request)

        start = time.perf_counter()
        should_capture_queries = bool(getattr(settings, "PERF_LOG_QUERIES", False))
        min_duration_ms = int(getattr(settings, "PERF_LOG_MIN_MS", 300))
        sql_wrapper = SqlTimingWrapper() if should_capture_queries else None

        active_attributes = build_http_metric_attributes(
            method=request.method,
            route="pending",
            status_code=0,
            target_group="pending",
            error=False,
        )
        change_active_requests(1, attributes=active_attributes)

        response = None
        caught_exc: Exception | None = None
        try:
            with ExitStack() as stack:
                if sql_wrapper is not None:
                    for alias in connections:
                        stack.enter_context(connections[alias].execute_wrapper(sql_wrapper))
                response = self.get_response(request)
            return response
        except Exception as exc:
            caught_exc = exc
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = int(getattr(response, "status_code", 500))
            route = _resolve_route(request)
            target_group = _resolve_target_group(route)
            is_error = status_code >= 500
            metric_attributes = build_http_metric_attributes(
                method=request.method,
                route=route,
                status_code=status_code,
                target_group=target_group,
                error=is_error,
            )

            query_count = 0
            sql_time_ms = 0.0
            if sql_wrapper is not None:
                sql_result = sql_wrapper.collect()
                query_count = sql_result.query_count
                sql_time_ms = round(sql_result.sql_time_ms, 2)

            dependency_time_ms, dependency_call_count = get_dependency_timing()
            workshop_id = _resolve_workshop_id(request)
            request_id = getattr(request, "request_id", None)
            user = getattr(request, "user", None)
            user_id = getattr(user, "id", None) if user is not None else None
            account_id = getattr(user, "account_id", None) if user is not None else None
            set_request_context(request_id, workshop_id, user_id, account_id)

            annotate_current_span(
                {
                    "http.method": request.method,
                    "http.route": route,
                    "http.status_code": status_code,
                    "http.target_group": target_group,
                    "request.id": request_id,
                    "workshop.id": workshop_id,
                    "db.query_count": query_count,
                    "db.sql_time_ms": sql_time_ms,
                    "dependency.time_ms": dependency_time_ms,
                    "dependency.call_count": dependency_call_count,
                }
            )
            record_http_request(duration_ms=duration_ms, attributes=metric_attributes)
            change_active_requests(-1, attributes=active_attributes)

            log_extra: dict[str, Any] = {
                "method": request.method,
                "route": route,
                "path": request.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "query_count": query_count,
                "sql_time_ms": sql_time_ms,
                "dependency_time_ms": dependency_time_ms,
                "dependency_call_count": dependency_call_count,
                "request_id": request_id,
                "workshop_id": workshop_id,
            }

            log_message = "request_completed"
            if is_error:
                if caught_exc is not None:
                    logger.error(
                        log_message,
                        extra=log_extra,
                        exc_info=(type(caught_exc), caught_exc, caught_exc.__traceback__),
                    )
                else:
                    logger.error(log_message, extra=log_extra)
            elif duration_ms >= min_duration_ms:
                logger.warning(log_message, extra=log_extra)
            else:
                logger.info(log_message, extra=log_extra)


class RequireFirstWorkshopMiddleware:
    allowed_routes = {
        "workshops:create",
        "workshops:webmania_company_sync",
        "accounts:login",
        "accounts:register",
        "accounts:logout",
        "iam:role_list",
        "iam:role_create",
        "iam:role_update",
        "iam:role_delete",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    @classmethod
    def _get_current_route(cls, request) -> str:
        cached_route = getattr(request, "_require_first_workshop_route", None)
        if cached_route is not None:
            return cached_route

        match = resolve(request.path_info)
        current_route = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
        setattr(request, "_require_first_workshop_route", current_route)
        return current_route

    @staticmethod
    def _get_cached_access_flag(request, *, cache_key: str, account_id: int | None) -> bool | None:
        cached = request.session.get(cache_key)
        if not isinstance(cached, dict):
            return None
        if cached.get("account_id") != account_id:
            return None
        return bool(cached.get("value"))

    @staticmethod
    def _set_cached_access_flag(request, *, cache_key: str, account_id: int | None, value: bool) -> None:
        request.session[cache_key] = {"account_id": account_id, "value": bool(value)}

    def _account_owner_has_workshop(self, request) -> bool:
        account_id = getattr(request.user, "account_id", None)
        cached = self._get_cached_access_flag(request, cache_key="require_first_workshop_owner_access", account_id=account_id)
        if cached is not None:
            return cached

        from apps.workshops.models.workshops import Workshop

        has_workshop = Workshop.objects.filter(account_id=account_id, is_active=True).exists()
        self._set_cached_access_flag(request, cache_key="require_first_workshop_owner_access", account_id=account_id, value=has_workshop)
        return has_workshop

    def _member_has_workshop(self, request) -> bool:
        account_id = getattr(request.user, "account_id", None)
        cached = self._get_cached_access_flag(request, cache_key="require_first_workshop_member_access", account_id=account_id)
        if cached is not None:
            return cached

        from apps.collaborators.models import WorkshopMember

        has_workshop = WorkshopMember.objects.filter(
            user=request.user,
            is_active=True,
            workshop__account_id=account_id,
            workshop__is_active=True,
        ).exists()
        self._set_cached_access_flag(request, cache_key="require_first_workshop_member_access", account_id=account_id, value=has_workshop)
        return has_workshop

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.path.startswith("/admin/"):
                return self.get_response(request)

            current = self._get_current_route(request)

            if current not in self.allowed_routes:
                if not getattr(request.user, "account_id", None):
                    return redirect(reverse("accounts:logout"))

                if request.user.is_account_owner:
                    if not self._account_owner_has_workshop(request):
                        return redirect(reverse("workshops:create"))
                else:
                    if not self._member_has_workshop(request):
                        return redirect(reverse("accounts:logout"))

        return self.get_response(request)
