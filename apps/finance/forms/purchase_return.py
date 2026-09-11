from __future__ import annotations

from decimal import Decimal
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import CPForCNPJInput, DecimalInput, NumberInput, SearchableSelectInput, TextareaInput, TextInput
from apps.customer.cpf_cnpj_validator import is_valid_cnpj
from apps.finance.forms.nfe_transport import build_nfe_transport_form_layout, clean_nfe_transport_form, configure_nfe_transport_form
from apps.finance.models import PurchaseReturnItemKind, PurchaseReturnRequest, TaxClassNfe
from apps.stock.models import StockImportFiscalItem

PRESENCE_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Não informar"),
    ("0", "0 - Não se aplica"),
    ("1", "1 - Operação presencial"),
    ("2", "2 - Operação não presencial, pela Internet"),
    ("3", "3 - Operação não presencial, Teleatendimento"),
    ("4", "4 - Entrega a domicílio"),
    ("5", "5 - Operação presencial, fora do estabelecimento"),
    ("9", "9 - Operação não presencial, outros"),
)

INTERMEDIARY_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Não informar"),
    ("0", "0 - Sem intermediador"),
    ("1", "1 - Operação em site ou plataforma de terceiros"),
)

PAYMENT_INDICATOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Não informar"),
    ("0", "0 - Pagamento à vista"),
    ("1", "1 - Pagamento a prazo"),
)

PAYMENT_METHOD_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Não informar"),
    ("01", "01 - Dinheiro"),
    ("02", "02 - Cheque"),
    ("03", "03 - Cartão de crédito"),
    ("04", "04 - Cartão de débito"),
    ("05", "05 - Cartão da loja / crediário"),
    ("10", "10 - Vale alimentação"),
    ("11", "11 - Vale refeição"),
    ("12", "12 - Vale presente"),
    ("13", "13 - Vale combustível"),
    ("14", "14 - Duplicata mercantil"),
    ("15", "15 - Boleto bancário"),
    ("16", "16 - Depósito bancário"),
    ("17", "17 - PIX dinâmico"),
    ("18", "18 - TED"),
    ("19", "19 - Programa de fidelidade / cashback"),
    ("20", "20 - PIX estático"),
    ("21", "21 - Crédito em loja"),
    ("22", "22 - Pagamento eletrônico não informado"),
    ("23", "23 - PIX automático"),
    ("24", "24 - TEF - Book Transfer"),
    ("90", "90 - Sem pagamento"),
    ("91", "91 - Pagamento posterior"),
    ("99", "99 - Outros"),
)


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


def _datetime_local_value(value: object) -> str:
    if value in (None, ""):
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M")
    return str(value)


def build_purchase_return_fiscal_initial(instance: PurchaseReturnRequest) -> dict[str, Any]:
    return {
        "operation_nature": instance.operation_nature,
        "cfop": instance.cfop,
        "tax_class": instance.tax_class,
        "additional_information": instance.additional_information,
        "fisco_information": instance.fisco_information,
        "volume": instance.volume,
        "freight_amount": instance.freight_amount,
        "discount_amount": instance.discount_amount,
        "accessory_expenses": instance.accessory_expenses,
        "insurance_amount": instance.insurance_amount,
        "customs_expenses": instance.customs_expenses,
        "total_override": instance.total_override,
        "presence": instance.presence,
        "intermediary": instance.intermediary,
        "intermediary_cnpj": instance.intermediary_cnpj,
        "intermediary_id": instance.intermediary_id,
        "purchase_order": instance.purchase_order,
        "contract": instance.contract,
        "commitment_note": instance.commitment_note,
        "payment_indicator": instance.payment_indicator,
        "payment_method": instance.payment_method,
        "payment_description": instance.payment_description,
        "payment_value": instance.payment_value,
        "payment_date": instance.payment_date,
        "issue_at": _datetime_local_value(instance.issue_at),
        "departure_at": _datetime_local_value(instance.departure_at),
        "delivery_forecast": instance.delivery_forecast,
    }


class PurchaseReturnFiscalForm(CoreForm):
    operation_nature = forms.CharField(
        label="Natureza da operação",
        max_length=60,
        help_text="Campo obrigatório da Webmania para /1/nfe/devolucao/.",
        widget=TextInput(),
    )
    cfop = forms.CharField(
        label="CFOP da Nota de Devolução",
        min_length=4,
        max_length=8,
        help_text="Campo obrigatório da Webmania. Informe somente números.",
        widget=forms.TextInput(attrs={"inputmode": "numeric"}),
    )
    tax_class = forms.CharField(label="Classe de imposto", required=False, max_length=30)
    additional_information = forms.CharField(label="Informações complementares", required=False, max_length=5000, widget=TextareaInput(rows=3))
    fisco_information = forms.CharField(label="Informações ao fisco", required=False, max_length=2000, widget=TextareaInput(rows=3))
    volume = forms.IntegerField(label="Quantidade de volumes", required=False, min_value=1, max_value=999999999999999, widget=NumberInput())
    freight_amount = forms.DecimalField(label="Frete", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2, widget=DecimalInput(min_value=0, decimal_places=2))
    discount_amount = forms.DecimalField(label="Desconto", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2, widget=DecimalInput(min_value=0, decimal_places=2))
    accessory_expenses = forms.DecimalField(label="Despesas acessórias", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2, widget=DecimalInput(min_value=0, decimal_places=2))
    insurance_amount = forms.DecimalField(label="Seguro", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2, widget=DecimalInput(min_value=0, decimal_places=2))
    customs_expenses = forms.DecimalField(label="Despesas aduaneiras", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2, widget=DecimalInput(min_value=0, decimal_places=2))
    total_override = forms.DecimalField(
        label="Total informado",
        required=False,
        min_value=Decimal("0"),
        max_digits=15,
        decimal_places=2,
        help_text="A Webmania calcula o total automaticamente. Preencha somente para substituir.",
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    presence = forms.ChoiceField(label="Indicador de presença", required=False, choices=PRESENCE_CHOICES, widget=SearchableSelectInput(choices=PRESENCE_CHOICES))
    intermediary = forms.ChoiceField(label="Intermediador / marketplace", required=False, choices=INTERMEDIARY_CHOICES, widget=SearchableSelectInput(choices=INTERMEDIARY_CHOICES))
    intermediary_cnpj = forms.CharField(label="CNPJ do intermediador", required=False, max_length=18, widget=CPForCNPJInput(mode="cnpj"))
    intermediary_id = forms.CharField(label="Identificador no intermediador", required=False, max_length=60, widget=TextInput())
    purchase_order = forms.CharField(label="Pedido de compra", required=False, max_length=60, widget=TextInput())
    contract = forms.CharField(label="Contrato", required=False, max_length=60, widget=TextInput())
    commitment_note = forms.CharField(label="Nota de empenho", required=False, max_length=22, widget=TextInput())
    payment_indicator = forms.ChoiceField(label="Indicador de pagamento", required=False, choices=PAYMENT_INDICATOR_CHOICES, widget=SearchableSelectInput(choices=PAYMENT_INDICATOR_CHOICES))
    payment_method = forms.ChoiceField(label="Meio de pagamento", required=False, choices=PAYMENT_METHOD_CHOICES, widget=SearchableSelectInput(choices=PAYMENT_METHOD_CHOICES))
    payment_description = forms.CharField(label="Descrição do pagamento", required=False, max_length=60, help_text="Obrigatório somente para o meio 99 - Outros.", widget=TextInput())
    payment_value = forms.DecimalField(label="Valor do pagamento", required=False, min_value=Decimal("0"), max_digits=15, decimal_places=2, widget=DecimalInput(min_value=0, decimal_places=2))
    payment_date = forms.DateField(label="Data do pagamento", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    issue_at = forms.DateTimeField(
        label="Data e hora de emissão",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    departure_at = forms.DateTimeField(
        label="Data e hora de entrada/saída",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    delivery_forecast = forms.DateField(label="Previsão de entrega", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args: Any, instance: PurchaseReturnRequest | None = None, **kwargs: Any) -> None:
        self.instance = instance
        if instance is not None:
            initial = build_purchase_return_fiscal_initial(instance)
            initial.update(kwargs.get("initial") or {})
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        tax_class_choices: list[tuple[str, str]] = [("", "Não informar classe de imposto")]
        if instance is not None and instance.workshop_id:
            tax_classes = TaxClassNfe.objects.filter(workshop_id=instance.workshop_id).order_by("reference")
            tax_class_choices.extend(
                (
                    tax_class.reference,
                    f"{tax_class.reference} - {tax_class.description}" if tax_class.description else tax_class.reference,
                )
                for tax_class in tax_classes
            )

        tax_class_field = self.fields["tax_class"]
        tax_class_field.widget = SearchableSelectInput(choices=tax_class_choices)
        tax_class_field.help_text = "Opcional. Selecione somente uma classe de NF-e sincronizada com a Webmania para esta oficina."
        self._valid_tax_class_refs = {reference for reference, _label in tax_class_choices if reference}

        current_tax_class = str((self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", "")) or "").strip()
        if not self.is_bound and current_tax_class and current_tax_class not in self._valid_tax_class_refs:
            self.initial["tax_class"] = ""

        configure_nfe_transport_form(
            form=self,
            snapshot=getattr(instance, "transport_snapshot", {}),
            freight_mode=getattr(instance, "freight_mode", 9),
        )
        self.fields["freight_mode"].required = False
        self.fields["freight_mode"].help_text = "Padrão 9 - Sem transporte. Preencha transportadora e volumes somente quando houver transporte."
        self.fields["tax_class"].required = False
        self.fields["additional_information"].required = False
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h3 class='text-lg font-semibold'>Dados fiscais da Nota de Devolução</h3>"),
                HTML("<p class='text-sm text-base-content/70'>Somente natureza da operação e CFOP são obrigatórios na emissão da devolução.</p>"),
                Div(
                    Field("operation_nature", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("cfop", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("volume", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("additional_information", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("fisco_information", wrapper_class="col-span-12 lg:col-span-6"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                css_class="space-y-4 rounded-xl border border-base-300 bg-base-200/30 p-5",
            ),
            Div(
                HTML("<h3 class='text-lg font-semibold'>Valores do pedido</h3>"),
                HTML("<p class='text-sm text-base-content/70'>Informe frete, desconto, seguro e despesas acessórias quando precisarem constar na Nota de Devolução.</p>"),
                Div(
                    Field("freight_amount", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("discount_amount", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("accessory_expenses", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("insurance_amount", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("customs_expenses", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("total_override", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                css_class="space-y-4 rounded-xl border border-base-300 bg-base-200/30 p-5",
            ),
            Div(
                HTML("<h3 class='text-lg font-semibold'>Presença, intermediador e referências</h3>"),
                Div(
                    Field("presence", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("intermediary", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("intermediary_cnpj", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("intermediary_id", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("purchase_order", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("contract", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("commitment_note", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                css_class="space-y-4 rounded-xl border border-base-300 bg-base-200/30 p-5",
            ),
            Div(
                HTML("<h3 class='text-lg font-semibold'>Pagamento</h3>"),
                HTML("<p class='text-sm text-base-content/70'>Opcional. Preencha somente se a devolução precisar declarar forma de pagamento, inclusive 90 - Sem pagamento.</p>"),
                Div(
                    Field("payment_indicator", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("payment_method", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("payment_value", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("payment_date", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("payment_description", wrapper_class="col-span-12 lg:col-span-8"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                css_class="space-y-4 rounded-xl border border-base-300 bg-base-200/30 p-5",
            ),
            Div(
                HTML("<h3 class='text-lg font-semibold'>Datas da nota</h3>"),
                HTML("<p class='text-sm text-base-content/70'>Opcional. A Webmania preenche automaticamente quando estes campos ficam vazios.</p>"),
                Div(
                    Field("issue_at", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("departure_at", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("delivery_forecast", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                css_class="space-y-4 rounded-xl border border-base-300 bg-base-200/30 p-5",
            ),
            build_nfe_transport_form_layout(),
        )

    def clean_cfop(self) -> str:
        cfop = str(self.cleaned_data["cfop"]).strip()
        if not cfop.isdigit():
            raise forms.ValidationError("Informe o CFOP somente com números.")
        return cfop

    def clean_tax_class(self) -> str:
        tax_class = str(self.cleaned_data.get("tax_class") or "").strip()
        if tax_class and tax_class not in self._valid_tax_class_refs:
            raise forms.ValidationError("Selecione uma classe de imposto sincronizada com a Webmania para esta oficina.")
        return tax_class

    def clean_intermediary_cnpj(self) -> str:
        digits = "".join(character for character in str(self.cleaned_data.get("intermediary_cnpj") or "") if character.isdigit())
        if digits and not is_valid_cnpj(digits):
            raise forms.ValidationError("Informe um CNPJ válido para o intermediador.")
        return digits

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        intermediary = str(cleaned_data.get("intermediary") or "").strip()
        if intermediary == "1":
            if not cleaned_data.get("intermediary_cnpj"):
                self.add_error("intermediary_cnpj", "Informe o CNPJ do intermediador.")
            if not str(cleaned_data.get("intermediary_id") or "").strip():
                self.add_error("intermediary_id", "Informe o identificador cadastrado no intermediador.")
        payment_method = str(cleaned_data.get("payment_method") or "").strip()
        if payment_method == "99" and not str(cleaned_data.get("payment_description") or "").strip():
            self.add_error("payment_description", "Informe a descrição do meio de pagamento 99 - Outros.")
        if payment_method == "01" and cleaned_data.get("payment_value") is None:
            self.add_error("payment_value", "Informe o valor do pagamento em dinheiro.")
        payment_fields = (cleaned_data.get("payment_indicator"), cleaned_data.get("payment_description"), cleaned_data.get("payment_value"), cleaned_data.get("payment_date"))
        if any(value not in (None, "") for value in payment_fields) and not payment_method:
            self.add_error("payment_method", "Selecione o meio de pagamento.")
        if not self.errors:
            cleaned_data["freight_mode"] = str(cleaned_data.get("freight_mode") or 9)
            cleaned_data["transport_snapshot"] = clean_nfe_transport_form(cleaned_data)
            cleaned_data["freight_mode"] = int(cleaned_data["freight_mode"])
        return cleaned_data

    def persistable_data(self) -> dict[str, Any]:
        return {field_name: self.cleaned_data.get(field_name) for field_name in PurchaseReturnRequest.FISCAL_CONFIGURATION_FIELDS}


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
