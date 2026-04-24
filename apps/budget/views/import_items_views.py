import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View
from apps.budget.models import Budget, BudgetItem, BudgetKitItemOverride
from apps.workshops.mixin import WorkshopScopedMixin
from .shared import _get_budget_for_workshop
from apps.core.widgets import SearchableSelectInput
from django import forms
from django.urls import reverse

class ImportItemsSearchForm(forms.Form):
    model = Budget
    workshop_permission_codename = "view_budget"

    reference_budget_id = forms.ChoiceField(
        label="Orçamento de Origem",
        required=True,
        widget=SearchableSelectInput(
            attrs={
                "class": "select select-bordered w-full",
                "data-placeholder": "Selecione um orçamento...",
            }
        ),
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
        budget = _get_budget_for_workshop(self.workshop, pk)
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
        budget = _get_budget_for_workshop(self.workshop, pk)
        reference_budget_id = request.POST.get("reference_budget_id")
        
        if not reference_budget_id:
            return HttpResponse("Nenhum orçamento selecionado.", status=400)
            
        reference_budget = _get_budget_for_workshop(self.workshop, reference_budget_id)
        
        items = reference_budget.items.select_related("product", "service", "kit").all()
        products = [item for item in items if item.product_id is not None or (item.is_local and not item.service_id and not item.kit_id)]
        services = [item for item in items if item.service_id is not None]
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
        budget = _get_budget_for_workshop(self.workshop, pk)
        
        selected_item_ids = request.POST.getlist("selected_items")
        
        if not selected_item_ids:
            return HttpResponse(status=204)
            
        source_items = BudgetItem.objects.filter(id__in=selected_item_ids, workshop=self.workshop)
        
        for source_item in source_items:
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
        triggers = {
            "showToast": {"message": "Itens copiados com sucesso.", "type": "success"},
            "redirectAfterToast": {"url": redirect_url, "delay": 500}
        }
        response["HX-Trigger"] = json.dumps(triggers)
        return response
