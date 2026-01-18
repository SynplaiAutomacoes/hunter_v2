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
            initial_products = [{"id": p.id, "name": str(p)} for p in self.instance.products.all()]
            initial_services = [{"id": s.id, "name": str(s)} for s in self.instance.services.all()]

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
                            @add-kit-product.window=\"addProduct($event.detail)\"
                            @add-kit-service.window=\"addService($event.detail)\"
                        >
                            <div class=\"flex flex-wrap gap-2 mb-3\">
                                <label for=\"kit-products-modal\" class=\"btn btn-outline btn-sm\">Adicionar Produto</label>
                                <label for=\"kit-services-modal\" class=\"btn btn-outline btn-sm\">Adicionar Serviço</label>
                            </div>

                            <div class=\"p-4 bg-base-300 rounded-box mb-4\">
                                <div class=\"font-semibold mb-2\">Produtos</div>
                                <ul class=\"flex flex-col gap-2\">
                                    <template x-for=\"(item, index) in selectedProducts\" :key=\"'p-'+item.id\">
                                        <li class=\"flex gap-2 items-center\">
                                            <div class=\"p-2 rounded-md w-full flex items-center bg-base-200 text-base-content cursor-default border border-base-300\">
                                                <span x-text=\"item.name\"></span>
                                            </div>
                                            <button type=\"button\" class=\"btn-table-delete\" @click=\"removeProduct(index)\" title=\"Remover\">
                                                <span class=\"material-icons text-base\">delete</span>
                                            </button>
                                        </li>
                                    </template>
                                    <li x-show=\"selectedProducts.length === 0\" class=\"text-sm text-gray-500 italic\">Nenhum produto adicionado.</li>
                                </ul>
                                <select name=\"kit_products\" multiple class=\"hidden\">
                                    <template x-for=\"item in selectedProducts\" :key=\"'po-'+item.id\">
                                        <option :value=\"item.id\" selected></option>
                                    </template>
                                </select>
                            </div>

                            <div class=\"p-4 bg-base-300 rounded-box\">
                                <div class=\"font-semibold mb-2\">Serviços</div>
                                <ul class=\"flex flex-col gap-2\">
                                    <template x-for=\"(item, index) in selectedServices\" :key=\"'s-'+item.id\">
                                        <li class=\"flex gap-2 items-center\">
                                            <div class=\"p-2 rounded-md w-full flex items-center bg-base-200 text-base-content cursor-default border border-base-300\">
                                                <span x-text=\"item.name\"></span>
                                            </div>
                                            <button type=\"button\" class=\"btn-table-delete\" @click=\"removeService(index)\" title=\"Remover\">
                                                <span class=\"material-icons text-base\">delete</span>
                                            </button>
                                        </li>
                                    </template>
                                    <li x-show=\"selectedServices.length === 0\" class=\"text-sm text-gray-500 italic\">Nenhum serviço adicionado.</li>
                                </ul>
                                <select name=\"kit_services\" multiple class=\"hidden\">
                                    <template x-for=\"item in selectedServices\" :key=\"'so-'+item.id\">
                                        <option :value=\"item.id\" selected></option>
                                    </template>
                                </select>
                            </div>

                            <input type=\"checkbox\" id=\"kit-products-modal\" class=\"modal-toggle\" />
                            <div class=\"modal\" role=\"dialog\" aria-modal=\"true\">
                                <div class=\"modal-box\">
                                    <h3 class=\"text-lg font-bold\">Adicionar Produto</h3>
                                    <div class=\"mt-4\">
                                        <div class=\"relative\">
                                            <input
                                                type=\"text\"
                                                id=\"kit-product-search-input\"
                                                name=\"product_search\"
                                                class=\"input input-bordered w-full\"
                                                placeholder=\"Buscar produto por código, nome ou marca...\"
                                                autocomplete=\"off\"
                                                hx-get=\"{product_search_url}\"
                                                hx-trigger=\"keyup changed delay:500ms\"
                                                hx-target=\"#kit-product-suggestions\"
                                                hx-swap=\"innerHTML\"
                                            />
                                            <div id=\"kit-product-suggestions\" class=\"absolute z-50 w-full top-full left-0\"></div>
                                        </div>
                                    </div>
                                    <div class=\"modal-action\">
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
                                        <div class=\"relative\">
                                            <input
                                                type=\"text\"
                                                id=\"kit-service-search-input\"
                                                name=\"service_search\"
                                                class=\"input input-bordered w-full\"
                                                placeholder=\"Buscar serviço por nome...\"
                                                autocomplete=\"off\"
                                                hx-get=\"{service_search_url}\"
                                                hx-trigger=\"keyup changed delay:500ms\"
                                                hx-target=\"#kit-service-suggestions\"
                                                hx-swap=\"innerHTML\"
                                            />
                                            <div id=\"kit-service-suggestions\" class=\"absolute z-50 w-full top-full left-0\"></div>
                                        </div>
                                    </div>
                                    <div class=\"modal-action\">
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
                                    addProduct(item) {{
                                        if (!this.selectedProducts.find(i => i.id == item.id)) {{
                                            this.selectedProducts.push(item);
                                        }}
                                        const input = document.getElementById('kit-product-search-input');
                                        const box = document.getElementById('kit-product-suggestions');
                                        if (input) input.value = '';
                                        if (box) box.innerHTML = '';
                                    }},
                                    addService(item) {{
                                        if (!this.selectedServices.find(i => i.id == item.id)) {{
                                            this.selectedServices.push(item);
                                        }}
                                        const input = document.getElementById('kit-service-search-input');
                                        const box = document.getElementById('kit-service-suggestions');
                                        if (input) input.value = '';
                                        if (box) box.innerHTML = '';
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

        KitProduct.objects.filter(kit=instance).exclude(product_id__in=product_ids).delete()
        KitService.objects.filter(kit=instance).exclude(service_id__in=service_ids).delete()

        existing_product_ids = set(KitProduct.objects.filter(kit=instance).values_list("product_id", flat=True))
        for pid in product_ids:
            if int(pid) not in existing_product_ids:
                KitProduct.objects.create(kit=instance, product_id=int(pid))

        existing_service_ids = set(KitService.objects.filter(kit=instance).values_list("service_id", flat=True))
        for sid in service_ids:
            if int(sid) not in existing_service_ids:
                KitService.objects.create(kit=instance, service_id=int(sid))

        return instance
