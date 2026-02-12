import re
from datetime import datetime
from decimal import Decimal

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django.db import transaction
import gzip
import base64
from lxml import etree
from django.urls import reverse
from django.utils import timezone
from djmoney.forms import MoneyField
from djmoney.money import Money
from pynfe.processamento import ComunicacaoSefaz

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.widgets import TextInput, SelectInput, NumberInput, MoneyInput, CalendarDateInput, PercentageInput

from apps.stock.models import StockPaymentMethod, StockImport, StockProduct, StockMovement, SefazZipCache

from apps.stock.utils import NFParser
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


class ImportStep1Form(forms.ModelForm):
    xml_file = forms.FileField(label="Selecione o arquivo XML", required=False)
    access_key = forms.CharField(label="Insira a chave de acesso", max_length=47, required=False, widget=TextInput(attrs={"oninput": "this.value = this.value.replace(/[^0-9]/g, '')"}))

    class Meta:
        model = StockImport
        fields = ["method"]
        widgets = {"method": forms.Select(attrs={"x-model": "method", "class": "select select-bordered w-full"})}

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        if self.instance:
            self.fields["method"].initial = self.instance.method

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                # Coluna Esquerda: Seleção
                Div(
                    HTML('<h2 class="text-2xl font-bold mb-6">Método de Importação</h2>'),
                    Field("method", css_class="select select-bordered w-full"),
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
        nf_data = None

        if method == "XML":
            xml_file = self.files.get("xml_file")
            nf_data = NFParser.parse_nfe_xml_to_dict(xml_file)
        elif method == "KEY":
            chave = re.sub(r"\D", "", self.cleaned_data.get("access_key"))
            workshop = self.workshop

            try:
                comunicacao = ComunicacaoSefaz(workshop.uf, workshop.pfx_certificate.path, workshop.certificate_password)
                cnpj_clean = re.sub(r"\D", "", workshop.cnpj)
                xml_response = comunicacao.consulta_distribuicao(cnpj=cnpj_clean, chave=chave)
                nf_data = NFParser.parse_nfe_xml_to_dict(xml_response.content)
            except Exception as e:
                raise forms.ValidationError(f"Erro ao importar chave no Sefaz: {str(e)}")

        if nf_data:
            if StockImport.objects.filter(workshop=self.workshop, nf_key=nf_data["nf_key"]).exists():
                raise forms.ValidationError("Não é possível importar a mesma NF mais de uma vez.")

            obj.nf_number = nf_data["nf_number"]
            obj.nf_key = nf_data["nf_key"]
            obj.supplier_cnpj = nf_data["supplier_cnpj"]
            obj.supplier_name = nf_data["supplier_name"]
            obj.items_data = nf_data["items"]
            obj.payments_data = nf_data['payments']

        if commit:
            obj.save()
        return obj

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")

        if method == 'XML' and not self.files.get('xml_file'):
            self.add_error("xml_file", "O arquivo XML é obrigatório para este método.")

        if method == "KEY":
            key = cleaned_data.get("access_key")
            if not key or len(re.sub(r"\D", "", key)) != 44:
                self.add_error("access_key", "Insira uma chave válida de 44 dígitos.")

            if not self.workshop.pfx_certificate or not self.workshop.certificate_password:
                self.add_error(None, "Oficina sem certificado configurado.")

        return cleaned_data


class ImportStepSupplierForm(forms.ModelForm):
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
        nNF = self.instance.nf_number or "---"

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


class ImportStepItemsForm(forms.ModelForm):
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
                    <td class="text-right font-semibold whitespace-nowrap">{Money(valor_unit, 'BRL')}</td>
                    <td class="text-right font-bold whitespace-nowrap">{Money(valor_total, 'BRL')}</td>
                </tr>"""


            product_id = item.get("linked_product_id")
            product = Product.objects.filter(id=product_id, workshop=self.workshop).first() if product_id else None
            if product:
                rows_system += f"""<tr class="h-16 border-b">
                        <td class="max-w-[150px]">
                            <div class="text-sm font-medium truncate" title="{product.name}">{product.name}</div>
                            <div class="text-[10px] opacity-50 font-mono">{product.code}</div>
                        </td>
                        <td class="text-center">{product.cost_price}</td>
                        <td class="text-center">{product.selling_price}</td>
                        <td class="text-center">{product.stock_products.current_quantity}</td>
                        <td class="text-center">
                            <button type="button" class="btn btn-ghost btn-xs text-error" 
                                    hx-post='{reverse("stock:unlink_item")}?item_idx={idx}&pk={self.instance.pk}' hx-target="#step-container">
                                <span class="material-icons text-xs">link_off</span>
                            </button>
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
            <div class="col-span-12 lg:col-span-5">
                <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">Itens Importados</h3>
                <div class="rounded-xl border border-base-300 overflow-x-auto">
                    <table class="table table-sm w-full">
                        <thead>
                            <tr class="bg-base-300">
                                <th>Descrição</th>
                                <th class="text-center">Quantidade</th>
                                <th class="text-right">Valor Unitário</th>
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
        for item in self.instance.items_data:
            if not item.get("linked_product_id"):
                self.add_error(None, "Existem itens pendentes de vínculo.")
        return cleaned_data


class ImportStepPaymentForm(forms.ModelForm):
    payment_method = forms.ChoiceField(choices=StockPaymentMethod.PAYMENT_METHOD_CHOICES, label="Forma de Pagamento", widget=SelectInput, required=False)
    installments_count = forms.IntegerField(min_value=1, initial=1, label="Número de Parcelas", widget=NumberInput, required=False)
    first_amount = MoneyField(max_digits=14, decimal_places=2, label="Valor Pago", widget=MoneyInput, required=False)
    payment_date = forms.DateField(label="Data de Vencimento", widget=CalendarDateInput, required=False)

    total_nf_display = forms.CharField(label="Valor Total", required=False, widget=MoneyInput)
    total_allocated_display = forms.CharField(label="Valor Pago", required=False, widget=MoneyInput)
    pending_display = forms.CharField(label="Valor Pendente", required=False, widget=MoneyInput)

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

        # Cálculos Financeiros
        valor_total = sum(
            Decimal(str(item.get("valor", 0))) * Decimal(str(item.get("qtd", 0)))
            for item in self.import_items
        )
        valor_pago = sum(
            Decimal(str(p.get("total_paid", 0)))
            for p in self.import_payments
        )
        valor_pendente = valor_total - valor_pago

        resume = {
            "total_nf_display": valor_total,
            "total_allocated_display": valor_pago,
            "pending_display": valor_pendente,
        }

        for field_name, value in resume.items():
            money_obj = Money(value, 'BRL')
            self.initial[field_name] = money_obj

            if self.is_bound:
                 self.data._mutable = True
                 self.data[f"{field_name}_0"] = str(value)
                 self.data[f"{field_name}_1"] = 'BRL'
                 self.data._mutable = False

            self.fields[field_name].widget.attrs.update({
                "readonly": True,
                "class": "cursor-not-allowed opacity-75"
            })

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML('<h3 class="font-bold text-2xl pb-2 mb-2">Configuração das Formas de Pagamento</h3>'),
                HTML('<h5 class="text-lg pb-2 mb-4">Adicione, edite e salve múltiplos planos de pagamentos para esta importação.</h5>'),
                #
                Div(Field("total_nf_display", wrapper_class="col-span-12 lg:col-span-4"), Field("total_allocated_display", wrapper_class="col-span-12 lg:col-span-4"), Field("pending_display", wrapper_class="col-span-12 lg:col-span-4"), css_class="grid grid-cols-12 gap-4 mb-2 pb-4"),
                #
                Div(
                    Field("payment_method", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("installments_count", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("first_amount", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-4 mb-2 pb-4",
                ),
                #
                Div(
                    Field("payment_date", wrapper_class="col-span-12 lg:col-span-4"),
                    Div(css_class="col-span-12 lg:col-span-4"),
                    HTML(f"""<button type="button" hx-post="{reverse("stock:add_payment_session")}?pk={self.instance.pk}"
                                        hx-target="#import-step-container" 
                                        hx-include="#import-step-container"
                                        hx-indicator="#payment-loader"
                                        class="btn btn-primary col-span-12 lg:col-span-4"> Incluir Pagamento</button>"""),
                    css_class="grid grid-cols-12 gap-4 mb-2 pb-4",
                ),
                #
                HTML('<div class="mt-6 overflow-x-auto">'),
                HTML(self._generate_payments_table_html()),
                HTML("</div>"),
                id="import-step-container",
                css_class="card-body",
            )
        )

    def _generate_payments_table_html(self):
        rows = ""
        for p in self.import_payments:
            payment_date = p.get("payment_date", "")
            try:
                date_obj = datetime.strptime(payment_date, '%Y-%m-%d')
                payment_date = date_obj.strftime('%d/%m/%Y')
            except:
                continue
            delete_url = reverse("stock:remove_payment_session", kwargs={"payment_id": p["id"]})
            delete_url += f"?pk={self.instance.pk}"
            rows += f"""<tr>
                    <td>{p["method_display"]}</td>
                    <td>{p["installments"]}x</td>
                    <td>{payment_date}x</td>
                    <td class="font-bold">{Money(p["total_paid"], 'BRL')}</td>
                    <td class="text-center">
                        <button type="button" 
                                hx-post="{delete_url}" 
                                hx-target="#import-step-container" 
                                hx-confirm="Deseja remover este pagamento?"
                                class="btn btn-ghost btn-xs text-error">
                            <span class="material-icons text-sm">delete</span>
                        </button>
                    </td>
                </tr>"""

        if not rows:
            rows = '<tr><td colspan="5" class="text-center text-gray-500 italic py-4">Nenhum pagamento registrado.</td></tr>'

        return f"""<table class="table table-zebra w-full">
                <thead>
                    <tr class="bg-base-300">
                        <th>Forma de Pagamento</th>
                        <th>Parcelas</th>
                        <th>Data de Vencimento</th>
                        <th>Valor Pago</th>
                        <th class="text-center">Ações</th>
                    </tr>
                </thead>
                <tbody class="bg-base-200">
                    {rows}
                </tbody>
            </table>"""


class ImportStepSummaryForm(forms.ModelForm):
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
            if ',' in raw_value:
                clean_value = raw_value.replace('.', '').replace(',', '.')
            else:
                clean_value = raw_value
            value = Money(Decimal(clean_value), 'BRL')
            
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
                    stock_qty = product.stock_products.current_quantity if hasattr(product, 'stock_products') else 0
                    rows_html += f"""<tr>
                        <td class="text-xs text-warning" title="Código do Produto Vinculado: {product.code}">{product.code}</td>
                        <td class="max-w-[150px] truncate text-warning" title="Descrição do Produto Vinculado: {product.name}">{product.name}</td>
                        <td class="text-right text-warning" title="Estoque Atual do Produto Vinculado: {stock_qty}">{stock_qty}</td>
                        <td class="text-right font-bold text-warning" title="Valor de Custo do Produto Vinculado: {product.cost_price}">{product.cost_price}</td>
                    </tr>
                    <tr class="h-5"><td colspan="4"></td></tr>"""


        payments_html = ""
        total_value = Money(0, "BRL")
        for pay in self.instance.payments_data:
            raw_value = str(pay.get("total_paid", "0.00"))
            if ',' in raw_value:
                clean_value = raw_value.replace('.', '').replace(',', '.')
            else:
                clean_value = raw_value
            value = Money(Decimal(clean_value), 'BRL')
            total_value += value
            payments_html += f"""<div class="flex justify-between items-center mb-2">
                            <span class="text-sm">{pay.get("method_display", "Boleto")} ({pay.get("installments", 1)}x)</span>
                            <span class="font-bold">{value}</span>
                        </div>"""

        supplier_name = self.instance.supplier_name or 'Não informado'
        supplier_cnpj = self.instance.supplier_cnpj or "Não informado"
        nf_number = self.instance.nf_number or "---"

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
                                        <th class="text-right">Valor Unitário</th>
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
                                <span>Total Geral</span>
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

        if instance.status == StockImport.ImportStatus.COMPLETED:
            return instance

        supplier = None
        if instance.supplier_cnpj:
            supplier, _ = Supplier.objects.get_or_create(cnpj=instance.supplier_cnpj, workshop=workshop, defaults={"name": instance.supplier_name})

        for item in instance.items_data:
            product_id = item.get("linked_product_id")
            product = Product.objects.get(id=product_id, workshop=workshop)
            stock_product, created = StockProduct.objects.get_or_create(workshop=workshop, product=product, defaults={"supplier": supplier, "last_nf": instance.nf_number})

            quantity = Decimal(str(item.get("qtd", 0)))
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
            stock_product.last_nf = instance.nf_number
            stock_product.save()

        for pay in instance.payments_data:
            payment_due_date = pay.get("payment_date")
            if isinstance(payment_due_date, str) and payment_due_date:
                try:
                    payment_due_date = datetime.strptime(payment_due_date, '%Y-%m-%d')
                except ValueError:
                    payment_due_date = timezone.now()
            else:
                payment_due_date = timezone.now()

            total_val = Decimal(str(pay.get("total_paid", 0)))
            installments = int(pay.get("installments", 1))
            first_amount = Decimal(str(pay.get("first_amount", total_val)))
            remaining_amount = Decimal('0.00')
            if installments > 1:
                remaining_amount = (total_val - first_amount) / (installments - 1)

            StockPaymentMethod.objects.create(
                workshop=workshop,
                payment_method=pay.get("method", "BOLETO"),
                installments_count=installments,
                first_installment_amount=Money(first_amount, 'BRL'),
                remaining_installments_amount=Money(remaining_amount, 'BRL'),
                nf_number=instance.nf_number,
                due_date=payment_due_date
            )

        instance.status = StockImport.ImportStatus.COMPLETED
        if commit:
            instance.save()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        for item in self.instance.items_data:
            if not item.get("linked_product_id"):
                self.add_error(None, "Existem itens pendentes de vínculo.")
        return cleaned_data


class ImportSefazListForm(forms.ModelForm):
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

        if self.workshop and self.workshop.can_search_sefaz:
            self.update_sefaz_list()

        imported_keys = StockImport.objects.filter(workshop=self.workshop).values_list("nf_key", flat=True)
        self.notas = SefazZipCache.objects.filter(workshop=self.workshop)

        for nota in self.notas:
            nota.is_imported = nota.key in imported_keys

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("selected_key", id="id_selected_key"),
            HTML("{% include 'stock/partials/sefaz_table.html' %}")
        )

    def update_sefaz_list(self):
        """Encapsula a lógica de busca na SEFAZ fornecida"""
        try:
            uf = self.workshop.uf
            certificado = self.workshop.pfx_certificate.path
            senha = self.workshop.certificate_password
            cnpj = re.sub(r"\D", "", self.workshop.cnpj)
            nsu = self.workshop.last_nsu_sefaz

            comunicacao = ComunicacaoSefaz(uf, certificado, senha)
            xml_resp = comunicacao.consulta_distribuicao(cnpj=cnpj, nsu=nsu)

            # Parsing do retorno da SEFAZ (simplificado do seu exemplo)
            tree = etree.fromstring(xml_resp.content)
            ns = {"ns": "http://www.portalfiscal.inf.br/nfe"}

            if tree.xpath("//ns:cStat/text()", namespaces=ns)[0] == "138":
                self.workshop.last_nsu_sefaz = tree.xpath("//ns:ultNSU/text()", namespaces=ns)[0]

                docs = tree.xpath("//ns:docZip", namespaces=ns)
                for doc in docs:
                    content = gzip.decompress(base64.b64decode(doc.text))
                    nfe_tree = etree.fromstring(content)
                    tag = etree.QName(nfe_tree).localname

                    dados = {}
                    if tag == 'resNFe':
                        dados = {
                            'key': nfe_tree.get('chNFe'),
                            'nome': nfe_tree.get('xNome'),
                            'cnpj': nfe_tree.get('CNPJ') or nfe_tree.get('CPF'),
                            'valor': nfe_tree.get('vNF'),
                            'data': nfe_tree.get('dhEmi')
                        }
                    elif tag == 'nfeProc':
                        dados = {
                            'key': nfe_tree.xpath('//ns:infNFe/@Id', namespaces=ns)[0].replace('NFe',''),
                            'nome': nfe_tree.xpath('//ns:emit/ns:xNome/text()', namespaces=ns)[0],
                            'cnpj': nfe_tree.xpath('//ns:emit/ns:CNPJ/text()', namespaces=ns)[0],
                            'valor': nfe_tree.xpath('//ns:vNF/text()', namespaces=ns)[0],
                            'data': nfe_tree.xpath('//ns:dhEmi/text()', namespaces=ns)[0]
                        }

                    if dados.get("key"):
                        SefazZipCache.objects.update_or_create(key=dados["key"], workshop=self.workshop, defaults={"issuer_name": dados["nome"], "issuer_cnpj": dados["cnpj"], "total_value": dados["valor"], "issue_date": dados["data"]})

            self.workshop.last_sefaz_search_date = timezone.now()
            self.workshop.save()
        except Exception as e:
            print(f"Erro SEFAZ: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        key = self.cleaned_data.get("selected_key")

        if key:
            try:
                comunicacao = ComunicacaoSefaz(self.workshop.uf, self.workshop.pfx_certificate.path, self.workshop.certificate_password)
                xml_completo = comunicacao.consulta_distribuicao(cnpj=re.sub(r"\D", "", self.workshop.cnpj), chave=key)

                nf_data = NFParser.parse_nfe_xml_to_dict(xml_completo.content)

                if nf_data:
                    instance.nf_number = nf_data["nf_number"]
                    instance.nf_key = nf_data["nf_key"]
                    instance.supplier_cnpj = nf_data["supplier_cnpj"]
                    instance.supplier_name = nf_data["supplier_name"]
                    instance.items_data = nf_data["items"]
                    instance.payments_data = nf_data["payments"]
                    instance.method = "SEFAZ"
            except Exception as e:
                raise forms.ValidationError(f"Erro ao baixar nota completa: {e}")

        if commit:
            instance.save()
        return instance

    def clean(self):
        cleaned_data = super().clean()

        if not cleaned_data.get("selected_key"):
            self.add_error(None, "Selecione uma NF antes de avançar.")

        return cleaned_data


class QuickProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "unit", "group", "cost_price", "selling_price", "profit_margin", "origin_cst", "purpose"]
        widgets = {
            "code": TextInput(),
            "name": TextInput(),
            "unit": SelectInput(),
            "group": SelectInput(),
            "cost_price": MoneyInput(),
            "selling_price": MoneyInput(),
            "profit_margin": PercentageInput(attrs={"readonly": True}),
            "origin_cst": SelectInput(),
            "purpose": SelectInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if workshop:
            self.fields["group"].queryset = self.fields["group"].queryset.filter(workshop=workshop)

        self.helper = FormHelper()
        self.helper.form_tag = False  # Importante para o modal
        self.helper.layout = Layout(
            Div(
                # Usando x-data para o cálculo de margem idêntico ao original
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
                    Field("profit_margin", wrapper_class="col-span-12 lg:col-span-4", css_class="opacity-50"),
                    Field("origin_cst", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("purpose", wrapper_class="col-span-12 lg:col-span-6"),
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


class CatalogGroupQuickForm(forms.ModelForm):
    class Meta:
        model = CatalogGroup
        fields = ["name"]
        widgets = {"name": TextInput(attrs={"placeholder": "Grupo"})}

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Div(
            Field("name", wrapper_class="col-span-1"), css_class="grid grid-cols-1 gap-4 items-start"))

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name and self.workshop:
            # Validação extra para garantir unicidade case-insensitive no workshop
            qs = CatalogGroup.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um grupo com este nome.")
        return name
