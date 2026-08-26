from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.product_issues import normalize_ncm
from apps.core.presentation.forms import AddressFormMixin, CoreForm, address_layout
from apps.core.presentation.widgets import (
    CPForCNPJInput,
    DecimalInput,
    EmailInput,
    NumberInput,
    PhoneInput,
    RadioButtonGroupInput,
    SearchableSelectInput,
    TextInput,
)
from apps.finance.nfe_transport import BRAZILIAN_STATE_CHOICES
from apps.finance.services.fiscal_recipient import validate_recipient_snapshot
from apps.finance.services.standalone_emission import normalize_note_mode


def _pricing_layout_fields() -> tuple[Field, Field, Field, Field]:
    return (
        Field("quantity", wrapper_class="col-span-12 sm:col-span-3"),
        Field("cost_value", wrapper_class="col-span-12 sm:col-span-3"),
        Field("unit_value", wrapper_class="col-span-12 sm:col-span-3"),
        Field("total_value", wrapper_class="col-span-12 sm:col-span-3"),
    )


def _resolve_unit_value(*, quantity: int | Decimal, unit_value: object, total_value: object) -> Decimal:
    qty = Decimal(str(quantity if quantity and quantity > 0 else 1))
    try:
        unit = Decimal(str(unit_value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        unit = Decimal("0")
    if unit > 0:
        return unit
    try:
        total = Decimal(str(total_value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        total = Decimal("0")
    if total > 0:
        return (total / qty).quantize(Decimal("0.01"))
    return Decimal("0")


def _line_pricing_snapshot(*, quantity: int | Decimal, cost_value: object, unit_value: Decimal) -> dict[str, str]:
    cost = Decimal("0")
    if cost_value not in (None, ""):
        try:
            cost = Decimal(str(cost_value))
        except (InvalidOperation, TypeError, ValueError):
            cost = Decimal("0")
    qty = Decimal(str(quantity or 0))
    total = (qty * unit_value).quantize(Decimal("0.01"))
    return {
        "quantity": str(int(qty)),
        "cost_value": str(cost),
        "unit_value": str(unit_value),
        "total_value": str(total),
    }


class StandaloneNoteModeForm(CoreForm):
    note_mode = forms.ChoiceField(
        label="Tipo de nota",
        choices=(
            ("nfe", "Nota Fiscal de Produto"),
            ("nfse", "Nota Fiscal de Serviço"),
            ("both", "Ambas"),
        ),
        widget=RadioButtonGroupInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Tipo de emissão avulsa</h2>"),
                HTML(
                    "<p class='text-base-content/70 mb-6'>Escolha quais notas serão emitidas sem Ordem de Serviço. "
                    "O destinatário informado não será cadastrado como cliente.</p>"
                ),
                Div(
                    HTML(
                        """
                        <div class="mb-3 flex items-center justify-between gap-3">
                            <div>
                                <p class="text-sm font-bold text-base-content">Tipo de Nota Fiscal</p>
                                <p class="text-xs text-base-content/60">Escolha se a emissão será de produtos, serviços ou ambas.</p>
                            </div>
                            <span class="material-icons text-base-content/40">receipt_long</span>
                        </div>
                        """
                    ),
                    Field("note_mode", label=False, help_text=False, wrapper_class="mb-0"),
                    css_class="rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm",
                ),
                HTML(
                    """
                    <div class="mt-6 rounded-2xl border border-base-300 bg-base-200/60 p-5 space-y-2">
                        <p class="text-sm font-semibold text-base-content">Como funciona</p>
                        <p class="text-sm text-base-content/70">
                            Informe o destinatário, adicione os itens e configure a emissão. Os dados fiscais
                            desta nota não criam um cliente no sistema.
                        </p>
                    </div>
                    """
                ),
                css_class="space-y-4",
            )
        )

    def clean_note_mode(self) -> str:
        note_mode = normalize_note_mode(self.cleaned_data.get("note_mode"))
        if not note_mode:
            raise forms.ValidationError("Selecione o tipo de nota fiscal.")
        return note_mode


class StandaloneRecipientForm(AddressFormMixin, CoreForm):
    customer_type = forms.CharField(required=False, widget=forms.HiddenInput())
    cpf_or_cnpj = forms.CharField(label="CPF", required=True, widget=CPForCNPJInput(mode="both"))
    name = forms.CharField(label="Nome", required=True, widget=TextInput())
    phone = forms.CharField(label="Telefone", required=False, widget=PhoneInput())
    email = forms.EmailField(label="E-mail", required=False, widget=EmailInput())
    state_registration = forms.CharField(label="Inscrição Estadual", required=False, widget=TextInput())
    municipal_registration = forms.CharField(label="Inscrição Municipal", required=False, widget=TextInput())
    cep = forms.CharField(label="CEP", required=True)
    logradouro = forms.CharField(label="Logradouro", required=True, widget=TextInput())
    numero = forms.IntegerField(label="Número", required=True, min_value=1)
    complemento = forms.CharField(label="Complemento", required=False, widget=TextInput())
    bairro = forms.CharField(label="Bairro", required=True, widget=TextInput())
    cidade = forms.CharField(label="Cidade", required=True, widget=TextInput())
    estado = forms.ChoiceField(label="Estado", required=True, choices=BRAZILIAN_STATE_CHOICES, widget=SearchableSelectInput(choices=BRAZILIAN_STATE_CHOICES))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_address_fields()

        initial_customer_type = str(self.data.get("customer_type") or self.initial.get("customer_type") or "PF").upper()
        if initial_customer_type not in {"PF", "PJ"}:
            initial_customer_type = "PF"
        self.fields["customer_type"].required = False
        self.fields["customer_type"].initial = initial_customer_type
        self.initial["customer_type"] = initial_customer_type
        self.fields["cpf_or_cnpj"].widget.mode = "cnpj" if initial_customer_type == "PJ" else "cpf"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold col-span-12'>Destinatário da nota</h2>"),
                HTML(
                    "<p class='text-base-content/70 mb-2 col-span-12'>Informe os dados fiscais de quem receberá a nota.</p>"
                    "<p class='text-sm font-semibold text-warning mb-4 col-span-12'>Este destinatário não será cadastrado como cliente.</p>"
                ),
                HTML(
                    f"""
                    <div
                        x-data="{{ tipo: '{initial_customer_type}' }}"
                        class="col-span-12 grid grid-cols-1 lg:grid-cols-12 gap-2"
                    >
                    """
                ),
                HTML(
                    """
                    <div class="col-span-12 flex flex-wrap items-center gap-4 pb-1">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input
                                type="radio"
                                class="radio radio-primary"
                                value="PF"
                                x-model="tipo"
                            >
                            <span class="font-medium">Pessoa Física</span>
                        </label>

                        <label class="flex items-center gap-2 cursor-pointer">
                            <input
                                type="radio"
                                class="radio radio-primary"
                                value="PJ"
                                x-model="tipo"
                            >
                            <span class="font-medium">Pessoa Jurídica</span>
                        </label>

                        <input type="hidden" name="customer_type" :value="tipo">
                    </div>
                    """
                ),
                HTML('<h3 class="text-xl font-bold col-span-12">Dados Gerais</h3>'),
                Div(
                    Field("cpf_or_cnpj", wrapper_class="col-span-12"),
                    x_init="""
                                const syncDocumentField = value => {
                                    const hiddenInput = $el.querySelector('input[type="hidden"][name="cpf_or_cnpj"]');
                                    const widgetRoot = hiddenInput ? hiddenInput.closest('[x-data]') : null;
                                    if (!widgetRoot || !window.Alpine) return;

                                    const widget = Alpine.$data(widgetRoot);
                                    widget.docMode = value === 'PJ' ? 'cnpj' : 'cpf';

                                    let digits = (hiddenInput.value || '').replace(/\\D/g, '');
                                    digits = digits.slice(0, widget.maxDigitsForMode(digits));
                                    hiddenInput.value = digits;

                                    const displayInput = widgetRoot.querySelector('input[type="text"]');
                                    if (displayInput) {
                                        displayInput.value = widget.format(digits);
                                    }
                                };

                                $watch('tipo', value => {
                                    let label = $el.querySelector('label');
                                    if (label) {
                                        label.firstChild.textContent = value === 'PJ' ? 'CNPJ ' : 'CPF ';
                                    }
                                    syncDocumentField(value);
                                });
                                let label = $el.querySelector('label');
                                if (label) {
                                    label.firstChild.textContent = tipo === 'PJ' ? 'CNPJ ' : 'CPF ';
                                }
                                $nextTick(() => syncDocumentField(tipo));
                            """,
                    css_class="col-span-12 lg:col-span-6",
                ),
                Div(
                    Field("name", wrapper_class="col-span-12"),
                    x_init="""
                                $watch('tipo', value => {
                                    let label = $el.querySelector('label');
                                    if (label) {
                                        label.firstChild.textContent = value === 'PJ' ? 'Razão Social ' : 'Nome ';
                                    }
                                });
                                let label = $el.querySelector('label');
                                if (label) {
                                    label.firstChild.textContent = tipo === 'PJ' ? 'Razão Social ' : 'Nome ';
                                }
                            """,
                    css_class="col-span-12 lg:col-span-6",
                ),
                Field("phone", wrapper_class="col-span-12 lg:col-span-6"),
                Field("email", wrapper_class="col-span-12 lg:col-span-6"),
                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-6">'),
                Field("state_registration", wrapper_class="col-span-12"),
                HTML("</div>"),
                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-6">'),
                Field("municipal_registration", wrapper_class="col-span-12"),
                HTML("</div>"),
                HTML('<div class="col-span-12 divider my-1"></div>'),
                address_layout(),
                HTML("</div>"),
                css_class="grid grid-cols-12 gap-2",
            )
        )

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        snapshot = {
            "customer_type": str(cleaned_data.get("customer_type") or "PF").upper(),
            "name": str(cleaned_data.get("name") or "").strip(),
            "cpf_or_cnpj": "".join(char for char in str(cleaned_data.get("cpf_or_cnpj") or "") if char.isdigit()),
            "phone": str(cleaned_data.get("phone") or "").strip(),
            "email": str(cleaned_data.get("email") or "").strip(),
            "logradouro": str(cleaned_data.get("logradouro") or "").strip(),
            "numero": cleaned_data.get("numero"),
            "complemento": str(cleaned_data.get("complemento") or "").strip(),
            "bairro": str(cleaned_data.get("bairro") or "").strip(),
            "cidade": str(cleaned_data.get("cidade") or "").strip(),
            "estado": str(cleaned_data.get("estado") or "").strip(),
            "cep": "".join(char for char in str(cleaned_data.get("cep") or "") if char.isdigit()),
            "state_registration": str(cleaned_data.get("state_registration") or "").strip(),
            "municipal_registration": str(cleaned_data.get("municipal_registration") or "").strip(),
        }
        for field_name, messages in validate_recipient_snapshot(snapshot).items():
            for message in messages:
                self.add_error(field_name if field_name in self.fields else None, message)
        cleaned_data["recipient_snapshot"] = snapshot
        return cleaned_data


class StandaloneAddProductForm(CoreForm):
    product = forms.ModelChoiceField(label="Produto", queryset=Product.objects.none(), widget=SearchableSelectInput())
    quantity = forms.IntegerField(
        label="Quantidade",
        min_value=0,
        initial=1,
        widget=NumberInput(mode="positive"),
    )
    cost_value = forms.DecimalField(
        label="Custo",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    unit_value = forms.DecimalField(
        label="Valor unitário de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    total_value = forms.DecimalField(
        label="Valor total de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        if workshop is not None:
            self.fields["product"].queryset = Product.objects.filter(workshop=workshop, is_active=True).order_by("name")
            self.fields["product"].widget = SearchableSelectInput(choices=self.fields["product"].choices)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("product", wrapper_class="col-span-12"),
                *_pricing_layout_fields(),
                css_class="grid grid-cols-1 sm:grid-cols-12 gap-3",
            )
        )


class StandaloneAddServiceForm(CoreForm):
    service = forms.ModelChoiceField(label="Serviço", queryset=Service.objects.none(), widget=SearchableSelectInput())
    quantity = forms.IntegerField(
        label="Quantidade",
        min_value=0,
        initial=1,
        widget=NumberInput(mode="positive"),
    )
    cost_value = forms.DecimalField(
        label="Custo",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    unit_value = forms.DecimalField(
        label="Valor unitário de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    total_value = forms.DecimalField(
        label="Valor total de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        if workshop is not None:
            self.fields["service"].queryset = Service.objects.filter(workshop=workshop, is_active=True).order_by("name")
            self.fields["service"].widget = SearchableSelectInput(choices=self.fields["service"].choices)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("service", wrapper_class="col-span-12"),
                *_pricing_layout_fields(),
                css_class="grid grid-cols-1 sm:grid-cols-12 gap-3",
            )
        )


class StandaloneManualProductForm(CoreForm):
    description = forms.CharField(label="Descrição", max_length=255, widget=TextInput())
    product_code = forms.CharField(label="Código", max_length=120, widget=TextInput())
    ncm = forms.CharField(label="NCM", max_length=10, required=False, widget=TextInput())
    unit = forms.CharField(label="Unidade", max_length=12, initial="UN", widget=TextInput())
    quantity = forms.IntegerField(
        label="Quantidade",
        min_value=0,
        initial=1,
        widget=NumberInput(mode="positive"),
    )
    cost_value = forms.DecimalField(
        label="Custo",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    unit_value = forms.DecimalField(
        label="Valor unitário de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    total_value = forms.DecimalField(
        label="Valor total de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("description", wrapper_class="col-span-12"),
                Field("product_code", wrapper_class="col-span-12 sm:col-span-4"),
                Field("ncm", wrapper_class="col-span-12 sm:col-span-4"),
                Field("unit", wrapper_class="col-span-12 sm:col-span-4"),
                *_pricing_layout_fields(),
                css_class="grid grid-cols-1 sm:grid-cols-12 gap-3",
            )
        )

    def clean_ncm(self):
        return normalize_ncm(self.cleaned_data.get("ncm"))


class StandaloneManualServiceForm(CoreForm):
    description = forms.CharField(label="Descrição", max_length=255, widget=TextInput())
    quantity = forms.IntegerField(
        label="Quantidade",
        min_value=0,
        initial=1,
        widget=NumberInput(mode="positive"),
    )
    cost_value = forms.DecimalField(
        label="Custo",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    unit_value = forms.DecimalField(
        label="Valor unitário de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        widget=DecimalInput(min_value=0, decimal_places=2),
    )
    total_value = forms.DecimalField(
        label="Valor total de venda",
        min_value=Decimal("0"),
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        widget=DecimalInput(min_value=0, decimal_places=2),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("description", wrapper_class="col-span-12"),
                *_pricing_layout_fields(),
                css_class="grid grid-cols-1 sm:grid-cols-12 gap-3",
            )
        )


def build_standalone_items_form(*, note_mode: str, nfe_lines: list[dict[str, object]], nfse_lines: list[dict[str, object]]) -> type[CoreForm]:
    products_html = _render_product_lines_html(nfe_lines)
    services_html = _render_service_lines_html(nfse_lines)

    sections: list[str] = []
    if note_mode in {"nfe", "both"}:
        sections.append(
            f"""
            <div class="overflow-x-auto rounded-xl border border-base-300 bg-base-100/80 p-4">
                <div class="mb-3 flex items-center justify-between gap-2">
                    <h3 class="font-semibold">Produtos da NF-e</h3>
                    <span class="badge badge-ghost badge-sm">{len(nfe_lines)} item(ns)</span>
                </div>
                {products_html}
            </div>
            """
        )
    if note_mode in {"nfse", "both"}:
        sections.append(
            f"""
            <div class="overflow-x-auto rounded-xl border border-base-300 bg-base-100/80 p-4">
                <div class="mb-3 flex items-center justify-between gap-2">
                    <h3 class="font-semibold">Serviços da NFS-e</h3>
                    <span class="badge badge-ghost badge-sm">{len(nfse_lines)} item(ns)</span>
                </div>
                {services_html}
            </div>
            """
        )

    sections_wrapper = f'<div class="grid grid-cols-1 xl:grid-cols-2 gap-6">{"".join(sections)}</div>' if len(sections) > 1 else "".join(sections)

    class StandaloneItemsReviewForm(CoreForm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.helper = FormHelper()
            self.helper.form_tag = False
            self.helper.layout = Layout(
                Div(
                    HTML("<h3 class='text-lg font-semibold'>Itens adicionados</h3>"),
                    HTML("<p class='text-sm text-base-content/60 mb-4'>Revise a lista antes de continuar. Use Remover para ajustar.</p>"),
                    HTML(sections_wrapper),
                    css_class="space-y-2",
                )
            )

    return StandaloneItemsReviewForm


def _format_decimal(value: object) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (InvalidOperation, TypeError, ValueError):
        return str(value or "0,00")


def _line_has_invalid_ncm(line: dict[str, object]) -> bool:
    return len(normalize_ncm(line.get("ncm"))) != 8


def _ncm_warning_html(*, description: str) -> str:
    tip = escape("Produto com NCM invalido.")
    return (
        f'<span class="inline-flex items-center gap-2 min-w-0">'
        f'<span class="break-words whitespace-normal leading-snug">{escape(description)}</span>'
        f'<span class="tooltip tooltip-right shrink-0" data-tip="{tip}">'
        f'<span class="material-icons text-warning" style="font-size: 18px;">warning</span>'
        f"</span>"
        f"</span>"
    )


def _render_product_lines_html(lines: list[dict[str, object]]) -> str:
    if not lines:
        return (
            "<table class='table table-zebra w-full'>"
            "<tbody><tr><td class='text-base-content/60 py-4 text-center' colspan='6'>Nenhum produto adicionado.</td></tr></tbody>"
            "</table>"
        )

    rows = []
    grand_total = Decimal("0")
    for index, line in enumerate(lines):
        total = Decimal(str(line.get("total_value") or "0"))
        if total == 0:
            total = Decimal(str(line.get("quantity") or "0")) * Decimal(str(line.get("unit_value") or "0"))
        grand_total += total
        description = str(line.get("description") or "")
        description_html = _ncm_warning_html(description=description) if _line_has_invalid_ncm(line) else escape(description)
        rows.append(
            f"""
            <tr>
                <td class="py-2">{description_html}</td>
                <td class="py-2 text-center">{line.get('quantity')}</td>
                <td class="py-2 text-right">{_format_decimal(line.get('cost_value'))}</td>
                <td class="py-2 text-right">{_format_decimal(line.get('unit_value'))}</td>
                <td class="py-2 text-right font-semibold">{_format_decimal(total)}</td>
                <td class="py-2 text-center">
                    <button type="submit" name="remove_nfe_line" value="{index}" class="btn btn-ghost btn-xs text-error">Remover</button>
                </td>
            </tr>
            """
        )
    return f"""
    <table class="table table-zebra w-full">
        <thead>
            <tr>
                <th>Produto</th>
                <th class="text-center">Qtd</th>
                <th class="text-right">Custo</th>
                <th class="text-right">Unitário</th>
                <th class="text-right">Total</th>
                <th></th>
            </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
        <tfoot>
            <tr>
                <td colspan="4" class="text-right font-semibold">Total</td>
                <td class="text-right font-bold">{_format_decimal(grand_total)}</td>
                <td></td>
            </tr>
        </tfoot>
    </table>
    """


def _render_service_lines_html(lines: list[dict[str, object]]) -> str:
    if not lines:
        return (
            "<table class='table table-zebra w-full'>"
            "<tbody><tr><td class='text-base-content/60 py-4 text-center' colspan='6'>Nenhum serviço adicionado.</td></tr></tbody>"
            "</table>"
        )

    rows = []
    grand_total = Decimal("0")
    for index, line in enumerate(lines):
        total = Decimal(str(line.get("total_value") or "0"))
        if total == 0:
            total = Decimal(str(line.get("quantity") or "0")) * Decimal(str(line.get("unit_value") or "0"))
        grand_total += total
        rows.append(
            f"""
            <tr>
                <td class="py-2">{escape(str(line.get('description') or ''))}</td>
                <td class="py-2 text-center">{line.get('quantity')}</td>
                <td class="py-2 text-right">{_format_decimal(line.get('cost_value'))}</td>
                <td class="py-2 text-right">{_format_decimal(line.get('unit_value'))}</td>
                <td class="py-2 text-right font-semibold">{_format_decimal(total)}</td>
                <td class="py-2 text-center">
                    <button type="submit" name="remove_nfse_line" value="{index}" class="btn btn-ghost btn-xs text-error">Remover</button>
                </td>
            </tr>
            """
        )
    return f"""
    <table class="table table-zebra w-full">
        <thead>
            <tr>
                <th>Serviço</th>
                <th class="text-center">Qtd</th>
                <th class="text-right">Custo</th>
                <th class="text-right">Unitário</th>
                <th class="text-right">Total</th>
                <th></th>
            </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
        <tfoot>
            <tr>
                <td colspan="4" class="text-right font-semibold">Total</td>
                <td class="text-right font-bold">{_format_decimal(grand_total)}</td>
                <td></td>
            </tr>
        </tfoot>
    </table>
    """
