from typing import Any

from crispy_forms.layout import Div, Field, Submit
from django import forms

from crispy_forms.helper import FormHelper, Layout

from apps.core.widgets import SelectInput, CalendarDateInput
from apps.workshops.models.workshops import Workshop


class DreForm(forms.Form):
    TIPO_DATA_CHOICES = (
        ("PG", "PAGOS"),
        ("NPG", "SERÃO PAGOS"),
        ("A", "AMBOS"),
    )

    filial = forms.ChoiceField(
        widget=SelectInput(),
        choices=[],
        required=True,
        label="Selecione a filial"
    )

    data_inicial = forms.DateField(
        widget=CalendarDateInput(),
        required=False,
        label='Data Inicial'
    )

    data_final = forms.DateField(
        widget=CalendarDateInput(),
        required=False,
        label='Data Final'
    )

    tipo_data = forms.ChoiceField(
        widget=SelectInput(),
        choices=TIPO_DATA_CHOICES,
        required=True,
        label="Selecione o tipo da data"
    )

    def __init__(self, *args: Any, workshops=None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.workshop = workshops

        if workshops:
            choices = [("", "TODAS AS FILIAIS")]
            choices += [(w.id, w.name) for w in workshops]
            self.fields["filial"].choices = choices

        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.layout = Layout(
            Div(
                Field("filial", wrapper_class="col-span-12 lg:col-span-3"),
                Field("data_inicial", wrapper_class="col-span-12 lg:col-span-3"),
                Field("data_final", wrapper_class="col-span-12 lg:col-span-3"),
                Field("tipo_data", wrapper_class="col-span-12 lg:col-span-3"),
                css_class="grid grid-cols-12 gap-4",
            ),
            Submit("submit", "Gerar DRE", css_class="btn btn-primary"),
        )