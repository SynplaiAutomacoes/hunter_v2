from __future__ import annotations

from django import forms

from apps.core.forms import CoreModelForm
from apps.core.widgets import CheckboxInput, NumberInput, SearchableSelectInput, TextareaInput
from apps.finance.models.finance import FiscalDocument, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentStatus, FiscalDocumentType, FiscalReferencedBasis
from apps.finance.models.financial_movement import FinancialMovement
from apps.stock.models import StockMovement


class FiscalReferencedBasisCreateForm(CoreModelForm):
    confirm_preparation_only = forms.BooleanField(
        required=True,
        label="Confirmo que esta base nao emite NF-e de credito/debito",
        widget=CheckboxInput(),
    )

    class Meta:
        model = FiscalReferencedBasis
        fields = ["source_document", "source_item_sequence", "fiscal_hypothesis", "financial_reference", "stock_reference", "notes"]
        widgets = {
            "source_document": SearchableSelectInput(),
            "source_item_sequence": NumberInput(attrs={"min": 1, "max": 999}),
            "fiscal_hypothesis": SearchableSelectInput(),
            "financial_reference": SearchableSelectInput(),
            "stock_reference": SearchableSelectInput(),
            "notes": TextareaInput(rows=4),
        }

    def __init__(self, *args, workshop, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.fields["source_document"].queryset = FiscalDocument.objects.filter(
            workshop=workshop,
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.LOCAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            status=FiscalDocumentStatus.APPROVED,
        ).order_by("-criado_em")
        self.fields["financial_reference"].queryset = FinancialMovement.objects.filter(workshop=workshop).order_by("-criado_em")
        self.fields["stock_reference"].queryset = StockMovement.objects.filter(workshop=workshop).order_by("-criado_em")
        self.fields["financial_reference"].required = False
        self.fields["stock_reference"].required = False
        self.fields["notes"].help_text = "Registre a evidencia operacional/fiscal. A base nao autoriza emissao."

    def clean_source_document(self) -> FiscalDocument:
        document = self.cleaned_data["source_document"]
        if document.workshop_id != self.workshop.pk:
            raise forms.ValidationError("Documento fiscal de outra oficina.")
        return document
