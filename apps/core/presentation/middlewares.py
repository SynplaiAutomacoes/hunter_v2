from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.conf import settings
from django.db import connections
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import resolve, reverse

from apps.core.logging_filters import clear_request_context, set_request_context
from apps.core.observability import SqlTimingWrapper, annotate_current_span, build_http_metric_attributes, change_active_requests, record_http_request


logger = logging.getLogger("performance.request")


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        setattr(request, "request_id", request_id)
        set_request_context(request_id, None, None, None)

        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            clear_request_context()


class RequestPerformanceLoggingMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not getattr(settings, "PERF_LOGGING_ENABLED", False):
            return self.get_response(request)

        self._refresh_request_context(request)

        start = time.perf_counter()
        should_capture_queries = bool(getattr(settings, "PERF_LOG_QUERIES", False))
        min_duration_ms = int(getattr(settings, "PERF_LOG_MIN_MS", 300))
        active_request_attributes = build_http_metric_attributes(
            method=request.method or "UNKNOWN",
            route=_get_route_name(request),
            status_code=0,
            target_group=_get_target_group(request),
            error=False,
        )
        change_active_requests(1, attributes=active_request_attributes)

        sql_wrappers: list[SqlTimingWrapper] | None = None
        if should_capture_queries:
            sql_wrappers = []
            for alias in connections:
                wrapper = SqlTimingWrapper()
                sql_wrappers.append(wrapper)
                connections[alias].execute_wrappers.append(wrapper)

        response = None
        try:
            response = self.get_response(request)
            return response
        finally:
            self._refresh_request_context(request)
            duration_ms = (time.perf_counter() - start) * 1000

            query_count = 0
            sql_time_ms = 0.0
            if should_capture_queries and sql_wrappers:
                sql_wrappers.reverse()
                for wrapper in sql_wrappers:
                    for alias in connections:
                        try:
                            connections[alias].execute_wrappers.remove(wrapper)
                        except ValueError:
                            pass
                for wrapper in sql_wrappers:
                    result = wrapper.collect()
                    query_count += result.query_count
                    sql_time_ms += result.sql_time_ms

            status_code = getattr(response, "status_code", 500)
            route = _get_route_name(request)
            target_group = _get_target_group(request)
            is_error = status_code >= 500

            metric_attributes = build_http_metric_attributes(
                method=request.method or "UNKNOWN",
                route=route,
                status_code=status_code,
                target_group=target_group,
                error=is_error,
            )
            record_http_request(duration_ms=duration_ms, attributes=metric_attributes)
            change_active_requests(-1, attributes=active_request_attributes)
            annotate_current_span(
                {
                    "http.request.method": request.method,
                    "http.route": route,
                    "http.response.status_code": status_code,
                    "app.request_id": getattr(request, "request_id", None),
                    "app.workshop_id": getattr(getattr(request, "workshop", None), "id", None),
                    "app.user_id": getattr(getattr(request, "user", None), "id", None),
                    "app.account_id": getattr(getattr(request, "user", None), "account_id", None),
                    "app.query_count": query_count,
                    "app.sql_time_ms": round(sql_time_ms, 2),
                }
            )

            log_extra = {
                "method": request.method,
                "path": request.path,
                "route": route,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "query_count": query_count,
                "sql_time_ms": round(sql_time_ms, 2),
                "response_bytes": _get_response_size_bytes(response),
                "htmx": bool(getattr(request, "htmx", False)),
            }

            if duration_ms >= min_duration_ms or is_error:
                logger.warning(
                    "request_completed",
                    extra=log_extra,
                )
            else:
                logger.info(
                    "request_completed",
                    extra=log_extra,
                )

    @staticmethod
    def _refresh_request_context(request: HttpRequest) -> None:
        set_request_context(
            getattr(request, "request_id", None),
            getattr(getattr(request, "workshop", None), "id", None),
            getattr(getattr(request, "user", None), "id", None),
            getattr(getattr(request, "user", None), "account_id", None),
        )


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

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            if request.path.startswith("/admin/"):
                return self.get_response(request)

            match = resolve(request.path_info)
            current = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name

            if current not in self.allowed_routes:
                if not getattr(request.user, "account_id", None):
                    return redirect(reverse("accounts:logout"))

                if request.user.is_account_owner:
                    from apps.workshops.models.workshops import Workshop

                    if not Workshop.objects.filter(
                        account_id=request.user.account_id,
                        is_active=True,
                    ).exists():
                        return redirect(reverse("workshops:create"))
                else:
                    from apps.collaborators.models import WorkshopMember

                    if not WorkshopMember.objects.filter(
                        user=request.user,
                        is_active=True,
                        workshop__account_id=request.user.account_id,
                        workshop__is_active=True,
                    ).exists():
                        return redirect(reverse("accounts:logout"))

        return self.get_response(request)


def _get_route_name(request: HttpRequest) -> str:
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is not None:
        if resolver_match.view_name:
            return str(resolver_match.view_name)
        if resolver_match.route:
            return str(resolver_match.route)

    if request.path.startswith("/admin/"):
        return "admin"

    return request.path


def _get_target_group(request: HttpRequest) -> str:
    route = _get_route_name(request)
    normalized_route = route.lstrip("/")
    first_segment = normalized_route.split(":", 1)[0].split("/", 1)[0].strip()
    return first_segment or "root"


def _get_response_size_bytes(response: HttpResponse | None) -> int | None:
    if response is None:
        return None

    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            return int(content_length)
        except ValueError:
            return None

    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        return len(content)

    return None
