from __future__ import annotations

import time

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import StreamingHttpResponse
from django.views import View

from apps.budget.realtime import get_budget_status_version


class BudgetEventsView(LoginRequiredMixin, View):
    def get(self, request):
        def event_stream():
            last_version = get_budget_status_version()
            heartbeat_at = time.monotonic()

            while True:
                current_version = get_budget_status_version()
                if current_version != last_version:
                    last_version = current_version
                    yield f"event: budget-status-changed\ndata: {current_version}\n\n"

                now = time.monotonic()
                if now - heartbeat_at >= 15:
                    heartbeat_at = now
                    yield ": keepalive\n\n"

                time.sleep(1)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
