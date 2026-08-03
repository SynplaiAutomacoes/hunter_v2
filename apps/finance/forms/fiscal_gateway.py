from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.finance.models import NfeEmissionOrigin


class FiscalOperation:
    NORMAL = "normal"
    RETURN = "return"
    CORRECTION = "correction"
    COMPLEMENTARY = "complementary"
    ADJUSTMENT = "adjustment"
    TRANSPORT = "transport"


FISCAL_OPERATION_CHOICES: tuple[tuple[str, str], ...] = (
    (FiscalOperation.NORMAL, "Nota Fiscal de Saída"),
    (FiscalOperation.RETURN, "Devolução"),
    (FiscalOperation.CORRECTION, "Carta de Correção"),
    (FiscalOperation.COMPLEMENTARY, "Nota Complementar"),
    (FiscalOperation.ADJUSTMENT, "Nota de Ajuste"),
    (FiscalOperation.TRANSPORT, "Transporte"),
)

NFE_EMISSION_ORIGIN_CHOICES: tuple[tuple[str, str], ...] = tuple(NfeEmissionOrigin.choices)


class FiscalOperationGatewayForm(CoreForm):
    operation = forms.ChoiceField(
        label="Tipo de operação",
        choices=FISCAL_OPERATION_CHOICES,
        widget=forms.RadioSelect,
    )


class NfeEmissionOriginGatewayForm(CoreForm):
    origin = forms.ChoiceField(
        label="Origem da emissão",
        choices=NFE_EMISSION_ORIGIN_CHOICES,
        widget=forms.RadioSelect,
    )
