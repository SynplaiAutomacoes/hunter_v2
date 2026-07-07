from __future__ import annotations

import json
from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.forms import BaseInlineFormSet
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from apps.collaborators.forms import CollaboratorBenefitFormSet, WorkshopCollaboratorCreateForm, WorkshopCollaboratorModalForm, WorkshopCollaboratorUpdateForm
from apps.collaborators.models import CollaboratorBenefit, CollaboratorPayroll, WorkshopCollaborator, WorkshopMember
from apps.collaborators.services import calculate_transport_allowance_total, freeze_existing_pricing_history, get_reference_work_days, sync_collaborator_payroll, sync_current_month_salary_costs
from apps.core.presentation.navigation import COLLABORATOR_CREATE_FAVORITE_PAGE
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.utils import clean_id
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.mixin import WorkshopScopedMixin

AuthUser = get_user_model()
User = get_user_model()


COLLABORATOR_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(
        param_name="collaborator_type",
        lookup="collaborator_type",
        kind="choice",
        allowed_values=frozenset({"A", "P"}),
        normalizer=str.upper,
    ),
    QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),
    QueryParamFilter(param_name="system_access", lookup="system_access", kind="boolean"),
    QueryParamFilter(param_name="position", lookup="position", kind="icontains"),
)


# TODO: Validar melhor o fluxo de edição e criação com relação ao acesso ao sistema.
class WorkshopCollaboratorListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkshopCollaborator
    template_name = "collaborators/collaborator_list.html"
    context_object_name = "collaborators"

    htmx_template_name = "collaborators/partials/collaborator_table.html"

    def get_queryset(self):
        queryset = super().get_queryset().order_by("-criado_em")
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=COLLABORATOR_LIST_FILTERS,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label=WorkshopCollaborator.name.field.verbose_name, attr=WorkshopCollaborator.name.field.name),
            TableColumn(label=WorkshopCollaborator.cpf.field.verbose_name, attr=WorkshopCollaborator.cpf.field.name, format="cpf"),
            TableColumn(label=WorkshopCollaborator.position.field.verbose_name, attr=WorkshopCollaborator.position.field.name),
            TableColumn(label=WorkshopCollaborator.is_active.field.verbose_name, attr=WorkshopCollaborator.is_active.field.name),
            TableColumn(label=WorkshopCollaborator.system_access.field.verbose_name, attr=WorkshopCollaborator.system_access.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("collaborators:collaborator_update"),
        ]

        context["collaborator_type_choices"] = WorkshopCollaborator.collaborator_type.field.choices

        return context


class WorkshopCollaboratorCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorCreateForm
    template_name = "collaborators/collaborator_create.html"
    success_url = reverse_lazy("collaborators:collaborator_list")
    favorite_page_definition = COLLABORATOR_CREATE_FAVORITE_PAGE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.request.user.account
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_work_days"] = get_reference_work_days(collaborator=WorkshopCollaborator(workshop=self.workshop))
        context["current_transport_total"] = "R$ 0,00"
        return context

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.workshop = self.workshop

            if form.instance.salary is None:
                form.instance.salary = 0

            if form.cleaned_data.get("system_access"):
                username = form.cleaned_data["system_username"]
                password = form.cleaned_data["password1"]
                role = form.cleaned_data["role"]

                user = User(
                    username=username,
                    cpf=form.cleaned_data["cpf"],
                    email=form.cleaned_data.get("email") or "",
                    account=self.workshop.account,
                    is_active=form.cleaned_data.get("is_active", True),
                )
                parts = (form.cleaned_data.get("name") or "").split(" ", 1)
                user.first_name = parts[0] if parts else ""
                user.last_name = parts[1] if len(parts) > 1 else ""
                user.set_password(password)
                user.save()

                form.instance.user = user

                response = super().form_valid(form)

                WorkshopMember.objects.update_or_create(
                    user=user,
                    workshop=self.workshop,
                    defaults={
                        "role": role,
                        "is_active": self.object.is_active,
                    },
                )
            else:
                form.instance.user = None
                response = super().form_valid(form)

            sync_collaborator_payroll(collaborator=self.object)
            freeze_existing_pricing_history(workshop=self.workshop, cutoff=self.object.criado_em)
            sync_current_month_salary_costs(workshop=self.workshop)

        return response

    def form_invalid(self, form):
        cpf_errors = form.errors.get("cpf")
        if cpf_errors and any("Já existe um colaborador com este CPF." in error for error in cpf_errors):
            messages.error(self.request, "Já existe um colaborador com este CPF.")
        return super().form_invalid(form)


class WorkshopCollaboratorUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorUpdateForm
    template_name = "collaborators/collaborator_update.html"
    success_url = reverse_lazy("collaborators:collaborator_list")

    @staticmethod
    def _parse_selected_movement_ids(raw_values: list[str]) -> list[int]:
        movement_ids: list[int] = []
        for raw_value in raw_values:
            value = str(raw_value or "").strip()
            if value.isdigit():
                movement_ids.append(int(value))
        return movement_ids

    def _delete_selected_pending_movements(self, *, collaborator: WorkshopCollaborator) -> None:
        if collaborator.termination_date is None:
            return

        movement_ids = self._parse_selected_movement_ids(self.request.POST.getlist("delete_movement_ids"))
        if not movement_ids:
            return

        deleted_count, _ = FinancialMovement.objects.filter(
            workshop=self.workshop,
            collaborator=collaborator,
            is_paid=False,
            pk__in=movement_ids,
        ).delete()
        if deleted_count:
            messages.success(self.request, f"{deleted_count} lançamento(s) removido(s) com sucesso.")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.request.user.account
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        benefit_formset = kwargs.get("benefit_formset")
        if benefit_formset is None:
            benefit_formset = CollaboratorBenefitFormSet(instance=self.object, prefix="benefits")
        reference_date = self.request.GET.get("reference_date")
        history_month = str(self.request.GET.get("history_month") or "").strip()
        history_year = str(self.request.GET.get("history_year") or "").strip()
        history_status = str(self.request.GET.get("history_status") or "").strip()
        payroll_history = self.object.payrolls.select_related("financial_movement").prefetch_related("items").all()

        if history_month.isdigit():
            payroll_history = payroll_history.filter(reference_month=int(history_month))
        if history_year.isdigit():
            payroll_history = payroll_history.filter(reference_year=int(history_year))
        if history_status == "paid":
            payroll_history = payroll_history.filter(financial_movement__is_paid=True)
        elif history_status == "forecast":
            payroll_history = payroll_history.exclude(financial_movement__is_paid=True)

        month_choices = sorted({payroll.reference_month for payroll in self.object.payrolls.only("reference_month")}, reverse=True)
        year_choices = sorted({payroll.reference_year for payroll in self.object.payrolls.only("reference_year")}, reverse=True)
        pending_financial_movements = list(FinancialMovement.objects.filter(workshop=self.workshop, collaborator=self.object, is_paid=False).select_related("payment_method").order_by("due_date", "id"))
        context["benefit_formset"] = benefit_formset
        context["benefit_empty_form"] = benefit_formset.empty_form
        context["payroll_history"] = payroll_history[:24]
        context["current_work_days"] = get_reference_work_days(collaborator=self.object)
        context["current_transport_total"] = calculate_transport_allowance_total(collaborator=self.object)
        context["active_tab"] = self.request.POST.get("tab") or self.request.GET.get("tab") or "cadastro"
        context["reference_date"] = reference_date
        context["history_month_choices"] = month_choices
        context["history_year_choices"] = year_choices
        context["selected_history_month"] = history_month
        context["selected_history_year"] = history_year
        context["selected_history_status"] = history_status
        context["pending_financial_movements"] = pending_financial_movements
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        benefit_formset = CollaboratorBenefitFormSet(request.POST, instance=self.object, prefix="benefits")
        if form.is_valid() and benefit_formset.is_valid():
            return self.forms_valid(form, benefit_formset)
        return self.forms_invalid(form, benefit_formset)

    def forms_valid(self, form, benefit_formset: BaseInlineFormSet):
        with transaction.atomic():
            if form.instance.salary is None:
                form.instance.salary = 0

            response = super().form_valid(form)
            collaborator = self.object

            benefit_formset.instance = collaborator
            benefit_formset.save()

            if collaborator.system_access:
                role = form.cleaned_data["role"]

                if collaborator.user_id:
                    user = collaborator.user
                    user.username = form.cleaned_data["system_username"]
                    user.email = collaborator.email or user.email
                    user.is_active = collaborator.is_active
                    user.save(update_fields=["username", "email", "is_active"])
                else:
                    user = User(
                        username=form.cleaned_data["system_username"],
                        cpf=collaborator.cpf,
                        email=collaborator.email or "",
                        account=self.workshop.account,
                        is_active=collaborator.is_active,
                    )
                    parts = (collaborator.name or "").split(" ", 1)
                    user.first_name = parts[0] if parts else ""
                    user.last_name = parts[1] if len(parts) > 1 else ""
                    user.set_password(form.cleaned_data["password1"])
                    user.save()

                    collaborator.user = user
                    collaborator.save(update_fields=["user"])

                WorkshopMember.objects.update_or_create(
                    user=user,
                    workshop=self.workshop,
                    defaults={
                        "role": role,
                        "is_active": collaborator.is_active,
                    },
                )
            elif collaborator.user_id:
                WorkshopMember.objects.filter(user=collaborator.user, workshop=self.workshop).update(is_active=False)
                collaborator.user.is_active = False
                collaborator.user.save(update_fields=["is_active"])

            sync_collaborator_payroll(collaborator=collaborator)
            sync_current_month_salary_costs(workshop=self.workshop)
            self._delete_selected_pending_movements(collaborator=collaborator)
            return response

    def forms_invalid(self, form, benefit_formset: BaseInlineFormSet):
        return self.render_to_response(self.get_context_data(form=form, benefit_formset=benefit_formset))

    def form_valid(self, form):
        benefit_formset = CollaboratorBenefitFormSet(self.request.POST or None, instance=form.instance, prefix="benefits")
        return self.forms_valid(form, benefit_formset)


class WorkshopCollaboratorDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopCollaborator
    success_url = reverse_lazy("collaborators:collaborator_list")

    htmx_template_name = "collaborators/partials/collaborator_delete_modal.html"
    htmx_trigger = "collaborators-table-refresh"

    def _delete_collaborator_and_related(self, *, using: str):
        user_id = self.object.user_id
        workshop_id = self.object.workshop_id

        with transaction.atomic(using=using):
            if user_id:
                WorkshopMember.objects.using(using).filter(user_id=user_id, workshop_id=workshop_id).delete()
                AuthUser.objects.using(using).filter(pk=user_id).delete()

            self.object.delete(using=using)

    def form_valid(self, form):
        using = self.object._state.db
        self._delete_collaborator_and_related(using=using)

        if bool(getattr(self.request, "htmx", False)):
            response = HttpResponse()
            if self.htmx_trigger:
                response["HX-Trigger"] = self.htmx_trigger
            return response

        return HttpResponseRedirect(self.get_success_url())


class CollaboratorPayrollMarkPaidView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCollaborator
    workshop_permission_codename = "change_financialmovement"

    def post(self, request, pk, payroll_id):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=pk, workshop=self.workshop)
        payroll = get_object_or_404(CollaboratorPayroll.objects.select_related("financial_movement"), pk=payroll_id, collaborator=collaborator)

        if payroll.financial_movement is not None:
            payroll.financial_movement.is_paid = True
            payroll.financial_movement.save(update_fields=["is_paid"])
            sync_collaborator_payroll(collaborator=collaborator, reference_date=date(payroll.reference_year, payroll.reference_month, 1))

        query_params = self.request.POST.copy()
        query_params.pop("csrfmiddlewaretoken", None)
        redirect_url = reverse("collaborators:collaborator_update", kwargs={"pk": collaborator.pk})
        encoded = query_params.urlencode()
        if encoded:
            redirect_url = f"{redirect_url}?{encoded}"
        return HttpResponseRedirect(redirect_url)


@method_decorator(xframe_options_exempt, name="dispatch")
class CollaboratorPayrollReceiptView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCollaborator
    workshop_permission_codename = "view_financialmovement"

    def get(self, request, pk, payroll_id):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=pk, workshop=self.workshop)
        payroll = get_object_or_404(
            CollaboratorPayroll.objects.select_related("financial_movement", "collaborator", "workshop").prefetch_related("items"),
            pk=payroll_id,
            collaborator=collaborator,
        )
        return render(
            request,
            "collaborators/payroll_receipt.html",
            {
                "collaborator": collaborator,
                "payroll": payroll,
            },
        )


class CollaboratorBenefitDeleteView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCollaborator
    workshop_permission_codename = "change_workshopcollaborator"

    def post(self, request, pk, benefit_id):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=clean_id(pk), workshop=self.workshop)
        benefit = get_object_or_404(CollaboratorBenefit, pk=clean_id(benefit_id), collaborator=collaborator)
        benefit.delete()
        sync_collaborator_payroll(collaborator=collaborator)
        return HttpResponseRedirect(f"{reverse('collaborators:collaborator_update', kwargs={'pk': clean_id(collaborator.pk)})}?tab=cadastro")


class WorkshopCollaboratorModalCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorModalForm
    template_name = "collaborators/partials/collaborator_create_modal.html"

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.workshop = self.workshop

            if self.object.salary is None:
                self.object.salary = 0

            self.object.save()
            sync_collaborator_payroll(collaborator=self.object)
            freeze_existing_pricing_history(workshop=self.workshop, cutoff=self.object.criado_em)
            sync_current_month_salary_costs(workshop=self.workshop)

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"collaboratorSaved": {"id": str(self.object.pk), "name": self.object.name}})
        return response


class WorkshopCollaboratorModalUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorModalForm
    template_name = "collaborators/partials/collaborator_update_modal.html"

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)

            if self.object.salary is None:
                self.object.salary = 0

            self.object.save()
            sync_collaborator_payroll(collaborator=self.object)
            sync_current_month_salary_costs(workshop=self.workshop)

            if self.object.user_id:
                user = self.object.user
                if self.object.email and user.email != self.object.email:
                    user.email = self.object.email
                    user.save(update_fields=["email"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"collaboratorSaved": {"id": str(self.object.pk), "name": self.object.name}})
        return response
