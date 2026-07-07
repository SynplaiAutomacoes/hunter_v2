from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import CheckboxInput, NumberInput, SearchableSelectInput
from apps.finance.models.finance import FiscalHypothesis, FiscalReferencedBasis, FiscalReferencedBasisStatus


class FiscalCreditProductPreviewCreateForm(CoreForm):
    basis = forms.ModelChoiceField(label="Base fiscal aprovada", queryset=FiscalReferencedBasis.objects.none(), widget=SearchableSelectInput())
    product_cfop = forms.CharField(label="CFOP definido para a previa", min_length=4, max_length=4)
    product_quantity = forms.DecimalField(label="Quantidade explicita", min_value=0.000001, max_digits=18, decimal_places=6, widget=NumberInput(attrs={"step": "0.000001", "min": "0.000001"}))
    product_unit_price = forms.DecimalField(label="Valor unitario explicito", min_value=0.01, max_digits=18, decimal_places=2, widget=NumberInput(attrs={"step": "0.01", "min": "0.01"}))
    product_total_amount = forms.DecimalField(label="Total explicito", min_value=0.01, max_digits=18, decimal_places=2, widget=NumberInput(attrs={"step": "0.01", "min": "0.01"}))
    explicit_value_confirmation = forms.BooleanField(
        label="Confirmo que quantidade, valor unitario, total e CFOP foram definidos explicitamente para esta previa",
        required=True,
        widget=CheckboxInput(),
    )

    def __init__(self, *args, workshop, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.fields["basis"].queryset = FiscalReferencedBasis.objects.filter(
            workshop=workshop,
            status=FiscalReferencedBasisStatus.APPROVED,
            fiscal_hypothesis=FiscalHypothesis.CREDIT_FINE_INTEREST,
        ).select_related("commercial_item").order_by("-approved_at")
        self.fields["product_quantity"].help_text = "Nao ha quantidade padrao. Informe somente mediante criterio fiscal explicito."
        self.fields["product_total_amount"].help_text = "Deve fechar com quantidade x unitario e com multa + juros da base."

    def clean_basis(self) -> FiscalReferencedBasis:
        basis = self.cleaned_data["basis"]
        if basis.workshop_id != self.workshop.pk:
            raise forms.ValidationError("A base pertence a outra oficina.")
        return basis

