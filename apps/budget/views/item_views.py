import json
import re
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape
from django.views import View
from django.views.generic import TemplateView
from djmoney.money import Money

from apps.budget.forms import BudgetItemEditForm, BudgetStep3Form
from apps.budget.models import Budget, BudgetItem
from apps.catalog.kit_applications import build_vehicle_context_label, evaluate_kit_vehicle_compatibility, vehicle_has_complete_application_context
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.price_tracking import build_product_price_warning
from apps.catalog.product_issues import annotate_product_issues
from apps.core.widgets import NumberInput
from apps.workshops.mixin import WorkshopScopedMixin

from .shared import (
    LOCKED_BUDGET_EDIT_MESSAGE,
    _build_locked_budget_response,
    _calculate_service_prices,
    _get_budget_for_workshop,
    _get_budget_item_for_workshop,
    _get_budget_workshop_cost,
    _get_current_step_from_referer,
    _is_budget_edit_locked,
    _parse_duration_from_string,
    _step_redirect_response,
    logger,
    reset_steps_after_step_4,
)


THOUSAND_SEPARATED_INT_PATTERN = re.compile(r"^\d{1,3}(?:[\s.,]\d{3})+$")


def _normalize_selected_item_ids(raw_ids: list[str]) -> tuple[list[int], list[str]]:
    normalized_ids: list[int] = []
    invalid_ids: list[str] = []

    for raw_id in raw_ids:
        value = str(raw_id).strip()
        if not value:
            invalid_ids.append(value)
            continue

        if value.isdigit():
            normalized_ids.append(int(value))
            continue

        if THOUSAND_SEPARATED_INT_PATTERN.fullmatch(value):
            normalized_ids.append(int(re.sub(r"[\s.,]", "", value)))
            continue

        invalid_ids.append(value)

    # Evita processamento repetido para IDs duplicados
    deduplicated_ids = list(dict.fromkeys(normalized_ids))
    return deduplicated_ids, invalid_ids


def _is_local_product_item(item: BudgetItem) -> bool:
    has_product_cost = bool(item.product_cost_price and item.product_cost_price.amount > 0)
    has_product_sale = bool(item.product_selling_price and item.product_selling_price.amount > 0)
    has_shipping = bool(item.shipping and item.shipping.amount > 0)
    return bool(item.is_local and (has_product_cost or has_product_sale or has_shipping))


def _is_product_budget_item(item: BudgetItem) -> bool:
    return bool(item.product is not None) or _is_local_product_item(item)


def _is_local_service_item(item: BudgetItem) -> bool:
    has_service_cost = bool(item.service_cost_price and item.service_cost_price.amount > 0)
    has_service_sale = bool(item.service_selling_price and item.service_selling_price.amount > 0)
    has_duration = bool(item.duration)
    return bool(item.is_local and (has_service_cost or has_service_sale or has_duration))


def _is_service_budget_item(item: BudgetItem) -> bool:
    return bool(item.service is not None) or _is_local_service_item(item)


def _is_kit_budget_item(item: BudgetItem) -> bool:
    return bool(item.kit is not None)


KIT_COMPATIBILITY_BADGE_CLASSES = {
    "compatible": "badge-success",
    "partially_compatible": "badge-accent",
    "no_applications": "badge-warning",
    "missing_vehicle_data": "badge-warning",
    "incompatible": "badge-error",
}
KIT_COMPATIBILITY_SORT_ORDER = {
    "compatible": 0,
    "partially_compatible": 1,
    "missing_vehicle_data": 2,
    "no_applications": 3,
    "incompatible": 4,
}


def _render_modal_error(*, title: str, message: str, icon: str = "warning") -> HttpResponse:
    icon_class = "text-warning" if icon == "warning" else "text-error"
    button_label = "Entendi" if icon == "warning" else "Fechar"
    safe_title = escape(title)
    safe_message = escape(message)
    html = f"""
    <div class="modal-box w-11/12 max-w-md bg-base-100">
        <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2" onclick="form_modal.close()">✕</button>
        <div class="flex flex-col items-center justify-center py-8 text-center">
            <span class="material-icons {icon_class} text-6xl mb-4">{icon}</span>
            <h3 class="font-bold text-xl mb-2">{safe_title}</h3>
            <p class="text-base-content/70 mb-6">{safe_message}</p>
            <button class="btn btn-primary" onclick="form_modal.close()">{button_label}</button>
        </div>
    </div>
    """
    return HttpResponse(html)


def _prepare_kit_selection_items(*, kits: list[Kit], budget: Budget, existing_items: set[int]) -> tuple[list[Kit], dict[str, object]]:
    vehicle = budget.vehicle
    filter_active = vehicle_has_complete_application_context(vehicle)

    hidden_count = 0
    compatible_count = 0
    incompatible_count = 0
    no_application_count = 0

    for kit in kits:
        compatibility = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)
        kit.compatibility_status = compatibility.status
        kit.compatibility_label = compatibility.label
        kit.compatibility_description = compatibility.description
        kit.compatibility_badge_class = KIT_COMPATIBILITY_BADGE_CLASSES.get(compatibility.status, "badge-ghost")
        kit.application_lines = kit.application_preview_lines(limit=3)

        hidden_by_default = compatibility.status in {"incompatible", "no_applications"} and kit.pk not in existing_items
        kit.hidden_by_compatibility_filter = hidden_by_default
        kit.selection_disabled = not compatibility.selectable and kit.pk not in existing_items

        if hidden_by_default:
            hidden_count += 1

        if compatibility.status == "compatible":
            compatible_count += 1
        elif compatibility.status == "incompatible":
            incompatible_count += 1
        elif compatibility.status == "no_applications":
            no_application_count += 1

    ordered_kits = sorted(
        kits,
        key=lambda kit: (
            kit.pk not in existing_items,
            KIT_COMPATIBILITY_SORT_ORDER.get(getattr(kit, "compatibility_status", ""), len(KIT_COMPATIBILITY_SORT_ORDER)),
            kit.name.lower(),
        ),
    )

    return ordered_kits, {
        "kit_vehicle_filter_active": filter_active,
        "kit_vehicle_filter_context": build_vehicle_context_label(vehicle),
        "kit_hidden_count": hidden_count,
        "kit_compatible_count": compatible_count,
        "kit_incompatible_count": incompatible_count,
        "kit_no_application_count": no_application_count,
    }


def _get_incompatible_budget_kits(*, workshop, budget: Budget, selected_ids: list[int]) -> list[Kit]:
    kits = list(Kit.objects.filter(workshop=workshop, id__in=selected_ids).prefetch_related("applications"))
    incompatible_kits = [kit for kit in kits if evaluate_kit_vehicle_compatibility(kit=kit, vehicle=budget.vehicle).status == "incompatible"]
    return incompatible_kits


class ItemSelectionModalView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = Budget
    template_name = "budget/partials/modals/modal_item_list.html"
    workshop_permission_codename = "add_budget"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        budget_id = self.kwargs.get("budget_id")
        item_type = self.kwargs.get("item_type")

        budget = _get_budget_for_workshop(self.workshop, budget_id)

        map_config = {
            "product": (Product, "Selecionar Produto"),
            "service": (Service, "Selecionar Serviço"),
            "kit": (Kit, "Selecionar Kit"),
        }

        model_class, title = map_config.get(item_type, (Product, "Selecionar Item"))
        queryset = model_class.objects.filter(workshop=self.workshop, is_active=True)
        if item_type == "product":
            queryset = queryset.select_related("stock_products")
        elif item_type == "kit":
            queryset = queryset.prefetch_related("applications")

        # Get already added items to mark them as selected
        existing_items = set()
        if item_type == "product":
            existing_items = set(budget.items.filter(product__isnull=False).values_list("product_id", flat=True))
        elif item_type == "service":
            existing_items = set(budget.items.filter(service__isnull=False).values_list("service_id", flat=True))
        elif item_type == "kit":
            existing_items = set(budget.items.filter(kit__isnull=False).values_list("kit_id", flat=True))

        ordered_items = list(queryset)
        kit_context: dict[str, object] = {}
        if item_type == "kit":
            ordered_items, kit_context = _prepare_kit_selection_items(kits=ordered_items, budget=budget, existing_items=existing_items)
        elif existing_items:
            ordered_items.sort(key=lambda item: item.pk not in existing_items)

        raw_selected_ids = self.request.GET.getlist("selected_ids")
        selected_ids: set[int] = set()
        for raw_id in raw_selected_ids:
            value = str(raw_id).strip()
            if value.isdigit():
                selected_ids.add(int(value))

        raw_newly_created_id = str(self.request.GET.get("newly_created_id", "")).strip()
        newly_created_id = int(raw_newly_created_id) if raw_newly_created_id.isdigit() else None

        if newly_created_id is not None:
            selected_ids.add(newly_created_id)

        context.update(
            {
                "items": ordered_items,
                "budget": budget,
                "item_type": item_type,
                "modal_title": title,
                "existing_items": existing_items,
                "selected_ids": selected_ids,
                "newly_created_id": newly_created_id,
            }
        )
        context.update(kit_context)
        return context


class AddItemToBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, *args, **kwargs):
        budget = _get_budget_for_workshop(self.workshop, kwargs["budget_id"])
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        if kwargs["item_type"] == "kit":
            incompatible_kits = _get_incompatible_budget_kits(workshop=self.workshop, budget=budget, selected_ids=[kwargs["item_id"]])
            if incompatible_kits:
                return HttpResponse("Kit incompatível com o veículo selecionado.", status=400)

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

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        return _step_redirect_response(request, budget, fallback_step=4)


class RemoveItemFromBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, *args, **kwargs):
        budget = _get_budget_for_workshop(self.workshop, kwargs["budget_id"])
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        item_filter = {f"{kwargs['item_type']}_id": kwargs["item_id"]}

        item = get_object_or_404(BudgetItem, workshop=self.workshop, budget=budget, **item_filter)

        item.delete()

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        return _step_redirect_response(request, budget, fallback_step=4)


class RemoveBudgetItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Remove item do orçamento pelo item_id (funciona para itens locais e normais)"""

    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, item_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id)

        item.delete()

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        return _step_redirect_response(request, budget, fallback_step=4)


class RemoveProductItemsBatchFromBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        raw_selected_ids = request.POST.getlist("selected_product_items")
        selected_ids, invalid_ids = _normalize_selected_item_ids(raw_selected_ids)

        if invalid_ids:
            logger.warning(
                "IDs invalidos enviados para remocao em lote de pecas",
                extra={
                    "budget_id": budget_id,
                    "invalid_count": len(invalid_ids),
                    "invalid_ids": invalid_ids[:10],
                },
            )

        if not selected_ids:
            logger.warning(
                "Tentativa de remocao em lote de pecas sem selecao",
                extra={"budget_id": budget_id},
            )
            return _step_redirect_response(request, budget, fallback_step=4)

        budget_items = list(BudgetItem.objects.filter(workshop=self.workshop, budget=budget, id__in=selected_ids))
        deletable_ids = [item.pk for item in budget_items if _is_product_budget_item(item)]

        if not deletable_ids:
            logger.warning(
                "Tentativa de remocao em lote de pecas sem itens elegiveis",
                extra={"budget_id": budget_id, "selected_count": len(selected_ids)},
            )
            return _step_redirect_response(request, budget, fallback_step=4)

        BudgetItem.objects.filter(workshop=self.workshop, budget=budget, id__in=deletable_ids).delete()

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        return _step_redirect_response(request, budget, fallback_step=4)


class RemoveServiceItemsBatchFromBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        raw_selected_ids = request.POST.getlist("selected_service_items")
        selected_ids, invalid_ids = _normalize_selected_item_ids(raw_selected_ids)

        if invalid_ids:
            logger.warning(
                "IDs invalidos enviados para remocao em lote de servicos",
                extra={
                    "budget_id": budget_id,
                    "invalid_count": len(invalid_ids),
                    "invalid_ids": invalid_ids[:10],
                },
            )

        if not selected_ids:
            logger.warning(
                "Tentativa de remocao em lote de servicos sem selecao",
                extra={"budget_id": budget_id},
            )
            return _step_redirect_response(request, budget, fallback_step=4)

        budget_items = list(BudgetItem.objects.filter(workshop=self.workshop, budget=budget, id__in=selected_ids))
        deletable_ids = [item.pk for item in budget_items if _is_service_budget_item(item)]

        if not deletable_ids:
            logger.warning(
                "Tentativa de remocao em lote de servicos sem itens elegiveis",
                extra={"budget_id": budget_id, "selected_count": len(selected_ids)},
            )
            return _step_redirect_response(request, budget, fallback_step=4)

        BudgetItem.objects.filter(workshop=self.workshop, budget=budget, id__in=deletable_ids).delete()

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        return _step_redirect_response(request, budget, fallback_step=4)


class RemoveKitItemsBatchFromBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        raw_selected_ids = request.POST.getlist("selected_kit_items")
        selected_ids, invalid_ids = _normalize_selected_item_ids(raw_selected_ids)

        if invalid_ids:
            logger.warning(
                "IDs invalidos enviados para remocao em lote de kits",
                extra={
                    "budget_id": budget_id,
                    "invalid_count": len(invalid_ids),
                    "invalid_ids": invalid_ids[:10],
                },
            )

        if not selected_ids:
            logger.warning(
                "Tentativa de remocao em lote de kits sem selecao",
                extra={"budget_id": budget_id},
            )
            return _step_redirect_response(request, budget, fallback_step=4)

        budget_items = list(BudgetItem.objects.filter(workshop=self.workshop, budget=budget, id__in=selected_ids))
        deletable_ids = [item.pk for item in budget_items if _is_kit_budget_item(item)]

        if not deletable_ids:
            logger.warning(
                "Tentativa de remocao em lote de kits sem itens elegiveis",
                extra={"budget_id": budget_id, "selected_count": len(selected_ids)},
            )
            return _step_redirect_response(request, budget, fallback_step=4)

        BudgetItem.objects.filter(workshop=self.workshop, budget=budget, id__in=deletable_ids).delete()

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        return _step_redirect_response(request, budget, fallback_step=4)


class BudgetItemUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    @staticmethod
    def _is_queue_request(request) -> bool:
        raw_in_queue = request.POST.get("in_queue") or request.GET.get("in_queue") or "false"
        return str(raw_in_queue).lower() == "true"

    def _render_edit_modal(self, request, *, form: BudgetItemEditForm, item: BudgetItem, budget_id: int, in_queue: bool) -> HttpResponse:
        return render(
            request,
            "budget/partials/modals/modal_edit_item.html",
            {
                "form": form,
                "item": item,
                "budget_id": budget_id,
                "in_queue": in_queue,
                "stock_quantity_html": self._build_stock_quantity_html(item=item),
            },
        )

    @staticmethod
    def _build_stock_quantity_html(*, item: BudgetItem) -> str:
        return NumberInput(attrs={"readonly": "readonly", "disabled": "disabled", "id": "stock-quantity-reference"}).render(
            name="stock_quantity_reference",
            value=item.stock_quantity or 0,
        )

    def get(self, request, budget_id, item_id):
        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id)
        annotate_product_issues(workshop=self.workshop, items=[item])
        form = BudgetItemEditForm(instance=item, budget_id=budget_id)
        in_queue = self._is_queue_request(request)
        return self._render_edit_modal(request, form=form, item=item, budget_id=budget_id, in_queue=in_queue)

    def post(self, request, budget_id, item_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id)
        form = BudgetItemEditForm(request.POST, instance=item, budget_id=budget_id)
        in_queue = self._is_queue_request(request)
        if form.is_valid():
            action = request.POST.get("action")
            if action in {"save_only", "update_master"} and item.product:
                price_warning = build_product_price_warning(product=item.product, attempted_price=form.cleaned_data.get("product_selling_price"))
                if price_warning and request.POST.get("confirm_lower_price") != "1":
                    form.add_error("product_selling_price", price_warning.message)
                    annotate_product_issues(workshop=self.workshop, items=[item])
                    return self._render_edit_modal(request, form=form, item=item, budget_id=budget_id, in_queue=in_queue)
            try:
                item = form.save()
                self._sync_product_ncm(item=item, form=form)
            except Exception:
                logger.exception(
                    "Falha ao salvar item do orcamento",
                    extra={
                        "budget_id": budget_id,
                        "item_id": item_id,
                        "item_type": "service" if item.service_id else "product" if item.product_id else "kit" if item.kit_id else "unknown",
                        "action": action,
                    },
                )
                raise

            # Reset etapas 5 e 6 após modificar a etapa 4
            reset_steps_after_step_4(budget)

            if action == "update_master":
                self.update_master_record(item=item, form=form)

            # Mantém o mesmo comportamento de create/delete: recarrega etapa atual
            # para refletir imediatamente o reset das etapas 5 e 6.
            return _step_redirect_response(request, budget, fallback_step=4)

        logger.warning(
            "Formulario invalido ao salvar item do orcamento",
            extra={
                "budget_id": budget_id,
                "item_id": item_id,
                "item_type": "service" if item.service_id else "product" if item.product_id else "kit" if item.kit_id else "unknown",
                "errors": form.errors.get_json_data(),
            },
        )

        annotate_product_issues(workshop=self.workshop, items=[item])
        return self._render_edit_modal(request, form=form, item=item, budget_id=budget_id, in_queue=in_queue)

    @staticmethod
    def _sync_product_ncm(*, item: BudgetItem, form: BudgetItemEditForm) -> None:
        if not item.product or "ncm" not in form.cleaned_data:
            return

        product = item.product
        new_ncm = str(form.cleaned_data.get("ncm") or "").strip()
        if str(product.ncm or "") == new_ncm:
            return

        product.ncm = new_ncm
        product.save(update_fields=["ncm"])

    def update_master_record(self, *, item: BudgetItem, form: BudgetItemEditForm):
        if item.product:
            product = item.product
            product.name = item.description
            product.cost_price = item.product_cost_price
            product.selling_price = item.product_selling_price
            if "ncm" in form.cleaned_data:
                product.ncm = str(form.cleaned_data.get("ncm") or "").strip()
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


class BudgetItemCalculateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def post(self, request, budget_id, item_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id)

        # Usamos o form para processar o valor da duração vindo do POST
        form = BudgetItemEditForm(request.POST, instance=item, budget_id=budget_id)

        # Chamamos full_clean() para popular cleaned_data
        try:
            form.full_clean()
        except Exception:
            logger.exception("Falha ao executar full_clean no calculo de item", extra={"budget_id": budget_id, "item_id": item_id})

        cleaned_data = getattr(form, "cleaned_data", {})

        # Tentamos obter a duração, mesmo que o form tenha outros erros
        duration = cleaned_data.get("duration")

        # Se não estiver no cleaned_data (erro de validação), tentamos pegar o valor bruto
        if duration is None:
            raw_duration = request.POST.get("duration")
            duration = _parse_duration_from_string(raw_duration)

        # Lógica de busca do WorkshopCost (similar ao calculate_pricing_methods do modelo)
        workshop_cost, workshop_cost_missing = _get_budget_workshop_cost(budget, self.workshop)
        service_cost_price, service_selling_price = _calculate_service_prices(duration, workshop_cost)

        # Arredondamento
        service_cost_price_amount = service_cost_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
        service_selling_price_amount = service_selling_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP)

        # Atualiza a instância com os novos valores calculados
        item.service_cost_price = Money(service_cost_price_amount, "BRL")
        item.service_selling_price = Money(service_selling_price_amount, "BRL")
        if duration:
            item.duration = duration

        # Atualiza os dados do POST para refletir os novos preços no formulário bound
        data = request.POST.copy()

        # No Django, campos MoneyField costumam usar o sufixo _0 para o valor numérico no POST
        data["service_cost_price_0"] = str(service_cost_price_amount)
        data["service_cost_price_1"] = "BRL"
        if not budget.is_warranty_budget:
            data["service_selling_price_0"] = str(service_selling_price_amount)
            data["service_selling_price_1"] = "BRL"

        # Garante que o valor da duração formatado também vá para o POST do novo form
        if duration:
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            data["duration"] = f"{hours:02d}:{minutes:02d}"

        # Re-inicializa o formulário com os dados atualizados e a instância
        form = BudgetItemEditForm(data, instance=item, budget_id=budget_id)

        # Apenas o campo de venda vai por OOB, o de custo é o target principal
        oob_fields = [] if budget.is_warranty_budget else ["service_selling_price"]

        # Se houver erros no form (especialmente na duração), incluímos nos campos OOB
        # para que as mensagens de erro sejam exibidas no modal.
        if form.errors:
            for field_with_error in form.errors:
                if field_with_error not in oob_fields:
                    oob_fields.append(field_with_error)

        context = {
            "form": form,
            "item": item,
            "budget_id": budget_id,
            "oob_fields": oob_fields,
        }

        response = render(request, "budget/partials/modals/modal_edit_item_fields.html", context)

        # Add toast error if WorkshopCost is missing
        if workshop_cost_missing:
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Custo da oficina não cadastrado para o mês atual. Os valores não puderam ser calculados automaticamente.", "type": "error"}})

        return response


class BudgetImageView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "view_budget"

    def get(self, request, pk):
        from apps.budget.models import BudgetImage

        image = get_object_or_404(BudgetImage, pk=pk, workshop=self.workshop)

        return HttpResponse(image.content, content_type=image.content_type)


class AddItemsBatchToBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, item_type):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        modal_context = request.POST.get("modal_context", "")

        if item_type not in {"product", "service", "kit"}:
            logger.warning(
                "Tentativa de adicionar itens em lote com tipo invalido",
                extra={"budget_id": budget_id, "item_type": item_type},
            )
            return HttpResponse("Tipo de item inválido.", status=400)

        # Recebe IDs dos checkboxes marcados
        raw_selected_ids = request.POST.getlist("selected_items")
        selected_ids, invalid_ids = _normalize_selected_item_ids(raw_selected_ids)

        if invalid_ids:
            logger.warning(
                "IDs invalidos enviados para adicao em lote",
                extra={
                    "budget_id": budget_id,
                    "item_type": item_type,
                    "invalid_count": len(invalid_ids),
                    "invalid_ids": invalid_ids[:10],
                },
            )

        if not selected_ids:
            logger.warning(
                "Tentativa de adicionar itens em lote sem selecao",
                extra={"budget_id": budget_id, "item_type": item_type},
            )
            # Return error message in the modal container
            error_html = """
            <div class="modal-box w-11/12 max-w-md bg-base-100">
                <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2" onclick="form_modal.close()">✕</button>
                <div class="flex flex-col items-center justify-center py-8">
                    <span class="material-icons text-warning text-6xl mb-4">warning</span>
                    <h3 class="font-bold text-xl mb-2">Nenhum item selecionado</h3>
                    <p class="text-base-content/70 mb-6">Por favor, selecione pelo menos um item para adicionar ao orçamento.</p>
                    <button class="btn btn-primary" onclick="form_modal.close()">Entendi</button>
                </div>
            </div>
            """
            return HttpResponse(error_html)

        try:
            if item_type == "kit":
                incompatible_kits = _get_incompatible_budget_kits(workshop=self.workshop, budget=budget, selected_ids=selected_ids)
                if incompatible_kits:
                    incompatible_names = ", ".join(kit.name for kit in incompatible_kits[:3])
                    if len(incompatible_kits) > 3:
                        incompatible_names = f"{incompatible_names} e mais {len(incompatible_kits) - 3} kit(s)"
                    return _render_modal_error(
                        title="Kit indisponível para este veículo",
                        message=f"Os kits selecionados não correspondem à aplicação do veículo atual: {incompatible_names}.",
                        icon="error",
                    )

                for item_id in selected_ids:
                    item, created = BudgetItem.objects.get_or_create(workshop=self.workshop, budget=budget, kit_id=item_id, defaults={"quantity": 1})
                    if not created:
                        item.quantity += 1
                        item.save()

                # Reset etapas 5 e 6 após modificar a etapa 4
                reset_steps_after_step_4(budget)

                return _step_redirect_response(request, budget, fallback_step=4)

            created_items = []
            for item_id in selected_ids:
                item_filter = {f"{item_type}_id": item_id}

                budget_item, created = BudgetItem.objects.get_or_create(workshop=self.workshop, budget=budget, **item_filter, defaults={"quantity": 1})
                if not created:
                    budget_item.quantity += 1
                    budget_item.save()

                created_items.append(budget_item.pk)
        except Exception:
            logger.exception(
                "Falha ao adicionar itens em lote ao orcamento",
                extra={
                    "budget_id": budget_id,
                    "item_type": item_type,
                    "selected_count": len(raw_selected_ids),
                    "selected_ids": raw_selected_ids[:20],
                },
            )
            error_html = """
            <div class="modal-box w-11/12 max-w-md bg-base-100">
                <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2" onclick="form_modal.close()">✕</button>
                <div class="flex flex-col items-center justify-center py-8">
                    <span class="material-icons text-error text-6xl mb-4">error</span>
                    <h3 class="font-bold text-xl mb-2">Não foi possível adicionar os itens</h3>
                    <p class="text-base-content/70 mb-6">Tente novamente em instantes. Se o problema persistir, contate o suporte.</p>
                    <button class="btn btn-primary" onclick="form_modal.close()">Fechar</button>
                </div>
            </div>
            """
            return HttpResponse(error_html)

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        current_step = _get_current_step_from_referer(request, budget.current_step)

        context = {
            "budget": budget,
            "item_type": item_type,
            "item_ids": created_items,
            "total_items": len(created_items),
            "current_index": 0,
            "current_step": current_step,
        }

        response = render(request, "budget/partials/modals/modal_edit_queue.html", context)
        if modal_context == "child":
            response["HX-Trigger-After-Swap"] = json.dumps({"closeParentBudgetModal": True})
        return response


class BudgetSummaryView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Retorna apenas o partial do resumo do orçamento para atualização via HTMX."""

    model = Budget
    workshop_permission_codename = "view_budget"

    def get(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        return render(request, "budget/partials/components/budget_summary.html", {"budget": budget})


class BudgetStep3CollaboratorFieldView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Retorna apenas o campo de colaborador para refresh via HTMX após criar/editar colaborador."""

    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        form = BudgetStep3Form(instance=budget, workshop=self.workshop, request=request)

        # Configurações para o componente de múltiplos colaboradores
        import json

        initial_collaborators = []
        if budget.pk:
            initial_collaborators = [{"id": str(c.id), "name": c.name} for c in budget.collaborators.all()]

        if not initial_collaborators:
            initial_collaborators = [{"id": "", "is_new": True}]

        initial_collaborators_json = json.dumps(initial_collaborators)

        # Render the field using the template
        context = {
            "form": form,
            "field": form["collaborator"],
            "initial_collaborators_json": initial_collaborators_json,
        }

        return render(request, "budget/partials/components/collaborator_field.html", context)
