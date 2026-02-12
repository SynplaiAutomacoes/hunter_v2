import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View
from djmoney.money import Money

from apps.budget.forms.item_forms import BudgetKitProductEditRowForm, BudgetKitServiceEditRowForm
from apps.budget.models import Budget, BudgetItem
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost

from .shared import _get_budget_for_workshop, _get_budget_item_for_workshop, logger, reset_steps_after_step_4


class BudgetKitEditView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View para editar itens de um kit no contexto deste orçamento"""

    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def get(self, request, budget_id, item_id):
        from apps.budget.models import BudgetKitItemOverride

        _get_budget_for_workshop(self.workshop, budget_id)
        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, kit__isnull=False)

        # Buscar produtos do kit com overrides
        kit_products = []
        for kit_product in item.kit.kit_products.select_related("product").all():
            product = kit_product.product
            override = BudgetKitItemOverride.objects.filter(budget_item=item, product=product).first()

            quantity = override.quantity if override else kit_product.quantity
            cost = override.product_cost_price if override else product.cost_price
            price = override.product_selling_price if override else product.selling_price
            shipping = override.shipping if override else Money(0, "BRL")

            row_form = BudgetKitProductEditRowForm(
                initial={
                    "quantity": quantity,
                    "cost": cost,
                    "price": price,
                    "shipping": shipping,
                },
                prefix=f"product_{product.id}",
            )

            kit_products.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "form": row_form,
                }
            )

        # Buscar serviços do kit com overrides
        kit_services = []
        for kit_service in item.kit.kit_services.select_related("service").all():
            service = kit_service.service
            override = BudgetKitItemOverride.objects.filter(budget_item=item, service=service).first()

            # Format duration as HH:MM:SS
            duration_str = ""
            if override and override.duration:
                duration = override.duration
            elif service.duration:
                duration = service.duration
            else:
                duration = timedelta(0)

            if duration:
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            quantity = override.quantity if override else kit_service.quantity
            cost = override.service_cost_price if override else service.suggested_cost
            price = override.service_selling_price if override else service.selling_price

            row_form = BudgetKitServiceEditRowForm(
                initial={
                    "quantity": quantity,
                    "cost": cost,
                    "price": price,
                    "duration": duration_str,
                },
                prefix=f"service_{service.id}",
            )

            kit_services.append(
                {
                    "id": service.id,
                    "name": service.name,
                    "form": row_form,
                }
            )

        context = {
            "item": item,
            "kit_products": kit_products,
            "kit_services": kit_services,
        }

        return render(request, "budget/partials/modals/modal_edit_kit.html", context)

    def post(self, request, budget_id, item_id):
        from apps.budget.models import BudgetKitItemOverride
        from datetime import timedelta

        budget = _get_budget_for_workshop(self.workshop, budget_id)
        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, kit__isnull=False)

        # Parse products data
        products_json = request.POST.get("products", "[]")
        products_data = json.loads(products_json)

        for product_data in products_data:
            product_id = product_data.get("id")
            product = get_object_or_404(Product, id=product_id, workshop=self.workshop)

            # Create or update override
            override, created = BudgetKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                budget_item=item,
                product=product,
                defaults={
                    "quantity": max(0, int(product_data.get("quantity", 1))),
                    "product_cost_price": Money(Decimal(str(product_data.get("cost", 0))), "BRL"),
                    "product_selling_price": Money(Decimal(str(product_data.get("price", 0))), "BRL"),
                    "shipping": Money(Decimal(str(product_data.get("shipping", 0))), "BRL"),
                },
            )

        # Parse services data
        services_json = request.POST.get("services", "[]")
        services_data = json.loads(services_json)

        logger.debug(
            "Salvando overrides de kit",
            extra={"budget_item_id": item.id, "products_count": len(products_data), "services_count": len(services_data)},
        )

        for service_data in services_data:
            service_id = service_data.get("id")
            service = get_object_or_404(Service, id=service_id, workshop=self.workshop)

            # Parse duration string (HH:MM:SS)
            duration_str = service_data.get("duration", "00:00:00")
            duration = None
            if duration_str:
                try:
                    parts = duration_str.split(":")
                    if len(parts) == 3:
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        seconds = int(parts[2])
                        duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
                    elif len(parts) == 2:
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        duration = timedelta(hours=hours, minutes=minutes)
                except (ValueError, IndexError):
                    duration = timedelta(0)

            # Create or update override
            override, created = BudgetKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                budget_item=item,
                service=service,
                defaults={
                    "quantity": max(0, int(service_data.get("quantity", 1))),
                    "service_cost_price": Money(Decimal(str(service_data.get("cost", 0))), "BRL"),
                    "service_selling_price": Money(Decimal(str(service_data.get("price", 0))), "BRL"),
                    "duration": duration,
                },
            )

            logger.debug(
                "Override de servico salvo",
                extra={
                    "service_id": service.id,
                    "quantity": override.quantity,
                    "duration": str(override.duration) if override.duration else "",
                },
            )

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        # Force recalculation by accessing total_price
        _ = item.total_price

        # Redirect with full page reload (not HTMX)
        import time

        timestamp = int(time.time())
        response = HttpResponse()
        response["HX-Redirect"] = f"/budget/{budget_id}/edit/?step=4&_t={timestamp}"
        response["HX-Refresh"] = "true"  # Force full page refresh
        return response


class CalculateKitServiceView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Calcula custo e preço de um serviço baseado na duração (para edição de kit)"""

    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        from datetime import timedelta
        from decimal import Decimal

        service_id = request.POST.get("service_id")
        duration_str = request.POST.get("duration", "00:00:00")

        # Parse duration
        duration = None
        try:
            parts = duration_str.split(":")
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            elif len(parts) == 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                duration = timedelta(hours=hours, minutes=minutes)
        except (ValueError, IndexError):
            return JsonResponse({"error": "Invalid duration format"}, status=400)

        if not duration or duration.total_seconds() == 0:
            return JsonResponse({"error": "Duration is required"}, status=400)

        # Get service
        try:
            service = get_object_or_404(Service, id=service_id, workshop=self.workshop)
        except Http404:
            return JsonResponse({"error": "Service not found"}, status=404)

        # Calculate pricing using existing logic
        try:
            budget = _get_budget_for_workshop(self.workshop, budget_id)

            # Try to get WorkshopCost for calculation
            workshop_cost = WorkshopCost.objects.filter(workshop=self.workshop, month=timezone.now().month, year=timezone.now().year).first()

            if workshop_cost and workshop_cost.minimum_hourly_cost:
                # Calculate based on duration and hourly cost
                hours_decimal = Decimal(str(duration.total_seconds())) / Decimal("3600")
                cost = float(workshop_cost.minimum_hourly_cost.amount) * float(hours_decimal)

                # Apply markup from slider (if exists)
                slider_value = budget.slider if hasattr(budget, "slider") else 50
                markup_percentage = Decimal(str(slider_value)) / Decimal("100")
                price = cost * float(Decimal("1") + markup_percentage)

                return JsonResponse({"cost": round(cost, 2), "price": round(price, 2)})
            else:
                # Fallback to service defaults
                cost_val = float(service.suggested_cost.amount) if service.suggested_cost else 0
                price_val = float(service.selling_price.amount) if service.selling_price else 0

                return JsonResponse({"cost": cost_val, "price": price_val})
        except Exception as e:
            logger.exception("Erro ao calcular servico de kit", extra={"budget_id": budget_id, "service_id": service_id})
            return JsonResponse({"error": str(e)}, status=500)
