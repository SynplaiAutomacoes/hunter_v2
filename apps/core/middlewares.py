from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import connections
from django.shortcuts import redirect
from django.urls import resolve, reverse


logger = logging.getLogger("performance.request")


class RequestPerformanceLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "PERF_LOGGING_ENABLED", False):
            return self.get_response(request)

        start = time.perf_counter()
        should_capture_queries = bool(getattr(settings, "PERF_LOG_QUERIES", False))
        min_duration_ms = int(getattr(settings, "PERF_LOG_MIN_MS", 300))

        previous_force_debug: dict[str, bool] = {}
        if should_capture_queries:
            for alias in connections:
                connection = connections[alias]
                previous_force_debug[alias] = connection.force_debug_cursor
                connection.force_debug_cursor = True

        response = None
        try:
            response = self.get_response(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status_code = getattr(response, "status_code", 500)

            query_count = 0
            sql_time_ms = 0.0
            if should_capture_queries:
                for alias in connections:
                    connection = connections[alias]
                    query_count += len(connection.queries)
                    sql_time_ms += sum(float(query.get("time", 0.0)) for query in connection.queries) * 1000
                    connection.force_debug_cursor = previous_force_debug.get(alias, False)

            if duration_ms >= min_duration_ms:
                logger.warning(
                    "request_performance method=%s path=%s status=%s duration_ms=%.2f query_count=%s sql_time_ms=%.2f user_id=%s",
                    request.method,
                    request.path,
                    status_code,
                    duration_ms,
                    query_count,
                    sql_time_ms,
                    getattr(request.user, "id", None),
                )


class RequireFirstWorkshopMiddleware:
    allowed_routes = {
        "workshops:create",
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

    def __call__(self, request):
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
