from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm


class FiscalOperation:
    EMISSION = "emission"
    RETURN = "return"
    CORRECTION = "correction"
    COMPLEMENTARY = "complementary"
    ADJUSTMENT = "adjustment"


class EmissionLinkage:
    WORKORDER = "workorder"
    STANDALONE = "standalone"


class NoteDocument:
    NFE = "nfe"
    NFSE = "nfse"


class CorrectionSource:
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"


class GatewayStep:
    OPERATION = "operation"
    LINKAGE = "linkage"
    DOCUMENT = "document"
    CORRECTION_SOURCE = "correction_source"


FISCAL_OPERATION_CHOICES: tuple[tuple[str, str], ...] = (
    (FiscalOperation.EMISSION, "Nota Fiscal"),
    (FiscalOperation.RETURN, "Nota de Devolução"),
    (FiscalOperation.CORRECTION, "Carta de Correção"),
)

EMISSION_LINKAGE_CHOICES: tuple[tuple[str, str], ...] = (
    (EmissionLinkage.WORKORDER, "Vinculada a uma O.S."),
    (EmissionLinkage.STANDALONE, "Emissão avulsa"),
)

NOTE_DOCUMENT_CHOICES: tuple[tuple[str, str], ...] = (
    (NoteDocument.NFE, "Produto (NF-e)"),
    (NoteDocument.NFSE, "Serviço (NFS-e)"),
)

CORRECTION_SOURCE_CHOICES: tuple[tuple[str, str], ...] = (
    (CorrectionSource.REGISTERED, "Já cadastrada"),
    (CorrectionSource.UNREGISTERED, "Não cadastrada"),
)

DOCUMENT_OPERATIONS: frozenset[str] = frozenset({FiscalOperation.EMISSION})
NOTE_DOCUMENTS: frozenset[str] = frozenset({NoteDocument.NFE, NoteDocument.NFSE})
LINKAGE_VALUES: frozenset[str] = frozenset({EmissionLinkage.WORKORDER, EmissionLinkage.STANDALONE})
CORRECTION_SOURCE_VALUES: frozenset[str] = frozenset({CorrectionSource.REGISTERED, CorrectionSource.UNREGISTERED})
GATEWAY_STEP_VALUES: frozenset[str] = frozenset(
    {GatewayStep.OPERATION, GatewayStep.LINKAGE, GatewayStep.DOCUMENT, GatewayStep.CORRECTION_SOURCE}
)


class FiscalOperationGatewayForm(CoreForm):
    operation = forms.ChoiceField(
        label="Tipo de operação",
        choices=FISCAL_OPERATION_CHOICES,
        widget=forms.RadioSelect,
    )
    linkage = forms.ChoiceField(
        label="Tipo de emissão",
        choices=EMISSION_LINKAGE_CHOICES,
        widget=forms.RadioSelect,
        required=False,
    )
    note_document = forms.ChoiceField(
        label="Tipo de nota",
        choices=NOTE_DOCUMENT_CHOICES,
        widget=forms.RadioSelect,
        required=False,
    )
    correction_source = forms.ChoiceField(
        label="Origem da nota",
        choices=CORRECTION_SOURCE_CHOICES,
        widget=forms.RadioSelect,
        required=False,
    )
    gateway_step = forms.ChoiceField(
        choices=(
            (GatewayStep.OPERATION, "Operação"),
            (GatewayStep.LINKAGE, "Vínculo"),
            (GatewayStep.DOCUMENT, "Documento"),
            (GatewayStep.CORRECTION_SOURCE, "Origem da CC"),
        ),
        widget=forms.HiddenInput,
        initial=GatewayStep.OPERATION,
        required=False,
    )

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        operation = str(cleaned_data.get("operation") or "").strip()
        linkage = str(cleaned_data.get("linkage") or "").strip()
        note_document = str(cleaned_data.get("note_document") or "").strip()
        correction_source = str(cleaned_data.get("correction_source") or "").strip()
        gateway_step = str(cleaned_data.get("gateway_step") or GatewayStep.OPERATION).strip()
        if gateway_step not in GATEWAY_STEP_VALUES:
            gateway_step = GatewayStep.OPERATION
        cleaned_data["gateway_step"] = gateway_step

        if operation == FiscalOperation.CORRECTION:
            cleaned_data["linkage"] = ""
            cleaned_data["note_document"] = ""
            if gateway_step == GatewayStep.CORRECTION_SOURCE:
                if correction_source not in CORRECTION_SOURCE_VALUES:
                    self.add_error("correction_source", "Escolha se a NF-e já está cadastrada no sistema ou não.")
                cleaned_data["correction_source"] = correction_source
            else:
                cleaned_data["correction_source"] = ""
                cleaned_data["gateway_step"] = GatewayStep.OPERATION
            return cleaned_data

        cleaned_data["correction_source"] = ""

        if operation not in DOCUMENT_OPERATIONS:
            cleaned_data["linkage"] = ""
            cleaned_data["note_document"] = ""
            cleaned_data["gateway_step"] = GatewayStep.OPERATION
            return cleaned_data

        if gateway_step == GatewayStep.LINKAGE and linkage not in LINKAGE_VALUES:
            self.add_error("linkage", "Escolha se a emissão será vinculada a uma O.S. ou avulsa.")

        if gateway_step == GatewayStep.DOCUMENT:
            if linkage not in LINKAGE_VALUES:
                self.add_error("linkage", "Escolha se a emissão será vinculada a uma O.S. ou avulsa.")
            if note_document not in NOTE_DOCUMENTS:
                self.add_error("note_document", "Escolha se a nota será de produto (NF-e) ou de serviço (NFS-e).")

        return cleaned_data
