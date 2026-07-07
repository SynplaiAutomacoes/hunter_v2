from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import CheckboxInput, NumberInput, SearchableSelectInput, TextareaInput, TextInput
from apps.finance.models.finance import NfseMunicipalCapability, WebmaniaCompany


class NfseManualEmissionPreviewCreateForm(CoreForm):
    ENVIRONMENT_CHOICES = [("", "Selecione"), ("1", "Producao"), ("2", "Homologacao")]

    company = forms.ModelChoiceField(label="Empresa emissora", queryset=WebmaniaCompany.objects.none(), widget=SearchableSelectInput())
    municipal_capability = forms.ModelChoiceField(label="Capacidade municipal", queryset=NfseMunicipalCapability.objects.none(), widget=SearchableSelectInput())
    environment = forms.ChoiceField(label="Ambiente", choices=ENVIRONMENT_CHOICES)
    rps_number = forms.IntegerField(label="Numero RPS", min_value=1, widget=NumberInput(attrs={"min": "1"}))
    rps_series = forms.CharField(label="Serie RPS", max_length=20, widget=TextInput())
    service_payload = forms.JSONField(label="Servico", widget=TextareaInput(rows=8), help_text="JSON com discriminacao, valor_servicos e classe_imposto ou impostos.")
    taker_payload = forms.JSONField(label="Tomador", widget=TextareaInput(rows=8), help_text="JSON com CPF/CNPJ e nome/razao social.")
    values_payload = forms.JSONField(label="Valores", widget=TextareaInput(rows=5), help_text='JSON com valor_servicos. Ex.: {"valor_servicos": "250.00"}')
    taxation_payload = forms.JSONField(label="Tributacao", widget=TextareaInput(rows=5), help_text="JSON com classe/regras fiscais; use ibs_cbs_required=true quando aplicavel.")
    retention_payload = forms.JSONField(label="Retencoes", required=False, widget=TextareaInput(rows=4))
    ibs_cbs_payload = forms.JSONField(label="IBS/CBS", required=False, widget=TextareaInput(rows=4))
    explicit_confirmation = forms.BooleanField(label="Confirmo que esta preview nao emite NFS-e nem transmite para a Webmania", required=True, widget=CheckboxInput())

    def __init__(self, *args: object, workshop=None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        if workshop is not None:
            self.fields["company"].queryset = WebmaniaCompany.objects.filter(workshop=workshop).order_by("razao_social", "webmania_company_id")
            self.fields["municipal_capability"].queryset = NfseMunicipalCapability.objects.filter(workshop=workshop, is_active=True).select_related("company").order_by("city_name", "state")

    def clean(self) -> dict[str, object]:
        cleaned = super().clean() or {}
        company = cleaned.get("company")
        capability = cleaned.get("municipal_capability")
        if isinstance(company, WebmaniaCompany) and company.workshop_id != getattr(self.workshop, "pk", None):
            self.add_error("company", "Empresa emissora pertence a outra oficina.")
        if isinstance(capability, NfseMunicipalCapability):
            if capability.workshop_id != getattr(self.workshop, "pk", None):
                self.add_error("municipal_capability", "Capacidade municipal pertence a outra oficina.")
            if isinstance(company, WebmaniaCompany) and capability.company_id != company.pk:
                self.add_error("municipal_capability", "Capacidade municipal deve pertencer a empresa emissora.")
        return cleaned
