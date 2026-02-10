import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django.forms.widgets import DateInput
from django.urls import reverse
from djmoney.forms import MoneyField
from djmoney.money import Money

from apps.catalog.models.products import Product
from apps.core.widgets import TextInput, SelectInput, NumberInput, MoneyInput, CalendarDateInput
from apps.stock.models import StockPaymentMethod


class ImportStep1Form(forms.Form):
    METHOD_CHOICES = [
        ('SEFAZ', 'SEFAZ'),
        ('XML', 'Arquivo XML'),
        ('KEY', 'Chave de Acesso'),
    ]
    method = forms.ChoiceField(choices=METHOD_CHOICES, label="Selecione o método de Importação de Itens", widget=forms.Select(attrs={'x-model': 'method'}))
    xml_file = forms.FileField(label="Selecione o arquivo XML", required=False)
    access_key = forms.CharField(label="Insira a chave de acesso", max_length=47, required=False, widget=TextInput(attrs={'oninput': "this.value = this.value.replace(/[^0-9]/g, '')"}))

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = (Layout(
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
        )

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")

        if method == 'XML' and not self.files.get('xml_file'):
            self.add_error("xml_file", "O arquivo XML é obrigatório para este método.")

        if method == "KEY":
            key = cleaned_data.get("access_key")
            if not key or len(re.sub(r"\D", "", key)) != 44:
                self.add_error("access_key", "Insira uma chave válida de 44 dígitos.")

        return cleaned_data


class ImportStepSupplierForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        # Dados extraídos para exibição amigável
        nome = self.nf_data.get("supplier_name", "Não informado")
        cnpj = self.nf_data.get("supplier_cnpj", "Não informado")
        nNF = self.nf_data.get("nf_number", "---")

        self.helper.layout = Layout(
            HTML(f"""
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-indigo-50 p-6 rounded-lg border border-indigo-100 mb-6">
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


class ImportStepItemsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        table_html = self._generate_table_html()

        self.helper.layout = Layout(
            Div(
                HTML(table_html),
                css_class="mt-4"
            )
        )

    def _generate_table_html(self):
        rows_xml = ""
        rows_system = ""
        quick_create_url = reverse("catalog:quick_create")
        link_manual_url = reverse("stock:link_product_manual")

        for idx, item in enumerate(self.import_items):
            # --- Dados do XML ---
            ref_xml = item.get("ref", "")
            desc_xml = item.get("desc", "")
            qtd = Decimal(str(item.get("qtd", 0)))
            valor_unit = Decimal(str(item.get("valor", 0)))

            rows_xml += f"""
                <tr class="h-16 border-b hover:bg-base-200/30">
                    <td>
                        <div class="text-sm font-medium truncate w-48" title="{desc_xml}">{desc_xml}</div>
                        <div class="text-[10px] opacity-50 font-mono">{ref_xml}</div>
                    </td>
                    <td class="text-center">{qtd}</td>
                    <td class="text-right font-semibold">R$ {valor_unit:,.2f}</td>
                </tr>
            """

            # --- Dados do Sistema ---
            product_id = item.get("linked_product_id")
            db_product = Product.objects.filter(id=product_id, workshop=self.workshop).first() if product_id else None

            if db_product:
                stock_qty = getattr(db_product.stock_products.first(), "current_quantity", 0)
                cost_price = getattr(db_product, "cost_price", 0)

                rows_system += f"""
                    <tr class="h-16 border-b hover:bg-base-200/30">
                        <td>
                            <div class="font-bold text-sm text-success italic">✓ {db_product.name}</div>
                            <div class="text-xs opacity-60">Custo: R$ {cost_price:,.2f}</div>
                        </td>
                        <td class="text-center">{stock_qty}</td>
                        <td class="text-center">
                            <button type="button" class="btn btn-ghost btn-xs text-error" 
                                    hx-post='{reverse("stock:unlink_item")}?item_idx={idx}' hx-target="#import-card-content">
                                <span class="material-icons text-xs">link_off</span>
                            </button>
                        </td>
                    </tr>
                """
            else:
                rows_system += f"""
                    <tr class="h-16 border-b bg-warning/5">
                        <td colspan="2" class="italic text-warning text-xs">
                            <span class="flex items-center gap-1"><span class="material-icons text-sm">warning</span> Pendente</span>
                        </td>
                        <td class="text-center">
                            <div class="flex gap-1 justify-center">
                                <button type="button" class="btn btn-primary btn-xs" hx-target="#modal-container"
                                        hx-get="{quick_create_url}?ref={ref_xml}&desc={desc_xml}&price={valor_unit}&item_idx={idx}">Novo</button>
                                <button type="button" class="btn btn-outline btn-xs" hx-target="#modal-container"
                                        hx-get="{link_manual_url}?item_idx={idx}">Link</button>
                            </div>
                        </td>
                    </tr>
                    """

        return f"""<div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <div class="col-span-12 lg:col-span-5">
                <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">Itens Importados</h3>
                <div class="rounded-xl overflow-hidden">
                    <table class="table table-sm w-full">
                        <thead>
                            <tr>
                                <th>Descrição</th>
                                <th class="text-center">Quantidade</th>
                                <th class="text-right">Valor Pago</th>
                            </tr>
                        </thead>
                        <tbody>{rows_xml}</tbody>
                    </table>
                </div>
            </div>
            
            <div class="lg:col-span-1">
            
            <div class="col-span-12 lg:col-span-6">
                <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">Itens Cadastrados</h3>
                <div class="rounded-xl overflow-hidden">
                    <table class="table table-sm w-full">
                        <thead>
                            <tr>
                                <th>Produto Vinculado</th>
                                <th class="text-center">Valor de Custo</th>
                                <th class="text-center">Valor de Venda</th>
                                <th class="text-center">Estoque Atual</th>
                                <th class="text-center">Ações</th>
                            </tr>
                        </thead>
                        <tbody>{rows_system}</tbody>
                    </table>
                </div>
            </div>
        </div>"""


class ImportStepPaymentForm(forms.Form):
    payment_method = forms.ChoiceField(choices=StockPaymentMethod.PAYMENT_METHOD_CHOICES, label="Forma de Pagamento", widget=SelectInput, required=False)
    installments_count = forms.IntegerField(min_value=1, initial=1, label="Número de Parcelas", widget=NumberInput, required=False)
    first_amount = MoneyField(max_digits=14, decimal_places=2, label="Valor Pago", widget=MoneyInput, required=False)
    payment_date = forms.DateField(label="Data de Vencimento", widget=CalendarDateInput, required=False)

    total_nf_display = forms.CharField(label="Valor Total", required=False, widget=MoneyInput)
    total_allocated_display = forms.CharField(label="Valor Pago", required=False, widget=MoneyInput)
    pending_display = forms.CharField(label="Valor Pendente", required=False, widget=MoneyInput)

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.nf_data = kwargs.pop("nf_data", {})
        self.import_items = kwargs.pop("import_items", [])
        self.import_payments = kwargs.pop("import_payments", [])
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        # Cálculos Financeiros
        valor_total = Decimal('0.00')
        for item in self.import_items:
            qtd = Decimal(str(item.get("qtd", 0)))
            valor_unit = Decimal(str(item.get("valor", 0)))
            valor_total += valor_unit * qtd

        valor_pago = Decimal("0.00")
        for p in self.import_payments:
            valor_pago += Decimal(str(p.get("total_paid", 0)))

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
                    HTML(f"""<button type="button" hx-post="{reverse("stock:add_payment_session")}" 
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
                    <tr>
                        <th>Forma de Pagamento</th>
                        <th>Parcelas</th>
                        <th>Data de Vencimento</th>
                        <th>Valor Pago</th>
                        <th class="text-center">Ações</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>"""
