from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.finance.forms.nfe_transport import clean_nfe_transport_form, configure_nfe_transport_form
from apps.finance.models import TransportRequest
from apps.stock.models import StockImportFiscalItem


class TransportSelectionForm(forms.Form):
    stock_import_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput())


class TransportItemsForm(forms.Form):
    def __init__(self, *args: Any, request_instance: TransportRequest, available_quantities: dict[int, Decimal], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.request_instance = request_instance
        self.available_quantities = available_quantities
        selected = {item.source_item_id: item.quantity for item in request_instance.items.all()}
        self.source_items = list(request_instance.source_stock_import.fiscal_items.select_related("stock_product__product").order_by("sequence"))
        for item in self.source_items:
            self.fields[self.field_name(item)] = forms.DecimalField(
                required=False,
                min_value=Decimal("0"),
                max_digits=15,
                decimal_places=4,
                initial=selected.get(item.pk),
                widget=forms.NumberInput(attrs={"class": "input input-bordered w-32 text-right", "step": "0.0001", "min": "0", "max": str(available_quantities.get(item.pk, Decimal("0")))}),
            )

    @staticmethod
    def field_name(item: StockImportFiscalItem) -> str:
        return f"quantity_{item.pk}"

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        has_quantity = False
        for item in self.source_items:
            field_name = self.field_name(item)
            quantity = cleaned_data.get(field_name) or Decimal("0")
            available = self.available_quantities.get(item.pk, Decimal("0"))
            if quantity > available:
                self.add_error(field_name, f"O estoque disponível é {available}.")
            if quantity > 0:
                has_quantity = True
        if not has_quantity:
            raise forms.ValidationError("Selecione ao menos um produto e informe uma quantidade maior que zero.")
        return cleaned_data

    def quantities(self) -> dict[int, Decimal]:
        return {item.pk: self.cleaned_data.get(self.field_name(item)) or Decimal("0") for item in self.source_items}


class TransportDataForm(CoreForm):
    additional_information = forms.CharField(label="Informações adicionais", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args: Any, request_instance: TransportRequest, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.initial.setdefault("additional_information", request_instance.additional_information)
        configure_nfe_transport_form(
            form=self,
            snapshot=request_instance.transport_snapshot,
            freight_mode=request_instance.freight_mode,
        )
        self.transport_snapshot: dict[str, Any] = {}

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data
        self.transport_snapshot = clean_nfe_transport_form(cleaned_data)
        if not self.transport_snapshot:
            raise forms.ValidationError("A Nota de Transporte exige uma modalidade com dados de transporte.")
        return cleaned_data


class TransportFiscalForm(CoreForm):
    operation_nature = forms.CharField(label="Natureza da operação", max_length=255)
    cfop = forms.CharField(label="CFOP da Nota de Transporte", min_length=4, max_length=4, widget=forms.TextInput(attrs={"inputmode": "numeric"}))
    tax_class = forms.CharField(label="Classe de imposto", max_length=120)
    def clean_cfop(self) -> str:
        cfop = str(self.cleaned_data["cfop"]).strip()
        if len(cfop) != 4 or not cfop.isdigit():
            raise forms.ValidationError("Informe um CFOP válido com 4 dígitos.")
        return cfop
