from __future__ import annotations

from typing import Any

from crispy_forms.layout import Div, Field, HTML
from django import forms

from apps.core.presentation.widgets import CEPInput, CPForCNPJInput, DecimalInput, NumberInput, PlateInput, SearchableSelectInput, TextareaInput, TextInput
from apps.finance.nfe_transport import (
    BRAZILIAN_STATE_CHOICES,
    FREIGHT_MODE_CHOICES,
    TRANSPORT_PERSON_TYPE_CHOICES,
    NfeTransportValidationError,
    build_nfe_transport_form_initial,
    build_nfe_transport_snapshot,
)


def configure_nfe_transport_form(*, form: forms.BaseForm, snapshot: object = None, freight_mode: object = 9) -> None:
    initial_freight_mode = 9 if freight_mode in (None, "") else freight_mode
    form.fields["freight_mode"] = forms.ChoiceField(
        label="Modalidade de frete",
        choices=FREIGHT_MODE_CHOICES,
        initial=str(initial_freight_mode),
        widget=SearchableSelectInput(choices=FREIGHT_MODE_CHOICES),
        help_text="Sem transporte preserva o comportamento atual da NF-e.",
    )
    form.fields["transport_person_type"] = forms.ChoiceField(label="Tipo de transportador", choices=TRANSPORT_PERSON_TYPE_CHOICES, required=False, widget=SearchableSelectInput(choices=TRANSPORT_PERSON_TYPE_CHOICES))
    form.fields["transport_document"] = forms.CharField(label="CPF/CNPJ do transportador", required=False, max_length=18, widget=CPForCNPJInput(mode="both"))
    form.fields["transport_name"] = forms.CharField(label="Nome/Razao social", required=False, max_length=60, widget=TextInput())
    form.fields["transport_state_registration"] = forms.CharField(label="Inscricao estadual", required=False, max_length=14, widget=TextInput())
    form.fields["transport_address"] = forms.CharField(label="Endereco", required=False, max_length=60, widget=TextInput())
    form.fields["transport_state"] = forms.ChoiceField(label="UF", choices=BRAZILIAN_STATE_CHOICES, required=False, widget=SearchableSelectInput(choices=BRAZILIAN_STATE_CHOICES))
    form.fields["transport_city"] = forms.CharField(label="Cidade", required=False, max_length=60, widget=TextInput())
    form.fields["transport_postal_code"] = forms.CharField(label="CEP", required=False, max_length=10, widget=CEPInput())
    form.fields["transport_vehicle_plate"] = forms.CharField(label="Placa do veiculo", required=False, max_length=8, widget=PlateInput())
    form.fields["transport_vehicle_state"] = forms.ChoiceField(label="UF do veiculo", choices=BRAZILIAN_STATE_CHOICES, required=False, widget=SearchableSelectInput(choices=BRAZILIAN_STATE_CHOICES))
    form.fields["transport_rntc"] = forms.CharField(label="RNTRC/ANTT", required=False, max_length=20, widget=TextInput())
    form.fields["transport_volume_quantity"] = forms.IntegerField(label="Quantidade de volumes", required=False, min_value=1, max_value=999999999999999, widget=NumberInput())
    form.fields["transport_volume_species"] = forms.CharField(label="Especie dos volumes", required=False, max_length=60, widget=TextInput())
    form.fields["transport_gross_weight"] = forms.DecimalField(label="Peso bruto (kg)", required=False, min_value=0, max_digits=12, decimal_places=3, widget=DecimalInput(min_value=0, decimal_places=3))
    form.fields["transport_net_weight"] = forms.DecimalField(label="Peso liquido (kg)", required=False, min_value=0, max_digits=12, decimal_places=3, widget=DecimalInput(min_value=0, decimal_places=3))
    form.fields["transport_volume_brand"] = forms.CharField(label="Marca dos volumes", required=False, max_length=60, widget=TextInput())
    form.fields["transport_volume_numbering"] = forms.CharField(label="Numeracao dos volumes", required=False, max_length=60, widget=TextInput())
    form.fields["transport_seals"] = forms.CharField(label="Lacres", required=False, max_length=60, widget=TextInput())
    form.fields["nfe_transport_trailers_json"] = forms.CharField(
        label="Reboques",
        required=False,
        help_text='Lista JSON opcional. Ex.: [{"placa":"ABC1234","uf_veiculo":"SP","rntc":"123","vagao":1,"balsa":"B1"}]',
        widget=TextareaInput(rows=3),
    )

    initial = build_nfe_transport_form_initial(snapshot)
    initial.setdefault("freight_mode", str(initial_freight_mode))
    for field_name, value in initial.items():
        form.initial.setdefault(field_name, value)


def clean_nfe_transport_form(cleaned_data: dict[str, Any]) -> dict[str, Any]:
    try:
        return build_nfe_transport_snapshot(cleaned_data)
    except NfeTransportValidationError as exc:
        raise forms.ValidationError(str(exc)) from exc


def build_nfe_transport_form_layout() -> Any:
    return Div(
        HTML("<h3 class='text-lg font-semibold pt-4'>Transporte</h3>"),
        HTML("<p class='text-sm text-base-content/70'>Preencha somente quando houver transporte associado a esta NF-e. Nenhum valor de frete sera calculado.</p>"),
        Field("freight_mode"),
        Div(
            Field("transport_person_type", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_document", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_name", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_state_registration", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_address", wrapper_class="col-span-12 lg:col-span-8"),
            Field("transport_state", wrapper_class="col-span-12 lg:col-span-3"),
            Field("transport_city", wrapper_class="col-span-12 lg:col-span-5"),
            Field("transport_postal_code", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_vehicle_plate", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_vehicle_state", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_rntc", wrapper_class="col-span-12 lg:col-span-4"),
            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
        ),
        HTML("<h4 class='font-semibold pt-2'>Volumes</h4>"),
        Div(
            Field("transport_volume_quantity", wrapper_class="col-span-12 lg:col-span-3"),
            Field("transport_volume_species", wrapper_class="col-span-12 lg:col-span-5"),
            Field("transport_volume_brand", wrapper_class="col-span-12 lg:col-span-4"),
            Field("transport_gross_weight", wrapper_class="col-span-12 lg:col-span-3"),
            Field("transport_net_weight", wrapper_class="col-span-12 lg:col-span-3"),
            Field("transport_volume_numbering", wrapper_class="col-span-12 lg:col-span-3"),
            Field("transport_seals", wrapper_class="col-span-12 lg:col-span-3"),
            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
        ),
        HTML("<h4 class='font-semibold pt-2'>Reboques</h4>"),
        Field("nfe_transport_trailers_json"),
        css_class="space-y-4 rounded-2xl border border-base-300 p-4",
    )
