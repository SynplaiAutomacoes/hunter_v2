from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from djmoney.money import Money

from apps.catalog.kit_applications import normalize_vehicle_text
from apps.catalog.models.kits import Kit, KitApplication, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.widgets import CheckboxInput, TextInput, TextareaInput, SelectInput, MoneyInput, PercentageInput, ImageInput, DurationInput
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)


# TODO: Improve mobile visibility of table
class KitForm(forms.ModelForm):
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
        name = str(self.cleaned_data.get("name", "")).strip()
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
            posted_applications = self._extract_application_rows_from_post()
            return posted_applications or [self._empty_application_row()]

        if self.instance.pk:
            applications = [
                {
                    "brand": application.brand,
                    "model": application.model,
                    "engine": application.engine,
                    "fuel": application.fuel,
                    "year_start": str(application.year_start),
                    "year_end": str(application.year_end),
                }
                for application in self.instance.ordered_applications()
            ]
            if applications:
                return applications

        return [self._empty_application_row()]

    def get_layout(self):
        cancel_url = reverse("catalog:kits_list")
        product_search_url = reverse("catalog:kits_product_search")
        service_search_url = reverse("catalog:kits_service_search")

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

                initial_services.append(
                    {
                        "id": service.id,
                        "name": service.name,
                        "cost": str(service.suggested_cost) if service.suggested_cost else "-",
                        "sell": str(service.selling_price),
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
                initial_services.append(
                    {
                        "id": service.id,
                        "name": service.name,
                        "cost": str(service.suggested_cost) if service.suggested_cost else "-",
                        "sell": str(service.selling_price),
                        "qty": ks.quantity,
                        "duration": KitForm._format_duration(ks.duration),
                    }
                )

        products_json = json.dumps(initial_products)
        services_json = json.dumps(initial_services)
        applications_json = json.dumps(self._build_initial_applications())

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
                        >
                            <div class="p-4 bg-base-300 rounded-box mb-4">
                                <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                                    <div>
                                        <div class="font-semibold">Aplicações do Kit</div>
                                        <div class="text-sm text-base-content/70">Informe os veículos, motorizações e anos compatíveis com este kit.</div>
                                    </div>
                                    <button type="button" class="btn btn-sm btn-primary" @click="addApplication()">Adicionar aplicação</button>
                                </div>

                                <div class="space-y-3">
                                    <template x-for="(application, index) in applications" :key="`application-${{index}}`">
                                        <div class="p-4 border border-base-200 rounded-box bg-base-100">
                                            <div class="grid grid-cols-1 lg:grid-cols-12 gap-3 items-start">
                                                <div class="lg:col-span-2">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Marca</span>
                                                    </label>
                                                    <input type="text" name="kit_application_brand" class="input-theme w-full" x-model="application.brand" placeholder="Ex: Jeep" />
                                                </div>
                                                <div class="lg:col-span-3">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Modelo</span>
                                                    </label>
                                                    <input type="text" name="kit_application_model" class="input-theme w-full" x-model="application.model" placeholder="Ex: Renegade" />
                                                </div>
                                                <div class="lg:col-span-2">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Motor</span>
                                                    </label>
                                                    <input type="text" name="kit_application_engine" class="input-theme w-full" x-model="application.engine" placeholder="Ex: 2.0" />
                                                </div>
                                                <div class="lg:col-span-2">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Combustível</span>
                                                    </label>
                                                    <input type="text" name="kit_application_fuel" class="input-theme w-full" x-model="application.fuel" placeholder="Ex: Diesel" />
                                                </div>
                                                <div class="lg:col-span-1">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Ano inicial</span>
                                                    </label>
                                                    <input type="number" name="kit_application_year_start" class="input-theme w-full" min="1900" max="2100" x-model="application.year_start" placeholder="2015" />
                                                </div>
                                                <div class="lg:col-span-1">
                                                    <label class="label p-0 mb-1">
                                                        <span class="label-text">Ano final</span>
                                                    </label>
                                                    <input type="number" name="kit_application_year_end" class="input-theme w-full" min="1900" max="2100" x-model="application.year_end" placeholder="2021" />
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

                                    <div x-show="applications.length === 0" class="rounded-box border border-dashed border-base-300 p-4 text-sm text-base-content/70">
                                        Nenhuma aplicação adicionada. Cadastre ao menos uma aplicação para salvar o kit.
                                    </div>
                                </div>
                            </div>

                            <div class="p-4 bg-base-300 rounded-box mb-3">
                                <div class="text-sm text-base-content/70">Duração Total</div>
                                <div class="text-xl font-semibold" x-text="totalDurationDisplay"></div>
                            </div>

                            <div class="divider my-1"></div>
                            <h3 class="text-xl font-bold mb-2">Itens do Kit</h3>

                            <div class="flex flex-wrap gap-2 mb-3">
                                <label for="kit-products-modal" class="btn btn-sm btn-primary" @click="openProductsModal()">Adicionar Produto</label>
                                <label for="kit-services-modal" class="btn btn-sm btn-primary" @click="openServicesModal()">Adicionar Serviço</label>
                                <label for="kit-distribute-time-modal" class="btn btn-sm btn-primary" @click="openDistributeTimeModal()">Distribuir Tempos</label>
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
                                                        <input type="number" min="1" step="1" class="input-theme w-20 text-center" x-model.number="item.qty" />
                                                    </td>
                                                    <td class="text-right">
                                                        <button type="button" 
                                                                class="btn-table-edit mx-1"
                                                                @click="openProductEditModal(item.id)"
                                                                title="Editar Produto">
                                                            <span class="material-icons text-base">edit</span>
                                                        </button>
                                                        
                                                        <button type="button" class="btn-table-delete" @click="removeProduct(index)" title="Remover">
                                                            <span class="material-icons text-base">delete</span>
                                                        </button>
                                                    </td>
                                                </tr>
                                            </template>
                                            <tr x-show="selectedProducts.length === 0">
                                                <td colspan="5" class="text-sm text-gray-500 italic">Nenhum produto adicionado.</td>
                                            </tr>
                                        </tbody>
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
                                                <th class="text-right">Venda</th>
                                                <th class="text-center">Qtd</th>
                                                <th class="text-center">Duração</th>
                                                <th class="text-right"></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <template x-for="(item, index) in selectedServices" :key="'s-'+item.id">
                                                <tr>
                                                    <td><span x-text="item.name"></span></td>
                                                    <td class="text-right whitespace-nowrap"><span x-text="item.cost"></span></td>
                                                    <td class="text-right whitespace-nowrap"><span x-text="item.sell"></span></td>
                                                    <td class="text-center">
                                                        <input type="number" min="1" step="1" class="input-theme w-20 text-center" x-model.number="item.qty" />
                                                    </td>
                                                    <td class="text-center whitespace-nowrap">
                                                        <span x-text="formatDurationForDisplay(item.duration)"></span>
                                                    </td>
                                                    <td class="text-right">
                                                        <button type="button" 
                                                                class="btn-table-edit mx-1"
                                                                @click="openServiceEditModal(item.id)"
                                                                title="Editar Serviço">
                                                            <span class="material-icons text-base">edit</span>
                                                        </button>

                                                        <button type="button" class="btn-table-delete" @click="removeService(index)" title="Remover">
                                                            <span class="material-icons text-base">delete</span>
                                                        </button>
                                                    </td>
                                                </tr>
                                            </template>
                                            <tr x-show="selectedServices.length === 0">
                                                <td colspan="6" class="text-sm text-gray-500 italic">Nenhum serviço adicionado.</td>
                                            </tr>
                                        </tbody>
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
                                    <h3 class="text-lg font-bold">Distribuir Tempos</h3>
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
                        </div>

                        <script>
                            function kitItemsManager() {{
                                return {{
                                    selectedProducts: {products_json},
                                    selectedServices: {services_json},
                                    applications: {applications_json},
                                    modalSelectedProducts: [],
                                    modalSelectedServices: [],
                                    totalDurationDisplay: '00:00',

                                    init() {{
                                        this.refreshTotalDurationDisplay();
                                        this.resetEditModalContent();
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
                                    setEditModalMessage(message) {{
                                        const content = document.getElementById('edit-modal-content');
                                        if (!content) return;
                                        content.innerHTML = `<div class="p-6 text-sm text-base-content/70">${{message}}</div>`;
                                    }},
                                    resetEditModalContent() {{
                                        this.setEditModalMessage('Selecione um item para editar.');
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
                                        this.setEditModalMessage('Carregando serviço...');
                                        const modalToggle = document.getElementById('edit-item-modal');
                                        if (modalToggle) modalToggle.checked = true;
                                        if (!window.htmx) return;
                                        window.htmx.ajax('GET', `/catalog/edit_service_modal_form/${{serviceId}}/`, {{
                                            target: '#edit-modal-content',
                                            swap: 'innerHTML',
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
                                    refreshTotalDurationDisplay() {{
                                        const totalSeconds = this.selectedServices.reduce((sum, service) => {{
                                            return sum + this.parseDurationToSeconds(service.duration);
                                        }}, 0);
                                        this.totalDurationDisplay = this.formatSecondsToHHMM(totalSeconds);
                                    }},
                                    buildEmptyApplication() {{
                                        return {{
                                            brand: '',
                                            model: '',
                                            engine: '',
                                            fuel: '',
                                            year_start: '',
                                            year_end: '',
                                        }};
                                    }},
                                    addApplication() {{
                                        this.applications.push(this.buildEmptyApplication());
                                    }},
                                    removeApplication(index) {{
                                        this.applications.splice(index, 1);
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
                                            cost: s.cost,
                                            sell: s.sell,
                                            qty: s.qty,
                                            duration: s.duration || '00:00:00',
                                        }}));
                                        this.resetServiceSearch();
                                        this.reloadServiceSuggestions();
                                    }},
                                    openDistributeTimeModal() {{
                                        this.distributionTotalTime = '';
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
                                                ...item,
                                                qty: 1,
                                                duration: this.normalizeDurationForPost(item.duration || '00:00:00'),
                                            }});
                                            this.refreshTotalDurationDisplay();
                                        }}
                                    }},
                                    distributionTotalTime: '',

                                    parseTotalMinutes(value) {{
                                        const normalized = this.normalizeDistributionTime(value);
                                        const match = normalized.match(/^(\\d{{2}}):(\\d{{2}})$/);
                                        if (!match) return null;
                                        const hours = parseInt(match[1], 10);
                                        const minutes = parseInt(match[2], 10);
                                        if (Number.isNaN(hours) || Number.isNaN(minutes) || minutes > 59) return null;
                                        return (hours * 60) + minutes;
                                    }},
                                    normalizeDistributionTime(value) {{
                                        const digits = (value || '').toString().replace(/\\D/g, '').slice(0, 4);
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
                                    applyTimeDistribution() {{
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
                                        }});

                                        this.totalDurationDisplay = this.normalizeDistributionTime(this.distributionTotalTime);

                                        const modalToggle = document.getElementById('kit-distribute-time-modal');
                                        if (modalToggle) modalToggle.checked = false;
                                    }},

                                    applySelectedProducts() {{
                                        this.modalSelectedProducts.forEach(p => this.addProduct(p));

                                        const modalToggle = document.getElementById('kit-products-modal');
                                        if (modalToggle) modalToggle.checked = false;

                                        this.resetProductSearch();
                                        this.reloadProductSuggestions();
                                    }},
                                    applySelectedServices() {{
                                        this.modalSelectedServices.forEach(s => this.addService(s));

                                        const modalToggle = document.getElementById('kit-services-modal');
                                        if (modalToggle) modalToggle.checked = false;

                                        this.resetServiceSearch();
                                        this.reloadServiceSuggestions();
                                    }},
                                    removeProduct(index) {{ this.selectedProducts.splice(index, 1); }},
                                    removeService(index) {{
                                        this.selectedServices.splice(index, 1);
                                        this.refreshTotalDurationDisplay();
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

        cleaned_data["_kit_products_qty"] = product_qty
        cleaned_data["_kit_services_qty"] = service_qty
        cleaned_data["_kit_services_duration"] = service_duration

        raw_applications = self._extract_application_rows_from_post()
        if not raw_applications:
            self.add_error(None, "Cadastre ao menos uma aplicação para o kit.")

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

        for application in raw_applications:
            missing_fields = [label for field_name, label in required_application_fields.items() if not str(application.get(field_name, "")).strip()]
            if missing_fields:
                self.add_error(None, "Preencha marca, modelo, motor, combustível, ano inicial e ano final em todas as aplicações do kit.")
                continue

            try:
                year_start = int(str(application.get("year_start", "")).strip())
                year_end = int(str(application.get("year_end", "")).strip())
            except (TypeError, ValueError):
                self.add_error(None, "Informe anos válidos em todas as aplicações do kit.")
                continue

            if year_start > year_end:
                self.add_error(None, "O ano inicial da aplicação não pode ser maior que o ano final.")
                continue

            if year_start < 1900 or year_end > 2100:
                self.add_error(None, "Os anos de aplicação do kit devem estar entre 1900 e 2100.")
                continue

            normalized_key = (
                normalize_vehicle_text(str(application.get("brand", ""))),
                normalize_vehicle_text(str(application.get("model", ""))),
                normalize_vehicle_text(str(application.get("engine", ""))),
                normalize_vehicle_text(str(application.get("fuel", ""))),
                year_start,
                year_end,
            )

            if normalized_key in seen_applications:
                self.add_error(None, "Existem aplicações repetidas no kit.")
                continue

            seen_applications.add(normalized_key)
            normalized_applications.append(
                {
                    "brand": str(application.get("brand", "")).strip(),
                    "model": str(application.get("model", "")).strip(),
                    "engine": str(application.get("engine", "")).strip(),
                    "fuel": str(application.get("fuel", "")).strip(),
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
            product_ids=product_ids,
            product_qty=product_qty,
        )

        instance.total_price = totals["total_sell"]
        instance.total_duration = totals["services_total_duration"]

        instance.save(update_fields=["total_price", "total_duration"])

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

    def _calculate_total_kits(self, service_ids: list[str], service_qty: dict[str, int], service_duration: dict[str, timedelta], product_ids: list[str], product_qty: dict[str, int]) -> dict[str, timedelta | Any]:
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
            services_sell += (service.selling_price.amount if service.selling_price else Decimal("0")) * qty

            row_duration = service_duration.get(sid, service.duration or timedelta()) * qty
            services_total_duration += row_duration
        total_sell = products_sell + services_sell

        return {
            "total_sell": Money(total_sell, "BRL"),
            "services_total_duration": services_total_duration,
        }


class QuickProductEditForm(forms.ModelForm):
    equivalent_search = forms.CharField(required=False, label="Produtos Equivalentes")

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
            "unit": SelectInput(),
            "group": SelectInput(),
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
            "origin_cst": SelectInput(),
            "purpose": SelectInput(),
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

        initial_equivalents = []
        if self.instance.pk:
            initial_equivalents = [{"id": p.id, "name": str(p)} for p in self.instance.equivalent_parts.all()]

        equivalents_json = json.dumps(initial_equivalents)

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
                    Div(
                        Div(
                            Field(
                                "equivalent_search",
                                css_class="input-theme border-none !bg-transparent",
                                wrapper_class="w-full !bg-transparent",
                                autocomplete="off",
                                placeholder="Buscar...",
                                hx_get=search_product_url,
                                hx_trigger="keyup changed delay:500ms",
                                hx_target="#product-suggestions",
                                hx_swap="innerHTML",
                                id="equivalent-search-input",
                                hx_vals=json.dumps({"ignore_id": self.instance.pk}) if self.instance.pk else "{}",
                            ),
                            HTML('<div id="product-suggestions" class="absolute z-50 w-full top-full left-0"></div>'),
                            css_class="relative w-full mb-3",
                        ),
                        HTML("""
                            <ul class="flex flex-col gap-2">
                                <template x-for="(item, index) in selecteds" :key="item.id">
                                    <li class="flex gap-2 items-center">
                                        <div class="p-2 rounded-md w-full flex items-center bg-base-200 text-base-content cursor-default border border-base-300">
                                            <span x-text="item.name"></span>
                                        </div>

                                        <button type="button" class="btn-table-delete" @click="remove(index)" title="Remover">
                                            <span class="material-icons text-base">delete</span>
                                        </button>
                                    </li>
                                </template>

                                <li x-show="selecteds.length === 0" class="text-sm text-gray-500 italic">
                                    Nenhum produto equivalente adicionado.
                                </li>
                            </ul>
                            """),
                        # Select Oculto para salvar
                        HTML("""
                            <select name="equivalent_parts" multiple class="hidden">
                                <template x-for="item in selecteds" :key="item.id">
                                    <option :value="item.id" selected></option>
                                </template>
                            </select>
                            """),
                        **{
                            "x-data": f"""{{ selecteds: {equivalents_json},remove(index) {{ this.selecteds.splice(index, 1); }}}}""",
                            "id": "equivalents-manager",
                            "@add-equivalent.window": """
                                if(!selecteds.find(i=>i.id==$event.detail.id)) {
                                    selecteds.push($event.detail);
                                    // Limpa input e sugestões
                                    document.getElementById('equivalent-search-input').value = '';
                                    document.getElementById('product-suggestions').innerHTML = '';
                                }
                            """,
                        },
                        css_class="col-span-12 p-4 bg-base-300 rounded-box",
                    ),
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
                        calculateMargin() {
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
                                if (marginEl) {
                                    marginEl.value = margin.toFixed(2).replace(".", ",");
                                    marginEl.dispatchEvent(new Event('input', { bubbles: true }));
                                }
                            } else {
                                if (marginEl) {
                                    marginEl.value = "0,00";
                                    marginEl.dispatchEvent(new Event('input', { bubbles: true }));
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

    def clean(self):
        cleaned_data = super().clean()
        cost_price = cleaned_data.get("cost_price")
        selling_price = cleaned_data.get("selling_price")

        if cost_price and selling_price:
            if selling_price < cost_price:
                self.add_error("selling_price", "O preço de venda não pode ser menor que o valor de custo.")

        return cleaned_data


class QuickServiceEditForm(forms.ModelForm):
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
