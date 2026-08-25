from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm


class FiscalOperation:
    NORMAL = "normal"
    STANDALONE = "standalone"
    RETURN = "return"
    CORRECTION = "correction"
    COMPLEMENTARY = "complementary"
    ADJUSTMENT = "adjustment"


FISCAL_OPERATION_CHOICES: tuple[tuple[str, str], ...] = (
    (FiscalOperation.NORMAL, "NF-e Normal"),
    (FiscalOperation.STANDALONE, "Emissão avulsa"),
    (FiscalOperation.RETURN, "Nota de Devolução"),
    (FiscalOperation.CORRECTION, "Carta de Correção"),
    (FiscalOperation.COMPLEMENTARY, "Nota Complementar"),
    (FiscalOperation.ADJUSTMENT, "Nota de Ajuste"),
)


class FiscalOperationGatewayForm(CoreForm):
    operation = forms.ChoiceField(
        label="Tipo de operação",
        choices=FISCAL_OPERATION_CHOICES,
        widget=forms.RadioSelect,
    )
