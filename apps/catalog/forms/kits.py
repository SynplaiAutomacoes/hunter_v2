from __future__ import annotations

from html import escape
import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, cast

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from djmoney.money import Money

from apps.catalog.forms.equivalent_products import EquivalentProductsFormMixin
from apps.catalog.fipe_service import get_brand_options
from apps.catalog.kit_applications import normalize_vehicle_text
from apps.catalog.models import FipeVehicleModel, FipeVehicleType
from apps.catalog.models.kits import Kit, KitApplication, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.util import calculate_catalog_service_prices, get_current_workshop_cost
from apps.core.text_normalization import sentence_case
from apps.core.presentation.widgets import CheckboxInput, TextInput, TextareaInput, MoneyInput, PercentageInput, ImageInput, DurationInput, SearchableSelectInput
from apps.customer.vehicle_engine import normalize_vehicle_engine_choice, vehicle_engine_form_choices
from apps.customer.vehicle_fuel import normalize_vehicle_fuel_choice, vehicle_fuel_form_choices
from apps.workshops.models.workshops import Workshop
from apps.core.presentation.forms import CoreModelForm

logger = logging.getLogger(__name__)


# TODO: Improve mobile visibility of table
class KitForm(CoreModelForm):
    product_search = forms.CharField(required=False, label="Produtos")
    service_search = forms.CharField(required=False, label="Serviços")

    class Meta:
        model = Kit
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Kit Revisão 10.000km"}),
            "description": TextareaInput(attrs={"class": "!bg-transparent"}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def clean_name(self) -> str:
        name = sentence_case(str(self.cleaned_data.get("name", "")).strip())
        if not name or not self.workshop:
            return name

        existing = Kit.objects.filter(workshop=self.workshop, name=name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise forms.ValidationError("Já existe um kit com este nome na oficina ativa.")

        return name

    @staticmethod
    def _empty_application_row() -> dict[str, str]:
        return {
            "brand": "",
            "model": "",
            "engine": "",
            "fuel": "",
            "year_start": "",
            "year_end": "",
        }

    def _extract_application_rows_from_post(self) -> list[dict[str, str]]:
        field_names = ("brand", "model", "engine", "fuel", "year_start", "year_end")
        field_values = {field_name: self._getlist_from_data(f"kit_application_{field_name}") for field_name in field_names}
        row_count = max((len(values) for values in field_values.values()), default=0)

        applications: list[dict[str, str]] = []
        for index in range(row_count):
            row = {field_name: str(field_values[field_name][index] if index < len(field_values[field_name]) else "").strip() for field_name in field_names}
            if not any(row.values()):
                continue
            applications.append(row)

        return applications

    def _build_initial_applications(self) -> list[dict[str, str]]:
        if self.is_bound:
            return [self._normalize_application_row_for_display(application) for application in self._extract_application_rows_from_post()]

        if self.instance.pk:
            applications = [
                self._normalize_application_row_for_display(
                    {
                        "brand": application.brand,
                        "model": application.model,
                        "engine": application.engine,
                        "fuel": application.fuel,
                        "year_start": str(application.year_start),
                        "year_end": str(application.year_end),
                    }
                )
                for application in self.instance.ordered_applications()
            ]
            if applications:
                return applications

        return []

    @staticmethod
    def _normalize_application_row_for_display(application: dict[str, str]) -> dict[str, str]:
        return {
            "brand": str(application.get("brand", "")).strip(),
            "model": str(application.get("model", "")).strip(),
            "engine": normalize_vehicle_engine_choice(application.get("engine", "")),
            "fuel": normalize_vehicle_fuel_choice(application.get("fuel", "")),
            "year_start": str(application.get("year_start", "")).strip(),
            "year_end": str(application.get("year_end", "")).strip(),
        }

    @staticmethod
    def _ensure_application_option(options: list[dict[str, str]], value: str) -> list[dict[str, str]]:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            return options

        if any(str(option.get("id", "")).strip() == normalized_value for option in options):
            return options

        return [*options, {"id": normalized_value, "label": normalized_value}]

    @staticmethod
    def _build_application_model_options(initial_applications: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
        brands = sorted({str(application.get("brand", "")).strip() for application in initial_applications if str(application.get("brand", "")).strip()})
        options_by_brand: dict[str, list[dict[str, str]]] = {brand: [] for brand in brands}

        if brands:
            for model in FipeVehicleModel.objects.filter(vehicle_type=FipeVehicleType.CARROS, is_active=True, brand__vehicle_type=FipeVehicleType.CARROS, brand__is_active=True, brand__name__in=brands).select_related("brand").order_by("brand__name", "name"):
                options_by_brand.setdefault(model.brand.name, []).append({"id": model.name, "label": model.name})

        for application in initial_applications:
            brand = str(application.get("brand", "")).strip()
            model = str(application.get("model", "")).strip()
            if not brand:
                continue
            options_by_brand[brand] = KitForm._ensure_application_option(options_by_brand.get(brand, []), model)

        return options_by_brand

    @staticmethod
    def _build_application_widget_state(application: dict[str, str], *, model_options: list[dict[str, str]] | None = None) -> dict[str, object]:
        state: dict[str, object] = {**application}
        model = str(application.get("model", "")).strip()
        fuel = str(application.get("fuel", "")).strip()

        state["modelOptions"] = KitForm._ensure_application_option(list(model_options or []), model)
        state["fuelOptions"] = [{"id": fuel, "label": fuel}] if fuel else []
        state["engineLocked"] = bool(str(application.get("engine", "")).strip())
        state["fuelLocked"] = bool(fuel)
        return state

    @staticmethod
    def _build_application_select_options_html(*, target_expression: str, choices: list[tuple[str, str]]) -> str:
        options_html: list[str] = []
        for option_value, option_label in choices:
            if not option_value:
                continue

            option_value_literal = escape(json.dumps(str(option_value)), quote=True)
            option_label_text = escape(str(option_label))
            options_html.append(
                f"""
                <li
                    @click="{target_expression} = {option_value_literal}; open = false"
                    class="relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white group transition-colors"
                >
                    <span class="block truncate" :class="{{'font-bold': {target_expression} == {option_value_literal}}}">
                        {option_label_text}
                    </span>

                    <span
                        x-show="{target_expression} == {option_value_literal}"
                        class="absolute inset-y-0 right-0 flex items-center pr-4 text-primary group-hover:text-white"
                    >
                        <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
                        </svg>
                    </span>
                </li>
                """
            )

        return "".join(options_html)

    @classmethod
    def _build_application_select_html(cls, *, field_name: str, target_expression: str) -> str:
        choices = vehicle_engine_form_choices() if field_name == "kit_application_engine" else vehicle_fuel_form_choices()
        options_html = cls._build_application_select_options_html(target_expression=target_expression, choices=choices)
        escaped_name = escape(field_name, quote=True)

        return f"""
        <div class="relative" x-data="{{ open: false }}" @click.outside="open = false">
            <input type="hidden" name="{escaped_name}" :value="{target_expression}">

            <button
                type="button"
                @click="open = !open"
                class="input-theme flex w-full cursor-default items-center justify-between text-left"
                :class="{{'ring-2 ring-primary border-primary': open}}"
            >
                <span x-text="{target_expression} || 'Selecione...'" :class="{{'input-placeholder-color': !{target_expression}}}"></span>

                <span class="pointer-events-none flex items-center pr-2">
                    <svg class="h-5 w-5 transition-transform duration-200" :class="{{'rotate-180': open}}" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M10 3a1 1 0 01.707.293l3 3a1 1 0 01-1.414 1.414L10 5.414 7.707 7.707a1 1 0 01-1.414-1.414l3-3A1 1 0 0110 3zm-3.707 9.293a1 1 0 011.414 0L10 14.586l2.293-2.293a1 1 0 011.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                    </svg>
                </span>
            </button>

            <div
                x-show="open"
                x-transition:enter="transition ease-out duration-100"
                x-transition:enter-start="transform opacity-0 scale-95"
                x-transition:enter-end="transform opacity-100 scale-100"
                x-transition:leave="transition ease-in duration-75"
                x-transition:leave-start="transform opacity-100 scale-100"
                x-transition:leave-end="transform opacity-0 scale-95"
                class="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md bg-base-100 py-1 text-base shadow-lg ring-1 ring-primary ring-opacity-5 focus:outline-none sm:text-sm"
                style="display: none;"
            >
                <ul role="listbox">
                    <li
                        @click="{target_expression} = ''; open = false"
                        class="cursor-pointer select-none py-2 pl-3 pr-9 font-semibold text-error hover:bg-primary hover:text-white"
                    >
                        Limpar seleção
                    </li>
                    {options_html}
                </ul>
            </div>
        </div>
        """

    @staticmethod
    def _format_money_display(value: Money | Decimal | None) -> str:
        if value is None:
            return str(Money(0, "BRL"))
        if isinstance(value, Money):
            return str(value)
        return str(Money(value, "BRL"))

    @staticmethod
    def _parse_money_value(raw_value: str) -> Decimal | None:
        value = (raw_value or "").strip()
        if not value:
            return None

        normalized = value.replace("R$", "").replace("\xa0", "").replace(" ", "")
        if not normalized or normalized in {"-", ",", "."}:
            return None

        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")

        try:
            amount = Decimal(normalized)
        except InvalidOperation:
            return None

        if amount < 0:
            return None

        return amount.quantize(Decimal("0.01"))

    def get_layout(self):
        cancel_url = reverse("catalog:kits_list")
        product_search_url = reverse("catalog:kits_product_search")
        service_search_url = reverse("catalog:kits_service_search")
        service_bulk_pricing_url = reverse("catalog:kits_service_bulk_pricing")
        valid_pricing_modes = {choice[0] for choice in Kit.ServicePricingMode.choices}
        selected_pricing_mode = Kit.ServicePricingMode.BY_DURATION

        if self.instance.pk and self.instance.service_pricing_mode in valid_pricing_modes:
            selected_pricing_mode = self.instance.service_pricing_mode

        if self.is_bound:
            posted_mode = str(self.data.get("kit_service_pricing_mode", "") or "").strip()
            if posted_mode in valid_pricing_modes:
                selected_pricing_mode = posted_mode

        workshop_cost = None
        if self.workshop:
            workshop_cost, _ = get_current_workshop_cost(self.workshop)

        def resolve_duration_based_prices(duration_value: timedelta) -> tuple[str, str]:
            if workshop_cost is None:
                return "-", "-"

            calculated_cost, calculated_sell = calculate_catalog_service_prices(duration_value, workshop_cost)
            return self._format_money_display(calculated_cost), self._format_money_display(calculated_sell)

        initial_products = []
        initial_services = []
        if self.is_bound and self.workshop:
            posted_product_ids = [pid for pid in self._getlist_from_data("kit_products") if pid.isdigit()]
            posted_service_ids = [sid for sid in self._getlist_from_data("kit_services") if sid.isdigit()]

            unique_product_ids = list(dict.fromkeys(posted_product_ids))
            unique_service_ids = list(dict.fromkeys(posted_service_ids))

            products_map = {
                product.id: product
                for product in Product.objects.filter(workshop=self.workshop, id__in=unique_product_ids).only(
                    "id",
                    "code",
                    "name",
                    "cost_price",
                    "cost_price_currency",
                    "selling_price",
                    "selling_price_currency",
                )
            }

            for pid in unique_product_ids:
                pid_int = int(pid)
                product = products_map.get(pid_int)
                if not product:
                    continue
                raw_qty = self.data.get(f"kit_product_qty_{pid}", "1")
                try:
                    qty = max(1, int(str(raw_qty)))
                except (TypeError, ValueError):
                    qty = 1
                initial_products.append(
                    {
                        "id": product.id,
                        "name": f"{product.code} - {product.name}",
                        "cost": str(product.cost_price),
                        "sell": str(product.selling_price),
                        "qty": qty,
                    }
                )

            services_map = {
                service.id: service
                for service in Service.objects.filter(workshop=self.workshop, id__in=unique_service_ids).only(
                    "id",
                    "name",
                    "duration",
                    "suggested_cost",
                    "suggested_cost_currency",
                    "selling_price",
                    "selling_price_currency",
                )
            }

            for sid in unique_service_ids:
                sid_int = int(sid)
                service = services_map.get(sid_int)
                if not service:
                    continue
                raw_qty = self.data.get(f"kit_service_qty_{sid}", "1")
                try:
                    qty = max(1, int(str(raw_qty)))
                except (TypeError, ValueError):
                    qty = 1

                raw_duration = str(self.data.get(f"kit_service_duration_{sid}", "") or "").strip()
                duration_value = self._parse_duration_value(raw_duration)
                formatted_duration = KitForm._format_duration(duration_value)
                raw_cost = str(self.data.get(f"kit_service_cost_{sid}", "") or "").strip()
                cost_value = self._parse_money_value(raw_cost)
                cost_by_duration, sell_by_duration = resolve_duration_based_prices(duration_value or timedelta())
                raw_sell_by_duration = str(self.data.get(f"kit_service_sell_by_duration_{sid}", "") or "").strip()
                sell_by_duration_value = self._parse_money_value(raw_sell_by_duration)
                raw_sell = str(self.data.get(f"kit_service_sell_{sid}", "") or "").strip()
                sell_value = self._parse_money_value(raw_sell)

                initial_services.append(
                    {
                        "id": service.id,
                        "name": service.name,
                        "cost_by_duration": cost_by_duration,
                        "cost_manual": self._format_money_display(cost_value) if cost_value is not None else "",
                        "sell_by_duration": self._format_money_display(sell_by_duration_value) if sell_by_duration_value is not None else sell_by_duration,
                        "sell_inserted": self._format_money_display(sell_value if sell_value is not None else service.selling_price),
                        "qty": qty,
                        "duration": formatted_duration,
                    }
                )
        elif self.instance.pk:
            kit_products = (
                KitProduct.objects.filter(kit=self.instance)
                .select_related("product")
                .only(
                    "quantity",
                    "product__id",
                    "product__code",
                    "product__name",
                    "product__cost_price",
                    "product__cost_price_currency",
                    "product__selling_price",
                    "product__selling_price_currency",
                )
            )
            for kp in kit_products:
                product = kp.product
                initial_products.append(
                    {
                        "id": product.id,
                        "name": f"{product.code} - {product.name}",
                        "cost": str(product.cost_price),
                        "sell": str(product.selling_price),
                        "qty": kp.quantity,
                    }
                )

            kit_services = (
                KitService.objects.filter(kit=self.instance)
                .select_related("service")
                .only(
                    "quantity",
                    "duration",
                    "cost_price",
                    "cost_price_currency",
                    "duration_selling_price",
                    "duration_selling_price_currency",
                    "selling_price",
                    "selling_price_currency",
                    "service__id",
                    "service__name",
                    "service__suggested_cost",
                    "service__suggested_cost_currency",
                    "service__selling_price",
                    "service__selling_price_currency",
                )
            )
            for ks in kit_services:
                service = ks.service
                cost_by_duration, sell_by_duration = resolve_duration_based_prices(ks.duration or timedelta())
                initial_services.append(
                    {
                        "id": service.id,
                        "name": service.name,
                        "cost_by_duration": cost_by_duration,
                        "cost_manual": self._format_money_display(ks.cost_price) if ks.cost_price is not None else "",
                        "sell_by_duration": self._format_money_display(ks.duration_selling_price) if ks.duration_selling_price is not None else sell_by_duration,
                        "sell_inserted": self._format_money_display(ks.resolved_selling_price),
                        "qty": ks.quantity,
                        "duration": KitForm._format_duration(ks.duration),
                    }
                )

        initial_applications = self._build_initial_applications()
        application_model_options = self._build_application_model_options(initial_applications)
        products_json = json.dumps(initial_products)
        services_json = json.dumps(initial_services)
        applications_json = json.dumps([self._build_application_widget_state(application, model_options=application_model_options.get(str(application.get("brand", "")).strip(), [])) for application in initial_applications])
        brand_options = get_brand_options(vehicle_type=FipeVehicleType.CARROS)
        brand_option_items = [{"id": option.value, "label": option.label} for option in brand_options]
        existing_brand_values = {str(option["id"]) for option in brand_option_items}
        for application in initial_applications:
            brand = str(application.get("brand", "")).strip()
            if brand and brand not in existing_brand_values:
                brand_option_items.append({"id": brand, "label": brand})
                existing_brand_values.add(brand)
        brand_options_json = json.dumps(brand_option_items)
        brand_options_html = "\n".join(
            f'<option value="{escape(str(option["id"]), quote=True)}">{escape(str(option["label"]))}</option>'
            for option in brand_option_items
        )
        engine_options_json = json.dumps([{"id": value, "label": label} for value, label in vehicle_engine_form_choices() if value])
        fuel_options_json = json.dumps([{"id": value, "label": label} for value, label in vehicle_fuel_form_choices() if value])

        return Layout(
            Div(
                Div(
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Dados do Kit</h3>'),
                    Field("name", wrapper_class="col-span-12 lg:col-span-11"),
                    Field("is_active", wrapper_class="col-span-12 lg:col-span-1"),
                    Field("description", wrapper_class="col-span-12"),
                    HTML(
                        f"""
                        <div
                            class="col-span-12"
                            x-data="kitItemsManager()"
                            @kit-service-updated.window="applyUpdatedService($event.detail)"
                        >
                            <div class="p-4 bg-base-300 rounded-box mb-4">
                                <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                                    <div>
                                        <div class="font-semibold">Aplicações do Kit</div>
                                        <div class="text-sm text-base-content/70">Opcional: informe os veículos, motorizações e anos compatíveis com este kit.</div>
                                    </div>
                                    <button type="button" class="btn btn-sm btn-primary" @click="addApplication()">Adicionar aplicação</button>
                                </div>

                                <div class="space-y-3">
                                    <template x-for="(application, index) in applications" :key="`application-${{index}}`">
                                        <div class="p-4 border border-base-200 rounded-box bg-base-100">
                                            <div class="grid grid-cols-1 lg:grid-cols-12 gap-3 items-start">
                                                <div class="lg:col-span-2">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Marca <span class="text-error" aria-hidden="true">*</span></span>
                                                    </label>
                                                    <select name="kit_application_brand" class="input-theme w-full" x-model="application.brand" @change="onApplicationBrandChange(index)">
                                                        <option value="">Selecione...</option>
                                                        {brand_options_html}
                                                    </select>
                                                </div>
                                                <div class="lg:col-span-3">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Modelo <span class="text-error" aria-hidden="true">*</span></span>
                                                    </label>
                                                    <select
                                                        name="kit_application_model"
                                                        class="input-theme w-full"
                                                        x-model="application.model"
                                                        x-html="buildApplicationModelOptionsHtml(application)"
                                                        x-effect="syncSelectElementValue($el, application.model)"
                                                        @change="onApplicationModelChange(index)"
                                                        :disabled="!application.brand || application.loadingModels"
                                                    ></select>
                                                </div>
                                                <div class="lg:col-span-1">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Ano inicial <span class="text-error" aria-hidden="true">*</span></span>
                                                    </label>
                                                    <input type="number" name="kit_application_year_start" class="input-theme w-full [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0 [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0" min="1900" max="2100" x-model="application.year_start" placeholder="2015" />
                                                </div>
                                                <div class="lg:col-span-1">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Ano final <span class="text-error" aria-hidden="true">*</span></span>
                                                    </label>
                                                    <input type="number" name="kit_application_year_end" class="input-theme w-full [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0 [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0" min="1900" max="2100" x-model="application.year_end" placeholder="2021" />
                                                </div>
                                                <div class="lg:col-span-2">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Motor</span>
                                                    </label>
                                                    <input type="hidden" :name="application.engineLocked ? 'kit_application_engine' : null" :value="application.engine">
                                                    <input
                                                        x-show="application.engineLocked"
                                                        type="text"
                                                        class="input-theme w-full"
                                                        :value="application.engine || ''"
                                                        disabled
                                                    />
                                                    <select x-show="!application.engineLocked" :name="application.engineLocked ? null : 'kit_application_engine'" class="input-theme w-full" x-model="application.engine" :disabled="!application.model">
                                                        <option value="">Selecione...</option>
                                                        <template x-for="option in application.engineOptions" :key="`engine-${{index}}-${{option.id}}`">
                                                            <option :value="option.id" x-text="option.label"></option>
                                                        </template>
                                                    </select>
                                                    <p x-show="!application.engineLocked && application.model && !application.engine" style="display: none;" class="mt-1 flex items-start gap-1 text-xs text-warning">
                                                        <span class="material-icons text-sm leading-none">warning</span>
                                                        <span>Motor não identificado pela FIPE. Selecione manualmente.</span>
                                                    </p>
                                                </div>
                                                <div class="lg:col-span-2">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Combustível</span>
                                                    </label>
                                                    <input type="hidden" :name="application.fuelLocked ? 'kit_application_fuel' : null" :value="application.fuel">
                                                    <input
                                                        x-show="application.fuelLocked"
                                                        type="text"
                                                        class="input-theme w-full"
                                                        :value="application.fuel || ''"
                                                        disabled
                                                    />
                                                    <select x-show="!application.fuelLocked" :name="application.fuelLocked ? null : 'kit_application_fuel'" class="input-theme w-full" x-model="application.fuel" :disabled="!application.model || application.loadingFuels">
                                                        <option value="" x-text="application.loadingFuels ? 'Carregando...' : 'Selecione...' "></option>
                                                        <template x-for="option in application.fuelOptions" :key="`fuel-${{index}}-${{option.id}}`">
                                                            <option :value="option.id" x-text="option.label"></option>
                                                        </template>
                                                    </select>
                                                    <p x-show="!application.fuelLocked && application.model && !application.fuel && !application.loadingFuels" style="display: none;" class="mt-1 flex items-start gap-1 text-xs text-warning">
                                                        <span class="material-icons text-sm leading-none">warning</span>
                                                        <span>Combustível não identificado pela FIPE. Selecione manualmente.</span>
                                                    </p>
                                                </div>
                                                <div class="lg:col-span-1 flex justify-end lg:pt-7">
                                                    <button type="button" class="btn btn-ghost btn-sm text-error" @click="removeApplication(index)">
                                                        <span class="material-icons text-base">delete</span>
                                                    </button>
                                                </div>
                                            </div>

                                            <div class="mt-3 flex items-center justify-between gap-2 text-sm text-base-content/70">
                                                <span x-text="formatApplicationPreview(application)"></span>
                                                <span class="badge badge-ghost" x-text="`Aplicação ${{index + 1}}`"></span>
                                            </div>
                                        </div>
                                    </template>

                                    <div x-show="applications.length === 0" class="min-h-28 rounded-box border border-dashed border-base-300 bg-base-100 flex items-center justify-center p-4 text-center text-sm text-base-content/70">
                                        Nenhuma aplicação adicionada.
                                    </div>

                                </div>
                            </div>

                            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">
                                <div class="p-4 bg-base-300 rounded-box">
                                    <div class="text-sm text-base-content/70">Duração Total</div>
                                    <div class="text-xl font-semibold" x-text="totalDurationDisplay"></div>
                                </div>
                                <div class="p-4 bg-base-300 rounded-box">
                                    <div class="text-sm text-base-content/70" x-text="servicePricingMode === 'by_duration' ? 'Valor do Kit por Duração' : 'Valor inserido do kit'"></div>
                                    <div class="text-xl font-semibold" x-text="currentKitSellTotalDisplay()"></div>
                                </div>
                            </div>

                            <div class="divider my-1"></div>
                            <h3 class="text-xl font-bold mb-2">Itens do Kit</h3>

                            <div class="flex flex-wrap gap-2 mb-3">
                                <label for="kit-products-modal" class="btn btn-sm btn-primary" @click="openProductsModal()">Adicionar Produto</label>
                                <label for="kit-services-modal" class="btn btn-sm btn-primary" @click="openServicesModal()">Adicionar Serviço</label>
                                <label for="kit-distribute-time-modal" class="btn btn-sm btn-primary" @click="openDistributeTimeModal()">Inserir tempo total do Kit</label>
                                <label for="kit-distribute-service-sell-modal" class="btn btn-sm btn-primary" @click="openDistributeServiceSellModal()">Inserir Valor Total Venda Serviços</label>
                            </div>

                            <div class="p-4 bg-base-300 rounded-box mb-4">
                                <div class="font-semibold mb-2">Produtos</div>
                                <div class="overflow-x-auto">
                                    <table class="table table-sm">
                                        <thead>
                                            <tr>
                                                <th>Produto</th>
                                                <th class="text-right">Custo</th>
                                                <th class="text-right">Venda</th>
                                                <th class="text-center">Qtd</th>
                                                <th class="text-right"></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <template x-for="(item, index) in selectedProducts" :key="'p-'+item.id">
                                                <tr>
                                                    <td>
                                                        <span x-text="item.name"></span>
                                                    </td>
                                                    <td class="text-right whitespace-nowrap"><span x-text="item.cost"></span></td>
                                                    <td class="text-right whitespace-nowrap"><span x-text="item.sell"></span></td>
                                                    <td class="text-center">
                                                        <input type="number" min="1" step="1" class="input-theme w-20 text-center [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0 [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0" x-model.number="item.qty" />
                                                    </td>
                                                    <td class="text-right whitespace-nowrap">
                                                        <div class="flex items-center justify-end gap-1 min-w-max">
                                                            <button type="button"
                                                                    class="btn-table-edit"
                                                                    @click="openProductEditModal(item.id)"
                                                                    title="Editar Produto">
                                                                <span class="material-icons text-base">edit</span>
                                                            </button>

                                                            <button type="button" class="btn-table-delete" @click="removeProduct(index)" title="Remover">
                                                                <span class="material-icons text-base">delete</span>
                                                            </button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            </template>
                                            <tr x-show="selectedProducts.length === 0">
                                                <td colspan="5" class="text-sm text-gray-500 italic">Nenhum produto adicionado.</td>
                                            </tr>
                                        </tbody>
                                        <tfoot>
                                            <tr class="border-t border-base-300">
                                                <th>Total dos produtos</th>
                                                <th class="text-right whitespace-nowrap" x-text="productsCostTotalDisplay()"></th>
                                                <th class="text-right whitespace-nowrap" x-text="productsSellTotalDisplay()"></th>
                                                <th></th>
                                                <th></th>
                                            </tr>
                                        </tfoot>
                                    </table>
                                </div>
                                <select name="kit_products" multiple class="hidden">
                                    <template x-for="item in selectedProducts" :key="'po-'+item.id">
                                        <option :value="item.id" selected></option>
                                    </template>
                                </select>
                                <template x-for="item in selectedProducts" :key="'pq-'+item.id">
                                    <input type="hidden" :name="'kit_product_qty_' + item.id" :value="item.qty" />
                                </template>
                            </div>

                            <div class="p-4 bg-base-300 rounded-box">
                                <div class="font-semibold mb-2">Serviços</div>
                                <div class="overflow-x-auto">
                                    <table class="table table-sm">
                                        <thead>
                                            <tr>
                                                <th>Serviço</th>
                                                <th class="text-right">Custo</th>
                                                <th class="text-right transition-all duration-200" :class="servicePricingColumnClasses('by_duration', 'header')">Valor de venda por tempo</th>
                                                <th class="text-right transition-all duration-200" :class="servicePricingColumnClasses('inserted_value', 'header')">Valor de Venda Inserido</th>
                                                <th class="text-center">Qtd</th>
                                                <th class="text-center">Duração</th>
                                                <th class="text-right"></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <template x-for="(item, index) in selectedServices" :key="'s-'+item.id">
                                                <tr>
                                                    <td><span x-text="item.name"></span></td>
                                                    <td class="text-right whitespace-nowrap"><span x-text="resolvedServiceCostDisplay(item)"></span></td>
                                                    <td class="text-right whitespace-nowrap transition-all duration-200" :class="servicePricingColumnClasses('by_duration', 'body')"><span x-text="item.sell_by_duration"></span></td>
                                                    <td class="text-right whitespace-nowrap transition-all duration-200" :class="servicePricingColumnClasses('inserted_value', 'body')"><span x-text="item.sell_inserted"></span></td>
                                                    <td class="text-center">
                                                        <input type="number" min="1" step="1" class="input-theme w-20 text-center [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0 [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0" x-model.number="item.qty" @change="handleServiceQuantityChange(index, $event)" />
                                                    </td>
                                                    <td class="text-center whitespace-nowrap">
                                                        <span x-text="formatDurationForDisplay(item.duration)"></span>
                                                    </td>
                                                    <td class="text-right whitespace-nowrap">
                                                        <div class="flex items-center justify-end gap-1 min-w-max">
                                                            <button type="button"
                                                                    class="btn-table-edit"
                                                                    @click="openServiceEditModal(item.id)"
                                                                    title="Editar Serviço">
                                                                <span class="material-icons text-base">edit</span>
                                                            </button>

                                                            <button type="button" class="btn-table-delete" @click="removeService(index)" title="Remover">
                                                                <span class="material-icons text-base">delete</span>
                                                            </button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            </template>
                                            <tr x-show="selectedServices.length === 0">
                                                <td colspan="7" class="text-sm text-gray-500 italic">Nenhum serviço adicionado.</td>
                                            </tr>
                                        </tbody>
                                        <tfoot>
                                            <tr class="border-t border-base-300">
                                                <th>Total dos serviços</th>
                                                <th class="text-right whitespace-nowrap" x-text="servicesCostTotalDisplay()"></th>
                                                <th class="text-right whitespace-nowrap transition-all duration-200" :class="servicePricingColumnClasses('by_duration', 'footer')" x-text="servicesSellByDurationTotalDisplay()"></th>
                                                <th class="text-right whitespace-nowrap transition-all duration-200" :class="servicePricingColumnClasses('inserted_value', 'footer')" x-text="servicesSellInsertedTotalDisplay()"></th>
                                                <th></th>
                                                <th></th>
                                                <th></th>
                                            </tr>
                                            <tr>
                                                <th colspan="2"></th>
                                                <th colspan="2" class="pt-3 pb-1 px-0">
                                                    <div class="text-[11px] font-semibold text-center mb-1 text-base-content/70">Escolha qual método esse kit será cobrado</div>
                                                    <div class="relative grid grid-cols-2 items-center p-1 rounded-full bg-base-100 border border-base-300 w-full max-w-none mx-auto">
                                                        <div
                                                            class="absolute top-1 bottom-1 left-1 w-[calc(50%-0.25rem)] rounded-full bg-primary transition-transform duration-200"
                                                            :class="servicePricingMode === 'by_duration' ? 'translate-x-0' : 'translate-x-full'"
                                                        ></div>
                                                        <button
                                                            type="button"
                                                            class="relative z-10 px-2 py-1 text-xs font-semibold text-center rounded-md transition-colors duration-200"
                                                            :class="servicePricingMode === 'by_duration' ? 'text-primary-content' : 'text-base-content/70'"
                                                            @click="setServicePricingMode('by_duration')"
                                                        >
                                                            Valor de venda por tempo
                                                        </button>
                                                        <button
                                                            type="button"
                                                            class="relative z-10 px-2 py-1 text-xs font-semibold text-center rounded-md transition-colors duration-200"
                                                            :class="servicePricingMode === 'inserted_value' ? 'text-primary-content' : 'text-base-content/70'"
                                                            @click="setServicePricingMode('inserted_value')"
                                                        >
                                                            Valor de venda inserido
                                                        </button>
                                                    </div>
                                                </th>
                                                <th colspan="3"></th>
                                            </tr>
                                        </tfoot>
                                    </table>
                                </div>
                                <select name="kit_services" multiple class="hidden">
                                    <template x-for="item in selectedServices" :key="'so-'+item.id">
                                        <option :value="item.id" selected></option>
                                    </template>
                                </select>
                                <template x-for="item in selectedServices" :key="'sq-'+item.id">
                                    <input type="hidden" :name="'kit_service_qty_' + item.id" :value="item.qty" />
                                </template>
                                <template x-for="item in selectedServices" :key="'sd-'+item.id">
                                    <input type="hidden" :name="'kit_service_duration_' + item.id" :value="normalizeDurationForPost(item.duration)" />
                                </template>
                                <template x-for="item in selectedServices" :key="'sc-'+item.id">
                                    <input type="hidden" :name="'kit_service_cost_' + item.id" :value="serviceManualCostForPost(item)" />
                                </template>
                                <template x-for="item in selectedServices" :key="'sbd-'+item.id">
                                    <input type="hidden" :name="'kit_service_sell_by_duration_' + item.id" :value="normalizeMoneyForPost(item.sell_by_duration)" />
                                </template>
                                <template x-for="item in selectedServices" :key="'ss-'+item.id">
                                    <input type="hidden" :name="'kit_service_sell_' + item.id" :value="normalizeMoneyForPost(item.sell_inserted)" />
                                </template>
                                <input type="hidden" name="kit_service_pricing_mode" :value="servicePricingMode" />
                            </div>

                            <input type="checkbox" id="kit-products-modal" class="modal-toggle" />
                            <div class="modal" role="dialog" aria-modal="true">
                                <div class="modal-box max-w-4xl">
                                    <h3 class="text-lg font-bold">Adicionar Produto</h3>
                                    <div class="mt-4">
                                        <input
                                            type="text"
                                            id="kit-product-search-input"
                                            name="product_search"
                                            class="input-theme w-full"
                                            placeholder="Filtrar por código, nome ou marca..."
                                            autocomplete="off"
                                            hx-get="{product_search_url}"
                                            hx-trigger="keyup changed delay:500ms"
                                            hx-target="#kit-product-items"
                                            hx-swap="innerHTML"
                                        />

                                        <div class="mt-3 max-h-80 overflow-y-auto border border-base-200 rounded-box">
                                            <table class="table table-sm bg-base-100">
                                                <thead class="sticky top-0 bg-base-100">
                                                    <tr>
                                                        <th class="w-10"></th>
                                                        <th>Produto</th>
                                                        <th class="text-right">Custo</th>
                                                        <th class="text-right">Venda</th>
                                                    </tr>
                                                </thead>
                                                <tbody id="kit-product-items"></tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div class="modal-action">
                                        <button type="button" class="btn btn-primary" @click="applySelectedProducts()">Adicionar</button>
                                        <label for="kit-products-modal" class="btn btn-ghost">Fechar</label>
                                    </div>
                                </div>
                                <label class="modal-backdrop" for="kit-products-modal">Close</label>
                            </div>

                            <input type="checkbox" id="kit-services-modal" class="modal-toggle" />
                            <div class="modal" role="dialog" aria-modal="true">
                                <div class="modal-box max-w-4xl">
                                    <h3 class="text-lg font-bold">Adicionar Serviço</h3>
                                    <div class="mt-4">
                                        <input
                                            type="text"
                                            id="kit-service-search-input"
                                            name="service_search"
                                            class="input-theme w-full"
                                            placeholder="Filtrar por nome..."
                                            autocomplete="off"
                                            hx-get="{service_search_url}"
                                            hx-trigger="keyup changed delay:500ms"
                                            hx-target="#kit-service-items"
                                            hx-swap="innerHTML"
                                        />

                                        <div class="mt-3 max-h-80 overflow-y-auto border border-base-200 rounded-box">
                                            <table class="table table-sm bg-base-100">
                                                <thead class="sticky top-0 bg-base-100">
                                                    <tr>
                                                        <th class="w-10"></th>
                                                        <th>Serviço</th>
                                                        <th class="text-right">Custo</th>
                                                        <th class="text-right">Venda</th>
                                                    </tr>
                                                </thead>
                                                <tbody id="kit-service-items"></tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div class="modal-action">
                                        <button type="button" class="btn btn-primary" @click="applySelectedServices()">Adicionar</button>
                                        <label for="kit-services-modal" class="btn btn-ghost">Fechar</label>
                                    </div>
                                </div>
                                <label class="modal-backdrop" for="kit-services-modal">Close</label>
                            </div>

                            <input type="checkbox" id="kit-distribute-time-modal" class="modal-toggle" />
                            <div class="modal" role="dialog" aria-modal="true">
                                <div class="modal-box max-w-md">
                                    <h3 class="text-lg font-bold">Inserir tempo total do Kit</h3>
                                    <p class="text-sm text-base-content/70 mt-1">Informe o tempo total do kit para distribuir entre os serviços com base na quantidade.</p>
                                    <div class="mt-4 space-y-2">
                                        <label class="label p-0" for="kit-total-time-input">
                                            <span class="label-text">Tempo total do kit (HH:MM)</span>
                                        </label>
                                        <input
                                            id="kit-total-time-input"
                                            type="text"
                                            class="input-theme w-full"
                                            placeholder="Ex: 02:40"
                                            x-model="distributionTotalTime"
                                            @input="handleDistributionTimeInput($event)"
                                        />
                                        <p class="text-xs text-base-content/70">Serviços selecionados: <span class="font-semibold" x-text="selectedServices.length"></span></p>
                                    </div>
                                    <div class="modal-action">
                                        <button type="button" class="btn btn-primary" @click="applyTimeDistribution()">Distribuir</button>
                                        <label for="kit-distribute-time-modal" class="btn btn-ghost">Fechar</label>
                                    </div>
                                </div>
                                <label class="modal-backdrop" for="kit-distribute-time-modal">Close</label>
                            </div>

                            <input type="checkbox" id="kit-distribute-service-sell-modal" class="modal-toggle" />
                            <div class="modal" role="dialog" aria-modal="true">
                                <div class="modal-box max-w-md">
                                    <h3 class="text-lg font-bold">Inserir Valor Total Venda Serviços</h3>
                                    <p class="text-sm text-base-content/70 mt-1">Informe o valor total de venda dos serviços do kit para distribuir entre os serviços com base na quantidade.</p>
                                    <div class="mt-4 space-y-2">
                                        <label class="label p-0" for="kit-total-service-sell-input">
                                            <span class="label-text">Valor total de venda dos serviços</span>
                                        </label>
                                        <input
                                            id="kit-total-service-sell-input"
                                            type="text"
                                            class="input-theme w-full"
                                            placeholder="Ex: R$ 150,00"
                                            x-model="distributionTotalServiceSell"
                                            @input="handleDistributionServiceSellInput($event)"
                                        />
                                        <p class="text-xs text-base-content/70">Serviços selecionados: <span class="font-semibold" x-text="selectedServices.length"></span></p>
                                    </div>
                                    <div class="modal-action">
                                        <button type="button" class="btn btn-primary" @click="applyServiceSellDistribution()">Distribuir</button>
                                        <label for="kit-distribute-service-sell-modal" class="btn btn-ghost">Fechar</label>
                                    </div>
                                </div>
                                <label class="modal-backdrop" for="kit-distribute-service-sell-modal">Close</label>
                            </div>

                            <input type="checkbox" id="edit-item-modal" class="modal-toggle" @change="if (!$event.target.checked) resetEditModalContent()" />
                            <div class="modal" role="dialog">
                                <div class="modal-box w-11/12 max-w-5xl relative bg-base-100">
                                    <label for="edit-item-modal" class="btn btn-sm btn-circle absolute right-2 top-2" @click="resetEditModalContent()">✕</label>

                                    <div id="edit-modal-content">
                                        <div class="p-6 text-sm text-base-content/70">Selecione um item para editar.</div>
                                    </div>
                                </div>
                                <label class="modal-backdrop" for="edit-item-modal" @click="resetEditModalContent()">Close</label>
                            </div>

                            <input type="checkbox" id="edit-kit-service-modal" class="modal-toggle" @change="if (!$event.target.checked) resetServiceEditForm()" />
                            <div class="modal" role="dialog" aria-modal="true">
                                <div class="modal-box w-11/12 max-w-2xl relative bg-base-100">
                                    <label for="edit-kit-service-modal" class="btn btn-sm btn-circle absolute right-2 top-2" @click="resetServiceEditForm()">✕</label>
                                    <h3 class="text-lg font-bold">Editar serviço do kit</h3>
                                    <p class="text-sm text-base-content/70 mt-1" x-text="serviceEditForm.name || 'Ajuste os valores locais do serviço dentro deste kit.'"></p>

                                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                                        <div class="space-y-2">
                                            <label class="label p-0" for="kit-service-edit-duration">
                                                <span class="label-text">Duração</span>
                                            </label>
                                            <input
                                                id="kit-service-edit-duration"
                                                type="text"
                                                class="input-theme w-full"
                                                placeholder="Ex: 01:30"
                                                x-model="serviceEditForm.duration"
                                                @input="handleServiceEditDurationInput($event)"
                                            />
                                            <p class="text-xs text-base-content/70">Ao alterar a duração, o custo manual é limpo e o custo por duração é recalculado.</p>
                                        </div>

                                        <div class="space-y-2">
                                            <label class="label p-0" for="kit-service-edit-sell">
                                                <span class="label-text">Valor de venda inserido</span>
                                            </label>
                                            <input
                                                id="kit-service-edit-sell"
                                                type="text"
                                                class="input-theme w-full"
                                                placeholder="Ex: R$ 150,00"
                                                x-model="serviceEditForm.sell"
                                                @input="handleServiceEditMoneyInput($event, 'sell')"
                                            />
                                        </div>

                                        <div class="space-y-2">
                                            <label class="label p-0" for="kit-service-edit-sell-duration">
                                                <span class="label-text">Valor de venda por tempo</span>
                                            </label>
                                            <input
                                                id="kit-service-edit-sell-duration"
                                                type="text"
                                                class="input-theme w-full"
                                                x-model="serviceEditForm.sellByDuration"
                                                @input="handleServiceEditMoneyInput($event, 'sellByDuration')"
                                            />
                                            <p class="text-xs text-base-content/70">Esse valor e recalculado automaticamente com base na duração do serviço.</p>
                                        </div>

                                        <div class="space-y-2 md:col-span-2">
                                            <label class="label p-0" for="kit-service-edit-cost">
                                                <span class="label-text">Custo local do kit</span>
                                            </label>
                                            <input
                                                id="kit-service-edit-cost"
                                                type="text"
                                                class="input-theme w-full"
                                                placeholder="Deixe vazio para usar o custo por duração"
                                                x-model="serviceEditForm.cost"
                                                @input="handleServiceEditMoneyInput($event, 'cost')"
                                            />
                                            <p class="text-xs text-base-content/70">Se ficar vazio, o kit usa o custo por duração exibido na tabela.</p>
                                        </div>
                                    </div>

                                    <div class="modal-action mt-8">
                                        <button type="button" class="btn btn-primary" @click="applyServiceEdit()">Salvar alterações</button>
                                        <label for="edit-kit-service-modal" class="btn btn-ghost" @click="resetServiceEditForm()">Cancelar</label>
                                    </div>
                                </div>
                                <label class="modal-backdrop" for="edit-kit-service-modal" @click="resetServiceEditForm()">Close</label>
                            </div>
                        </div>

                        <script>
                            function kitItemsManager() {{
                                return {{
                                    kitId: {self.instance.pk if self.instance.pk else "null"},
                                    selectedProducts: {products_json},
                                    selectedServices: {services_json},
                                    applications: {applications_json},
                                    brandOptions: {brand_options_json},
                                    baseEngineOptions: {engine_options_json},
                                    baseFuelOptions: {fuel_options_json},
                                    modalSelectedProducts: [],
                                    modalSelectedServices: [],
                                    serviceEditForm: {{
                                        id: null,
                                        name: '',
                                        duration: '',
                                        sellByDuration: '',
                                        sell: '',
                                        cost: '',
                                        originalDuration: '',
                                        originalSellByDuration: '',
                                        originalSell: '',
                                        originalCost: '',
                                        originalManualCost: '',
                                    }},
                                    servicePricingMode: '{selected_pricing_mode}',
                                    totalDurationDisplay: '00:00',

                                    init() {{
                                        this.applications = this.applications.map((application) => this.normalizeApplicationState(application));
                                        this.refreshTotalDurationDisplay();
                                        this.resetEditModalContent();
                                        this.initializeApplications();
                                    }},
                                    normalizeApplicationState(application = {{}}) {{
                                        const model = application.model || '';
                                        const fuel = application.fuel || '';
                                        return {{
                                            brand: application.brand || '',
                                            model: model,
                                            engine: application.engine || '',
                                            fuel: fuel,
                                            year_start: application.year_start || '',
                                            year_end: application.year_end || '',
                                            modelOptions: this.ensureSelectedOption(application.modelOptions, model),
                                            engineOptions: this.buildEngineOptions(application.engine || ''),
                                            fuelOptions: this.ensureSelectedOption(application.fuelOptions, fuel),
                                            engineLocked: !!application.engineLocked,
                                            fuelLocked: !!application.fuelLocked,
                                            loadingModels: false,
                                            loadingFuels: false,
                                        }};
                                    }},
                                    buildEngineOptions(selectedValue = '') {{
                                        const normalizedSelectedValue = (selectedValue || '').toString().trim();
                                        const options = Array.isArray(this.baseEngineOptions) ? [...this.baseEngineOptions] : [];
                                        if (!normalizedSelectedValue) return options;
                                        const hasOption = options.some((option) => String(option.id) === normalizedSelectedValue);
                                        return hasOption ? options : [...options, {{ id: normalizedSelectedValue, label: normalizedSelectedValue }}];
                                    }},
                                    extractEngineFromModelName(modelName) {{
                                        const normalizedModelName = (modelName || '').toString().trim();
                                        if (!normalizedModelName) return '';
                                        const match = normalizedModelName.match(/(^|[^0-9])(\d[\.,]\d)(?!\d)/);
                                        return match ? match[2].replace(',', '.') : '';
                                    }},
                                    getApplicationModelLabel(application) {{
                                        if (!application || !application.model) return '';
                                        const selectedOption = (application.modelOptions || []).find((option) => String(option.id) === String(application.model));
                                        if (selectedOption && selectedOption.label) return selectedOption.label;
                                        return application.model;
                                    }},
                                    escapeSelectOptionValue(value) {{
                                        return String(value ?? '').replace(/[&<>"']/g, (character) => ({{
                                            '&': '&amp;',
                                            '<': '&lt;',
                                            '>': '&gt;',
                                            '"': '&quot;',
                                            "'": '&#39;',
                                        }}[character]));
                                    }},
                                    buildApplicationModelOptionsHtml(application) {{
                                        const selectedModel = application && application.model != null ? String(application.model).trim() : '';
                                        const placeholderLabel = application && application.loadingModels ? 'Carregando...' : 'Selecione...';
                                        const options = this.ensureSelectedOption(application ? application.modelOptions : [], selectedModel);
                                        const placeholderSelected = selectedModel ? '' : ' selected';
                                        const optionHtml = options.map((option) => {{
                                            const optionValue = String(option.id).trim();
                                            const selected = optionValue === selectedModel ? ' selected' : '';
                                            return `<option value="${{this.escapeSelectOptionValue(optionValue)}}"${{selected}}>${{this.escapeSelectOptionValue(option.label)}}</option>`;
                                        }});
                                        return [`<option value=""${{placeholderSelected}}>${{this.escapeSelectOptionValue(placeholderLabel)}}</option>`, ...optionHtml].join('');
                                    }},
                                    syncSelectElementValue(selectElement, selectedValue) {{
                                        this.$nextTick(() => {{
                                            if (!selectElement) return;
                                            const normalizedSelectedValue = selectedValue != null ? String(selectedValue).trim() : '';
                                            if (selectElement.value !== normalizedSelectedValue) {{
                                                selectElement.value = normalizedSelectedValue;
                                            }}
                                        }});
                                    }},
                                    syncApplicationEngineFromModel(index) {{
                                        const application = this.applications[index];
                                        if (!application) return;

                                        const detectedEngine = this.extractEngineFromModelName(this.getApplicationModelLabel(application));
                                        if (detectedEngine) {{
                                            application.engine = detectedEngine;
                                            application.engineOptions = this.buildEngineOptions(detectedEngine);
                                            application.engineLocked = true;
                                            return;
                                        }}

                                        application.engineOptions = this.buildEngineOptions(application.engine);
                                        application.engineLocked = false;
                                    }},
                                    async initializeApplications() {{
                                        await Promise.all(this.applications.map((_, index) => this.hydrateApplication(index)));
                                    }},
                                    async fetchCatalogOptions(url) {{
                                        const response = await fetch(url, {{ headers: {{ 'X-Requested-With': 'XMLHttpRequest' }} }});
                                        if (!response.ok) {{
                                            throw new Error('Falha ao carregar opções da FIPE.');
                                        }}
                                        return await response.json();
                                    }},
                                    normalizeCatalogOptions(options) {{
                                        if (!Array.isArray(options)) return [];
                                        return options
                                            .map((option) => ({{
                                                id: option && option.id != null ? String(option.id).trim() : '',
                                                label: option && option.label != null ? String(option.label).trim() : '',
                                            }}))
                                            .filter((option) => option.id || option.label)
                                            .map((option) => ({{
                                                id: option.id || option.label,
                                                label: option.label || option.id,
                                            }}));
                                    }},
                                    ensureSelectedOption(options, selectedValue) {{
                                        const normalizedOptions = this.normalizeCatalogOptions(options);
                                        const normalizedSelectedValue = selectedValue != null ? String(selectedValue).trim() : '';
                                        if (!normalizedSelectedValue) return normalizedOptions;
                                        const hasOption = normalizedOptions.some((option) => String(option.id) === normalizedSelectedValue);
                                        return hasOption ? normalizedOptions : [...normalizedOptions, {{ id: normalizedSelectedValue, label: normalizedSelectedValue }}];
                                    }},
                                    async hydrateApplication(index) {{
                                        const application = this.applications[index];
                                        if (!application) return;
                                        if (application.brand) {{
                                            await this.loadApplicationModels(index, {{ preserveModel: true, preserveFuel: true }});
                                        }}
                                        if (application.brand && application.model) {{
                                            await this.loadApplicationFuels(index, {{ preserveFuel: true }});
                                        }}
                                    }},
                                    async loadApplicationModels(index, {{ preserveModel = false, preserveFuel = false }} = {{}}) {{
                                        const application = this.applications[index];
                                        if (!application) return;

                                        if (!application.brand) {{
                                            application.modelOptions = [];
                                            application.engineOptions = this.buildEngineOptions('');
                                            application.fuelOptions = [];
                                            application.model = '';
                                            application.engine = '';
                                            application.engineLocked = false;
                                            application.fuel = '';
                                            application.fuelLocked = false;
                                            return;
                                        }}

                                        application.loadingModels = true;
                                        const selectedModel = preserveModel ? application.model : '';
                                        const selectedEngine = preserveModel ? application.engine : '';
                                        const selectedFuel = preserveFuel ? application.fuel : '';
                                        try {{
                                            let options = await this.fetchCatalogOptions(`/catalog/fipe/models/?brand=${{encodeURIComponent(application.brand)}}`);
                                            options = this.ensureSelectedOption(options, selectedModel);
                                            application.modelOptions = options;
                                            if (preserveModel) {{
                                                application.model = selectedModel;
                                                application.engine = selectedEngine;
                                                application.engineLocked = !!selectedEngine;
                                                this.$nextTick(() => {{
                                                    application.model = selectedModel;
                                                }});
                                            }} else {{
                                                application.model = '';
                                                application.engine = '';
                                                application.engineLocked = false;
                                            }}
                                            if (!preserveFuel) {{
                                                application.fuel = '';
                                                application.fuelLocked = false;
                                            }} else {{
                                                application.fuel = selectedFuel;
                                                application.fuelLocked = !!selectedFuel;
                                            }}
                                            if (!preserveModel || !selectedEngine) {{
                                                this.syncApplicationEngineFromModel(index);
                                            }}
                                            application.fuelOptions = [];
                                        }} catch (error) {{
                                            console.error('Erro ao carregar modelos da FIPE:', error);
                                            this.showToast('Nao foi possivel carregar os modelos da FIPE.', 'error');
                                        }} finally {{
                                            application.loadingModels = false;
                                        }}
                                    }},
                                    async loadApplicationFuels(index, {{ preserveFuel = false }} = {{}}) {{
                                        const application = this.applications[index];
                                        if (!application) return;

                                        if (!application.brand || !application.model) {{
                                            application.fuelOptions = [];
                                            application.fuel = '';
                                            application.fuelLocked = false;
                                            return;
                                        }}

                                        application.loadingFuels = true;
                                        try {{
                                            const selectedFuel = preserveFuel ? application.fuel : '';
                                            const payload = await this.fetchCatalogOptions(`/catalog/fipe/fuels/?brand=${{encodeURIComponent(application.brand)}}&model=${{encodeURIComponent(application.model)}}`);
                                            const rawFuelOptions = Array.isArray(payload.fuels) ? payload.fuels : [];
                                            let options;
                                            if (rawFuelOptions.length === 0 && !preserveFuel) {{
                                                options = Array.isArray(this.baseFuelOptions) ? [...this.baseFuelOptions] : [];
                                                application.fuel = '';
                                                application.fuelLocked = false;
                                            }} else if (rawFuelOptions.length === 0 && preserveFuel) {{
                                                options = this.ensureSelectedOption([], selectedFuel);
                                                application.fuel = selectedFuel;
                                                application.fuelLocked = !!selectedFuel;
                                            }} else {{
                                                options = this.ensureSelectedOption(rawFuelOptions, preserveFuel ? selectedFuel : '');
                                                if (!preserveFuel) {{
                                                    if (options.length === 1) {{
                                                        application.fuel = options[0].id;
                                                        application.fuelLocked = true;
                                                    }} else {{
                                                        application.fuel = '';
                                                        application.fuelLocked = false;
                                                    }}
                                                }} else {{
                                                    application.fuel = selectedFuel;
                                                    application.fuelLocked = !!selectedFuel;
                                                }}
                                            }}
                                            application.fuelOptions = options;
                                            if (!preserveFuel && payload.year_start != null && payload.year_end != null) {{
                                                application.year_start = String(payload.year_start);
                                                application.year_end = String(payload.year_end);
                                            }}
                                        }} catch (error) {{
                                            console.error('Erro ao carregar combustíveis da FIPE:', error);
                                            this.showToast('Nao foi possivel carregar os combustíveis da FIPE.', 'error');
                                        }} finally {{
                                            application.loadingFuels = false;
                                        }}
                                    }},

                                    buildSearchUrl(baseUrl, paramName, query) {{
                                        const params = new URLSearchParams();
                                        const normalizedQuery = (query || '').toString().trim();
                                        if (normalizedQuery) {{
                                            params.set(paramName, normalizedQuery);
                                        }}
                                        const queryString = params.toString();
                                        return queryString ? `${{baseUrl}}?${{queryString}}` : baseUrl;
                                    }},
                                    reloadProductSuggestions(query = '') {{
                                        if (!window.htmx) return;
                                        window.htmx.ajax('GET', this.buildSearchUrl('{product_search_url}', 'product_search', query), {{
                                            target: '#kit-product-items',
                                            swap: 'innerHTML',
                                        }});
                                    }},
                                    reloadServiceSuggestions(query = '') {{
                                        if (!window.htmx) return;
                                        window.htmx.ajax('GET', this.buildSearchUrl('{service_search_url}', 'service_search', query), {{
                                            target: '#kit-service-items',
                                            swap: 'innerHTML',
                                        }});
                                    }},
                                    resetProductSearch() {{
                                        const input = document.getElementById('kit-product-search-input');
                                        if (input) input.value = '';
                                    }},
                                    resetServiceSearch() {{
                                        const input = document.getElementById('kit-service-search-input');
                                        if (input) input.value = '';
                                    }},
                                    buildEmptyServiceEditForm() {{
                                        return {{
                                            id: null,
                                            name: '',
                                            duration: '',
                                            sellByDuration: '',
                                            sell: '',
                                            cost: '',
                                            originalDuration: '',
                                            originalSellByDuration: '',
                                            originalSell: '',
                                            originalCost: '',
                                            originalManualCost: '',
                                        }};
                                    }},
                                    setEditModalMessage(message) {{
                                        const content = document.getElementById('edit-modal-content');
                                        if (!content) return;
                                        content.innerHTML = `<div class="p-6 text-sm text-base-content/70">${{message}}</div>`;
                                    }},
                                    resetEditModalContent() {{
                                        this.setEditModalMessage('Selecione um item para editar.');
                                    }},
                                    resetServiceEditForm() {{
                                        this.serviceEditForm = this.buildEmptyServiceEditForm();
                                    }},
                                    openProductEditModal(productId) {{
                                        this.setEditModalMessage('Carregando produto...');
                                        const modalToggle = document.getElementById('edit-item-modal');
                                        if (modalToggle) modalToggle.checked = true;
                                        if (!window.htmx) return;
                                        window.htmx.ajax('GET', `/catalog/edit_product_modal_form/${{productId}}/`, {{
                                            target: '#edit-modal-content',
                                            swap: 'innerHTML',
                                        }});
                                    }},
                                    openServiceEditModal(serviceId) {{
                                        const service = this.selectedServices.find(item => String(item.id) === String(serviceId));
                                        if (!service) return;
                                        this.serviceEditForm = {{
                                            id: service.id,
                                            name: service.name,
                                            duration: this.formatDurationForDisplay(service.duration),
                                            sellByDuration: service.sell_by_duration,
                                            sell: service.sell_inserted,
                                            cost: this.resolvedServiceCostDisplay(service),
                                            originalDuration: this.normalizeDurationForPost(service.duration),
                                            originalSellByDuration: service.sell_by_duration,
                                            originalSell: service.sell_inserted,
                                            originalCost: this.resolvedServiceCostDisplay(service),
                                            originalManualCost: service.cost_manual || '',
                                        }};
                                        const modalToggle = document.getElementById('edit-kit-service-modal');
                                        if (modalToggle) modalToggle.checked = true;
                                    }},
                                    getCsrfToken() {{
                                        const csrfField = document.querySelector('input[name="csrfmiddlewaretoken"]');
                                        return csrfField ? csrfField.value : '';
                                    }},
                                    async persistEditedService(service) {{
                                        if (!this.kitId || !service) return;

                                        const response = await fetch(`/catalog/kits/${{this.kitId}}/services/${{service.id}}/local-update/`, {{
                                            method: 'POST',
                                            headers: {{
                                                'Content-Type': 'application/json',
                                                'X-CSRFToken': this.getCsrfToken(),
                                                'X-Requested-With': 'XMLHttpRequest',
                                            }},
                                            credentials: 'same-origin',
                                            body: JSON.stringify({{
                                                qty: service.qty,
                                                duration: this.normalizeDurationForPost(service.duration),
                                                cost: this.serviceManualCostForPost(service),
                                                sell_by_duration: this.normalizeMoneyForPost(service.sell_by_duration),
                                                sell: this.normalizeMoneyForPost(service.sell_inserted),
                                                service_pricing_mode: this.servicePricingMode,
                                            }}),
                                        }});

                                        const payload = await response.json().catch(() => ({{}}));
                                        if (!response.ok) {{
                                            throw new Error(payload.error || 'Falha ao salvar alteracoes do serviço do kit.');
                                        }}
                                    }},
                                    async syncSelectedServicesState() {{
                                        if (!this.kitId) return;

                                        const response = await fetch(`/catalog/kits/${{this.kitId}}/services/sync/`, {{
                                            method: 'POST',
                                            headers: {{
                                                'Content-Type': 'application/json',
                                                'X-CSRFToken': this.getCsrfToken(),
                                                'X-Requested-With': 'XMLHttpRequest',
                                            }},
                                            credentials: 'same-origin',
                                            body: JSON.stringify({{
                                                service_pricing_mode: this.servicePricingMode,
                                                services: this.selectedServices.map((service) => ({{
                                                    id: service.id,
                                                    qty: this.resolveItemQuantity(service),
                                                    duration: this.normalizeDurationForPost(service.duration),
                                                    cost: this.serviceManualCostForPost(service),
                                                    sell_by_duration: this.normalizeMoneyForPost(service.sell_by_duration),
                                                    sell: this.normalizeMoneyForPost(service.sell_inserted),
                                                }})),
                                            }}),
                                        }});

                                        const payload = await response.json().catch(() => ({{}}));
                                        if (!response.ok) {{
                                            throw new Error(payload.error || 'Falha ao sincronizar serviços do kit.');
                                        }}
                                    }},
                                    showToast(message, type = 'warning') {{
                                        document.body.dispatchEvent(new CustomEvent('showToast', {{
                                            detail: {{ message, type }},
                                        }}));
                                    }},
                                    applyUpdatedService(payload) {{
                                        if (!payload || payload.id === undefined || payload.id === null) return;
                                        const service = this.selectedServices.find(item => String(item.id) === String(payload.id));
                                        if (!service) return;

                                        service.name = payload.name ?? service.name;
                                        service.cost_manual = payload.cost ?? service.cost_manual;
                                        service.sell_inserted = payload.sell ?? service.sell_inserted;
                                        service.duration = payload.duration ?? service.duration;

                                        this.refreshTotalDurationDisplay();
                                        this.refreshServicePricingFromDurations().catch((error) => {{
                                            console.error('Error refreshing duration-based pricing:', error);
                                        }});
                                        this.resetEditModalContent();

                                        const modalToggle = document.getElementById('edit-item-modal');
                                        if (modalToggle) modalToggle.checked = false;
                                    }},
                                    handleServiceEditDurationInput(event) {{
                                        const formatted = this.normalizeDistributionTime(event.target.value);
                                        this.serviceEditForm.duration = formatted;
                                        event.target.value = formatted;
                                    }},
                                    handleServiceEditMoneyInput(event, fieldName) {{
                                        const formatted = this.normalizeMoneyInput(event.target.value);
                                        this.serviceEditForm[fieldName] = formatted;
                                        event.target.value = formatted;
                                    }},
                                    serviceHasManualCost(service) {{
                                        return !!((service.cost_manual || '').toString().trim());
                                    }},
                                    resolvedServiceCostDisplay(service) {{
                                        return this.serviceHasManualCost(service) ? service.cost_manual : service.cost_by_duration;
                                    }},
                                    serviceManualCostForPost(service) {{
                                        return this.serviceHasManualCost(service) ? this.normalizeMoneyForPost(service.cost_manual) : '';
                                    }},
                                    async applyServiceEdit() {{
                                        const service = this.selectedServices.find(item => String(item.id) === String(this.serviceEditForm.id));
                                        if (!service) return;

                                        const normalizedDuration = this.normalizeDurationForPost(this.serviceEditForm.duration);
                                        if (!normalizedDuration || normalizedDuration === '00:00:00') {{
                                            window.alert('Informe uma duração válida no formato HH:MM.');
                                            return;
                                        }}

                                        const normalizedSellByDuration = this.normalizeMoneyInput(this.serviceEditForm.sellByDuration) || service.sell_by_duration;
                                        const normalizedSell = this.normalizeMoneyInput(this.serviceEditForm.sell) || service.sell_inserted;
                                        const normalizedCost = this.normalizeMoneyInput(this.serviceEditForm.cost);
                                        const durationChanged = normalizedDuration !== this.serviceEditForm.originalDuration;
                                        const durationSellChanged = normalizedSellByDuration !== this.serviceEditForm.originalSellByDuration;

                                        service.duration = normalizedDuration;
                                        service.sell_by_duration = normalizedSellByDuration;
                                        service.sell_inserted = normalizedSell;

                                        if (durationChanged) {{
                                            service.cost_manual = normalizedCost !== this.serviceEditForm.originalCost ? normalizedCost : '';
                                        }} else if (normalizedCost !== this.serviceEditForm.originalCost) {{
                                            service.cost_manual = normalizedCost;
                                        }}

                                        this.refreshTotalDurationDisplay();

                                        if (durationChanged && !durationSellChanged) {{
                                            try {{
                                                await this.refreshServicePricingFromDurations();
                                                this.serviceEditForm.sellByDuration = service.sell_by_duration;
                                            }} catch (error) {{
                                                console.error('Error refreshing service pricing after local edit:', error);
                                                this.showToast('Nao foi possivel recalcular custo e valor por duração.', 'error');
                                            }}
                                        }}

                                        try {{
                                            await this.persistEditedService(service);
                                        }} catch (error) {{
                                            console.error('Error persisting local service edit:', error);
                                            this.showToast('Nao foi possivel salvar as alteracoes do serviço no kit.', 'error');
                                            return;
                                        }}

                                        this.resetServiceEditForm();
                                        const modalToggle = document.getElementById('edit-kit-service-modal');
                                        if (modalToggle) modalToggle.checked = false;
                                    }},
                                    async refreshServicePricingFromDurations() {{
                                        if (this.selectedServices.length === 0) return;

                                        const response = await fetch('{service_bulk_pricing_url}', {{
                                            method: 'POST',
                                            headers: {{
                                                'Content-Type': 'application/json',
                                                'X-CSRFToken': this.getCsrfToken(),
                                                'X-Requested-With': 'XMLHttpRequest',
                                            }},
                                            credentials: 'same-origin',
                                            body: JSON.stringify({{
                                                services: this.selectedServices.map((service) => ({{
                                                    id: service.id,
                                                    duration: this.normalizeDurationForPost(service.duration),
                                                }})),
                                            }}),
                                        }});

                                        const payload = await response.json().catch(() => ({{}}));
                                        if (!response.ok) {{
                                            throw new Error(payload.error || 'Falha ao recalcular valores de venda dos serviços.');
                                        }}

                                        if (payload.workshop_cost_missing) {{
                                            this.showToast('Configure os custos da oficina para recalcular custo e valor por duração.', 'warning');
                                            return;
                                        }}

                                        const pricingMap = new Map((payload.services || []).map((service) => [String(service.id), service]));
                                        this.selectedServices.forEach((service) => {{
                                            const recalculated = pricingMap.get(String(service.id));
                                            if (recalculated) {{
                                                if (recalculated.cost) service.cost_by_duration = recalculated.cost;
                                                if (recalculated.sell) service.sell_by_duration = recalculated.sell;
                                            }}
                                        }});
                                    }},

                                    parseDurationToSeconds(value) {{
                                        const normalized = this.normalizeDurationForPost(value);
                                        const parts = normalized.split(':');
                                        if (parts.length !== 3) return 0;
                                        const hours = Number.parseInt(parts[0], 10);
                                        const minutes = Number.parseInt(parts[1], 10);
                                        const seconds = Number.parseInt(parts[2], 10);
                                        if (Number.isNaN(hours) || Number.isNaN(minutes) || Number.isNaN(seconds)) return 0;
                                        return (hours * 3600) + (minutes * 60) + seconds;
                                    }},
                                    formatSecondsToHHMM(totalSeconds) {{
                                        const safeSeconds = Math.max(0, Number.parseInt(totalSeconds, 10) || 0);
                                        const hours = Math.floor(safeSeconds / 3600);
                                        const minutes = Math.floor((safeSeconds % 3600) / 60);
                                        return `${{String(hours).padStart(2, '0')}}:${{String(minutes).padStart(2, '0')}}`;
                                    }},
                                    parseMoneyValue(value) {{
                                        const normalized = (value || '').toString().trim();
                                        if (!normalized || normalized === '-') return 0;

                                        const sanitized = normalized.replace(/[^0-9,.-]/g, '');
                                        if (!sanitized || sanitized === '-' || sanitized === ',' || sanitized === '.') return 0;

                                        const decimalValue = sanitized.includes(',') ? sanitized.split('.').join('').replace(',', '.') : sanitized.replace(/,/g, '');
                                        const parsed = Number.parseFloat(decimalValue);
                                        return Number.isNaN(parsed) ? 0 : parsed;
                                    }},
                                    formatCurrency(value) {{
                                        const parsed = typeof value === 'number' ? value : Number.parseFloat(value);
                                        const safeValue = Number.isNaN(parsed) ? 0 : parsed;
                                        return new Intl.NumberFormat('pt-BR', {{
                                            style: 'currency',
                                            currency: 'BRL',
                                        }}).format(safeValue);
                                    }},
                                    parseMoneyToCents(value) {{
                                        const digits = (value || '').toString().replace(/[^0-9]/g, '');
                                        if (!digits) return null;
                                        const parsed = Number.parseInt(digits, 10);
                                        return Number.isNaN(parsed) ? null : parsed;
                                    }},
                                    normalizeMoneyInput(value) {{
                                        const cents = this.parseMoneyToCents(value);
                                        if (cents === null) return '';
                                        return this.formatCurrency(cents / 100);
                                    }},
                                    normalizeMoneyForPost(value) {{
                                        return this.parseMoneyValue(value).toFixed(2);
                                    }},
                                    async setServicePricingMode(mode) {{
                                        if (mode !== 'by_duration' && mode !== 'inserted_value') return;
                                        const previousMode = this.servicePricingMode;
                                        this.servicePricingMode = mode;
                                        try {{
                                            await this.syncSelectedServicesState();
                                        }} catch (error) {{
                                            this.servicePricingMode = previousMode;
                                            console.error('Error syncing service pricing mode:', error);
                                            this.showToast('Nao foi possivel salvar o modo de precificação do kit.', 'error');
                                        }}
                                    }},
                                    servicePricingColumnClasses(mode, section = 'body') {{
                                        const isActive = this.servicePricingMode === mode;
                                        const baseClasses = 'transition-all duration-200';
                                        const inactiveClasses = 'bg-transparent shadow-[inset_1px_0_0_0_color-mix(in_oklab,var(--color-base-300)_100%,transparent),inset_-1px_0_0_0_color-mix(in_oklab,var(--color-base-300)_100%,transparent),inset_0_-1px_0_0_0_color-mix(in_oklab,var(--color-base-300)_100%,transparent)]';
                                        const activeClassesBySection = {{
                                            header: 'bg-success/10 shadow-[inset_1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent),inset_-1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent),inset_0_-1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent)]',
                                            body: 'bg-success/10 shadow-[inset_1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent),inset_-1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent),inset_0_-1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent)]',
                                            footer: 'bg-success/10 shadow-[inset_1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent),inset_-1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent),inset_0_-1px_0_0_0_color-mix(in_oklab,var(--color-success)_45%,transparent)]',
                                        }};
                                        return `${{baseClasses}} ${{isActive ? activeClassesBySection[section] || activeClassesBySection.body : inactiveClasses}}`;
                                    }},
                                    resolveItemQuantity(item) {{
                                        const qty = Number.parseInt(item.qty, 10);
                                        if (Number.isNaN(qty) || qty < 0) return 0;
                                        return qty;
                                    }},
                                    calculateItemsTotal(items, fieldName) {{
                                        return items.reduce((sum, item) => {{
                                            return sum + (this.parseMoneyValue(item[fieldName]) * this.resolveItemQuantity(item));
                                        }}, 0);
                                    }},
                                    productsCostTotalDisplay() {{
                                        return this.formatCurrency(this.calculateItemsTotal(this.selectedProducts, 'cost'));
                                    }},
                                    productsSellTotalDisplay() {{
                                        return this.formatCurrency(this.calculateItemsTotal(this.selectedProducts, 'sell'));
                                    }},
                                    servicesCostTotalDisplay() {{
                                        return this.formatCurrency(this.selectedServices.reduce((sum, service) => {{
                                            return sum + (this.parseMoneyValue(this.resolvedServiceCostDisplay(service)) * this.resolveItemQuantity(service));
                                        }}, 0));
                                    }},
                                    servicesSellByDurationTotalDisplay() {{
                                        return this.formatCurrency(this.calculateItemsTotal(this.selectedServices, 'sell_by_duration'));
                                    }},
                                    servicesSellInsertedTotalDisplay() {{
                                        return this.formatCurrency(this.calculateItemsTotal(this.selectedServices, 'sell_inserted'));
                                    }},
                                    currentKitSellTotalDisplay() {{
                                        const productsTotal = this.calculateItemsTotal(this.selectedProducts, 'sell');
                                        const servicesTotal = this.servicePricingMode === 'by_duration'
                                            ? this.calculateItemsTotal(this.selectedServices, 'sell_by_duration')
                                            : this.calculateItemsTotal(this.selectedServices, 'sell_inserted');
                                        return this.formatCurrency(productsTotal + servicesTotal);
                                    }},
                                    refreshTotalDurationDisplay() {{
                                        const totalSeconds = this.selectedServices.reduce((sum, service) => {{
                                            return sum + this.parseDurationToSeconds(service.duration);
                                        }}, 0);
                                        this.totalDurationDisplay = this.formatSecondsToHHMM(totalSeconds);
                                    }},
                                    buildEmptyApplication() {{
                                        return this.normalizeApplicationState({{
                                            brand: '',
                                            model: '',
                                            engine: '',
                                            fuel: '',
                                            year_start: '',
                                            year_end: '',
                                        }});
                                    }},
                                    addApplication() {{
                                        this.applications.push(this.buildEmptyApplication());
                                    }},
                                    removeApplication(index) {{
                                        this.applications.splice(index, 1);
                                    }},
                                    async onApplicationBrandChange(index) {{
                                        await this.loadApplicationModels(index);
                                    }},
                                    async onApplicationModelChange(index) {{
                                        this.syncApplicationEngineFromModel(index);
                                        await this.loadApplicationFuels(index);
                                    }},
                                    formatApplicationPreview(application) {{
                                        const vehicle = [application.brand, application.model].filter(Boolean).join(' ').trim();
                                        const powertrain = [application.engine, application.fuel].filter(Boolean).join(' ').trim();
                                        const yearStart = (application.year_start || '').toString().trim();
                                        const yearEnd = (application.year_end || '').toString().trim();
                                        const years = yearStart && yearEnd ? `${{yearStart}}${{yearStart === yearEnd ? '' : ` a ${{yearEnd}}`}}` : '';
                                        const parts = [vehicle, powertrain, years].filter(Boolean);
                                        return parts.length > 0 ? parts.join(' - ') : 'Aplicação em branco';
                                    }},

                                    openProductsModal() {{
                                        this.modalSelectedProducts = this.selectedProducts.map(p => ({{
                                            id: p.id,
                                            name: p.name,
                                            cost: p.cost,
                                            sell: p.sell,
                                            qty: p.qty,
                                        }}));
                                        this.resetProductSearch();
                                        this.reloadProductSuggestions();
                                    }},
                                    openServicesModal() {{
                                        this.modalSelectedServices = this.selectedServices.map(s => ({{
                                            id: s.id,
                                            name: s.name,
                                            cost_by_duration: s.cost_by_duration,
                                            cost_manual: s.cost_manual || '',
                                            sell_by_duration: s.sell_by_duration,
                                            sell_inserted: s.sell_inserted,
                                            qty: s.qty,
                                            duration: s.duration || '00:00:00',
                                        }}));
                                        this.resetServiceSearch();
                                        this.reloadServiceSuggestions();
                                    }},
                                    openDistributeTimeModal() {{
                                        this.distributionTotalTime = '';
                                    }},
                                    openDistributeServiceSellModal() {{
                                        this.distributionTotalServiceSell = '';
                                    }},

                                    toggleModalProduct(item) {{
                                        const idx = this.modalSelectedProducts.findIndex(i => i.id == item.id);
                                        if (idx >= 0) {{
                                            this.modalSelectedProducts.splice(idx, 1);
                                        }} else {{
                                            this.modalSelectedProducts.push(item);
                                        }}
                                    }},
                                    toggleModalService(item) {{
                                        const idx = this.modalSelectedServices.findIndex(i => i.id == item.id);
                                        if (idx >= 0) {{
                                            this.modalSelectedServices.splice(idx, 1);
                                        }} else {{
                                            this.modalSelectedServices.push(item);
                                        }}
                                    }},

                                    addProduct(item) {{
                                        if (!this.selectedProducts.find(i => i.id == item.id)) {{
                                            this.selectedProducts.push({{
                                                ...item,
                                                qty: 1,
                                            }});
                                        }}
                                    }},
                                    addService(item) {{
                                        if (!this.selectedServices.find(i => i.id == item.id)) {{
                                            this.selectedServices.push({{
                                                id: item.id,
                                                name: item.name,
                                                cost_by_duration: '-',
                                                cost_manual: '',
                                                sell_by_duration: '-',
                                                sell_inserted: item.sell || this.formatCurrency(0),
                                                qty: 1,
                                                duration: this.normalizeDurationForPost(item.duration || '00:00:00'),
                                            }});
                                            this.refreshTotalDurationDisplay();
                                        }}
                                    }},
                                    distributionTotalTime: '',
                                    distributionTotalServiceSell: '',

                                    parseTotalMinutes(value) {{
                                        const normalized = this.normalizeDistributionTime(value);
                                        const match = normalized.match(/^([0-9]{{2}}):([0-9]{{2}})$/);
                                        if (!match) return null;
                                        const hours = parseInt(match[1], 10);
                                        const minutes = parseInt(match[2], 10);
                                        if (Number.isNaN(hours) || Number.isNaN(minutes) || minutes > 59) return null;
                                        return (hours * 60) + minutes;
                                    }},
                                    normalizeDistributionTime(value) {{
                                        const digits = (value || '').toString().replace(/[^0-9]/g, '').slice(0, 4);
                                        if (!digits) return '';
                                        if (digits.length <= 2) return digits;
                                        const hh = digits.slice(0, 2);
                                        const mm = digits.slice(2, 4);
                                        return `${{hh}}:${{mm}}`;
                                    }},
                                    handleDistributionTimeInput(event) {{
                                        const formatted = this.normalizeDistributionTime(event.target.value);
                                        this.distributionTotalTime = formatted;
                                        event.target.value = formatted;
                                    }},
                                    handleDistributionServiceSellInput(event) {{
                                        const formatted = this.normalizeMoneyInput(event.target.value);
                                        this.distributionTotalServiceSell = formatted;
                                        event.target.value = formatted;
                                    }},
                                    normalizeDurationForPost(value) {{
                                        const raw = (value || '').toString().trim();
                                        if (!raw) return '00:00:00';
                                        const parts = raw.split(':').map(p => p.trim());
                                        if (parts.length === 3) {{
                                            const h = parseInt(parts[0], 10);
                                            const m = parseInt(parts[1], 10);
                                            const s = parseInt(parts[2], 10);
                                            if (Number.isNaN(h) || Number.isNaN(m) || Number.isNaN(s)) return '00:00:00';
                                            return `${{String(Math.max(0, h)).padStart(2, '0')}}:${{String(Math.min(59, Math.max(0, m))).padStart(2, '0')}}:${{String(Math.min(59, Math.max(0, s))).padStart(2, '0')}}`;
                                        }}
                                        if (parts.length === 2) {{
                                            const h = parseInt(parts[0], 10);
                                            const m = parseInt(parts[1], 10);
                                            if (Number.isNaN(h) || Number.isNaN(m)) return '00:00:00';
                                            return `${{String(Math.max(0, h)).padStart(2, '0')}}:${{String(Math.min(59, Math.max(0, m))).padStart(2, '0')}}:00`;
                                        }}
                                        return '00:00:00';
                                    }},
                                    formatDurationForDisplay(value) {{
                                        return this.normalizeDurationForPost(value).slice(0, 5);
                                    }},
                                    async applyTimeDistribution() {{
                                        if (this.selectedServices.length === 0) {{
                                            window.alert('Adicione ao menos um serviço para distribuir tempos.');
                                            return;
                                        }}
                                        const totalMinutes = this.parseTotalMinutes(this.distributionTotalTime);
                                        if (totalMinutes === null) {{
                                            window.alert('Informe um tempo total válido no formato HH:MM.');
                                            return;
                                        }}

                                        const withWeights = this.selectedServices.map((service, index) => ({{
                                            index,
                                            weight: Math.max(1, Number.parseInt(service.qty, 10) || 1),
                                            fraction: 0,
                                            assigned: 0,
                                        }}));
                                        const totalWeight = withWeights.reduce((sum, item) => sum + item.weight, 0);

                                        withWeights.forEach((item) => {{
                                            const exact = (totalMinutes * item.weight) / totalWeight;
                                            item.assigned = Math.floor(exact);
                                            item.fraction = exact - item.assigned;
                                        }});

                                        let assignedTotal = withWeights.reduce((sum, item) => sum + item.assigned, 0);
                                        let remainder = totalMinutes - assignedTotal;

                                        withWeights
                                            .slice()
                                            .sort((a, b) => b.fraction - a.fraction)
                                            .forEach((item) => {{
                                                if (remainder > 0) {{
                                                    item.assigned += 1;
                                                    remainder -= 1;
                                                }}
                                            }});

                                        withWeights.forEach((item) => {{
                                            const hours = Math.floor(item.assigned / 60);
                                            const minutes = item.assigned % 60;
                                            this.selectedServices[item.index].duration = `${{String(hours).padStart(2, '0')}}:${{String(minutes).padStart(2, '0')}}:00`;
                                            this.selectedServices[item.index].cost_manual = '';
                                        }});

                                        try {{
                                            await this.refreshServicePricingFromDurations();
                                            await this.syncSelectedServicesState();
                                        }} catch (error) {{
                                            console.error('Error recalculating kit service pricing:', error);
                                            this.showToast('Nao foi possivel recalcular custo e valor por duração.', 'error');
                                        }}

                                        this.refreshTotalDurationDisplay();

                                        const modalToggle = document.getElementById('kit-distribute-time-modal');
                                        if (modalToggle) modalToggle.checked = false;
                                    }},
                                    async applyServiceSellDistribution() {{
                                        if (this.selectedServices.length === 0) {{
                                            window.alert('Adicione ao menos um serviço para distribuir valores.');
                                            return;
                                        }}

                                        const totalCents = this.parseMoneyToCents(this.distributionTotalServiceSell);
                                        if (totalCents === null) {{
                                            window.alert('Informe um valor total de venda válido para os serviços.');
                                            return;
                                        }}

                                        const weightedServices = this.selectedServices
                                            .map((service, index) => ({{
                                                index,
                                                weight: this.resolveItemQuantity(service),
                                            }}))
                                            .filter((item) => item.weight > 0);

                                        if (weightedServices.length === 0) {{
                                            window.alert('Informe uma quantidade válida para os serviços selecionados.');
                                            return;
                                        }}

                                        const totalWeight = weightedServices.reduce((sum, item) => sum + item.weight, 0);
                                        const baseUnitCents = Math.floor(totalCents / totalWeight);
                                        const anchor = weightedServices.slice().sort((a, b) => a.weight - b.weight || a.index - b.index)[0];
                                        const nonAnchorWeight = totalWeight - anchor.weight;
                                        const anchorUnitCents = Math.max(0, Math.round((totalCents - (baseUnitCents * nonAnchorWeight)) / anchor.weight));

                                        weightedServices.forEach((item) => {{
                                            const unitCents = item.index === anchor.index ? anchorUnitCents : baseUnitCents;
                                            this.selectedServices[item.index].sell_inserted = this.formatCurrency(unitCents / 100);
                                        }});

                                        this.distributionTotalServiceSell = this.formatCurrency(this.calculateItemsTotal(this.selectedServices, 'sell_inserted'));

                                        try {{
                                            await this.syncSelectedServicesState();
                                        }} catch (error) {{
                                            console.error('Error syncing distributed service selling values:', error);
                                            this.showToast('Nao foi possivel salvar os valores de venda dos serviços.', 'error');
                                            return;
                                        }}

                                        const modalToggle = document.getElementById('kit-distribute-service-sell-modal');
                                        if (modalToggle) modalToggle.checked = false;
                                    }},

                                    applySelectedProducts() {{
                                        this.modalSelectedProducts.forEach(p => this.addProduct(p));

                                        const modalToggle = document.getElementById('kit-products-modal');
                                        if (modalToggle) modalToggle.checked = false;

                                        this.resetProductSearch();
                                        this.reloadProductSuggestions();
                                    }},
                                    async applySelectedServices() {{
                                        this.modalSelectedServices.forEach(s => this.addService(s));

                                        try {{
                                            await this.refreshServicePricingFromDurations();
                                            await this.syncSelectedServicesState();
                                        }} catch (error) {{
                                            console.error('Error recalculating pricing after selecting services:', error);
                                            this.showToast('Nao foi possivel salvar os serviços selecionados no kit.', 'error');
                                        }}

                                        const modalToggle = document.getElementById('kit-services-modal');
                                        if (modalToggle) modalToggle.checked = false;

                                        this.resetServiceSearch();
                                        this.reloadServiceSuggestions();
                                    }},
                                    async handleServiceQuantityChange(index, event) {{
                                        const parsedQty = Math.max(1, Number.parseInt(event.target.value, 10) || 1);
                                        this.selectedServices[index].qty = parsedQty;
                                        event.target.value = parsedQty;
                                        try {{
                                            await this.syncSelectedServicesState();
                                        }} catch (error) {{
                                            console.error('Error syncing service quantity:', error);
                                            this.showToast('Nao foi possivel salvar a quantidade do serviço no kit.', 'error');
                                        }}
                                    }},
                                    removeProduct(index) {{ this.selectedProducts.splice(index, 1); }},
                                    async removeService(index) {{
                                        this.selectedServices.splice(index, 1);
                                        this.refreshTotalDurationDisplay();
                                        try {{
                                            await this.syncSelectedServicesState();
                                        }} catch (error) {{
                                            console.error('Error removing service from kit sync:', error);
                                            this.showToast('Nao foi possivel remover o serviço do kit.', 'error');
                                        }}
                                    }},
                                }}
                            }}
                        </script>
                        
                        """
                    ),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                ),
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean(self):
        cleaned_data = cast(dict[str, Any], super().clean() or {})

        product_ids = [pid for pid in self._getlist_from_data("kit_products") if pid and pid.isdigit()]
        service_ids = [sid for sid in self._getlist_from_data("kit_services") if sid and sid.isdigit()]

        seen = set()
        unique_product_ids = []
        for pid in product_ids:
            if pid not in seen:
                unique_product_ids.append(pid)
                seen.add(pid)

        seen = set()
        unique_service_ids = []
        for sid in service_ids:
            if sid not in seen:
                unique_service_ids.append(sid)
                seen.add(sid)

        if len(unique_product_ids) != len(product_ids):
            logger.warning(
                "Produtos duplicados detectados no envio de kit",
                extra={"kit_id": self.instance.pk, "product_ids": product_ids},
            )
            self.add_error(None, "Existem produtos repetidos no kit.")
        if len(unique_service_ids) != len(service_ids):
            logger.warning(
                "Servicos duplicados detectados no envio de kit",
                extra={"kit_id": self.instance.pk, "service_ids": service_ids},
            )
            self.add_error(None, "Existem serviços repetidos no kit.")

        cleaned_data["_kit_products_ids"] = unique_product_ids
        cleaned_data["_kit_services_ids"] = unique_service_ids

        product_qty: dict[str, int] = {}
        for pid in unique_product_ids:
            raw = self.data.get(f"kit_product_qty_{pid}", "1")
            try:
                qty = int(raw)
            except (TypeError, ValueError):
                qty = 0
            if qty < 1:
                logger.warning(
                    "Quantidade invalida para produto no kit",
                    extra={"kit_id": self.instance.pk, "product_id": pid, "raw_quantity": raw},
                )
                self.add_error(None, "Quantidade inválida para produto.")
            product_qty[pid] = qty if qty >= 1 else 1

        service_qty: dict[str, int] = {}
        service_duration: dict[str, timedelta] = {}
        service_cost: dict[str, Decimal | None] = {}
        service_sell_by_duration: dict[str, Decimal | None] = {}
        service_sell: dict[str, Decimal | None] = {}
        for sid in unique_service_ids:
            raw = self.data.get(f"kit_service_qty_{sid}", "1")
            try:
                qty = int(raw)
            except (TypeError, ValueError):
                qty = 0
            if qty < 1:
                logger.warning(
                    "Quantidade invalida para servico no kit",
                    extra={"kit_id": self.instance.pk, "service_id": sid, "raw_quantity": raw},
                )
                self.add_error(None, "Quantidade inválida para serviço.")
            service_qty[sid] = qty if qty >= 1 else 1

            raw_duration = str(self.data.get(f"kit_service_duration_{sid}", "") or "").strip()
            duration_value = self._parse_duration_value(raw_duration)
            if duration_value is None:
                logger.warning(
                    "Duracao invalida para servico no kit",
                    extra={"kit_id": self.instance.pk, "service_id": sid, "raw_duration": raw_duration},
                )
                self.add_error(None, "Duração inválida para serviço.")
                duration_value = timedelta()
            service_duration[sid] = duration_value

            raw_cost = str(self.data.get(f"kit_service_cost_{sid}", "") or "").strip()
            cost_value = self._parse_money_value(raw_cost)
            if raw_cost and cost_value is None:
                logger.warning(
                    "Valor de custo invalido para servico no kit",
                    extra={"kit_id": self.instance.pk, "service_id": sid, "raw_cost_price": raw_cost},
                )
                self.add_error(None, "Valor de custo inválido para serviço.")
            service_cost[sid] = cost_value

            raw_sell_by_duration = str(self.data.get(f"kit_service_sell_by_duration_{sid}", "") or "").strip()
            sell_by_duration_value = self._parse_money_value(raw_sell_by_duration)
            if raw_sell_by_duration and sell_by_duration_value is None:
                logger.warning(
                    "Valor de venda por tempo invalido para servico no kit",
                    extra={"kit_id": self.instance.pk, "service_id": sid, "raw_duration_sell_price": raw_sell_by_duration},
                )
                self.add_error(None, "Valor de venda por tempo inválido para serviço.")
            service_sell_by_duration[sid] = sell_by_duration_value

            raw_sell = str(self.data.get(f"kit_service_sell_{sid}", "") or "").strip()
            sell_value = self._parse_money_value(raw_sell)
            if raw_sell and sell_value is None:
                logger.warning(
                    "Valor de venda invalido para servico no kit",
                    extra={"kit_id": self.instance.pk, "service_id": sid, "raw_selling_price": raw_sell},
                )
                self.add_error(None, "Valor de venda inválido para serviço.")
            service_sell[sid] = sell_value

        cleaned_data["_kit_products_qty"] = product_qty
        cleaned_data["_kit_services_qty"] = service_qty
        cleaned_data["_kit_services_duration"] = service_duration
        cleaned_data["_kit_services_cost"] = service_cost
        cleaned_data["_kit_services_sell_by_duration"] = service_sell_by_duration
        cleaned_data["_kit_services_sell"] = service_sell

        raw_service_pricing_mode = str(self.data.get("kit_service_pricing_mode", "") or "").strip()
        valid_pricing_modes = {choice[0] for choice in Kit.ServicePricingMode.choices}
        if not raw_service_pricing_mode:
            raw_service_pricing_mode = self.instance.service_pricing_mode if self.instance.pk else Kit.ServicePricingMode.BY_DURATION
        elif raw_service_pricing_mode not in valid_pricing_modes:
            logger.warning(
                "Modo de precificacao de servicos invalido no kit",
                extra={"kit_id": self.instance.pk, "raw_service_pricing_mode": raw_service_pricing_mode},
            )
            raw_service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        cleaned_data["_kit_service_pricing_mode"] = raw_service_pricing_mode

        raw_applications = self._extract_application_rows_from_post()
        normalized_applications: list[dict[str, int | str]] = []
        seen_applications: set[tuple[str, str, str, str, int, int]] = set()
        required_application_fields = {
            "brand": "marca",
            "model": "modelo",
            "engine": "motor",
            "fuel": "combustível",
            "year_start": "ano inicial",
            "year_end": "ano final",
        }

        for app_index, application in enumerate(raw_applications, start=1):
            app_label = f"Aplicação {app_index}"

            normalized_engine = normalize_vehicle_engine_choice(application.get("engine", ""))
            normalized_fuel = normalize_vehicle_fuel_choice(application.get("fuel", ""))

            if application.get("engine") and not normalized_engine:
                self.add_error(None, f"{app_label}: Selecione um motor válido.")
                continue

            if application.get("fuel") and not normalized_fuel:
                self.add_error(None, f"{app_label}: Selecione um combustível válido.")
                continue

            normalized_application = {
                **application,
                "engine": normalized_engine,
                "fuel": normalized_fuel,
            }

            missing_fields = [label for field_name, label in required_application_fields.items() if not str(normalized_application.get(field_name, "")).strip()]
            if missing_fields:
                self.add_error(None, f"{app_label}: Preencha {', '.join(missing_fields)}.")
                continue

            try:
                year_start = int(str(normalized_application.get("year_start", "")).strip())
                year_end = int(str(normalized_application.get("year_end", "")).strip())
            except (TypeError, ValueError):
                self.add_error(None, f"{app_label}: Informe anos válidos.")
                continue

            if year_start > year_end:
                self.add_error(None, f"{app_label}: O ano inicial não pode ser maior que o ano final.")
                continue

            if year_start < 1900 or year_end > 2100:
                self.add_error(None, f"{app_label}: Os anos devem estar entre 1900 e 2100.")
                continue

            normalized_key = (
                normalize_vehicle_text(str(normalized_application.get("brand", ""))),
                normalize_vehicle_text(str(normalized_application.get("model", ""))),
                normalize_vehicle_text(str(normalized_application.get("engine", ""))),
                normalize_vehicle_text(str(normalized_application.get("fuel", ""))),
                year_start,
                year_end,
            )

            if normalized_key in seen_applications:
                self.add_error(None, f"{app_label}: Aplicação repetida no kit.")
                continue

            seen_applications.add(normalized_key)
            normalized_applications.append(
                {
                    "brand": str(normalized_application.get("brand", "")).strip(),
                    "model": str(normalized_application.get("model", "")).strip(),
                    "engine": str(normalized_application.get("engine", "")).strip(),
                    "fuel": str(normalized_application.get("fuel", "")).strip(),
                    "year_start": year_start,
                    "year_end": year_end,
                }
            )

        cleaned_data["_kit_applications"] = normalized_applications

        if self.workshop:
            if unique_product_ids:
                valid_products = set(Product.objects.filter(workshop=self.workshop, id__in=unique_product_ids).values_list("id", flat=True))
                if set(map(int, unique_product_ids)) != valid_products:
                    logger.warning(
                        "Produto de outra oficina detectado no kit",
                        extra={"kit_id": self.instance.pk, "requested_product_ids": unique_product_ids, "valid_product_ids": list(valid_products)},
                    )
                    self.add_error(None, "Alguns produtos selecionados não pertencem à oficina ativa.")

            if unique_service_ids:
                valid_services = set(Service.objects.filter(workshop=self.workshop, id__in=unique_service_ids).values_list("id", flat=True))
                if set(map(int, unique_service_ids)) != valid_services:
                    logger.warning(
                        "Servico de outra oficina detectado no kit",
                        extra={"kit_id": self.instance.pk, "requested_service_ids": unique_service_ids, "valid_service_ids": list(valid_services)},
                    )
                    self.add_error(None, "Alguns serviços selecionados não pertencem à oficina ativa.")

        return cleaned_data

    def save(self, commit=True):
        instance: Kit = super().save(commit=commit)

        if not instance.pk:
            return instance

        product_ids = self.cleaned_data.get("_kit_products_ids", [])
        service_ids = self.cleaned_data.get("_kit_services_ids", [])
        product_qty: dict[str, int] = self.cleaned_data.get("_kit_products_qty", {})
        service_qty: dict[str, int] = self.cleaned_data.get("_kit_services_qty", {})
        service_duration: dict[str, timedelta] = self.cleaned_data.get("_kit_services_duration", {})
        service_cost: dict[str, Decimal | None] = self.cleaned_data.get("_kit_services_cost", {})
        service_sell_by_duration: dict[str, Decimal | None] = self.cleaned_data.get("_kit_services_sell_by_duration", {})
        service_sell: dict[str, Decimal | None] = self.cleaned_data.get("_kit_services_sell", {})
        service_pricing_mode: str = self.cleaned_data.get("_kit_service_pricing_mode", Kit.ServicePricingMode.BY_DURATION)
        applications: list[dict[str, int | str]] = self.cleaned_data.get("_kit_applications", [])

        KitProduct.objects.filter(kit=instance).exclude(product_id__in=product_ids).delete()
        KitService.objects.filter(kit=instance).exclude(service_id__in=service_ids).delete()

        for pid in product_ids:
            try:
                KitProduct.objects.update_or_create(
                    kit=instance,
                    product_id=int(pid),
                    defaults={"quantity": int(product_qty.get(pid, 1) or 1)},
                )
            except Exception:
                logger.exception(
                    "Falha ao persistir produto no kit",
                    extra={"kit_id": instance.pk, "product_id": pid, "quantity": product_qty.get(pid, 1)},
                )
                raise

        for sid in service_ids:
            try:
                KitService.objects.update_or_create(
                    kit=instance,
                    service_id=int(sid),
                    defaults={
                        "quantity": int(service_qty.get(sid, 1) or 1),
                        "duration": service_duration.get(sid, timedelta()),
                        "cost_price": Money(service_cost[sid], "BRL") if service_cost.get(sid) is not None else None,
                        "duration_selling_price": Money(service_sell_by_duration[sid], "BRL") if service_sell_by_duration.get(sid) is not None else None,
                        "selling_price": Money(service_sell[sid], "BRL") if service_sell.get(sid) is not None else None,
                    },
                )
            except Exception:
                logger.exception(
                    "Falha ao persistir servico no kit",
                    extra={
                        "kit_id": instance.pk,
                        "service_id": sid,
                        "quantity": service_qty.get(sid, 1),
                        "duration": str(service_duration.get(sid, timedelta())),
                        "cost_price": str(service_cost.get(sid) if service_cost.get(sid) is not None else ""),
                        "duration_selling_price": str(service_sell_by_duration.get(sid) if service_sell_by_duration.get(sid) is not None else ""),
                        "selling_price": str(service_sell.get(sid) if service_sell.get(sid) is not None else ""),
                    },
                )
                raise

        try:
            KitApplication.objects.filter(kit=instance).delete()
            KitApplication.objects.bulk_create(
                [
                    KitApplication(
                        kit=instance,
                        brand=str(application["brand"]),
                        model=str(application["model"]),
                        engine=str(application["engine"]),
                        fuel=str(application["fuel"]),
                        year_start=int(application["year_start"]),
                        year_end=int(application["year_end"]),
                    )
                    for application in applications
                ]
            )
        except Exception:
            logger.exception(
                "Falha ao persistir aplicações do kit",
                extra={"kit_id": instance.pk, "applications_count": len(applications)},
            )
            raise

        prefetched_cache = getattr(instance, "_prefetched_objects_cache", None)
        if isinstance(prefetched_cache, dict):
            prefetched_cache.pop("applications", None)

        totals = self._calculate_total_kits(
            service_ids=service_ids,
            service_qty=service_qty,
            service_duration=service_duration,
            service_sell_by_duration=service_sell_by_duration,
            service_sell=service_sell,
            service_pricing_mode=service_pricing_mode,
            product_ids=product_ids,
            product_qty=product_qty,
        )

        instance.total_price = totals["total_sell"]
        instance.total_duration = totals["services_total_duration"]
        instance.service_pricing_mode = service_pricing_mode

        instance.save(update_fields=["total_price", "total_duration", "service_pricing_mode"])

        return instance

    @staticmethod
    def _format_duration(value: timedelta | None) -> str:
        if not value:
            return "00:00:00"

        total_seconds = int(value.total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _parse_duration_value(raw_value: str) -> timedelta | None:
        value = (raw_value or "").strip()
        if not value:
            return timedelta()

        parts = value.split(":")
        try:
            if len(parts) == 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = 0
            elif len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
            else:
                return None
        except ValueError:
            return None

        if hours < 0 or minutes < 0 or seconds < 0:
            return None
        if minutes > 59 or seconds > 59:
            return None
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def _getlist_from_data(self, key: str) -> list[str]:
        getlist = getattr(self.data, "getlist", None)
        if callable(getlist):
            values = cast(Any, getlist)(key)
            if values is None:
                return []
            if isinstance(values, (list, tuple)):
                return [str(v) for v in values]
            return [str(values)]

        value = self.data.get(key, [])
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value]
        return [str(value)]

    def _calculate_total_kits(
        self,
        service_ids: list[str],
        service_qty: dict[str, int],
        service_duration: dict[str, timedelta],
        service_sell_by_duration: dict[str, Decimal | None],
        service_sell: dict[str, Decimal | None],
        service_pricing_mode: str,
        product_ids: list[str],
        product_qty: dict[str, int],
    ) -> dict[str, timedelta | Any]:
        products_map = {str(p.id): p for p in Product.objects.filter(workshop=self.workshop, id__in=product_ids).only("id", "selling_price", "selling_price_currency")}

        services_map = {str(s.id): s for s in Service.objects.filter(workshop=self.workshop, id__in=service_ids).only("id", "selling_price", "selling_price_currency", "duration")}

        products_sell = Decimal(0)
        services_sell = Decimal(0)
        services_total_duration = timedelta()

        for pid in product_ids:
            product = products_map.get(str(pid))
            if not product:
                continue
            qty = int(product_qty.get(pid, 1) or 1)
            products_sell += (product.selling_price.amount if product.selling_price else Decimal("0")) * qty
        for sid in service_ids:
            service = services_map.get(str(sid))
            if not service:
                continue
            qty = int(service_qty.get(sid, 1) or 1)
            if service_pricing_mode == Kit.ServicePricingMode.BY_DURATION:
                unit_sell = service_sell_by_duration.get(sid)
            else:
                unit_sell = service_sell.get(sid)
            if unit_sell is None:
                unit_sell = service.selling_price.amount if service.selling_price else Decimal("0")
            services_sell += unit_sell * qty

            row_duration = service_duration.get(sid, service.duration or timedelta()) * qty
            services_total_duration += row_duration
        total_sell = products_sell + services_sell

        return {
            "total_sell": Money(total_sell, "BRL"),
            "services_total_duration": services_total_duration,
        }


class QuickProductEditForm(EquivalentProductsFormMixin, CoreModelForm):
    equivalent_search = forms.CharField(required=False, label="Produtos Equivalentes")
    profit_margin = forms.DecimalField(required=False, max_digits=16, decimal_places=12, widget=PercentageInput(attrs={"readonly": True}))

    class Meta:
        model = Product
        fields = [
            # Identificação
            "code",
            "name",
            "description",
            "unit",
            "group",
            "brand",
            "model",
            # Estoque
            "sku",
            "barcode",
            "location",
            "equivalent_parts",
            # Financeiro
            "cost_price",
            "selling_price",
            "profit_margin",
            # Fiscal
            "ncm",
            "cest",
            "origin_cst",
            "purpose",
            # Detalhes
            "image",
            "application",
            "is_active",
        ]
        widgets = {
            "code": TextInput(),
            "name": TextInput(),
            "description": TextareaInput(attrs={"class": "!bg-transparent"}),
            "unit": SearchableSelectInput(),
            "group": SearchableSelectInput(),
            "brand": TextInput(),
            "model": TextInput(),
            "sku": TextInput(),
            "barcode": TextInput(),
            "location": TextInput(),
            "cost_price": MoneyInput(),
            "selling_price": MoneyInput(),
            "profit_margin": PercentageInput(attrs={"readonly": True}),
            "ncm": TextInput(),
            "cest": TextInput(),
            "origin_cst": SearchableSelectInput(),
            "purpose": SearchableSelectInput(),
            "image": ImageInput(),
            "application": TextareaInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if workshop:
            self.fields["group"].queryset = self.fields["group"].queryset.filter(workshop=workshop)
            self.fields["equivalent_parts"].queryset = Product.objects.filter(workshop=workshop)

            if self.instance.pk:
                self.fields["equivalent_parts"].queryset = self.fields["equivalent_parts"].queryset.exclude(pk=self.instance.pk)

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        search_product_url = reverse("catalog:product_search")
        equivalent_sync_url = reverse("catalog:product-equivalents-sync-hx", kwargs={"product_id": self.instance.pk}) if self.instance.pk else ""

        return Layout(
            Div(
                Div(
                    # --- DADOS GERAIS ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Dados Gerais</h3>'),
                    Field("code", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("unit", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("group", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("brand", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("model", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("description", wrapper_class="col-span-12 lg:col-span-11"),
                    Field("is_active", wrapper_class="col-span-12 lg:col-span-1"),
                    HTML('<div class="col-span-12 divider my-1"></div>'),
                    # --- FINANCEIRO ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Financeiro</h3>'),
                    Div(
                        Field("cost_price", wrapper_class="col-span-12 lg:col-span-4"),
                        Div(
                            Field("selling_price", wrapper_class="w-full"),
                            HTML("""
                                <div class="text-error text-xs mt-1" 
                                     x-show="priceError" 
                                     x-cloak 
                                     x-transition>
                                    ⚠️ O preço de venda está menor que o custo!
                                </div>
                            """),
                            css_class="col-span-12 lg:col-span-4",
                        ),
                        Field("profit_margin", wrapper_class="col-span-12 lg:col-span-4", css_class="opacity-50 cursor-not-allowed"),
                        css_class="contents",
                        **{
                            "@input": "calculateMargin()",
                        },
                    ),
                    HTML('<div class="col-span-12 divider my-1"></div>'),
                    # --- ESTOQUE E LOGÍSTICA ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Estoque e Logística</h3>'),
                    Field("location", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("barcode", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("sku", wrapper_class="col-span-12 lg:col-span-4"),
                    # --- Peças Equivalentes ---
                    self.build_equivalent_products_section(search_url=search_product_url, sync_url=equivalent_sync_url),
                    HTML('<div class="col-span-12 divider my-1"></div>'),
                    # --- FISCAL ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Fiscal</h3>'),
                    Field("ncm", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("cest", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("origin_cst", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("purpose", wrapper_class="col-span-12"),
                    HTML('<div class="col-span-12 divider my-1"></div>'),
                    # --- DETALHES ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Detalhes</h3>'),
                    Field("image", wrapper_class="col-span-12 lg:col-span- 6"),
                    Field("application", wrapper_class="col-span-12"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                ),
                **{
                    "x-data": """{
                        priceError: false,
                        _calculatingMargin: false,
                        calculateMargin() {
                            if (this._calculatingMargin) return;
                            const getRawValue = (fieldId) => {
                                const el = document.getElementById(fieldId);
                                return el ? parseFloat(el.value) || 0 : 0;
                            }

                            let cost = getRawValue("id_cost_price_0");
                            let sell = getRawValue("id_selling_price_0");

                            if (sell > 0 && sell < cost) {
                                this.priceError = true;
                            } else {
                                this.priceError = false;
                            }

                            let marginEl = document.getElementById("id_profit_margin_display");

                            if (sell > 0) {
                                let margin = ((sell - cost) / sell) * 100;
                                margin = Math.round(margin * 100) / 100;
                                if (marginEl) {
                                    marginEl.value = parseFloat(margin.toFixed(2)).toFixed(2).replace(".", ",");
                                    this._calculatingMargin = true;
                                    marginEl.dispatchEvent(new Event('input', { bubbles: true }));
                                    this._calculatingMargin = false;
                                }
                            } else {
                                if (marginEl) {
                                    marginEl.value = "0,00";
                                    this._calculatingMargin = true;
                                    marginEl.dispatchEvent(new Event('input', { bubbles: true }));
                                    this._calculatingMargin = false;
                                }
                            }
                        }
                    }"""
                },
            ),
        )

    def clean_code(self):
        code = self.cleaned_data.get("code")

        if code and self.workshop:
            qs = Product.objects.filter(workshop=self.workshop, code__iexact=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError("Já existe um produto cadastrado com este código.")

        return code

    @staticmethod
    def _normalize_profit_margin(raw_margin: Decimal | None) -> Decimal:
        if raw_margin is None:
            return Decimal("0.00")

        normalized_margin = Decimal(raw_margin)
        if normalized_margin > Decimal("1"):
            return normalized_margin.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (normalized_margin * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def clean_profit_margin(self) -> Decimal:
        cost_price = self.cleaned_data.get("cost_price")
        selling_price = self.cleaned_data.get("selling_price")

        if cost_price is not None and selling_price is not None:
            cost_amount = Decimal(getattr(cost_price, "amount", cost_price) or 0)
            selling_amount = Decimal(getattr(selling_price, "amount", selling_price) or 0)
            if selling_amount <= 0:
                return Decimal("0.00")

            margin_percent = ((selling_amount - cost_amount) / selling_amount) * Decimal("100")
            return margin_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return self._normalize_profit_margin(self.cleaned_data.get("profit_margin"))

    def clean(self):
        cleaned_data = super().clean()
        cost_price = cleaned_data.get("cost_price")
        selling_price = cleaned_data.get("selling_price")

        if cost_price and selling_price:
            if selling_price < cost_price:
                self.add_error("selling_price", "O preço de venda não pode ser menor que o valor de custo.")

        return cleaned_data


class QuickServiceEditForm(CoreModelForm):
    class Meta:
        model = Service
        fields = ["name", "is_third_party", "duration", "selling_price", "suggested_cost", "description", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Troca de Óleo, Alinhamento..."}),
            "is_third_party": CheckboxInput(),
            "duration": DurationInput(),
            "selling_price": MoneyInput(),
            "suggested_cost": MoneyInput(),
            "description": TextareaInput(attrs={"class": "!bg-transparent"}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if self.workshop:
            self.fields["duration"].widget.attrs.update(
                {
                    "hx-post": reverse("catalog:calculate_service_prices"),
                    "hx-trigger": "keyup changed delay:300ms",
                    "hx-target": "#div_id_suggested_cost",  # Alvo principal (o resto vai via OOB)
                    "hx-include": "closest form",
                }
            )

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        search_url = reverse("catalog:services_search")

        return Layout(
            Div(
                # Linha 1: Nome e Checkbox Terceiro
                Div(
                    Field(
                        "name",
                        hx_get=search_url,
                        hx_trigger="keyup changed delay:500ms",
                        hx_target="#name-suggestions",  # Onde renderizar o resultado
                        hx_swap="innerHTML",
                        autocomplete="off",
                        wrapper_class="w-full",
                    ),
                    # Container VAZIO para as sugestões (Preenchido via HTMX)
                    HTML('<div id="name-suggestions" class="absolute z-50 w-full top-full left-0"></div>'),
                    css_class="relative col-span-12 lg:col-span-9",
                ),
                Field("is_third_party", wrapper_class="col-span-12 lg:col-span-2 text-nowrap"),
                # Linha 2: Valores e Duração
                Field("duration", wrapper_class="col-span-12 lg:col-span-4"),
                Field("suggested_cost", wrapper_class="col-span-12 lg:col-span-4"),
                Field("selling_price", wrapper_class="col-span-12 lg:col-span-4"),
                # Linha 3: Descrição e Ativo
                Field("description", wrapper_class="col-span-12"),
                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
            ),
        )

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name and self.workshop:
            qs = Service.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um serviço com este nome.")
        return name
