import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView
from djmoney.money import Money
from apps.budget.forms import BudgetStep1Form, BudgetStep2Form, BudgetStep3Form, BudgetStep4Form, BudgetStep5Form, BudgetStep6Form
from apps.budget.approval import BudgetApprovalError, approve_budget_with_stock
from apps.budget.models import Budget, BudgetItem, BudgetStatus, SignatureStatus
from apps.budget.service import SuperSignError, send_budget_for_signature
from apps.core.forms import MultiStepFormMixin
from apps.core.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workorder.discount_sync import sync_budget_discount_to_workorder
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.util.workshops import get_active_workshop_or_404

from .shared import _get_budget_for_workshop, logger


def trigger_signature_send_if_needed(*, request, budget: Budget) -> tuple[str, str, str | None]:
    with transaction.atomic():
        locked_budget = Budget.objects.select_for_update().get(pk=budget.pk)

        if locked_budget.signature_request_status == SignatureStatus.SENT and locked_budget.signature_external_id:
            return "info", "Orçamento já enviado para assinatura do cliente.", reverse("budget:budget_list")

        if locked_budget.signature_request_status == SignatureStatus.SENDING:
            return "info", "O envio do orçamento ainda está em processamento.", None

        locked_budget.mark_signature_sending()

    try:
        result = send_budget_for_signature(budget=budget, request=request)
    except SuperSignError:
        budget.mark_signature_failed()
        logger.exception("Falha ao enviar orcamento para assinatura", extra={"budget_id": budget.pk})
        return "error", "Falha ao enviar orçamento para assinatura. Tente novamente em instantes.", None

    budget.mark_signature_sent(result.envelope_id, document_id=result.document_id)
    return "success", "Orçamento enviado para assinatura do cliente.", reverse("budget:budget_list")


BUDGET_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(
        param_name="client",
        lookup="customer__name",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="vehicle",
        lookup="vehicle__plate",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="collaborator",
        lookup="collaborator__name",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="status",
        lookup="status",
        kind="choice",
        allowed_values=frozenset(str(status_value) for status_value, _ in (Budget.status.field.choices or ())),
    ),
)


class BudgetListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Budget
    template_name = "budget/budget_list.html"
    context_object_name = "budget"
    htmx_template_name = "budget/partials/budget_table.html"

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("customer", "vehicle", "collaborator")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=BudgetItem.objects.select_related("product", "service", "kit")
                    .prefetch_related(
                        "kit_overrides",
                        "kit__kit_products__product",
                        "kit__kit_services__service",
                    )
                    .order_by("id"),
                )
            )
        )

        status_filter = str(self.request.GET.get("status") or "").strip()
        if not status_filter:
            queryset = queryset.exclude(status=BudgetStatus.CANCELLED)

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=BUDGET_LIST_FILTERS,
        )

        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(Budget.customer.field.verbose_name, attr=Budget.customer.field.name),
            TableColumn(Budget.vehicle.field.verbose_name, attr=Budget.vehicle.field.name),
            TableColumn(Budget.collaborator.field.verbose_name, attr="collaborator_name"),
            TableColumn(Budget.criado_em.field.verbose_name, attr=Budget.criado_em.field.name),
            TableColumn("Valor Total", attr="total_budget_value"),
            TableColumn(Budget.status.field.verbose_name, attr="budget_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("budget:budget_update"),
        ]
        context["status_choices"] = Budget.status.field.choices
        context["budget_events_enabled"] = getattr(settings, "BUDGET_EVENTS_ENABLED", False)
        context["budget_poll_interval_seconds"] = getattr(settings, "BUDGET_POLL_INTERVAL_SECONDS", 20)
        return context


class BudgetCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = Budget
    template_name = "budget/budget_form.html"

    steps_definition = [
        {"title": "Dados do Cliente", "form_class": BudgetStep1Form, "status": BudgetStatus.WAITING_CLIENT, "auto_apply": True},
        {"title": "Relato do Cliente", "form_class": BudgetStep2Form, "status": BudgetStatus.WAITING_DIAGNOSIS, "auto_apply": True},
        {"title": "Diagnóstico", "form_class": BudgetStep3Form, "status": BudgetStatus.WAITING_ITEMS, "auto_apply": True},
        {"title": "Peças e Serviços", "form_class": BudgetStep4Form, "status": BudgetStatus.WAITING_PRICING, "auto_apply": True},
        {"title": "Método de Precificação", "form_class": BudgetStep5Form, "status": BudgetStatus.WAITING_REVIEW, "auto_apply": True},
        {"title": "Revisão e Confirmação", "form_class": BudgetStep6Form, "auto_apply": False},
    ]

    def get(self, request, *args, **kwargs):
        today = timezone.now()
        if not WorkshopCost.objects.filter(workshop=self.workshop, month=today.month, year=today.year).exists():
            messages.warning(request, "Cadastre um custo mensal da oficina para este mês antes de prosseguir.")
            return redirect("budget:budget_list")

        requested_step = request.GET.get("step")
        budget_pk = request.GET.get("pk")
        if budget_pk and not requested_step:
            budget = self.get_object()
            if budget:
                target_url = f"{reverse('budget:budget_create')}?step={budget.current_step}&pk={budget.pk}"
                return redirect(target_url)

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

    def _render_htmx_step_response(self, *, step: int, push_url: str, triggers: dict | None = None):
        steps = self.get_steps_config()
        idx = max(0, min(step - 1, len(steps) - 1))
        form_class = steps[idx].get("form_class")
        if form_class is None:
            raise ValueError(f"Nenhum form configurado para etapa {step}.")

        form_kwargs = self.get_form_kwargs()
        form_kwargs["instance"] = self.object
        next_form = form_class(**form_kwargs)
        self._model_instance = self.object
        context = self.get_context_data(form=next_form, current_step=step)
        context["form"] = next_form

        response = self.render_to_response(context)
        response["HX-Push-Url"] = push_url
        if triggers:
            response["HX-Trigger"] = json.dumps(triggers)
        return response

    def _block_step5_advance_if_needed(self, current_step):
        if current_step != 5 or self._is_step5_calculation_done():
            return None

        warning_message = "Realize o cálculo da etapa 5 antes de avançar para a revisão."
        if self.kwargs.get("pk"):
            current_url = f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={current_step}"
        else:
            current_url = f"{reverse('budget:budget_create')}?step={current_step}&pk={self.object.pk}"

        if self.request.htmx:
            return self._render_htmx_step_response(step=current_step, push_url=current_url, triggers={"showToast": {"message": warning_message, "type": "warning"}})

        messages.warning(self.request, warning_message)
        return redirect(current_url)

    def _is_step5_calculation_done(self):
        if not self.object:
            return False
        return bool(self.object.step5_calculation_viewed or self.object.current_step > 5)

    def _sync_step5_calculation_viewed_from_post(self, current_step):
        if current_step != 5:
            return

        if self.object.current_step > 5 and not self.object.step5_calculation_viewed:
            self.object.step5_calculation_viewed = True
            self.object.save(update_fields=["step5_calculation_viewed"])
            return

        step5_calculated = self.request.POST.get("step5_calculated")
        if step5_calculated != "1" or self._is_step5_calculation_done():
            return

        self.object.step5_calculation_viewed = True
        self.object.save(update_fields=["step5_calculation_viewed"])

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user

        self.object = form.save()  # Salva o progresso atual

        # Aplicar status automático configurado para esta etapa (se houver)
        try:
            self.apply_step_status(budget=self.object, current_step=self.get_current_step(), actor=self.request.user)
        except Exception:
            logger.exception("Falha ao aplicar status automatico no create do budget", extra={"budget_id": self.object.pk})

        current_step = self.get_current_step()
        self._sync_step5_calculation_viewed_from_post(current_step)
        block_step5_response = self._block_step5_advance_if_needed(current_step)
        if block_step5_response:
            return block_step5_response

        if self.object.current_step < current_step + 1:
            self.object.current_step = current_step + 1
            self.object.save(update_fields=["current_step"])

        if current_step < len(self.steps_definition):
            next_step = current_step + 1
            success_url = f"{reverse('budget:budget_create')}?step={next_step}&pk={self.object.pk}"

            if self.request.htmx:
                return self._render_htmx_step_response(step=next_step, push_url=success_url)

            return redirect(success_url)

        toast_type, toast_message, redirect_url = ("success", "Orçamento finalizado. Envie para assinatura no modal de PDF.", reverse("budget:budget_list"))

        if self.request.htmx:
            response = HttpResponse(status=204)
            triggers = {"showToast": {"message": toast_message, "type": toast_type}}
            if redirect_url:
                triggers["redirectAfterToast"] = {"url": redirect_url, "delay": 1200}
            response["HX-Trigger"] = json.dumps(triggers)
            return response

        if toast_type == "success":
            messages.success(self.request, toast_message)
        elif toast_type == "error":
            messages.error(self.request, toast_message)
        else:
            messages.info(self.request, toast_message)

        if redirect_url:
            return redirect(redirect_url)

        return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={current_step}")


class BudgetUpdateView(BudgetCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        # Ensure workshop is available before budget_object access.
        # MultiStepFormMixin.budget_object calls self.get_object(), which needs self.workshop.
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect("budget:budget_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return Budget.objects.get(pk=pk, workshop=self.workshop)
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

        # Aplicar status automático configurado para esta etapa (se houver)
        try:
            self.apply_step_status(budget=self.object, current_step=self.get_current_step(), actor=self.request.user, isUpdate=True)
        except Exception:
            logger.exception("Falha ao aplicar status automatico no update do budget", extra={"budget_id": self.object.pk})

        current_step = self.get_current_step()
        self._sync_step5_calculation_viewed_from_post(current_step)
        block_step5_response = self._block_step5_advance_if_needed(current_step)
        if block_step5_response:
            return block_step5_response

        # Lógica de progressão de etapa (opcional em Update, mas útil se ele puder avançar)
        if self.object.current_step < current_step + 1:
            self.object.current_step = current_step + 1
            self.object.save(update_fields=["current_step"])

        if current_step < len(self.steps_definition):
            next_step = current_step + 1
            # Importante: Apontamos para budget_update para manter o contexto de edição
            success_url = f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={next_step}"

            if self.request.htmx:
                return self._render_htmx_step_response(step=next_step, push_url=success_url)

            return redirect(success_url)

        toast_type, toast_message, redirect_url = ("success", "Orçamento finalizado. Envie para assinatura no modal de PDF.", reverse("budget:budget_list"))

        if self.request.htmx:
            response = HttpResponse(status=204)
            triggers = {"showToast": {"message": toast_message, "type": toast_type}}
            if redirect_url:
                triggers["redirectAfterToast"] = {"url": redirect_url, "delay": 1200}
            response["HX-Trigger"] = json.dumps(triggers)
            return response

        if toast_type == "success":
            messages.success(self.request, toast_message)
        elif toast_type == "error":
            messages.error(self.request, toast_message)
        else:
            messages.info(self.request, toast_message)

        if redirect_url:
            return redirect(redirect_url)

        return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={current_step}")


class BudgetDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Budget
    success_url = reverse_lazy("budget:budget_list")

    htmx_template_name = "budget/partials/budget_delete_modal.html"
    htmx_trigger = "budget-table-refresh"


class UpdateBudgetDiscountView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        try:
            raw_discount_value = request.POST.get("discount_value_0", "0").replace(",", ".") or "0"
            raw_discount_percentage = request.POST.get("discount_percentage", "0").replace(",", ".") or "0"

            budget.discount_value = Money(Decimal(raw_discount_value), "BRL")
            budget.discount_percentage = Decimal(raw_discount_percentage)
            budget.save(update_fields=["discount_value", "discount_percentage"])
            sync_budget_discount_to_workorder(budget=budget)
        except (ValueError, TypeError, InvalidOperation):
            logger.warning(
                "Valor de desconto invalido recebido",
                extra={
                    "budget_id": budget_id,
                    "raw_discount": request.POST.get("discount_value_0"),
                    "raw_discount_percentage": request.POST.get("discount_percentage"),
                },
            )

        return HttpResponse(status=204)


class UpdateBudgetStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, status):
        budget = _get_budget_for_workshop(self.workshop, budget_id)

        # Mapa de status
        status_map = {
            "cancel": BudgetStatus.CANCELLED,
            "approve": BudgetStatus.APPROVED,
            "reject": BudgetStatus.REJECTED,
        }

        if status not in status_map:
            error_message = "Status invalido"
            messages.error(request, error_message)
            return JsonResponse({"success": False, "error": error_message}, status=400)

        # Validação de Aprovação
        if status == "approve":
            try:
                approve_budget_with_stock(budget=budget, user=request.user)
            except BudgetApprovalError as exc:
                error_message = str(exc)
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=400)
            except Exception:
                error_message = "Erro interno ao processar aprovação automática de estoque."
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=500)

        else:
            budget.status = status_map[status]
            budget.save()

        return JsonResponse({"success": True})


class SendBudgetSignatureView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        toast_type, toast_message, _ = trigger_signature_send_if_needed(request=request, budget=budget)
        status_code = 200 if toast_type in {"success", "info"} else 400
        return JsonResponse({"success": toast_type in {"success", "info"}, "type": toast_type, "message": toast_message}, status=status_code)


class UpdateSliderView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        slider_value = request.POST.get("slider")
        if slider_value is not None:
            budget.slider = int(slider_value)
            budget.save(update_fields=["slider"])

        html = f"""
                <span id="display-venda-pecas" hx-swap-oob="true" class="col-span-4 p-2 border-l border-base-300 whitespace-nowrap step5-accent-text" data-base-val="{budget.get_total_products_by_slider.amount}" data-cost-val="{budget.total_costs_products_value.amount}" data-frete-val="{budget.total_products_shipping.amount}">
                    {budget.get_total_products_by_slider}
                </span>
                <span id="display-venda-mo" hx-swap-oob="true" class="col-span-4 p-2 border-l border-base-300 step5-accent-text" data-base-val="{budget.get_total_labor_by_slider.amount}" data-cost-val="{budget.total_labor_cost_value.amount}">
                    {budget.get_total_labor_by_slider}
                </span>
                <span id="step5-subtotal-display" hx-swap-oob="true" data-base-total="{budget.total_base_value.amount}">
                    {budget.total_base_value}
                </span>
                <span id="step5-discount-display" hx-swap-oob="true">
                    {budget.resolved_discount_value}
                </span>
                <span id="valor-final-display" hx-swap-oob="true">
                    {budget.total_budget_value}
                </span>
                """
        return HttpResponse(html)


class MarkStep5CalculationViewedView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not budget.step5_calculation_viewed:
            budget.step5_calculation_viewed = True
            budget.save(update_fields=["step5_calculation_viewed"])
        return HttpResponse(status=204)


class SaveObservationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        try:
            budget = _get_budget_for_workshop(self.workshop, budget_id)
            data = json.loads(request.body)
            observation = data.get("observation", "").strip()
            budget.pdf_observation = observation
            budget.save(update_fields=["pdf_observation"])
            return JsonResponse({"success": True})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"success": False}, status=400)
