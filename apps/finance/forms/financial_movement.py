from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms
from django.template.loader import render_to_string
from django.urls import reverse_lazy

from apps.core.widgets import SearchableSelectInput, TextInput, TextareaInput, CalendarDateInput, SelectInput, MoneyInput, NumberInput
from apps.finance.models import PaymentMethod, FinancialGroup
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_movement import FinancialMovement
from apps.sources.models import Source


class FinancialMovementBaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)


class MovementStep1Form(FinancialMovementBaseForm):
    class Meta:
        model = FinancialMovement
        fields = ["source"]
        widgets = {"source": SearchableSelectInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # self.fields["source"].widget.attrs.update(
        #     {
        #         "hx-get": reverse_lazy("finance:source_details"),
        #         "hx-trigger": "change",
        #         "hx-target": "#source-details",
        #         "hx-swap": "innerHTML",
        #         "hx-include": "[name='source']",
        #     }
        # )

        if self.workshop:
            queryset = Source.objects.filter(workshop=self.workshop)
            self.fields["source"].queryset = queryset
            self.fields["source"].widget.choices = [(s.id, s.name) for s in queryset]

        source_id = self.data.get("source") or (self.instance.source_id if self.instance.pk else None)
        source_obj = None
        if source_id:
            source_obj = Source.objects.filter(id=source_id, workshop=self.workshop).first()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML("""<script>
                document.addEventListener('DOMContentLoaded', function() {
                    const sourceInput = document.querySelector('input[name="source"]');
                    const detailsContainer = document.querySelector('#source-details');
                
                    if (sourceInput) {
                        sourceInput.addEventListener('change', function() {
                            const sourceId = this.value;
                            
                            if (!sourceId) {
                                detailsContainer.innerHTML = "<p class='italic opacity-50 text-center py-8'>Selecione uma origem para ver os detalhes.</p>";
                                return;
                            }
                
                            const url = `{% url 'finance:source_details' %}?source=${sourceId}`;
                
                            fetch(url, {
                                headers: {
                                    'X-Requested-With': 'XMLHttpRequest'
                                }
                            })
                            .then(response => response.text())
                            .then(html => {
                                detailsContainer.innerHTML = html;
                            })
                            .catch(error => console.error('Erro ao buscar detalhes:', error));
                        });
                    }
                });
            </script>"""),
            Div(
                Div(
                    HTML('<h2 class="text-xl font-bold mb-4">Origem da Movimentação</h2>'),
                    Field("source"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                Div(
                    HTML('<h2 class="text-xl font-bold mb-4">Dados da Origem</h2>'),
                    Div(
                        HTML(render_to_string("finance/partials/source_resume.html", {"source_obj": source_obj})),
                        id="source-details",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-12 gap-6",
            ),
        )


class MovementStep2Form(FinancialMovementBaseForm):
    class Meta:
        model = FinancialMovement
        fields = ["description", "items_observation"]
        widgets = {"description": TextInput(), "items_observation": TextareaInput(attrs={"rows": 4, "placeholder": "Ex: Compra de 50 cápsulas de café expresso..."})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = True
        self.helper = FormHelper()
        self.helper.form_tag = False


class MovementStep3Form(FinancialMovementBaseForm):
    is_paid = forms.TypedChoiceField(
        label="Pago",
        required=True,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Não"), (True, "Sim")),
        widget=SelectInput(choices=[(False, "Não"), (True, "Sim")]),
        initial=False,
    )

    class Meta:
        model = FinancialMovement
        fields = ["direction", "payment_method", "is_paid", "amount", "due_date", "nf_number", "budget_plan", "bank_account", "attachment", "financial_observation"]
        widgets = {"direction": SelectInput(), "payment_method": SearchableSelectInput(), "amount": MoneyInput(), "due_date": CalendarDateInput(), "nf_number": NumberInput(), "budget_plan": SearchableSelectInput(), "bank_account": SearchableSelectInput(), "financial_observation": TextareaInput(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["due_date"].required = True
        self.fields["direction"].required = True
        self.fields["amount"].required = True
        self.fields["payment_method"].required = True
        self.fields["is_paid"].initial = bool(self.instance.is_paid) if self.instance.pk else False

        if self.workshop:
            self.fields["payment_method"].widget.choices = [(pm.id, str(pm)) for pm in PaymentMethod.objects.filter(workshop=self.workshop)]
            self.fields["budget_plan"].widget.choices = [(bp.id, str(bp)) for bp in FinancialGroup.objects.filter(workshop=self.workshop)]
            self.fields["bank_account"].widget.choices = [(ba.id, str(ba)) for ba in BankAccount.objects.filter(workshop=self.workshop)]

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Div("due_date", css_class="col-span-4"),
                Div("direction", css_class="col-span-4"),
                Div("amount", css_class="col-span-4"),
                #
                Div("budget_plan", css_class="col-span-6"),
                Div("bank_account", css_class="col-span-6"),
                #
                Div("payment_method", css_class="col-span-4"),
                Div("is_paid", css_class="col-span-4"),
                Div("nf_number", css_class="col-span-4"),
                Div("attachment", css_class="col-span-12"),
                #
                Div("financial_observation", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            )
        )


class MovementStep4Form(FinancialMovementBaseForm):
    class Meta:
        model = FinancialMovement
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        self.helper = FormHelper()
        self.helper.form_tag = False

        is_entry = inst.direction == FinancialMovement.MovementDirection.CREDIT
        status_color = "text-success" if is_entry else "text-error"
        direction_label = inst.get_direction_display()

        self.helper.layout = Layout(
            HTML(f"""
                    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">

                        <div class="col-span-12 lg:col-span-6 space-y-6">
                            <div>
                                <h3 class="text-2xl font-bold mb-6 flex items-center gap-2 text-base-content">
                                    <span class="material-icons">description</span>
                                    Revisão da Movimentação
                                </h3>

                                <div class="card bg-base-200 shadow-sm border border-base-300">
                                    <div class="card-body p-6">
                                        <h4 class="text-base uppercase font-black opacity-50 mb-4 flex items-center gap-1">
                                            <span class="material-icons text-sm">inventory_2</span> Origem e Identificação
                                        </h4>

                                        <div class="space-y-4">
                                            <div>
                                                <p class="text-sm opacity-60">Origem</p>
                                                <p class="text-lg font-semibold">{inst.source.name if inst.source else "Não informada"}</p>
                                            </div>

                                            <div>
                                                <p class="text-sm opacity-60">Descrição</p>
                                                <p class="text-md italic">"{inst.description or "Sem descrição"}"</p>
                                            </div>

                                            <div class="alert bg-base-100 border-none shadow-inner py-3 mt-4">
                                                <span class="material-icons text-info">notes</span>
                                                <div class="flex flex-col">
                                                    <span class="text-xs font-bold uppercase opacity-50">Observações</span>
                                                    <span class="text-sm">{inst.items_observation or "Nenhuma observação adicional registrada."}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="hidden lg:block lg:col-span-1"></div>

                        <div class="col-span-12 lg:col-span-5 flex flex-col gap-6">
                            <div class="card bg-base-300 shadow-md h-full">
                                <div class="card-body p-6 flex flex-col">
                                    <h2 class="text-xl font-bold mb-6 uppercase text-base-content opacity-70 flex items-center gap-2">
                                        <span class="material-icons text-sm">payments</span> 
                                        Resumo Financeiro
                                    </h2>

                                    <div class="space-y-4 flex-grow">
                                        <div class="flex justify-between items-center bg-base-100 p-3 rounded-lg">
                                            <span class="text-sm font-medium">Operação:</span>
                                            <span class="badge badge-lg font-bold {status_color} bg-opacity-10 border-none">
                                                {direction_label}
                                            </span>
                                        </div>

                                        <div class="flex justify-between items-center px-2">
                                            <span class="text-sm opacity-70 italic">Data de Vencimento:</span>
                                            <span class="font-mono font-bold tracking-wider italic text-base-content">
                                                {inst.due_date.strftime("%d/%m/%Y") if inst.due_date else "---"}
                                            </span>
                                        </div>

                                        <div class="divider my-2"></div>

                                        <div class="bg-base-100 p-4 rounded-xl border border-base-300">
                                            <div class="flex justify-between items-end">
                                                <span class="text-sm uppercase font-black opacity-40 mb-1">Valor Total</span>
                                                <span class="text-3xl font-black {status_color}">
                                                    {inst.amount}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    """)
        )
