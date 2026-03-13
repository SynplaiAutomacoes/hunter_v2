from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, ListView

from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms.financial_movement import MovementStep1Form, MovementStep2Form, MovementStep3Form, \
    MovementStep4Form
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


class FinancialMovementListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = FinancialMovement
    template_name = "finance/financial_movement/financial_movement_list.html"
    context_object_name = "financial_movement"
    htmx_template_name = "finance/partials/financial_movement/financial_movement_table.html"
    workshop_permission_codename = "view_financialmovement"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kw):
        context = super().get_context_data(**kw)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(FinancialMovement.source.field.verbose_name, attr="source__name"),
            TableColumn("Tipo", attr="get_direction_display"),
            TableColumn(FinancialMovement.amount.field.verbose_name, attr=FinancialMovement.amount.field.name),
            TableColumn(FinancialMovement.due_date.field.verbose_name, attr=FinancialMovement.due_date.field.name),
        ]
        context["actions"] = [
            TableActionDefaults.edit("finance:financial_movement_update"),
        ]
        return context


class FinancialMovementCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = FinancialMovement
    template_name = "finance/movement_form.html"
    workshop_permission_codename = "add_financialmovement"

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.htmx:
            return ["finance/partials/financial_movement/import_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.request.GET.get("pk") or self.kwargs.get("pk")
        if pk:
            return get_object_or_404(FinancialMovement, id=pk, workshop=self.workshop)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        obj = self.get_object()
        kwargs.update({"request": self.request, "workshop": self.workshop, "instance": obj})
        return kwargs

    def get_steps_definition(self):
        return [
            {"title": "Origem", "form_class": MovementStep1Form},
            {"title": "Descrição", "form_class": MovementStep2Form},
            {"title": "Pagamento", "form_class": MovementStep3Form},
            {"title": "Revisão", "form_class": MovementStep4Form},
        ]

    def get_success_url(self):
        return reverse("finance:financial_movement_list")

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        self.object = form.save()

        current_step = self.get_current_step()
        steps_config = self.get_steps_config()
        total_steps = len(steps_config)

        if hasattr(self.object, "current_step"):
            next_step_value = current_step + 1
            if self.object.current_step < next_step_value:
                self.object.current_step = next_step_value
                self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            next_step = current_step + 1
            success_url = f"{self.request.path}?step={next_step}&pk={self.object.pk}"
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class FinancialMovementUpdateView(FinancialMovementCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('finance:financial_movement_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect("finance:financial_movement_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return FinancialMovement.objects.get(pk=pk, workshop=self.workshop)
        return super().get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        self.object = form.save()

        current_step = self.get_current_step()
        steps_config = self.get_steps_config()
        total_steps = len(steps_config)

        if hasattr(self.object, "current_step"):
            next_step_value = current_step + 1
            if self.object.current_step < next_step_value:
                self.object.current_step = next_step_value
                self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            next_step = current_step + 1
            success_url = f"{reverse('finance:financial_movement_update', kwargs={'pk': self.object.pk})}?step={next_step}"
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)
