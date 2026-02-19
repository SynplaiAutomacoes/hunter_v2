import json
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views import View

from apps.budget.forms import LocalProductForm, LocalServiceForm
from apps.budget.models import Budget
from apps.budget.utils import HtmxResponseHelper
from apps.workshops.mixin import WorkshopScopedMixin

from .shared import _calculate_service_prices, _get_budget_for_workshop, _get_budget_item_for_workshop, _get_budget_workshop_cost, _local_item_kind, _parse_duration_from_string, reset_steps_after_step_4


class CreateLocalItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Modal para criar item local (produto ou serviço apenas neste orçamento)"""

    model = Budget
    workshop_permission_codename = "add_budget"

    def get(self, request, budget_id, item_type):
        _get_budget_for_workshop(self.workshop, budget_id)

        if item_type == "product":
            form = LocalProductForm()
            title = "Incluir Novo Produto Local"
        elif item_type == "service":
            form = LocalServiceForm(budget_id=budget_id)
            title = "Incluir Novo Serviço Local"
        else:
            return HttpResponse("Tipo inválido", status=400)

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": title,
        }
        return render(request, "budget/partials/modals/modal_create_local_item.html", context)

    def post(self, request, budget_id, item_type):
        budget = _get_budget_for_workshop(self.workshop, budget_id)

        if item_type == "product":
            form = LocalProductForm(request.POST)
        elif item_type == "service":
            form = LocalServiceForm(request.POST, budget_id=budget_id)
        else:
            return HttpResponse("Tipo inválido", status=400)

        if form.is_valid():
            item = form.save(commit=False)
            item.workshop = self.workshop
            item.budget = budget
            item.is_local = True
            item.save()

            # Reset etapas 5 e 6 após modificar a etapa 4
            reset_steps_after_step_4(budget)

            # Re-renderiza a seção inteira para remover placeholders de "Nenhum item"
            # quando o primeiro item local é adicionado.
            from apps.budget.forms.shared import _render_budget_items_rows

            rows = _render_budget_items_rows(budget, step6=False)
            target_selector = "#product-list-body" if item_type == "product" else "#service-list-body"

            response = HtmxResponseHelper.success(
                f"{'Produto' if item_type == 'product' else 'Serviço'} local criado com sucesso!",
                close_modal=True,
                update_summary=True,
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
                "code": f"TEMP-{item.id}",  # Código temporário
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

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, is_local=True)
        item_type = _local_item_kind(item)

        if item_type == "product":
            # Cadastrar produto
            form = QuickProductForm(request.POST, workshop=self.workshop)

            if form.is_valid():
                product = form.save(commit=False)
                product.workshop = self.workshop
                product.save()

                # Vincular ao budget item
                item.product = product
                item.is_local = False
                item.save()

                # Retornar a linha atualizada com OOB swap
                context = {"item": item, "budget": item.budget, "is_full_render": False}
                row_html = render_to_string("budget/partials/items/item_product_row.html", context)

                response = HtmxResponseHelper.success("Produto cadastrado com sucesso!", close_modal=True, update_summary=True, content=row_html)
                response["HX-Refresh"] = "true"
                return response

        else:
            # Cadastrar serviço
            form = QuickServiceForm(request.POST)

            if form.is_valid():
                service = form.save(commit=False)
                service.workshop = self.workshop
                service.save()

                # Vincular ao budget item
                item.service = service
                item.is_local = False
                item.save()

                # Retornar a linha atualizada
                context = {"item": item, "budget": item.budget, "is_full_render": False}
                row_html = render_to_string("budget/partials/items/item_service_row.html", context)

                response = HtmxResponseHelper.success("Serviço cadastrado com sucesso!", close_modal=True, update_summary=True, content=row_html)
                response["HX-Refresh"] = "true"
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
        return render(request, "budget/partials/modals/modal_quick_create.html", context)


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
        data["service_selling_price_0"] = str(service_selling_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
        data["service_selling_price_1"] = "BRL"

        form = LocalServiceForm(data, budget_id=budget_id)

        context = {
            "form": form,
            "budget_id": budget_id,
            "oob_fields": ["service_selling_price"],
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

        if item_type == "product":
            form = QuickProductForm(workshop=self.workshop)
            title = "Cadastrar Novo Produto"
        elif item_type == "service":
            form = QuickServiceForm()
            title = "Cadastrar Novo Serviço"
        else:
            return HttpResponse("Tipo inválido", status=400)

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": title,
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)

    def post(self, request, budget_id, item_type):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        budget = _get_budget_for_workshop(self.workshop, budget_id)

        if item_type == "product":
            form = QuickProductForm(request.POST, workshop=self.workshop)
        elif item_type == "service":
            form = QuickServiceForm(request.POST)
        else:
            return HttpResponse("Tipo inválido", status=400)

        if form.is_valid():
            item = form.save(commit=False)
            item.workshop = self.workshop
            item.save()

            # Retornar a lista atualizada de itens
            from apps.catalog.models.products import Product
            from apps.catalog.models.services import Service

            if item_type == "product":
                model_class = Product
            else:
                model_class = Service

            queryset = model_class.objects.filter(workshop=self.workshop, is_active=True)

            # Get already added items
            existing_items = set()
            if item_type == "product":
                existing_items = set(budget.items.filter(product__isnull=False).values_list("product_id", flat=True))
            elif item_type == "service":
                existing_items = set(budget.items.filter(service__isnull=False).values_list("service_id", flat=True))

            context = {
                "items": queryset,
                "budget": budget,
                "item_type": item_type,
                "modal_title": f"Selecionar {'Produto' if item_type == 'product' else 'Serviço'}",
                "existing_items": existing_items,
                "newly_created_id": item.id,  # ID do item recém-criado
            }

            return HtmxResponseHelper.render_and_trigger("budget/partials/modals/modal_item_list.html", context, {"showToast": {"message": f"{'Produto' if item_type == 'product' else 'Serviço'} cadastrado com sucesso!", "type": "success"}})

        # Se form inválido
        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": f"Cadastrar Novo {'Produto' if item_type == 'product' else 'Serviço'}",
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)
