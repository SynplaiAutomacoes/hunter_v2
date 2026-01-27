from __future__ import annotations

import datetime
from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from djmoney.forms import MoneyField

from apps.core.widgets import (
    TextInput,
    SelectInput,
    DurationInput,
    PercentageInput,
    MoneyInput,
    NumberInput,
    DecimalInput,
)
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop


class WorkshopCostForm(forms.ModelForm):
    class Meta:
        model = WorkshopCost
        fields = [
            # Referência
            "month",
            "year",
            # Mecânicos
            "mechanic_quantity",
            "work_hours_per_day",
            "work_days_per_month",
            "productivity_average",
            # Taxas
            "card_rate",
            "tax_rate",
            "profit_margin",
            "commission_rate",
            "risk_coefficient",
            # Metas Inputs
            "parts_purchase_cap",
            "freight_cost",
            "third_party_service_cap",
            # Calculados (Readonly)
            "total_value",
            "total_monthly_costs",
            "profit_target",
            "gross_revenue_target",
            "profitability_multiplier",
        ]
        widgets = {
            "month": SelectInput(),
            "year": TextInput(),
            "mechanic_quantity": NumberInput(),
            "work_hours_per_day": DurationInput(mode="hours"),
            "work_days_per_month": NumberInput(),
            "productivity_average": PercentageInput(min_percent=50, max_percent=80),
            "card_rate": PercentageInput(),
            "tax_rate": PercentageInput(),
            "profit_margin": PercentageInput(),
            "commission_rate": PercentageInput(max_percent=10),
            "risk_coefficient": DecimalInput(min_value=1.0, max_value=1.5, decimal_places=1),
            "parts_purchase_cap": MoneyInput(),
            "freight_cost": MoneyInput(),
            "third_party_service_cap": MoneyInput(),
            # Readonly widgets
            "total_value": MoneyInput(attrs={"readonly": True}),
            "total_monthly_costs": MoneyInput(attrs={"readonly": True}),
            "profit_target": MoneyInput(attrs={"readonly": True}),
            "gross_revenue_target": MoneyInput(attrs={"readonly": True}),
            "profitability_multiplier": TextInput(attrs={"readonly": True}),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        # Preenchimento automático de Data se for criação
        if not self.instance.pk and not self.data:
            today = datetime.date.today()
            self.fields["month"].initial = today.month
            self.fields["year"].initial = today.year

        self.active_costs = MonthlyCost.objects.filter(workshop=workshop, is_active=True)

        # Se for edição, busca os valores já salvos nos Items
        saved_values = {}
        if self.instance.pk:
            saved_values = {item.monthly_cost_id: item.amount for item in self.instance.items.all()}

        self.cost_fields_names = []
        for cost in self.active_costs:
            field_name = f"cost_item_{cost.id}"
            self.cost_fields_names.append(field_name)

            self.fields[field_name] = MoneyField(label=cost.name, required=False, widget=MoneyInput())

            if cost.id in saved_values:
                self.initial[field_name] = saved_values[cost.id]

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("workshops:workshop_cost_list")
        calculate_url = reverse("workshops:workshop_cost_calculate")

        # Gera os campos dinâmicos de custo para o Layout
        cost_fields_layout = [Field(name, wrapper_class="col-span-12 lg:col-span-3") for name in self.cost_fields_names]

        return Layout(
            Div(
                # Envoltório com HTMX Trigger. Qualquer mudança (change) ou digitação (keyup) nestes campos dispara o recálculo.
                Div(
                    # --- SEÇÃO 1: Referência ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Mês de Referência</h3>'),
                    Field("month", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("year", wrapper_class="col-span-12 lg:col-span-6"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 2: Mecânicos ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Mecânicos Produtivos</h3>'),
                    Field("mechanic_quantity", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("work_hours_per_day", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("work_days_per_month", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("productivity_average", wrapper_class="col-span-12 lg:col-span-12"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 3: Custos Mensais (Dinâmico) ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Custos Mensais</h3>'),
                    Div(
                        *cost_fields_layout,
                        css_class="contents",  # Permite que os filhos obedeçam ao Grid pai
                    ),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 4: Taxas e Impostos ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Taxas e Impostos</h3>'),
                    Field("card_rate", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("tax_rate", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("profit_margin", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("commission_rate", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("risk_coefficient", wrapper_class="col-span-12 lg:col-span-12"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 5: Metas e Indicadores ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Metas e Indicadores</h3>'),
                    Field("parts_purchase_cap", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("freight_cost", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("third_party_service_cap", wrapper_class="col-span-12 lg:col-span-4"),
                    
                    # Atributos HTMX no container de inputs
                    # hx-include="closest form": Garante que todos os dados do form sejam enviados
                    hx_post=calculate_url,
                    hx_trigger="input delay:100ms, change delay:100ms",
                    hx_target="#calculation-results",
                    hx_include="closest form",
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start col-span-12"
                ),
                # Campos calculados (Desabilitados visualmente)
                Div(
                    HTML('<div class="col-span-12 mb-4"><span class="badge badge-neutral">Cálculos Automáticos</span></div>'),
                    Field("total_value", wrapper_class="col-span-12"),
                    Field("total_monthly_costs", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("profit_target", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("gross_revenue_target", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("profitability_multiplier", wrapper_class="col-span-12 lg:col-span-6"),
                    css_id="calculation-results",
                    css_class="col-span-12 bg-base-300 p-6 rounded-box grid grid-cols-1 lg:grid-cols-12 gap-4 items-start mt-4",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
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
        month = cleaned_data.get("month")
        year = cleaned_data.get("year")

        if month and year and self.workshop:
            qs = WorkshopCost.objects.filter(workshop=self.workshop, month=month, year=year)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um custo mensal para este Mês/Ano.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.workshop = self.workshop

        if commit:
            instance.save()

            for cost in self.active_costs:
                field_name = f"cost_item_{cost.id}"
                amount = self.cleaned_data.get(field_name)

                if amount is not None:
                    WorkshopCostItem.objects.update_or_create(workshop_cost=instance, monthly_cost=cost, defaults={"amount": amount})
        return instance
