import re
import logging
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

from django import forms
from django.conf import settings
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django.db import transaction
import gzip
import base64

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe
from lxml.etree import fromstring
from django.urls import reverse
from django.utils import timezone
from djmoney.forms import MoneyField
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.price_tracking import build_product_price_warning, record_product_last_purchase_price, record_product_last_used_price
from apps.core.presentation.forms import address_layout, AddressFormMixin, CoreForm, CoreModelForm
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.widgets import TextInput, NumberInput, MoneyInput, CalendarDateInput, PercentageInput, CPForCNPJInput, CheckboxInput, PhoneInput, EmailInput, TextareaInput, SearchableSelectInput
from apps.core.utils import alert_confirm_layout
from apps.finance.models.payment_method import PaymentMethod

from apps.stock.financial_entries import ADDITIONAL_CHARGE_ENTRY_TYPE, PAYMENT_ENTRY_TYPE, calculate_import_totals, get_entry_amount, get_entry_reason, normalize_entry_type, sync_payment_entries_with_financial_movements
from apps.stock.models import StockPaymentMethod, StockImport, StockProduct, StockMovement, SefazZipCache
from apps.stock.models import StockTransfer
from apps.core.text_normalization import name_case, sentence_case

from apps.core.infrastructure.providers.sefaz_provider import get_sefaz_service
from apps.stock.utils import NFParser, extract_nf_number_from_access_key, parse_sefaz_distribution_doc_metadata
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.files import workshop_certificate_temp_path, workshop_has_certificate
from apps.workshops.util.workshops import has_workshop_perm


external_calls_logger = logging.getLogger("performance.external")

MONEY_QUANTIZER = Decimal("0.01")
NF_WITHOUT_ITEMS_MESSAGE = "A NF-e foi localizada, mas o XML retornado não contém os itens da nota. Sem esses itens não é possível vincular produtos no estoque. Importe o XML completo da NF-e ou tente novamente quando a SEFAZ disponibilizar o documento completo."


def _parse_decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None

    raw_value = str(value).strip()
    if not raw_value:
        return None

    normalized_value = raw_value.replace(".", "").replace(",", ".") if "," in raw_value else raw_value
    try:
        return Decimal(normalized_value)
    except (InvalidOperation, ValueError):
        return None


def _parse_decimal_or(value: Any, default: Decimal) -> Decimal:
    parsed_value = _parse_decimal_value(value)
    return parsed_value if parsed_value is not None else default


def _money_from_value(value: Any) -> Money | None:
    parsed_value = _parse_decimal_value(value)
    if parsed_value is None:
        return None
    return Money(parsed_value.quantize(MONEY_QUANTIZER), "BRL")


def _format_money_display(value: Money | None) -> str:
    return str(value) if value is not None else "--"


def _has_importable_nf_items(nf_data: dict[str, Any] | None) -> bool:
    return bool(nf_data and nf_data.get("items"))


# Stock


class ImportStep1Form(CoreModelForm):
    xml_file = forms.FileField(label="Selecione o arquivo XML", required=False)
    access_key = forms.CharField(label="Insira a chave de acesso", max_length=47, required=False, widget=TextInput(attrs={"oninput": "this.value = this.value.replace(/[^0-9]/g, '')"}))

    class Meta:
        model = StockImport
        fields = ["method"]
        widgets = {"method": SearchableSelectInput(choices=StockImport.ImportMethods.choices, attrs={"x-model": "method"})}

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        self.parsed_nf_data = None
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.method:
            self.fields["method"].initial = self.instance.method

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                # Coluna Esquerda: Seleção
                Div(
                    HTML('<h2 class="text-2xl font-bold mb-6">Método de Importação</h2>'),
                    Field("method"),
                    css_class="col-span-12 lg:col-span-5",
                ),
                #
                Div(css_class="hidden lg:block lg:col-span-2"),
                #
                # Coluna Direita
                Div(
                    # Cabeçalhos Dinâmicos
                    HTML('<h2 class="text-2xl font-bold mb-6" x-show="method == \'XML\'">Importação do Arquivo</h2>'),
                    HTML('<h2 class="text-2xl font-bold mb-6" x-show="method == \'KEY\'">Chave de Acesso</h2>'),
                    # Campos Dinâmicos
                    Div(Field("xml_file", css_class="file-input file-input-bordered w-full"), x_show="method == 'XML'"),
                    Div(Field("access_key", css_class="input input-bordered w-full"), x_show="method == 'KEY'"),
                    css_class="col-span-12 lg:col-span-5",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            )
        )

    def save(self, commit=True):
        obj = super().save(commit=False)
        method = self.cleaned_data.get("method")

        if self.parsed_nf_data:
            data = self.parsed_nf_data
            obj.workshop = self.workshop
            obj.nf_number = data.get("nf_number") or extract_nf_number_from_access_key(data.get("nf_key"))
            obj.nf_key = data.get("nf_key", "")
            obj.supplier_cnpj = data.get("supplier_cnpj")
            obj.supplier_name = data.get("supplier_name")
            obj.items_data = data.get("items", [])
            obj.payments_data = data.get("payments", [])

        if method in ["XML", "KEY"] and not obj.nf_key:
            raise ValueError("A chave da NF-e é obrigatória para este método de importação.")

        if commit:
            obj.save()
            synced_entries, payments_updated = sync_payment_entries_with_financial_movements(
                stock_import=obj,
                entries=list(obj.payments_data or []),
                user=self.request.user,
                replace_existing=True,
            )
            if payments_updated:
                obj.payments_data = synced_entries
                obj.save(update_fields=["payments_data"])
        return obj

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")
        nf_data = None

        if method == "XML":
            xml_file = self.files.get("xml_file")
            if not xml_file:
                self.add_error("xml_file", "O arquivo XML é obrigatório para este método.")
            else:
                try:
                    nf_data = NFParser.parse_nfe_xml_to_dict(self.workshop, xml_file)
                except Exception:
                    self.add_error("xml_file", "Erro ao ler o arquivo XML.")

        if method == "KEY":
            key = cleaned_data.get("access_key")
            nf_key = re.sub(r"\D", "", key) if key else ""

            if len(nf_key) != 44:
                self.add_error("access_key", "Insira uma chave válida de 44 dígitos.")

            elif not workshop_has_certificate(self.workshop) or not self.workshop.certificate_password:
                self.add_error("method", "Oficina sem certificado configurado.")

            else:
                try:
                    with workshop_certificate_temp_path(self.workshop) as certificate_path:
                        content = get_sefaz_service().consultar_distribuicao(
                            certificado_path=certificate_path,
                            certificado_senha=self.workshop.certificate_password,
                            uf=self.workshop.uf.upper(),
                            cnpj=re.sub(r"\D", "", self.workshop.cnpj),
                            chave=nf_key,
                        )

                    if b"<cStat>215</cStat>" in content:
                        self.add_error("access_key", "Rejeição da SEFAZ por falha no esquema. Verifique se o CNPJ do certificado é o destinatário da nota.")
                        return cleaned_data

                    if b"<cStat>137</cStat>" in content:
                        self.add_error("access_key", "Nenhum documento encontrado para esta chave no CNPJ informado.")
                        return cleaned_data

                    if b"<cStat>593</cStat>" in content:
                        self.add_error("access_key", "CNPJ-Base consultado difere do CNPJ-Base do Certificado Digital.")
                        return cleaned_data

                    nf_data = NFParser.parse_nfe_xml_to_dict(self.workshop, content)
                except Exception:
                    self.add_error("access_key", "Erro ao buscar chave na SEFAZ ou chave inválida.")

        if nf_data:
            if not nf_data.get("nf_key"):
                nf_data["nf_key"] = cleaned_data.get("access_key") or self.data.get("access_key")

            nf_number = nf_data.get("nf_number") or extract_nf_number_from_access_key(nf_data.get("nf_key"))
            if nf_number:
                nf_data["nf_number"] = nf_number

            if not _has_importable_nf_items(nf_data):
                field_name = "xml_file" if method == "XML" else "access_key" if method == "KEY" else "method"
                self.add_error(field_name, NF_WITHOUT_ITEMS_MESSAGE)
                return cleaned_data

            if StockImport.objects.filter(workshop=self.workshop, nf_key=nf_data["nf_key"]).exclude(pk=self.instance.pk).exists():
                self.add_error("method", f"A NF com chave {nf_data['nf_key']} já existe.")

            elif nf_data.get("nf_number") and StockImport.objects.filter(workshop=self.workshop, nf_number=nf_data["nf_number"], supplier_cnpj=nf_data["supplier_cnpj"]).exclude(pk=self.instance.pk).exists():
                self.add_error("method", f"A NF número {nf_data['nf_number']} deste fornecedor já foi importada.")

            self.parsed_nf_data = nf_data

        return cleaned_data


class ImportStepSupplierForm(CoreModelForm):
    class Meta:
        model = StockImport
        fields = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        nome = self.instance.supplier_name or "Não informado"
        cnpj = self.instance.supplier_cnpj or "Não informado"
        nNF = self.instance.nf_number_display or "---"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-base-300 p-6 rounded-lg mb-6">
                <div>
                    <p class="text-xs text-indigo-600 font-bold uppercase tracking-wider mb-1">Emitente (Fornecedor)</p>
                    <p class="font-bold text-gray-900 text-lg">{nome}</p>
                    <p class="text-sm text-gray-600 font-mono">CNPJ: {cnpj}</p>
                </div>
                <div>
                    <p class="text-xs text-indigo-600 font-bold uppercase tracking-wider mb-1">Dados da Nota</p>
                    <p class="font-bold text-gray-900 text-lg">NF-e: {nNF}</p>
                    <p class="text-xs text-gray-500 italic">Os itens serão conciliados na próxima etapa.</p>
                </div>
            </div>
            <div class="alert alert-info shadow-sm mb-4">
                <span class="material-icons">info</span>
                <div>
                    <h3 class="font-bold text-sm">Informação</h3>
                    <div class="text-xs">Ao avançar, o fornecedor será vinculado ou cadastrado automaticamente.</div>
                </div>
            </div>
            """)
        )

    def save(self, commit=True):
        cnpj = self.instance.supplier_cnpj or self.nf_data["supplier_cnpj"]
        name = self.instance.supplier_name or self.nf_data["supplier_name"]
        Supplier.objects.get_or_create(workshop=self.workshop, cnpj=cnpj, defaults={"name": name})
        return self.instance


class ImportStepItemsForm(CoreModelForm):
    class Meta:
        model = StockImport
        fields = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Div(HTML(self._generate_table_html()), css_class="mt-4"))

    def _generate_table_html(self):
        rows_xml = ""
        rows_system = ""
        quick_create_url = reverse("stock:product_quick_create")
        link_manual_url = reverse("stock:link_product_manual")
        item_editor_url = reverse("stock:manual_link_item_editor")
        empty_import_alert = ""

        if not self.import_items:
            empty_import_alert = f"""
            <div class="alert alert-warning mb-4 col-span-12">
                <span class="material-icons">warning</span>
                <div>
                    <h3 class="font-bold text-sm">Itens da NF-e não carregados</h3>
                    <div class="text-xs">{NF_WITHOUT_ITEMS_MESSAGE}</div>
                </div>
            </div>
            """
            rows_xml = """<tr><td colspan="4" class="text-center py-8 text-sm opacity-60">Nenhum item importado.</td></tr>"""
            rows_system = """<tr><td colspan="5" class="text-center py-8 text-sm opacity-60">Nenhum item disponível para vincular.</td></tr>"""

        for idx, item in enumerate(self.import_items):
            ref_xml = item.get("ref", "")
            desc_xml = item.get("desc", "")
            qtd = Decimal(str(item.get("qtd", 0)))
            valor_unit = Decimal(str(item.get("valor", 0)))
            valor_total = qtd * valor_unit
            rows_xml += f"""<tr class="h-16 border-b">
                    <td class="max-w-[150px]">
                        <div class="text-sm font-medium truncate" title="{desc_xml}">{desc_xml}</div>
                        <div class="text-[10px] opacity-50 font-mono">{ref_xml}</div>
                    </td>
                    <td class="text-center">{qtd}</td>
                    <td class="text-right font-semibold whitespace-nowrap">{Money(valor_unit, "BRL")}</td>
                    <td class="text-right font-bold whitespace-nowrap">{Money(valor_total, "BRL")}</td>
                </tr>"""

            product_id = item.get("linked_product_id")
            product = Product.objects.filter(id=product_id, workshop=self.workshop).first() if product_id else None
            if product:
                item_unit_cost = _format_money_display(_money_from_value(item.get("valor")) or product.cost_price)
                item_selling_price = _format_money_display(_money_from_value(item.get("selling_price")) or product.selling_price)
                rows_system += f"""<tr class="h-16 border-b">
                        <td class="max-w-[150px]">
                            <div class="text-sm font-medium truncate" title="{product.name}">{product.name}</div>
                            <div class="text-[10px] opacity-50 font-mono">{product.code}</div>
                        </td>
                        <td class="text-center whitespace-nowrap">{item_unit_cost}</td>
                        <td class="text-center whitespace-nowrap">{item_selling_price}</td>
                        <td class="text-center">{product.stock_products.current_quantity}</td>
                        <td class="text-center">
                            <div class="flex gap-1 justify-center">
                                <button type="button" class="btn btn-ghost btn-xs text-info" title="Editar Item"
                                        hx-get="{item_editor_url}?pk={self.instance.pk}&product_id={product.pk}&item_idx={idx}"
                                        hx-target="#child-modal-container"
                                        hx-swap="innerHTML">
                                    <span class="material-icons text-xs">edit</span>
                                </button>
                                <button type="button" class="btn btn-ghost btn-xs text-error" title="Desvincular Item"
                                        hx-post='{reverse("stock:unlink_item")}?item_idx={idx}&pk={self.instance.pk}' hx-target="#step-container">
                                    <span class="material-icons text-xs">link_off</span>
                                </button>
                            </div>
                        </td>
                    </tr>"""
            else:
                rows_system += f"""<tr class="h-16 border-b">
                        <td class="italic text-warning text-xs">
                            <span class="flex items-center gap-1"><span class="material-icons text-sm">warning</span> Pendente</span>
                        </td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td class="text-center">
                            <div class="flex gap-1 justify-center">
                                <button type="button" class="btn btn-primary btn-sm" hx-target="#modal-container"
                                        hx-get="{quick_create_url}?ref={ref_xml}&desc={desc_xml}&price={valor_unit}&item_idx={idx}&pk={self.instance.pk}">Cadastrar</button>
                                <button type="button" class="btn btn-outline btn-sm" hx-target="#modal-container"
                                        hx-get="{link_manual_url}?item_idx={idx}&pk={self.instance.pk}">Vincular</button>
                            </div>
                        </td>
                    </tr>
                    """

        return f"""<div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {empty_import_alert}
            <div class="col-span-12 lg:col-span-5">
                <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">Itens Importados</h3>
                <div class="rounded-xl border border-base-300 overflow-x-auto">
                    <table class="table table-sm w-full">
                        <thead>
                            <tr class="bg-base-300">
                                <th>Descrição</th>
                                <th class="text-center">Quantidade</th>
                                <th class="text-right">Valor de Custo</th>
                                <th class="text-right">Valor Total</th>
                            </tr>
                        </thead>
                        <tbody class="bg-base-200">{rows_xml}</tbody>
                    </table>
                </div>
            </div>
            
            <div class="hidden lg:block lg:col-span-1"></div>
            
            <div class="col-span-12 lg:col-span-6">
                <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">Itens Cadastrados</h3>
                <div class="rounded-xl border border-base-300 overflow-x-auto">
                    <table class="table table-sm w-full">
                        <thead>
                            <tr class="bg-base-300">
                                <th>Produto Vinculado</th>
                                <th class="text-center">Valor de Custo</th>
                                <th class="text-center">Valor de Venda</th>
                                <th class="text-center">Estoque Atual</th>
                                <th class="text-center">Ações</th>
                            </tr>
                        </thead>
                        <tbody class="bg-base-200">{rows_system}</tbody>
                    </table>
                </div>
            </div>
        </div>"""

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.items_data:
            self.add_error(None, NF_WITHOUT_ITEMS_MESSAGE)
            return cleaned_data

        for item in self.instance.items_data:
            if not item.get("linked_product_id"):
                self.add_error(None, "Existem itens pendentes de vínculo.")
        return cleaned_data


class ImportStepPaymentForm(CoreModelForm):
    payment_method = forms.ModelChoiceField(queryset=PaymentMethod.objects.none(), label="Forma de Pagamento", widget=SearchableSelectInput, required=False, empty_label="Selecione uma forma")
    installments_count = forms.IntegerField(min_value=1, initial=1, label="Número de Parcelas", widget=forms.HiddenInput, required=False)
    first_amount = MoneyField(max_digits=14, decimal_places=2, label="Valor Pago", widget=MoneyInput, required=False)
    payment_date = forms.DateField(label="Data de Vencimento", widget=CalendarDateInput, required=False)

    total_nf_display = forms.CharField(label="Valor Total", required=False, widget=MoneyInput)
    total_allocated_display = forms.CharField(label="Valor total a ser pago", required=False, widget=MoneyInput)
    pending_display = forms.CharField(label="Valor total pendente", required=False, widget=MoneyInput)

    class Meta:
        model = StockImport
        fields = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        if self.workshop:
            self.fields["payment_method"].queryset = PaymentMethod.objects.filter(workshop=self.workshop, is_active=True).order_by("description")

        totals = calculate_import_totals(items=self.import_items, entries=self.import_payments)
        valor_total = totals.total_value
        valor_pago = totals.total_paid
        valor_pendente = totals.pending_value

        resume = {
            "total_nf_display": valor_total,
            "total_allocated_display": valor_pago,
            "pending_display": valor_pendente,
        }

        for field_name, value in resume.items():
            money_obj = Money(value, "BRL")
            self.initial[field_name] = money_obj

            if self.is_bound:
                self.data._mutable = True
                self.data[f"{field_name}_0"] = str(value)
                self.data[f"{field_name}_1"] = "BRL"
                self.data._mutable = False

            self.fields[field_name].widget.attrs.update({"readonly": True, "class": "cursor-not-allowed opacity-75"})

        self.fields["payment_method"].label = mark_safe('Forma de Pagamento <span class="text-error">*</span>')
        self.fields["first_amount"].label = mark_safe('Valor a ser pago <span class="text-error">*</span>')
        self.fields["payment_date"].label = mark_safe('Data de Vencimento <span class="text-error">*</span>')
        self.fields["total_allocated_display"].label = "Valor Pago"
        self.fields["pending_display"].label = "Valor Pendente"

        today_iso = timezone.localdate().isoformat()
        pending_amount_js = format(valor_pendente, "f")

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
            <script>
                (function() {{
                    window.initStockPaymentForm = function() {{
                        const paymentContainer = document.getElementById('import-step-container');
                        if (paymentContainer && paymentContainer.dataset.paymentInitialized === 'true') return;

                        const paymentMethodInput = document.getElementById('id_payment_method');
                        const firstAmountInput = document.getElementById('id_first_amount_0');
                        const firstAmountDisplay = document.getElementById('id_first_amount_0_display');
                        const dueDateInput = document.getElementById('id_payment_date');
                        const btnAdd = document.querySelector('button[hx-post*="add_payment_session"]');
                        const warningDiv = document.getElementById('payment-warning-js');
                        const warningMessage = warningDiv ? warningDiv.querySelector('.payment-warning-message') : null;
                        const successDiv = document.getElementById('payment-success-js');
                        const successMessage = successDiv ? successDiv.querySelector('.payment-success-message') : null;
                        const pendingValue = parseFloat('{pending_amount_js}') || 0;
                        const todayValue = '{today_iso}';

                        if (!paymentMethodInput || !firstAmountInput || !btnAdd) return;

                        if (paymentContainer) {{
                            paymentContainer.dataset.paymentInitialized = 'true';
                        }}

                        const toggleWarning = (show, message) => {{
                            if (!warningDiv) return;
                            warningDiv.classList.toggle('hidden', !show);
                            if (warningMessage) warningMessage.textContent = message || '';
                        }};

                        const showSuccess = (show, message) => {{
                            if (!successDiv) return;
                            successDiv.classList.toggle('hidden', !show);
                            if (successMessage) successMessage.textContent = message || '';
                        }};

                        const updateDueDate = (force) => {{
                            if (dueDateInput && paymentMethodInput.value && (force || !dueDateInput.value)) {{
                                dueDateInput.value = todayValue;
                            }}
                        }};

                        const checkPaymentLimit = () => {{
                            const totalProposed = parseFloat(firstAmountInput.value) || 0;

                            if (pendingValue <= 0) {{
                                btnAdd.disabled = true;
                                btnAdd.classList.add('btn-disabled', 'opacity-50');
                                showSuccess(true, 'Importação completamente paga.');
                                toggleWarning(false, '');
                                return;
                            }}

                            if (totalProposed > (pendingValue + 0.001)) {{
                                btnAdd.disabled = true;
                                btnAdd.classList.add('btn-disabled', 'opacity-50');
                                const excess = (totalProposed - pendingValue).toLocaleString('pt-BR', {{minimumFractionDigits: 2}});
                                toggleWarning(true, `O valor a ser pago não pode exceder o saldo disponível de R$ {"{"}pendingValue.toLocaleString('pt-BR', {{minimumFractionDigits: 2}}){"}"}. Excesso de R$ ${{excess}}.`);
                                showSuccess(false, '');
                            }} else {{
                                btnAdd.disabled = false;
                                btnAdd.classList.remove('btn-disabled', 'opacity-50');
                                toggleWarning(false, '');
                                showSuccess(false, '');
                            }}
                        }};

                        paymentMethodInput.addEventListener('change', function() {{
                            updateDueDate(true);
                            checkPaymentLimit();
                        }});
                        paymentMethodInput.addEventListener('input', function() {{
                            updateDueDate(true);
                            checkPaymentLimit();
                        }});

                        if (firstAmountDisplay) {{
                            firstAmountDisplay.addEventListener('input', function() {{
                                requestAnimationFrame(checkPaymentLimit);
                            }});
                            firstAmountDisplay.addEventListener('blur', function() {{
                                setTimeout(checkPaymentLimit, 0);
                            }});
                        }}

                        updateDueDate(false);
                        setTimeout(checkPaymentLimit, 500);
                    }};

                    window.setTimeout(window.initStockPaymentForm, 0);
                }})();
            </script>
            """),
            Div(
                HTML('<h3 class="font-bold text-2xl pb-2 mb-2">Configuração das Formas de Pagamento</h3>'),
                HTML('<h5 class="text-lg pb-2 mb-4">Adicione e salve múltiplos planos de pagamento para esta importação.</h5>'),
                #
                HTML(f"""
                    <div id="payment-warning-js" class="hidden col-span-12 mb-4">
                        <div class="alert alert-error shadow-lg border-2 border-error">
                            <span class="material-icons">error_outline</span>
                            <div>
                                <h3 class="font-bold text-sm">Valor Não Permitido</h3>
                                <div class="text-xs payment-warning-message">
                                    O valor a ser pago não pode exceder o saldo disponível de <strong>R$ {valor_pendente:,.2f}</strong>.
                                </div>
                            </div>
                        </div>
                    </div>
                    <div id="payment-success-js" class="hidden col-span-12 mb-4">
                        <div class="alert alert-success shadow-lg border-2 border-success">
                            <span class="material-icons">check_circle</span>
                            <div>
                                <h3 class="font-bold text-sm">Importação Paga</h3>
                                <div class="text-xs payment-success-message">
                                    Importação completamente paga.
                                </div>
                            </div>
                        </div>
                    </div>
                """),
                #
                Div(Field("total_nf_display", wrapper_class="col-span-12 lg:col-span-4"), Field("total_allocated_display", wrapper_class="col-span-12 lg:col-span-4"), Field("pending_display", wrapper_class="col-span-12 lg:col-span-4"), css_class="grid grid-cols-12 gap-4 mb-2 pb-4 border-b-2 border-base-50"),
                #
                Div(
                    Field("payment_method", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("first_amount", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("payment_date", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-4 mb-2 mt-4",
                ),
                Div(
                    Field("installments_count"),
                    HTML(f"""<div class="col-span-12 flex justify-end gap-2">
                        <button type="button"
                                hx-get="{reverse("stock:add_additional_value_modal")}?pk={self.instance.pk}"
                                hx-target="#modal-container"
                                class="btn btn-outline">Adicionar Valor</button>
                        <button type="button" hx-post="{reverse("stock:add_payment_session")}?pk={self.instance.pk}"
                                hx-target="#import-step-container"
                                hx-include="#import-step-container"
                                hx-indicator="#payment-loader"
                                class="btn btn-primary">Salvar Plano de Pagamento</button>
                    </div>"""),
                    css_class="grid grid-cols-12 gap-4 mb-4 pb-4",
                ),
                #
                HTML('<div class="mt-6 overflow-x-auto">'),
                HTML(self._generate_payments_table_html()),
                HTML("</div>"),
                alert_confirm_layout(title="Deseja remover este lançamento financeiro?"),
                id="import-step-container",
                css_class="card-body",
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        totals = calculate_import_totals(items=self.import_items, entries=self.import_payments)
        if totals.pending_value > 0:
            self.add_error(None, f"Não é possível avançar. Existem R$ {totals.pending_value:.2f} pendentes. Pague o valor total antes de continuar.")
        return cleaned_data

    def _generate_payments_table_html(self):
        rows = ""
        for entry in self.import_payments:
            entry_type = normalize_entry_type(entry)
            payment_date = str(entry.get("payment_date") or "")
            if entry_type == PAYMENT_ENTRY_TYPE and payment_date:
                try:
                    payment_date = datetime.strptime(payment_date, "%Y-%m-%d").strftime("%d/%m/%Y")
                except ValueError:
                    payment_date = "-"
            else:
                payment_date = "-"

            amount = get_entry_amount(entry)
            sign = "+" if entry_type == ADDITIONAL_CHARGE_ENTRY_TYPE else "-"
            entry_type_label = "Valor adicional" if entry_type == ADDITIONAL_CHARGE_ENTRY_TYPE else "Pagamento"
            reason = get_entry_reason(entry) or "-"
            description = str(entry.get("method_display") or entry_type_label)
            delete_url = reverse("stock:remove_payment_session", kwargs={"payment_id": entry["id"]})
            delete_url += f"?pk={self.instance.pk}"
            rows += f"""<tr>
                    <td>{description}</td>
                    <td>{entry_type_label}</td>
                    <td>{payment_date}</td>
                    <td class="font-bold whitespace-nowrap">{sign} {Money(amount, "BRL")}</td>
                    <td>{reason}</td>
                    <td class="text-center">
                        <button type="button" 
                                hx-post="{delete_url}" 
                                hx-target="#import-step-container" 
                                data-confirm="Deseja remover este lançamento financeiro?"
                                class="btn btn-ghost btn-xs text-error">
                            <span class="material-icons text-sm">delete</span>
                        </button>
                    </td>
                </tr>"""

        if not rows:
            rows = '<tr><td colspan="6" class="text-center text-gray-500 italic py-4">Nenhum lançamento financeiro registrado.</td></tr>'

        return f"""<table class="table table-zebra w-full">
                <thead>
                    <tr class="bg-base-300">
                        <th>Descrição</th>
                        <th>Tipo</th>
                        <th>Vencimento</th>
                        <th>Valor</th>
                        <th>Motivo</th>
                        <th class="text-center">Ações</th>
                    </tr>
                </thead>
                <tbody class="bg-base-200">
                    {rows}
                </tbody>
            </table>"""


class ImportStepSummaryForm(CoreModelForm):
    class Meta:
        model = StockImport
        fields = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        rows_html = ""
        for item in self.instance.items_data:
            raw_value = str(item.get("valor", "0.00"))
            if "," in raw_value:
                clean_value = raw_value.replace(".", "").replace(",", ".")
            else:
                clean_value = raw_value
            value = Money(Decimal(clean_value), "BRL")

            # Item da nota
            rows_html += f"""<tr>
                        <td class="text-xs" title="{item.get("ref")}">{item.get("ref")}</td>
                        <td class="max-w-[150px] truncate" title="{item.get("desc")}">{item.get("desc")}</td>
                        <td class="text-right">{item.get("qtd")}</td>
                        <td class="text-right font-bold">{value}</td>
                    </tr>"""

            # Produto vinculado (se existir)
            product_id = item.get("linked_product_id")
            if product_id:
                product = Product.objects.filter(id=product_id, workshop=self.workshop).first()
                if product:
                    stock_qty = product.stock_products.current_quantity if hasattr(product, "stock_products") else 0
                    rows_html += f"""<tr>
                        <td class="text-xs text-warning" title="Código do Produto Vinculado: {product.code}">{product.code}</td>
                        <td class="max-w-[150px] truncate text-warning" title="Descrição do Produto Vinculado: {product.name}">{product.name}</td>
                        <td class="text-right text-warning" title="Estoque Atual do Produto Vinculado: {stock_qty}">{stock_qty}</td>
                        <td class="text-right font-bold text-warning" title="Valor de Custo do Produto Vinculado: {product.cost_price}">{product.cost_price}</td>
                    </tr>
                    <tr class="h-5"><td colspan="4"></td></tr>"""

        payments_html = ""
        totals = calculate_import_totals(items=list(self.instance.items_data or []), entries=list(self.instance.payments_data or []))
        total_value = Money(totals.pending_value, "BRL")
        for pay in self.instance.payments_data:
            value = Money(get_entry_amount(pay), "BRL")
            entry_type = normalize_entry_type(pay)
            sign = "+" if entry_type == ADDITIONAL_CHARGE_ENTRY_TYPE else "-"
            if entry_type == ADDITIONAL_CHARGE_ENTRY_TYPE:
                details = get_entry_reason(pay) or "Sem motivo informado"
            else:
                payment_date = pay.get("payment_date", "")
                try:
                    payment_date_display = datetime.strptime(payment_date, "%Y-%m-%d").strftime("%d/%m/%Y") if payment_date else "-"
                except ValueError:
                    payment_date_display = "-"
                details = f"{pay.get('method_display', 'Não encontrado')} - Vencimento {payment_date_display}"

            payments_html += f"""<div class="flex justify-between items-center mb-2 gap-4">
                            <span class="text-sm">{details}</span>
                            <span class="font-bold">{sign} {value}</span>
                        </div>"""

        supplier_name = self.instance.supplier_name or "Não informado"
        supplier_cnpj = self.instance.supplier_cnpj or "Não informado"
        nf_number = self.instance.nf_number_display or "---"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div class="space-y-6">
                    <div>
                        <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">Itens da Nota</h3>
                        <div class="overflow-x-auto rounded-lg bg-base-50">
                            <table class="table table-sm w-full">
                                <thead>
                                    <tr class="bg-base-300">
                                        <th>Código</th>
                                        <th>Descrição</th>
                                        <th class="text-right">Quantidade</th>
                                        <th class="text-right">Valor de Custo</th>
                                    </tr>
                                </thead>
                                <tbody class="gap-2 bg-base-200">
                                    {rows_html}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            
                <div class="space-y-6">
                    <div class="card bg-base-200 shadow-sm">
                        <div class="card-body p-4">
                            <h3 class="text-base font-bold uppercase mb-3">Fornecedor</h3>
                            <p class="text-lg font-bold">{supplier_name}</p>
                            <p class="text-sm opacity-70">CNPJ: {supplier_cnpj}</p>
                            <div class="divider my-1"></div>
                            <p class="text-sm">Nota Fiscal: <span class="font-bold">#{nf_number}</span></p>
                        </div>
                    </div>
            
                    <div class="card bg-base-200 shadow-sm">
                        <div class="card-body p-4">
                            <h3 class="text-base font-bold uppercase mb-3">Resumo Financeiro</h3>
                            {payments_html}
                            <div class="divider my-1"></div>
                            <div class="flex justify-between items-center font-black text-xl">
                                <span>Saldo Pendente</span>
                                <span>{total_value}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            """),
        )

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=False)
        workshop = self.workshop
        resolved_nf_number = instance.nf_number or extract_nf_number_from_access_key(instance.nf_key)

        if resolved_nf_number and instance.nf_number != resolved_nf_number:
            instance.nf_number = resolved_nf_number

        if instance.status == StockImport.ImportStatus.COMPLETED:
            return instance

        supplier = None
        if instance.supplier_cnpj:
            supplier, _ = Supplier.objects.get_or_create(cnpj=instance.supplier_cnpj, workshop=workshop, defaults={"name": instance.supplier_name})

        for item in instance.items_data:
            product_id = item.get("linked_product_id")
            product = Product.objects.get(id=product_id, workshop=workshop)
            stock_product, _created = StockProduct.objects.get_or_create(workshop=workshop, product=product, defaults={"supplier": supplier, "last_nf": resolved_nf_number})

            quantity = Decimal(str(item.get("qtd", 0)))
            purchase_price = _money_from_value(item.get("valor"))
            selling_price = _money_from_value(item.get("selling_price"))

            StockMovement.objects.create(
                workshop=workshop,
                stock_product=stock_product,
                type=StockMovement.MovementType.ENTRY,
                supplier=supplier,
                transcation_by=self.request.user,
                quantity=quantity,
                status=StockMovement.MovementStatus.APPROVED,
            )

            stock_product.current_quantity += quantity
            stock_product.last_nf = resolved_nf_number
            update_fields = ["current_quantity", "last_nf"]
            if supplier is not None:
                stock_product.supplier = supplier
                update_fields.append("supplier")
            stock_product.save(update_fields=update_fields)

            record_product_last_purchase_price(product=product, price=purchase_price)
            record_product_last_used_price(product=product, price=selling_price)

        payments_data = list(instance.payments_data or [])
        for pay in payments_data:
            if normalize_entry_type(pay) != PAYMENT_ENTRY_TYPE:
                continue

            payment_due_date = pay.get("payment_date")
            if isinstance(payment_due_date, str) and payment_due_date:
                try:
                    payment_due_date = timezone.make_aware(datetime.strptime(payment_due_date, "%Y-%m-%d"))
                except ValueError:
                    payment_due_date = timezone.now()
            else:
                payment_due_date = timezone.now()

            total_val = Decimal(str(pay.get("total_paid", 0)))
            installments = int(pay.get("installments", 1))
            first_amount = Decimal(str(pay.get("first_amount", total_val)))
            remaining_amount = Decimal("0.00")

            method_id = pay.get("method")
            payment_method_obj = get_object_or_404(PaymentMethod, id=method_id, workshop=workshop)
            StockPaymentMethod.objects.create(workshop=workshop, payment_method=payment_method_obj, installments_count=installments, first_installment_amount=Money(first_amount, "BRL"), remaining_installments_amount=Money(remaining_amount, "BRL"), nf_number=resolved_nf_number or "MANUAL", due_date=payment_due_date)

        payments_data, payments_updated = sync_payment_entries_with_financial_movements(
            stock_import=instance,
            entries=payments_data,
            user=self.request.user,
        )

        instance.status = StockImport.ImportStatus.COMPLETED
        if commit:
            if payments_updated:
                instance.payments_data = payments_data
            instance.save()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        for item in self.instance.items_data:
            if not item.get("linked_product_id"):
                self.add_error(None, "Existem itens pendentes de vínculo.")

        totals = calculate_import_totals(items=self.instance.items_data or [], entries=self.instance.payments_data or [])
        if totals.pending_value > 0:
            self.add_error(None, f"Não é possível finalizar. Existem R$ {totals.pending_value:.2f} pendentes. Pague o valor total antes de continuar.")

        return cleaned_data


class AdditionalChargeSessionForm(CoreForm):
    amount = MoneyField(max_digits=14, decimal_places=2, label="Valor", widget=MoneyInput)
    reason = forms.CharField(label="Motivo", max_length=255, widget=TextareaInput(attrs={"rows": 3, "placeholder": "Ex: Frete da transportadora"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("amount"),
                Field("reason"),
                css_class="space-y-4",
            )
        )

    def clean_reason(self) -> str:
        reason = str(self.cleaned_data.get("reason") or "").strip()
        if not reason:
            raise forms.ValidationError("Informe o motivo do valor adicional.")
        return sentence_case(reason)


class ImportSefazListForm(CoreModelForm):
    selected_key = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = StockImport
        fields = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        queryset = SefazZipCache.objects.filter(workshop=self.workshop).order_by("-issue_date", "-criado_em")

        page_number = self.request.GET.get("page", 1) if self.request else 1
        paginator = Paginator(queryset, 10)
        self.page_obj = paginator.get_page(page_number)

        imported_keys = StockImport.objects.filter(workshop=self.workshop).values_list("nf_key", flat=True)

        for nota in self.page_obj:
            nota.is_imported = nota.key in imported_keys

        self.notas = self.page_obj

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("selected_key", id="id_selected_key"), HTML("{% include 'stock/partials/sefaz_table.html' %}"))

    def update_sefaz_list(self) -> tuple[bool, str]:
        """Atualiza cache de notas da SEFAZ e retorna (sucesso, mensagem)."""
        if not self.workshop:
            return False, "Oficina não identificada para consulta na SEFAZ."

        if not self.workshop.can_search_sefaz:
            return False, "A busca da SEFAZ foi executada recentemente. Aguarde alguns minutos para atualizar novamente."

        if not workshop_has_certificate(self.workshop) or not self.workshop.certificate_password:
            return False, "Configure certificado e senha da oficina antes de buscar notas na SEFAZ."

        started_at = time.perf_counter()
        try:
            cnpj = re.sub(r"\D", "", self.workshop.cnpj)
            nsu = self.workshop.last_nsu_sefaz

            with workshop_certificate_temp_path(self.workshop) as certificate_path:
                xml_content = get_sefaz_service().consultar_distribuicao(
                    certificado_path=certificate_path,
                    certificado_senha=self.workshop.certificate_password,
                    uf=self.workshop.uf.upper(),
                    cnpj=cnpj,
                    nsu=nsu,
                )

            # Parsing do retorno da SEFAZ (simplificado do seu exemplo)
            tree = fromstring(xml_content)
            ns = {"ns": "http://www.portalfiscal.inf.br/nfe"}
            cached_count = 0

            if tree.xpath("//ns:cStat/text()", namespaces=ns)[0] == "138":
                self.workshop.last_nsu_sefaz = tree.xpath("//ns:ultNSU/text()", namespaces=ns)[0]

                docs = tree.xpath("//ns:docZip", namespaces=ns)
                for doc in docs:
                    content = gzip.decompress(base64.b64decode(doc.text))
                    dados = parse_sefaz_distribution_doc_metadata(content) or {}

                    if dados.get("key"):
                        SefazZipCache.objects.update_or_create(
                            key=dados["key"],
                            workshop=self.workshop,
                            defaults={
                                "nf_number": dados.get("nf_number"),
                                "issuer_name": dados.get("nome"),
                                "issuer_cnpj": dados.get("cnpj"),
                                "total_value": dados.get("valor"),
                                "issue_date": dados.get("data"),
                            },
                        )
                        cached_count += 1

            self.workshop.last_sefaz_search_date = timezone.now()
            self.workshop.save(update_fields=["last_nsu_sefaz", "last_sefaz_search_date"])

            if settings.PERF_LOGGING_ENABLED:
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                external_calls_logger.warning("external_call service=sefaz_consulta_distribuicao duration_ms=%.2f workshop_id=%s success=true", elapsed_ms, self.workshop.id)

            return True, f"Lista da SEFAZ atualizada com sucesso ({cached_count} nota(s) processada(s))."
        except Exception as exc:
            if settings.PERF_LOGGING_ENABLED:
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                external_calls_logger.warning("external_call service=sefaz_consulta_distribuicao duration_ms=%.2f workshop_id=%s success=false", elapsed_ms, self.workshop.id)
            return False, f"Erro ao atualizar lista da SEFAZ: {exc}"

    def save(self, commit=True):
        instance = super().save(commit=False)
        key = self.cleaned_data.get("selected_key")

        if key:
            try:
                with workshop_certificate_temp_path(self.workshop) as certificate_path:
                    xml_completo = get_sefaz_service().consultar_distribuicao(
                        certificado_path=certificate_path,
                        certificado_senha=self.workshop.certificate_password,
                        uf=self.workshop.uf,
                        cnpj=re.sub(r"\D", "", self.workshop.cnpj),
                        chave=key,
                    )

                nf_data = NFParser.parse_nfe_xml_to_dict(self.workshop, xml_completo)

                if nf_data:
                    if not _has_importable_nf_items(nf_data):
                        raise forms.ValidationError(NF_WITHOUT_ITEMS_MESSAGE)

                    resolved_nf_number = nf_data.get("nf_number") or extract_nf_number_from_access_key(nf_data.get("nf_key"))
                    instance.nf_number = resolved_nf_number
                    instance.nf_key = nf_data["nf_key"]
                    instance.supplier_cnpj = nf_data["supplier_cnpj"]
                    instance.supplier_name = nf_data["supplier_name"]
                    instance.items_data = nf_data["items"]
                    instance.payments_data = nf_data["payments"]
                    instance.method = "SEFAZ"

                    SefazZipCache.objects.filter(workshop=self.workshop, key=instance.nf_key).update(
                        nf_number=resolved_nf_number or None,
                        issuer_name=instance.supplier_name,
                        issuer_cnpj=instance.supplier_cnpj,
                    )
            except forms.ValidationError:
                raise
            except Exception as e:
                raise forms.ValidationError(f"Erro ao baixar nota completa: {e}")

        if commit:
            instance.save()
            synced_entries, payments_updated = sync_payment_entries_with_financial_movements(
                stock_import=instance,
                entries=list(instance.payments_data or []),
                user=self.request.user,
                replace_existing=True,
            )
            if payments_updated:
                instance.payments_data = synced_entries
                instance.save(update_fields=["payments_data"])
        return instance

    def clean(self):
        cleaned_data = super().clean()

        if not cleaned_data.get("selected_key"):
            self.add_error(None, "Selecione uma NF antes de avançar.")

        return cleaned_data


class ImportStepSupplierManualForm(CoreModelForm):
    supplier_select = forms.ChoiceField(label="Selecione o Fornecedor", required=True)

    class Meta:
        model = StockImport
        fields = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        current_supplier = None
        if self.instance and self.instance.supplier_cnpj:
            current_supplier = Supplier.objects.filter(workshop=self.workshop, cnpj=self.instance.supplier_cnpj).first()

        suppliers = Supplier.objects.filter(workshop=self.workshop, is_active=True).order_by("name")
        choices = [("", "Pesquisar fornecedor...")] + [(str(s.id), f"{s.name} ({s.cnpj})") for s in suppliers]

        self.fields["supplier_select"].choices = choices

        if current_supplier:
            self.initial["supplier_select"] = str(current_supplier.id)

        self.fields["supplier_select"].widget = SearchableSelectInput(choices=choices, attrs={"hx-get": reverse("stock:supplier_details"), "hx-target": "#supplier-info-container", "hx-trigger": "change, load", "class": "w-full", "x-model": "supplierId", "@change": "supplierId = $el.value"})

        initial_alpine = {"supName": self.instance.supplier_name or "", "supCnpj": self.instance.supplier_cnpj or "", "supplierId": str(current_supplier.id) if current_supplier else ""}

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                # Coluna Esquerda
                Div(
                    HTML('<h2 class="text-2xl font-bold mb-6 text-base-content">Fornecedor</h2>'),
                    Div(
                        Div(Field("supplier_select"), css_class="flex-grow"),
                        HTML("""<button type="button" class="btn btn-circle mb-2 ml-2" 
                                     :title="supplierId ? 'Editar Fornecedor' : 'Cadastrar Fornecedor'"
                                     :class="supplierId ? 'btn-warning' : 'btn-primary'"
                                     @click="const url = supplierId ? '/stock/supplier/quick-update/' + supplierId + '/' : '/stock/supplier/quick-create/';
                                            htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                            document.getElementById('form_modal').showModal();">
                                     <span class="material-icons" x-text="supplierId ? 'edit' : 'local_shipping'"></span>
                        </button>"""),
                        css_class="flex items-end mb-6",
                    ),
                    #
                    HTML("""<div class="alert mt-4 bg-info/10 text-info border-none">
                             <span class="material-icons">help_outline</span>
                             <span class="text-xs">Selecione um fornecedor acima para prosseguir com a importação manual.</span>
                    </div>"""),
                    css_class="col-span-12 lg:col-span-5",
                ),
                #
                Div(css_class="hidden lg:block lg:col-span-1"),
                #
                # Coluna Direita
                Div(
                    HTML("""
                        <div class="card bg-base-200 shadow-sm min-h-full">
                            <div class="card-body p-6">
                                <h2 class="text-xl font-bold mb-6 uppercase text-base-content opacity-70 flex items-center gap-2">
                                    <span class="material-icons text-sm">analytics</span> 
                                    Perfil do Fornecedor
                                </h2>

                                <div id="supplier-info-container" class="flex-grow flex flex-col justify-center">
                                    <div class="text-center opacity-30 py-10">
                                        <span class="material-icons text-5xl mb-2">manage_search</span>
                                        <p class="text-xs">Aguardando seleção de fornecedor...</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    """),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch",
                x_data=f"{{ supName: '{initial_alpine['supName']}', supCnpj: '{initial_alpine['supCnpj']}', supplierId: '{initial_alpine['supplierId']}' }}",
                x_on_update_supplier_info_window="supName = $event.detail.name; supCnpj = $event.detail.cnpj;",
            ),
        )

    def save(self, commit=True):
        supplier_id = self.cleaned_data.get("supplier_select")
        if supplier_id:
            supplier = Supplier.objects.get(id=supplier_id)
            self.instance.supplier_name = supplier.name
            self.instance.supplier_cnpj = supplier.cnpj
        return super().save(commit=commit)


class ManualLinkItemEditForm(CoreForm):
    product_id = forms.IntegerField(widget=forms.HiddenInput())
    item_idx = forms.IntegerField(required=False, widget=forms.HiddenInput())
    confirm_lower_price = forms.CharField(required=False, widget=forms.HiddenInput())
    quantity = forms.DecimalField(label="Quantidade", max_digits=10, decimal_places=2, min_value=Decimal("0.01"), widget=NumberInput(mode="positive"))
    unit_cost = MoneyField(label="Valor de Custo", max_digits=14, decimal_places=2, widget=MoneyInput())
    selling_price = MoneyField(label="Valor de Venda", max_digits=14, decimal_places=2, widget=MoneyInput())

    def __init__(self, *args: Any, product: Product, stock_import: StockImport, item_idx: int | None = None, **kwargs: Any):
        self.product = product
        self.stock_import = stock_import
        self.item_idx = item_idx
        super().__init__(*args, **kwargs)

        confirm_lower_price_initial = ""
        if self.is_bound and self.data is not None:
            confirm_lower_price_initial = "1" if str(self.data.get("confirm_lower_price") or "").strip() == "1" else ""

        self.fields["product_id"].initial = getattr(self.product, "pk", None)
        self.fields["item_idx"].initial = self.item_idx
        self.fields["confirm_lower_price"].initial = confirm_lower_price_initial
        self.fields["confirm_lower_price"].widget.attrs["x-model"] = "confirmLowerPriceValue"
        self.fields["selling_price"].widget.attrs["x-on:input.capture"] = "resetLowerPriceConfirmation()"

        if not self.is_bound:
            if self.is_editing and self.item_data is not None:
                self.initial.setdefault("quantity", _parse_decimal_or(self.item_data.get("qtd"), Decimal("1")))
                self.initial.setdefault("unit_cost", _money_from_value(self.item_data.get("valor")) or self.product.cost_price)
                self.initial.setdefault("selling_price", _money_from_value(self.item_data.get("selling_price")) or self.product.selling_price)
            else:
                self.initial.setdefault("quantity", Decimal("1"))
                self.initial.setdefault("unit_cost", self.product.cost_price)
                self.initial.setdefault("selling_price", self.product.selling_price)

    @property
    def item_data(self) -> dict[str, Any] | None:
        if self.item_idx is None:
            return None

        items = list(self.stock_import.items_data or [])
        if 0 <= self.item_idx < len(items):
            return dict(items[self.item_idx])
        return None

    @property
    def is_editing(self) -> bool:
        return self.item_idx is not None

    @property
    def has_existing_link(self) -> bool:
        item_data = self.item_data or {}
        return bool(item_data.get("linked_product_id"))

    @property
    def is_linking_imported_item(self) -> bool:
        return self.item_idx is not None and not self.has_existing_link

    @property
    def is_manual_import(self) -> bool:
        return self.stock_import.method == StockImport.ImportMethods.MANUAL

    @property
    def modal_title(self) -> str:
        if self.has_existing_link:
            return "Editar item vinculado"
        if self.is_linking_imported_item:
            return "Configurar item antes de vincular"
        return "Configurar item antes de inserir"

    @property
    def modal_description(self) -> str:
        if self.has_existing_link:
            return "Revise quantidade e preços antes de atualizar o item na tabela da importação."
        if self.is_linking_imported_item:
            return "Revise quantidade e preços antes de vincular o produto ao item importado."
        return "Revise quantidade e preços antes de adicionar o produto na tabela da importação manual."

    @property
    def submit_label(self) -> str:
        if self.has_existing_link:
            return "Salvar alterações"
        if self.is_linking_imported_item:
            return "Salvar e Vincular"
        return "Salvar e Inserir"

    @property
    def submit_icon(self) -> str:
        if self.has_existing_link:
            return "edit"
        if self.is_linking_imported_item:
            return "link"
        return "playlist_add"

    @property
    def save_help_text(self) -> str:
        if self.has_existing_link:
            return "Ao salvar, este item sera atualizado na tabela desta etapa."
        if self.is_linking_imported_item:
            return "Ao salvar, o produto sera vinculado ao item importado e os dados informados ficarao salvos nesta etapa."
        return "Ao salvar, este item sera adicionado a tabela desta etapa e continuara editavel depois."

    @property
    def success_message(self) -> str:
        if self.has_existing_link:
            message = "atualizado na importacao manual" if self.is_manual_import else "atualizado na importacao"
        elif self.is_linking_imported_item:
            message = "vinculado na importacao"
        else:
            message = "adicionado a importacao manual"

        return f"{self.product.name} {message}."

    @property
    def current_quantity(self) -> int:
        if hasattr(self.product, "stock_products"):
            return self.product.stock_products.current_quantity
        return 0

    @property
    def last_purchase_price_display(self) -> str:
        return _format_money_display(getattr(self.product, "last_purchase_price", None))

    @property
    def last_used_price_display(self) -> str:
        return _format_money_display(getattr(self.product, "last_used_price", None))

    @property
    def alpine_data(self) -> str:
        confirm_lower_price_initial = str(self.fields["confirm_lower_price"].initial or "")
        last_used_amount = ""
        last_used_price = getattr(self.product, "last_used_price", None)
        if last_used_price is not None:
            last_used_amount = str(last_used_price.amount.quantize(MONEY_QUANTIZER))

        return f"""{{
            confirmLowerPriceValue: {confirm_lower_price_initial!r},
            lowerPriceConfirmed: {str(bool(confirm_lower_price_initial)).lower()},
            lastUsedPrice: {last_used_amount!r},
            priceHelpMessage: '',
            isSubmitting: false,
            init() {{
                const form = this.getForm();
                if (!form || form.dataset.manualLinkEditorReady === '1') return;

                form.dataset.manualLinkEditorReady = '1';
                const stopSubmitting = () => {{
                    this.isSubmitting = false;
                }};

                form.addEventListener('htmx:afterRequest', stopSubmitting);
                form.addEventListener('htmx:responseError', stopSubmitting);
                form.addEventListener('htmx:sendError', stopSubmitting);
            }},
            getRawMoneyValue(fieldId) {{
                const field = document.getElementById(fieldId);
                if (!field) return 0;
                return Number.parseFloat(field.value || '0') || 0;
            }},
            getForm() {{
                return this.$root;
            }},
            getLowerPriceModal() {{
                return this.$refs.lowerPriceModal || document.getElementById('manual-link-lower-price-modal');
            }},
            openLowerPriceModal() {{
                const modal = this.getLowerPriceModal();
                if (modal && typeof modal.showModal === 'function') {{
                    if (!modal.open) {{
                        modal.showModal();
                    }}
                    return;
                }}

                if (window.confirm('O valor informado está abaixo do último valor utilizado para este produto. Deseja continuar mesmo assim?')) {{
                    this.continueWithLowerPrice();
                    return;
                }}

                this.cancelLowerPrice();
            }},
            closeLowerPriceModal() {{
                const modal = this.getLowerPriceModal();
                if (modal && modal.open) {{
                    modal.close();
                }}
            }},
            formatCurrency(value) {{
                const numericValue = Number.parseFloat(value || '0');
                return numericValue.toLocaleString('pt-BR', {{ style: 'currency', currency: 'BRL' }});
            }},
            shouldWarnForLowerPrice() {{
                if (!this.lastUsedPrice) return false;
                const sellingPrice = this.getRawMoneyValue('id_selling_price_0');
                if (sellingPrice <= 0) return false;
                return sellingPrice < (Number.parseFloat(this.lastUsedPrice) || 0);
            }},
            submitForm() {{
                if (this.isSubmitting) return;

                const form = this.getForm();
                if (!form) return;

                this.isSubmitting = true;
                this.priceHelpMessage = '';
                htmx.trigger(form, 'manual-link-editor-submit');
            }},
            handleSubmit(event) {{
                event.preventDefault();
                if (this.isSubmitting) return;

                if (this.shouldWarnForLowerPrice() && !this.lowerPriceConfirmed) {{
                    this.priceHelpMessage = '';
                    this.openLowerPriceModal();
                    return;
                }}

                this.submitForm();
            }},
            continueWithLowerPrice() {{
                this.lowerPriceConfirmed = true;
                this.confirmLowerPriceValue = '1';
                this.priceHelpMessage = '';
                this.closeLowerPriceModal();
                this.$nextTick(() => this.submitForm());
            }},
            cancelLowerPrice() {{
                const amountField = document.getElementById('id_selling_price_0');
                const displayField = document.getElementById('id_selling_price_0_display');
                this.closeLowerPriceModal();
                if (amountField) {{
                    amountField.value = '';
                    amountField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    amountField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
                if (displayField) {{
                    displayField.value = '';
                    displayField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    displayField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}

                this.confirmLowerPriceValue = '';
                this.lowerPriceConfirmed = false;
                this.priceHelpMessage = `Último valor usado: ${{this.formatCurrency(this.lastUsedPrice)}}`;
            }},
            resetLowerPriceConfirmation() {{
                this.confirmLowerPriceValue = '';
                this.lowerPriceConfirmed = false;
                this.priceHelpMessage = '';
            }}
        }}"""

    def build_item_data(self, existing_item: dict[str, Any] | None = None) -> dict[str, Any]:
        quantity = Decimal(str(self.cleaned_data["quantity"] or 0))
        unit_cost = self.cleaned_data["unit_cost"]
        selling_price = self.cleaned_data["selling_price"]

        item_data = dict(existing_item or {})
        item_data.setdefault("ref", str(self.product.code))
        item_data.setdefault("desc", str(self.product.name))
        item_data["qtd"] = str(quantity)
        item_data["valor"] = str(unit_cost.amount.quantize(MONEY_QUANTIZER))
        item_data["selling_price"] = str(selling_price.amount.quantize(MONEY_QUANTIZER))
        item_data["linked_product_id"] = str(self.product.pk)
        return item_data

    def clean_product_id(self) -> int:
        product_id = int(self.cleaned_data["product_id"])
        if not self.product.pk or product_id != self.product.pk:
            raise forms.ValidationError("Produto inválido para vinculação.")
        return product_id

    def clean_item_idx(self) -> int | None:
        raw_item_idx = self.cleaned_data.get("item_idx")
        if raw_item_idx in (None, ""):
            return None

        item_idx = int(raw_item_idx)
        if item_idx < 0:
            raise forms.ValidationError("Índice do item inválido.")

        if self.is_editing:
            items = list(self.stock_import.items_data or [])
            if item_idx >= len(items):
                raise forms.ValidationError("Índice do item inválido.")

        return item_idx

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        selling_price = cleaned_data.get("selling_price")
        confirm_lower_price = str(cleaned_data.get("confirm_lower_price") or "").strip() == "1"

        warning = build_product_price_warning(product=self.product, attempted_price=selling_price)
        if warning and not confirm_lower_price:
            self.add_error(None, warning.message)

        return cleaned_data


class ImportManualItemsForm(CoreModelForm):
    class Meta:
        model = StockImport
        fields = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        self.linked_products = self._get_linked_products()
        confirm_lower_price_value = "1" if self.is_bound and str(self.data.get("confirm_lower_price") or "").strip() == "1" else ""

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Div(
                    HTML('<h2 class="text-2xl font-bold text-base-content">Peças Selecionadas</h2>'),
                    Div(
                        HTML(f"""<button type="button" class="btn btn-outline btn-success btn-sm" 
                                        hx-get="{reverse("stock:link_product_manual") + f"?pk={self.instance.pk}&manual=true"}" hx-target="#modal-container">
                                        <span class="flex items-center gap-1">
                                            <span class="material-icons text-sm">link</span> Vincular ao Item
                                        </span>
                        </button>"""),
                        HTML(f"""<button type="button" class="btn btn-success btn-sm" 
                                    hx-get="{reverse("stock:product_quick_create") + f"?pk={self.instance.pk}&manual=true"}" hx-target="#modal-container">
                                    <span class="flex items-center gap-1">
                                        <span class="material-icons text-sm">add</span> Criar Novo Item
                                    </span>
                        </button>"""),
                        css_class="flex gap-2",
                    ),
                    css_class="flex justify-between items-center mb-6",
                ),
                HTML(f'<input type="hidden" name="confirm_lower_price" id="manual-confirm-lower-price-input" value="{confirm_lower_price_value}">'),
                HTML("""
                    {% if form.non_field_errors %}
                        <div class="alert alert-warning mb-4">
                            <span class="material-icons">warning</span>
                            <div class="space-y-1 text-sm">
                                {% for error in form.non_field_errors %}
                                    <p>{{ error }}</p>
                                {% endfor %}
                            </div>
                        </div>
                    {% endif %}
                """),
                HTML(self._generate_manual_table_html()),
                HTML(self._build_lower_price_warning_modal()),
                HTML(self._build_lower_price_warning_script()),
                css_class="mt-4",
            )
        )

    def _get_linked_products(self) -> dict[int, Product]:
        if not self.workshop:
            return {}

        product_ids: list[int] = []
        for item in self.instance.items_data or []:
            try:
                product_id = int(item.get("linked_product_id") or 0)
            except (TypeError, ValueError):
                continue

            if product_id:
                product_ids.append(product_id)

        if not product_ids:
            return {}

        queryset = Product.objects.filter(workshop=self.workshop, id__in=product_ids).select_related("stock_products")
        return {product.id: product for product in queryset}

    def _get_product_for_item(self, item: dict[str, Any]) -> Product | None:
        try:
            product_id = int(item.get("linked_product_id") or 0)
        except (TypeError, ValueError):
            return None
        return self.linked_products.get(product_id)

    def _build_manual_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for idx, item in enumerate(self.instance.items_data or []):
            if not item.get("linked_product_id"):
                continue

            product = self._get_product_for_item(item)
            if product is None:
                continue

            quantity_key = f"items_qty_{idx}"
            unit_cost_key = f"items_price_{idx}_0"
            selling_price_key = f"items_selling_price_{idx}_0"

            quantity_source = self.data.get(quantity_key) if self.is_bound and quantity_key in self.data else item.get("qtd", "1")
            unit_cost_source = self.data.get(unit_cost_key) if self.is_bound and unit_cost_key in self.data else item.get("valor", "0")

            selling_price_source: Any = None
            if self.is_bound and selling_price_key in self.data:
                selling_price_source = self.data.get(selling_price_key)
            elif item.get("selling_price") not in (None, ""):
                selling_price_source = item.get("selling_price")
            elif getattr(product, "selling_price", None) is not None:
                selling_price_source = product.selling_price.amount

            quantity = _parse_decimal_or(quantity_source, Decimal("1"))
            unit_cost = _parse_decimal_or(unit_cost_source, Decimal("0.00")).quantize(MONEY_QUANTIZER)
            selling_price = _parse_decimal_or(selling_price_source, Decimal("0.00")).quantize(MONEY_QUANTIZER)
            subtotal = (quantity * unit_cost).quantize(MONEY_QUANTIZER)

            rows.append(
                {
                    "idx": idx,
                    "product": product,
                    "quantity": quantity,
                    "unit_cost": unit_cost,
                    "selling_price": selling_price,
                    "subtotal": subtotal,
                }
            )

        return rows

    def _sync_instance_items_from_rows(self, rows: list[dict[str, Any]]) -> None:
        items = [dict(item) for item in (self.instance.items_data or [])]
        for row in rows:
            item = items[row["idx"]]
            item["qtd"] = str(row["quantity"])
            item["valor"] = str(row["unit_cost"])
            item["selling_price"] = str(row["selling_price"])
        self.instance.items_data = items

    def _generate_manual_table_html(self) -> str:
        rows = ""
        total_geral = Decimal("0.00")

        for row in self._build_manual_rows():
            idx = row["idx"]
            product = row["product"]
            quantidade = row["quantity"]
            valor = row["unit_cost"]
            selling_price = row["selling_price"]
            subtotal = row["subtotal"]
            total_geral += subtotal

            estoque_atual = product.stock_products.current_quantity if hasattr(product, "stock_products") else 0
            last_used_price = getattr(product, "last_used_price", None)

            quantity_html = f'<div class="w-full text-center font-medium">{escape(str(quantidade))}</div>'
            unit_cost_html = f'<div class="w-full text-right whitespace-nowrap">{_format_money_display(Money(valor, "BRL"))}</div>'
            selling_price_html = f'<div class="w-full text-right whitespace-nowrap">{_format_money_display(Money(selling_price, "BRL"))}</div>'

            rows += f"""
                <tr class="h-16 border-b border-base-300">
                    <td>
                        <div class="font-medium">{escape(product.name)}</div>
                        <div class="text-xs opacity-50">{escape(product.code)}</div>
                    </td>
                    <td class="text-center">
                        <span class="badge badge-ghost font-mono">{estoque_atual}</span>
                    </td>
                    <td>{quantity_html}</td>
                    <td>{unit_cost_html}</td>
                    <td>{selling_price_html}</td>
                    <td class="text-right whitespace-nowrap">{_format_money_display(getattr(product, "last_purchase_price", None))}</td>
                    <td class="text-right whitespace-nowrap">{_format_money_display(last_used_price)}</td>
                    <td class="text-right font-bold whitespace-nowrap">{Money(subtotal, "BRL")}</td>
                    <td class="text-center">
                        <div class="flex items-center justify-center gap-1">
                            <button type="button" class="btn btn-ghost btn-circle btn-sm text-info" title="Editar Item"
                                    hx-get="{reverse("stock:manual_link_item_editor")}?pk={self.instance.pk}&product_id={product.pk}&item_idx={idx}"
                                    hx-target="#child-modal-container"
                                    hx-swap="innerHTML">
                                <span class="material-icons text-sm">edit</span>
                            </button>
                            <button type="button" class="btn btn-ghost btn-circle btn-sm text-error" title="Desvincular Item"
                                    hx-post="{reverse("stock:unlink_item")}?item_idx={idx}&pk={self.instance.pk}"
                                    hx-target="#step-container">
                                <span class="material-icons text-sm">link_off</span>
                            </button>
                        </div>
                    </td>
                </tr>"""

        return f"""
        <div class="overflow-x-auto rounded-xl border border-base-300">
            <table class="table w-full">
                <thead>
                    <tr class="bg-base-300">
                        <th>Produto</th>
                        <th class="text-center">Em estoque</th>
                        <th class="text-center">Quantidade</th>
                        <th class="text-right">Valor de Custo</th>
                        <th class="text-right">Valor de Venda</th>
                        <th class="text-right">Último valor de compra</th>
                        <th class="text-right">Último valor de venda</th>
                        <th class="text-right">Subtotal</th>
                        <th class="text-center">Ações</th>
                    </tr>
                </thead>
                <tbody>
                    {rows if rows else '<tr><td colspan="9" class="text-center italic py-8">Nenhum item adicionado.</td></tr>'}
                </tbody>
                <tfoot>
                    <tr class="bg-base-300">
                        <td></td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td colspan="2"><p class="text-right font-black text-lg">Total: {Money(total_geral, "BRL")}</p></td>
                    </tr>
                </tfoot>
            </table>
        </div>"""

    @staticmethod
    def _build_lower_price_warning_modal() -> str:
        return """
        <dialog id="manual-import-lower-price-modal" class="modal">
            <div class="modal-box max-w-md bg-base-100 p-0 overflow-hidden">
                <div class="p-6 border-b border-base-200 flex items-start gap-3 bg-base-50">
                    <span class="material-icons text-warning text-3xl">warning</span>
                    <div>
                        <h3 class="font-bold text-xl">Confirmar valor abaixo do ultimo uso</h3>
                        <p class="text-sm text-base-content/80 mt-2">O valor de venda informado para <span id="manual-import-lower-price-product" class="font-semibold">este produto</span> está abaixo do ultimo valor utilizado.</p>
                        <p class="text-sm text-base-content/80 mt-1" id="manual-import-lower-price-last-used"></p>
                        <p class="text-sm text-base-content/80 mt-1">Deseja continuar mesmo assim?</p>
                    </div>
                </div>
                <div class="p-6 flex justify-end gap-3">
                    <button type="button" class="btn btn-ghost" id="manual-import-lower-price-cancel">Cancelar</button>
                    <button type="button" class="btn btn-warning" id="manual-import-lower-price-continue">Continuar mesmo assim</button>
                </div>
            </div>
            <form method="dialog" class="modal-backdrop">
                <button type="button" id="manual-import-lower-price-close">Fechar</button>
            </form>
        </dialog>"""

    @staticmethod
    def _build_lower_price_warning_script() -> str:
        return """
        <script>
            (function() {
                const form = document.getElementById('import-form');
                const confirmInput = document.getElementById('manual-confirm-lower-price-input');
                const modal = document.getElementById('manual-import-lower-price-modal');
                const productLabel = document.getElementById('manual-import-lower-price-product');
                const lastUsedLabel = document.getElementById('manual-import-lower-price-last-used');

                if (!form || !confirmInput || form.dataset.manualLowerPriceWarningReady === '1') {
                    return;
                }

                form.dataset.manualLowerPriceWarningReady = '1';

                let pendingSubmitter = null;

                const getSellingInputs = () => Array.from(form.querySelectorAll('.js-manual-selling-price-input'));
                const formatCurrency = (value) => value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                const getRawValue = (input) => {
                    const hiddenId = input.id ? input.id.replace(/_display$/, '') : '';
                    const hiddenInput = hiddenId ? document.getElementById(hiddenId) : null;
                    return Number.parseFloat(hiddenInput?.value || '0') || 0;
                };
                const findLowerPriceInput = () => getSellingInputs().find((input) => {
                    const lastUsedPrice = Number.parseFloat(input.dataset.lastUsedPrice || '0') || 0;
                    const sellingPrice = getRawValue(input);
                    return lastUsedPrice > 0 && sellingPrice > 0 && sellingPrice < lastUsedPrice;
                }) || null;
                const closeModal = () => {
                    if (modal?.open) {
                        modal.close();
                    }
                };
                const submitForm = () => {
                    if (pendingSubmitter) {
                        form.requestSubmit(pendingSubmitter);
                        return;
                    }
                    form.requestSubmit();
                };
                const openModal = (input) => {
                    const lastUsedPrice = Number.parseFloat(input.dataset.lastUsedPrice || '0') || 0;

                    if (!modal || typeof modal.showModal !== 'function') {
                        return window.confirm('O valor informado esta abaixo do ultimo valor utilizado para este produto. Deseja continuar mesmo assim?');
                    }

                    if (productLabel) {
                        productLabel.textContent = input.dataset.productName || 'este produto';
                    }

                    if (lastUsedLabel) {
                        lastUsedLabel.textContent = `Último valor usado: ${formatCurrency(lastUsedPrice)}`;
                    }

                    if (!modal.open) {
                        modal.showModal();
                    }

                    return null;
                };
                const resetConfirmation = () => {
                    confirmInput.value = '';
                };
                const cancelConfirmation = () => {
                    resetConfirmation();
                    pendingSubmitter = null;
                    closeModal();
                };

                getSellingInputs().forEach((input) => {
                    input.addEventListener('input', resetConfirmation);
                });

                form.addEventListener('submit', (event) => {
                    if (confirmInput.value === '1') {
                        return;
                    }

                    const lowerPriceInput = findLowerPriceInput();
                    if (!lowerPriceInput) {
                        return;
                    }

                    event.preventDefault();
                    pendingSubmitter = event.submitter || null;

                    const fallbackConfirmed = openModal(lowerPriceInput);
                    if (fallbackConfirmed === true) {
                        confirmInput.value = '1';
                        submitForm();
                    }
                });

                document.getElementById('manual-import-lower-price-cancel')?.addEventListener('click', cancelConfirmation);
                document.getElementById('manual-import-lower-price-close')?.addEventListener('click', cancelConfirmation);
                document.getElementById('manual-import-lower-price-continue')?.addEventListener('click', () => {
                    confirmInput.value = '1';
                    closeModal();
                    submitForm();
                });
            })();
        </script>"""

    def clean(self):
        cleaned_data = super().clean()
        rows = self._build_manual_rows()
        self._sync_instance_items_from_rows(rows)

        if not rows:
            raise forms.ValidationError("Adicione pelo menos um item para prosseguir.")

        confirm_lower_price = str(self.data.get("confirm_lower_price") or "").strip() == "1"
        for row in rows:
            warning = build_product_price_warning(product=row["product"], attempted_price=Money(row["selling_price"], "BRL"))
            if warning and not confirm_lower_price:
                self.add_error(None, f"{row['product'].name}: {warning.message}")
                break

        return cleaned_data


# Transfer


class TransferStepOperationForm(CoreModelForm):
    class Meta:
        model = StockTransfer
        fields = ["operation_type"]
        widgets = {
            "operation_type": SearchableSelectInput(),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML('<h2 class="text-2xl font-bold mb-6">Tipo de Operação</h2>'),
                Field("operation_type"),
            )
        )


class TransferStepReasonForm(CoreModelForm):
    selected_product_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = StockTransfer
        fields = ["reason"]
        widgets = {"reason": TextareaInput()}

    def _render_search_and_list_html(self) -> str:
        search_query = self.request.GET.get("source_search", "").strip() if self.request is not None else ""
        queryset = Product.objects.filter(workshop=self.instance.source_workshop, is_active=True, stock_products__current_quantity__gt=0).select_related("stock_products").order_by("name")

        if search_query:
            queryset = apply_text_search(queryset, search_value=search_query, lookups=("code", "name"))

        selected_ids = {str(item.get("source_product_id")) for item in (self.instance.items_data or [])}

        rows = ""
        for product in queryset[:15]:
            is_selected = str(product.id) in selected_ids
            row_class = "bg-primary/10 text-primary" if is_selected else "hover:bg-base-200 cursor-pointer"
            icon = "check_circle" if is_selected else "add_circle_outline"

            action_url = reverse("stock:remove_transfer_item") if is_selected else reverse("stock:add_transfer_source_item")
            hx_vals = f'{{"pk": "{self.instance.pk}", "source_product_id": "{product.id}"}}' if is_selected else f'{{"pk": "{self.instance.pk}", "product_id": "{product.id}", "quantity": "1"}}'

            rows += f"""
            <tr class="{row_class}" 
                hx-post="{action_url}" 
                hx-vals='{hx_vals}'
                hx-target="#step-container">
                <td class="w-10"><span class="material-icons text-sm">{icon}</span></td>
                <td>
                    <div class="font-bold">{product.name}</div>
                    <div class="text-[10px] opacity-70">{product.code or "S/ Cód"}</div>
                </td>
                <td class="text-right font-mono">{product.stock_products.current_quantity if product.stock_products else 0}</td>
            </tr>"""

        search_url = f"{reverse('stock:transfer_update', kwargs={'pk': self.instance.pk})}?step=2"

        selected_items_html = self._render_selected_items_html()

        return f"""
        <div class="space-y-4">
            <input type="text" name="source_search" value="{search_query}" 
                   class="input input-bordered w-full" 
                   placeholder="Buscar produto para seleção..."
                   hx-get="{search_url}"
                   hx-trigger="keyup changed delay:300ms"
                   hx-target="#step-container">

            <div class="overflow-x-auto rounded-lg border border-base-300 max-h-60">
                <table class="table table-sm w-full">
                    <thead class="bg-base-200 sticky top-0">
                        <tr>
                            <th></th>
                            <th>Produto</th>
                            <th class="text-right">Estoque Atual</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows or '<tr><td colspan="3" class="text-center py-8">Nenhum produto encontrado.</td></tr>'}
                    </tbody>
                </table>
            </div>
            {selected_items_html}
        </div>"""

    def _render_selected_items_html(self) -> str:
        items = self.instance.items_data or []
        rows = ""
        for idx, item in enumerate(items):
            product = Product.objects.filter(id=item.get("source_product_id"), workshop=self.instance.source_workshop).first()
            if not product:
                continue

            quantity = int(str(item.get("qtd", 1) or 1))

            quantity_input = NumberInput(mode="positive").render(
                name=f"items_qty_{idx}",
                value=str(quantity),
                attrs={
                    "class": "text-center input input-bordered input-sm w-16",
                    "min": "1",
                    "hx-post": reverse("stock:update_transfer_item_data", kwargs={"pk": self.instance.pk}),
                    "hx-trigger": "change delay:300ms",
                    "hx-vals": f"js:{{item_idx: {idx}}}",
                    "hx-target": "#step-container",
                },
            )

            rows += f"""
            <tr class="border-b border-base-300">
                <td>
                    <div class="font-bold">{product.name}</div>
                    <div class="text-[10px] opacity-70">{product.code}</div>
                </td>
                <td class="text-center">{quantity_input}</td>
                <td class="text-right">
                    <button type="button" class="btn btn-ghost btn-xs text-error"
                            hx-post="{reverse("stock:remove_transfer_item")}?pk={self.instance.pk}&item_idx={idx}"
                            hx-target="#step-container">
                        <span class="material-icons text-sm">delete</span>
                    </button>
                </td>
            </tr>"""

        if not rows:
            return ""

        return f"""
        <div class="mt-6">
            <h3 class="text-sm font-bold uppercase mb-3 opacity-60">Itens Selecionados</h3>
            <div class="overflow-x-auto rounded-lg border border-base-300">
                <table class="table table-sm w-full">
                    <thead class="bg-base-200">
                        <tr>
                            <th>Produto</th>
                            <th class="text-center">Qtd</th>
                            <th class="text-right">Ação</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>"""

    def __init__(self, *args: Any, **kwargs: Any):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.fields["reason"].required = True
        self.fields["reason"].label = "Motivo da Baixa"
        self.fields["reason"].widget = forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Ex: Danificado na montagem, item vencido, uso interno...",
                "hx-post": reverse("stock:update_transfer_reason", kwargs={"pk": self.instance.pk}),
                "hx-trigger": "blur",
                "hx-swap": "none",
            }
        )

        self.helper.layout = Layout(
            Div(
                HTML('<h2 class="text-2xl font-bold mb-2 text-base-content">Motivo da Baixa</h2>'),
                HTML('<p class="text-sm text-base-content/70 mb-6">Selecione o item e explique por que estes item esta saindo do estoque.</p>'),
                Div(
                    # Coluna da Esquerda: Busca e Seleção
                    Div(HTML(self._render_search_and_list_html()), css_class="col-span-12 lg:col-span-7"),
                    # Coluna da Direita: Justificativa
                    Div(
                        HTML('<h3 class="text-sm font-bold uppercase mb-4 opacity-60">Justificativa</h3>'),
                        Field("reason"),
                        HTML("""<div class="alert bg-warning/10 text-warning border-none mt-4">
                            <span class="material-icons">info</span>
                            <span class="text-xs">A baixa irá alterar a quantidade do item selecionado permanentemente do estoque.</span>
                        </div> """),
                        css_class="col-span-12 lg:col-span-5 bg-base-200/30 p-4 rounded-xl border border-base-300",
                    ),
                    css_class="grid grid-cols-12 gap-6",
                ),
            )
        )

    def clean(self):
        cleaned_data = super().clean()

        if not self.instance.items_data:
            self.add_error(None, "Você precisa selecionar um item da lista para prosseguir com a baixa.")

        reason = self.cleaned_data.get("reason")
        if len(reason) < 5:
            raise forms.ValidationError("Por favor, forneça um motivo mais detalhado para a baixa.")

        return cleaned_data

    def clean_reason(self):
        value = self.cleaned_data.get("reason")
        return sentence_case(value) if value else value


class TransferStepWorkshopsForm(CoreModelForm):
    source_workshop = forms.ModelChoiceField(queryset=Workshop.objects.none(), label="Oficina de Origem", widget=SearchableSelectInput())
    destination_workshop = forms.ModelChoiceField(queryset=Workshop.objects.none(), label="Oficina de Destino", widget=SearchableSelectInput())

    class Meta:
        model = StockTransfer
        fields = ["source_workshop", "destination_workshop"]

    def __init__(self, *args: Any, **kwargs: Any):
        self.request = kwargs.pop("request", None)
        self.allowed_workshops = kwargs.pop("allowed_workshops", Workshop.objects.none())
        super().__init__(*args, **kwargs)

        self.fields["source_workshop"].queryset = self.allowed_workshops
        self.fields["destination_workshop"].queryset = self.allowed_workshops

        active_workshop_id = self.request.session.get("active_workshop_id") if self.request is not None else None
        if not self.instance.pk and active_workshop_id:
            self.initial.setdefault("destination_workshop", active_workshop_id)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML('<h2 class="text-2xl font-bold mb-6 text-base-content">Origem e Destino</h2>'),
                Div(
                    Field("source_workshop", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("destination_workshop", wrapper_class="col-span-12 lg:col-span-6"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                HTML(
                    """
                    <div class="alert mt-6 bg-info/10 text-info border-none">
                        <span class="material-icons">swap_horiz</span>
                        <span class="text-xs">Selecione a oficina de onde o estoque sairá e a oficina que receberá os itens.</span>
                    </div>
                    """
                ),
            )
        )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        source_workshop = cleaned_data.get("source_workshop")
        destination_workshop = cleaned_data.get("destination_workshop")

        if source_workshop and destination_workshop and source_workshop == destination_workshop:
            self.add_error("destination_workshop", "Selecione uma oficina diferente da origem.")

        if source_workshop and destination_workshop and source_workshop.account_id != destination_workshop.account_id:
            self.add_error("destination_workshop", "A transferência só pode ocorrer entre oficinas da mesma conta.")

        if self.request is not None:
            for field_name, workshop in (("source_workshop", source_workshop), ("destination_workshop", destination_workshop)):
                if workshop and not has_workshop_perm(
                    user=self.request.user,
                    workshop=workshop,
                    app_label="stock",
                    model="stockmovement",
                    codename="change_stockmovement",
                    request=self.request,
                ):
                    self.add_error(field_name, "Você não possui permissão para movimentar estoque nesta oficina.")

        return cleaned_data


class TransferItemsForm(CoreModelForm):
    class Meta:
        model = StockTransfer
        fields = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(HTML(self._build_transfer_items_html()))

    def _build_transfer_items_html(self) -> str:
        return f"""
        <div class="space-y-6">
            <div>
                <h2 class="text-2xl font-bold text-base-content">Pareamento de Produtos</h2>
                <p class="text-sm text-base-content/70 mt-1">Escolha na esquerda os itens da oficina de origem e vincule ou crie o produto correspondente na oficina de destino.</p>
            </div>
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
                {self._render_source_column()}
                {self._render_destination_column()}
            </div>
        </div>"""

    def _selected_items_map(self) -> dict[str, dict[str, Any]]:
        return {str(item.get("source_product_id")): item for item in (self.instance.items_data or []) if item.get("source_product_id")}

    def _source_products(self):
        search_query = self.request.GET.get("source_search", "").strip() if self.request is not None else ""
        queryset = Product.objects.filter(workshop=self.instance.source_workshop, is_active=True, stock_products__current_quantity__gt=0).select_related("group", "stock_products").order_by("name")
        if search_query:
            queryset = apply_text_search(queryset, search_value=search_query, lookups=("code", "name", "brand"))
        return queryset, search_query

    def _render_source_column(self) -> str:
        queryset, search_query = self._source_products()
        selected_map = self._selected_items_map()
        rows = ""

        for product in queryset:
            selected_item = selected_map.get(str(product.id))
            stock_entry = StockProduct.objects.filter(workshop=self.instance.source_workshop, product=product).first()
            available_quantity = stock_entry.current_quantity if stock_entry else 0
            selected = selected_item is not None
            row_class = "bg-primary/5 border-primary/20" if selected else ""

            rows += f"""
            <tr class="border-b border-base-300 {row_class}">
                <td>
                    <div class="font-semibold">{product.name}</div>
                    <div class="text-xs opacity-60">{product.code or "Sem codigo"}</div>
                </td>
                <td class="text-center"><span class="badge badge-ghost font-mono">{available_quantity}</span></td>
                <td class="text-right">
                    {self._render_source_action_button(product_id=product.id, selected=selected)}
                </td>
            </tr>"""

        search_url = f"{reverse('stock:transfer_update', kwargs={'pk': self.instance.pk})}?step=3"
        return f"""
        <div class="card bg-base-100 border border-base-300 shadow-sm">
            <div class="card-body p-4 space-y-4">
                <div>
                    <div class="flex items-center justify-between gap-3 mb-1">
                        <h3 class="text-base font-bold uppercase">Origem</h3>
                        <span class="badge badge-outline">{self.instance.source_workshop.name}</span>
                    </div>
                    <p class="text-sm text-base-content/70">Selecione os itens que vao sair do estoque.</p>
                </div>
                <label class="form-control w-full">
                    <input type="text" name="source_search" value="{search_query}" class="input input-bordered w-full"
                           placeholder="Buscar por codigo, nome ou marca"
                           hx-get="{search_url}"
                           hx-include="this"
                           hx-vals='{{"pk": "{self.instance.pk}"}}'
                           hx-trigger="keyup changed delay:300ms"
                           hx-target="#step-container"
                           hx-push-url="true">
                </label>
                <div class="overflow-x-auto rounded-xl border border-base-300 max-h-[34rem]">
                    <table class="table table-sm w-full">
                        <thead class="bg-base-200 sticky top-0 z-10">
                            <tr>
                                <th>Produto</th>
                                <th class="text-center">Estoque</th>
                                <th class="text-right">Acao</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows or '<tr><td colspan="3" class="text-center italic py-8">Nenhum produto com estoque encontrado.</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>"""

    def _render_source_action_button(self, *, product_id: int, selected: bool) -> str:
        if selected:
            return f"""
            <button type="button" class="btn btn-error btn-xs"
                    hx-post="{reverse("stock:remove_transfer_item")}?pk={self.instance.pk}&source_product_id={product_id}"
                    hx-target="#step-container">
                Remover
            </button>"""
        return f"""
        <button type="button" class="btn btn-primary btn-xs"
                hx-post="{reverse("stock:add_transfer_source_item")}"
                hx-vals='{{"pk": "{self.instance.pk}", "product_id": "{product_id}", "quantity": "1"}}'
                hx-target="#step-container">
            Selecionar
        </button>"""

    def _render_destination_column(self) -> str:
        items = self.instance.items_data or []
        rows = ""
        total_geral = Decimal("0.00")

        for idx, item in enumerate(items):
            source_product = Product.objects.filter(id=item.get("source_product_id"), workshop=self.instance.source_workshop).first()
            destination_product = Product.objects.filter(id=item.get("destination_product_id"), workshop=self.instance.destination_workshop).first()
            if source_product is None:
                continue

            stock_entry = StockProduct.objects.filter(workshop=self.instance.source_workshop, product=source_product).first()
            available_quantity = stock_entry.current_quantity if stock_entry else 0
            quantity = int(str(item.get("qtd", 1) or 1))
            value = Decimal(str(item.get("valor", "0")).replace(",", "."))
            subtotal = Decimal(quantity) * value
            total_geral += subtotal

            quantity_input = NumberInput(mode="positive").render(
                name=f"items_qty_{idx}",
                value=str(quantity),
                attrs={
                    "class": "text-center input input-bordered input-sm w-20",
                    "min": "1",
                    "hx-post": reverse("stock:update_transfer_item_data", kwargs={"pk": self.instance.pk}),
                    "hx-trigger": "change delay:300ms",
                    "hx-vals": f"js:{{item_idx: {idx}}}",
                    "hx-target": "#step-container",
                    "hx-swap": "innerHTML",
                },
            )

            rows += f"""
            <tr class="border-b border-base-300 align-top">
                <td>
                    <div class="font-semibold">{source_product.name}</div>
                    <div class="text-xs opacity-60">{source_product.code or "Sem codigo"}</div>
                </td>
                <td class="text-center">
                    <span class="badge badge-ghost font-mono">{available_quantity}</span>
                </td>
                <td class="text-center">{quantity_input}</td>
                <td>{self._render_destination_cell(idx=idx, destination_product=destination_product)}</td>
                <td class="text-right font-semibold">{Money(subtotal, "BRL")}</td>
                <td class="text-right">
                    <button type="button" class="btn btn-ghost btn-xs text-error"
                            hx-post="{reverse("stock:remove_transfer_item")}?pk={self.instance.pk}&item_idx={idx}"
                            hx-target="#step-container">
                        Remover
                    </button>
                </td>
            </tr>"""

        return f"""
        <div class="card bg-base-100 border border-base-300 shadow-sm">
            <div class="card-body p-4 space-y-4">
                <div class="flex items-center justify-between gap-3">
                    <div>
                        <h3 class="text-base font-bold uppercase">Destino</h3>
                        <p class="text-sm text-base-content/70">Associe cada item selecionado a um produto da oficina de destino.</p>
                    </div>
                    <span class="badge badge-outline">{self.instance.destination_workshop.name}</span>
                </div>
                <div class="overflow-x-auto rounded-xl border border-base-300 max-h-[34rem]">
                    <table class="table table-sm w-full">
                        <thead class="bg-base-200 sticky top-0 z-10">
                            <tr>
                                <th>Produto de Origem</th>
                                <th class="text-center">Estoque</th>
                                <th class="text-center">Quantidade</th>
                                <th>Produto no Destino</th>
                                <th class="text-right">Subtotal</th>
                                <th class="text-right">Acao</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows or '<tr><td colspan="6" class="text-center italic py-8">Selecione itens na coluna da esquerda para montar a transferencia.</td></tr>'}
                        </tbody>
                    </table>
                </div>
                <div class="pt-2 border-t border-base-300 flex items-center justify-between font-semibold">
                    <span>Total selecionado</span>
                    <span>{Money(total_geral, "BRL")}</span>
                </div>
            </div>
        </div>"""

    def _render_destination_cell(self, *, idx: int, destination_product: Product | None) -> str:
        if destination_product is not None:
            return f"""
            <div class="space-y-2">
                <div>
                    <div class="text-[11px] uppercase tracking-wide text-success font-semibold">Produto vinculado</div>
                    <div class="font-medium">{destination_product.name}</div>
                    <div class="text-xs opacity-50">{destination_product.code}</div>
                </div>
                <div class="flex gap-2">
                    <button type="button" class="btn btn-outline btn-xs" hx-target="#modal-container"
                            hx-get="{reverse("stock:transfer_destination_link")}?pk={self.instance.pk}&item_idx={idx}">Vincular Outro</button>
                    <button type="button" class="btn btn-ghost btn-xs text-error"
                            hx-post="{reverse("stock:transfer_unlink_destination")}?pk={self.instance.pk}&item_idx={idx}"
                            hx-target="#step-container">Desvincular Item</button>
                </div>
            </div>"""

        return f"""
        <div class="flex flex-wrap gap-2 items-center">
            <span class="italic text-warning text-xs">Nenhum produto vinculado</span>
            <button type="button" class="btn btn-primary btn-xs" hx-target="#modal-container"
                    hx-get="{reverse("stock:transfer_destination_link")}?pk={self.instance.pk}&item_idx={idx}">Vincular Produto</button>
            <button type="button" class="btn btn-success btn-xs"
                    hx-post="{reverse("stock:create_transfer_destination_product")}?pk={self.instance.pk}&item_idx={idx}"
                    hx-target="#step-container">Cadastrar Produto</button>
        </div>"""

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if not self.instance.items_data:
            self.add_error(None, "Selecione ao menos um item na oficina de origem para transferir.")
            return cleaned_data

        for item in self.instance.items_data:
            if not item.get("destination_product_id"):
                self.add_error(None, "Existem itens sem produto vinculado na oficina de destino.")
                break

        return cleaned_data


class TransferSummaryForm(CoreModelForm):
    class Meta:
        model = StockTransfer
        fields = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(HTML(self._build_summary_html()))

    def _build_summary_html(self) -> str:
        rows = ""
        total = Decimal("0.00")
        is_transfer = self.instance.operation_type == StockTransfer.OperationType.TRANSFER

        for item in self.instance.items_data or []:
            source_product = Product.objects.filter(id=item.get("source_product_id"), workshop=self.instance.source_workshop).first()
            if source_product is None:
                continue

            destination_product = None
            if is_transfer:
                destination_product = Product.objects.filter(id=item.get("destination_product_id"), workshop=self.instance.destination_workshop).first()
                if destination_product is None:
                    continue

            quantidade = int(str(item.get("qtd", 0) or 0))
            valor = Decimal(str(item.get("valor", "0")).replace(",", "."))
            subtotal = Decimal(quantidade) * valor
            total += subtotal

            if is_transfer:
                dest_cell = f'<td><div class="font-medium">{destination_product.name}</div><div class="text-xs opacity-50">{destination_product.code}</div></td>'
            else:
                dest_cell = ""

            rows += f"""
            <tr>
                <td><div class="font-medium">{source_product.name}</div><div class="text-xs opacity-50">{source_product.code}</div></td>
                {dest_cell}
                <td class="text-center">{quantidade}</td>
                <td class="text-right">{Money(valor, "BRL")}</td>
                <td class="text-right font-bold">{Money(subtotal, "BRL")}</td>
            </tr>"""

        table_header = (
            """
            <th>Origem</th>
            <th>Destino</th>
            <th class="text-center">Qtd</th>
            <th class="text-right">Custo</th>
            <th class="text-right">Subtotal</th>
        """
            if is_transfer
            else """
            <th>Produto</th>
            <th class="text-center">Qtd</th>
            <th class="text-right">Custo Unitário</th>
            <th class="text-right">Subtotal</th>
        """
        )

        destination_block = ""
        if is_transfer:
            dest_name = self.instance.destination_workshop.name if self.instance.destination_workshop else "---"
            destination_block = f"""
                <div class="divider my-1"></div>
                <p class="text-sm opacity-70">Entrando em</p>
                <p class="text-lg font-bold">{dest_name}</p>
            """

        reason_block = ""
        if not is_transfer and self.instance.reason:
            reason_block = f"""
                <div class="card bg-warning/5 border border-warning/20 shadow-sm mt-4">
                    <div class="card-body p-4">
                        <h3 class="text-xs font-bold uppercase opacity-60">Motivo da Baixa</h3>
                        <p class="text-sm italic">"{self.instance.reason}"</p>
                    </div>
                </div>
            """

        return f"""
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div class="lg:col-span-8">
                <div class="card bg-base-200 shadow-sm">
                    <div class="card-body p-4">
                        <h3 class="text-base font-bold uppercase mb-3">{"Itens da Transferência" if is_transfer else "Itens para Baixa"}</h3>
                        <div class="overflow-x-auto rounded-xl border border-base-300">
                            <table class="table w-full">
                                <thead>
                                    <tr class="bg-base-300">
                                        {table_header}
                                    </tr>
                                </thead>
                                <tbody>{rows or '<tr><td colspan="5" class="text-center italic py-8">Nenhum item selecionado.</td></tr>'}</tbody>
                            </table>
                        </div>
                    </div>
                </div>
                {reason_block}
            </div>
            <div class="lg:col-span-4 space-y-6">
                <div class="card bg-base-200 shadow-sm">
                    <div class="card-body p-4">
                        <h3 class="text-base font-bold uppercase mb-3">Detalhes</h3>
                        <p class="text-sm opacity-70">Oficina de Origem</p>
                        <p class="text-lg font-bold">{self.instance.source_workshop.name}</p>
                        {destination_block}
                    </div>
                </div>
                <div class="card bg-base-200 shadow-sm">
                    <div class="card-body p-4">
                        <h3 class="text-base font-bold uppercase mb-3">{"Total da Transferência" if is_transfer else "Total da Baixa"}</h3>
                        <div class="flex justify-between items-center font-black text-xl">
                            <span>{Money(total, "BRL")}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>"""

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if not self.instance.items_data:
            self.add_error(None, "Adicione ao menos um item para transferir.")

        is_transfer = self.instance.operation_type == StockTransfer.OperationType.TRANSFER
        for item in self.instance.items_data:
            if is_transfer and not item.get("destination_product_id"):
                self.add_error(None, "Existem itens sem produto vinculado na oficina de destino.")
                break

            try:
                quantity = int(str(item.get("qtd", 0) or 0))
            except (TypeError, ValueError):
                quantity = 0

            source_entry = StockProduct.objects.filter(workshop=self.instance.source_workshop, product_id=item.get("source_product_id")).select_related("product").first()
            if quantity <= 0:
                self.add_error(None, "Todas as quantidades devem ser maiores que zero.")
                break
            if source_entry is None:
                self.add_error(None, "Um dos itens da transferência não pôde ser localizado.")
                break
            if source_entry.current_quantity < quantity:
                self.add_error(None, f"Saldo insuficiente para o produto {source_entry.product.name} na oficina de origem.")
                break

        return cleaned_data

    @transaction.atomic
    def save(self, commit: bool = True) -> StockTransfer:
        instance: StockTransfer = super().save(commit=False)
        if instance.status == StockTransfer.TransferStatus.COMPLETED:
            return instance

        is_transfer = instance.operation_type == StockTransfer.OperationType.TRANSFER
        source_product_ids = [int(item["source_product_id"]) for item in instance.items_data]
        source_entries = StockProduct.objects.select_for_update().select_related("product").filter(workshop=instance.source_workshop, product_id__in=source_product_ids)
        source_by_product_id = {entry.product_id: entry for entry in source_entries}

        if is_transfer:
            destination_product_ids = [int(item["destination_product_id"]) for item in instance.items_data]
            destination_entries = StockProduct.objects.select_for_update().select_related("product").filter(workshop=instance.destination_workshop, product_id__in=destination_product_ids)
            destination_by_product_id = {entry.product_id: entry for entry in destination_entries}
        else:
            destination_by_product_id = {}

        parsed_items: list[tuple[StockProduct, StockProduct, int]] = []
        for item in instance.items_data:
            quantity = int(str(item.get("qtd", 0) or 0))
            if quantity <= 0:
                raise forms.ValidationError("Todas as quantidades devem ser maiores que zero.")

            source_product_id = int(item["source_product_id"])
            destination_product_id = int(item["destination_product_id"]) if is_transfer else None
            source_entry = source_by_product_id.get(source_product_id)
            destination_entry = destination_by_product_id.get(destination_product_id) if is_transfer else None

            if source_entry is None or (is_transfer and destination_entry is None):
                raise forms.ValidationError("Um dos itens da transferência não pôde ser localizado.")
            if source_entry.current_quantity < quantity:
                raise forms.ValidationError(f"Saldo insuficiente para o produto {source_entry.product.name} na oficina de origem.")

            parsed_items.append((source_entry, destination_entry, quantity))

        for source_entry, destination_entry, quantity in parsed_items:
            source_entry.current_quantity -= quantity
            source_entry.save(update_fields=["current_quantity"])

            if is_transfer and destination_entry:
                destination_entry.current_quantity += quantity
                destination_entry.save(update_fields=["current_quantity"])

            StockMovement.objects.create(
                workshop=instance.source_workshop,
                stock_transfer=instance,
                stock_product=source_entry,
                type=StockMovement.MovementType.EXIT,
                quantity=quantity,
                status=StockMovement.MovementStatus.APPROVED,
                transcation_by=self.request.user if self.request is not None else None,
            )

            if is_transfer and instance.destination_workshop and destination_entry:
                StockMovement.objects.create(
                    workshop=instance.destination_workshop,
                    stock_transfer=instance,
                    stock_product=destination_entry,
                    type=StockMovement.MovementType.ENTRY,
                    quantity=quantity,
                    status=StockMovement.MovementStatus.APPROVED,
                    transcation_by=self.request.user if self.request is not None else None,
                )

        instance.status = StockTransfer.TransferStatus.COMPLETED
        if commit:
            instance.save()
        return instance


# Quick Forms


class QuickProductForm(CoreModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "unit", "group", "cost_price", "selling_price", "profit_margin", "ncm", "origin_cst", "purpose"]
        widgets = {
            "code": TextInput(),
            "name": TextInput(),
            "unit": SearchableSelectInput(),
            "group": SearchableSelectInput(),
            "cost_price": MoneyInput(),
            "selling_price": MoneyInput(),
            "profit_margin": PercentageInput(),
            "ncm": TextInput(attrs={"placeholder": "Ex: 87089990"}),
            "origin_cst": SearchableSelectInput(),
            "purpose": SearchableSelectInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if workshop:
            self.fields["group"].queryset = self.fields["group"].queryset.filter(workshop=workshop)

        self.fields["ncm"].required = False

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Div(
                    Field("code", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("name", wrapper_class="col-span-12 lg:col-span-9"),
                    Field("unit", wrapper_class="col-span-12 lg:col-span-6"),
                    Div(
                        Field("group", wrapper_class="w-full"),
                        HTML(f'''<div class="flex items-center ml-2"> 
                                    <button type="button" 
                                        style="height: 60%; aspect-ratio: 1 / 1;"
                                        class="btn btn-primary rounded-full flex items-center justify-center p-0" 
                                        hx-get="{reverse("stock:group_quick_create")}" 
                                        hx-target="#group-modal-container"
                                        title="Cadastrar novo grupo">
                                        <span class="material-icons" style="font-size: 1.5rem;">add</span>
                                    </button>
                                </div>'''),
                        css_class="col-span-12 lg:col-span-6 flex items-stretch h-12",
                    ),
                    Field("cost_price", wrapper_class="col-span-12 lg:col-span-4"),
                    Div(
                        Field("selling_price", wrapper_class="w-full"),
                        HTML('<div class="text-error text-xs" x-show="priceError" x-cloak>⚠️ Menor que o custo</div>'),
                        css_class="col-span-12 lg:col-span-4",
                    ),
                    Field("profit_margin", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("ncm", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("origin_cst", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("purpose", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-3",
                ),
                **{
                    "x-data": """{
                        priceError: false,
                        calculateMargin() {
                            const getVal = (id) => parseFloat(document.getElementById(id)?.value) || 0;
                            let cost = getVal("id_cost_price_0");
                            let sell = getVal("id_selling_price_0");
                            this.priceError = sell > 0 && sell < cost;
                            let marginEl = document.getElementById("id_profit_margin_display");
                            if (sell > 0) {
                                let m = ((sell - cost) / sell) * 100;
                                marginEl.value = m.toFixed(2).replace(".", ",");
                                marginEl.dispatchEvent(new Event('input'));
                            }
                        }
                    }""",
                    "@input": "calculateMargin()",
                },
            )
        )

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return sentence_case(value) if value else value


class QuickSupplierForm(AddressFormMixin, CoreModelForm):
    class Meta:
        model = Supplier
        fields = ["cnpj", "name", "contact_person", "phone", "mobile", "email", "registration_date", "is_active", "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "estado"]
        widgets = {
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "name": TextInput(),
            "contact_person": TextInput(),
            "phone": PhoneInput(),
            "mobile": PhoneInput(),
            "email": EmailInput(),
            "registration_date": CalendarDateInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.setup_address_fields()
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("cnpj", wrapper_class="col-span-12 lg:col-span-4"),
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                Field("contact_person", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("phone", wrapper_class="col-span-12 lg:col-span-4"),
                Field("mobile", wrapper_class="col-span-12 lg:col-span-4"),
                Field("email", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("registration_date", wrapper_class="col-span-12 lg:col-span-6"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-6"),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                # Seção: Endereço
                address_layout(),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        cnpj = cleaned_data.get("cnpj")

        # Só validamos se tivermos o CNPJ e a workshop disponível
        if cnpj and self.workshop:
            queryset = Supplier.objects.filter(workshop=self.workshop, cnpj=cnpj)

            # Se for edição (update), ignoramos o próprio objeto
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                # Adiciona o erro especificamente no campo CNPJ
                self.add_error("cnpj", "Já existe um fornecedor cadastrado com este CNPJ nesta oficina.")

        return cleaned_data

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return name_case(value) if value else value

    def clean_contact_person(self):
        value = self.cleaned_data.get("contact_person")
        return name_case(value) if value else value

    def clean_logradouro(self):
        value = self.cleaned_data.get("logradouro")
        return sentence_case(value) if value else value

    def clean_complemento(self):
        value = self.cleaned_data.get("complemento")
        return sentence_case(value) if value else value

    def clean_bairro(self):
        value = self.cleaned_data.get("bairro")
        return sentence_case(value) if value else value

    def clean_cidade(self):
        value = self.cleaned_data.get("cidade")
        return sentence_case(value) if value else value


class CatalogGroupQuickForm(CoreModelForm):
    class Meta:
        model = CatalogGroup
        fields = ["name"]
        widgets = {"name": TextInput(attrs={"placeholder": "Grupo"})}

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Div(Field("name", wrapper_class="col-span-1"), css_class="grid grid-cols-1 gap-4 items-start"))

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name and self.workshop:
            # Validação extra para garantir unicidade case-insensitive no workshop
            qs = CatalogGroup.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um grupo com este nome.")
        return sentence_case(name) if name else name
