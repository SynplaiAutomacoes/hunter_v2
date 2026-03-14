from typing import Any, cast

from crispy_forms.layout import Div, Field
from django import forms

from crispy_forms.helper import FormHelper, Layout

from apps.core.widgets import CalendarDateInput, SelectInput
from apps.finance.models import FinancialGroup


class DreForm(forms.Form):
    TIPO_DATA_CHOICES = (
        ("PG", "PAGOS"),
        ("NPG", "SERÃO PAGOS"),
        ("A", "AMBOS"),
    )

    filial = forms.ChoiceField(widget=SelectInput(), choices=[], required=True, label="Selecione a filial")

    data_inicial = forms.DateField(widget=CalendarDateInput(), required=True, label="Data Inicial")

    data_final = forms.DateField(widget=CalendarDateInput(), required=True, label="Data Final")

    tipo_data = forms.ChoiceField(widget=SelectInput(), choices=TIPO_DATA_CHOICES, required=True, label="Selecione o tipo da data")

    financial_groups = forms.ModelMultipleChoiceField(
        queryset=FinancialGroup.objects.none(),
        required=False,
        label="Selecione os Grupos Financeiros",
    )

    def __init__(self, *args: Any, workshops=None, financial_groups_qs=None, **kwargs: Any):
        super().__init__(*args, **kwargs)

        if workshops:
            choices = [("", "SELECIONE UMA FILIAL")]
            choices += [(w.id, w.name) for w in workshops]
            filial_field = cast(forms.ChoiceField, self.fields["filial"])
            filial_field.choices = choices

        if financial_groups_qs is not None:
            financial_groups_field = cast(forms.ModelMultipleChoiceField, self.fields["financial_groups"])
            financial_groups_field.queryset = financial_groups_qs

        self.helper = FormHelper()
        self.helper.form_method = "get"
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("filial", wrapper_class="col-span-12 lg:col-span-3"),
                Field("data_inicial", wrapper_class="col-span-12 lg:col-span-3"),
                Field("data_final", wrapper_class="col-span-12 lg:col-span-3"),
                Field("tipo_data", wrapper_class="col-span-12 lg:col-span-3"),
                css_class="grid grid-cols-12 gap-4",
            ),
        )
