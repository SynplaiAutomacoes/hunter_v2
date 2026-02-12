from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, cast

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.widgets import CheckboxInput, TextInput, TextareaInput
from apps.workshops.models.workshops import Workshop


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

        return Layout(
            Div(
                Div(
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Dados do Kit</h3>'),
                    Field("name", wrapper_class="col-span-12 lg:col-span-11"),
                    Field("is_active", wrapper_class="col-span-12 lg:col-span-1"),
                    Field("description", wrapper_class="col-span-12"),
                    HTML('<div class="col-span-12 divider my-1"></div>'),
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Itens do Kit</h3>'),
                    HTML(
                        f"""
                        <div
                            class="col-span-12"
                            x-data="kitItemsManager()"
                        >
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
                                                <tbody
                                                    id="kit-product-items"
                                                    hx-get="{product_search_url}"
                                                    hx-trigger="load"
                                                    hx-target="this"
                                                    hx-swap="innerHTML"
                                                ></tbody>
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
                                                <tbody
                                                    id="kit-service-items"
                                                    hx-get="{service_search_url}"
                                                    hx-trigger="load"
                                                    hx-target="this"
                                                    hx-swap="innerHTML"
                                                ></tbody>
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
                        </div>

                        <script>
                            function kitItemsManager() {{
                                return {{
                                    selectedProducts: {products_json},
                                    selectedServices: {services_json},
                                    modalSelectedProducts: [],
                                    modalSelectedServices: [],

                                    openProductsModal() {{
                                        this.modalSelectedProducts = this.selectedProducts.map(p => ({{
                                            id: p.id,
                                            name: p.name,
                                            cost: p.cost,
                                            sell: p.sell,
                                            qty: p.qty,
                                        }}));
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
                                        }}
                                    }},
                                    distributionTotalTime: '',

                                    parseTotalMinutes(value) {{
                                        const normalized = this.normalizeDistributionTime(value);
                                        const match = normalized.match(/^(\d{{2}}):(\d{{2}})$/);
                                        if (!match) return null;
                                        const hours = parseInt(match[1], 10);
                                        const minutes = parseInt(match[2], 10);
                                        if (Number.isNaN(hours) || Number.isNaN(minutes) || minutes > 59) return null;
                                        return (hours * 60) + minutes;
                                    }},
                                    normalizeDistributionTime(value) {{
                                        const digits = (value || '').toString().replace(/\D/g, '').slice(0, 4);
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

                                        const modalToggle = document.getElementById('kit-distribute-time-modal');
                                        if (modalToggle) modalToggle.checked = false;
                                    }},

                                    applySelectedProducts() {{
                                        this.modalSelectedProducts.forEach(p => this.addProduct(p));

                                        const modalToggle = document.getElementById('kit-products-modal');
                                        if (modalToggle) modalToggle.checked = false;

                                        const input = document.getElementById('kit-product-search-input');
                                        if (input) input.value = '';

                                        const list = document.getElementById('kit-product-items');
                                        if (list) list.innerHTML = '';
                                        if (list && window.htmx) window.htmx.trigger(list, 'load');
                                    }},
                                    applySelectedServices() {{
                                        this.modalSelectedServices.forEach(s => this.addService(s));

                                        const modalToggle = document.getElementById('kit-services-modal');
                                        if (modalToggle) modalToggle.checked = false;

                                        const input = document.getElementById('kit-service-search-input');
                                        if (input) input.value = '';

                                        const list = document.getElementById('kit-service-items');
                                        if (list) list.innerHTML = '';
                                        if (list && window.htmx) window.htmx.trigger(list, 'load');
                                    }},
                                    removeProduct(index) {{ this.selectedProducts.splice(index, 1); }},
                                    removeService(index) {{ this.selectedServices.splice(index, 1); }},
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
            self.add_error(None, "Existem produtos repetidos no kit.")
        if len(unique_service_ids) != len(service_ids):
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
                self.add_error(None, "Quantidade inválida para serviço.")
            service_qty[sid] = qty if qty >= 1 else 1

            raw_duration = str(self.data.get(f"kit_service_duration_{sid}", "") or "").strip()
            duration_value = self._parse_duration_value(raw_duration)
            if duration_value is None:
                self.add_error(None, "Duração inválida para serviço.")
                duration_value = timedelta()
            service_duration[sid] = duration_value

        cleaned_data["_kit_products_qty"] = product_qty
        cleaned_data["_kit_services_qty"] = service_qty
        cleaned_data["_kit_services_duration"] = service_duration

        if self.workshop:
            if unique_product_ids:
                valid_products = set(Product.objects.filter(workshop=self.workshop, id__in=unique_product_ids).values_list("id", flat=True))
                if set(map(int, unique_product_ids)) != valid_products:
                    self.add_error(None, "Alguns produtos selecionados não pertencem à oficina ativa.")

            if unique_service_ids:
                valid_services = set(Service.objects.filter(workshop=self.workshop, id__in=unique_service_ids).values_list("id", flat=True))
                if set(map(int, unique_service_ids)) != valid_services:
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

        KitProduct.objects.filter(kit=instance).exclude(product_id__in=product_ids).delete()
        KitService.objects.filter(kit=instance).exclude(service_id__in=service_ids).delete()

        for pid in product_ids:
            KitProduct.objects.update_or_create(
                kit=instance,
                product_id=int(pid),
                defaults={"quantity": int(product_qty.get(pid, 1) or 1)},
            )

        for sid in service_ids:
            KitService.objects.update_or_create(
                kit=instance,
                service_id=int(sid),
                defaults={
                    "quantity": int(service_qty.get(sid, 1) or 1),
                    "duration": service_duration.get(sid, timedelta()),
                },
            )

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
