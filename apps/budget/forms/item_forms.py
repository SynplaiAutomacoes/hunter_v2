from django import forms
from django.forms import RadioSelect
from django.urls import reverse
from djmoney.forms import MoneyField
from djmoney.money import Money

from apps.budget.models import BudgetItem, BudgetItemBenefitType
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.presentation.widgets import CheckboxInput, DurationInput, MoneyInput, NumberInput, TextInput, SearchableSelectInput

from .shared import _budget_item_type
from apps.core.presentation.forms import CoreForm, CoreModelForm


class BudgetItemEditForm(CoreModelForm):
    ncm = forms.CharField(required=False, widget=TextInput(attrs={"placeholder": "Ex: 87089990"}))

    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "is_customer_supplied", "product_selling_price", "product_cost_price", "shipping", "service_selling_price", "service_cost_price", "service_shipping", "duration", "ncm", "item_benefit_type"]

        widgets = {
            "description": TextInput(),
            "quantity": NumberInput(),
            "is_customer_supplied": CheckboxInput(),
            "product_selling_price": MoneyInput(),
            "product_cost_price": MoneyInput(),
            "shipping": MoneyInput(),
            "service_selling_price": MoneyInput(),
            "service_cost_price": MoneyInput(),
            "service_shipping": MoneyInput(),
            "duration": DurationInput(),
            "item_benefit_type": RadioSelect(),
        }

    def __init__(self, *args, budget_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        item = self.instance
        budget = getattr(item, "budget", None)
        is_fixed_budget = budget.is_fixed_budget if budget else False

        # Se budget for warranty/courtesy, o campo item_benefit_type é readonly
        if is_fixed_budget:
            self.fields["item_benefit_type"].disabled = True

        if "service_shipping" in self.fields:
            self.fields["service_shipping"].required = False

        # Se for kit, remover todos os campos de edição (kits usam modal próprio)
        if item.kit:
            fields_to_remove = ["service_selling_price", "service_cost_price", "service_shipping", "duration", "product_selling_price", "product_cost_price", "shipping", "is_customer_supplied"]
            for field in fields_to_remove:
                if field in self.fields:
                    self.fields.pop(field)
            return

        item_type = _budget_item_type(item)

        if item_type == "product":
            self.fields.pop("service_selling_price")
            self.fields.pop("service_cost_price")
            self.fields.pop("service_shipping")
            self.fields.pop("duration")
            if item.product is None:
                self.fields.pop("ncm")
            else:
                self.fields["ncm"].label = "NCM"
                self.fields["ncm"].initial = str(item.product.ncm or "")
        elif item_type == "service":
            self.fields.pop("product_selling_price")
            self.fields.pop("product_cost_price")
            self.fields.pop("shipping")
            self.fields.pop("is_customer_supplied")
            self.fields.pop("ncm")

            if budget_id:
                self.fields["duration"].widget.attrs.update(
                    {
                        "hx-post": reverse("budget:calculate_item", kwargs={"budget_id": budget_id, "item_id": item.id}),
                        "hx-trigger": "keyup changed delay:200ms",
                        "hx-target": "#div_id_service_cost_price",
                        "hx-swap": "outerHTML",
                        "hx-include": "closest form",
                        "hx-indicator": "#calculation-indicator",
                    }
                )
        else:
            self.fields.pop("is_customer_supplied")
            self.fields.pop("ncm")

    def clean_item_benefit_type(self):
        value = self.cleaned_data.get("item_benefit_type")
        item = self.instance
        budget_type = getattr(getattr(item, "budget", None), "budget_type", "sale")
        if budget_type == "warranty" and value != BudgetItemBenefitType.WARRANTY:
            raise forms.ValidationError("Itens em orçamento de garantia devem ser do tipo 'Garantia'.")
        if budget_type == "courtesy" and value != BudgetItemBenefitType.COURTESY:
            raise forms.ValidationError("Itens em orçamento de cortesia devem ser do tipo 'Cortesia'.")
        return value

    def clean_service_shipping(self):
        return self.cleaned_data.get("service_shipping") or Money(0, "BRL")


class BudgetKitProductEditRowForm(CoreForm):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    shipping = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "shipping"}))


class BudgetKitServiceEditRowForm(CoreForm):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    duration = forms.CharField(required=False, widget=DurationInput(attrs={"data-field": "duration"}))


class LocalProductForm(CoreModelForm):
    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "product_cost_price", "product_selling_price", "shipping", "item_benefit_type"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Parafuso XPTO"}),
            "quantity": NumberInput(),
            "product_cost_price": MoneyInput(),
            "product_selling_price": MoneyInput(),
            "shipping": MoneyInput(),
            "item_benefit_type": RadioSelect(),
        }

    def __init__(self, *args, is_warranty_budget=False, item_benefit_type="normal", **kwargs):
        super().__init__(*args, **kwargs)
        self._is_warranty_budget = is_warranty_budget
        self._expected_benefit_type = item_benefit_type
        self.fields["description"].label = "Descrição"
        self.fields["quantity"].label = "Quantidade"
        self.fields["product_cost_price"].label = "Custo"
        self.fields["shipping"].label = "Frete"

        # Disable item_benefit_type if budget is fixed
        if is_warranty_budget:
            self.fields["item_benefit_type"].disabled = True

        self.fields["product_selling_price"].label = "Valor de Venda"

    def clean_item_benefit_type(self):
        value = self.cleaned_data.get("item_benefit_type")
        if self._is_warranty_budget and value != "warranty":
            raise forms.ValidationError("Itens em orçamento de garantia devem ser do tipo 'Garantia'.")
        if self._expected_benefit_type == "courtesy" and value != "courtesy":
            raise forms.ValidationError("Itens em orçamento de cortesia devem ser do tipo 'Cortesia'.")
        return value


class LocalServiceForm(CoreModelForm):
    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "service_cost_price", "service_selling_price", "service_shipping", "duration", "item_benefit_type"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Serviço Especial Ferrari"}),
            "quantity": NumberInput(),
            "service_cost_price": MoneyInput(),
            "service_selling_price": MoneyInput(),
            "service_shipping": MoneyInput(),
            "duration": DurationInput(),
            "item_benefit_type": RadioSelect(),
        }

    def __init__(self, *args, budget_id=None, is_warranty_budget=False, item_benefit_type="normal", **kwargs):
        super().__init__(*args, **kwargs)
        self._is_warranty_budget = is_warranty_budget
        self._expected_benefit_type = item_benefit_type
        self.fields["description"].label = "Descrição"
        self.fields["quantity"].label = "Quantidade"
        self.fields["service_cost_price"].label = "Custo"
        self.fields["service_shipping"].label = "Frete"
        self.fields["service_shipping"].required = False
        self.fields["duration"].label = "Duração"

        # Disable item_benefit_type if budget is fixed
        if is_warranty_budget:
            self.fields["item_benefit_type"].disabled = True

        self.fields["service_selling_price"].label = "Valor de Venda"

        # Adicionar cálculo automático
        if budget_id and not self.instance.pk:
            self.fields["duration"].widget.attrs.update(
                {
                    "hx-post": reverse("budget:calculate_local_service", kwargs={"budget_id": budget_id}),
                    "hx-trigger": "keyup changed delay:200ms",
                    "hx-target": "#div_id_service_cost_price",
                    "hx-swap": "outerHTML",
                    "hx-include": "closest form",
                    "hx-indicator": "#calculation-indicator",
                }
            )

    def clean_item_benefit_type(self):
        value = self.cleaned_data.get("item_benefit_type")
        if self._is_warranty_budget and value != "warranty":
            raise forms.ValidationError("Itens em orçamento de garantia devem ser do tipo 'Garantia'.")
        if self._expected_benefit_type == "courtesy" and value != "courtesy":
            raise forms.ValidationError("Itens em orçamento de cortesia devem ser do tipo 'Cortesia'.")
        return value

    def clean_service_shipping(self):
        return self.cleaned_data.get("service_shipping") or Money(0, "BRL")


class QuickProductForm(CoreModelForm):
    """Formulário simplificado para cadastro rápido de produtos (apenas campos obrigatórios)"""

    class Meta:
        model = Product
        fields = ["code", "unit", "name", "group", "cost_price", "selling_price", "ncm"]
        widgets = {
            "code": TextInput(attrs={"placeholder": "Ex: P001"}),
            "name": TextInput(attrs={"placeholder": "Ex: Filtro de Óleo"}),
            "unit": SearchableSelectInput(),
            "group": SearchableSelectInput(),
            "cost_price": MoneyInput(),
            "selling_price": MoneyInput(),
            "ncm": TextInput(attrs={"placeholder": "Ex: 87089990"}),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.similar_name_target_id = "product-name-suggestions"

        if workshop:
            self.fields["group"].queryset = CatalogGroup.objects.filter(workshop=workshop)

        self.fields["name"].widget.attrs.update(
            {
                "autocomplete": "off",
                "hx-get": reverse("catalog:product_search"),
                "hx-trigger": "keyup changed delay:400ms",
                "hx-target": f"#{self.similar_name_target_id}",
                "hx-swap": "innerHTML",
                "hx-vals": '{"quick_name_lookup": "1"}',
            }
        )

        # Labels
        self.fields["code"].label = "Código"
        self.fields["name"].label = "Nome do Produto"
        self.fields["unit"].label = "Unidade"
        self.fields["group"].label = "Grupo"
        self.fields["cost_price"].label = "Custo"
        self.fields["selling_price"].label = "Valor de Venda"
        self.fields["ncm"].label = "NCM"
        self.fields["ncm"].required = False

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name and self.workshop:
            qs = Product.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um produto com este nome.")
        return name

    def clean_code(self):
        code = self.cleaned_data.get("code")
        if code and self.workshop:
            qs = Product.objects.filter(workshop=self.workshop, code__iexact=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um produto cadastrado com este código.")
        return code


class QuickServiceForm(CoreModelForm):
    """Formulário simplificado para cadastro rápido de serviços (apenas campos obrigatórios)"""

    class Meta:
        model = Service
        fields = ["name", "duration", "selling_price"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Troca de Óleo"}),
            "duration": DurationInput(),
            "selling_price": MoneyInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.similar_name_target_id = "service-name-suggestions"

        self.fields["name"].widget.attrs.update(
            {
                "autocomplete": "off",
                "hx-get": reverse("catalog:services_search"),
                "hx-trigger": "keyup changed delay:500ms",
                "hx-target": f"#{self.similar_name_target_id}",
                "hx-swap": "innerHTML",
                "hx-vals": '{"target_id": "service-name-suggestions"}',
            }
        )

        # Labels
        self.fields["name"].label = "Nome do Serviço"
        self.fields["duration"].label = "Duração"
        self.fields["selling_price"].label = "Valor de Venda"

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name and self.workshop:
            qs = Service.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um serviço com este nome.")
        return name
