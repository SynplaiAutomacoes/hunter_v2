from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import CheckboxInput, NumberInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models.finance import NfseItem, NfseItemStatus


class NfseSubstitutionPreviewCreateForm(CoreForm):
    original_nfse = forms.ModelChoiceField(label="NFS-e original autorizada", queryset=NfseItem.objects.none(), widget=SearchableSelectInput())
    environment = forms.ChoiceField(label="Ambiente", choices=(("1", "Producao"), ("2", "Homologacao")), widget=SearchableSelectInput(choices=(("1", "Producao"), ("2", "Homologacao"))))
    reason_code = forms.ChoiceField(label="Motivo", choices=((1, "Erro na emissao"), (2, "Servico nao prestado"), (4, "Duplicidade da nota")), widget=SearchableSelectInput(choices=((1, "Erro na emissao"), (2, "Servico nao prestado"), (4, "Duplicidade da nota"))))
    rps_number = forms.IntegerField(label="Numero do novo RPS", min_value=1, widget=NumberInput(attrs={"min": "1"}))
    rps_series = forms.CharField(label="Serie do novo RPS", max_length=20, widget=TextInput())
    service_payload = forms.JSONField(label="Servico do novo RPS", widget=TextareaInput(rows=10), help_text="JSON explicito com discriminacao, valor_servicos e classe_imposto ou impostos/retenções.")
    taker_payload = forms.JSONField(label="Tomador do novo RPS", widget=TextareaInput(rows=8), help_text="JSON explicito com CPF/CNPJ e nome/razao social.")
    explicit_confirmation = forms.BooleanField(label="Confirmo que este e um novo RPS validado e que nenhuma substituicao sera transmitida nesta etapa", required=True, widget=CheckboxInput())

    def __init__(self, *args, workshop, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.fields["original_nfse"].queryset = NfseItem.objects.filter(workshop=workshop, status=NfseItemStatus.aprovado).exclude(verification_code="").exclude(xml_url="").select_related("request", "manual_emission").order_by("-id")

    def clean_original_nfse(self) -> NfseItem:
        item = self.cleaned_data["original_nfse"]
        if item.workshop_id != self.workshop.pk:
            raise forms.ValidationError("A NFS-e original pertence a outra oficina.")
        return item
