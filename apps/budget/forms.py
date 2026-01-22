from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django import forms

from apps.budget.models import Budget
from apps.core.widgets import TextInput, SelectInput, NumberInput


class BudgetStep1Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = [
            "workshop",
            "collaborator",
            # TODO add 'Data de Entrada' field
            "customer",
            "vehicle",
            "current_km",
            "fuel_level",
        ]
        widgets = {
            "workshop": TextInput(attrs={"readonly": "readonly"}),
            "collaborator": TextInput(attrs={"readonly": "readonly"}),
            "customer": SelectInput(),
            "vehicle": SelectInput(),
            "current_km": NumberInput(),
            "fuel_level": NumberInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.user = kwargs.pop("user", None)  # Passar o user para pegar o colaborador
        super().__init__(*args, **kwargs)

        # Preenchimento inicial (Campos não editáveis)
        if self.workshop:
            self.fields["workshop"].initial = self.workshop.name
            self.fields["customer"].queryset = self.fields["customer"].queryset.filter(workshop=self.workshop)
            self.fields["vehicle"].queryset = self.fields["vehicle"].queryset.none()

        if self.user:
            self.fields["collaborator"].initial = self.user.get_full_name() or self.user.username

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                # Coluna Esquerda
                Div(
                    # Orçamento
                    Div(
                        HTML('<h3 class="text-lg font-bold mb-2">Orçamento</h3>'),
                        Div(
                            Field("workshop", wrapper_class="col-span-12 lg:col-span-4"),
                            Field("collaborator", wrapper_class="col-span-12 lg:col-span-4"),
                            css_class="grid grid-cols-12 gap-4",
                        ),
                        css_class="mb-6 p-4 bg-base-200 rounded-lg",
                    ),

                    # Cliente
                    Div(
                        HTML('<h3 class="text-lg font-bold mb-2">Cliente</h3>'),
                        Div(
                            Field("customer", wrapper_class="col-span-12 lg:col-span-6", hx_get="/budget/helper/customer-detail/", hx_target="#resumo-cliente", hx_trigger="change"),
                            Field("vehicle", wrapper_class="col-span-12 lg:col-span-6", hx_get="/budget/helper/vehicle-detail/", hx_target="#resumo-veiculo", hx_trigger="change"),
                            css_class="grid grid-cols-12 gap-4",
                        ),
                        css_class="mb-6 p-4 bg-base-200 rounded-lg",
                    ),
                    # Veículo
                    Div(
                        HTML('<h3 class="text-lg font-bold mb-2">Veículo</h3>'),
                        Div(
                            Field("current_km", wrapper_class="col-span-12 lg:col-span-6"),
                            Field("fuel_level", wrapper_class="col-span-12 lg:col-span-6"),
                            css_class="grid grid-cols-12 gap-4"
                        ),
                        css_class="p-4 bg-base-200 rounded-lg"
                    ),
                    css_class="col-span-12 lg:col-span-8",
                ),

                # Coluna Direita (Resumo)
                Div(
                    Div(
                        HTML('<h2 class="text-xl font-bold mb-4 border-b pb-2">Resumo</h2>'),
                        # Cliente
                        HTML('<h4 class="font-semibold text-primary mb-2">Cliente</h4>'),
                        Div(
                            id="resumo-cliente",
                            css_class="mb-6 overflow-x-auto",
                            content="""
                            <table class="table table-compact w-full">
                                <tr><th>Nome</th><td class="text-gray-500">-</td></tr>
                                <tr><th>CPF</th><td class="text-gray-500">-</td></tr>
                            </table>
                        """,
                        ),
                        # Veículo
                        HTML('<h4 class="font-semibold text-primary mb-2">Veículo</h4>'),
                        Div(
                            id="resumo-veiculo",
                            css_class="overflow-x-auto",
                            content="""
                            <table class="table table-compact w-full">
                                <tr><th>Placa</th><td class="text-gray-500">-</td></tr>
                                <tr><th>Modelo</th><td class="text-gray-500">-</td></tr>
                            </table>
                        """,
                        ),
                        css_class="sticky top-4 p-6 bg-white shadow-md border rounded-xl",
                    ),
                    css_class="col-span-12 lg:col-span-4",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start flex",
            )
        )