import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, DeleteView

from apps.budget.forms import BudgetStep1Form, BudgetStep2Form, BudgetStep3Form, BudgetStep4Form, BudgetStep5Form, BudgetStep6Form
from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin, HtmxDeleteResponseMixin
from apps.customer.models import Customer, Vehicle
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


class BudgetListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Budget
    template_name = "budget/budget_list.html"
    context_object_name = "budget"
    htmx_template_name = "budget/partials/budget_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(Budget.customer.field.verbose_name, attr=Budget.customer.field.name),
            TableColumn(Budget.vehicle.field.verbose_name, attr=Budget.vehicle.field.name),
            TableColumn(Budget.collaborator.field.verbose_name, attr="collaborator_name"),
            TableColumn(Budget.criado_em.field.verbose_name, attr=Budget.criado_em.field.name),
            TableColumn(Budget.expiration_date.field.verbose_name, attr="expiration_date_display"),
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
            self.object.save(update_fields=['current_step'])

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
        customer_id = request.GET.get('customer')
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

        data = [
            {"id": v.id, "label": str(v)}
            for v in vehicles
        ]

        return JsonResponse(data, safe=False)


class VehicleDetailView(View):
    def get(self, request, *args, **kwargs):
        vehicle_id = request.GET.get('vehicle')
        vehicle = None
        if vehicle_id:
            vehicle = get_object_or_404(Vehicle, id=vehicle_id)
        return render(request, 'budget/partials/vehicle_resume.html', {'vehicle': vehicle})


def item_selection_modal(request, budget_id, item_type):
    budget = get_object_or_404(Budget, id=budget_id)
    workshop = get_active_workshop_or_404(request=request)

    if item_type == "product":
        queryset = Product.objects.filter(workshop=workshop, is_active=True)
        title = "Selecionar Produto"
    elif item_type == "service":
        queryset = Service.objects.filter(workshop=workshop, is_active=True)
        title = "Selecionar Serviço"
    else:
        queryset = Kit.objects.filter(workshop=workshop, is_active=True)
        title = "Selecionar Kit"

    return render(request, "budget/partials/modal_item_list.html", {"items": queryset, "budget": budget, "item_type": item_type, "modal_title": title})


def add_item_to_budget(request, budget_id, item_id, item_type):
    budget = get_object_or_404(Budget, id=budget_id)
    workshop = get_active_workshop_or_404(request=request)

    item, created = BudgetItem.objects.get_or_create(workshop=workshop, budget=budget, **{f"{item_type}_id": item_id}, defaults={"quantity": 1})

    if not created:
        item.quantity += 1
        item.save()

    response = HttpResponse()
    response["HX-Refresh"] = "true"
    return response


def remove_item_from_budget(request, budget_id, item_id, item_type):
    budget = get_object_or_404(Budget, id=budget_id)
    workshop = get_active_workshop_or_404(request=request)

    item = get_object_or_404(BudgetItem, workshop=workshop, budget=budget, **{f"{item_type}_id": item_id})
    item.delete()

    response = HttpResponse()
    response["HX-Refresh"] = "true"
    return response


def update_budget_discount(request, budget_id):
    workshop = get_active_workshop_or_404(request=request)
    budget = get_object_or_404(Budget, pk=budget_id, workshop=workshop)

    try:
        budget.discount_value = Decimal(request.POST.get("discount_value_0", "0").replace(",", "."))
        budget.save()
    except (ValueError, TypeError):
        pass

    response = HttpResponse()
    response["HX-Refresh"] = "true"
    return response

def save_observation(request):
    workshop = get_active_workshop_or_404(request=request)

    try:
        data = json.loads(request.body)
        observation = data.get("observation", "").strip()
    except json.JSONDecodeError:
        pass

    workshop.pdf_observation = observation
    workshop.save()

    return JsonResponse({"success": True})

def update_budget_status(request, budget_id, status):
    workshop = get_active_workshop_or_404(request=request)
    budget = get_object_or_404(Budget, id=budget_id, workshop=workshop)

    if status == "cancel":
        budget.status = BudgetStatus.CANCELLED
    elif status == "approve":
        budget.status = BudgetStatus.APPROVED
    elif status == "reject":
        budget.status = BudgetStatus.REJECTED

    budget.save()

    return JsonResponse({"success": True})


def update_slider(request, budget_id):
    workshop = get_active_workshop_or_404(request=request)
    budget = get_object_or_404(Budget, id=budget_id, workshop=workshop)
    slider_value = request.POST.get("slider")
    if slider_value is not None:
        budget.slider = int(slider_value)
        budget.save()

    return HttpResponse(status=204)
