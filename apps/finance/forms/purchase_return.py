from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.finance.models import PurchaseReturnItemKind, PurchaseReturnRequest
from apps.stock.models import StockImportFiscalItem


class PurchaseReturnSourceForm(CoreForm):
    access_key = forms.CharField(
        label="Chave de acesso da NF-e",
        max_length=44,
        min_length=44,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "placeholder": "Digite os 44 dígitos da chave"}),
    )

    def clean_access_key(self) -> str:
        access_key = str(self.cleaned_data["access_key"]).strip()
        if len(access_key) != 44 or not access_key.isdigit():
            raise forms.ValidationError("Informe uma chave de acesso válida com 44 dígitos.")
        return access_key


class PurchaseReturnSearchForm(CoreForm):
    supplier = forms.CharField(label="Fornecedor", required=False, max_length=255)
    number = forms.CharField(label="Número da NF-e", required=False, max_length=50)
    issued_from = forms.DateField(label="Emitida a partir de", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    issued_until = forms.DateField(label="Emitida até", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    product = forms.CharField(label="Produto", required=False, max_length=255)
    value_min = forms.DecimalField(label="Valor mínimo", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2)
    value_max = forms.DecimalField(label="Valor máximo", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2)
    access_key = forms.CharField(label="Chave de acesso (opcional)", required=False, max_length=44, widget=forms.TextInput(attrs={"inputmode": "numeric"}))

    def clean_access_key(self) -> str:
        access_key = str(self.cleaned_data.get("access_key") or "").strip()
        if access_key and (not access_key.isdigit() or len(access_key) > 44):
            raise forms.ValidationError("A chave deve conter somente números e ter até 44 dígitos.")
        return access_key

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        issued_from = cleaned_data.get("issued_from")
        issued_until = cleaned_data.get("issued_until")
        value_min = cleaned_data.get("value_min")
        value_max = cleaned_data.get("value_max")
        if issued_from and issued_until and issued_from > issued_until:
            self.add_error("issued_until", "A data final deve ser igual ou posterior à data inicial.")
        if value_min is not None and value_max is not None and value_min > value_max:
            self.add_error("value_max", "O valor máximo deve ser igual ou superior ao valor mínimo.")
        return cleaned_data


class PurchaseReturnSelectionForm(forms.Form):
    stock_import_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput())


class PurchaseReturnFiscalForm(CoreForm):
    operation_nature = forms.CharField(label="Natureza da operação", max_length=255)
    cfop = forms.CharField(label="CFOP da Nota de Devolução", min_length=4, max_length=8, widget=forms.TextInput(attrs={"inputmode": "numeric"}))
    tax_class = forms.CharField(label="Classe de imposto", required=False, max_length=120)
    additional_information = forms.CharField(label="Informações complementares", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_cfop(self) -> str:
        cfop = str(self.cleaned_data["cfop"]).strip()
        if not cfop.isdigit():
            raise forms.ValidationError("Informe o CFOP somente com números.")
        return cfop


class PurchaseReturnItemsForm(forms.Form):
    def __init__(self, *args: Any, request_instance: PurchaseReturnRequest, available_quantities: dict[int, Decimal], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.request_instance = request_instance
        self.available_quantities = available_quantities
        selected = {item.source_item_id: item.quantity for item in request_instance.items.all()}
        manual_item = request_instance.items.filter(kind=PurchaseReturnItemKind.MANUAL).order_by("pk").first()
        self.source_items = list(request_instance.source_stock_import.fiscal_items.select_related("stock_product__product").order_by("sequence"))
        for item in self.source_items:
            self.fields[self.field_name(item)] = forms.DecimalField(
                required=False,
                min_value=Decimal("0"),
                max_digits=15,
                decimal_places=4,
                initial=selected.get(item.pk),
                widget=forms.NumberInput(attrs={"class": "input input-bordered w-32 text-right", "step": "0.0001", "min": "0", "max": str(available_quantities.get(item.sequence, Decimal("0")))}),
            )
        self.fields["manual_enabled"] = forms.BooleanField(label="Adicionar produto avulso", required=False, initial=manual_item is not None)
        self.fields["manual_description"] = forms.CharField(label="Descrição", required=False, max_length=255, initial=getattr(manual_item, "description", ""))
        self.fields["manual_product_code"] = forms.CharField(label="Código", required=False, max_length=120, initial=getattr(manual_item, "product_code", ""))
        self.fields["manual_ncm"] = forms.CharField(label="NCM", required=False, max_length=10, initial=getattr(manual_item, "ncm", ""))
        self.fields["manual_cest"] = forms.CharField(label="CEST", required=False, max_length=10, initial=getattr(manual_item, "cest", ""))
        self.fields["manual_unit"] = forms.CharField(label="Unidade", required=False, max_length=12, initial=getattr(manual_item, "unit", "UN") or "UN")
        self.fields["manual_quantity"] = forms.DecimalField(label="Quantidade", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=4, initial=getattr(manual_item, "quantity", None), widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0"}))
        self.fields["manual_unit_value"] = forms.DecimalField(label="Valor unitário", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=4, initial=getattr(manual_item, "unit_value", None), widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0"}))
        self.fields["manual_cfop"] = forms.CharField(label="CFOP", required=False, max_length=8, initial=getattr(manual_item, "cfop", ""))
        self.fields["manual_origin"] = forms.IntegerField(label="Origem tributária", required=False, min_value=0, max_value=8, initial=getattr(manual_item, "origin", 0))
        self.fields["manual_tax_class"] = forms.CharField(label="Classe de imposto", required=False, max_length=120, initial=getattr(manual_item, "tax_class", ""))

    @staticmethod
    def field_name(item: StockImportFiscalItem) -> str:
        return f"quantity_{item.pk}"

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        has_quantity = False
        for item in self.source_items:
            field_name = self.field_name(item)
            quantity = cleaned_data.get(field_name) or Decimal("0")
            available = self.available_quantities.get(item.sequence, Decimal("0"))
            if quantity > available:
                self.add_error(field_name, f"O saldo disponível é {available}.")
            if quantity > 0:
                has_quantity = True
        manual_enabled = bool(cleaned_data.get("manual_enabled"))
        if manual_enabled:
            required_manual_fields = ("manual_description", "manual_ncm", "manual_unit", "manual_quantity", "manual_unit_value")
            for field_name in required_manual_fields:
                if cleaned_data.get(field_name) in (None, ""):
                    self.add_error(field_name, "Campo obrigatório para produto avulso.")
            if cleaned_data.get("manual_quantity") and cleaned_data["manual_quantity"] > 0:
                has_quantity = True
        if not has_quantity:
            raise forms.ValidationError("Selecione ao menos um produto ou adicione um produto avulso com quantidade maior que zero.")
        return cleaned_data

    def quantities(self) -> dict[int, Decimal]:
        return {item.pk: self.cleaned_data.get(self.field_name(item)) or Decimal("0") for item in self.source_items}

    def manual_items(self) -> list[dict[str, Any]]:
        if not self.cleaned_data.get("manual_enabled"):
            return []
        return [
            {
                "description": self.cleaned_data.get("manual_description"),
                "product_code": self.cleaned_data.get("manual_product_code"),
                "ncm": self.cleaned_data.get("manual_ncm"),
                "cest": self.cleaned_data.get("manual_cest"),
                "unit": self.cleaned_data.get("manual_unit"),
                "quantity": self.cleaned_data.get("manual_quantity"),
                "unit_value": self.cleaned_data.get("manual_unit_value"),
                "cfop": self.cleaned_data.get("manual_cfop"),
                "origin": self.cleaned_data.get("manual_origin") or 0,
                "tax_class": self.cleaned_data.get("manual_tax_class"),
            }
        ]
