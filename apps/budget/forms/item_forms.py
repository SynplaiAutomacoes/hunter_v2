from django import forms
from django.urls import reverse
from djmoney.forms import MoneyField

from apps.budget.models import BudgetItem
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.widgets import DurationInput, MoneyInput, NumberInput, SelectInput, TextInput

from .shared import _budget_item_type


class BudgetItemEditForm(forms.ModelForm):
    ncm = forms.CharField(required=False, widget=TextInput(attrs={"placeholder": "Ex: 87089990"}))

    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "product_selling_price", "product_cost_price", "shipping", "service_selling_price", "service_cost_price", "duration", "ncm"]

        widgets = {
            "description": TextInput(),
            "quantity": NumberInput(),
            "product_selling_price": MoneyInput(),
            "product_cost_price": MoneyInput(),
            "shipping": MoneyInput(),
            "service_selling_price": MoneyInput(),
            "service_cost_price": MoneyInput(),
            "duration": DurationInput(),
        }

    def __init__(self, *args, budget_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        item = self.instance

        # Se for kit, remover todos os campos de edição (kits usam modal próprio)
        if item.kit:
            fields_to_remove = ["service_selling_price", "service_cost_price", "duration", "product_selling_price", "product_cost_price", "shipping"]
            for field in fields_to_remove:
                if field in self.fields:
                    self.fields.pop(field)
            return

        item_type = _budget_item_type(item)

        if item_type == "product":
            self.fields.pop("service_selling_price")
            self.fields.pop("service_cost_price")
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
            self.fields.pop("ncm")


class BudgetKitProductEditRowForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    shipping = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "shipping"}))


class BudgetKitServiceEditRowForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    duration = forms.CharField(required=False, widget=DurationInput(attrs={"data-field": "duration"}))


class LocalProductForm(forms.ModelForm):
    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "product_cost_price", "product_selling_price", "shipping"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Parafuso XPTO"}),
            "quantity": NumberInput(),
            "product_cost_price": MoneyInput(),
            "product_selling_price": MoneyInput(),
            "shipping": MoneyInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].label = "Descrição"
        self.fields["quantity"].label = "Quantidade"
        self.fields["product_cost_price"].label = "Custo"
        self.fields["product_selling_price"].label = "Valor de Venda"
        self.fields["shipping"].label = "Frete"


class LocalServiceForm(forms.ModelForm):
    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "service_cost_price", "service_selling_price", "duration"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Serviço Especial Ferrari"}),
            "quantity": NumberInput(),
            "service_cost_price": MoneyInput(),
            "service_selling_price": MoneyInput(),
            "duration": DurationInput(),
        }

    def __init__(self, *args, budget_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].label = "Descrição"
        self.fields["quantity"].label = "Quantidade"
        self.fields["service_cost_price"].label = "Custo"
        self.fields["service_selling_price"].label = "Valor de Venda"
        self.fields["duration"].label = "Duração"

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


class QuickProductForm(forms.ModelForm):
    """Formulário simplificado para cadastro rápido de produtos (apenas campos obrigatórios)"""

    class Meta:
        model = Product
        fields = ["code", "unit", "name", "group", "cost_price", "selling_price", "ncm"]
        widgets = {
            "code": TextInput(attrs={"placeholder": "Ex: P001"}),
            "name": TextInput(attrs={"placeholder": "Ex: Filtro de Óleo"}),
            "unit": SelectInput(),
            "group": SelectInput(),
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


class QuickServiceForm(forms.ModelForm):
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
