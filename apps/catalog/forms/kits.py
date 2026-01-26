from __future__ import annotations

import json

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.widgets import CheckboxInput, TextInput, TextareaInput
from apps.workshops.models.workshops import Workshop


class KitForm(forms.ModelForm):
    product_search = forms.CharField(required=False, label="Produtos")
    service_search = forms.CharField(required=False, label="Serviços")

    class Meta:
        model = Kit
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Kit Revisão 10.000km"}),
            "description": TextareaInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("catalog:kits_list")
        product_search_url = reverse("catalog:kits_product_search")
        service_search_url = reverse("catalog:kits_service_search")

        initial_products = []
        initial_services = []
        if self.instance.pk:
            # djmoney MoneyField (produtos) usa 2 colunas (valor + moeda).
            # Incluir `*_currency` evita problemas quando o template/JS acessa o Money.
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
                p = kp.product
                initial_products.append(
                    {
                        "id": p.id,
                        "name": f"{p.code} - {p.name}",
                        "cost": str(p.cost_price),
                        "sell": str(p.selling_price),
                        "qty": kp.quantity,
                    }
                )

            # djmoney MoneyField (serviços) usa 2 colunas (valor + moeda).
            # Incluir `*_currency` evita problemas quando o template/JS acessa o Money.
            kit_services = (
                KitService.objects.filter(kit=self.instance)
                .select_related("service")
                .only(
                    "quantity",
                    "service__id",
                    "service__name",
                    "service__suggested_cost",
                    "service__suggested_cost_currency",
                    "service__selling_price",
                    "service__selling_price_currency",
                )
            )
            for ks in kit_services:
                s = ks.service
                initial_services.append(
                    {
                        "id": s.id,
                        "name": s.name,
                        "cost": str(s.suggested_cost) if s.suggested_cost else "-",
                        "sell": str(s.selling_price),
                        "qty": ks.quantity,
                    }
                )

        products_json = json.dumps(initial_products)
        services_json = json.dumps(initial_services)

        return Layout(
            Div(
                Div(
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Dados do Kit</h3>'),
                    Field("name", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("is_active", wrapper_class="col-span-12 lg:col-span-2"),
                    Field("description", wrapper_class="col-span-12"),
                    HTML('<div class="col-span-12 divider my-1"></div>'),
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Itens do Kit</h3>'),
                    HTML(
                        f"""
                        <div
                            class=\"col-span-12\"
                            x-data=\"kitItemsManager()\"
                        >
                            <div class=\"flex flex-wrap gap-2 mb-3\">
                                <label for=\"kit-products-modal\" class=\"btn btn-outline btn-sm\" @click=\"openProductsModal()\">Adicionar Produto</label>
                                <label for=\"kit-services-modal\" class=\"btn btn-outline btn-sm\" @click=\"openServicesModal()\">Adicionar Serviço</label>
                            </div>

                            <div class=\"p-4 bg-base-300 rounded-box mb-4\">
                                <div class=\"font-semibold mb-2\">Produtos</div>
                                <div class=\"overflow-x-auto\">
                                    <table class=\"table table-sm\">
                                        <thead>
                                            <tr>
                                                <th>Produto</th>
                                                <th class=\"text-right\">Custo</th>
                                                <th class=\"text-right\">Venda</th>
                                                <th class=\"text-center\">Qtd</th>
                                                <th class=\"text-right\"></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <template x-for=\"(item, index) in selectedProducts\" :key=\"'p-'+item.id\">
                                                <tr>
                                                    <td>
                                                        <span x-text=\"item.name\"></span>
                                                    </td>
                                                    <td class=\"text-right whitespace-nowrap\"><span x-text=\"item.cost\"></span></td>
                                                    <td class=\"text-right whitespace-nowrap\"><span x-text=\"item.sell\"></span></td>
                                                    <td class=\"text-center\">
                                                        <input type=\"number\" min=\"1\" step=\"1\" class=\"input input-bordered input-sm w-20 text-center\" x-model.number=\"item.qty\" />
                                                    </td>
                                                    <td class=\"text-right\">
                                                        <button type=\"button\" class=\"btn-table-delete\" @click=\"removeProduct(index)\" title=\"Remover\">
                                                            <span class=\"material-icons text-base\">delete</span>
                                                        </button>
                                                    </td>
                                                </tr>
                                            </template>
                                            <tr x-show=\"selectedProducts.length === 0\">
                                                <td colspan=\"5\" class=\"text-sm text-gray-500 italic\">Nenhum produto adicionado.</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                                <select name=\"kit_products\" multiple class=\"hidden\">
                                    <template x-for=\"item in selectedProducts\" :key=\"'po-'+item.id\">
                                        <option :value=\"item.id\" selected></option>
                                    </template>
                                </select>
                                <template x-for=\"item in selectedProducts\" :key=\"'pq-'+item.id\">
                                    <input type=\"hidden\" :name=\"'kit_product_qty_' + item.id\" :value=\"item.qty\" />
                                </template>
                            </div>

                            <div class=\"p-4 bg-base-300 rounded-box\">
                                <div class=\"font-semibold mb-2\">Serviços</div>
                                <div class=\"overflow-x-auto\">
                                    <table class=\"table table-sm\">
                                        <thead>
                                            <tr>
                                                <th>Serviço</th>
                                                <th class=\"text-right\">Custo</th>
                                                <th class=\"text-right\">Venda</th>
                                                <th class=\"text-center\">Qtd</th>
                                                <th class=\"text-right\"></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <template x-for=\"(item, index) in selectedServices\" :key=\"'s-'+item.id\">
                                                <tr>
                                                    <td><span x-text=\"item.name\"></span></td>
                                                    <td class=\"text-right whitespace-nowrap\"><span x-text=\"item.cost\"></span></td>
                                                    <td class=\"text-right whitespace-nowrap\"><span x-text=\"item.sell\"></span></td>
                                                    <td class=\"text-center\">
                                                        <input type=\"number\" min=\"1\" step=\"1\" class=\"input input-bordered input-sm w-20 text-center\" x-model.number=\"item.qty\" />
                                                    </td>
                                                    <td class=\"text-right\">
                                                        <button type=\"button\" class=\"btn-table-delete\" @click=\"removeService(index)\" title=\"Remover\">
                                                            <span class=\"material-icons text-base\">delete</span>
                                                        </button>
                                                    </td>
                                                </tr>
                                            </template>
                                            <tr x-show=\"selectedServices.length === 0\">
                                                <td colspan=\"5\" class=\"text-sm text-gray-500 italic\">Nenhum serviço adicionado.</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                                <select name=\"kit_services\" multiple class=\"hidden\">
                                    <template x-for=\"item in selectedServices\" :key=\"'so-'+item.id\">
                                        <option :value=\"item.id\" selected></option>
                                    </template>
                                </select>
                                <template x-for=\"item in selectedServices\" :key=\"'sq-'+item.id\">
                                    <input type=\"hidden\" :name=\"'kit_service_qty_' + item.id\" :value=\"item.qty\" />
                                </template>
                            </div>

                            <input type=\"checkbox\" id=\"kit-products-modal\" class=\"modal-toggle\" />
                            <div class=\"modal\" role=\"dialog\" aria-modal=\"true\">
                                <div class=\"modal-box\">
                                    <h3 class=\"text-lg font-bold\">Adicionar Produto</h3>
                                    <div class=\"mt-4\">
                                        <input
                                            type=\"text\"
                                            id=\"kit-product-search-input\"
                                            name=\"product_search\"
                                            class=\"input input-bordered w-full\"
                                            placeholder=\"Filtrar por código, nome ou marca...\"
                                            autocomplete=\"off\"
                                            hx-get=\"{product_search_url}\"
                                            hx-trigger=\"keyup changed delay:500ms\"
                                            hx-target=\"#kit-product-items\"
                                            hx-swap=\"innerHTML\"
                                        />

                                        <div class=\"mt-3 max-h-80 overflow-y-auto border border-base-200 rounded-box\">
                                            <table class=\"table table-sm bg-base-100\">
                                                <thead class=\"sticky top-0 bg-base-100\">
                                                    <tr>
                                                        <th class=\"w-10\"></th>
                                                        <th>Produto</th>
                                                        <th class=\"text-right\">Custo</th>
                                                        <th class=\"text-right\">Venda</th>
                                                    </tr>
                                                </thead>
                                                <tbody
                                                    id=\"kit-product-items\"
                                                    hx-get=\"{product_search_url}\"
                                                    hx-trigger=\"load\"
                                                    hx-target=\"this\"
                                                    hx-swap=\"innerHTML\"
                                                ></tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div class=\"modal-action\">
                                        <button type=\"button\" class=\"btn btn-primary\" @click=\"applySelectedProducts()\">Adicionar</button>
                                        <label for=\"kit-products-modal\" class=\"btn btn-ghost\">Fechar</label>
                                    </div>
                                </div>
                                <label class=\"modal-backdrop\" for=\"kit-products-modal\">Close</label>
                            </div>

                            <input type=\"checkbox\" id=\"kit-services-modal\" class=\"modal-toggle\" />
                            <div class=\"modal\" role=\"dialog\" aria-modal=\"true\">
                                <div class=\"modal-box\">
                                    <h3 class=\"text-lg font-bold\">Adicionar Serviço</h3>
                                    <div class=\"mt-4\">
                                        <input
                                            type=\"text\"
                                            id=\"kit-service-search-input\"
                                            name=\"service_search\"
                                            class=\"input input-bordered w-full\"
                                            placeholder=\"Filtrar por nome...\"
                                            autocomplete=\"off\"
                                            hx-get=\"{service_search_url}\"
                                            hx-trigger=\"keyup changed delay:500ms\"
                                            hx-target=\"#kit-service-items\"
                                            hx-swap=\"innerHTML\"
                                        />

                                        <div class=\"mt-3 max-h-80 overflow-y-auto border border-base-200 rounded-box\">
                                            <table class=\"table table-sm bg-base-100\">
                                                <thead class=\"sticky top-0 bg-base-100\">
                                                    <tr>
                                                        <th class=\"w-10\"></th>
                                                        <th>Serviço</th>
                                                        <th class=\"text-right\">Custo</th>
                                                        <th class=\"text-right\">Venda</th>
                                                    </tr>
                                                </thead>
                                                <tbody
                                                    id=\"kit-service-items\"
                                                    hx-get=\"{service_search_url}\"
                                                    hx-trigger=\"load\"
                                                    hx-target=\"this\"
                                                    hx-swap=\"innerHTML\"
                                                ></tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div class=\"modal-action\">
                                        <button type=\"button\" class=\"btn btn-primary\" @click=\"applySelectedServices()\">Adicionar</button>
                                        <label for=\"kit-services-modal\" class=\"btn btn-ghost\">Fechar</label>
                                    </div>
                                </div>
                                <label class=\"modal-backdrop\" for=\"kit-services-modal\">Close</label>
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
                                        }}));
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
                                            }});
                                        }}
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
        cleaned_data = super().clean()

        def _getlist(key: str) -> list[str]:
            if hasattr(self.data, "getlist"):
                return [str(v) for v in self.data.getlist(key)]
            value = self.data.get(key, [])
            if value is None:
                return []
            if isinstance(value, (list, tuple)):
                return [str(v) for v in value]
            return [str(value)]

        product_ids = [pid for pid in _getlist("kit_products") if pid and pid.isdigit()]
        service_ids = [sid for sid in _getlist("kit_services") if sid and sid.isdigit()]

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
        for sid in unique_service_ids:
            raw = self.data.get(f"kit_service_qty_{sid}", "1")
            try:
                qty = int(raw)
            except (TypeError, ValueError):
                qty = 0
            if qty < 1:
                self.add_error(None, "Quantidade inválida para serviço.")
            service_qty[sid] = qty if qty >= 1 else 1

        cleaned_data["_kit_products_qty"] = product_qty
        cleaned_data["_kit_services_qty"] = service_qty

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
                defaults={"quantity": int(service_qty.get(sid, 1) or 1)},
            )

        return instance
