from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from djmoney.money import Money
import holidays

from apps.collaborators.services import compute_salary_cost_amount_for_kind, compute_salary_monthly_cost_amounts, sync_current_month_salary_costs
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.forms.workshop_costs import WorkshopCostForm
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem


class WorkshopCostListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkshopCost
    template_name = "workshop_costs/workshop_cost_list.html"
    context_object_name = "workshop_costs"
    htmx_template_name = "workshop_costs/partials/workshop_cost_table.html"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label="Mês/Ano", attr="__str__", search_by=("month", "year")),
            TableColumn(label="Mecânicos", attr="mechanic_quantity"),
            TableColumn(label="Horas úteis/mês", attr="working_hours_per_month"),
            TableColumn(label="Total Geral", attr="total_monthly_costs"),
            TableColumn(label="Multiplicador de Lucratividade", attr="profitability_multiplier"),
            TableColumn(label="Custo Hora Mínimo", attr="minimum_hourly_cost"),
            TableColumn(label="Valor Sua Hora", attr="hourly_cost_value"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workshops:workshop_cost_update"),
            TableActionDefaults.copy("workshops:workshop_cost_copy"),
            TableActionDefaults.delete("workshops:workshop_cost_delete"),
        ]

        return context


class WorkshopCostCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCost
    form_class = WorkshopCostForm
    template_name = "workshop_costs/workshop_cost_create.html"
    success_url = reverse_lazy("workshops:workshop_cost_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class WorkshopCostUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = WorkshopCost
    form_class = WorkshopCostForm
    template_name = "workshop_costs/workshop_cost_update.html"
    success_url = reverse_lazy("workshops:workshop_cost_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class WorkshopCostCopyView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCost
    form_class = WorkshopCostForm
    template_name = "workshop_costs/workshop_cost_create.html"
    success_url = reverse_lazy("workshops:workshop_cost_list")

    def get_initial(self):
        initial = super().get_initial()
        original_instance = self.get_object()

        # Referência
        initial["month"] = original_instance.month
        initial["year"] = original_instance.year

        # Mecânicos
        initial["mechanic_quantity"] = original_instance.mechanic_quantity
        initial["work_hours_per_day"] = original_instance.work_hours_per_day
        initial["working_hours_per_month"] = original_instance.working_hours_per_month
        initial["productivity_average"] = original_instance.productivity_average

        # Taxas
        initial["card_rate"] = original_instance.card_rate
        initial["tax_rate"] = original_instance.tax_rate
        initial["profit_margin"] = original_instance.profit_margin
        initial["commission_rate"] = original_instance.commission_rate
        initial["risk_coefficient"] = original_instance.risk_coefficient

        # Metas Inputs
        initial["parts_purchase_cap"] = original_instance.parts_purchase_cap
        initial["freight_cost"] = original_instance.freight_cost
        initial["third_party_service_cap"] = original_instance.third_party_service_cap

        for item in original_instance.items.all():
            field_name = f"cost_item_{item.monthly_cost_id}"
            initial[field_name] = item.amount

        initial["work_day_dates"] = ",".join(work_day.date.isoformat() for work_day in original_instance.work_days.order_by("date"))

        # Calculados (Readonly)
        initial["total_value"] = original_instance.total_value
        initial["total_monthly_costs"] = original_instance.total_monthly_costs
        initial["profit_target"] = original_instance.profit_target
        initial["gross_revenue_target"] = original_instance.gross_revenue_target
        initial["profitability_multiplier"] = original_instance.profitability_multiplier

        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class WorkshopCostDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopCost
    success_url = reverse_lazy("workshops:workshop_cost_list")

    htmx_trigger = "workshop-costs-table-refresh"


class WorkshopCostCalculateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCost
    workshop_permission_codename = "view_workshopcost"

    def post(self, request, *args, **kwargs):
        form = WorkshopCostForm(request.POST, workshop=self.workshop)

        try:
            form.full_clean()
        except Exception:
            pass

        instance = form.instance
        cost_items = []

        @dataclass
        class MockItem:
            amount: Money

        cleaned_data = getattr(form, "cleaned_data", {})

        for cost in form.active_costs:
            field_name = f"cost_item_{cost.id}"
            amount = cleaned_data.get(field_name)

            if amount is None:
                amount = Money(0, "BRL")

            cost_items.append(MockItem(amount=amount))

        total_value = instance.calculate_total_value()
        total_monthly_costs = instance.calculate_total_monthly_costs(items=cost_items)
        profit_target = cleaned_data.get("profit_target")
        if profit_target is None:
            profit_target = self._money_from_post(request.POST, "profit_target")
        if profit_target is None:
            profit_target = Money(0, "BRL")
        gross_revenue_target = instance.calculate_gross_revenue_target(total_monthly_costs, profit_target, total_value)
        profitability_multiplier = instance.calculate_profitability_multiplier(gross_revenue_target, total_value)

        instance.total_value = total_value
        instance.total_monthly_costs = total_monthly_costs
        instance.profit_target = profit_target
        instance.gross_revenue_target = gross_revenue_target
        instance.profitability_multiplier = profitability_multiplier

        instance.calculate_monthly_costs()

        response_form = WorkshopCostForm(instance=instance, workshop=self.workshop)

        return render(request, "workshop_costs/partials/workshop_cost_calculation_results.html", {"form": response_form})

    @staticmethod
    def _money_from_post(post_data, field_name: str) -> Money | None:
        amount_raw = post_data.get(f"{field_name}_0")
        currency_raw = post_data.get(f"{field_name}_1") or "BRL"
        if amount_raw in (None, ""):
            return None
        try:
            raw_str = str(amount_raw).strip()
            if "," in raw_str:
                raw_str = raw_str.replace(".", "").replace(",", ".")
            amount = Decimal(raw_str)
        except (InvalidOperation, TypeError, ValueError):
            return None
        if str(currency_raw).replace(".", "", 1).replace("-", "", 1).isdigit():
            currency_raw = "BRL"
        return Money(amount, str(currency_raw or "BRL"))


class WorkshopCostSyncSalaryItemsView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCost
    workshop_permission_codename = "change_workshopcost"
    VALID_COST_KINDS = frozenset({"productive", "administrative", "pro_labore", "transport"})

    def post(self, request, *args, **kwargs):
        try:
            month = int(request.POST.get("month") or 0)
            year = int(request.POST.get("year") or 0)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Mês ou ano inválido."}, status=400)

        if month < 1 or month > 12 or year < 1:
            return JsonResponse({"error": "Mês ou ano inválido."}, status=400)

        cost_kind = str(request.POST.get("cost_kind") or "").strip()
        if cost_kind and cost_kind not in self.VALID_COST_KINDS:
            return JsonResponse({"error": "Tipo de custo inválido."}, status=400)

        reference_date = date(year, month, 1)
        workshop_cost = WorkshopCost.objects.filter(workshop=self.workshop, month=month, year=year).first()
        work_days_override: int | None = None
        if workshop_cost is None:
            try:
                work_days_override = int(request.POST.get("work_days_per_month") or 0)
            except (TypeError, ValueError):
                work_days_override = 0

        if cost_kind:
            try:
                monthly_cost_id = int(request.POST.get("monthly_cost_id") or 0)
            except (TypeError, ValueError):
                return JsonResponse({"error": "Custo mensal inválido."}, status=400)

            monthly_cost = MonthlyCost.objects.filter(pk=monthly_cost_id, workshop=self.workshop, is_active=True).first()
            if monthly_cost is None:
                return JsonResponse({"error": "Custo mensal não encontrado."}, status=404)

            amount = compute_salary_cost_amount_for_kind(
                workshop=self.workshop,
                cost_kind=cost_kind,
                reference_date=reference_date,
                work_days_override=work_days_override,
            )
            if workshop_cost is not None:
                WorkshopCostItem.objects.update_or_create(
                    workshop_cost=workshop_cost,
                    monthly_cost=monthly_cost,
                    defaults={"amount": amount},
                )
                workshop_cost.calculate_all()
                workshop_cost.save()

            return JsonResponse(
                {
                    "fields": {
                        f"cost_item_{monthly_cost.pk}_0": str(amount.amount),
                        f"cost_item_{monthly_cost.pk}_1": str(amount.currency),
                    },
                    "synced": workshop_cost is not None,
                }
            )

        if workshop_cost is not None:
            sync_current_month_salary_costs(workshop=self.workshop, reference_date=reference_date)

        amounts = compute_salary_monthly_cost_amounts(
            workshop=self.workshop,
            reference_date=reference_date,
            work_days_override=work_days_override,
        )
        fields: dict[str, str] = {}
        for monthly_cost_id, amount in amounts.items():
            fields[f"cost_item_{monthly_cost_id}_0"] = str(amount.amount)
            fields[f"cost_item_{monthly_cost_id}_1"] = str(amount.currency)

        return JsonResponse({"fields": fields, "synced": workshop_cost is not None})


class WorkshopCostSelectionModalView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = WorkshopCost
    template_name = "workshop_costs/partials/copy_selection_modal.html"
    context_object_name = "workshop_costs"

    def get_queryset(self):
        return super().get_queryset().order_by("-year", "-month")


class WorkshopCostHolidaysView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_codename = "view_workshopcost"

    def get(self, request, *args, **kwargs):
        from datetime import timedelta

        state = request.GET.get("state", "SP")
        try:
            month = int(request.GET.get("month", 0))
            year = int(request.GET.get("year", 0))
        except (TypeError, ValueError):
            return JsonResponse({"holidays": []})

        if not month or not year or month < 1 or month > 12:
            return JsonResponse({"holidays": []})

        holiday_calendar = holidays.Brazil(state=state, years=year)
        holiday_dates = []

        for holiday_date in holiday_calendar.keys():
            if holiday_date.year == year and holiday_date.month == month and holiday_date.weekday() < 5:
                holiday_dates.append(holiday_date.isoformat())

        good_friday_dates = [d for d in holiday_calendar.keys() if "Sexta" in str(holiday_calendar[d]) and d.year == year]
        if good_friday_dates:
            easter = good_friday_dates[0] + timedelta(days=2)

            movable_holidays = [
                easter - timedelta(days=48),
                easter - timedelta(days=47),
                easter - timedelta(days=46),
                easter + timedelta(days=60),
            ]

            for movable_date in movable_holidays:
                if movable_date.year == year and movable_date.month == month and movable_date.weekday() < 5:
                    holiday_dates.append(movable_date.isoformat())

        return JsonResponse({"holidays": sorted(set(holiday_dates))})
