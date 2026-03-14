from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.core.templatetags.table_tags import TableColumn
from apps.finance.forms.dre import DreForm
from apps.finance.models import FinancialGroup
from apps.workshops.models.workshops import Workshop
from apps.workshops.mixin import WorkshopScopedMixin


class DreReportView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = FinancialGroup
    workshop_permission_codename = "view_financialgroup"
    template_name = "finance/dre/dre.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
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

        selected_filial = (self.request.GET.get("filial") or "").strip()
        selected_workshop = None
        if selected_filial:
            try:
                selected_filial_id = int(selected_filial)
            except (TypeError, ValueError):
                selected_filial_id = None

            if selected_filial_id is not None:
                selected_workshop = workshops_qs.filter(pk=selected_filial_id).first()

        if selected_workshop is None:
            financial_groups = FinancialGroup.objects.none()
            empty_text = "É necessário selecionar uma filial"
        else:
            financial_groups = FinancialGroup.objects.filter(workshop=selected_workshop).order_by("sort_key", "id")
            empty_text = "Não há grupos financeiros"

        financial_groups_count = financial_groups.count()
        context["financial_groups"] = financial_groups
        context["financial_groups_per_page"] = max(financial_groups_count, 1)
        context["dre_financial_groups_empty_text"] = empty_text
        context["dre_financial_groups_selectable"] = financial_groups_count > 0
        context["dre_table_fields"] = [
            TableColumn(
                label="Grupo Financeiro",
                attr="dre_hierarchy_label",
                sortable=False,
                searchable=False,
            )
        ]

        form = DreForm(self.request.GET or None, workshops=workshops, financial_groups_qs=financial_groups)
        context["form"] = form

        return context
