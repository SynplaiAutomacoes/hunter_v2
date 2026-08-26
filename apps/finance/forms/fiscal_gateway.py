from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm


class FiscalOperation:
    NFE = "nfe"
    NFSE = "nfse"
    RETURN = "return"
    CORRECTION = "correction"
    COMPLEMENTARY = "complementary"
    ADJUSTMENT = "adjustment"


class EmissionLinkage:
    WORKORDER = "workorder"
    STANDALONE = "standalone"


class GatewayStep:
    OPERATION = "operation"
    LINKAGE = "linkage"


FISCAL_OPERATION_CHOICES: tuple[tuple[str, str], ...] = (
    (FiscalOperation.NFE, "NF-e"),
    (FiscalOperation.NFSE, "NFS-e"),
    (FiscalOperation.RETURN, "Nota de Devolução"),
    (FiscalOperation.CORRECTION, "Carta de Correção"),
    (FiscalOperation.COMPLEMENTARY, "Nota Complementar"),
    (FiscalOperation.ADJUSTMENT, "Nota de Ajuste"),
)

EMISSION_LINKAGE_CHOICES: tuple[tuple[str, str], ...] = (
    (EmissionLinkage.WORKORDER, "Vinculada a uma O.S."),
    (EmissionLinkage.STANDALONE, "Emissão avulsa"),
)

DOCUMENT_OPERATIONS: frozenset[str] = frozenset({FiscalOperation.NFE, FiscalOperation.NFSE})


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
    gateway_step = forms.ChoiceField(
        choices=(
            (GatewayStep.OPERATION, "Operação"),
            (GatewayStep.LINKAGE, "Fluxo"),
        ),
        widget=forms.HiddenInput,
        initial=GatewayStep.OPERATION,
        required=False,
    )

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        operation = str(cleaned_data.get("operation") or "").strip()
        linkage = str(cleaned_data.get("linkage") or "").strip()
        gateway_step = str(cleaned_data.get("gateway_step") or GatewayStep.OPERATION).strip()
        if gateway_step not in {GatewayStep.OPERATION, GatewayStep.LINKAGE}:
            gateway_step = GatewayStep.OPERATION
        cleaned_data["gateway_step"] = gateway_step

        if operation not in DOCUMENT_OPERATIONS:
            cleaned_data["linkage"] = ""
            cleaned_data["gateway_step"] = GatewayStep.OPERATION
            return cleaned_data

        if gateway_step == GatewayStep.LINKAGE and linkage not in {EmissionLinkage.WORKORDER, EmissionLinkage.STANDALONE}:
            self.add_error("linkage", "Escolha se a emissão será vinculada a uma O.S. ou avulsa.")
        return cleaned_data
