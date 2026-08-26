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


class GatewayStep:
    OPERATION = "operation"
    LINKAGE = "linkage"
    DOCUMENT = "document"


FISCAL_OPERATION_CHOICES: tuple[tuple[str, str], ...] = (
    (FiscalOperation.EMISSION, "Nota Fiscal"),
    (FiscalOperation.RETURN, "Nota de Devolução"),
    (FiscalOperation.CORRECTION, "Carta de Correção"),
    (FiscalOperation.COMPLEMENTARY, "Nota Complementar"),
    (FiscalOperation.ADJUSTMENT, "Nota de Ajuste"),
)

EMISSION_LINKAGE_CHOICES: tuple[tuple[str, str], ...] = (
    (EmissionLinkage.WORKORDER, "Vinculada a uma O.S."),
    (EmissionLinkage.STANDALONE, "Emissão avulsa"),
)

NOTE_DOCUMENT_CHOICES: tuple[tuple[str, str], ...] = (
    (NoteDocument.NFE, "Produto (NF-e)"),
    (NoteDocument.NFSE, "Serviço (NFS-e)"),
)

DOCUMENT_OPERATIONS: frozenset[str] = frozenset({FiscalOperation.EMISSION})
NOTE_DOCUMENTS: frozenset[str] = frozenset({NoteDocument.NFE, NoteDocument.NFSE})
LINKAGE_VALUES: frozenset[str] = frozenset({EmissionLinkage.WORKORDER, EmissionLinkage.STANDALONE})


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
    gateway_step = forms.ChoiceField(
        choices=(
            (GatewayStep.OPERATION, "Operação"),
            (GatewayStep.LINKAGE, "Vínculo"),
            (GatewayStep.DOCUMENT, "Documento"),
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
        gateway_step = str(cleaned_data.get("gateway_step") or GatewayStep.OPERATION).strip()
        if gateway_step not in {GatewayStep.OPERATION, GatewayStep.LINKAGE, GatewayStep.DOCUMENT}:
            gateway_step = GatewayStep.OPERATION
        cleaned_data["gateway_step"] = gateway_step

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
