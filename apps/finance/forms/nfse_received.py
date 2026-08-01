from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.finance.models.finance import WebmaniaCompany
from apps.finance.services.nfse_received_batch import MAX_NFSE_RECEIVED_BATCH_FILE_SIZE, MAX_NFSE_RECEIVED_BATCH_FILES, MAX_NFSE_RECEIVED_BATCH_TOTAL_SIZE


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return super().clean(data, initial)
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(file, initial) for file in files if file is not None]


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


class NfseReceivedDocumentBatchUploadForm(CoreForm):
    company = forms.ModelChoiceField(label="Empresa", queryset=WebmaniaCompany.objects.none(), required=True)
    xml_files = MultipleFileField(label="XMLs da NFS-e recebida", required=True, widget=MultipleFileInput(attrs={"multiple": True}))
    confirmed = forms.BooleanField(label="Confirmo que o lote usa somente XMLs recebidos e não executa consulta ou manifestação automatica.", required=True)

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        if workshop is not None:
            self.fields["company"].queryset = WebmaniaCompany.objects.filter(workshop=workshop, nfse_received_import_enabled=True).order_by("razao_social", "nome_completo", "pk")

    def clean_xml_files(self):
        files = self.cleaned_data["xml_files"]
        if len(files) > MAX_NFSE_RECEIVED_BATCH_FILES:
            raise forms.ValidationError(f"O lote deve ter no maximo {MAX_NFSE_RECEIVED_BATCH_FILES} arquivos.")
        total_size = 0
        for xml_file in files:
            total_size += xml_file.size
            if not xml_file.name.lower().endswith(".xml"):
                raise forms.ValidationError("Todos os arquivos devem ter extensão .xml.")
            if xml_file.size == 0:
                raise forms.ValidationError("Arquivos vazios não são aceitos.")
            if xml_file.size > MAX_NFSE_RECEIVED_BATCH_FILE_SIZE:
                raise forms.ValidationError("Cada XML deve ter no maximo 2 MB.")
        if total_size > MAX_NFSE_RECEIVED_BATCH_TOTAL_SIZE:
            raise forms.ValidationError("O tamanho total do lote excede o limite permitido.")
        return files


class NfseExternalXmlInboxUploadForm(CoreForm):
    company = forms.ModelChoiceField(label="Empresa", queryset=WebmaniaCompany.objects.none(), required=True)
    source_label = forms.CharField(label="Origem declarada", required=False, max_length=120, help_text="Ex.: anexos recebidos por e-mail, exportacao manual de ERP ou arquivo operacional da oficina.")
    xml_files = MultipleFileField(label="XMLs candidatos", required=True, widget=MultipleFileInput(attrs={"multiple": True}))
    confirmed = forms.BooleanField(label="Confirmo que a inbox não importa automaticamente, não consulta e não manifesta documentos.", required=True)

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        if workshop is not None:
            self.fields["company"].queryset = WebmaniaCompany.objects.filter(workshop=workshop, nfse_external_xml_inbox_enabled=True).order_by("razao_social", "nome_completo", "pk")

    def clean_xml_files(self):
        files = self.cleaned_data["xml_files"]
        if len(files) > MAX_NFSE_RECEIVED_BATCH_FILES:
            raise forms.ValidationError(f"A inbox deve receber no maximo {MAX_NFSE_RECEIVED_BATCH_FILES} arquivos por envio.")
        total_size = sum(xml_file.size for xml_file in files)
        if total_size > MAX_NFSE_RECEIVED_BATCH_TOTAL_SIZE:
            raise forms.ValidationError("O tamanho total do envio excede o limite permitido.")
        return files


class NfseExternalXmlInboxDiscardForm(CoreForm):
    reason = forms.CharField(label="Motivo do descarte", required=True, max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))
