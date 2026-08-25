from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.presentation.forms import AddressFormMixin, CoreForm
from apps.core.presentation.widgets import CPForCNPJInput, EmailInput, PhoneInput, SearchableSelectInput, TextInput
from apps.finance.services.fiscal_recipient import validate_recipient_snapshot
from apps.finance.services.standalone_emission import normalize_note_mode


class StandaloneNoteModeForm(CoreForm):
    note_mode = forms.ChoiceField(
        label="Tipo de nota",
        choices=(
            ("nfe", "Nota Fiscal de Produto"),
            ("nfse", "Nota Fiscal de Serviço"),
            ("both", "Ambas"),
        ),
        widget=forms.RadioSelect,
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
                Field("note_mode"),
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
    estado = forms.CharField(label="Estado", required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_address_fields(include_complemento=True)

        initial_customer_type = str(self.data.get("customer_type") or self.initial.get("customer_type") or "PF").upper()
        if initial_customer_type not in {"PF", "PJ"}:
            initial_customer_type = "PF"
        self.initial["customer_type"] = initial_customer_type
        self.fields["cpf_or_cnpj"].widget.mode = "cnpj" if initial_customer_type == "PJ" else "cpf"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Destinatário da nota</h2>"),
                HTML(
                    "<p class='text-base-content/70 mb-2'>Informe os dados fiscais de quem receberá a nota.</p>"
                    "<p class='text-sm font-semibold text-warning mb-6'>Este destinatário não será cadastrado como cliente.</p>"
                ),
                HTML(
                    f"""
                    <div x-data="{{ tipo: '{initial_customer_type}' }}" class="space-y-4">
                        <div class="flex flex-wrap items-center gap-4">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" class="radio radio-primary" value="PF" x-model="tipo">
                                <span class="font-medium">Pessoa Física</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" class="radio radio-primary" value="PJ" x-model="tipo">
                                <span class="font-medium">Pessoa Jurídica</span>
                            </label>
                            <input type="hidden" name="customer_type" :value="tipo">
                        </div>
                    """
                ),
                Field("cpf_or_cnpj"),
                Field("name"),
                Field("phone"),
                Field("email"),
                HTML('<div x-show="tipo === \'PJ\'" class="grid grid-cols-1 md:grid-cols-2 gap-4">'),
                Field("state_registration"),
                Field("municipal_registration"),
                HTML("</div>"),
                Field("cep"),
                Field("logradouro"),
                Field("numero"),
                Field("complemento"),
                Field("bairro"),
                Field("cidade"),
                Field("estado"),
                HTML("</div>"),
                css_class="space-y-4",
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
    quantity = forms.DecimalField(label="Quantidade", min_value=Decimal("0.0001"), decimal_places=4, initial=Decimal("1"))
    unit_value = forms.DecimalField(label="Valor unitário", min_value=Decimal("0"), decimal_places=2, required=False)

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        if workshop is not None:
            self.fields["product"].queryset = Product.objects.filter(workshop=workshop, is_active=True).order_by("name")
            self.fields["product"].widget = SearchableSelectInput(choices=self.fields["product"].choices)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("product"), Field("quantity"), Field("unit_value"))


class StandaloneAddServiceForm(CoreForm):
    service = forms.ModelChoiceField(label="Serviço", queryset=Service.objects.none(), widget=SearchableSelectInput())
    quantity = forms.DecimalField(label="Quantidade", min_value=Decimal("0.0001"), decimal_places=4, initial=Decimal("1"))
    unit_value = forms.DecimalField(label="Valor unitário", min_value=Decimal("0"), decimal_places=2, required=False)

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        if workshop is not None:
            self.fields["service"].queryset = Service.objects.filter(workshop=workshop, is_active=True).order_by("name")
            self.fields["service"].widget = SearchableSelectInput(choices=self.fields["service"].choices)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("service"), Field("quantity"), Field("unit_value"))


class StandaloneManualProductForm(CoreForm):
    description = forms.CharField(label="Descrição", max_length=255, widget=TextInput())
    product_code = forms.CharField(label="Código", max_length=120, widget=TextInput())
    ncm = forms.CharField(label="NCM", max_length=10, widget=TextInput())
    unit = forms.CharField(label="Unidade", max_length=12, initial="UN", widget=TextInput())
    quantity = forms.DecimalField(label="Quantidade", min_value=Decimal("0.0001"), decimal_places=4, initial=Decimal("1"))
    unit_value = forms.DecimalField(label="Valor unitário", min_value=Decimal("0"), decimal_places=2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("description"), Field("product_code"), Field("ncm"), Field("unit"), Field("quantity"), Field("unit_value"))


class StandaloneManualServiceForm(CoreForm):
    description = forms.CharField(label="Descrição", max_length=255, widget=TextInput())
    quantity = forms.DecimalField(label="Quantidade", min_value=Decimal("0.0001"), decimal_places=4, initial=Decimal("1"))
    unit_value = forms.DecimalField(label="Valor unitário", min_value=Decimal("0"), decimal_places=2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("description"), Field("quantity"), Field("unit_value"))


def build_standalone_items_form(*, note_mode: str, nfe_lines: list[dict[str, object]], nfse_lines: list[dict[str, object]]) -> CoreForm:
    class StandaloneItemsReviewForm(CoreForm):
        pass

    form = StandaloneItemsReviewForm()
    products_html = _render_product_lines_html(nfe_lines)
    services_html = _render_service_lines_html(nfse_lines)

    sections: list[str] = []
    if note_mode in {"nfe", "both"}:
        sections.append(
            f"""
            <div class="space-y-4">
                <h3 class="text-xl font-semibold">Produtos da NF-e</h3>
                <div class="overflow-x-auto">{products_html}</div>
            </div>
            """
        )
    if note_mode in {"nfse", "both"}:
        sections.append(
            f"""
            <div class="space-y-4">
                <h3 class="text-xl font-semibold">Serviços da NFS-e</h3>
                <div class="overflow-x-auto">{services_html}</div>
            </div>
            """
        )

    form.helper = FormHelper()
    form.helper.form_tag = False
    form.helper.layout = Layout(
        Div(
            HTML("<h2 class='text-2xl font-bold'>Itens da emissão avulsa</h2>"),
            HTML("<p class='text-base-content/70 mb-6'>Adicione os produtos e/ou serviços que compõem esta nota.</p>"),
            HTML("".join(sections)),
            css_class="space-y-6",
        )
    )
    return form


def _format_decimal(value: object) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (InvalidOperation, TypeError, ValueError):
        return str(value or "0,00")


def _render_product_lines_html(lines: list[dict[str, object]]) -> str:
    if not lines:
        return "<p class='text-base-content/60'>Nenhum produto adicionado.</p>"

    rows = []
    for index, line in enumerate(lines):
        total = Decimal(str(line.get("quantity") or "0")) * Decimal(str(line.get("unit_value") or "0"))
        rows.append(
            f"""
            <tr class="border-b border-base-300/60">
                <td class="py-2">{escape(str(line.get('description') or ''))}</td>
                <td class="py-2 text-center">{line.get('quantity')}</td>
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
                <th class="text-right">Unitário</th>
                <th class="text-right">Total</th>
                <th></th>
            </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
    </table>
    """


def _render_service_lines_html(lines: list[dict[str, object]]) -> str:
    if not lines:
        return "<p class='text-base-content/60'>Nenhum serviço adicionado.</p>"

    rows = []
    for index, line in enumerate(lines):
        total = Decimal(str(line.get("quantity") or "0")) * Decimal(str(line.get("unit_value") or "0"))
        rows.append(
            f"""
            <tr class="border-b border-base-300/60">
                <td class="py-2">{escape(str(line.get('description') or ''))}</td>
                <td class="py-2 text-center">{line.get('quantity')}</td>
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
                <th class="text-right">Unitário</th>
                <th class="text-right">Total</th>
                <th></th>
            </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
    </table>
    """
