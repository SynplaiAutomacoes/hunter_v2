import json
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views import View

from apps.budget.forms import LocalProductForm, LocalServiceForm
from apps.budget.models import Budget, BudgetItem
from apps.budget.utils import HtmxResponseHelper
from apps.workshops.mixin import WorkshopScopedMixin

from .shared import _calculate_service_prices, _get_budget_for_workshop, _get_budget_item_for_workshop, _get_budget_workshop_cost, _get_current_step_from_referer, _local_item_kind, _parse_duration_from_string, reset_steps_after_step_4, _is_budget_edit_locked, LOCKED_BUDGET_EDIT_MESSAGE, _check_concurrent_budget_lock, _build_concurrent_budget_lock_response


class CreateLocalItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Modal para criar item local (produto ou serviço apenas neste orçamento)"""

    model = Budget
    workshop_permission_codename = "add_budget"

    def get(self, request, budget_id, item_type):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        modal_context = request.GET.get("modal_context", "parent")
        modal_target = "#child-modal-container" if modal_context == "child" else "#modal-container"

        default_benefit = "warranty" if budget.budget_type == "warranty" else ("courtesy" if budget.budget_type == "courtesy" else "normal")
        if item_type == "product":
            form = LocalProductForm(is_warranty_budget=budget.is_warranty_budget, item_benefit_type=default_benefit)
            title = "Incluir Novo Produto Local"
        elif item_type == "service":
            form = LocalServiceForm(budget_id=budget_id, is_warranty_budget=budget.is_warranty_budget, item_benefit_type=default_benefit)
            title = "Incluir Novo Serviço Local"
        else:
            return HttpResponse("Tipo inválido", status=400)

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": title,
            "modal_context": modal_context,
            "modal_target": modal_target,
        }
        return render(request, "budget/partials/modals/modal_create_local_item.html", context)

    def post(self, request, budget_id, item_type):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        modal_context = request.POST.get("modal_context", "parent")
        modal_target = "#child-modal-container" if modal_context == "child" else "#modal-container"
        default_benefit = "warranty" if budget.budget_type == "warranty" else ("courtesy" if budget.budget_type == "courtesy" else "normal")
        if item_type == "product":
            form = LocalProductForm(request.POST, is_warranty_budget=budget.is_warranty_budget, item_benefit_type=default_benefit)
        elif item_type == "service":
            form = LocalServiceForm(request.POST, budget_id=budget_id, is_warranty_budget=budget.is_warranty_budget, item_benefit_type=default_benefit)
        else:
            return HttpResponse("Tipo inválido", status=400)

        if form.is_valid():
            item = form.save(commit=False)
            item.workshop = self.workshop
            item.budget = budget
            item.is_local = True
            item.local_item_type = item_type
            item.save()

            # Reset etapas 5 e 6 após modificar a etapa 4
            reset_steps_after_step_4(budget)

            # Re-renderiza a seção inteira para remover placeholders de "Nenhum item"
            # quando o primeiro item local é adicionado.
            from apps.budget.forms.shared import _render_budget_items_rows

            rows = _render_budget_items_rows(budget, step6=False)
            target_selector = "#product-list-body" if item_type == "product" else "#service-list-body"
            additional_triggers = {"closeParentBudgetModal": True} if modal_context == "child" else None

            response = HtmxResponseHelper.success(
                f"{'Produto' if item_type == 'product' else 'Serviço'} local criado com sucesso!",
                close_modal=True,
                update_summary=True,
                additional_triggers=additional_triggers,
                content=rows[item_type],
            )
            response["HX-Retarget"] = target_selector
            response["HX-Reswap"] = "innerHTML"
            return response

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": f"Incluir Novo {'Produto' if item_type == 'product' else 'Serviço'} Local",
            "modal_context": modal_context,
            "modal_target": modal_target,
        }
        return render(request, "budget/partials/modals/modal_create_local_item.html", context)


class RegisterLocalItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Abre modal para cadastrar item local no banco de dados"""

    model = Budget
    workshop_permission_codename = "add_budget"

    def get(self, request, budget_id, item_id):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, is_local=True)
        item_type = _local_item_kind(item)

        if item_type == "product":
            # É um produto - usar formulário simplificado
            initial = {
                "name": item.description,
                "cost_price": item.product_cost_price,
                "selling_price": item.product_selling_price,
                "code": f"TEMP-{item_id}",  # Código temporário
                "unit": "UND",  # Unidade padrão
            }
            form = QuickProductForm(initial=initial, workshop=self.workshop)
            title = "Cadastrar Produto no Banco de Dados"
            item_type = "product"
        else:
            # É um serviço - usar formulário simplificado
            initial = {
                "name": item.description,
                "selling_price": item.service_selling_price,
                "duration": item.duration,
            }
            form = QuickServiceForm(initial=initial)
            title = "Cadastrar Serviço no Banco de Dados"
            item_type = "service"

        context = {
            "form": form,
            "item": item,
            "budget_id": budget_id,
            "item_id": item_id,
            "item_type": item_type,
            "title": title,
            "is_register_mode": True,  # Flag para identificar que é registro de item local
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)

    def post(self, request, budget_id, item_id):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, is_local=True)
        item_type = _local_item_kind(item)

        if item_type == "product":
            # Cadastrar produto
            form = QuickProductForm(request.POST, workshop=self.workshop)

            if form.is_valid():
                product = form.save(commit=False)
                product.workshop = self.workshop
                try:
                    product.save()
                except IntegrityError:
                    form.add_error("code", "Já existe um produto cadastrado com este código.")
                else:
                    # Vincular ao budget item
                    item.product = product
                    item.is_local = False
                    item.local_item_type = ""
                    item.save()

                    # Retornar a linha atualizada com OOB swap
                    context = {"item": item, "budget": item.budget, "is_full_render": False}
                    row_html = render_to_string("budget/partials/items/item_product_row.html", context)

                    response = HtmxResponseHelper.success("Produto cadastrado com sucesso!", close_modal=True, update_summary=True, content=row_html)
                    return response

        else:
            # Cadastrar serviço
            form = QuickServiceForm(request.POST, workshop=self.workshop)

            if form.is_valid():
                service = form.save(commit=False)
                service.workshop = self.workshop
                try:
                    service.save()
                except IntegrityError:
                    form.add_error("name", "Já existe um serviço com este nome.")
                else:
                    # Vincular ao budget item
                    item.service = service
                    item.is_local = False
                    item.local_item_type = ""
                    item.save()

                    # Retornar a linha atualizada
                    context = {"item": item, "budget": item.budget, "is_full_render": False}
                    row_html = render_to_string("budget/partials/items/item_service_row.html", context)

                    response = HtmxResponseHelper.success("Serviço cadastrado com sucesso!", close_modal=True, update_summary=True, content=row_html)
                    return response

        # Se form inválido, retorna com erros
        context = {
            "form": form,
            "item": item,
            "budget_id": budget_id,
            "item_id": item_id,
            "item_type": item_type,
            "title": f"Cadastrar {'Produto' if item_type == 'product' else 'Serviço'} no Banco de Dados",
            "is_register_mode": True,
        }
        response = render(request, "budget/partials/modals/modal_quick_create.html", context)
        response["HX-Retarget"] = "#modal-container"
        response["HX-Reswap"] = "innerHTML"
        return response


class CalculateLocalServiceView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Calcular custos de serviço local baseado na duração"""

    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        duration = _parse_duration_from_string(request.POST.get("duration", ""))
        workshop_cost, workshop_cost_missing = _get_budget_workshop_cost(budget, self.workshop)
        service_cost_price, service_selling_price = _calculate_service_prices(duration, workshop_cost)

        # Preparar form
        data = request.POST.copy()
        data["service_cost_price_0"] = str(service_cost_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
        data["service_cost_price_1"] = "BRL"
        if not budget.is_warranty_budget:
            data["service_selling_price_0"] = str(service_selling_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
            data["service_selling_price_1"] = "BRL"

        default_benefit = "warranty" if budget.budget_type == "warranty" else ("courtesy" if budget.budget_type == "courtesy" else "normal")
        form = LocalServiceForm(data, budget_id=budget_id, is_warranty_budget=budget.is_warranty_budget, item_benefit_type=default_benefit)

        context = {
            "form": form,
            "budget_id": budget_id,
            "oob_fields": ([] if budget.is_warranty_budget else ["service_selling_price"]),
        }

        response = render(request, "budget/partials/modals/modal_local_service_fields.html", context)

        if workshop_cost_missing:
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Custo da oficina não cadastrado para o mês atual.", "type": "error"}})

        return response


class QuickCreateProductView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Cadastro rápido de produto com atualização automática da lista"""

    model = Budget
    workshop_permission_codename = "add_budget"

    def get(self, request, budget_id, item_type):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        _get_budget_for_workshop(self.workshop, budget_id)
        modal_context = request.GET.get("modal_context", "parent")
        modal_target = "#child-modal-container" if modal_context == "child" else "#modal-container"

        if item_type == "product":
            form = QuickProductForm(workshop=self.workshop)
            title = "Cadastrar Novo Produto"
        elif item_type == "service":
            form = QuickServiceForm(workshop=self.workshop)
            title = "Cadastrar Novo Serviço"
        else:
            return HttpResponse("Tipo inválido", status=400)

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": title,
            "modal_context": modal_context,
            "modal_target": modal_target,
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)

    def post(self, request, budget_id, item_type):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        modal_context = request.POST.get("modal_context", "parent")
        modal_target = "#child-modal-container" if modal_context == "child" else "#modal-container"

        if item_type == "product":
            form = QuickProductForm(request.POST, workshop=self.workshop)
        elif item_type == "service":
            form = QuickServiceForm(request.POST, workshop=self.workshop)
        else:
            return HttpResponse("Tipo inválido", status=400)

        if form.is_valid():
            catalog_item = form.save(commit=False)
            catalog_item.workshop = self.workshop
            try:
                catalog_item.save()
            except IntegrityError:
                if item_type == "product":
                    form.add_error("code", "Já existe um produto cadastrado com este código.")
                else:
                    form.add_error("name", "Já existe um serviço com este nome.")
            else:
                if modal_context == "child":
                    item_label = "Produto" if item_type == "product" else "Serviço"
                    return HtmxResponseHelper.success(
                        f"{item_label} cadastrado com sucesso!",
                        close_modal=True,
                        additional_triggers={
                            "quickItemCreated": {
                                "item_id": catalog_item.pk,
                                "item_type": item_type,
                                "budget_id": budget_id,
                            }
                        },
                    )

                if item_type == "product":
                    budget_item = BudgetItem.objects.create(
                        workshop=self.workshop,
                        budget=budget,
                        product=catalog_item,
                        quantity=1,
                    )
                else:
                    budget_item = BudgetItem.objects.create(
                        workshop=self.workshop,
                        budget=budget,
                        service=catalog_item,
                        quantity=1,
                    )

                # Reset etapas 5 e 6 após modificar a etapa 4
                reset_steps_after_step_4(budget)

                created_budget_item_id = getattr(budget_item, "pk")

                current_step = _get_current_step_from_referer(request, budget.current_step)
                context = {
                    "budget": budget,
                    "item_type": item_type,
                    "item_ids": [created_budget_item_id],
                    "total_items": 1,
                    "current_index": 0,
                    "current_step": current_step,
                }

                return HtmxResponseHelper.render_and_trigger(
                    "budget/partials/modals/modal_edit_queue.html",
                    context,
                    {
                        "showToast": {
                            "message": f"{'Produto' if item_type == 'product' else 'Serviço'} cadastrado e adicionado ao orçamento!",
                            "type": "success",
                        }
                    },
                )

        # Se form inválido
        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": f"Cadastrar Novo {'Produto' if item_type == 'product' else 'Serviço'}",
            "modal_context": modal_context,
            "modal_target": modal_target,
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)
