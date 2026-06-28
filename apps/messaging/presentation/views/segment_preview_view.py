from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from apps.customer.models import Customer
from apps.messaging.domain.value_objects import FilterCriteria
from apps.messaging.infrastructure.services.segment_query_builder import resolve_segment
from apps.workshops.mixin import WorkshopScopedMixin


class CustomerMessageGroupSegmentPreviewView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Customer
    workshop_permission_codename = "view_customer"

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        raw_criteria = request.GET.get("filter_criteria", "")
        if not raw_criteria:
            return JsonResponse({"count": 0, "customers": []})

        try:
            criteria_data = json.loads(raw_criteria)
            criteria = FilterCriteria.from_dict(criteria_data)
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({"error": str(e)}, status=400)

        customers = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        total_count = customers.count()
        sample = list(customers.values("id", "name", "phone", "email")[:10])
        for c in sample:
            if c.get("phone") is not None:
                c["phone"] = str(c["phone"])

        return JsonResponse(
            {
                "count": total_count,
                "customers": sample,
            }
        )
