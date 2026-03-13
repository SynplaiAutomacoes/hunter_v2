from __future__ import annotations

from typing import Any

from apps.workshops.models.workshops import Workshop

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.finance.models import FinancialGroup
from apps.workshops.mixin import WorkshopScopedMixin


class DreReportView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    template_name = "finance/dre/dre.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        financial_groups = FinancialGroup.objects.all().order_by("sort_key")
        context["financial_groups"] = financial_groups

        workshops_qs = (
            Workshop.objects.filter(
                account_id=self.request.user.account_id,
                is_active=True,
                members__user=self.request.user,
                members__is_active=True,
            )
            .distinct()  # Remove duplicatas
            .order_by("name")
        )

        workshops = list(workshops_qs)

        filial = self.request.GET.get("filial", "")
        data_inicial = self.request.GET.get("data_inicial", "")
        data_final = self.request.GET.get("data_final", "")
        tipo_data = self.request.GET.get("tipo_data", "")

        context["workshops"] = workshops
        context["filial"] = filial
        context["data_inicial"] = data_inicial
        context["data_final"] = data_final
        context["tipo_data"] = tipo_data

        return context