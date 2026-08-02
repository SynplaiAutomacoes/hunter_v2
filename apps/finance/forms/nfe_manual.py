from __future__ import annotations

from decimal import Decimal
from typing import Any, TypedDict, cast

from django import forms

from apps.budget.forms.item_forms import QuickProductForm
from apps.catalog.models.products import Product
from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import BrlCurrencyInput, SearchableSelectInput, TextareaInput
from apps.customer.models import Customer
from apps.finance.models import NfeManualItemOrigin


class NfeTemporaryProductSnapshot(TypedDict):
    description: str
    code: str
    ncm: str
    unit: str
    origin_cst: int
    cest: str


class BrlDecimalField(forms.DecimalField):
    def to_python(self, value: Any) -> Decimal | None:  # type: ignore[override]
        if isinstance(value, str) and "," in value:
            value = value.replace(".", "").replace(",", ".")
        return super().to_python(value)


class WholeQuantityField(forms.DecimalField):
    def validate(self, value: Decimal | None) -> None:  # type: ignore[override]
        super().validate(value)
        if value is not None and value != value.to_integral_value():
            raise forms.ValidationError("Informe uma quantidade inteira.")


class NfeManualEmissionForm(CoreForm):
    recipient = forms.ModelChoiceField(label="Destinatário", queryset=Customer.objects.none(), widget=SearchableSelectInput())
    tax_class = forms.ChoiceField(label="Classe de imposto", choices=[])
    additional_information = forms.CharField(label="Informações complementares", required=False, widget=TextareaInput(rows=4))

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
        if tax_class and self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            self.add_error("tax_class", "Selecione uma classe de imposto válida.")
        return cleaned


class NfeManualQuickProductForm(QuickProductForm):
    SAVE_TO_CATALOG = "yes"
    USE_ONLY_IN_EMISSION = "no"

    save_to_catalog = forms.ChoiceField(
        label="Salvar este produto no cadastro?",
        choices=((SAVE_TO_CATALOG, "Sim"), (USE_ONLY_IN_EMISSION, "Não, usar somente nesta emissão")),
        initial=SAVE_TO_CATALOG,
        required=False,
        widget=forms.RadioSelect,
    )

    class Meta(QuickProductForm.Meta):
        fields = [*QuickProductForm.Meta.fields, "cest", "origin_cst"]

    def __init__(self, *args: Any, workshop=None, can_save_to_catalog: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, workshop=workshop, **kwargs)
        self.can_save_to_catalog = can_save_to_catalog
        self.fields["ncm"].required = True
        self.fields["cest"].required = False
        self.fields["origin_cst"].required = False
        self.fields["cest"].label = "CEST (opcional)"
        self.fields["origin_cst"].label = "Origem CST"
        self.order_fields(["save_to_catalog", "code", "name", "unit", "group", "cost_price", "selling_price", "ncm", "cest", "origin_cst"])

        if not can_save_to_catalog:
            self.fields["save_to_catalog"].choices = ((self.USE_ONLY_IN_EMISSION, "Não, usar somente nesta emissão"),)
            self.fields["save_to_catalog"].initial = self.USE_ONLY_IN_EMISSION

        if not self.should_save_to_catalog:
            self.fields["group"].required = False
            self.fields["cost_price"].required = False

    @property
    def should_save_to_catalog(self) -> bool:
        if self.is_bound:
            value = str(self.data.get(self.add_prefix("save_to_catalog")) or "")
            if value:
                return value == self.SAVE_TO_CATALOG
        return self.can_save_to_catalog

    def clean_save_to_catalog(self) -> str:
        value = str(self.cleaned_data.get("save_to_catalog") or "")
        if value:
            return value
        return self.SAVE_TO_CATALOG if self.can_save_to_catalog else self.USE_ONLY_IN_EMISSION

    def clean_origin_cst(self) -> int:
        value = self.cleaned_data.get("origin_cst")
        return int(value if value not in (None, "") else Product.OriginCST.NACIONAL)

    def clean_name(self) -> str:
        if self.should_save_to_catalog:
            return str(super().clean_name())
        return str(self.cleaned_data.get("name") or "")

    def clean_code(self) -> str:
        if self.should_save_to_catalog:
            return str(super().clean_code())
        return str(self.cleaned_data.get("code") or "")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if cleaned.get("save_to_catalog") == self.SAVE_TO_CATALOG and not self.can_save_to_catalog:
            self.add_error("save_to_catalog", "Você não possui permissão para salvar produtos no cadastro.")
        return cleaned

    def build_fiscal_snapshot(self) -> NfeTemporaryProductSnapshot:
        return {
            "description": str(self.cleaned_data["name"]),
            "code": str(self.cleaned_data["code"]),
            "ncm": str(self.cleaned_data["ncm"]),
            "unit": str(self.cleaned_data["unit"]),
            "origin_cst": int(self.cleaned_data["origin_cst"]),
            "cest": str(self.cleaned_data.get("cest") or ""),
        }


class NfeManualItemForm(CoreForm):
    item_origin = forms.ChoiceField(choices=NfeManualItemOrigin.choices, initial=NfeManualItemOrigin.CATALOG, required=False, widget=forms.HiddenInput())
    product: forms.ModelChoiceField = forms.ModelChoiceField(label="Produto", queryset=Product.objects.none(), required=False)
    fiscal_snapshot = forms.JSONField(required=False, widget=forms.HiddenInput())
    quantity = WholeQuantityField(
        label="Quantidade",
        min_value=Decimal("1"),
        max_digits=12,
        decimal_places=4,
        initial=Decimal("1"),
        widget=forms.NumberInput(attrs={"step": "1", "min": "1", "inputmode": "numeric"}),
    )
    unit_price = BrlDecimalField(label="Valor unitário", min_value=Decimal("0.01"), max_digits=14, decimal_places=2, widget=BrlCurrencyInput())

    def __init__(self, *args: Any, workshop=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        if workshop is not None:
            self.fields["product"].queryset = Product.objects.filter(workshop=workshop, is_active=True).order_by("name", "code")

    def clean_product(self) -> Product | None:
        product = cast(Product | None, self.cleaned_data.get("product"))
        if product is None:
            return None
        if product.workshop_id != getattr(self.workshop, "pk", None):
            raise forms.ValidationError("O produto pertence a outra oficina.")
        return product

    def clean_item_origin(self) -> str:
        return str(self.cleaned_data.get("item_origin") or NfeManualItemOrigin.CATALOG)

    def clean_fiscal_snapshot(self) -> dict[str, Any]:
        snapshot = self.cleaned_data.get("fiscal_snapshot")
        return snapshot if isinstance(snapshot, dict) else {}

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        item_origin = cleaned.get("item_origin")
        product = cleaned.get("product")
        fiscal_snapshot = cleaned.get("fiscal_snapshot")

        if item_origin == NfeManualItemOrigin.CATALOG and product is None:
            self.add_error("product", "Selecione um produto cadastrado.")
        if item_origin == NfeManualItemOrigin.TEMPORARY:
            if product is not None:
                self.add_error("product", "O produto temporário não pode estar vinculado ao catálogo.")
            if not fiscal_snapshot:
                self.add_error("fiscal_snapshot", "Informe os dados do produto temporário.")
        return cleaned


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
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
