from __future__ import annotations

import json
import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.forms import BaseInlineFormSet
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from apps.collaborators.forms import CollaboratorBenefitFormSet, CollaboratorCommissionScopeForm, WorkshopCollaboratorCreateForm, WorkshopCollaboratorModalForm, WorkshopCollaboratorUpdateForm
from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionRule, CollaboratorPayroll, WorkshopCollaborator, WorkshopMember
from apps.collaborators.services import (
    apply_collaborator_work_days_for_reference,
    calculate_transport_allowance_total,
    delete_collaborator_benefit_and_sync_payrolls,
    delete_selected_pending_collaborator_movements,
    freeze_existing_pricing_history,
    get_reference_work_days,
    get_workshop_work_days,
    mark_payroll_as_paid,
    refresh_unpaid_payroll_commissions_for_references,
    sync_collaborator_payroll_range,
    sync_current_month_salary_costs,
)
from apps.core.presentation.navigation import COLLABORATOR_CREATE_FAVORITE_PAGE
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.utils import clean_id
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import can_view_payroll_details, has_workshop_perm

AuthUser = get_user_model()
User = get_user_model()
logger = logging.getLogger(__name__)


def _should_sync_monthly_costs(request) -> bool:
    return bool(request.POST.get("sync_monthly_costs") == "1")


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
            if form.instance.transport_allowance_daily is None:
                form.instance.transport_allowance_daily = 0

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

            freeze_existing_pricing_history(workshop=self.workshop, cutoff=self.object.criado_em)
            if _should_sync_monthly_costs(self.request):
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

    def _get_selected_movement_ids(self) -> list[int]:
        movement_ids = self._parse_selected_movement_ids(self.request.POST.getlist("delete_movement_ids"))
        if movement_ids:
            return movement_ids

        payload = str(self.request.POST.get("delete_movement_ids_payload") or "").strip()
        if not payload:
            return []

        return self._parse_selected_movement_ids(payload.split(","))

    def _delete_selected_pending_movements(self, *, collaborator: WorkshopCollaborator) -> None:
        if collaborator.termination_date is None:
            return

        movement_ids = self._get_selected_movement_ids()
        if not movement_ids:
            return

        deleted_count = delete_selected_pending_collaborator_movements(
            collaborator=collaborator,
            workshop=self.workshop,
            movement_ids=movement_ids,
        )
        if deleted_count:
            messages.success(self.request, f"{deleted_count} lançamento(s) removido(s) com sucesso.")

    def get_success_url(self):
        params = ["tab=cadastro"]
        request = getattr(self, "request", None)
        open_from_query = bool(request is not None and request.GET.get("open_pending_delete") == "1")
        if open_from_query or getattr(self, "_open_pending_delete", False):
            params.append("open_pending_delete=1")
        return f"{reverse('collaborators:collaborator_update', kwargs={'pk': clean_id(self.object.pk)})}?{'&'.join(params)}"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.request.user.account
        kwargs["workshop"] = self.workshop
        return kwargs

    def _get_commission_scope_forms(self, data=None):
        forms: dict[str, CollaboratorCommissionScopeForm] = {}
        for scope in (CollaboratorCommissionRule.Scope.SERVICE, CollaboratorCommissionRule.Scope.PRODUCT):
            prefix = f"commission_{scope}"
            instance = None
            if getattr(self, "object", None) and getattr(self.object, "pk", None):
                instance = CollaboratorCommissionRule.objects.filter(collaborator=self.object, scope=scope).first()
            # For display, if no instance, create an empty one with is_active False to render form correctly
            # but don't persist yet; ModelForm with None instance will work.
            forms[scope] = CollaboratorCommissionScopeForm(
                data=data,
                instance=instance,
                workshop=self.workshop,
                scope=scope,
                prefix=prefix,
            )
        return forms

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        benefit_formset = kwargs.get("benefit_formset")
        if benefit_formset is None:
            benefit_formset = CollaboratorBenefitFormSet(instance=self.object, prefix="benefits", form_kwargs={"workshop": self.workshop})
        # Commission scope forms (v3)
        commission_service_form = kwargs.get("commission_service_form")
        commission_product_form = kwargs.get("commission_product_form")
        if commission_service_form is None or commission_product_form is None:
            commission_forms = self._get_commission_scope_forms()
            commission_service_form = commission_service_form or commission_forms[CollaboratorCommissionRule.Scope.SERVICE]
            commission_product_form = commission_product_form or commission_forms[CollaboratorCommissionRule.Scope.PRODUCT]
        context["commission_service_form"] = commission_service_form
        context["commission_product_form"] = commission_product_form
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
        context["workshop_default_work_days"] = get_workshop_work_days(workshop=self.workshop)
        context["current_transport_total"] = calculate_transport_allowance_total(collaborator=self.object)
        context["active_tab"] = self.request.POST.get("tab") or self.request.GET.get("tab") or "cadastro"
        context["reference_date"] = reference_date
        context["history_month_choices"] = month_choices
        context["history_year_choices"] = year_choices
        context["selected_history_month"] = history_month
        context["selected_history_year"] = history_year
        context["selected_history_status"] = history_status
        context["pending_financial_movements"] = pending_financial_movements
        context["open_pending_delete"] = str(self.request.GET.get("open_pending_delete") or "").strip() == "1"
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        benefit_formset = CollaboratorBenefitFormSet(request.POST, instance=self.object, prefix="benefits", form_kwargs={"workshop": self.workshop})
        commission_forms = self._get_commission_scope_forms(data=request.POST)
        service_form = commission_forms[CollaboratorCommissionRule.Scope.SERVICE]
        product_form = commission_forms[CollaboratorCommissionRule.Scope.PRODUCT]
        # Se não recebe comissão, forçar inativo (mesmo que formulário venha com is_active)
        receives_commission = form.data.get("receives_commission") is not None if form.is_bound else bool(getattr(self.object, "receives_commission", False))
        # Validar todos os formulários (scope forms só validam se receives_commission ativo; caso contrário, considerar válidos)
        forms_valid = form.is_valid() and benefit_formset.is_valid()
        scope_forms_valid = True
        if receives_commission or form.cleaned_data.get("receives_commission"):
            # Validar regras apenas se recebe comissão
            scope_forms_valid = service_form.is_valid() and product_form.is_valid()
        else:
            # Limpar erros de scope quando não recebe comissão
            scope_forms_valid = True
        if forms_valid and scope_forms_valid:
            return self.forms_valid(form, benefit_formset, service_form, product_form)
        return self.forms_invalid(form, benefit_formset, service_form, product_form)

    def _save_commission_scope_forms(self, collaborator: WorkshopCollaborator, service_form, product_form) -> bool:
        global_rule_changed = False
        # Se não recebe comissão, desativar todas as regras existentes
        receives = bool(collaborator.receives_commission)
        if not receives:
            global_rule_changed = CollaboratorCommissionRule.objects.filter(
                collaborator=collaborator,
                is_active=True,
                apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
            ).exists()
            CollaboratorCommissionRule.objects.filter(collaborator=collaborator, is_active=True).update(is_active=False)
            return global_rule_changed
        for scope, scope_form in (
            (CollaboratorCommissionRule.Scope.SERVICE, service_form),
            (CollaboratorCommissionRule.Scope.PRODUCT, product_form),
        ):
            if scope_form is None:
                continue
            # scope_form já foi validado; mas pode ser inativo
            cleaned = getattr(scope_form, "cleaned_data", {}) or {}
            is_active = bool(cleaned.get("is_active"))
            instance = scope_form.instance
            persisted_instance = (
                CollaboratorCommissionRule.objects.filter(pk=instance.pk)
                .only("is_active", "apply_scope")
                .first()
                if instance and instance.pk
                else None
            )
            was_global = bool(
                persisted_instance
                and persisted_instance.is_active
                and persisted_instance.apply_scope == CollaboratorCommissionRule.ApplyScope.GLOBAL
            )
            # Caso inativo e sem registro prévio, não criar
            if not is_active and (instance is None or instance.pk is None):
                continue
            if not is_active and instance and instance.pk:
                global_rule_changed = global_rule_changed or was_global
                instance.is_active = False
                instance.save(update_fields=["is_active"])
                continue
            if is_active:
                rule = scope_form.save(commit=False)
                rule.collaborator = collaborator
                rule.scope = scope
                # modality já definido no clean via cleaned["modality"] mas save pode não setar; garantir
                if "modality" in cleaned:
                    rule.modality = cleaned["modality"]
                rule.is_active = True
                rule.save()
                is_global = rule.apply_scope == CollaboratorCommissionRule.ApplyScope.GLOBAL
                if (was_global or is_global) and scope_form.has_changed():
                    global_rule_changed = True
                # Se havia regra antiga do mesmo escopo inativa, garantir única ativa (constraint)
                # Desativar outras do mesmo escopo (caso tenha duplicata histórica)
                CollaboratorCommissionRule.objects.filter(collaborator=collaborator, scope=scope).exclude(pk=rule.pk).update(is_active=False)
        return global_rule_changed

    def forms_valid(self, form, benefit_formset: BaseInlineFormSet, service_form=None, product_form=None):
        previous_termination_date = WorkshopCollaborator.objects.filter(pk=self.object.pk).values_list("termination_date", flat=True).first()
        with transaction.atomic():
            if form.instance.salary is None:
                form.instance.salary = 0
            if form.instance.transport_allowance_daily is None:
                form.instance.transport_allowance_daily = 0

            response = super().form_valid(form)
            collaborator = self.object
            should_sync_monthly_costs = _should_sync_monthly_costs(self.request)

            benefit_formset.instance = collaborator
            benefit_formset.save()
            # Salvar regras de comissão v3
            if service_form is not None or product_form is not None:
                # Caso não tenha passado forms (compatibilidade com form_valid simples), tentar construir
                if service_form is None or product_form is None:
                    commission_forms = self._get_commission_scope_forms(data=self.request.POST)
                    service_form = service_form or commission_forms.get(CollaboratorCommissionRule.Scope.SERVICE)
                    product_form = product_form or commission_forms.get(CollaboratorCommissionRule.Scope.PRODUCT)
                    # Re-validar se necessário (quando chamado via form_valid simples sem passar commission forms)
                    if service_form and not service_form.is_valid():
                        # Se não recebe comissão, ignorar
                        if not collaborator.receives_commission:
                            service_form = None
                    if product_form and not product_form.is_valid():
                        if not collaborator.receives_commission:
                            product_form = None
                global_rule_changed = self._save_commission_scope_forms(collaborator, service_form, product_form)
                if global_rule_changed:
                    from apps.collaborators.commission.orchestrator import WorkOrderCommissionOrchestrator

                    affected_references = WorkOrderCommissionOrchestrator().sync_global_commissions_after_rule_change(collaborator)
                    refresh_unpaid_payroll_commissions_for_references(
                        collaborator=collaborator,
                        references=affected_references,
                    )

            raw_work_days = str(self.request.POST.get("work_days") or "").strip()
            if raw_work_days == "":
                apply_collaborator_work_days_for_reference(
                    collaborator=collaborator,
                    work_days=None,
                    sync_salary_costs=should_sync_monthly_costs,
                )
            elif raw_work_days.isdigit():
                apply_collaborator_work_days_for_reference(
                    collaborator=collaborator,
                    work_days=int(raw_work_days),
                    sync_salary_costs=should_sync_monthly_costs,
                )

            if collaborator.system_access:
                role = form.cleaned_data["role"]

                if collaborator.user_id:
                    user = collaborator.user
                    user.username = form.cleaned_data["system_username"]
                    user.email = collaborator.email or user.email
                    user.is_active = collaborator.is_active
                    update_fields = ["username", "email", "is_active"]
                    new_password = form.cleaned_data.get("password1")
                    if new_password:
                        user.set_password(new_password)
                        update_fields.append("password")
                    user.save(update_fields=update_fields)
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

            if should_sync_monthly_costs:
                sync_current_month_salary_costs(workshop=self.workshop)

            termination_newly_set = previous_termination_date is None and collaborator.termination_date is not None
            has_pending = FinancialMovement.objects.filter(workshop=self.workshop, collaborator=collaborator, is_paid=False).exists()
            self._open_pending_delete = bool(termination_newly_set and has_pending)
            if self._open_pending_delete:
                return HttpResponseRedirect(self.get_success_url())
            return response

    def forms_invalid(self, form, benefit_formset: BaseInlineFormSet, service_form=None, product_form=None):
        return self.render_to_response(
            self.get_context_data(
                form=form,
                benefit_formset=benefit_formset,
                commission_service_form=service_form,
                commission_product_form=product_form,
            )
        )

    def form_valid(self, form):
        # Compatibilidade: quando chamado via UpdateView genérico, construir scope forms e delegar
        benefit_formset = CollaboratorBenefitFormSet(self.request.POST or None, instance=form.instance, prefix="benefits", form_kwargs={"workshop": self.workshop})
        commission_forms = self._get_commission_scope_forms(data=self.request.POST)
        service_form = commission_forms[CollaboratorCommissionRule.Scope.SERVICE]
        product_form = commission_forms[CollaboratorCommissionRule.Scope.PRODUCT]
        if not benefit_formset.is_valid():
            return self.forms_invalid(form, benefit_formset, service_form, product_form)
        # form já está validado ao entrar em form_valid, mas precisamos checar receives para decidir validar scopes
        receives = bool(form.cleaned_data.get("receives_commission")) if hasattr(form, "cleaned_data") else bool(getattr(form.instance, "receives_commission", False))
        if receives and (not service_form.is_valid() or not product_form.is_valid()):
            return self.forms_invalid(form, benefit_formset, service_form, product_form)
        return self.forms_valid(form, benefit_formset, service_form, product_form)


class WorkshopCollaboratorGenerateMovementsView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCollaborator
    workshop_permission_codename = "change_workshopcollaborator"

    def post(self, request, *args, **kwargs):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=kwargs["pk"], workshop=self.workshop)
        logger.warning(
            "Collaborator generate movements request received",
            extra={
                "collaborator_id": collaborator.pk,
                "workshop_id": self.workshop.pk,
                "starting_month": request.POST.get("starting_month"),
                "starting_year": request.POST.get("starting_year"),
                "repeat_count": request.POST.get("repeat_count"),
                "salary_repeat_count": request.POST.get("salary_repeat_count"),
                "payment_day_type": collaborator.payment_day_type,
                "payment_day_of_month": collaborator.payment_day_of_month,
                "is_active": collaborator.is_active,
                "salary_amount": str(collaborator.salary.amount if collaborator.salary is not None else "0"),
            },
        )
        if not collaborator.is_active:
            logger.warning(
                "Collaborator generate movements skipped because collaborator is inactive",
                extra={"collaborator_id": collaborator.pk, "workshop_id": self.workshop.pk},
            )
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Colaborador inativo. Ative-o para gerar movimentações.", "type": "warning"}})
            return response

        try:
            starting_month = int(str(request.POST.get("starting_month") or ""))
            starting_year = int(str(request.POST.get("starting_year") or ""))
            repeat_count = int(str(request.POST.get("repeat_count") or request.POST.get("salary_repeat_count") or "0"))
        except (TypeError, ValueError):
            logger.warning(
                "Collaborator generate movements received invalid parameters",
                extra={
                    "collaborator_id": collaborator.pk,
                    "workshop_id": self.workshop.pk,
                    "starting_month": request.POST.get("starting_month"),
                    "starting_year": request.POST.get("starting_year"),
                    "repeat_count": request.POST.get("repeat_count"),
                    "salary_repeat_count": request.POST.get("salary_repeat_count"),
                },
            )
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Parâmetros inválidos.", "type": "error"}})
            return response

        if repeat_count <= 0:
            logger.warning(
                "Collaborator generate movements skipped because repeat count is not positive",
                extra={"collaborator_id": collaborator.pk, "workshop_id": self.workshop.pk, "repeat_count": repeat_count},
            )
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "A quantidade de meses deve ser maior que zero.", "type": "warning"}})
            return response

        if collaborator.salary is None or collaborator.salary.amount is None or float(str(collaborator.salary.amount or 0)) <= 0:
            logger.warning(
                "Collaborator generate movements skipped because salary is zero",
                extra={"collaborator_id": collaborator.pk, "workshop_id": self.workshop.pk, "salary_amount": str(collaborator.salary.amount if collaborator.salary is not None else "0")},
            )
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "O salário do colaborador está zerado. Nenhuma movimentação foi gerada.", "type": "warning"}})
            return response

        reference_date = date(starting_year, starting_month, 1)
        with transaction.atomic():
            generated_payrolls = sync_collaborator_payroll_range(
                collaborator=collaborator,
                start_reference_date=reference_date,
                months_count=repeat_count,
            )
            sync_current_month_salary_costs(workshop=self.workshop)
        logger.warning(
            "Collaborator generate movements completed",
            extra={
                "collaborator_id": collaborator.pk,
                "workshop_id": self.workshop.pk,
                "requested_repeat_count": repeat_count,
                "generated_payroll_count": len(generated_payrolls),
                "generated_payrolls": [
                    {
                        "payroll_id": payroll.pk,
                        "reference_year": payroll.reference_year,
                        "reference_month": payroll.reference_month,
                        "due_date": payroll.due_date.isoformat(),
                        "financial_movement_id": payroll.financial_movement_id,
                        "financial_movements_count": payroll.financial_movements.count(),
                        "salary_amount": str(payroll.salary_amount.amount),
                        "transport_amount": str(payroll.transport_allowance_amount.amount),
                        "benefits_amount": str(payroll.benefits_amount.amount),
                        "commission_amount": str(payroll.commission_amount.amount),
                        "total_amount": str(payroll.total_amount.amount),
                    }
                    for payroll in generated_payrolls
                ],
            },
        )

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"showToast": {"message": f"{repeat_count} folhas de pagamento geradas com sucesso.", "type": "success"}, "collaboratorMovementsGenerated": {}})
        return response


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


class WorkshopCollaboratorPendingMovementDeleteView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCollaborator
    workshop_permission_codename = "change_workshopcollaborator"

    @staticmethod
    def _parse_selected_movement_ids(raw_values: list[str]) -> list[int]:
        movement_ids: list[int] = []
        for raw_value in raw_values:
            value = str(raw_value or "").strip()
            if value.isdigit():
                movement_ids.append(int(value))
        return movement_ids

    def _get_selected_movement_ids(self, request) -> list[int]:
        movement_ids = self._parse_selected_movement_ids(request.POST.getlist("delete_movement_ids"))
        if movement_ids:
            return movement_ids

        payload = str(request.POST.get("delete_movement_ids_payload") or "").strip()
        if not payload:
            return []

        return self._parse_selected_movement_ids(payload.split(","))

    def post(self, request, pk):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=clean_id(pk), workshop=self.workshop)
        movement_ids = self._get_selected_movement_ids(request)

        logger.warning(
            "Collaborator pending delete payload received",
            extra={
                "collaborator_id": collaborator.pk,
                "workshop_id": self.workshop.pk,
                "delete_movement_ids": request.POST.getlist("delete_movement_ids"),
                "delete_movement_ids_payload": request.POST.get("delete_movement_ids_payload", ""),
                "parsed_movement_ids": movement_ids,
            },
        )

        if not movement_ids:
            messages.warning(request, "Selecione ao menos um lançamento para apagar.")
            return HttpResponseRedirect(f"{reverse('collaborators:collaborator_update', kwargs={'pk': clean_id(collaborator.pk)})}?tab=cadastro")

        deleted_count = delete_selected_pending_collaborator_movements(
            collaborator=collaborator,
            workshop=self.workshop,
            movement_ids=movement_ids,
        )

        logger.warning(
            "Collaborator pending delete result",
            extra={
                "collaborator_id": collaborator.pk,
                "workshop_id": self.workshop.pk,
                "parsed_movement_ids": movement_ids,
                "deleted_count": deleted_count,
            },
        )

        if deleted_count:
            messages.success(request, f"{deleted_count} lançamento(s) removido(s) com sucesso.")
        else:
            messages.warning(request, "Nenhum lançamento pendente selecionado foi removido.")

        return HttpResponseRedirect(f"{reverse('collaborators:collaborator_update', kwargs={'pk': clean_id(collaborator.pk)})}?tab=cadastro")


class CollaboratorPayrollMarkPaidView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCollaborator
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "change_financialmovement"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.workshop = self._resolve_workshop(request, kwargs)
        can_mark = (
            can_view_payroll_details(user=request.user, workshop=self.workshop, request=request)
            or has_workshop_perm(
                user=request.user,
                workshop=self.workshop,
                app_label="finance",
                model="financialmovement",
                codename="change_financialmovement",
                request=request,
            )
        )
        if not can_mark:
            raise PermissionDenied
        return View.dispatch(self, request, *args, **kwargs)

    def post(self, request, pk, payroll_id):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=pk, workshop=self.workshop)
        payroll: CollaboratorPayroll = get_object_or_404(CollaboratorPayroll.objects.select_related("financial_movement"), pk=payroll_id, collaborator=collaborator)

        if payroll.financial_movement is not None:
            mark_payroll_as_paid(payroll=payroll)

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
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "view_financialmovement"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.workshop = self._resolve_workshop(request, kwargs)
        can_view = (
            can_view_payroll_details(user=request.user, workshop=self.workshop, request=request)
            or has_workshop_perm(
                user=request.user,
                workshop=self.workshop,
                app_label="finance",
                model="financialmovement",
                codename="view_financialmovement",
                request=request,
            )
            or has_workshop_perm(
                user=request.user,
                workshop=self.workshop,
                app_label="collaborators",
                model="workshopcollaborator",
                codename="view_workshopcollaborator",
                request=request,
            )
        )
        if not can_view:
            raise PermissionDenied
        return View.dispatch(self, request, *args, **kwargs)

    def get(self, request, pk, payroll_id):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=pk, workshop=self.workshop)
        payroll: CollaboratorPayroll = get_object_or_404(
            CollaboratorPayroll.objects.select_related("financial_movement", "collaborator", "workshop").prefetch_related("items"),
            pk=payroll_id,
            collaborator=collaborator,
        )
        movements = payroll.get_financial_movements()
        movements_by_component: dict[str, FinancialMovement] = {}
        benefit_global_obs = ""
        for m in movements:
            comp = str(m.payroll_component or "")
            if comp and comp not in movements_by_component:
                movements_by_component[comp] = m
            if comp == "BENEFIT" and m.financial_observation and not benefit_global_obs:
                benefit_global_obs = m.financial_observation.strip()

        for item in payroll.items.all():
            comp_key = str(item.item_type)
            if comp_key == "BENEFIT":
                item.movement_observation = benefit_global_obs or (item.description or "")
            elif comp_key in movements_by_component:
                mov_obs = str(movements_by_component[comp_key].financial_observation or "").strip()
                item.movement_observation = mov_obs or (item.description or "")
            else:
                item.movement_observation = item.description or ""

        commission_mov = movements_by_component.get("COMMISSION")
        commission_obs = (str(commission_mov.financial_observation or "").strip() if commission_mov else "") or "Valor consolidado das comissões da competência."

        response = render(
            request,
            "collaborators/payroll_receipt.html",
            {
                "collaborator": collaborator,
                "payroll": payroll,
                "commission_details": commission_obs,
            },
        )
        response["Cache-Control"] = "no-store"
        return response


class CollaboratorBenefitDeleteView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCollaborator
    workshop_permission_codename = "change_workshopcollaborator"

    def post(self, request, pk, benefit_id):
        collaborator = get_object_or_404(WorkshopCollaborator, pk=clean_id(pk), workshop=self.workshop)
        benefit = get_object_or_404(CollaboratorBenefit, pk=clean_id(benefit_id), collaborator=collaborator)
        with transaction.atomic():
            delete_collaborator_benefit_and_sync_payrolls(benefit=benefit)
            sync_current_month_salary_costs(workshop=self.workshop)
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
            if self.object.transport_allowance_daily is None:
                self.object.transport_allowance_daily = 0

            self.object.save()
            freeze_existing_pricing_history(workshop=self.workshop, cutoff=self.object.criado_em)
            if _should_sync_monthly_costs(self.request):
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
            if self.object.transport_allowance_daily is None:
                self.object.transport_allowance_daily = 0

            self.object.save()
            if _should_sync_monthly_costs(self.request):
                sync_current_month_salary_costs(workshop=self.workshop)

            if self.object.user_id:
                user = self.object.user
                if self.object.email and user.email != self.object.email:
                    user.email = self.object.email
                    user.save(update_fields=["email"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"collaboratorSaved": {"id": str(self.object.pk), "name": self.object.name}})
        return response
