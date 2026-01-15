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
)
from apps.workshops.models.workshops import Workshop


class ProductForm(forms.ModelForm):
    # Campo auxiliar para busca de equivalentes (não salvo diretamente)
    equivalent_search = forms.CharField(required=False, label="Adicionar Equivalente")

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
            "description": TextInput(),
            "unit": SelectInput(),
            "group": SelectInput(),
            "brand": TextInput(),
            "model": TextInput(),
            "sku": TextInput(),
            "barcode": TextInput(),
            "location": TextInput(),
            "cost_price": MoneyInput(),
            "selling_price": MoneyInput(),
            # Readonly e disabled para evitar edição manual da margem
            "profit_margin": PercentageInput(attrs={"readonly": True}),
            "ncm": TextInput(),
            "cest": TextInput(),
            "origin_cst": SelectInput(),
            "purpose": SelectInput(),
            "application": TextInput(),
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

        equivalents_json = json.dumps(initial_equivalents).replace('"', "&quot;")

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
                    HTML('<h3 class="col-span-12 text-lg font-bold mb-2">Financeiro</h3>'),
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
                        HTML('<label class="label"><span class="label-text font-bold">Peças Equivalentes</span></label>'),
                        Field("equivalent_search", wrapper_class="w-full", autocomplete="off", placeholder="Digite para buscar produtos...", hx_get=search_product_url, hx_trigger="keyup changed delay:300ms", hx_target="#product-suggestions"),
                        HTML('<div id="product-suggestions" class="relative"></div>'),
                        HTML(f"""
                        <div class="mt-2" 
                             x-data='{{ 
                                selecteds: {equivalents_json},
                                remove(index) {{ this.selecteds.splice(index, 1); }}
                             }}' 
                             id="equivalents-manager"
                             @add-equivalent.window="if(!selecteds.find(i=>i.id==$event.detail.id)) selecteds.push($event.detail)"
                        >
                            <select name="equivalent_parts" multiple class="hidden">
                                <template x-for="item in selecteds" :key="item.id">
                                    <option :value="item.id" selected></option>
                                </template>
                            </select>

                            <div class="flex flex-wrap gap-2">
                                <template x-for="(item, index) in selecteds" :key="item.id">
                                    <div class="badge badge-lg gap-2 pl-4 pr-2 py-4 bg-base-200 border-base-300">
                                        <span x-text="item.name"></span>
                                        <button type="button" @click="remove(index)" class="btn btn-ghost btn-xs btn-circle text-error">
                                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                                        </button>
                                    </div>
                                </template>
                                <span x-show="selecteds.length === 0" class="text-sm text-gray-400 italic py-2">Nenhuma equivalência selecionada.</span>
                            </div>
                        </div>
                        """),
                        css_class="col-span-12 bg-base-100 p-4 rounded-box border border-base-200",
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
                    Field("image", wrapper_class="col-span-12 lg:col-span-6"),
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

    def clean(self):
        cleaned_data = super().clean()
        cost_price = cleaned_data.get("cost_price")
        selling_price = cleaned_data.get("selling_price")

        if cost_price and selling_price:
            if selling_price < cost_price:
                self.add_error("selling_price", "O preço de venda não pode ser menor que o valor de custo.")

        return cleaned_data
