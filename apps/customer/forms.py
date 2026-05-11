from collections.abc import Callable

from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit, Button
from django.urls import reverse

from .models import Customer, Vehicle
from .fipe_service import get_brand_form_choices, get_fuel_form_choices, get_model_form_choices
from apps.core.text_normalization import name_case, plate_case, sentence_case
from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, SearchableSelectInput, RGInput, PhoneInput, EmailInput, CheckboxInput, NumberInput, PlateInput
from .cpf_cnpj_validator import is_valid_cpf, is_valid_cnpj
from .vehicle_engine import normalize_vehicle_engine_choice, vehicle_engine_form_choices
from .vehicle_fuel import normalize_vehicle_fuel_choice, vehicle_fuel_form_choices
from ..core.forms import AddressFormMixin, address_layout
from ..workshops.models.workshops import Workshop
from apps.core.forms import CoreModelForm


def _set_normalized_initial_choice(form: forms.BaseForm, field_name: str, current_value: object, normalizer: Callable[[object], str]) -> None:
    normalized_value = normalizer(current_value)
    form.initial[field_name] = normalized_value
    if field_name in form.fields:
        form.fields[field_name].initial = normalized_value


def _get_current_field_value(form: forms.BaseForm, field_name: str) -> str:
    instance = getattr(form, "instance", None)
    raw_value = form.data.get(form.add_prefix(field_name)) if form.is_bound else form.initial.get(field_name) or getattr(instance, field_name, "")
    return str(raw_value or "").strip()


def _configure_vehicle_catalog_fields(form: forms.BaseForm) -> None:
    brand_value = _get_current_field_value(form, "brand")
    model_value = _get_current_field_value(form, "model")
    fuel_value = _get_current_field_value(form, "fuel")

    form.fields["brand"].widget = SearchableSelectInput(choices=get_brand_form_choices(current_value=brand_value))
    form.fields["model"].widget = SearchableSelectInput(choices=get_model_form_choices(brand_name=brand_value, current_value=model_value))
    form.fields["fuel"].widget = SearchableSelectInput(choices=get_fuel_form_choices(brand_name=brand_value, model_name=model_value, current_value=fuel_value))


def _canonicalize_catalog_name(value: object) -> str:
    return sentence_case(str(value or "").strip()) if str(value or "").strip() else ""


class VehicleInlineForm(CoreModelForm):
    engine = forms.CharField(label="Motor", required=False, widget=SearchableSelectInput(choices=vehicle_engine_form_choices()))
    fuel = forms.CharField(label="Combustível", required=False, widget=SearchableSelectInput(choices=vehicle_fuel_form_choices()))

    class Meta:
        model = Vehicle
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        _configure_vehicle_catalog_fields(self)
        self.fields["engine"].widget = SearchableSelectInput(choices=vehicle_engine_form_choices())
        if not self.is_bound:
            self.initial["brand"] = _get_current_field_value(self, "brand")
            self.initial["model"] = _get_current_field_value(self, "model")
            _set_normalized_initial_choice(self, "engine", self.initial.get("engine") or getattr(self.instance, "engine", None), normalize_vehicle_engine_choice)
            _set_normalized_initial_choice(self, "fuel", self.initial.get("fuel") or getattr(self.instance, "fuel", None), normalize_vehicle_fuel_choice)

    def clean_plate(self):
        plate = plate_case(self.cleaned_data.get("plate") or "")
        workshop = self.workshop or getattr(self.instance, "workshop", None)

        if not plate or not workshop:
            return plate

        queryset = Vehicle.objects.filter(workshop=workshop, plate=plate)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError("Já existe um veículo com esta placa nesta oficina.")

        return plate

    def clean_fuel(self):
        fuel = self.cleaned_data.get("fuel")
        normalized_fuel = normalize_vehicle_fuel_choice(fuel)
        if fuel and not normalized_fuel:
            raise forms.ValidationError("Selecione um combustível válido.")
        return normalized_fuel

    def clean_engine(self):
        engine = self.cleaned_data.get("engine")
        normalized_engine = normalize_vehicle_engine_choice(engine)
        if engine and not normalized_engine:
            raise forms.ValidationError("Selecione um motor válido.")
        return normalized_engine

    def clean_brand(self):
        return _canonicalize_catalog_name(self.cleaned_data.get("brand"))

    def clean_model(self):
        return _canonicalize_catalog_name(self.cleaned_data.get("model"))


class VehicleInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        seen_plates = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue

            plate = (form.cleaned_data.get("plate") or "").strip().upper()
            if not plate:
                continue

            if plate in seen_plates:
                form.add_error("plate", "Não é permitido repetir a mesma placa na lista de veículos.")
                continue

            seen_plates.add(plate)


VehicleFormSet = inlineformset_factory(
    parent_model=Customer,
    model=Vehicle,
    form=VehicleInlineForm,
    formset=VehicleInlineFormSet,
    fields=[
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
    widgets={
        "plate": PlateInput(),
        "brand": SearchableSelectInput(),
        "model": SearchableSelectInput(),
        "year_fabrication": TextInput(),
        "year_model": TextInput(),
        "color": TextInput(),
        "fuel": SearchableSelectInput(choices=vehicle_fuel_form_choices()),
        "engine": SearchableSelectInput(choices=vehicle_engine_form_choices()),
        "type": TextInput(),
        "renavam": TextInput(),
        "chassi": TextInput(),
        "km": NumberInput(),
    },
)


class CustomerForm(AddressFormMixin, CoreModelForm):
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
            "sex": SearchableSelectInput(),
            "phone": PhoneInput(),
            "email": EmailInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.setup_address_fields()

        initial_customer_type = str(self.data.get("customer_type") or self.initial.get("customer_type") or getattr(self.instance, "customer_type", "PF") or "PF").upper()
        if initial_customer_type not in {"PF", "PJ"}:
            initial_customer_type = "PF"

        self.fields["customer_type"].required = False
        self.fields["customer_type"].initial = initial_customer_type
        self.initial["customer_type"] = initial_customer_type
        self.fields["cpf_or_cnpj"].widget.mode = "cnpj" if initial_customer_type == "PJ" else "cpf"

        self.helper = FormHelper()
        self.helper.form_method = "post"

        cancel_url = reverse("customer:customer_list")
        add_vehicle_url = reverse("customer:add-vehicle-form")

        self.helper.layout = Layout(
            Div(
                HTML(
                    """
                    <div
                        x-data="{ tipo: '$initial_customer_type' }"
                        class="col-span-12 grid grid-cols-1 lg:grid-cols-12 gap-4"
                    >
                """.replace("$initial_customer_type", initial_customer_type)
                ),
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
                Div(
                    Field("cpf_or_cnpj", wrapper_class="col-span-12"),
                    x_init="""
                                const syncDocumentField = value => {
                                    const hiddenInput = $el.querySelector('input[type="hidden"][name="cpf_or_cnpj"]');
                                    const widgetRoot = hiddenInput ? hiddenInput.closest('[x-data]') : null;
                                    if (!widgetRoot || !window.Alpine) return;

                                    const widget = Alpine.$data(widgetRoot);
                                    widget.docMode = value === 'PJ' ? 'cnpj' : 'cpf';

                                    let digits = (hiddenInput.value || '').replace(/\D/g, '');
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
                    css_class="col-span-12 lg:col-span-4",
                ),
                Div(
                    Field("name", wrapper_class="col-span-12"),
                    x_init="""
                                $watch('tipo', value => {
                                    let label = $el.querySelector('label');
                                    if (label) {
                                        let hasAsterisk = label.querySelector('.asteriskField');
                                        label.firstChild.textContent = value === 'PJ' ? 'Razão Social ' : 'Nome ';
                                    }
                                });
                                let label = $el.querySelector('label');
                                if (label) {
                                    label.firstChild.textContent = tipo === 'PJ' ? 'Razão Social ' : 'Nome ';
                                }
                            """,
                    css_class="col-span-12 lg:col-span-4",
                ),
                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("fantasy_name", wrapper_class="col-span-12"),
                HTML("</div>"),
                # ─────────────────────────────
                # Linha 2 — Registros PJ
                # Inscrição Municipal | Inscrição Estadual | Data de Fundação
                # ─────────────────────────────
                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("municipal_registration", wrapper_class="col-span-12"),
                HTML("</div>"),
                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("state_registration", wrapper_class="col-span-12"),
                HTML("</div>"),
                HTML('<div x-show="tipo === \'PJ\'" class="col-span-12 lg:col-span-4">'),
                Field("foundation_date", wrapper_class="col-span-12"),
                HTML("</div>"),
                # ─────────────────────────────
                # Linha 3 — Contato / Status
                # Telefone | RG (PF) | Email
                # ─────────────────────────────
                Field("phone", wrapper_class="col-span-12 lg:col-span-4"),
                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-4">'),
                Field("rg", wrapper_class="col-span-12"),
                HTML("</div>"),
                Field("email", wrapper_class="col-span-12 lg:col-span-4"),
                # ─────────────────────────────
                # Linha 4 — Status / Dados PF
                # Ativo | Data de Nascimento | Sexo
                # ─────────────────────────────
                Field("is_active", wrapper_class="col-span-12 lg:col-span-4"),
                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-4">'),
                Field("birth_date", wrapper_class="col-span-12"),
                HTML("</div>"),
                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-4">'),
                Field("sex", wrapper_class="col-span-12"),
                HTML("</div>"),
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
                Div(HTML('<div id="vehicle-formset-container" class="space-y-4">{% include "customer/partials/vehicle_formset_list.html" %}</div>'), css_class="col-span-12"),
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

        cleaned_data = super().clean() or {}

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
            queryset = Customer.objects.filter(workshop=self.workshop, cpf_or_cnpj=documento)

            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                self.add_error("cpf_or_cnpj", "Já existe um cliente cadastrado com este documento nesta oficina.")

        return cleaned_data

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return name_case(value) if value else value

    def clean_fantasy_name(self):
        value = self.cleaned_data.get("fantasy_name")
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


class QuickCustomerForm(AddressFormMixin, CoreModelForm):
    class Meta:
        model = Customer
        fields = [
            "customer_type",
            "cpf_or_cnpj",
            "name",
            "phone",
            "email",
            "cep",
            "logradouro",
            "numero",
            "bairro",
            "cidade",
            "estado",
        ]
        widgets = {
            "cpf_or_cnpj": CPForCNPJInput(mode="both"),
            "name": TextInput(),
            "phone": PhoneInput(),
            "email": EmailInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        self.setup_address_fields()

        initial_customer_type = str(self.data.get("customer_type") or self.initial.get("customer_type") or getattr(self.instance, "customer_type", "PF") or "PF").upper()
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
                Div(
                    Field("cpf_or_cnpj", wrapper_class="col-span-12"),
                    x_init="""
                                const syncDocumentField = value => {
                                    const hiddenInput = $el.querySelector('input[type="hidden"][name="cpf_or_cnpj"]');
                                    const widgetRoot = hiddenInput ? hiddenInput.closest('[x-data]') : null;
                                    if (!widgetRoot || !window.Alpine) return;

                                    const widget = Alpine.$data(widgetRoot);
                                    widget.docMode = value === 'PJ' ? 'cnpj' : 'cpf';

                                    let digits = (hiddenInput.value || '').replace(/\D/g, '');
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
                HTML('<div class="col-span-12 divider my-1"></div>'),
                address_layout(include_complemento=False),
                HTML("</div>"),
                css_class="grid grid-cols-12 gap-2",
            )
        )

    def clean(self):
        cleaned_data = super().clean() or {}

        customer_type = str(cleaned_data.get("customer_type") or "PF").upper()
        cleaned_data["customer_type"] = customer_type
        document = cleaned_data.get("cpf_or_cnpj")
        name = cleaned_data.get("name")

        if customer_type == "PF":
            if not document:
                self.add_error("cpf_or_cnpj", "CPF é obrigatório para pessoa física.")
            elif not is_valid_cpf(document):
                self.add_error("cpf_or_cnpj", "Informe um CPF válido.")

            if not name:
                self.add_error("name", "Nome é obrigatório para pessoa física.")

        elif customer_type == "PJ":
            if not document:
                self.add_error("cpf_or_cnpj", "CNPJ é obrigatório para pessoa jurídica.")
            elif not is_valid_cnpj(document):
                self.add_error("cpf_or_cnpj", "Informe um CNPJ válido.")

            if not name:
                self.add_error("name", "Razão social é obrigatória para pessoa jurídica.")

        else:
            self.add_error("customer_type", "Selecione o tipo de cliente (PF ou PJ).")

        if document and self.workshop:
            queryset = Customer.objects.filter(workshop=self.workshop, cpf_or_cnpj=document)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                self.add_error("cpf_or_cnpj", "Já existe um cliente cadastrado com este documento nesta oficina.")

        return cleaned_data

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return name_case(value) if value else value

    def clean_logradouro(self):
        value = self.cleaned_data.get("logradouro")
        return sentence_case(value) if value else value

    def clean_bairro(self):
        value = self.cleaned_data.get("bairro")
        return sentence_case(value) if value else value

    def clean_cidade(self):
        value = self.cleaned_data.get("cidade")
        return sentence_case(value) if value else value


class QuickVehicleForm(CoreModelForm):
    engine = forms.CharField(label="Motor", required=False, widget=SearchableSelectInput(choices=vehicle_engine_form_choices()))
    fuel = forms.CharField(label="Combustível", required=False, widget=SearchableSelectInput(choices=vehicle_fuel_form_choices()))

    class Meta:
        model = Vehicle
        fields = ["plate", "brand", "model", "engine", "fuel", "year_fabrication", "year_model", "color"]
        widgets = {
            "plate": PlateInput(),
            "brand": SearchableSelectInput(),
            "model": SearchableSelectInput(),
            "engine": SearchableSelectInput(choices=vehicle_engine_form_choices()),
            "fuel": SearchableSelectInput(choices=vehicle_fuel_form_choices()),
            "year_fabrication": TextInput(),
            "year_model": TextInput(),
            "color": TextInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.customer = kwargs.pop("customer", None)
        super().__init__(*args, **kwargs)
        _configure_vehicle_catalog_fields(self)
        self.fields["engine"].widget = SearchableSelectInput(choices=vehicle_engine_form_choices())
        if not self.is_bound:
            self.initial["brand"] = _get_current_field_value(self, "brand")
            self.initial["model"] = _get_current_field_value(self, "model")
            _set_normalized_initial_choice(self, "engine", self.initial.get("engine") or getattr(self.instance, "engine", None), normalize_vehicle_engine_choice)
            _set_normalized_initial_choice(self, "fuel", self.initial.get("fuel") or getattr(self.instance, "fuel", None), normalize_vehicle_fuel_choice)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML('{% include "customer/partials/vehicle_fipe_script.html" %}'),
            Div(
                Field("plate", wrapper_class="col-span-12 lg:col-span-4"),
                Field("brand", wrapper_class="col-span-12 lg:col-span-4"),
                Field("model", wrapper_class="col-span-12 lg:col-span-4"),
                Field("engine", wrapper_class="col-span-12 lg:col-span-3"),
                Field("fuel", wrapper_class="col-span-12 lg:col-span-3"),
                Field("year_fabrication", wrapper_class="col-span-12 lg:col-span-2"),
                Field("year_model", wrapper_class="col-span-12 lg:col-span-2"),
                Field("color", wrapper_class="col-span-12 lg:col-span-2"),
                css_class="grid grid-cols-12 gap-2",
            ),
        )

    def clean_plate(self):
        plate = (self.cleaned_data.get("plate") or "").strip().upper()
        workshop = self.workshop or getattr(self.instance, "workshop", None)

        if not plate or not workshop:
            return plate

        queryset = Vehicle.objects.filter(workshop=workshop, plate=plate)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError("Já existe um veículo com esta placa nesta oficina.")

        return plate

    def clean_fuel(self):
        fuel = self.cleaned_data.get("fuel")
        normalized_fuel = normalize_vehicle_fuel_choice(fuel)
        if fuel and not normalized_fuel:
            raise forms.ValidationError("Selecione um combustível válido.")
        return normalized_fuel

    def clean_engine(self):
        engine = self.cleaned_data.get("engine")
        normalized_engine = normalize_vehicle_engine_choice(engine)
        if engine and not normalized_engine:
            raise forms.ValidationError("Selecione um motor válido.")
        return normalized_engine

    def clean_brand(self):
        return _canonicalize_catalog_name(self.cleaned_data.get("brand"))

    def clean_model(self):
        return _canonicalize_catalog_name(self.cleaned_data.get("model"))

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.workshop:
            instance.workshop = self.workshop
        if self.customer:
            instance.customer = self.customer
        if commit:
            instance.save()
        return instance
