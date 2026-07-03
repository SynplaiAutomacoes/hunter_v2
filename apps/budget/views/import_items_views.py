import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View
from apps.budget.models import Budget, BudgetItem
from apps.workshops.mixin import WorkshopScopedMixin
from .shared import _get_budget_for_workshop, _is_budget_edit_locked, LOCKED_BUDGET_EDIT_MESSAGE, _check_concurrent_budget_lock, _build_concurrent_budget_lock_response
from apps.core.presentation.widgets import SearchableSelectInput
from django import forms
from django.urls import reverse
from apps.core.presentation.forms import CoreForm
from ...core.utils import clean_id


class ImportItemsSearchForm(CoreForm):
    model = Budget
    workshop_permission_codename = "view_budget"

    reference_budget_id = forms.ChoiceField(
        label="Orçamento de Origem",
        required=True,
        widget=SearchableSelectInput(),
    )

    def __init__(self, *args, **kwargs):
        available_budgets = kwargs.pop("available_budgets", [])
        super().__init__(*args, **kwargs)
        choices = [("", "Selecione um orçamento")]
        for b in available_budgets:
            display_name = f"Orçamento #{b.id}"
            if b.customer:
                display_name += f" - {b.customer.name}"
            if b.vehicle:
                display_name += f" - {b.vehicle.plate}"
            choices.append((str(b.id), display_name))
        self.fields["reference_budget_id"].choices = choices
        self.fields["reference_budget_id"].widget.choices = choices


class BudgetImportItemsSearchModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        available_budgets = Budget.objects.filter(workshop=self.workshop).exclude(pk=budget.pk).select_related("customer", "vehicle").order_by("-id")[:50]

        form = ImportItemsSearchForm(available_budgets=available_budgets)

        context = {
            "budget": budget,
            "form": form,
        }
        return render(request, "budget/partials/import_items_search_modal.html", context)


class BudgetImportItemsSelectModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        reference_budget_id = request.POST.get("reference_budget_id")

        if not reference_budget_id:
            return HttpResponse("Nenhum orçamento selecionado.", status=400)

        reference_budget = _get_budget_for_workshop(self.workshop, reference_budget_id)

        items = reference_budget.items.select_related("product", "service", "kit").all()
        products = [item for item in items if item.product_id is not None or item.local_item_type == "product" or (item.is_local and not item.local_item_type and not item.service_id and not item.kit_id)]
        services = [item for item in items if item.service_id is not None or item.local_item_type == "service"]
        kits = [item for item in items if item.kit_id is not None]

        context = {
            "budget": budget,
            "reference_budget": reference_budget,
            "products": products,
            "services": services,
            "kits": kits,
        }
        return render(request, "budget/partials/import_items_select_modal.html", context)


class BudgetImportItemsProcessView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        selected_item_ids = [int(clean_id(item)) for item in request.POST.getlist("selected_items") if clean_id(item)]

        if not selected_item_ids:
            return HttpResponse(status=204)

        source_items = BudgetItem.objects.filter(id__in=selected_item_ids, workshop=self.workshop).select_related("product", "service", "kit").prefetch_related("kit_overrides")

        for source_item in source_items:
            existing_item = None
            if not source_item.kit_id:
                existing_item = budget.items.filter(
                    product=source_item.product,
                    service=source_item.service,
                    kit=None,
                    is_local=source_item.is_local,
                    local_item_type=source_item.local_item_type,
                    is_customer_supplied=source_item.is_customer_supplied,
                    description=source_item.description,
                    product_cost_price=source_item.product_cost_price,
                    product_selling_price=source_item.product_selling_price,
                    service_cost_price=source_item.service_cost_price,
                    service_selling_price=source_item.service_selling_price,
                    shipping=source_item.shipping,
                    duration=source_item.duration,
                ).first()

            if existing_item:
                existing_item.quantity += source_item.quantity
                existing_item.save()
            else:
                source_overrides = []
                if source_item.kit_id:
                    source_overrides = list(source_item.kit_overrides.all())

                new_item = BudgetItem.objects.get(pk=source_item.pk)
                new_item.pk = None
                new_item.budget = budget
                new_item.kit_snapshot_frozen = False
                new_item.save()

                if source_item.kit_id and source_overrides:
                    new_item.kit_overrides.all().delete()
                    for override in source_overrides:
                        override.pk = None
                        override.budget_item = new_item
                        override.save()

                    new_item.refresh_kit_snapshot_totals()

        response = HttpResponse(status=204)
        redirect_url = f"{reverse('budget:budget_update', kwargs={'pk': budget.pk})}?step=4"
        triggers = {"showToast": {"message": "Itens copiados com sucesso.", "type": "success"}, "redirectAfterToast": {"url": redirect_url, "delay": 500}}
        response["HX-Trigger"] = json.dumps(triggers)
        return response
