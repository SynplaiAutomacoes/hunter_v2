import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView

from apps.budget.forms import BudgetItemEditForm, BudgetStep1Form, BudgetStep2Form, BudgetStep3Form, BudgetStep4Form, BudgetStep5Form, BudgetStep6Form
from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.customer.models import Customer, Vehicle
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.util.workshops import get_active_workshop_or_404


class BudgetListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Budget
    template_name = "budget/budget_list.html"
    context_object_name = "budget"
    htmx_template_name = "budget/partials/budget_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(Budget.customer.field.verbose_name, attr=Budget.customer.field.name),
            TableColumn(Budget.vehicle.field.verbose_name, attr=Budget.vehicle.field.name),
            TableColumn(Budget.collaborator.field.verbose_name, attr="collaborator_name"),
            TableColumn(Budget.criado_em.field.verbose_name, attr=Budget.criado_em.field.name),
            TableColumn("Valor Total", attr="total_budget_value"),
            TableColumn(Budget.status.field.verbose_name, attr="budget_status"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("budget:budget_update"),
            TableActionDefaults.delete("budget:budget_delete"),
        ]
        return context


class BudgetCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = Budget
    template_name = "budget/budget_form.html"

    steps_definition = [
        {"title": "Dados do Cliente", "form_class": BudgetStep1Form},
        {"title": "Relato do Cliente", "form_class": BudgetStep2Form},
        {"title": "Diagnóstico", "form_class": BudgetStep3Form},
        {"title": "Peças e Serviços", "form_class": BudgetStep4Form},
        {"title": "Método de Precificação", "form_class": BudgetStep5Form},
        {"title": "Revisão e Confirmação", "form_class": BudgetStep6Form},
    ]

    def get(self, request, *args, **kwargs):
        today = timezone.now()
        if not WorkshopCost.objects.filter(workshop=self.workshop, month=today.month, year=today.year).exists():
            messages.warning(request, "Cadastre um custo mensal da oficina para este mês antes de prosseguir.")
            return redirect("budget:budget_list")

        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.htmx:
            return ["budget/partials/budget_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if pk:
            return Budget.objects.get(pk=pk, workshop=self.workshop)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["workshop"] = self.workshop
        kwargs["instance"] = self.get_object()
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user

        self.object = form.save()  # Salva o progresso atual

        current_step = self.get_current_step()
        if self.object.current_step < current_step + 1:
            self.object.current_step = current_step + 1
            self.object.save(update_fields=["current_step"])

        if current_step < len(self.steps_definition):
            next_step = current_step + 1
            success_url = f"{reverse('budget:budget_create')}?step={next_step}&pk={self.object.pk}"

            if self.request.htmx:
                response = redirect(success_url)
                response["HX-Push-Url"] = success_url
                return response

            return redirect(success_url)

        return super().form_valid(form)


class BudgetUpdateView(BudgetCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if not self.budget_object:
            return redirect("budget:budget_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return Budget.objects.get(pk=pk)
        return super().get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        # Mantemos a lógica de salvar o workshop e colaborador
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user
        self.object = form.save()

        current_step = self.get_current_step()

        # Lógica de progressão de etapa (opcional em Update, mas útil se ele puder avançar)
        if self.object.current_step < current_step + 1:
            self.object.current_step = current_step + 1
            self.object.save(update_fields=["current_step"])

        if current_step < len(self.steps_definition):
            next_step = current_step + 1
            # Importante: Apontamos para budget_update para manter o contexto de edição
            success_url = f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={next_step}"

            if self.request.htmx:
                response = redirect(success_url)
                response["HX-Push-Url"] = success_url
                return response

            return redirect(success_url)

        # Se for o último passo, volta para a lista
        return redirect(reverse("budget:budget_list"))


class BudgetDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Budget
    success_url = reverse_lazy("budget:budget_list")

    htmx_template_name = "budget/partials/budget_delete_modal.html"
    htmx_trigger = "budget-table-refresh"


class CustomerDetailView(View):
    def get(self, request, *args, **kwargs):
        customer_id = request.GET.get("customer")
        customer = None
        if customer_id:
            customer = get_object_or_404(Customer, id=customer_id)
        return render(request, "budget/partials/customer_resume.html", {"customer": customer})


class VehicleListView(View):
    def get(self, request, *args, **kwargs):
        customer_id = request.GET.get("customer")

        vehicles = Vehicle.objects.none()
        if customer_id:
            vehicles = Vehicle.objects.filter(customer_id=customer_id)

        data = [{"id": v.id, "label": str(v)} for v in vehicles]

        return JsonResponse(data, safe=False)


class VehicleDetailView(View):
    def get(self, request, *args, **kwargs):
        vehicle_id = request.GET.get("vehicle")
        vehicle = None
        if vehicle_id:
            vehicle = get_object_or_404(Vehicle, id=vehicle_id)
        return render(request, "budget/partials/vehicle_resume.html", {"vehicle": vehicle})


class ItemSelectionModalView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = Budget
    template_name = "budget/partials/modal_item_list.html"
    workshop_permission_codename = "add_budget"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        budget_id = self.kwargs.get("budget_id")
        item_type = self.kwargs.get("item_type")

        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        map_config = {
            "product": (Product, "Selecionar Produto"),
            "service": (Service, "Selecionar Serviço"),
            "kit": (Kit, "Selecionar Kit"),
        }

        model_class, title = map_config.get(item_type, (Product, "Selecionar Item"))
        queryset = model_class.objects.filter(workshop=self.workshop, is_active=True)

        context.update({"items": queryset, "budget": budget, "item_type": item_type, "modal_title": title})
        return context


class AddItemToBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, *args, **kwargs):
        budget = get_object_or_404(Budget, id=kwargs["budget_id"], workshop=self.workshop)

        item_filter = {f"{kwargs['item_type']}_id": kwargs["item_id"]}

        item, created = BudgetItem.objects.get_or_create(
            workshop=self.workshop,
            budget=budget,
            **item_filter,
            defaults={"quantity": 1},
        )

        if not created:
            item.quantity += 1
            item.save()

        success_url = f"{reverse('budget:budget_update', kwargs={'pk': budget.id})}?step={budget.current_step}"

        response = HttpResponse()
        response["HX-Redirect"] = success_url
        return response


class RemoveItemFromBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, *args, **kwargs):
        budget = get_object_or_404(Budget, id=kwargs["budget_id"], workshop=self.workshop)

        item_filter = {f"{kwargs['item_type']}_id": kwargs["item_id"]}

        item = get_object_or_404(BudgetItem, workshop=self.workshop, budget=budget, **item_filter)

        item.delete()

        success_url = f"{reverse('budget:budget_update', kwargs={'pk': budget.id})}?step={budget.current_step}"

        response = HttpResponse()
        response["HX-Redirect"] = success_url
        return response


class UpdateBudgetDiscountView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = get_object_or_404(Budget, pk=budget_id, workshop=self.workshop)
        try:
            val = request.POST.get("discount_value_0", "0").replace(",", ".")
            budget.discount_value = Decimal(val)
            budget.save()
        except (ValueError, TypeError):
            pass

        return HttpResponse(headers={"HX-Refresh": "true"})


class UpdateBudgetStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, status):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        status_map = {
            "cancel": BudgetStatus.CANCELLED,
            "approve": BudgetStatus.APPROVED,
            "reject": BudgetStatus.REJECTED,
        }

        if status in status_map:
            budget.status = status_map[status]
            budget.save()

        return JsonResponse({"success": True})


class UpdateSliderView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        slider_value = request.POST.get("slider")
        if slider_value is not None:
            budget.slider = int(slider_value)
            budget.save()
        return HttpResponse(status=204)


class SaveObservationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request):
        try:
            data = json.loads(request.body)
            observation = data.get("observation", "").strip()
            self.workshop.pdf_observation = observation
            self.workshop.save()
            return JsonResponse({"success": True})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"success": False}, status=400)


class BudgetItemUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def get(self, request, budget_id, item_id):
        item = get_object_or_404(BudgetItem, pk=item_id, budget_id=budget_id)
        form = BudgetItemEditForm(instance=item)
        return render(request, "budget/partials/modal_edit_item.html", {"form": form, "item": item, "budget_id": budget_id})

    def post(self, request, budget_id, item_id):
        item = get_object_or_404(BudgetItem, pk=item_id, budget_id=budget_id)
        form = BudgetItemEditForm(request.POST, instance=item)
        if form.is_valid():
            action = request.POST.get("action")
            item = form.save()

            if action == "update_master":
                self.update_master_record(item)

            context = {"item": item, "budget": item.budget, "is_full_render": False}
            if item.product:
                template = "budget/partials/item_product_row.html"
            elif item.service:
                template = "budget/partials/item_service_row.html"
            else:
                template = "budget/partials/item_kit_row.html"

            response = render(request, template, context)
            response["HX-Trigger"] = "update-summary"
            return response

        return render(request, "budget/partials/modal_edit_item.html", {"form": form, "item": item})

    def update_master_record(self, item):
        if item.product:
            product = item.product
            product.name = item.description
            product.cost_price = item.product_cost_price
            product.selling_price = item.product_selling_price
            product.save()
        elif item.service:
            service = item.service
            service.name = item.description
            service.suggested_cost = item.service_cost_price
            service.selling_price = item.service_selling_price
            service.duration = item.duration
            service.save()
        elif item.kit:
            kit = item.kit
            kit.name = item.description


class BudgetImageView(LoginRequiredMixin, View):
    def get(self, request, pk):
        from django.http import HttpResponse

        from apps.budget.models import BudgetImage

        image = get_object_or_404(BudgetImage, pk=pk)

        return HttpResponse(image.content, content_type=image.content_type)


class AddItemsBatchToBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, item_type):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        selected_ids = request.POST.getlist("selected_ids[]")
        if not selected_ids:
            return HttpResponse("Nenhum item selecionado", status=400)

        created_items = []
        for item_id in selected_ids:
            item_filter = {f"{item_type}_id": item_id}

            budget_item, created = BudgetItem.objects.get_or_create(workshop=self.workshop, budget=budget, **item_filter, defaults={"quantity": 1})

            created_items.append(budget_item.id)

        context = {
            "budget": budget,
            "item_type": item_type,
            "item_ids": created_items,
            "total_items": len(created_items),
            "current_index": 0,
        }

        return render(request, "budget/partials/modal_edit_queue.html", context)
