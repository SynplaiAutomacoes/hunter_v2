from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit, Button
from django.urls import reverse

from .models import Customer, Vehicle
from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, SelectInput, RGInput, PhoneInput, EmailInput, CheckboxInput, CEPInput, \
    NumberInput
from .cpf_cnpj_validator import is_valid_cpf, is_valid_cnpj
from ..core.forms import AddressFormMixin, address_layout
from ..workshops.models.workshops import Workshop


VehicleFormSet = inlineformset_factory(
    parent_model=Customer,
    model=Vehicle,
    fields = [
        "plate",
        "brand",
        "model",
        "year_fabrication",
        "year_model",
        "color",
        "fuel",
        "engine",
        "type",
        "renavam",
        "chassi",
        "km",
    ],
    extra=0,
    can_delete=True,
    widgets = {
        "plate": TextInput(),
        "brand": TextInput(),
        "model": TextInput(),
        "year_fabrication": TextInput(),
        "year_model": TextInput(),
        "color": TextInput(),
        "fuel": TextInput(),
        "engine": TextInput(),
        "type": TextInput(),
        "renavam": TextInput(),
        "chassi": TextInput(),
        "km": NumberInput(),
    },
)


class CustomerForm(AddressFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "customer_type",
            "cpf_or_cnpj",
            "name",
            "rg",
            "birth_date",
            "sex",
            "phone",
            "email",
            "is_active",
            "fantasy_name",
            "state_registration",
            "municipal_registration",
            "foundation_date",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "estado",
        ]
        widgets = {
            "cpf_or_cnpj": CPForCNPJInput(mode="both"),
            "name": TextInput(),
            "fantasy_name": TextInput(),
            "municipal_registration": TextInput(),
            "state_registration": TextInput(),
            "foundation_date": CalendarDateInput(),
            "rg": RGInput(),
            "birth_date": CalendarDateInput(),
            "sex": SelectInput(),
            "phone": PhoneInput(),
            "email": EmailInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.setup_address_fields()
        self.helper = FormHelper()
        self.helper.form_method = "post"

        cancel_url = reverse("customer:customer_list")
        add_vehicle_url = reverse("customer:add-vehicle-form")

        self.helper.layout = Layout(
            Div(
                HTML("""
                    <div
                        x-data="{ tipo: $el.dataset.tipo || 'PF' }"
                        data-tipo="{{ form.initial.customer_type|default_if_none:'PF' }}"
                        class="col-span-12 grid grid-cols-1 lg:grid-cols-12 gap-4"
                    >
                """),

                HTML("""
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
                """),

                HTML('<h3 class="text-xl font-bold col-span-12">Dados Gerais</h3>'),

                # ─────────────────────────────
                # Linha 1 — Identificação
                # CPF/CNPJ | Nome | Nome Fantasia (PJ)
                # ─────────────────────────────
                Field("cpf_or_cnpj", wrapper_class="col-span-12 lg:col-span-4"),
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),

                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("fantasy_name", wrapper_class="col-span-12"),
                HTML('</div>'),

                # ─────────────────────────────
                # Linha 2 — Registros PJ
                # Inscrição Municipal | Inscrição Estadual | Data de Fundação
                # ─────────────────────────────
                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("municipal_registration", wrapper_class="col-span-12"),
                HTML('</div>'),

                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("state_registration", wrapper_class="col-span-12"),
                HTML('</div>'),

                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("foundation_date", wrapper_class="col-span-12"),
                HTML('</div>'),

                # ─────────────────────────────
                # Linha 3 — Contato / Status
                # Telefone | RG (PF) | Email
                # ─────────────────────────────
                Field("phone", wrapper_class="col-span-12 lg:col-span-4"),

                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-4">'),
                Field("rg", wrapper_class="col-span-12"),
                HTML('</div>'),

                Field("email", wrapper_class="col-span-12 lg:col-span-4"),

                # ─────────────────────────────
                # Linha 4 — Status / Dados PF
                # Ativo | Data de Nascimento | Sexo
                # ─────────────────────────────
                Field("is_active", wrapper_class="col-span-12 lg:col-span-4"),

                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-4">'),
                Field("birth_date", wrapper_class="col-span-12"),
                HTML('</div>'),

                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-4">'),
                Field("sex", wrapper_class="col-span-12"),
                HTML('</div>'),

                HTML("</div>"),  # FECHA O X-DATA
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                # Seção: Endereço
                address_layout(),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                # Seção: Veículo
                Div(
                    Div(
                        HTML('<h3 class="text-xl font-bold">Veículos</h3>'),
                        Button(
                            name="add_vehicle",
                            value="+ Adicionar Veículo",
                            css_class="btn btn-primary",
                            hx_get=add_vehicle_url,
                            hx_target="#vehicle-list",
                            hx_swap="beforeend",
                            hx_vals='js:{index: document.querySelectorAll(".vehicle-item").length}',
                        ),
                        css_class="flex items-center justify-between mb-4 border-b pb-2",
                    ),
                    css_class="col-span-12",
                ),
                Div(HTML('<div id="vehicle-list" class="space-y-4">{% include "customer/partials/vehicle_formset_list.html" %}</div>'), css_class="col-span-12"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
            ),
            #
            HTML('<div class="divider"></div>'),
            #
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean(self):
        """
           Validação contextual do formulário de Customer, considerando Pessoa Física (PF)
           e Pessoa Jurídica (PJ) em um único formulário.

           Regras de negócio aplicadas:
           - Pessoa Física (customer_type="PF"):
               • Campos obrigatórios: nome (name) e CPF (cpf_or_cnpj)
               • O CPF deve ser válido conforme as regras oficiais
           - Pessoa Jurídica (customer_type="PJ"):
               • Campos obrigatórios: razão social (name) e CNPJ (cpf_or_cnpj)
               • O CNPJ deve ser válido conforme as regras oficiais

           Regras adicionais:
           - A validação do documento (CPF/CNPJ) é feita de forma explícita e contextual,
             com base no campo customer_type, sem inferência por tamanho ou outros campos.
           - O campo cpf_or_cnpj deve ser único por workshop.
           - Em operações de edição, o próprio registro é ignorado na verificação
             de unicidade.
           - Campos não obrigatórios permanecem opcionais, mesmo que visíveis no formulário.
           - Esta implementação complementa as validações existentes, preservando o
             comportamento definido em super().clean().

           Retorno:
           - Retorna cleaned_data com os erros adicionados aos campos correspondentes,
             quando aplicável.
           """

        cleaned_data = super().clean()

        tipo = cleaned_data.get("customer_type")
        documento = cleaned_data.get("cpf_or_cnpj")
        nome = cleaned_data.get("name")
        razao_social = cleaned_data.get("name")

        if not self.workshop:
            return cleaned_data

        # Documento obrigatório e válido conforme o tipo
        if tipo == "PF":
            if not documento:
                self.add_error("cpf_or_cnpj", "CPF é obrigatório para pessoa física.")
            elif not is_valid_cpf(documento):
                self.add_error("cpf_or_cnpj", "Informe um CPF válido.")

            if not nome:
                self.add_error("name", "Nome é obrigatório para pessoa física.")

        elif tipo == "PJ":
            if not documento:
                self.add_error("cpf_or_cnpj", "CNPJ é obrigatório para pessoa jurídica.")
            elif not is_valid_cnpj(documento):
                self.add_error("cpf_or_cnpj", "Informe um CNPJ válido.")

            if not razao_social:
                self.add_error("name", "Razão social é obrigatória para pessoa jurídica.")

        # Unicidade do documento por oficina
        if documento:
            queryset = Customer.objects.filter(
                workshop=self.workshop,
                cpf_or_cnpj=documento
            )

            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                self.add_error(
                    "cpf_or_cnpj",
                    "Já existe um cliente cadastrado com este documento nesta oficina."
                )

        return cleaned_data


class QuickCustomerForm(AddressFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["cpf_or_cnpj","name","birth_date","cep","logradouro","numero","complemento","bairro","cidade","estado"]
        widgets = {
            "cpf_or_cnpj": CPForCNPJInput(mode="both"),
            "name": TextInput(),
            "birth_date": CalendarDateInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        self.setup_address_fields()
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("cpf_or_cnpj", wrapper_class="col-span-12"),
                Field("name", wrapper_class="col-span-12 lg:col-span-6"),
                Field("birth_date", wrapper_class="col-span-12 lg:col-span-6"),
                HTML('<div class="col-span-12 divider my-1"></div>'),
                address_layout(),
                css_class="grid grid-cols-12 gap-2",
            )
        )


class QuickVehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "plate", "brand", "model", "year_fabrication", "year_model",
            "color", "fuel", "engine", "type", "renavam", "chassi", "km"
        ]
        widgets = {
            "plate": TextInput(),
            "brand": TextInput(),
            "model": TextInput(),
            "year_fabrication": TextInput(),
            "year_model": TextInput(),
            "color": TextInput(),
            "fuel": TextInput(),
            "engine": TextInput(),
            "type": TextInput(),
            "renavam": TextInput(),
            "chassi": TextInput(),
            "km": NumberInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.customer = kwargs.pop("customer", None)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("plate", wrapper_class="col-span-12 lg:col-span-4"),
                Field("brand", wrapper_class="col-span-12 lg:col-span-4"),
                Field("model", wrapper_class="col-span-12 lg:col-span-4"),
                Field("year_fabrication", wrapper_class="col-span-12 lg:col-span-3"),
                Field("year_model", wrapper_class="col-span-12 lg:col-span-3"),
                Field("color", wrapper_class="col-span-12 lg:col-span-3"),
                Field("fuel", wrapper_class="col-span-12 lg:col-span-3"),
                Field("engine", wrapper_class="col-span-12 lg:col-span-4"),
                Field("type", wrapper_class="col-span-12 lg:col-span-4"),
                Field("km", wrapper_class="col-span-12 lg:col-span-4"),
                Field("renavam", wrapper_class="col-span-12 lg:col-span-6"),
                Field("chassi", wrapper_class="col-span-12 lg:col-span-6"),
                css_class="grid grid-cols-12 gap-2",
            )
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.workshop:
            instance.workshop = self.workshop
        if self.customer:
            instance.customer = self.customer
        if commit:
            instance.save()
        return instance