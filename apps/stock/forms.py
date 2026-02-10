import re
from decimal import Decimal, InvalidOperation

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django.urls import reverse
from djmoney.forms import MoneyField
from djmoney.money import Money

from apps.catalog.models.products import Product
from apps.core.widgets import TextInput, SelectInput, NumberInput, MoneyInput
from apps.stock.models import StockPaymentMethod


class ImportStep1Form(forms.Form):
    METHOD_CHOICES = [
        ('SEFAZ', 'SEFAZ'),
        ('XML', 'Arquivo XML'),
        ('KEY', 'Chave de Acesso'),
        ('OS', 'Abrir Ordem de Serviço'),
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
                HTML('<h2 class="text-2xl font-bold mb-4">Itens Importados</h2>'),
                HTML(table_html),
                css_class="mt-4"
            )
        )

    def _generate_table_html(self):
        rows = ""
        total_geral = Decimal("0.00")
        has_missing = False

        quick_create_url = reverse("catalog:quick_create")

        for item in self.import_items:
            ref = item.get("ref", "")
            desc = item.get("desc", "")

            # Tenta encontrar o produto no catálogo
            db_product = Product.objects.filter(workshop=self.workshop, code=ref).first()

            # Cálculos de valores (convertendo strings para Decimal)
            try:
                qtd = Decimal(str(item.get("qtd", 0)))
                valor_unit = Decimal(str(item.get("valor", 0)))
            except:
                qtd = Decimal("0")
                valor_unit = Decimal("0")

            subtotal = qtd * valor_unit
            total_geral += subtotal
            desc_display = f'<div class="font-bold text-error">{desc}</div><div class="text-xs opacity-50">Código: {ref}</div>'

            if db_product:
                status_badge = '<div class="badge badge-success gap-2 py-3"> <span class="material-icons text-xs">check_circle</span> Vinculado </div>'
                action_btn = '<div class="text-sm text-success font-bold text-center italic"></div>'
            else:
                has_missing = True
                status_badge = '<div class="badge badge-warning gap-2 py-3"> <span class="material-icons text-xs">help</span> Novo </div>'
                url_with_params = f"{quick_create_url}?ref={ref}&desc={desc}&price={valor_unit}"
                action_btn = f"""<button type="button" class="btn btn-sm btn-primary w-full" 
                                            hx-get="{url_with_params}" 
                                            hx-target="#modal-container">
                                        <span class="material-icons text-xs">add</span> Cadastrar
                                    </button>"""

            rows += f"""
                    <tr class="hover">
                        <td class="w-10">{status_badge}</td>
                        <td>{desc_display}</td>
                        <td class="text-center font-mono">{qtd}</td>
                        <td class="text-right">R$ {valor_unit:,.2f}</td>
                        <td class="text-right font-bold">R$ {subtotal:,.2f}</td>
                        <td class="w-32">{action_btn}</td>
                    </tr>
                    """

        warning_alert = ""
        if has_missing:
            warning_alert = """
                    <div class="alert alert-warning shadow-sm mb-4">
                        <span class="material-icons">info</span>
                        <div>
                            <h3 class="font-bold">Itens pendentes!</h3>
                            <div class="text-xs">Cadastre os produtos marcados como "Novo" para liberar a importação.</div>
                        </div>
                    </div>
                    """

        table_base = f"""
                <div class="overflow-x-auto border rounded-xl bg-base-100 shadow-sm">
                    <table class="table table-md w-full">
                        <thead>
                            <tr class="bg-base-200 text-base-content">
                                <th>Status</th>
                                <th>Produto / Referência</th>
                                <th class="text-center">Qtd.</th>
                                <th class="text-right">Valor Unitário</th>
                                <th class="text-right">Subtotal</th>
                                <th class="text-center">Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows if rows else '<tr><td colspan="6" class="text-center py-4">Nenhum item encontrado</td></tr>'}
                        </tbody>
                        <tfoot class="bg-base-200">
                            <tr class="text-right font-bold text-lg uppercase">
                                <td colspan="4">Total da Nota:</td>
                                <td>R$ {total_geral:,.2f}</td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
                """
        return warning_alert + table_base


class ImportStepPaymentForm(forms.Form):
    payment_method = forms.ChoiceField(choices=StockPaymentMethod.PAYMENT_METHOD_CHOICES, label="Forma de Pagamento", widget=SelectInput)
    installments_count = forms.IntegerField(min_value=1, initial=1, label="Número de Parcelas", widget=NumberInput)
    first_amount = MoneyField(max_digits=14, decimal_places=2, label="Valor Pago", widget=MoneyInput)

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
                Div(
                    Field("total_nf_display", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("total_allocated_display", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("pending_display", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-4 mb-2 pb-4"
                ),
                #
                Div(
                    Field("payment_method", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("installments_count", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("first_amount", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-4 mb-2 pb-4",
                ),
                #
                Div(
                    Div(css_class="col-span-12 lg:col-span-8"),
                    HTML(f"""<button type="button" hx-post="{reverse("stock:add_payment_session")}" 
                                        hx-target="#import-step-container" 
                                        hx-include="#import-step-container"
                                        hx-indicator="#payment-loader"
                                        class="btn btn-primary col-span-12 lg:col-span-4"> Incluir Pagamento</button>"""),
                    css_class="grid grid-cols-12 gap-4 mb-2 pb-4"
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
            delete_url = reverse("stock:remove_payment_session", kwargs={"payment_id": p["id"]})
            rows += f"""<tr>
                    <td>{p["method_display"]}</td>
                    <td>{p["installments"]}x</td>
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
            rows = '<tr><td colspan="4" class="text-center text-gray-500 italic py-4">Nenhum pagamento registrado.</td></tr>'

        return f"""<table class="table table-zebra w-full">
                <thead>
                    <tr>
                        <th>Forma de Pagamento</th>
                        <th>Parcelas</th>
                        <th>Valor Pago</th>
                        <th class="text-center">Ações</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>"""
