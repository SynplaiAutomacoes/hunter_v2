from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django import forms
from django.urls import reverse

from apps.budget.models import Budget
from apps.core.widgets import TextInput, SelectInput, NumberInput, CalendarDateInput


class BudgetStep1Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = [
            "workshop",
            "collaborator",
            "entry_date",
            "customer",
            "vehicle",
            "current_km",
            "fuel_level",
        ]
        widgets = {
            "workshop": TextInput(attrs={"readonly": "readonly", "style": "cursor:not-allowed;"}),
            "collaborator": TextInput(attrs={"readonly": "readonly", "style": "cursor:not-allowed;"}),
            "entry_date": CalendarDateInput(),
            "customer": SelectInput(),
            "vehicle": SelectInput(),
            "current_km": NumberInput(),
            "fuel_level": NumberInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        customer_detail = reverse("customer:customer-detail")
        vehicle_detail = reverse("customer:vehicle-detail")

        # Preenchimento inicial (Campos não editáveis)
        if self.workshop:
            self.fields["workshop"].initial = self.workshop.name
            self.fields["customer"].queryset = self.fields["customer"].queryset.filter(workshop=self.workshop)
            self.fields["vehicle"].queryset = self.fields["vehicle"].queryset.none()

        if self.request and self.request.user:
            user = self.request.user
            self.fields["collaborator"].initial = user.get_full_name() or user.username

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"<span hx-get='{customer_detail}' hx-trigger='load' hx-target='#resumo-cliente' style='display:none;'></span>"),
            HTML(f"<span hx-get='{vehicle_detail}' hx-trigger='load' hx-target='#resumo-veiculo' style='display:none;'></span>"),
            Div(
                # Coluna Esquerda
                Div(
                    # Orçamento
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Orçamento</h3>'),
                        Div(
                            Field("workshop", wrapper_class="col-span-12 lg:col-span-12"),
                            Field("collaborator", wrapper_class="col-span-12 lg:col-span-12"),
                            Field("entry_date", wrapper_class="col-span-12 lg:col-span-12"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    # Cliente
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Cliente</h3>'),
                        Div(
                            Field("customer", wrapper_class="col-span-12 lg:col-span-12", hx_get=f"{customer_detail}", hx_target="#resumo-cliente", hx_trigger="change"),
                            Field("vehicle", wrapper_class="col-span-12 lg:col-span-12", hx_get=f"{vehicle_detail}", hx_target="#resumo-veiculo", hx_trigger="change"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    # Veículo
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Veículo</h3>'),
                        Div(
                            Field("current_km", wrapper_class="col-span-12 lg:col-span-6"),
                            Field("fuel_level", wrapper_class="col-span-12 lg:col-span-6"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                # Coluna Direita (Resumo)
                Div(
                    Div(
                        HTML('<h2 class="text-2xl font-bold mb-4 pb-2">Resumo</h2>'),
                        # Cliente
                        HTML('<h4 class="text-lg font-bold mb-2">Cliente</h4>'),
                        Div(id="resumo-cliente", css_class="mb-6 overflow-x-auto"),

                        # Veículo
                        HTML('<h4 class="text-lg font-bold mb-2">Veículo</h4>'),
                        Div(id="resumo-veiculo", css_class="overflow-x-auto"),
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-38",
            ),
        )