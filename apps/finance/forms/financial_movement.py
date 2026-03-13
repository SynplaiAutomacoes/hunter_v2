from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.core.widgets import SearchableSelectInput, TextInput, TextareaInput
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
        widgets = {
            "source": SearchableSelectInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            Div(
                Div(
                    HTML('<h2 class="text-xl font-bold mb-4">Origem da Movimentação</h2>'),
                    Field("source",
                          hx_get=self.request.path,
                          hx_target="#source-details",
                          hx_trigger="change",
                          hx_select="#source-details-content",
                          hx_include="#id_source"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                Div(
                    HTML('<h2 class="text-xl font-bold mb-4">Dados da Origem</h2>'),
                    Div(
                        Div(
                            HTML(f"""
                                <div class="bg-base-200 p-4 rounded-lg space-y-2 animate-in fade-in duration-300">
                                    <p><strong>Razão Social:</strong> {source_obj.name or "----"}</p>
                                    <p><strong>CNPJ:</strong> {source_obj.cnpj or "---"}</p>
                                    <p><strong>Telefone:</strong> {source_obj.phone or "---"}</p>
                                    <p><strong>E-mail:</strong> {source_obj.email or "---"}</p>
                                </div>
                            """) if source_obj else HTML("<p class='italic opacity-50 text-center py-8'>Selecione uma origem para ver os detalhes.</p>"),
                            id="source-details-content"
                        ),
                        id="source-details",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-12 gap-6",
            )
        )


class MovementStep2Form(FinancialMovementBaseForm):
    class Meta:
        model = FinancialMovement
        fields = ["description", "items_observation"]
        widgets = {
            "description": TextInput(),
            "items_observation": TextareaInput(attrs={"rows": 4, "placeholder": "Ex: Compra de 50 cápsulas de café expresso..."})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = True
        self.helper = FormHelper()
        self.helper.form_tag = False
