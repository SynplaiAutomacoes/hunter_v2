import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView
from apps.budget.forms import BudgetStep1Form, BudgetStep2Form, BudgetStep3Form, BudgetStep4Form, BudgetStep5Form, BudgetStep6Form
from apps.budget.models import Budget, BudgetStatus, SignatureStatus
from apps.budget.service import SuperSignError, send_budget_for_signature
from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.util.workshops import get_active_workshop_or_404

from .shared import _get_budget_for_workshop, logger
from ...stock.models import StockMovement


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
            TableColumn(Budget.status.field.verbose_name, attr="budget_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("budget:budget_update"),
        ]
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

        # Aplicar status automático configurado para esta etapa (se houver)
        try:
            self.apply_step_status(budget=self.object, current_step=self.get_current_step(), actor=self.request.user)
        except Exception:
            logger.exception("Falha ao aplicar status automatico no create do budget", extra={"budget_id": self.object.pk})

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

        toast_type, toast_message, redirect_url = self._trigger_signature_send_if_needed(self.object)

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

    def _trigger_signature_send_if_needed(self, budget: Budget) -> tuple[str, str, str | None]:
        with transaction.atomic():
            locked_budget = Budget.objects.select_for_update().get(pk=budget.pk)

            if locked_budget.signature_request_status == SignatureStatus.SENT and locked_budget.signature_external_id:
                return "info", "Orçamento já enviado para assinatura do cliente.", reverse("budget:budget_list")

            if locked_budget.signature_request_status == SignatureStatus.SENDING:
                return "info", "O envio do orçamento ainda está em processamento.", None

            locked_budget.mark_signature_sending()

        try:
            result = send_budget_for_signature(budget=budget, request=self.request)
        except SuperSignError:
            budget.mark_signature_failed()
            logger.exception("Falha ao enviar orcamento para assinatura", extra={"budget_id": budget.pk})
            return "error", "Falha ao enviar orçamento para assinatura. Tente novamente em instantes.", None

        budget.mark_signature_sent(result.envelope_id)
        return "success", "Orçamento enviado para assinatura do cliente.", reverse("budget:budget_list")


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

        toast_type, toast_message, redirect_url = self._trigger_signature_send_if_needed(self.object)

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
            val = request.POST.get("discount_value_0", "0").replace(",", ".") or "0"
            budget.discount_value = Decimal(val)
            budget.save()
        except (ValueError, TypeError):
            logger.warning("Valor de desconto invalido recebido", extra={"budget_id": budget_id, "raw_discount": request.POST.get("discount_value_0")})

        return HttpResponse(headers={"HX-Refresh": "true"})


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
            local_items = budget.items.filter(is_local=True)
            if local_items.exists():
                error_message = "Não é possível aprovar. Existem itens sem cadastro (locais)."
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=400)

            try:
                with transaction.atomic():
                    # Consumir produto do estoque
                    for item in budget.items.all():
                        stock_product = item.product.stock_products

                        if stock_product.current_quantity < item.quantity:
                            warn_message = f"Estoque insuficiente para {item.product.referencia}. Disponível: {stock_product.current_quantity}, Necessário: {item.quantity}"
                            messages.warning(request, warn_message)
                            raise ValueError(warn_message)

                        stock_product.current_quantity -= item.quantity
                        stock_product.save()

                        StockMovement.objects.create(workshop=self.workshop, stock_product=stock_product, type="SAIDA", quantity=item.quantity, status="APROVADO", transcation_by=request.user)

                    budget.status = status_map[status]
                    budget.save()
            except Exception:
                error_message = "Erro interno ao processar estoque."
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=500)

        else:
            budget.status = status_map[status]
            budget.save()

        return JsonResponse({"success": True})


class UpdateSliderView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        slider_value = request.POST.get("slider")
        if slider_value is not None:
            budget.slider = int(slider_value)
            budget.save()
        return HttpResponse(status=204)


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

    def post(self, request):
        try:
            data = json.loads(request.body)
            observation = data.get("observation", "").strip()
            self.workshop.pdf_observation = observation
            self.workshop.save()
            return JsonResponse({"success": True})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"success": False}, status=400)
