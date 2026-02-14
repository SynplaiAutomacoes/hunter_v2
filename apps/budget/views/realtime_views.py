from __future__ import annotations

import time

from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.http import StreamingHttpResponse
from django.views import View

from apps.budget.realtime import get_budget_status_version


class BudgetEventsView(LoginRequiredMixin, View):
    def get(self, request):
        check_interval = max(float(getattr(settings, "BUDGET_SSE_CHECK_INTERVAL_SECONDS", 3)), 1.0)

        def event_stream():
            last_version = get_budget_status_version()
            heartbeat_at = time.monotonic()

            while True:
                current_version = get_budget_status_version()
                if current_version != last_version:
                    last_version = current_version
                    yield f"event: budget-status-changed\ndata: {current_version}\n\n"

                now = time.monotonic()
                if now - heartbeat_at >= 30:
                    heartbeat_at = now
                    yield ": keepalive\n\n"

                time.sleep(check_interval)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
