import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from djmoney.money import Money

from apps.budget.forms.item_forms import BudgetKitProductEditRowForm, BudgetKitServiceEditRowForm
from apps.budget.models import Budget, BudgetItem, BudgetKitItemOverride
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.price_tracking import record_product_last_used_price
from apps.workshops.mixin import WorkshopScopedMixin

from .shared import (
    LOCKED_BUDGET_EDIT_MESSAGE,
    _build_concurrent_budget_lock_response,
    _build_locked_budget_response,
    _check_concurrent_budget_lock,
    _get_budget_for_workshop,
    _get_budget_item_for_workshop,
    _get_budget_workshop_cost,
    _is_budget_edit_locked,
    _parse_duration_from_string,
    reset_steps_after_step_4,
    sync_linked_workorder_from_budget,
)

logger = logging.getLogger(__name__)


def _calculate_service_mechanic_cost(duration: timedelta, budget: Budget) -> Money:
    return calculate_mechanic_service_cost(budget=budget, duration=duration)


class BudgetKitEditView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View para editar itens de um kit no contexto deste orçamento"""

    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def get(self, request, budget_id, item_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, kit__isnull=False)
        item.ensure_kit_snapshot()
        workshop_cost, workshop_cost_missing = _get_budget_workshop_cost(budget, self.workshop)

        # Buscar produtos do kit com overrides
        kit_products = []
        for override in item.kit_overrides.filter(product__isnull=False).select_related("product").all():
            product = override.product
            if product is None:
                continue

            row_form = BudgetKitProductEditRowForm(
                initial={
                    "quantity": override.quantity,
                    "cost": override.product_cost_price,
                    "price": override.product_selling_price,
                    "shipping": override.shipping,
                },
                prefix=f"product_{str(product.id)}",
            )

            kit_products.append(
                {
                    "id": str(product.id),
                    "name": product.name,
                    "form": row_form,
                }
            )

        # Buscar serviços do kit com overrides
        kit_services = []
        for override in item.kit_overrides.filter(service__isnull=False).select_related("service").all():
            service = override.service
            if service is None:
                continue

            # Format duration as HH:MM:SS
            duration_str = ""
            if override.duration:
                duration = override.duration
            else:
                duration = timedelta(0)

            if duration:
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            service_mechanic_cost = _calculate_service_mechanic_cost(duration, budget)
            row_form = BudgetKitServiceEditRowForm(
                initial={
                    "quantity": override.quantity,
                    "cost": service_mechanic_cost,
                    "price": override.service_selling_price,
                    "duration": duration_str,
                },
                prefix=f"service_{str(service.id)}",
            )

            kit_services.append(
                {
                    "id": str(service.id),
                    "name": service.name,
                    "form": row_form,
                }
            )

        context = {
            "item": item,
            "kit_products": kit_products,
            "kit_services": kit_services,
            "service_pricing_context": {
                "can_calculate": bool(workshop_cost and not workshop_cost_missing),
                "mechanic_hourly_cost": str(budget.mechanic_hour_cost_value.amount.quantize(Decimal("0.01"))),
                "hourly_cost_value": str(((workshop_cost.hourly_cost_value if workshop_cost else Money(0, "BRL")) or Money(0, "BRL")).amount.quantize(Decimal("0.01"))),
            },
        }

        return render(request, "budget/partials/modals/modal_edit_kit.html", context)

    def post(self, request, budget_id, item_id):
        from apps.budget.models import BudgetKitItemOverride
        from datetime import timedelta

        budget = _get_budget_for_workshop(self.workshop, str(budget_id))
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        item = _get_budget_item_for_workshop(self.workshop, str(budget_id), str(item_id), kit__isnull=False)
        item.ensure_kit_snapshot()

        products_json = request.POST.get("products", "[]")
        try:
            products_data = json.loads(products_json)
        except json.JSONDecodeError:
            logger.exception("budget_kit_products_json_invalid", extra={"budget_id": budget_id, "item_id": item_id, "payload": products_json})
            raise

        services_json = request.POST.get("services", "[]")
        try:
            services_data = json.loads(services_json)
        except json.JSONDecodeError:
            logger.exception("budget_kit_services_json_invalid", extra={"budget_id": budget_id, "item_id": item_id, "payload": services_json})
            raise

        logger.info("budget_kit_override_started", extra={"budget_id": budget_id, "item_id": item_id, "products_count": len(products_data), "services_count": len(services_data)})

        for product_data in products_data:
            product_id = str(product_data.get("id"))
            try:
                product = get_object_or_404(Product, id=str(product_id), workshop=self.workshop)
                existing_override = BudgetKitItemOverride.objects.filter(workshop=self.workshop, budget_item=item, product=product).first()
                product_selling_price = (existing_override.product_selling_price if existing_override else product.selling_price) if budget.is_warranty_budget else Money(Decimal(str(product_data.get("price", 0))), "BRL")

                BudgetKitItemOverride.objects.update_or_create(
                    workshop=self.workshop,
                    budget_item=item,
                    product=product,
                    defaults={
                        "quantity": max(0, int(product_data.get("quantity", 1))),
                        "product_cost_price": Money(Decimal(str(product_data.get("cost", 0))), "BRL"),
                        "product_selling_price": product_selling_price,
                        "shipping": Money(Decimal(str(product_data.get("shipping", 0))), "BRL"),
                    },
                )
                record_product_last_used_price(product=product, price=product_selling_price)
            except Exception:
                logger.exception("budget_kit_product_save_failed", extra={"budget_id": budget_id, "item_id": item_id, "product_id": product_id})
                raise

        for service_data in services_data:
            service_id = str(service_data.get("id"))
            try:
                service = get_object_or_404(Service, id=str(service_id), workshop=self.workshop)
                existing_override = BudgetKitItemOverride.objects.filter(workshop=self.workshop, budget_item=item, service=service).first()

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
                        logger.warning("budget_kit_service_duration_invalid", extra={"budget_id": budget_id, "item_id": item_id, "service_id": service_id, "duration": duration_str})
                        duration = timedelta(0)

                service_selling_price = (existing_override.service_selling_price if existing_override else service.selling_price) if budget.is_warranty_budget else Money(Decimal(str(service_data.get("price", 0))), "BRL")
                service_cost_price = _calculate_service_mechanic_cost(duration or timedelta(0), budget)

                override, created = BudgetKitItemOverride.objects.update_or_create(
                    workshop=self.workshop,
                    budget_item=item,
                    service=service,
                    defaults={
                        "quantity": max(0, int(service_data.get("quantity", 1))),
                        "service_cost_price": service_cost_price,
                        "service_selling_price": service_selling_price,
                        "duration": duration,
                    },
                )

                logger.info("budget_kit_service_saved", extra={"budget_id": budget_id, "item_id": item_id, "service_id": service.id, "override_created": created, "quantity": override.quantity, "duration": str(override.duration) if override.duration else ""})
            except Exception:
                logger.exception("budget_kit_service_save_failed", extra={"budget_id": budget_id, "item_id": item_id, "service_id": service_id})
                raise

        # Reset etapas 5 e 6 após modificar a etapa 4
        reset_steps_after_step_4(budget)

        item._clear_kit_snapshot_caches()
        item.refresh_kit_snapshot_totals()
        sync_linked_workorder_from_budget(budget)

        # Force recalculation by accessing total_price
        _ = item.total_price

        redirect_url = f"/budget/{budget_id}/edit/?step=4"
        if "application/json" in request.headers.get("Accept", ""):
            return JsonResponse({"ok": True, "redirect_url": redirect_url})

        # Redirect with full page reload (HTMX fallback)
        import time

        timestamp = int(time.time())
        response = HttpResponse()
        response["HX-Redirect"] = f"/budget/{budget_id}/edit/?step=4&_t={timestamp}"
        response["HX-Refresh"] = "true"  # Force full page refresh
        return response


def _parse_decimal_value(raw_value, default: Decimal = Decimal("0")) -> Decimal:
    if raw_value is None:
        return default

    text = str(raw_value).strip().replace("R$", "").replace(" ", "")
    if not text:
        return default

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return default


class BudgetKitProductCalculateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def post(self, request, budget_id, item_id, product_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, kit__isnull=False)

        product_in_kit = item.kit.kit_products.filter(product_id=product_id).exists()
        if not product_in_kit:
            return JsonResponse({"error": "product_not_in_kit"}, status=400)

        product = get_object_or_404(Product, id=product_id, workshop=self.workshop)
        existing_override = BudgetKitItemOverride.objects.filter(workshop=self.workshop, budget_item=item, product=product).first()

        quantity = request.POST.get("quantity")
        try:
            parsed_quantity = max(0, int(quantity)) if quantity is not None else (existing_override.quantity if existing_override else 1)
        except (ValueError, TypeError):
            parsed_quantity = existing_override.quantity if existing_override else 1

        cost_default = existing_override.product_cost_price.amount if existing_override else product.cost_price.amount
        price_default = existing_override.product_selling_price.amount if existing_override else product.selling_price.amount
        shipping_default = existing_override.shipping.amount if existing_override else Decimal("0")

        parsed_cost = _parse_decimal_value(request.POST.get("cost"), cost_default).quantize(Decimal("0.01"))
        parsed_price = _parse_decimal_value(request.POST.get("price"), price_default).quantize(Decimal("0.01")) if not budget.is_warranty_budget else price_default.quantize(Decimal("0.01"))
        parsed_shipping = _parse_decimal_value(request.POST.get("shipping"), shipping_default).quantize(Decimal("0.01"))

        BudgetKitItemOverride.objects.update_or_create(
            workshop=self.workshop,
            budget_item=item,
            product=product,
            defaults={
                "quantity": parsed_quantity,
                "product_cost_price": Money(parsed_cost, "BRL"),
                "product_selling_price": Money(parsed_price, "BRL"),
                "shipping": Money(parsed_shipping, "BRL"),
            },
        )
        record_product_last_used_price(product=product, price=Money(parsed_price, "BRL"))
        item._clear_kit_snapshot_caches()
        item.refresh_kit_snapshot_totals()
        reset_steps_after_step_4(budget)
        sync_linked_workorder_from_budget(budget)

        return JsonResponse(
            {
                "product_id": product_id,
                "quantity": parsed_quantity,
                "cost": str(parsed_cost),
                "price": str(parsed_price),
                "shipping": str(parsed_shipping),
                "summary_updated": True,
            }
        )


class BudgetKitServiceCalculateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def post(self, request, budget_id, item_id, service_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        item = _get_budget_item_for_workshop(self.workshop, budget_id, item_id, kit__isnull=False)

        service_in_kit = item.kit.kit_services.filter(service_id=service_id).exists()
        if not service_in_kit:
            return JsonResponse({"error": "service_not_in_kit"}, status=400)

        kit_service = get_object_or_404(item.kit.kit_services.select_related("service"), service_id=service_id)
        service = get_object_or_404(Service, id=service_id, workshop=self.workshop)
        existing_override = BudgetKitItemOverride.objects.filter(workshop=self.workshop, budget_item=item, service=service).first()

        changed_field = (request.POST.get("changed_field") or "").strip()

        raw_duration = request.POST.get("duration")
        parsed_duration = _parse_duration_from_string(raw_duration)
        duration = parsed_duration or (existing_override.duration if existing_override else kit_service.duration) or timedelta(0)

        workshop_cost, workshop_cost_missing = _get_budget_workshop_cost(budget, self.workshop)

        default_cost, default_price = item.resolve_kit_service_base_prices(kit_service=kit_service, workshop_cost=workshop_cost)

        if changed_field == "duration":
            service_cost_price_amount = _calculate_service_mechanic_cost(duration, budget).amount.quantize(Decimal("0.01"))
            price_default = existing_override.service_selling_price.amount if existing_override else default_price.amount
            service_selling_price_amount = price_default.quantize(Decimal("0.01"))
        else:
            cost_default = existing_override.service_cost_price.amount if existing_override and existing_override.service_cost_price else default_cost.amount
            price_default = existing_override.service_selling_price.amount if existing_override else default_price.amount
            service_cost_price_amount = _parse_decimal_value(request.POST.get("cost"), cost_default).quantize(Decimal("0.01"))
            service_selling_price_amount = price_default.quantize(Decimal("0.01")) if budget.is_warranty_budget else _parse_decimal_value(request.POST.get("price"), price_default).quantize(Decimal("0.01"))

        quantity = request.POST.get("quantity")
        try:
            parsed_quantity = max(0, int(quantity)) if quantity is not None else 1
        except ValueError:
            parsed_quantity = 1

        BudgetKitItemOverride.objects.update_or_create(
            workshop=self.workshop,
            budget_item=item,
            service=service,
            defaults={
                "quantity": parsed_quantity,
                "service_cost_price": Money(service_cost_price_amount, "BRL"),
                "service_selling_price": Money(service_selling_price_amount, "BRL"),
                "duration": duration,
            },
        )
        item._clear_kit_snapshot_caches()
        item.refresh_kit_snapshot_totals()
        reset_steps_after_step_4(budget)
        sync_linked_workorder_from_budget(budget)

        return JsonResponse(
            {
                "service_id": service_id,
                "duration": raw_duration,
                "quantity": parsed_quantity,
                "cost": str(service_cost_price_amount),
                "price": str(service_selling_price_amount),
                "workshop_cost_missing": workshop_cost_missing,
                "summary_updated": True,
            }
        )
