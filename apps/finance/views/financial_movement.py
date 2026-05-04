from __future__ import annotations

from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView

from apps.core.forms import MultiStepFormMixin
from apps.core.navigation import FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.finance.forms.financial_movement import MovementStep1Form, MovementStep2Form, MovementStep3Form, MovementStep4Form
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.navigation import append_query_params
from apps.collaborators.models import WorkshopCollaborator
from apps.sources.models import Source
from apps.suppliers.models import Supplier
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


class FinancialMovementListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = FinancialMovement
    template_name = "finance/financial_movement/financial_movement_list.html"
    context_object_name = "financial_movement"
    htmx_template_name = "finance/partials/financial_movement/financial_movement_table.html"
    workshop_permission_codename = "view_financialmovement"

    def _parse_date_param(self, raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_selected_source_id(self) -> int | None:
        raw_value = str(self.request.GET.get("source") or "").strip()
        if not raw_value:
            return None

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def get_queryset(self):
        queryset = super().get_queryset().select_related("source")

        start_date = self._parse_date_param(self.request.GET.get("data_inicial"))
        end_date = self._parse_date_param(self.request.GET.get("data_final"))
        source_id = self._get_selected_source_id()

        if start_date is not None:
            queryset = queryset.filter(due_date__gte=start_date)
        if end_date is not None:
            queryset = queryset.filter(due_date__lte=end_date)
        if source_id is not None:
            queryset = queryset.filter(source_id=source_id)

        return queryset.order_by("-criado_em")

    def get_context_data(self, **kw):
        context = super().get_context_data(**kw)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(FinancialMovement.source.field.verbose_name, attr="source", search_by="source__name"),
            TableColumn("Tipo", attr="get_direction_display", search_by="direction"),
            TableColumn(FinancialMovement.amount.field.verbose_name, attr=FinancialMovement.amount.field.name),
            TableColumn(FinancialMovement.due_date.field.verbose_name, attr=FinancialMovement.due_date.field.name),
        ]
        context["actions"] = [
            TableActionDefaults.edit("finance:financial_movement_update", preserve_current_url_as_next=True),
            TableActionDefaults.delete("finance:financial_movement_delete"),
        ]
        context["source_filters"] = Source.objects.filter(workshop=self.workshop).order_by("name", "id")
        context["selected_source_id"] = self._get_selected_source_id()
        return context


class FinancialMovementCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = FinancialMovement
    template_name = "finance/financial_movement/financial_movement_form.html"
    workshop_permission_codename = "add_financialmovement"
    favorite_page_definition = FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE

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

    def _get_next_url(self) -> str:
        next_url = str(self.request.GET.get("next") or self.request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()):
            return next_url
        return ""

    def _build_step_url(self, *, step: int, obj: FinancialMovement | None = None) -> str:
        params: dict[str, int | str] = {"step": step}
        if obj is not None and getattr(obj, "pk", None) and not self.kwargs.get("pk"):
            params["pk"] = obj.pk

        next_url = self._get_next_url()
        if next_url:
            params["next"] = next_url

        return append_query_params(url=self.request.path, params=params)

    def get_steps_definition(self):
        return [
            {"title": "Origem", "form_class": MovementStep1Form},
            {"title": "Descrição", "form_class": MovementStep2Form},
            {"title": "Pagamento", "form_class": MovementStep3Form},
            {"title": "Revisão", "form_class": MovementStep4Form},
        ]

    def get_success_url(self):
        return self._get_next_url() or reverse("finance:reports_home")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back_url"] = self.get_success_url()
        context["next_url"] = self._get_next_url()
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
            success_url = self._build_step_url(step=next_step, obj=self.object)
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            from django.http import HttpResponse

            response = HttpResponse(status=204)
            response["HX-Redirect"] = success_url
            return response

        return redirect(success_url)


class FinancialMovementUpdateView(FinancialMovementCreateView):
    favorite_page_definition = None

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(self._build_step_url(step=target_step, obj=self.object))

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
            success_url = self._build_step_url(step=next_step, obj=self.object)
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class FinancialMovementDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = FinancialMovement
    success_url = reverse_lazy("finance:financial_movement_list")
    workshop_permission_codename = "delete_financialmovement"

    htmx_template_name = "finance/partials/financial_movement/financial_movement_delete_modal.html"
    htmx_trigger = "financial_movement-table-refresh"


class EntityListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = FinancialMovement
    workshop_permission_codename = "view_financialmovement"

    def get(self, request, *args, **kwargs):
        entity_type = request.GET.get("type")
        workshop = self.workshop

        data = []
        if entity_type == "supplier":
            entities = Supplier.objects.filter(workshop=workshop)
            data = [{"id": e.id, "name": e.name} for e in entities]
        elif entity_type == "collaborator":
            entities = WorkshopCollaborator.objects.filter(workshop=workshop)
            data = [{"id": e.id, "name": str(e)} for e in entities]

        return JsonResponse(data, safe=False)


class EntityDetailView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = FinancialMovement
    workshop_permission_codename = "view_financialmovement"

    def get(self, request, *args, **kwargs):
        entity_type = request.GET.get("type")
        entity_id = request.GET.get("id")
        workshop = self.workshop

        context = {"type": entity_type}

        if entity_type == "supplier":
            context["entity"] = Supplier.objects.filter(id=entity_id, workshop=workshop).first()
            template = "finance/partials/supplier_resume.html"
        else:
            context["entity"] = WorkshopCollaborator.objects.filter(id=entity_id, workshop=workshop).first()
            template = "finance/partials/collaborator_resume.html"

        return render(request, template, context)
