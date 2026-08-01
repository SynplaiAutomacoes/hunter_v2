from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from django import forms

from apps.catalog.models.products import Product
from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import CheckboxInput, NumberInput, SearchableSelectInput, TextareaInput
from apps.customer.models import Customer


class NfeManualEmissionForm(CoreForm):
    recipient = forms.ModelChoiceField(label="Destinatário", queryset=Customer.objects.none(), widget=SearchableSelectInput())
    tax_class = forms.ChoiceField(label="Classe de imposto", choices=[])
    additional_information = forms.CharField(label="Informações complementares", required=False, widget=TextareaInput(rows=4))
    confirmation = forms.BooleanField(label="Confirmo a emissão desta NF-e pela Webmania", widget=CheckboxInput())

    def __init__(self, *args: Any, workshop=None, tax_class_choices: list[tuple[str, str]] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        if workshop is not None:
            self.fields["recipient"].queryset = Customer.objects.filter(workshop=workshop, is_active=True).order_by("name")

        choices = [("", "Selecione a classe de imposto"), *(tax_class_choices or [])]
        self.fields["tax_class"].choices = choices
        self.fields["tax_class"].widget = SearchableSelectInput(choices=choices)
        self._valid_tax_class_refs = {value for value, _label in choices if value}

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        workshop_id = getattr(self.workshop, "pk", None)
        recipient = cleaned.get("recipient")
        if isinstance(recipient, Customer) and recipient.workshop_id != workshop_id:
            self.add_error("recipient", "O destinatário pertence a outra oficina.")
        tax_class = str(cleaned.get("tax_class") or "").strip()
        if self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            self.add_error("tax_class", "Selecione uma classe de imposto válida.")
        return cleaned


class NfeManualItemForm(CoreForm):
    product: forms.ModelChoiceField = forms.ModelChoiceField(label="Produto", queryset=Product.objects.none())
    quantity = forms.DecimalField(label="Quantidade", min_value=Decimal("0.0001"), max_digits=12, decimal_places=4, initial=Decimal("1.0000"), widget=NumberInput(attrs={"step": "0.0001"}))
    unit_price = forms.DecimalField(label="Valor unitário", min_value=Decimal("0.01"), max_digits=14, decimal_places=2, widget=NumberInput(attrs={"step": "0.01"}))

    def __init__(self, *args: Any, workshop=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        if workshop is not None:
            self.fields["product"].queryset = Product.objects.filter(workshop=workshop, is_active=True).order_by("name", "code")

    def clean_product(self) -> Product:
        product = cast(Product, self.cleaned_data["product"])
        if product.workshop_id != getattr(self.workshop, "pk", None):
            raise forms.ValidationError("O produto pertence a outra oficina.")
        return product


class BaseNfeManualItemFormSet(forms.BaseFormSet):
    def clean(self) -> None:
        super().clean()
        if any(self.errors):
            return

        product_ids: set[int] = set()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            if product is None:
                continue
            if product.pk in product_ids:
                raise forms.ValidationError("Cada produto deve aparecer somente uma vez na emissão.")
            product_ids.add(product.pk)


NfeManualItemFormSet = forms.formset_factory(
    NfeManualItemForm,
    formset=BaseNfeManualItemFormSet,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
