from __future__ import annotations

import json
from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.catalog.models.products import Product
from apps.core.widgets import (
    TextInput,
    MoneyInput,
    SelectInput,
    PercentageInput,
    CheckboxInput,
    TextareaInput,
    ImageInput,
)
from apps.workshops.models.workshops import Workshop


# TODO: Improve equivalent products to use a modal similar to Kits. Probably make a reusable modal for it.
class ProductForm(forms.ModelForm):
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
        cancel_url = reverse("catalog:product_list")
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
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
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

    def clean_name(self):
        name = self.cleaned_data.get("name")

        if name and self.workshop:
            qs = Product.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError("Já existe um produto com este nome.")

        return name

    def clean(self):
        cleaned_data = super().clean()
        cost_price = cleaned_data.get("cost_price")
        selling_price = cleaned_data.get("selling_price")

        if cost_price and selling_price:
            if selling_price < cost_price:
                self.add_error("selling_price", "O preço de venda não pode ser menor que o valor de custo.")

        return cleaned_data
