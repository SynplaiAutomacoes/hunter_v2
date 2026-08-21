from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from djmoney.money import Money

from apps.catalog.fipe_service import get_brand_options, get_cached_fuel_options_for_model, get_model_options, get_vehicle_model_metadata, register_catalog_access_and_maybe_sync
from apps.catalog.forms.kits import KitForm, QuickProductEditForm, QuickServiceEditForm
from apps.budget.models import BudgetItem
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workorder.models import WorkOrderItem
from apps.catalog.util import build_product_kits_assignment_context, calculate_catalog_service_prices, get_current_workshop_cost, recalculate_kit_totals
from apps.core.presentation.navigation import KIT_CREATE_FAVORITE_PAGE
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.utils import clean_id
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.workshops.mixin import WorkshopScopedMixin

logger = logging.getLogger(__name__)


KIT_LIST_FILTERS: tuple[QueryParamFilter, ...] = (QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),)


def _selected_kit_ids_from_values(raw_values: list[str]) -> list[int]:
    selected_kit_ids: list[int] = []

    for raw_id in raw_values:
        cleaned_id = clean_id(raw_id)
        if not cleaned_id:
            continue
        selected_kit_ids.append(int(cleaned_id))

    return list(dict.fromkeys(selected_kit_ids))


def api_fipe_brands(request):
    try:
        register_catalog_access_and_maybe_sync()
        options = get_brand_options()
    except Exception:  # noqa: BLE001
        options = []
    return JsonResponse([{"id": option.value, "label": option.label} for option in options], safe=False)


def api_fipe_models(request):
    brand_name = str(request.GET.get("brand") or "").strip()
    if not brand_name:
        return JsonResponse([], safe=False)

    try:
        options = get_model_options(brand_name=brand_name)
    except Exception:  # noqa: BLE001
        options = []
    return JsonResponse([{"id": option.value, "label": option.label} for option in options], safe=False)


def api_fipe_fuels(request):
    brand_name = str(request.GET.get("brand") or "").strip()
    model_name = str(request.GET.get("model") or "").strip()
    if not brand_name or not model_name:
        return JsonResponse({"fuels": [], "year_start": None, "year_end": None})

    try:
        cached = get_cached_fuel_options_for_model(brand_name=brand_name, model_name=model_name)
        if cached:
            return JsonResponse({"fuels": [{"id": option, "label": option} for option in cached], "year_start": None, "year_end": None})

        metadata = get_vehicle_model_metadata(brand_name=brand_name, model_name=model_name)
    except Exception:  # noqa: BLE001
        metadata = {"fuels": [], "year_start": None, "year_end": None}

    return JsonResponse(
        {
            "fuels": [{"id": option, "label": option} for option in metadata["fuels"]],
            "year_start": metadata["year_start"],
            "year_end": metadata["year_end"],
        }
    )


class FipeCatalogAccessMixin:
    def maybe_register_fipe_catalog_access(self) -> None:
        if self.request.method == "GET":
            register_catalog_access_and_maybe_sync()


class KitListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Kit
    template_name = "kits/kits_list.html"
    context_object_name = "kits"
    htmx_template_name = "kits/partials/kits_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.annotate(
            has_usage=Exists(BudgetItem.objects.filter(kit=OuterRef("pk")).only("pk")) | Exists(WorkOrderItem.objects.filter(kit=OuterRef("pk")).only("pk")),
        )
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=KIT_LIST_FILTERS,
        )
        return queryset.prefetch_related("applications").distinct().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Kit.name.field.verbose_name, attr="name"),
            TableColumn(
                "Aplicações",
                attr=lambda kit: kit.applications_table_value(preview_limit=2),
                td_class="align-top",
                cell_template="kits/partials/applications_cell.html",
                mobile_stack=True,
                sortable=False,
                search_by=("applications__brand", "applications__model", "applications__engine", "applications__fuel"),
            ),
            TableColumn(Kit.is_active.field.verbose_name, attr="is_active"),
            TableColumn(Kit.total_price.field.verbose_name, attr="total_price"),
            TableColumn(Kit.total_duration.field.verbose_name, attr="total_duration"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("catalog:kits_update"),
            TableActionDefaults.delete("catalog:kits_delete", visible=lambda obj: not getattr(obj, "has_usage", False)),
        ]

        return context


class KitCreateView(FipeCatalogAccessMixin, PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Kit
    form_class = KitForm
    template_name = "kits/kits_create.html"
    success_url = reverse_lazy("catalog:kits_list")
    favorite_page_definition = KIT_CREATE_FAVORITE_PAGE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        self.maybe_register_fipe_catalog_access()
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        try:
            return super().form_valid(form)
        except IntegrityError:
            logger.exception(
                "Falha de integridade ao criar kit",
                extra={
                    "workshop_id": getattr(self.workshop, "id", None),
                    "kit_name": form.cleaned_data.get("name"),
                },
            )
            form.add_error("name", "Já existe um kit com este nome na oficina ativa.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        logger.warning(
            "Formulario invalido ao criar kit",
            extra={
                "workshop_id": getattr(self.workshop, "id", None),
                "errors": form.errors.get_json_data(),
                "non_field_errors": [str(error) for error in form.non_field_errors()],
            },
        )
        if form.errors.get("name"):
            messages.error(self.request, form.errors["name"][0])
        return super().form_invalid(form)


class KitUpdateView(FipeCatalogAccessMixin, LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Kit
    form_class = KitForm
    template_name = "kits/kits_update.html"
    success_url = reverse_lazy("catalog:kits_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        self.maybe_register_fipe_catalog_access()
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except IntegrityError:
            logger.exception(
                "Falha de integridade ao atualizar kit",
                extra={
                    "workshop_id": getattr(self.workshop, "id", None),
                    "kit_id": getattr(self.object, "id", None),
                    "kit_name": form.cleaned_data.get("name"),
                },
            )
            form.add_error("name", "Já existe um kit com este nome na oficina ativa.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        logger.warning(
            "Formulario invalido ao atualizar kit",
            extra={
                "workshop_id": getattr(self.workshop, "id", None),
                "kit_id": getattr(self.object, "id", None),
                "errors": form.errors.get_json_data(),
                "non_field_errors": [str(error) for error in form.non_field_errors()],
            },
        )
        if form.errors.get("name"):
            messages.error(self.request, form.errors["name"][0])
        return super().form_invalid(form)


class KitDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Kit
    success_url = reverse_lazy("catalog:kits_list")

    htmx_template_name = "kits/partials/kits_delete_modal.html"
    htmx_trigger = "kits-table-refresh"


class KitProductSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para listar/buscar produtos e retornar opções com checkbox para o modal do Kit."""

    model = Product
    workshop_permission_codename = "view_product"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")

        qs = Product.objects.filter(workshop=self.workshop, is_active=True)
        if query:
            qs = apply_text_search(qs, search_value=query, lookups=("code", "name", "brand"))

        # djmoney MoneyField usa 2 colunas (valor + moeda). Ao usar `.only(...)`,
        # precisamos incluir também os campos `*_currency` para evitar erros ao
        # acessar `product.cost_price` / `product.selling_price` em templates.
        qs = qs.order_by("name").only(
            "id",
            "code",
            "name",
            "brand",
            "cost_price",
            "cost_price_currency",
            "selling_price",
            "selling_price_currency",
        )

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(page)

        return render(
            request,
            "kits/partials/product_suggestions.html",
            {
                "products": page_obj.object_list,
                "page_obj": page_obj,
                "query": query,
            },
        )


class ProductQuickUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Product
    workshop_permission_codename = "change_product"
    template_name = "kits/partials/generic_form.html"
    form_class = QuickProductEditForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        product = form.save()
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps(
            {
                "kit-product-updated": {
                    "id": clean_id(product.pk),
                    "code": product.code,
                    "name": product.name,
                    "cost": KitForm._format_money_display(product.cost_price),
                    "sell": KitForm._format_money_display(product.selling_price),
                }
            }
        )
        return response


class ServiceQuickUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Service
    workshop_permission_codename = "change_service"
    template_name = "kits/partials/generic_form.html"
    form_class = QuickServiceEditForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        service = form.save()
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps(
            {
                "kit-service-updated": {
                    "id": clean_id(service.pk),
                    "name": service.name,
                    "cost": KitForm._format_money_display(service.suggested_cost),
                    "sell": KitForm._format_money_display(service.selling_price),
                    "duration": KitForm._format_duration(service.duration),
                }
            }
        )
        return response


class KitServiceBulkPricingView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Kit
    workshop_permission_codename = "change_kit"

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid_payload"}, status=400)

        services_payload = payload.get("services")
        if not isinstance(services_payload, list):
            return JsonResponse({"error": "invalid_services"}, status=400)

        service_ids: list[int] = []
        normalized_rows: list[dict[str, int | str]] = []
        for row in services_payload:
            if not isinstance(row, dict):
                return JsonResponse({"error": "invalid_service_row"}, status=400)

            cleaned_service_id = clean_id(row.get("id"))
            raw_duration = str(row.get("duration") or "").strip()
            duration = KitForm._parse_duration_value(raw_duration)
            if not cleaned_service_id or duration is None:
                return JsonResponse({"error": "invalid_service_row"}, status=400)

            service_id = int(cleaned_service_id)

            service_ids.append(service_id)
            normalized_rows.append({"id": service_id, "duration": KitForm._format_duration(duration)})

        valid_service_ids = set(Service.objects.filter(workshop=self.workshop, id__in=service_ids).values_list("id", flat=True))
        missing_ids = [service_id for service_id in service_ids if service_id not in valid_service_ids]
        priced_source_rows = [row for row in normalized_rows if int(row["id"]) in valid_service_ids]

        workshop_cost, missing = get_current_workshop_cost(self.workshop)
        if missing or workshop_cost is None:
            return JsonResponse({"services": [], "workshop_cost_missing": True, "missing_ids": missing_ids})

        priced_rows = []
        for row in priced_source_rows:
            duration = KitForm._parse_duration_value(str(row["duration"])) or KitForm._parse_duration_value("00:00:00")
            cost_price, selling_price = calculate_catalog_service_prices(duration, workshop_cost)
            priced_rows.append(
                {
                    "id": row["id"],
                    "cost": KitForm._format_money_display(cost_price),
                    "sell": KitForm._format_money_display(selling_price),
                }
            )

        return JsonResponse({"services": priced_rows, "workshop_cost_missing": False, "missing_ids": missing_ids})


class KitServicesSyncView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Kit
    workshop_permission_codename = "change_kit"

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid_payload"}, status=400)

        services_payload = payload.get("services")
        if not isinstance(services_payload, list):
            return JsonResponse({"error": "invalid_services"}, status=400)

        kit = Kit.objects.filter(workshop=self.workshop, pk=kwargs.get("pk")).first()
        if kit is None:
            return JsonResponse({"error": "kit_not_found"}, status=404)

        raw_mode = str(payload.get("service_pricing_mode") or "").strip()
        valid_modes = {choice[0] for choice in Kit.ServicePricingMode.choices}
        service_pricing_mode = raw_mode if raw_mode in valid_modes else kit.service_pricing_mode

        normalized_rows: list[dict[str, object]] = []
        service_ids: list[int] = []
        for row in services_payload:
            if not isinstance(row, dict):
                return JsonResponse({"error": "invalid_service_row"}, status=400)

            cleaned_service_id = clean_id(row.get("id"))
            raw_qty = row.get("qty", 1)
            raw_duration = str(row.get("duration") or "").strip()
            raw_cost = str(row.get("cost") or "").strip()
            raw_sell_by_duration = str(row.get("sell_by_duration") or "").strip()
            raw_sell = str(row.get("sell") or "").strip()

            try:
                quantity = max(1, int(str(raw_qty)))
            except (TypeError, ValueError):
                return JsonResponse({"error": "invalid_qty"}, status=400)

            duration = KitForm._parse_duration_value(raw_duration)
            cost_value = KitForm._parse_money_value(raw_cost)
            sell_by_duration_value = KitForm._parse_money_value(raw_sell_by_duration)
            sell_value = KitForm._parse_money_value(raw_sell)

            if not cleaned_service_id or duration is None:
                return JsonResponse({"error": "invalid_service_row"}, status=400)
            if raw_cost and cost_value is None:
                return JsonResponse({"error": "invalid_cost"}, status=400)
            if raw_sell_by_duration and sell_by_duration_value is None:
                return JsonResponse({"error": "invalid_sell_by_duration"}, status=400)
            if raw_sell and sell_value is None:
                return JsonResponse({"error": "invalid_sell"}, status=400)

            service_id = int(cleaned_service_id)
            service_ids.append(service_id)
            normalized_rows.append(
                {
                    "service_id": service_id,
                    "quantity": quantity,
                    "duration": duration,
                    "cost_value": cost_value,
                    "sell_by_duration_value": sell_by_duration_value,
                    "sell_value": sell_value,
                }
            )

        services_map = {service.id: service for service in Service.objects.filter(workshop=self.workshop, id__in=service_ids)}
        if len(services_map) != len(set(service_ids)):
            return JsonResponse({"error": "service_not_found"}, status=400)

        with transaction.atomic():
            existing_rows = {item.service_id: item for item in KitService.objects.filter(kit=kit).select_related("service")}
            posted_ids = set(service_ids)

            for service_id, existing in existing_rows.items():
                if service_id not in posted_ids:
                    existing.delete()

            for row in normalized_rows:
                service_id = int(row["service_id"])
                item = existing_rows.get(service_id)
                if item is None:
                    item = KitService(kit=kit, service=services_map[service_id])

                item.quantity = int(row["quantity"])
                item.duration = row["duration"]
                item.cost_price = Money(row["cost_value"], "BRL") if row["cost_value"] is not None else None
                item.duration_selling_price = Money(row["sell_by_duration_value"], "BRL") if row["sell_by_duration_value"] is not None else None
                item.selling_price = Money(row["sell_value"], "BRL") if row["sell_value"] is not None else None
                item.save()

            kit.service_pricing_mode = service_pricing_mode
            recalculate_kit_totals(kit)

        return JsonResponse({"saved": True})


class KitServiceLocalUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Kit
    workshop_permission_codename = "change_kit"

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid_payload"}, status=400)

        kit = Kit.objects.filter(workshop=self.workshop, pk=kwargs.get("pk")).first()
        if kit is None:
            return JsonResponse({"error": "kit_not_found"}, status=404)

        service_id = kwargs.get("service_id")
        raw_qty = payload.get("qty", 1)
        try:
            quantity = max(1, int(str(raw_qty)))
        except (TypeError, ValueError):
            return JsonResponse({"error": "invalid_qty"}, status=400)

        service = Service.objects.filter(workshop=self.workshop, pk=service_id).first()
        if service is None:
            return JsonResponse({"error": "service_not_found"}, status=404)

        kit_service, _ = KitService.objects.get_or_create(
            kit=kit,
            service=service,
            defaults={"quantity": quantity},
        )

        raw_duration = str(payload.get("duration") or "").strip()
        duration = KitForm._parse_duration_value(raw_duration)
        if duration is None:
            return JsonResponse({"error": "invalid_duration"}, status=400)

        raw_cost = str(payload.get("cost") or "").strip()
        cost_value = KitForm._parse_money_value(raw_cost)
        if raw_cost and cost_value is None:
            return JsonResponse({"error": "invalid_cost"}, status=400)

        raw_sell_by_duration = str(payload.get("sell_by_duration") or "").strip()
        sell_by_duration_value = KitForm._parse_money_value(raw_sell_by_duration)
        if raw_sell_by_duration and sell_by_duration_value is None:
            return JsonResponse({"error": "invalid_sell_by_duration"}, status=400)

        raw_sell = str(payload.get("sell") or "").strip()
        sell_value = KitForm._parse_money_value(raw_sell)
        if raw_sell and sell_value is None:
            return JsonResponse({"error": "invalid_sell"}, status=400)

        kit_service.duration = duration
        kit_service.quantity = quantity
        kit_service.cost_price = Money(cost_value, "BRL") if cost_value is not None else None
        kit_service.duration_selling_price = Money(sell_by_duration_value, "BRL") if sell_by_duration_value is not None else None
        kit_service.selling_price = Money(sell_value, "BRL") if sell_value is not None else None
        kit_service.save(update_fields=["quantity", "duration", "cost_price", "cost_price_currency", "duration_selling_price", "duration_selling_price_currency", "selling_price", "selling_price_currency", "atualizado_em"])

        service_pricing_mode = str(payload.get("service_pricing_mode") or "").strip()
        if service_pricing_mode in {choice[0] for choice in Kit.ServicePricingMode.choices} and kit.service_pricing_mode != service_pricing_mode:
            kit.service_pricing_mode = service_pricing_mode

        recalculate_kit_totals(kit)

        return JsonResponse(
            {
                "saved": True,
                "service": {
                    "id": kit_service.service_id,
                    "duration": KitForm._format_duration(kit_service.duration),
                    "cost": KitForm._format_money_display(kit_service.cost_price),
                    "sell_by_duration": KitForm._format_money_display(kit_service.duration_selling_price),
                    "sell": KitForm._format_money_display(kit_service.selling_price),
                },
            }
        )


class KitServiceSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para listar/buscar serviços e retornar opções com checkbox para o modal do Kit."""

    model = Service
    workshop_permission_codename = "view_service"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("service_search", "").strip()
        page = request.GET.get("page", "1")

        qs = Service.objects.filter(workshop=self.workshop, is_active=True)
        if query:
            qs = apply_text_search(qs, search_value=query, lookups=("name",))

        # djmoney MoneyField usa 2 colunas (valor + moeda). Ao usar `.only(...)`,
        # precisamos incluir também os campos `*_currency` para evitar erros ao
        # acessar `service.suggested_cost` / `service.selling_price` em templates.
        qs = qs.order_by("name").only(
            "id",
            "name",
            "duration",
            "suggested_cost",
            "suggested_cost_currency",
            "selling_price",
            "selling_price_currency",
        )

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(page)

        return render(
            request,
            "kits/partials/service_suggestions.html",
            {
                "services": page_obj.object_list,
                "page_obj": page_obj,
                "query": query,
            },
        )


class KitsByProductHXView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Product
    workshop_permission_codename = "view_kit"

    def get(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["product_id"], workshop=self.workshop)
        context = build_product_kits_assignment_context(
            workshop=self.workshop,
            product=product,
            query=request.GET.get("q", ""),
            page=request.GET.get("page", "1"),
            selected_kit_ids=_selected_kit_ids_from_values(request.GET.getlist("selected_kits")),
        )

        context["object"] = product
        context["product"] = product

        return render(
            request,
            "products/sections/product_kits_attribution.html",
            context,
        )


class ProductKitsAssignHXView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Product
    workshop_permission_codename = "change_kit"

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["product_id"], workshop=self.workshop)
        selected_kit_ids = _selected_kit_ids_from_values(request.POST.getlist("selected_kits"))

        kits = list(Kit.objects.filter(workshop=self.workshop, id__in=selected_kit_ids))
        existing_kit_ids = set(KitProduct.objects.filter(product=product, kit_id__in=selected_kit_ids).values_list("kit_id", flat=True))
        created_assignments = 0

        with transaction.atomic():
            for kit in kits:
                kit_id = int(kit.pk or 0)
                if kit_id in existing_kit_ids:
                    continue

                KitProduct.objects.create(kit=kit, product=product, quantity=1)
                recalculate_kit_totals(kit)
                created_assignments += 1

        context = build_product_kits_assignment_context(
            workshop=self.workshop,
            product=product,
            query=request.POST.get("q", ""),
            page=request.POST.get("page", "1"),
            selected_kit_ids=[],
        )
        context["object"] = product
        context["product"] = product

        response = render(request, "products/sections/product_kits_attribution.html", context)
        if created_assignments:
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {
                        "message": f"Produto atribuido a {created_assignments} kit(s) com sucesso.",
                        "type": "success",
                    }
                }
            )
        else:
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {
                        "message": "Selecione pelo menos um kit ainda nao atribuido.",
                        "type": "warning",
                    }
                }
            )
        return response


class ProductKitUnassignHXView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Product
    workshop_permission_codename = "change_kit"

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["product_id"], workshop=self.workshop)
        kit = get_object_or_404(Kit, pk=kwargs["kit_id"], workshop=self.workshop)

        deleted_count, _ = KitProduct.objects.filter(kit=kit, product=product).delete()
        if deleted_count:
            recalculate_kit_totals(kit)

        context = build_product_kits_assignment_context(
            workshop=self.workshop,
            product=product,
            query=request.POST.get("q", ""),
            page=request.POST.get("page", "1"),
            selected_kit_ids=_selected_kit_ids_from_values(request.POST.getlist("selected_kits")),
        )
        context["object"] = product
        context["product"] = product

        response = render(request, "products/sections/product_kits_attribution.html", context)
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {
                    "message": "Atribuicao removida com sucesso." if deleted_count else "Este produto nao estava atribuido a este kit.",
                    "type": "success" if deleted_count else "warning",
                }
            }
        )
        return response
