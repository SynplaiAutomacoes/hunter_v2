from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.catalog.models.products import Product
from apps.catalog.price_tracking import build_product_price_warning
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
    profit_margin = forms.DecimalField(required=False, max_digits=9, decimal_places=6, widget=PercentageInput(attrs={"readonly": True}))

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

    def __init__(self, *args, workshop: Workshop | None = None, next_url: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.next_url = str(next_url or "").strip()
        self.last_used_price = getattr(self.instance, "last_used_price", None)

        if self.instance.pk and self.instance.profit_margin is not None:
            self.initial["profit_margin"] = (Decimal(self.instance.profit_margin) / Decimal("100")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

        if workshop:
            self.fields["group"].queryset = self.fields["group"].queryset.filter(workshop=workshop)
            self.fields["equivalent_parts"].queryset = Product.objects.filter(workshop=workshop)

            if self.instance.pk:
                self.fields["equivalent_parts"].queryset = self.fields["equivalent_parts"].queryset.exclude(pk=self.instance.pk)

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.attrs = {
            "x-data": self._build_form_alpine_data(),
            "@submit": "handleSubmit($event)",
        }
        self.helper.layout = self.get_layout()

    def _build_form_alpine_data(self) -> str:
        last_used_amount = ""
        if self.last_used_price is not None:
            last_used_amount = str(self.last_used_price.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        return f"""{{
            lastUsedPrice: {json.dumps(last_used_amount)},
            priceError: false,
            lowerPriceConfirmed: false,
            lowerPriceWarning: false,
            priceHelpMessage: '',
            getRawMoneyValue(fieldId) {{
                const field = document.getElementById(fieldId);
                if (!field) return 0;
                return Number.parseFloat(field.value || '0') || 0;
            }},
            formatCurrency(value) {{
                const numericValue = Number.parseFloat(value || '0');
                return numericValue.toLocaleString('pt-BR', {{ style: 'currency', currency: 'BRL' }});
            }},
            calculateMargin() {{
                const cost = this.getRawMoneyValue('id_cost_price_0');
                const sell = this.getRawMoneyValue('id_selling_price_0');
                this.priceError = sell > 0 && sell < cost;
                this.lowerPriceConfirmed = false;
                this.lowerPriceWarning = false;

                const marginEl = document.getElementById('id_profit_margin_display');
                if (sell > 0) {{
                    const margin = ((sell - cost) / sell) * 100;
                    if (marginEl) {{
                        marginEl.value = margin.toFixed(2).replace('.', ',');
                        marginEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }} else if (marginEl) {{
                    marginEl.value = '0,00';
                    marginEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}

                if (sell > 0) {{
                    this.priceHelpMessage = '';
                }}
            }},
            shouldWarnForLowerPrice() {{
                if (!this.lastUsedPrice) return false;
                const sell = this.getRawMoneyValue('id_selling_price_0');
                if (sell <= 0) return false;
                return sell < (Number.parseFloat(this.lastUsedPrice) || 0);
            }},
            handleSubmit(event) {{
                this.calculateMargin();
                if (this.shouldWarnForLowerPrice() && !this.lowerPriceConfirmed) {{
                    event.preventDefault();
                    this.lowerPriceWarning = true;
                    this.priceHelpMessage = '';
                }}
            }},
            continueWithLowerPrice() {{
                this.lowerPriceConfirmed = true;
                this.lowerPriceWarning = false;
                this.priceHelpMessage = '';
                this.$nextTick(() => this.$root.requestSubmit());
            }},
            cancelLowerPrice() {{
                const amountField = document.getElementById('id_selling_price_0');
                const displayField = document.getElementById('id_selling_price_0_display');
                if (amountField) {{
                    amountField.value = '';
                    amountField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    amountField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
                if (displayField) {{
                    displayField.value = '';
                    displayField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    displayField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}

                this.lowerPriceConfirmed = false;
                this.lowerPriceWarning = false;
                this.priceHelpMessage = `Último valor usado: ${{this.formatCurrency(this.lastUsedPrice)}}`;
                this.calculateMargin();
            }}
        }}"""

    @staticmethod
    def _normalize_profit_margin(raw_margin: Decimal | None) -> Decimal:
        if raw_margin is None:
            return Decimal("0.00")

        normalized_margin = Decimal(raw_margin)
        if normalized_margin > Decimal("1"):
            return normalized_margin.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (normalized_margin * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def clean_profit_margin(self):
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

    def get_layout(self):
        cancel_url = self.next_url or reverse("catalog:product_list")
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
                        HTML('<input type="hidden" name="confirm_lower_price" :value="lowerPriceConfirmed ? \'1\' : \'\'">'),
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
                                <div class="alert alert-warning mt-3" x-show="lowerPriceWarning" x-cloak x-transition>
                                    <span class="material-icons">warning</span>
                                    <div class="flex-1">
                                        <div class="font-semibold">O valor informado está abaixo do ultimo valor utilizado.</div>
                                        <div class="text-sm">Revise o preço ou confirme para continuar mesmo assim.</div>
                                        <div class="mt-3 flex flex-wrap gap-2">
                                            <button type="button" class="btn btn-ghost btn-sm" @click="cancelLowerPrice()">Cancelar</button>
                                            <button type="button" class="btn btn-warning btn-sm" @click="continueWithLowerPrice()">Continuar mesmo assim</button>
                                        </div>
                                    </div>
                                </div>
                                <div class="text-warning text-xs mt-2" x-show="priceHelpMessage" x-text="priceHelpMessage" x-cloak></div>
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
        cleaned_data = super().clean() or {}
        cost_price = cleaned_data.get("cost_price")
        selling_price = cleaned_data.get("selling_price")

        if cost_price and selling_price:
            if selling_price < cost_price:
                self.add_error("selling_price", "O preço de venda não pode ser menor que o valor de custo.")

        price_warning = build_product_price_warning(product=self.instance, attempted_price=selling_price)
        if price_warning and self.data.get("confirm_lower_price") != "1":
            self.add_error("selling_price", price_warning.message)

        return cleaned_data
