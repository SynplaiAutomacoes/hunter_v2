from collections.abc import Callable

from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit, Button
from django.urls import reverse

from apps.catalog.models import FipeModelFuelCache, FipeVehicleBrand, FipeVehicleModel, FipeVehicleType
from .models import Customer, Vehicle
from apps.core.text_normalization import name_case, plate_case, sentence_case
from apps.core.presentation.widgets import CPForCNPJInput, CalendarDateInput, TextInput, SearchableSelectInput, RGInput, PhoneInput, EmailInput, CheckboxInput, NumberInput, PlateInput
from .cpf_cnpj_validator import is_valid_cpf, is_valid_cnpj
from .vehicle_engine import normalize_vehicle_engine_choice, vehicle_engine_form_choices
from .vehicle_fuel import normalize_vehicle_fuel_choice
from ..workshops.models.workshops import Workshop
from apps.core.presentation.forms import CoreModelForm, AddressFormMixin, address_layout


def _set_normalized_initial_choice(form: forms.BaseForm, field_name: str, current_value: object, normalizer: Callable[[object], str]) -> None:
    normalized_value = normalizer(current_value)
    form.initial[field_name] = normalized_value
    if field_name in form.fields:
        form.fields[field_name].initial = normalized_value


def _with_selected_choice(choices: list[tuple[str, str]], selected_value: object) -> list[tuple[str, str]]:
    normalized_selected_value = str(selected_value or "").strip()
    if not normalized_selected_value:
        return choices

    if any(str(value) == normalized_selected_value for value, _ in choices):
        return choices

    return [*choices, (normalized_selected_value, normalized_selected_value)]


def _vehicle_brand_form_choices() -> list[tuple[str, str]]:
    return [("", "Selecione"), *[(brand.name, brand.name) for brand in FipeVehicleBrand.objects.filter(vehicle_type=FipeVehicleType.CARROS, is_active=True).order_by("name")]]


def _vehicle_model_form_choices(brand_name: object, model_name: object = "") -> list[tuple[str, str]]:
    normalized_brand_name = str(brand_name or "").strip()
    choices = [("", "Selecione")]
    if normalized_brand_name:
        choices.extend((model.name, model.name) for model in FipeVehicleModel.objects.filter(vehicle_type=FipeVehicleType.CARROS, brand__vehicle_type=FipeVehicleType.CARROS, brand__name__iexact=normalized_brand_name, brand__is_active=True, is_active=True).order_by("name"))
    return _with_selected_choice(choices, model_name)


def _vehicle_fuel_form_choices_from_catalog(brand_name: object, model_name: object, selected_fuel: object = "") -> list[tuple[str, str]]:
    normalized_brand_name = str(brand_name or "").strip()
    normalized_model_name = str(model_name or "").strip()
    choices = [("", "Selecione")]

    if normalized_brand_name and normalized_model_name:
        model = (
            FipeVehicleModel.objects.filter(
                vehicle_type=FipeVehicleType.CARROS,
                brand__vehicle_type=FipeVehicleType.CARROS,
                brand__name__iexact=normalized_brand_name,
                name__iexact=normalized_model_name,
                brand__is_active=True,
                is_active=True,
            )
            .select_related("brand")
            .first()
        )
        if model is not None:
            cache = FipeModelFuelCache.objects.filter(vehicle_type=FipeVehicleType.CARROS, model=model).first()
            if cache is not None:
                seen_fuels: set[str] = set()
                for raw_value in cache.fuel_values:
                    normalized_value = normalize_vehicle_fuel_choice(raw_value) or str(raw_value or "").strip()
                    if not normalized_value or normalized_value in seen_fuels:
                        continue
                    seen_fuels.add(normalized_value)
                    choices.append((normalized_value, normalized_value))

    return _with_selected_choice(choices, selected_fuel)


class VehicleEngineModelValidationBypassMixin:
    def _post_clean(self) -> None:
        engine_field = self.instance._meta.get_field("engine")
        original_choices = engine_field.choices
        engine_field.choices = None
        try:
            super()._post_clean()
        finally:
            engine_field.choices = original_choices


class VehicleInlineForm(VehicleEngineModelValidationBypassMixin, CoreModelForm):
    brand = forms.CharField(label="Marca", required=False, widget=SearchableSelectInput(choices=[]))
    model = forms.CharField(label="Modelo", required=False, widget=SearchableSelectInput())
    engine = forms.CharField(label="Motor", required=False, widget=SearchableSelectInput(choices=[]))
    fuel = forms.CharField(label="Combustível", required=False, widget=SearchableSelectInput())

    class Meta:
        model = Vehicle
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        brand_value = self.data.get(self.add_prefix("brand")) if self.is_bound else self.initial.get("brand") or getattr(self.instance, "brand", None)
        model_value = self.data.get(self.add_prefix("model")) if self.is_bound else self.initial.get("model") or getattr(self.instance, "model", None)
        fuel_value = self.data.get(self.add_prefix("fuel")) if self.is_bound else self.initial.get("fuel") or getattr(self.instance, "fuel", None)

        self.fields["brand"].widget.choices = _with_selected_choice(_vehicle_brand_form_choices(), brand_value)
        self.fields["model"].widget.choices = _vehicle_model_form_choices(brand_name=brand_value, model_name=model_value)
        self.fields["fuel"].widget.choices = _vehicle_fuel_form_choices_from_catalog(brand_value, model_value, fuel_value)
        self.fields["engine"].widget.choices = vehicle_engine_form_choices()

        self.fields["brand"].widget.attrs.update({"data-catalog-field": "brand"})
        self.fields["model"].widget.attrs.update({"data-catalog-field": "model"})
        self.fields["fuel"].widget.attrs.update({"data-catalog-field": "fuel"})
        self.fields["engine"].widget.attrs.update({"data-catalog-field": "engine"})

        if not self.is_bound:
            _set_normalized_initial_choice(self, "engine", self.initial.get("engine") or getattr(self.instance, "engine", None), normalize_vehicle_engine_choice)
            _set_normalized_initial_choice(self, "fuel", self.initial.get("fuel") or getattr(self.instance, "fuel", None), normalize_vehicle_fuel_choice)

    def clean_plate(self):
        plate = plate_case(self.cleaned_data.get("plate") or "")
        workshop = self.workshop or getattr(self.instance, "workshop", None)

        if not plate or not workshop:
            return plate

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
        "brand": SearchableSelectInput(choices=[]),
        "model": SearchableSelectInput(),
        "year_fabrication": TextInput(),
        "year_model": TextInput(),
        "color": TextInput(),
        "fuel": SearchableSelectInput(),
        "engine": SearchableSelectInput(choices=[]),
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
            "accepts_messages",
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
            "accepts_messages": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.setup_address_fields()
        # Callable model default enables show_hidden_initial; our checkbox widget does not
        # reliably pair with that hidden input under crispy, so compare against instance/initial.
        self.fields["accepts_messages"].show_hidden_initial = False

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
                Field("accepts_messages", wrapper_class="col-span-12 lg:col-span-4"),
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
                Div(HTML('<div id="vehicle-section" class="space-y-4">{% include "customer/partials/vehicle_formset_list.html" %}</div>'), css_class="col-span-12"),
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
            "birth_date",
            "sex",
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
            "birth_date": CalendarDateInput(),
            "sex": SearchableSelectInput(),
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
                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-6">'),
                Field("birth_date", wrapper_class="col-span-12"),
                HTML("</div>"),
                HTML('<div x-show="tipo === \'PF\'" class="col-span-12 lg:col-span-6">'),
                Field("sex", wrapper_class="col-span-12"),
                HTML("</div>"),
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


class QuickVehicleForm(VehicleEngineModelValidationBypassMixin, CoreModelForm):
    brand = forms.CharField(label="Marca", required=False, widget=SearchableSelectInput(choices=[]))
    model = forms.CharField(label="Modelo", required=False, widget=SearchableSelectInput())
    engine = forms.CharField(label="Motor", required=False, widget=SearchableSelectInput(choices=vehicle_engine_form_choices()))
    fuel = forms.CharField(label="Combustível", required=False, widget=SearchableSelectInput())

    class Meta:
        model = Vehicle
        fields = ["plate", "brand", "model", "engine", "fuel", "year_fabrication", "year_model", "color"]
        widgets = {
            "plate": PlateInput(),
            "brand": SearchableSelectInput(choices=[]),
            "model": SearchableSelectInput(),
            "engine": SearchableSelectInput(choices=vehicle_engine_form_choices()),
            "fuel": SearchableSelectInput(),
            "year_fabrication": TextInput(),
            "year_model": TextInput(),
            "color": TextInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.customer = kwargs.pop("customer", None)
        super().__init__(*args, **kwargs)

        brand_value = self.data.get(self.add_prefix("brand")) if self.is_bound else self.initial.get("brand") or getattr(self.instance, "brand", None)
        model_value = self.data.get(self.add_prefix("model")) if self.is_bound else self.initial.get("model") or getattr(self.instance, "model", None)
        fuel_value = self.data.get(self.add_prefix("fuel")) if self.is_bound else self.initial.get("fuel") or getattr(self.instance, "fuel", None)

        self.fields["brand"].widget = SearchableSelectInput(choices=_with_selected_choice(_vehicle_brand_form_choices(), brand_value))
        self.fields["model"].widget = SearchableSelectInput(choices=_vehicle_model_form_choices(brand_value, model_value))
        self.fields["engine"].widget = SearchableSelectInput(choices=vehicle_engine_form_choices())
        self.fields["fuel"].widget = SearchableSelectInput(choices=_vehicle_fuel_form_choices_from_catalog(brand_value, model_value, fuel_value))

        self.fields["brand"].widget.attrs.update({"data-catalog-field": "brand"})
        self.fields["model"].widget.attrs.update({"data-catalog-field": "model"})
        self.fields["fuel"].widget.attrs.update({"data-catalog-field": "fuel"})
        self.fields["engine"].widget.attrs.update({"data-catalog-field": "engine"})

        if not self.is_bound:
            _set_normalized_initial_choice(self, "engine", self.initial.get("engine") or getattr(self.instance, "engine", None), normalize_vehicle_engine_choice)
            _set_normalized_initial_choice(self, "fuel", self.initial.get("fuel") or getattr(self.instance, "fuel", None), normalize_vehicle_fuel_choice)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML("""<script>
            (() => {
                if (window.customerVehicleCatalog) {
                    return;
                }

                const enginePattern = /(^|[^0-9])(\d[\.,]\d)(?!\d)/;

                const api = {
                    getField(container, fieldName) {
                        return container.querySelector(`[name="${fieldName}"], [name$="-${fieldName}"]`);
                    },
                    getFieldValue(container, fieldName) {
                        const input = this.getField(container, fieldName);
                        if (!input) {
                            return '';
                        }
                        const currentValue = String(input.value || '').trim();
                        if (currentValue) {
                            return currentValue;
                        }
                        return String(input.defaultValue || input.getAttribute('value') || '').trim();
                    },
                    getWidgetContainer(input) {
                        return input && input.type === 'hidden' ? input.closest('[x-data]') : null;
                    },
                    isHydrating(container) {
                        return !!(container && container.dataset && container.dataset.catalogHydrating === '1');
                    },
                    setHydrating(container, isHydrating) {
                        if (!container || !container.dataset) {
                            return;
                        }
                        container.dataset.catalogHydrating = isHydrating ? '1' : '0';
                    },
                    nextRequestId(container, requestType) {
                        if (!container || !container.dataset) {
                            return 0;
                        }
                        const key = `${requestType}RequestId`;
                        const nextValue = String((parseInt(container.dataset[key] || '0', 10) || 0) + 1);
                        container.dataset[key] = nextValue;
                        return nextValue;
                    },
                    isLatestRequest(container, requestType, requestId) {
                        if (!container || !container.dataset) {
                            return false;
                        }
                        return String(container.dataset[`${requestType}RequestId`] || '') === String(requestId);
                    },
                    setSearchableOptions(input, options) {
                        const widgetContainer = this.getWidgetContainer(input);
                        if (!widgetContainer) {
                            return;
                        }
                        widgetContainer.dispatchEvent(new CustomEvent('searchable-set-options', {
                            detail: { options },
                            bubbles: true,
                        }));
                    },
                    setSearchableSelection(input, value, label = '', options = [], { silent = false } = {}) {
                        const widgetContainer = this.getWidgetContainer(input);
                        if (!widgetContainer) {
                            this.setFieldValue(input, value, { silent });
                            return;
                        }
                        widgetContainer.dispatchEvent(new CustomEvent('searchable-set-selection', {
                            detail: { value, label, options, silent },
                            bubbles: true,
                        }));
                    },
                    setFieldValue(input, value, { silent = false } = {}) {
                        if (!input) {
                            return;
                        }

                        const normalizedValue = value === null || value === undefined ? '' : String(value);
                        const widgetContainer = this.getWidgetContainer(input);
                        if (widgetContainer && widgetContainer.querySelector('ul[role="listbox"]') && window.Alpine) {
                            widgetContainer.dispatchEvent(new CustomEvent('searchable-set-value', {
                                detail: { value: normalizedValue, silent },
                                bubbles: true,
                            }));
                            return;
                        }

                        input.value = normalizedValue;
                        if (!silent) {
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    },
                    normalizeOptions(options, selectedValue = '') {
                        const seen = new Set();
                        const normalizedOptions = [];

                        (Array.isArray(options) ? options : []).forEach((option) => {
                            const value = String(option && option.id !== undefined && option.id !== null ? option.id : option && option.value !== undefined && option.value !== null ? option.value : '').trim();
                            const label = String(option && option.label !== undefined && option.label !== null ? option.label : value).trim();
                            if (!value || seen.has(value)) {
                                return;
                            }
                            seen.add(value);
                            normalizedOptions.push({ id: value, label });
                        });

                        const normalizedSelectedValue = String(selectedValue || '').trim();
                        if (normalizedSelectedValue && !seen.has(normalizedSelectedValue)) {
                            normalizedOptions.push({ id: normalizedSelectedValue, label: normalizedSelectedValue });
                        }

                        return normalizedOptions;
                    },
                    extractEngineFromModelName(modelName) {
                        const normalizedModelName = String(modelName || '').trim();
                        if (!normalizedModelName) {
                            return '';
                        }
                        const match = normalizedModelName.match(enginePattern);
                        return match ? match[2].replace(',', '.') : '';
                    },
                    async fetchOptions(url) {
                        const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                        if (!response.ok) {
                            throw new Error('Falha ao carregar catálogo de veículos.');
                        }
                        const payload = await response.json();
                        return Array.isArray(payload) ? payload : [];
                    },
                    async fetchFuelOptions(url) {
                        const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                        if (!response.ok) {
                            throw new Error('Falha ao carregar catálogo de veículos.');
                        }
                        const payload = await response.json();
                        if (Array.isArray(payload)) {
                            return { options: payload, warning: '' };
                        }
                        return {
                            options: Array.isArray(payload && payload.options) ? payload.options : [],
                            warning: String(payload && payload.warning ? payload.warning : '').trim(),
                        };
                    },
                    showToast(message, type = 'warning') {
                        const normalizedMessage = String(message || '').trim();
                        if (!normalizedMessage) {
                            return;
                        }
                        document.body.dispatchEvent(new CustomEvent('showToast', {
                            detail: { message: normalizedMessage, type }
                        }));
                    },
                    async loadModels(container, { preserveModel = '', preserveFuel = '', preserveEngine = '', silent = false } = {}) {
                        const brand = this.getFieldValue(container, 'brand');
                        await this.loadModelsFor(container, { brand, preserveModel, preserveFuel, preserveEngine, silent });
                    },
                    async loadModelsFor(container, { brand = '', preserveModel = '', preserveFuel = '', preserveEngine = '', silent = false } = {}) {
                        const modelInput = this.getField(container, 'model');
                        const fuelInput = this.getField(container, 'fuel');
                        const requestId = this.nextRequestId(container, 'model');

                        if (!modelInput || !fuelInput) {
                            return;
                        }

                        if (!brand) {
                            this.setSearchableOptions(modelInput, []);
                            this.setSearchableOptions(fuelInput, []);
                            this.setFieldValue(modelInput, '', { silent });
                            this.setFieldValue(fuelInput, '', { silent });
                            this.syncEngine(container, preserveEngine, { silent });
                            return;
                        }

                        const options = this.normalizeOptions(await this.fetchOptions(`/customer/vehicle-catalog/models/?brand=${encodeURIComponent(brand)}`), preserveModel);
                        if (!this.isLatestRequest(container, 'model', requestId)) {
                            return;
                        }
                        this.setSearchableSelection(modelInput, preserveModel, preserveModel, options, { silent });
                        await this.loadFuelsFor(container, { brand, model: preserveModel, preserveFuel, silent, showWarning: !silent });
                        this.syncEngine(container, preserveEngine, { silent, modelName: preserveModel });
                    },
                    async loadFuels(container, { preserveFuel = '', silent = false } = {}) {
                        const brand = this.getFieldValue(container, 'brand');
                        const model = this.getFieldValue(container, 'model');
                        await this.loadFuelsFor(container, { brand, model, preserveFuel, silent });
                    },
                    async loadFuelsFor(container, { brand = '', model = '', preserveFuel = '', silent = false, showWarning = true } = {}) {
                        const fuelInput = this.getField(container, 'fuel');
                        const requestId = this.nextRequestId(container, 'fuel');

                        if (!fuelInput) {
                            return;
                        }

                        if (!brand || !model) {
                            this.setSearchableOptions(fuelInput, []);
                            this.setFieldValue(fuelInput, '', { silent });
                            return;
                        }

                        const fuelPayload = await this.fetchFuelOptions(`/customer/vehicle-catalog/fuels/?brand=${encodeURIComponent(brand)}&model=${encodeURIComponent(model)}`);
                        const options = this.normalizeOptions(fuelPayload.options, preserveFuel);
                        if (!this.isLatestRequest(container, 'fuel', requestId)) {
                            return;
                        }
                        if (showWarning && fuelPayload.warning) {
                            this.showToast(fuelPayload.warning);
                        }
                        this.setSearchableSelection(fuelInput, preserveFuel, preserveFuel, options, { silent });
                    },
                    syncEngine(container, fallbackEngine = '', { silent = false, modelName = '' } = {}) {
                        const engineInput = this.getField(container, 'engine');
                        if (!engineInput) {
                            return;
                        }

                        const detectedEngine = this.extractEngineFromModelName(modelName || this.getFieldValue(container, 'model')) || String(fallbackEngine || '').trim();
                        this.setSearchableSelection(engineInput, detectedEngine, detectedEngine, detectedEngine ? [{ id: detectedEngine, label: detectedEngine }] : [], { silent });
                    },
                    async hydrateContainer(container) {
                        const brand = this.getFieldValue(container, 'brand');
                        const model = this.getFieldValue(container, 'model');
                        const fuel = this.getFieldValue(container, 'fuel');
                        const engine = this.getFieldValue(container, 'engine');

                        if (!brand) {
                            return;
                        }

                        await this.loadModels(container, {
                            preserveModel: model,
                            preserveFuel: fuel,
                            preserveEngine: engine,
                            silent: true,
                        });
                    },
                    fillTextFields(container, fieldsMap) {
                        Object.entries(fieldsMap).forEach(([fieldName, fieldValue]) => {
                            if (!fieldValue) {
                                return;
                            }
                            const input = this.getField(container, fieldName);
                            if (input) {
                                this.setFieldValue(input, fieldValue);
                            }
                        });
                    },
                    async fillFromPlate(container, data) {
                        this.setHydrating(container, true);
                        try {
                            const brand = String(data.brand || '').trim();
                            const model = String(data.model || '').trim();
                            const fuel = String(data.fuel || '').trim();
                            const engine = String(data.engine || '').trim();
                            const brandInput = this.getField(container, 'brand');

                            this.setSearchableSelection(brandInput, brand, brand, brand ? [{ id: brand, label: brand }] : [], { silent: true });

                            const modelOptions = brand ? this.normalizeOptions(await this.fetchOptions(`/customer/vehicle-catalog/models/?brand=${encodeURIComponent(brand)}`), model) : this.normalizeOptions([], model);
                            const modelInput = this.getField(container, 'model');
                            if (modelInput) {
                                this.setSearchableSelection(modelInput, model, model, modelOptions, { silent: true });
                            }

                            const fuelPayload = brand && model ? await this.fetchFuelOptions(`/customer/vehicle-catalog/fuels/?brand=${encodeURIComponent(brand)}&model=${encodeURIComponent(model)}`) : { options: [], warning: '' };
                            const fuelOptions = this.normalizeOptions(fuelPayload.options, fuel);
                            const fuelInput = this.getField(container, 'fuel');
                            if (fuelInput) {
                                this.setSearchableSelection(fuelInput, fuel, fuel, fuelOptions, { silent: true });
                            }
                            if (fuelPayload.warning) {
                                this.showToast(fuelPayload.warning);
                            }

                            this.syncEngine(container, engine, { silent: true, modelName: model });

                            this.fillTextFields(container, {
                                year_fabrication: data.year_fabrication,
                                year_model: data.year_model,
                                color: data.color,
                                chassi: data.chassi,
                                renavam: data.renavam,
                                type: data.type,
                            });
                        } finally {
                            this.setHydrating(container, false);
                        }
                    },
                };

                document.addEventListener('searchable-change', async (event) => {
                    const fieldName = event.detail && event.detail.name ? String(event.detail.name) : '';
                    if (!fieldName) {
                        return;
                    }

                    const container = event.target.closest('.vehicle-item') || event.target.closest('.customer-vehicle-catalog-form') || event.target.closest('form');
                    if (!container || api.isHydrating(container)) {
                        return;
                    }

                    try {
                        if (fieldName.endsWith('brand')) {
                            await api.loadModels(container);
                            return;
                        }
                        if (fieldName.endsWith('model')) {
                            await api.loadFuels(container);
                            api.syncEngine(container);
                        }
                    } catch (error) {
                        console.warn('Erro ao carregar catálogo local de veículos:', error);
                    }
                });

                document.addEventListener('change', async (event) => {
                    const element = event.target;
                    const isPlateField = element.name && (element.name.endsWith('plate') || element.name === 'plate' || element.name.endsWith('-plate'));
                    if (!isPlateField) {
                        return;
                    }

                    const rawPlate = String(element.value || '').trim();
                    const plate = rawPlate.toUpperCase();
                    if (plate.length < 7) {
                        return;
                    }

                    const container = element.closest('.vehicle-item') || element.closest('.customer-vehicle-catalog-form') || element.closest('form');
                    if (!container) {
                        return;
                    }

                    const form = container.closest('form');
                    if (form) {
                        const prevTransferInput = form.querySelector('input[name="transfer_plate"]');
                        if (prevTransferInput) {
                            prevTransferInput.remove();
                        }
                    }

                    element.classList.add('loading-api');
                    try {
                        const media = rawPlate.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
                        const [checkPlateResult, dupResult] = await Promise.allSettled([
                            fetch(`/customer/check-plate/${media}/`),
                            fetch(`/customer/check-plate-duplicate/${rawPlate}/`),
                        ]);

                        if (checkPlateResult.status === 'fulfilled') {
                            const response = checkPlateResult.value;
                            if (response.ok) {
                                const data = await response.json();
                                await api.fillFromPlate(container, data);

                                const missingFields = [];
                                if (!data.engine) missingFields.push('Motor');
                                if (!data.fuel) missingFields.push('Combustível');

                                if (missingFields.length > 0) {
                                    document.body.dispatchEvent(new CustomEvent('showToast', {
                                        detail: {
                                            message: `Campos não disponíveis: ${missingFields.join(', ')}`,
                                            type: 'warning'
                                        }
                                    }));
                                }
                            }
                        } else {
                            console.error('Falha ao buscar placa no catálogo:', checkPlateResult.reason);
                        }

                        if (dupResult.status === 'fulfilled') {
                            const response = dupResult.value;
                            if (response.ok) {
                                const dupData = await response.json();
                                if (dupData.exists) {
                                    const targetForm = form || container;
                                    targetForm.dataset.transferVehicleId = dupData.vehicle_id;
                                    targetForm.dataset.transferCustomerName = dupData.customer_name;

                                    const plateDisplay = targetForm.querySelector('.transfer-plate-display');
                                    const customerDisplay = targetForm.querySelector('.transfer-customer-display');
                                    if (plateDisplay) plateDisplay.textContent = rawPlate;
                                    if (customerDisplay) customerDisplay.textContent = dupData.customer_name;

                                    const modalToggle = targetForm.querySelector('.transfer-modal-toggle');
                                    if (modalToggle) modalToggle.checked = true;
                                }
                            } else {
                                console.error('Erro no servidor ao verificar placa duplicada:', response.status, response.statusText);
                            }
                        } else {
                            console.error('Falha ao verificar placa duplicada:', dupResult.reason);
                        }
                    } catch (error) {
                        console.error('Erro ao processar placa:', error);
                    } finally {
                        element.classList.remove('loading-api');
                    }
                });

                document.addEventListener('click', (event) => {
                    const confirmBtn = event.target.closest('.transfer-confirm-btn');
                    if (!confirmBtn) return;

                    const form = confirmBtn.closest('form');
                    if (!form) return;

                    const vehicleId = form.dataset.transferVehicleId;
                    if (!vehicleId) return;

                    const existingHidden = form.querySelector('input[name="transfer_plate"]');
                    if (existingHidden) existingHidden.remove();

                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = 'transfer_plate';
                    hiddenInput.value = vehicleId;
                    form.appendChild(hiddenInput);

                    const modalToggle = form.querySelector('.transfer-modal-toggle');
                    if (modalToggle) modalToggle.checked = false;
                });

                const hydrateAll = (root = document) => {
                    root.querySelectorAll('.vehicle-item, .customer-vehicle-catalog-form').forEach((container) => {
                        api.hydrateContainer(container).catch((error) => {
                            console.warn('Erro ao hidratar catálogo local de veículos:', error);
                        });
                    });
                };

                document.addEventListener('DOMContentLoaded', () => hydrateAll());
                document.body.addEventListener('htmx:afterSwap', (event) => {
                    if (event.detail && event.detail.target) {
                        hydrateAll(event.detail.target);
                    }
                });

                window.customerVehicleCatalog = api;
            })();
            </script>"""),
            Div(
                Field("plate", wrapper_class="col-span-12 md:col-span-6 xl:col-span-3"),
                Field("brand", wrapper_class="col-span-12 md:col-span-6 xl:col-span-3"),
                Field("model", wrapper_class="col-span-12 xl:col-span-6"),
                Field("engine", wrapper_class="col-span-12 md:col-span-6 xl:col-span-3"),
                Field("fuel", wrapper_class="col-span-12 md:col-span-6 xl:col-span-3"),
                Field("year_fabrication", wrapper_class="col-span-12 sm:col-span-6 xl:col-span-2"),
                Field("year_model", wrapper_class="col-span-12 sm:col-span-6 xl:col-span-2"),
                Field("color", wrapper_class="col-span-12 md:col-span-6 xl:col-span-2"),
                css_class="customer-vehicle-catalog-form grid grid-cols-12 gap-x-4 gap-y-3 items-start",
            ),
        )

    def clean_plate(self):
        plate = (self.cleaned_data.get("plate") or "").strip().upper()
        workshop = self.workshop or getattr(self.instance, "workshop", None)

        if not plate or not workshop:
            return plate

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

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.workshop:
            instance.workshop = self.workshop
        if self.customer:
            instance.customer = self.customer
        if commit:
            instance.save()
        return instance
