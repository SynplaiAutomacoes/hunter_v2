from __future__ import annotations

from django import forms

from apps.core.forms import CoreForm
from apps.finance.models.finance import WebmaniaCompany


class NfseReceivedDocumentUploadForm(CoreForm):
    company = forms.ModelChoiceField(label="Empresa", queryset=WebmaniaCompany.objects.none(), required=True)
    xml_file = forms.FileField(label="XML da NFS-e recebida", required=True)
    confirmed = forms.BooleanField(label="Confirmo que este XML representa uma NFS-e recebida de terceiro.", required=True)

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        if workshop is not None:
            self.fields["company"].queryset = WebmaniaCompany.objects.filter(workshop=workshop, nfse_received_import_enabled=True).order_by("razao_social", "nome_completo", "pk")

    def clean_xml_file(self):
        xml_file = self.cleaned_data["xml_file"]
        if not xml_file.name.lower().endswith(".xml"):
            raise forms.ValidationError("Envie um arquivo XML.")
        if xml_file.size > 2 * 1024 * 1024:
            raise forms.ValidationError("O XML deve ter no maximo 2 MB.")
        return xml_file
