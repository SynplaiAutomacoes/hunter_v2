from __future__ import annotations

import json
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.core.cache import cache
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone

from apps.budget.models import Budget
from apps.catalog.models import FipeModelFuelCache, FipeVehicleBrand, FipeVehicleModel, FipeVehicleType
from apps.core.presentation.widgets import CPForCNPJInput, CheckboxButtonGroupInput, CheckboxInput, PhoneInput, PlateInput, SearchableSelectInput, TextInput, TextareaInput
from apps.customer.cpf_cnpj_validator import is_valid_cpf
from apps.customer.vehicle_engine import normalize_vehicle_engine_choice, vehicle_engine_form_choices
from apps.customer.models import Customer, Vehicle
from apps.customer.vehicle_fuel import normalize_vehicle_fuel_choice, vehicle_fuel_form_choices
from apps.core.text_normalization import name_case, plate_case, sentence_case
from apps.messaging.application.services.appointment_alert import sync_appointment_alert_schedule
from apps.scheduling.models import ALERT_LEAD_TIME_CHOICES, DEFAULT_ALERT_LEAD_TIMES, Appointment, AppointmentStatus
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop
from apps.core.presentation.forms import CoreForm, CoreModelForm


def _uppercase_text_input() -> TextInput:
    return TextInput(attrs={"oninput": "this.value = this.value.toUpperCase()", "autocapitalize": "characters"})


def _year_text_input() -> TextInput:
    return TextInput(attrs={"inputmode": "numeric", "maxlength": "4"})


def _normalize_upper_text(value: object) -> str:
    return str(value or "").strip().upper()


def _digits_only(value: object) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _with_selected_choice(choices: list[tuple[str, str]], selected_value: object) -> list[tuple[str, str]]:
    normalized_selected_value = str(selected_value or "").strip()
    if not normalized_selected_value:
        return choices

    if any(str(value) == normalized_selected_value for value, _ in choices):
        return choices

    return [*choices, (normalized_selected_value, normalized_selected_value)]


def _selected_instance_queryset(*, model: type[Customer] | type[Vehicle] | type[Budget] | type[WorkOrder], selected_id: object, workshop: Workshop | None = None):
    normalized_selected_id = str(selected_id or "").strip()
    if not normalized_selected_id:
        return model.objects.none()

    queryset = model.objects.filter(pk=normalized_selected_id)
    if workshop is not None:
        queryset = queryset.filter(workshop=workshop)
    return queryset


def _guest_vehicle_brand_form_choices() -> list[tuple[str, str]]:
    cache_key = "scheduling:guest_vehicle_brands"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    choices = [
        ("", "Selecione"),
        *[(brand.name, brand.name) for brand in FipeVehicleBrand.objects.filter(vehicle_type=FipeVehicleType.CARROS, is_active=True).order_by("name")],
    ]
    cache.set(cache_key, choices, 86400)
    return choices


def _guest_vehicle_model_form_choices(brand_name: object, model_name: object = "") -> list[tuple[str, str]]:
    normalized_brand_name = str(brand_name or "").strip()
    cache_key = f"scheduling:guest_vehicle_models:{normalized_brand_name}"
    choices = cache.get(cache_key)
    if choices is None:
        choices = [("", "Selecione")]
        if normalized_brand_name:
            choices.extend(
                (model.name, model.name)
                for model in FipeVehicleModel.objects.filter(
                    vehicle_type=FipeVehicleType.CARROS,
                    brand__vehicle_type=FipeVehicleType.CARROS,
                    brand__name__iexact=normalized_brand_name,
                    brand__is_active=True,
                    is_active=True,
                ).order_by("name")
            )
        cache.set(cache_key, choices, 86400)
    return _with_selected_choice(choices, model_name)


def _guest_vehicle_fuel_form_choices_from_catalog(brand_name: object, model_name: object, selected_fuel: object = "") -> list[tuple[str, str]]:
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


def _serialize_vehicle_details(vehicle: Vehicle | None) -> dict[str, str]:
    if vehicle is None:
        return {
            "plate": "",
            "brand": "",
            "model": "",
            "year_fabrication": "",
            "year_model": "",
            "engine": "",
            "fuel": "",
        }

    return {
        "plate": str(vehicle.plate or ""),
        "brand": str(vehicle.brand or ""),
        "model": str(vehicle.model or ""),
        "year_fabrication": str(vehicle.year_fabrication or ""),
        "year_model": str(vehicle.year_model or ""),
        "engine": normalize_vehicle_engine_choice(vehicle.engine),
        "fuel": normalize_vehicle_fuel_choice(vehicle.fuel),
    }


def _build_readonly_vehicle_field(*, field_id: str, label: str, value: str, wrapper_class: str) -> str:
    return f'''
        <div class="{wrapper_class}">
            <label for="{field_id}" class="mb-0 text-sm font-semibold text-base-content">{escape(label)}</label>
            <input type="text" id="{field_id}" value="{escape(value)}" class="input-theme" disabled>
        </div>
    '''


class AppointmentForm(CoreModelForm):
    is_customer_registered = forms.BooleanField(label="Cliente cadastrado", required=False, initial=True, widget=CheckboxInput())
    customer = forms.ModelChoiceField(label="Cliente", queryset=Customer.objects.none(), widget=SearchableSelectInput(), required=False)
    vehicle = forms.ModelChoiceField(label="Veiculo", queryset=Vehicle.objects.none(), widget=SearchableSelectInput(), required=False)
    guest_customer_name = forms.CharField(label="Nome", required=False, widget=_uppercase_text_input())
    guest_customer_cpf = forms.CharField(label="CPF", required=False, widget=CPForCNPJInput(mode="cpf"))
    guest_customer_phone = forms.CharField(label="Telefone", required=False, widget=PhoneInput())
    guest_vehicle_plate = forms.CharField(label="Placa", required=False, widget=PlateInput())
    guest_vehicle_brand = forms.CharField(label="Marca", required=False, widget=SearchableSelectInput(choices=[]))
    guest_vehicle_model = forms.CharField(label="Modelo", required=False, widget=SearchableSelectInput(choices=[]))
    guest_vehicle_year_fabrication = forms.CharField(label="Ano Fabricacao", required=False, widget=_year_text_input())
    guest_vehicle_year_model = forms.CharField(label="Ano Modelo", required=False, widget=_year_text_input())
    guest_vehicle_engine = forms.CharField(label="Motorizacao", required=False, widget=SearchableSelectInput(choices=vehicle_engine_form_choices()))
    guest_vehicle_fuel = forms.CharField(label="Combustivel", required=False, widget=SearchableSelectInput(choices=vehicle_fuel_form_choices()))
    budget = forms.ModelChoiceField(label="Orcamento vinculado", queryset=Budget.objects.none(), widget=SearchableSelectInput(), required=False)
    workorder = forms.ModelChoiceField(label="Ordem de servico vinculada", queryset=WorkOrder.objects.none(), widget=SearchableSelectInput(), required=False)
    alert_lead_times = forms.MultipleChoiceField(
        label="Antecedência do alerta",
        choices=ALERT_LEAD_TIME_CHOICES,
        widget=CheckboxButtonGroupInput,
        required=False,
    )

    class Meta:
        model = Appointment
        fields = [
            "title",
            "customer",
            "vehicle",
            "guest_customer_name",
            "guest_customer_cpf",
            "guest_customer_phone",
            "guest_vehicle_plate",
            "guest_vehicle_brand",
            "guest_vehicle_model",
            "guest_vehicle_year_fabrication",
            "guest_vehicle_year_model",
            "guest_vehicle_engine",
            "guest_vehicle_fuel",
            "starts_at",
            "ends_at",
            "block_color",
            "alert_customer",
            "alert_lead_times",
            "status",
            "budget",
            "workorder",
            "notes",
        ]
        widgets = {
            "title": TextInput(),
            "guest_customer_name": _uppercase_text_input(),
            "guest_customer_cpf": CPForCNPJInput(mode="cpf"),
            "guest_customer_phone": PhoneInput(),
            "guest_vehicle_plate": PlateInput(),
            "guest_vehicle_brand": SearchableSelectInput(choices=[]),
            "guest_vehicle_model": SearchableSelectInput(choices=[]),
            "guest_vehicle_year_fabrication": _year_text_input(),
            "guest_vehicle_year_model": _year_text_input(),
            "guest_vehicle_engine": SearchableSelectInput(choices=vehicle_engine_form_choices()),
            "guest_vehicle_fuel": SearchableSelectInput(choices=vehicle_fuel_form_choices()),
            "starts_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "input-theme h-12"}),
            "ends_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "input-theme h-12"}),
            "block_color": forms.HiddenInput(),
            "alert_customer": CheckboxInput(),
            "status": SearchableSelectInput(attrs={"class": "h-12"}),
            "notes": TextareaInput(rows=3),
        }

    def __init__(self, *args: Any, workshop: Workshop | None = None, request=None, **kwargs: Any):
        self.workshop = workshop
        self.request = request
        super().__init__(*args, **kwargs)

        if self.workshop is not None:
            self.instance.workshop = self.workshop

        customer_field = self.fields["customer"]
        registered_field = self.fields["is_customer_registered"]
        vehicle_field = self.fields["vehicle"]
        budget_field = self.fields["budget"]
        workorder_field = self.fields["workorder"]
        starts_at_field = self.fields["starts_at"]
        ends_at_field = self.fields["ends_at"]

        if not isinstance(starts_at_field, forms.DateTimeField) or not isinstance(ends_at_field, forms.DateTimeField):
            raise TypeError("Campos de data/hora invalidos no AppointmentForm")

        starts_at_field.input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]
        ends_at_field.input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]

        if not isinstance(customer_field, forms.ModelChoiceField) or not isinstance(vehicle_field, forms.ModelChoiceField):
            raise TypeError("Campos de cliente/veiculo invalidos no AppointmentForm")

        if not isinstance(budget_field, forms.ModelChoiceField) or not isinstance(workorder_field, forms.ModelChoiceField):
            raise TypeError("Campos de budget/workorder invalidos no AppointmentForm")

        if self.workshop:
            customer_field.queryset = Customer.objects.filter(workshop=self.workshop, is_active=True).order_by("name")

            budget_qs = Budget.objects.filter(workshop=self.workshop).select_related("customer", "vehicle").order_by("-criado_em")[:200]
            if self.instance and self.instance.budget_id:
                if not budget_qs.filter(pk=self.instance.budget_id).exists():
                    budget_qs = budget_qs | Budget.objects.filter(pk=self.instance.budget_id)
            budget_field.queryset = budget_qs

            workorder_qs = WorkOrder.objects.filter(workshop=self.workshop).select_related("budget", "budget__customer", "budget__vehicle").order_by("-criado_em")[:200]
            if self.instance and self.instance.workorder_id:
                if not workorder_qs.filter(pk=self.instance.workorder_id).exists():
                    workorder_qs = workorder_qs | WorkOrder.objects.filter(pk=self.instance.workorder_id)
            workorder_field.queryset = workorder_qs

            def _budget_label_from_instance(obj):
                return f"Orçamento #{obj.pk}"

            def _workorder_label_from_instance(obj):
                return f"O.S. #{obj.get_id}"

            budget_field.label_from_instance = _budget_label_from_instance
            workorder_field.label_from_instance = _workorder_label_from_instance

        customer_field.widget.attrs.update({":disabled": "!isCustomerRegistered"})
        vehicle_field.widget.attrs.update({":disabled": "!isCustomerRegistered || !customerId"})
        budget_field.widget.attrs.update({":disabled": "!isCustomerRegistered || !vehicleId"})
        workorder_field.widget.attrs.update({":disabled": "!isCustomerRegistered || !vehicleId"})

        is_customer_registered = True
        if self.is_bound:
            is_customer_registered = (self.data.get("is_customer_registered") or "") in {"on", "true", "1", "True"}
        elif self.instance and self.instance.pk:
            is_customer_registered = bool(self.instance.customer_id)
        elif "is_customer_registered" in self.initial:
            is_customer_registered = bool(self.initial.get("is_customer_registered"))

        registered_field.initial = is_customer_registered
        self.initial["is_customer_registered"] = is_customer_registered

        guest_field_names = [
            "guest_customer_name",
            "guest_customer_cpf",
            "guest_customer_phone",
            "guest_vehicle_plate",
            "guest_vehicle_brand",
            "guest_vehicle_model",
            "guest_vehicle_year_fabrication",
            "guest_vehicle_year_model",
            "guest_vehicle_engine",
            "guest_vehicle_fuel",
        ]
        for field_name in guest_field_names:
            self.fields[field_name].required = True
        self.fields["customer"].required = True

        if is_customer_registered:
            for field_name in guest_field_names:
                self.fields[field_name].required = False
        else:
            self.fields["customer"].required = False

        customer_field.error_messages["required"] = "Selecione um cliente cadastrado para continuar."
        self.fields["guest_customer_name"].error_messages["required"] = "Informe o nome do cliente."
        self.fields["guest_customer_cpf"].error_messages["required"] = "Informe o CPF do cliente."
        self.fields["guest_customer_phone"].error_messages["required"] = "Informe o telefone do cliente."
        self.fields["guest_vehicle_plate"].error_messages["required"] = "Informe a placa do veiculo."
        self.fields["guest_vehicle_brand"].error_messages["required"] = "Informe a marca do veiculo."
        self.fields["guest_vehicle_model"].error_messages["required"] = "Informe o modelo do veiculo."
        self.fields["guest_vehicle_year_fabrication"].error_messages["required"] = "Informe o ano de fabricação."
        self.fields["guest_vehicle_year_model"].error_messages["required"] = "Informe o ano do modelo."
        self.fields["guest_vehicle_engine"].error_messages["required"] = "Informe a motorização ou selecione uma opção."
        self.fields["guest_vehicle_fuel"].error_messages["required"] = "Informe o combustivel ou selecione uma opção."

        selected_customer_id = ""
        selected_vehicle_id = ""
        if self.is_bound:
            selected_customer_id = (self.data.get("customer") or "").strip()
            selected_vehicle_id = (self.data.get("vehicle") or "").strip()
        elif self.instance and self.instance.pk and is_customer_registered:
            selected_customer_id = str(self.instance.customer_id)
            selected_vehicle_id = str(self.instance.vehicle_id or "")

        if not selected_customer_id and self.initial.get("customer"):
            selected_customer_id = str(self.initial.get("customer"))

        if not selected_vehicle_id and self.initial.get("vehicle"):
            selected_vehicle_id = str(self.initial.get("vehicle"))

        selected_budget_id = ""
        selected_workorder_id = ""
        if self.is_bound:
            selected_budget_id = (self.data.get("budget") or "").strip()
            selected_workorder_id = (self.data.get("workorder") or "").strip()
        elif self.instance and self.instance.pk:
            selected_budget_id = str(self.instance.budget_id or "")
            selected_workorder_id = str(self.instance.workorder_id or "")

        if not selected_budget_id and self.initial.get("budget"):
            selected_budget_id = str(self.initial.get("budget"))
        if not selected_workorder_id and self.initial.get("workorder"):
            selected_workorder_id = str(self.initial.get("workorder"))

        if is_customer_registered:
            customer_field.queryset = _selected_instance_queryset(model=Customer, selected_id=selected_customer_id, workshop=self.workshop)

        if is_customer_registered and selected_customer_id and self.workshop:
            vehicle_field.queryset = Vehicle.objects.filter(workshop=self.workshop, customer_id=selected_customer_id).order_by("plate")
        else:
            vehicle_field.queryset = Vehicle.objects.none()

        if is_customer_registered and selected_vehicle_id and self.workshop:
            budget_field.queryset = Budget.objects.filter(workshop=self.workshop, vehicle_id=selected_vehicle_id).select_related("customer", "vehicle").order_by("-criado_em")
            workorder_field.queryset = WorkOrder.objects.filter(workshop=self.workshop, budget__vehicle_id=selected_vehicle_id).select_related("budget", "budget__customer", "budget__vehicle").order_by("-criado_em")
        else:
            budget_field.queryset = Budget.objects.none()
            workorder_field.queryset = WorkOrder.objects.none()

        customer_field.widget = SearchableSelectInput(choices=tuple(customer_field.choices), attrs={"data-source-url": reverse("scheduling:get_customers")})
        budget_field.widget = SearchableSelectInput(choices=tuple(budget_field.choices))
        workorder_field.widget = SearchableSelectInput(choices=tuple(workorder_field.choices))

        selected_registered_vehicle: Vehicle | None = None
        if is_customer_registered and selected_vehicle_id and self.workshop:
            selected_registered_vehicle = Vehicle.objects.filter(workshop=self.workshop, pk=selected_vehicle_id).first()

        selected_registered_vehicle_details = _serialize_vehicle_details(selected_registered_vehicle)

        if not self.is_bound:
            normalized_guest_vehicle_engine = normalize_vehicle_engine_choice(self.initial.get("guest_vehicle_engine") or getattr(self.instance, "guest_vehicle_engine", ""))
            self.initial["guest_vehicle_engine"] = normalized_guest_vehicle_engine
            self.fields["guest_vehicle_engine"].initial = normalized_guest_vehicle_engine
            normalized_guest_vehicle_fuel = normalize_vehicle_fuel_choice(self.initial.get("guest_vehicle_fuel") or getattr(self.instance, "guest_vehicle_fuel", ""))
            self.initial["guest_vehicle_fuel"] = normalized_guest_vehicle_fuel
            self.fields["guest_vehicle_fuel"].initial = normalized_guest_vehicle_fuel

        guest_brand_value = self.data.get("guest_vehicle_brand") if self.is_bound else self.initial.get("guest_vehicle_brand") or getattr(self.instance, "guest_vehicle_brand", "")
        guest_model_value = self.data.get("guest_vehicle_model") if self.is_bound else self.initial.get("guest_vehicle_model") or getattr(self.instance, "guest_vehicle_model", "")
        guest_fuel_value = self.data.get("guest_vehicle_fuel") if self.is_bound else self.initial.get("guest_vehicle_fuel") or getattr(self.instance, "guest_vehicle_fuel", "")

        self.fields["guest_vehicle_brand"].widget.choices = _with_selected_choice(_guest_vehicle_brand_form_choices(), guest_brand_value)
        self.fields["guest_vehicle_model"].widget.choices = _guest_vehicle_model_form_choices(guest_brand_value, guest_model_value)
        self.fields["guest_vehicle_fuel"].widget.choices = _guest_vehicle_fuel_form_choices_from_catalog(guest_brand_value, guest_model_value, guest_fuel_value)

        self.fields["guest_vehicle_brand"].widget.attrs.update({"data-catalog-field": "brand"})
        self.fields["guest_vehicle_model"].widget.attrs.update({"data-catalog-field": "model"})
        self.fields["guest_vehicle_fuel"].widget.attrs.update({"data-catalog-field": "fuel"})
        self.fields["guest_vehicle_engine"].widget.attrs.update({"data-catalog-field": "engine"})

        if self.instance and self.instance.pk:
            if self.instance.starts_at:
                self.initial["starts_at"] = timezone.localtime(self.instance.starts_at).strftime("%Y-%m-%dT%H:%M")
            if self.instance.ends_at:
                self.initial["ends_at"] = timezone.localtime(self.instance.ends_at).strftime("%Y-%m-%dT%H:%M")

        self.helper = FormHelper()
        self.helper.form_tag = False

        _all_engine_choices = [{"id": choice[0], "label": choice[1]} for choice in vehicle_engine_form_choices()]
        _all_fuel_choices = [{"id": choice[0], "label": choice[1]} for choice in vehicle_fuel_form_choices()]
        all_engine_choices_json = json.dumps(_all_engine_choices)
        all_fuel_choices_json = json.dumps(_all_fuel_choices)

        alert_customer_initial = bool(self.instance.alert_customer) if self.instance and self.instance.pk else bool(self.initial.get("alert_customer", True))
        if self.is_bound:
            alert_customer_initial = (self.data.get("alert_customer") or "") in {"on", "true", "1", "True"}

        alert_lead_times_field = self.fields["alert_lead_times"]
        alert_lead_times_field.required = False
        alert_lead_times_field.label = ""
        if not self.is_bound:
            if self.instance and self.instance.pk:
                alert_lead_times_field.initial = [str(value) for value in (self.instance.alert_lead_times or [])]
            elif self.initial.get("alert_lead_times") is not None:
                alert_lead_times_field.initial = [str(value) for value in self.initial["alert_lead_times"]]
            else:
                alert_lead_times_field.initial = [str(value) for value in DEFAULT_ALERT_LEAD_TIMES]

        customer_vehicle_x_data = json.dumps(
            {
                "customerId": selected_customer_id,
                "vehicleId": selected_vehicle_id,
                "isCustomerRegistered": is_customer_registered,
                "alertCustomer": alert_customer_initial,
            }
        )
        registered_vehicle_fields_html = "".join(
            [
                _build_readonly_vehicle_field(
                    field_id="id_registered_vehicle_plate_display",
                    label="Placa",
                    value=selected_registered_vehicle_details["plate"],
                    wrapper_class="col-span-12 lg:col-span-3",
                ),
                _build_readonly_vehicle_field(
                    field_id="id_registered_vehicle_brand_display",
                    label="Marca",
                    value=selected_registered_vehicle_details["brand"],
                    wrapper_class="col-span-12 lg:col-span-3",
                ),
                _build_readonly_vehicle_field(
                    field_id="id_registered_vehicle_model_display",
                    label="Modelo",
                    value=selected_registered_vehicle_details["model"],
                    wrapper_class="col-span-12 lg:col-span-3",
                ),
                _build_readonly_vehicle_field(
                    field_id="id_registered_vehicle_year_fabrication_display",
                    label="Ano Fabricacao",
                    value=selected_registered_vehicle_details["year_fabrication"],
                    wrapper_class="col-span-12 lg:col-span-3",
                ),
                _build_readonly_vehicle_field(
                    field_id="id_registered_vehicle_year_model_display",
                    label="Ano Modelo",
                    value=selected_registered_vehicle_details["year_model"],
                    wrapper_class="col-span-12 lg:col-span-3",
                ),
                _build_readonly_vehicle_field(
                    field_id="id_registered_vehicle_engine_display",
                    label="Motorizacao",
                    value=selected_registered_vehicle_details["engine"],
                    wrapper_class="col-span-12 lg:col-span-3",
                ),
                _build_readonly_vehicle_field(
                    field_id="id_registered_vehicle_fuel_display",
                    label="Combustivel",
                    value=selected_registered_vehicle_details["fuel"],
                    wrapper_class="col-span-12 lg:col-span-3",
                ),
            ]
        )

        self.helper.layout = Layout(
            HTML(
                f"""<script>
                    var allEngineChoices = {all_engine_choices_json};
                    var allFuelChoices = {all_fuel_choices_json};
                </script>"""
            ),
            HTML(
                r"""
                <script>
                    function getAlpineContext(element) {
                        if (!element || !window.Alpine) return null;
                        try {
                            return Alpine.$data(element);
                        } catch (error) {
                            return null;
                        }
                    }

                    function syncAppointmentContextFromInput(name, value) {
                        const shell = document.querySelector('[data-appointment-form-shell]');
                        const data = getAlpineContext(shell);
                        if (!data) return;

                        if (name === 'is_customer_registered') {
                            data.isCustomerRegistered = value === true || value === 'true' || value === 'on' || value === '1';
                            if (!data.isCustomerRegistered) {
                                data.customerId = '';
                                data.vehicleId = '';
                                clearRegisteredVehicleDetails();
                            }
                        }

                        if (name === 'customer') {
                            data.customerId = value || '';
                            data.vehicleId = '';
                            clearRegisteredVehicleDetails();
                        }

                        if (name === 'vehicle') {
                            data.vehicleId = value || '';
                            if (!data.vehicleId) {
                                clearRegisteredVehicleDetails();
                            }
                        }
                    }

                    function setRegisteredMode(isRegistered) {
                        const shell = document.querySelector('[data-appointment-form-shell]');
                        const shellData = getAlpineContext(shell);
                        if (shellData) {
                            shellData.isCustomerRegistered = !!isRegistered;
                        }

                        const toggle = document.getElementById('id_is_customer_registered');
                        if (toggle) {
                            toggle.checked = !!isRegistered;
                            toggle.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }

                    function setInputValue(inputId, value, options = {}) {
                        const input = document.getElementById(inputId);
                        if (!input || value === null || value === undefined || value === '') return;

                        const normalizedValue = options.uppercase ? String(value).toUpperCase() : String(value);

                        if (input.type === 'hidden') {
                            const widgetContainer = input.closest('[x-data]');
                            if (widgetContainer) {
                                widgetContainer.dispatchEvent(new CustomEvent('searchable-set-value', {
                                    detail: { value: normalizedValue },
                                    bubbles: true,
                                }));
                                return;
                            }
                        }

                        input.value = normalizedValue;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    function setReadonlyFieldValue(inputId, value) {
                        const input = document.getElementById(inputId);
                        if (!input) return;
                        input.value = value === null || value === undefined ? '' : String(value);
                    }

                    function getWidgetContainer(input) {
                        return input && input.type === 'hidden' ? input.closest('[x-data]') : null;
                    }

                    function setSearchableSelection(input, value, label = '', options = [], { silent = false } = {}) {
                        if (!input) return;

                        const normalizedValue = value === null || value === undefined ? '' : String(value);
                        const widgetContainer = getWidgetContainer(input);
                        if (!widgetContainer) {
                            setInputValue(input.id, normalizedValue);
                            return;
                        }

                        widgetContainer.dispatchEvent(new CustomEvent('searchable-set-selection', {
                            detail: { value: normalizedValue, label: String(label || normalizedValue), options, silent },
                            bubbles: true,
                        }));
                    }

                    function normalizeOptions(options, selectedValue = '') {
                        const seen = new Set();
                        const normalizedOptions = [];

                        (Array.isArray(options) ? options : []).forEach((option) => {
                            const value = String(option && option.id !== undefined && option.id !== null ? option.id : option && option.value !== undefined && option.value !== null ? option.value : '').trim();
                            const label = String(option && option.label !== undefined && option.label !== null ? option.label : value).trim();
                            if (!value || seen.has(value)) return;
                            seen.add(value);
                            normalizedOptions.push({ id: value, label });
                        });

                        const normalizedSelectedValue = String(selectedValue || '').trim();
                        if (normalizedSelectedValue && !seen.has(normalizedSelectedValue)) {
                            normalizedOptions.push({ id: normalizedSelectedValue, label: normalizedSelectedValue });
                        }

                        return normalizedOptions;
                    }

                    async function fetchOptions(url) {
                        const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                        if (!response.ok) {
                            throw new Error('Falha ao carregar catalogo de veiculos.');
                        }
                        const payload = await response.json();
                        return Array.isArray(payload) ? payload : [];
                    }

                    async function fetchFuelOptions(url) {
                        const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                        if (!response.ok) {
                            throw new Error('Falha ao carregar catalogo de veiculos.');
                        }
                        const payload = await response.json();
                        if (Array.isArray(payload)) {
                            return { options: payload, warning: '' };
                        }
                        return {
                            options: Array.isArray(payload && payload.options) ? payload.options : [],
                            warning: String(payload && payload.warning ? payload.warning : '').trim(),
                        };
                    }

                    async function loadGuestModelOptions(brand, preserveModel = '', { silent = false } = {}) {
                        const modelInput = document.getElementById('id_guest_vehicle_model');
                        if (!modelInput) return;

                        if (!brand) {
                            setSearchableSelection(modelInput, '', '', [], { silent });
                            return;
                        }

                        const modelOptions = normalizeOptions(await fetchOptions(`/customer/vehicle-catalog/models/?brand=${encodeURIComponent(brand)}`), preserveModel);
                        setSearchableSelection(modelInput, preserveModel, preserveModel, modelOptions, { silent });
                    }

                    async function loadGuestFuelOptions(brand, model, preserveFuel = '', { silent = false } = {}) {
                        const fuelInput = document.getElementById('id_guest_vehicle_fuel');
                        if (!fuelInput) return;

                        if (!brand || !model) {
                            setSearchableSelection(fuelInput, '', '', allFuelChoices, { silent });
                            return;
                        }

                        let fuelOptions;
                        let fuelWarning = '';
                        try {
                            const fuelPayload = await fetchFuelOptions(`/customer/vehicle-catalog/fuels/?brand=${encodeURIComponent(brand)}&model=${encodeURIComponent(model)}`);
                            fuelOptions = normalizeOptions(fuelPayload.options, preserveFuel);
                            fuelWarning = fuelPayload.warning;
                        } catch (error) {
                            console.warn('Erro ao carregar combustiveis do catalogo, usando fallback:', error);
                            fuelOptions = allFuelChoices;
                        }

                        if (!fuelOptions.length) {
                            fuelOptions = allFuelChoices;
                        }

                        setSearchableSelection(fuelInput, preserveFuel, preserveFuel, fuelOptions, { silent });

                        if (fuelWarning) {
                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: { message: fuelWarning, type: 'warning' },
                            }));
                        }
                    }

                    function clearRegisteredVehicleDetails() {
                        setReadonlyFieldValue('id_registered_vehicle_plate_display', '');
                        setReadonlyFieldValue('id_registered_vehicle_brand_display', '');
                        setReadonlyFieldValue('id_registered_vehicle_model_display', '');
                        setReadonlyFieldValue('id_registered_vehicle_year_fabrication_display', '');
                        setReadonlyFieldValue('id_registered_vehicle_year_model_display', '');
                        setReadonlyFieldValue('id_registered_vehicle_engine_display', '');
                        setReadonlyFieldValue('id_registered_vehicle_fuel_display', '');
                    }

                    function applyRegisteredVehicleDetails(data) {
                        setReadonlyFieldValue('id_registered_vehicle_plate_display', data && data.plate ? data.plate : '');
                        setReadonlyFieldValue('id_registered_vehicle_brand_display', data && data.brand ? data.brand : '');
                        setReadonlyFieldValue('id_registered_vehicle_model_display', data && data.model ? data.model : '');
                        setReadonlyFieldValue('id_registered_vehicle_year_fabrication_display', data && data.year_fabrication ? data.year_fabrication : '');
                        setReadonlyFieldValue('id_registered_vehicle_year_model_display', data && data.year_model ? data.year_model : '');
                        setReadonlyFieldValue('id_registered_vehicle_engine_display', data && data.engine ? data.engine : '');
                        setReadonlyFieldValue('id_registered_vehicle_fuel_display', data && data.fuel ? data.fuel : '');
                    }

                    async function updateRegisteredVehicleDetails(vehicleId) {
                        if (!vehicleId) {
                            clearRegisteredVehicleDetails();
                            return;
                        }

                        try {
                            const response = await fetch(`/scheduling/get-vehicle-detail/?vehicle=${encodeURIComponent(vehicleId)}`);
                            if (!response.ok) {
                                clearRegisteredVehicleDetails();
                                return;
                            }

                            applyRegisteredVehicleDetails(await response.json());
                        } catch (error) {
                            console.warn('Erro ao carregar detalhes do veiculo:', error);
                            clearRegisteredVehicleDetails();
                        }
                    }

                    async function updateVehicleList(customerId, selectedVehicleId = null) {
                        const vehicleInput = document.querySelector('#id_vehicle');
                        if (!vehicleInput) return;

                        const vehicleContainer = vehicleInput.closest('[x-data]');
                        if (!vehicleContainer) return;

                        const vehicleData = getAlpineContext(vehicleContainer);
                        const optionsUl = vehicleContainer.querySelector('ul[role="listbox"]');
                        if (!vehicleData || !optionsUl) return;

                        vehicleData.clear();
                        optionsUl.querySelectorAll('li[data-value]').forEach(li => li.remove());

                            if (!customerId) {
                                return;
                            }

                        try {
                            const response = await fetch(`/scheduling/get-vehicles/?customer=${encodeURIComponent(customerId)}`);
                            if (!response.ok) {
                                return;
                            }
                            const vehicles = await response.json();

                            vehicles.forEach(v => {
                                const li = document.createElement('li');
                                li.className = 'relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white transition-colors group';
                                li.setAttribute('data-value', String(v.id));
                                li.setAttribute('data-label', v.label);
                                li.setAttribute('data-search-text', String(v.label).toLowerCase());
                                li.setAttribute('x-show', '!search || $el.dataset.searchText.includes(search.toLowerCase())');
                                li.innerHTML = `<span class="block truncate">${v.label}</span>`;
                                li.addEventListener('click', () => vehicleData.select(li));
                                optionsUl.appendChild(li);

                                if (selectedVehicleId && String(v.id) === String(selectedVehicleId)) {
                                    vehicleData.select(li);
                                    syncAppointmentContextFromInput('vehicle', String(v.id));
                                }
                            });

                            if (window.Alpine && Alpine.initTree) {
                                Alpine.initTree(optionsUl);
                            }
                        } catch (error) {
                            console.error('Erro ao carregar veiculos:', error);
                        }
                    }

                    async function updateRelatedSelectList({ inputSelector, url, selectedValue = null, emptyErrorMessage }) {
                        const hiddenInput = document.querySelector(inputSelector);
                        if (!hiddenInput) return;

                        if (!url) {
                            setSearchableSelection(hiddenInput, '', '', []);
                            return;
                        }

                        try {
                            const options = normalizeOptions(await fetchOptions(url), selectedValue || '');
                            const selectedOption = options.find((option) => String(option.id) === String(selectedValue || ''));
                            setSearchableSelection(
                                hiddenInput,
                                selectedValue || '',
                                selectedOption ? selectedOption.label : String(selectedValue || ''),
                                options,
                                { silent: true }
                            );
                        } catch (error) {
                            console.warn(emptyErrorMessage, error);
                            setSearchableSelection(hiddenInput, '', '', []);
                        }
                    }

                    async function updateBudgetList(vehicleId, selectedBudgetId = null) {
                        if (!vehicleId) {
                            setSearchableSelection(document.getElementById('id_budget'), '', '', []);
                            return;
                        }

                        await updateRelatedSelectList({
                            inputSelector: '#id_budget',
                            url: `/scheduling/get-budgets/?vehicle=${encodeURIComponent(vehicleId)}`,
                            selectedValue: selectedBudgetId,
                            emptyErrorMessage: 'Erro ao carregar orçamentos do veículo:',
                        });
                    }

                    async function updateWorkorderList(vehicleId, selectedWorkorderId = null) {
                        if (!vehicleId) {
                            setSearchableSelection(document.getElementById('id_workorder'), '', '', []);
                            return;
                        }

                        await updateRelatedSelectList({
                            inputSelector: '#id_workorder',
                            url: `/scheduling/get-workorders/?vehicle=${encodeURIComponent(vehicleId)}`,
                            selectedValue: selectedWorkorderId,
                            emptyErrorMessage: 'Erro ao carregar ordens de serviço do veículo:',
                        });
                    }

                    async function updateGuestVehicleFields(plateValue) {
                        const plate = String(plateValue || '').replace(/[^a-zA-Z0-9]/g, '').trim().toUpperCase();
                        const plateInput = document.getElementById('id_guest_vehicle_plate');
                        if (!plateInput || plate.length < 7) {
                            return;
                        }

                        try {
                            plateInput.classList.add('loading-api');

                            const response = await fetch(`/customer/check-plate/${encodeURIComponent(plate)}/`);
                            if (!response.ok) {
                                return;
                            }

                            const data = await response.json();
                            const brand = String(data.brand || '').trim();
                            const model = String(data.model || '').trim();
                            const fuel = String(data.fuel || '').trim();
                            const engine = String(data.engine || '').trim();

                            const brandInput = document.getElementById('id_guest_vehicle_brand');
                            const engineInput = document.getElementById('id_guest_vehicle_engine');
                            setSearchableSelection(brandInput, brand, brand, brand ? [{ id: brand, label: brand }] : [], { silent: true });

                            await loadGuestModelOptions(brand, model, { silent: true });
                            await loadGuestFuelOptions(brand, model, fuel, { silent: true });

                            var engineOptions = engine ? [{ id: engine, label: engine }] : allEngineChoices;
                            setSearchableSelection(engineInput, engine, engine, engineOptions, { silent: true });

                            setInputValue('id_guest_vehicle_year_fabrication', data.year_fabrication, { uppercase: false });
                            setInputValue('id_guest_vehicle_year_model', data.year_model, { uppercase: false });

                            var missingFields = [];
                            if (!data.engine) missingFields.push('Motorização');
                            if (!data.fuel) missingFields.push('Combustível');

                            if (missingFields.length) {
                                document.body.dispatchEvent(new CustomEvent('showToast', {
                                    detail: {
                                        message: 'Preencha manualmente: ' + missingFields.join(' e ') + '.',
                                        type: 'warning',
                                    },
                                }));
                            }
                        } catch (error) {
                            console.warn('Erro ao buscar placa do agendamento:', error);
                        } finally {
                            plateInput.classList.remove('loading-api');
                        }
                    }

                    function selectCustomerFromQuickForm(customer) {
                        if (!customer || !customer.id) return;
                        setRegisteredMode(true);

                        const customerInput = document.querySelector('#id_customer');
                        if (!customerInput) return;

                        const customerEl = customerInput.closest('[x-data]');
                        if (!customerEl) return;

                        const customerData = getAlpineContext(customerEl);
                        const optionsUl = customerEl.querySelector('ul[role="listbox"]');
                        if (!customerData || !optionsUl) return;

                        const customerId = String(customer.id);
                        const customerName = customer.name || 'Cliente';
                        let option = optionsUl.querySelector(`li[data-value='${customerId}']`);

                        if (!option) {
                            option = document.createElement('li');
                            option.className = 'relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white transition-colors group';
                            option.setAttribute('data-value', customerId);
                            option.setAttribute('data-label', customerName);
                            option.setAttribute('data-search-text', String(customerName).toLowerCase());
                            option.setAttribute('x-show', '!search || $el.dataset.searchText.includes(search.toLowerCase())');
                            option.innerHTML = `<span class="block truncate">${customerName}</span>`;
                            option.addEventListener('click', () => customerData.select(option));
                            optionsUl.appendChild(option);

                            if (window.Alpine && Alpine.initTree) {
                                Alpine.initTree(optionsUl);
                            }
                        }

                        customerData.select(option);
                        syncAppointmentContextFromInput('customer', customerId);
                            updateVehicleList(customer.id);
                            updateBudgetList('');
                            updateWorkorderList('');
                        }

                    if (!window.__appointmentCustomerSavedBound) {
                        window.__appointmentCustomerSavedBound = true;
                        document.body.addEventListener('customerSaved', function (evt) {
                            const quickFormModal = document.getElementById('quick_form_modal');
                            if (quickFormModal && quickFormModal.open) {
                                quickFormModal.close();
                            }

                            const customer = evt && evt.detail ? evt.detail : null;
                            selectCustomerFromQuickForm(customer);
                        });
                    }

                    if (!window.__appointmentVehicleSavedBound) {
                        window.__appointmentVehicleSavedBound = true;
                        document.body.addEventListener('vehicleSaved', function (evt) {
                            const quickFormModal = document.getElementById('quick_form_modal');
                            if (quickFormModal && quickFormModal.open) {
                                quickFormModal.close();
                            }

                            const vehicle = evt && evt.detail ? evt.detail : null;
                            if (!vehicle || !vehicle.id) return;

                            setRegisteredMode(true);

                            const customerInput = document.querySelector('#id_customer');
                            const customerId = customerInput && customerInput.value ? customerInput.value : (vehicle.customer_id || '');
                            if (!customerId) return;

                            syncAppointmentContextFromInput('customer', customerId);
                            updateVehicleList(customerId, vehicle.id);
                            updateBudgetList(vehicle.id);
                            updateWorkorderList(vehicle.id);
                        });
                    }

                    if (window.Alpine) {
                        queueMicrotask(() => {
                            const shell = document.querySelector('[data-appointment-form-shell]');
                            const shellData = getAlpineContext(shell);
                            if (!shellData || !shellData.vehicleId) {
                                return;
                            }

                            updateBudgetList(shellData.vehicleId, document.getElementById('id_budget') ? document.getElementById('id_budget').value : '');
                            updateWorkorderList(shellData.vehicleId, document.getElementById('id_workorder') ? document.getElementById('id_workorder').value : '');
                        });
                    }
                </script>
                """
            ),
            Div(
                HTML('<div class="col-span-12 mb-1 mt-1 text-sm font-semibold uppercase tracking-wide text-base-content/70">Cliente e Veiculo</div>'),
                Field("title", wrapper_class="col-span-12"),
                Div(
                    HTML('<label for="id_is_customer_registered" class="mb-0 text-sm font-semibold text-base-content">Cliente cadastrado</label>'),
                    HTML(
                        """
                        <input
                            type="checkbox"
                            name="is_customer_registered"
                            id="id_is_customer_registered"
                            class="toggle toggle-primary"
                            {% if form.is_customer_registered.value %}checked{% endif %}
                        >
                        {% if form.is_customer_registered.errors %}
                            <span class="text-sm text-error">{{ form.is_customer_registered.errors|join:', ' }}</span>
                        {% endif %}
                        """
                    ),
                    css_class="col-span-12 flex items-center justify-between gap-3",
                ),
                Div(
                    Field("guest_customer_name", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("guest_customer_phone", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("guest_customer_cpf", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("guest_vehicle_plate", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("guest_vehicle_brand", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("guest_vehicle_model", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("guest_vehicle_year_fabrication", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("guest_vehicle_year_model", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("guest_vehicle_engine", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("guest_vehicle_fuel", wrapper_class="col-span-12 lg:col-span-3"),
                    x_show="!isCustomerRegistered",
                    css_class="col-span-12 grid grid-cols-12 gap-4",
                ),
                Div(
                    Field("customer", wrapper_class="flex-1 mb-0"),
                    HTML(
                        """
                        <button
                            type="button"
                            class="btn btn-circle mb-2"
                            :class="customerId ? 'btn-warning' : 'btn-primary'"
                            @click="const url = customerId ? `/customer/quick-update/${customerId}/` : '/customer/quick-create/'; htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'}); document.getElementById('quick_form_modal').showModal();"
                        >
                            <span class="material-icons" x-text="customerId ? 'edit' : 'person_add'"></span>
                        </button>
                        """
                    ),
                    x_show="isCustomerRegistered",
                    css_class="col-span-12 flex items-end gap-2",
                ),
                Div(
                    Field("vehicle", wrapper_class="flex-1 mb-0"),
                    HTML(
                        """
                        <button
                            type="button"
                            class="btn btn-circle mb-2"
                            :class="!customerId ? 'btn-disabled opacity-50' : (vehicleId ? 'btn-warning' : 'btn-primary')"
                            :disabled="!customerId"
                            @click="const url = vehicleId ? `/customer/vehicle/quick-update/${vehicleId}/` : `/customer/vehicle/quick-create/?customer_id=${customerId}`; htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'}); document.getElementById('quick_form_modal').showModal();"
                        >
                            <span class="material-icons" x-text="vehicleId ? 'edit' : 'directions_car_filled'"></span>
                        </button>
                        """
                    ),
                    x_show="isCustomerRegistered",
                    css_class="col-span-12 flex items-end gap-2",
                ),
                HTML(
                    f"""
                    <div x-show="isCustomerRegistered && vehicleId" class="col-span-12 grid grid-cols-12 gap-4 rounded-xl border border-base-300 bg-base-200/20 p-4">
                        <div class="col-span-12 mb-1 text-sm font-semibold uppercase tracking-wide text-base-content/70">Dados do Veiculo Selecionado</div>
                        {registered_vehicle_fields_html}
                    </div>
                    """
                ),
                HTML('<div class="col-span-12 mb-1 mt-2 text-sm font-semibold uppercase tracking-wide text-base-content/70">Horario e Status</div>'),
                Field("starts_at", wrapper_class="col-span-12 lg:col-span-6"),
                Field("ends_at", wrapper_class="col-span-12 lg:col-span-6"),
                Field(
                    "alert_customer",
                    wrapper_class="col-span-12 lg:col-span-6",
                    **{"@change": "alertCustomer = !!$event.target.checked"},
                ),
                Field("status", wrapper_class="col-span-12 lg:col-span-6"),
                Div(
                    HTML(
                        """
                        <div class="mb-3">
                            <span class="block text-sm font-semibold text-base-content">Antecedência do alerta</span>
                            <p class="mt-0.5 text-xs text-base-content/60">Escolha um ou mais horários antes do agendamento para avisar o cliente.</p>
                        </div>
                        """
                    ),
                    Field("alert_lead_times", wrapper_class="mb-0"),
                    css_class="col-span-12 rounded-box border border-base-300 bg-base-200/30 p-4",
                    **{"x-show": "alertCustomer", "x-cloak": True},
                ),
                HTML('<div class="col-span-12 mb-1 mt-2 text-sm font-semibold uppercase tracking-wide text-base-content/70">Vinculos</div>'),
                Field("budget", wrapper_class="col-span-12 lg:col-span-6"),
                Field("workorder", wrapper_class="col-span-12 lg:col-span-6"),
                HTML('<div class="col-span-12 mb-1 mt-2 text-sm font-semibold uppercase tracking-wide text-base-content/70">Observacoes</div>'),
                Field("notes", wrapper_class="col-span-12"),
                x_data=customer_vehicle_x_data,
                data_appointment_form_shell="1",
                **{
                    "@change": """
                        if ($event.target && $event.target.name === 'is_customer_registered') {
                            isCustomerRegistered = !!$event.target.checked;
                            if (!isCustomerRegistered) {
                                customerId = '';
                                vehicleId = '';
                                updateVehicleList('');
                                updateBudgetList('');
                                updateWorkorderList('');
                                clearRegisteredVehicleDetails();
                            }
                        } else if ($event.target && $event.target.name === 'customer') {
                            customerId = $event.target.value || '';
                            vehicleId = '';
                            updateVehicleList(customerId);
                            updateBudgetList('');
                            updateWorkorderList('');
                            clearRegisteredVehicleDetails();
                        } else if ($event.target && $event.target.name === 'vehicle') {
                            vehicleId = $event.target.value || '';
                            updateBudgetList(vehicleId);
                            updateWorkorderList(vehicleId);
                            if (isCustomerRegistered) {
                                updateRegisteredVehicleDetails(vehicleId);
                            }
                        } else if ($event.target && $event.target.name === 'guest_vehicle_plate' && !isCustomerRegistered) {
                            updateGuestVehicleFields($event.target.value || '');
                        } else if ($event.target && $event.target.name === 'guest_vehicle_brand' && !isCustomerRegistered) {
                            const selectedBrand = $event.target.value || '';
                            loadGuestModelOptions(selectedBrand).catch((error) => {
                                console.warn('Erro ao carregar modelos de veiculo:', error);
                            });
                            loadGuestFuelOptions(selectedBrand, '').catch((error) => {
                                console.warn('Erro ao carregar combustiveis do veiculo:', error);
                            });
                        } else if ($event.target && $event.target.name === 'guest_vehicle_model' && !isCustomerRegistered) {
                            const selectedBrand = (document.getElementById('id_guest_vehicle_brand') || {}).value || '';
                            const selectedModel = $event.target.value || '';
                            loadGuestFuelOptions(selectedBrand, selectedModel).catch((error) => {
                                console.warn('Erro ao carregar combustiveis do veiculo:', error);
                            });
                        }
                    """,
                },
                css_class="grid grid-cols-12 gap-4",
            ),
        )

    def clean_guest_vehicle_engine(self) -> str:
        guest_vehicle_engine = self.cleaned_data.get("guest_vehicle_engine")
        normalized_guest_vehicle_engine = normalize_vehicle_engine_choice(guest_vehicle_engine)
        if guest_vehicle_engine and not normalized_guest_vehicle_engine:
            self.instance._skip_guest_vehicle_engine_required_validation = True
            raise forms.ValidationError("Selecione um motor válido.")
        self.instance._skip_guest_vehicle_engine_required_validation = False
        return normalized_guest_vehicle_engine

    def clean_guest_vehicle_fuel(self) -> str:
        guest_vehicle_fuel = self.cleaned_data.get("guest_vehicle_fuel")
        return normalize_vehicle_fuel_choice(guest_vehicle_fuel)

    def clean_title(self):
        value = self.cleaned_data.get("title")
        return sentence_case(value) if value else value

    def clean_notes(self):
        value = self.cleaned_data.get("notes")
        return sentence_case(value) if value else value

    def clean_guest_customer_name(self):
        value = str(self.cleaned_data.get("guest_customer_name") or "")
        return name_case(value) if value else value

    def clean_guest_vehicle_brand(self):
        value = str(self.cleaned_data.get("guest_vehicle_brand") or "")
        return sentence_case(value) if value else value

    def clean_guest_vehicle_model(self):
        value = str(self.cleaned_data.get("guest_vehicle_model") or "")
        return sentence_case(value) if value else value

    def clean_guest_vehicle_plate(self):
        value = str(self.cleaned_data.get("guest_vehicle_plate") or "")
        return plate_case(value) if value else value

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}

        customer_raw = cleaned_data.get("customer")
        vehicle_raw = cleaned_data.get("vehicle")
        customer = customer_raw if isinstance(customer_raw, Customer) else None
        vehicle = vehicle_raw if isinstance(vehicle_raw, Vehicle) else None
        is_customer_registered = bool(cleaned_data.get("is_customer_registered"))
        guest_customer_name = name_case(str(cleaned_data.get("guest_customer_name") or ""))
        guest_customer_cpf = _digits_only(cleaned_data.get("guest_customer_cpf"))[:11]
        guest_customer_phone = str(cleaned_data.get("guest_customer_phone") or "").strip()
        guest_vehicle_plate = plate_case(str(cleaned_data.get("guest_vehicle_plate") or ""))
        guest_vehicle_brand = sentence_case(str(cleaned_data.get("guest_vehicle_brand") or ""))
        guest_vehicle_model = sentence_case(str(cleaned_data.get("guest_vehicle_model") or ""))
        guest_vehicle_year_fabrication = str(cleaned_data.get("guest_vehicle_year_fabrication") or "").strip()
        guest_vehicle_year_model = str(cleaned_data.get("guest_vehicle_year_model") or "").strip()
        guest_vehicle_engine = normalize_vehicle_engine_choice(cleaned_data.get("guest_vehicle_engine"))
        guest_vehicle_fuel = normalize_vehicle_fuel_choice(cleaned_data.get("guest_vehicle_fuel"))

        cleaned_data["guest_customer_name"] = guest_customer_name
        cleaned_data["guest_customer_cpf"] = guest_customer_cpf
        cleaned_data["guest_customer_phone"] = guest_customer_phone
        cleaned_data["guest_vehicle_plate"] = guest_vehicle_plate
        cleaned_data["guest_vehicle_brand"] = guest_vehicle_brand
        cleaned_data["guest_vehicle_model"] = guest_vehicle_model
        cleaned_data["guest_vehicle_year_fabrication"] = guest_vehicle_year_fabrication
        cleaned_data["guest_vehicle_year_model"] = guest_vehicle_year_model
        cleaned_data["guest_vehicle_engine"] = guest_vehicle_engine
        cleaned_data["guest_vehicle_fuel"] = guest_vehicle_fuel

        guest_field_names = [
            "guest_customer_name",
            "guest_customer_cpf",
            "guest_customer_phone",
            "guest_vehicle_plate",
            "guest_vehicle_brand",
            "guest_vehicle_model",
            "guest_vehicle_year_fabrication",
            "guest_vehicle_year_model",
            "guest_vehicle_engine",
            "guest_vehicle_fuel",
        ]
        if is_customer_registered:
            for field_name in guest_field_names:
                self.errors.pop(field_name, None)
                cleaned_data[field_name] = ""
        else:
            self.errors.pop("customer", None)
            if guest_customer_cpf and not is_valid_cpf(guest_customer_cpf):
                self.add_error("guest_customer_cpf", "Informe um CPF valido.")
            self.instance._guest_validation_done = True
            cleaned_data["customer"] = None
            cleaned_data["vehicle"] = None
            cleaned_data["budget"] = None
            cleaned_data["workorder"] = None

        if customer and vehicle and getattr(vehicle, "customer_id", None) != getattr(customer, "pk", None):
            self.add_error("vehicle", "O veiculo deve pertencer ao cliente selecionado.")

        if vehicle and customer is None:
            self.add_error("vehicle", "Selecione um cliente cadastrado para vincular um veiculo.")

        alert_customer = bool(cleaned_data.get("alert_customer"))
        alert_lead_times = cleaned_data.get("alert_lead_times") or []
        if alert_customer and not alert_lead_times:
            self.add_error("alert_lead_times", "Selecione ao menos uma antecedência do alerta.")
        if not alert_customer:
            cleaned_data["alert_lead_times"] = []
        else:
            cleaned_data["alert_lead_times"] = [int(value) for value in alert_lead_times]

        return cleaned_data

    def save(self, commit: bool = True) -> Appointment:
        self.instance.workshop = self.workshop
        if self.cleaned_data.get("is_customer_registered"):
            self.instance.guest_customer_name = ""
            self.instance.guest_customer_cpf = ""
            self.instance.guest_customer_phone = ""
            self.instance.guest_vehicle_plate = ""
            self.instance.guest_vehicle_brand = ""
            self.instance.guest_vehicle_model = ""
            self.instance.guest_vehicle_year_fabrication = ""
            self.instance.guest_vehicle_year_model = ""
            self.instance.guest_vehicle_engine = ""
            self.instance.guest_vehicle_fuel = ""
        else:
            self.instance.customer = None
            self.instance.vehicle = None
            self.instance.budget = None
            self.instance.workorder = None
        appointment = super().save(commit=commit)
        if commit:
            sync_appointment_alert_schedule(appointment)
        return appointment


class AppointmentCalendarFilterForm(CoreForm):
    date_from = forms.DateField(
        required=False,
        label="Data Início",
        widget=forms.DateInput(attrs={"type": "date", "class": "input-theme", "id": "appointment-filter-date-from"}),
    )
    date_to = forms.DateField(
        required=False,
        label="Data Fim",
        widget=forms.DateInput(attrs={"type": "date", "class": "input-theme", "id": "appointment-filter-date-to"}),
    )
    customer = forms.ModelChoiceField(
        required=False,
        label="Cliente",
        queryset=Customer.objects.none(),
        widget=SearchableSelectInput(attrs={"id": "appointment-filter-customer"}),
    )
    vehicle = forms.ModelChoiceField(
        required=False,
        label="Veiculo",
        queryset=Vehicle.objects.none(),
        widget=SearchableSelectInput(attrs={"id": "appointment-filter-vehicle"}),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "Todos"), *AppointmentStatus.choices],
        widget=forms.Select(attrs={"class": "select select-bordered w-full", "id": "appointment-filter-status"}),
    )

    def __init__(self, *args: Any, workshop: Workshop | None = None, **kwargs: Any):
        self.workshop = workshop
        super().__init__(*args, **kwargs)

        customer_field = self.fields["customer"]
        vehicle_field = self.fields["vehicle"]

        if not isinstance(customer_field, forms.ModelChoiceField) or not isinstance(vehicle_field, forms.ModelChoiceField):
            raise TypeError("Campos de cliente/veiculo invalidos no AppointmentCalendarFilterForm")

        customer_field.queryset = _selected_instance_queryset(
            model=Customer,
            selected_id=(self.data.get("customer") if self.is_bound else self.initial.get("customer")),
            workshop=self.workshop,
        )

        vehicle_field.widget.attrs.update({":disabled": "!customerId"})

        selected_customer_id = ""
        if self.is_bound:
            selected_customer_id = (self.data.get("customer") or "").strip()
        elif self.initial.get("customer"):
            selected_customer_id = str(self.initial.get("customer"))

        if selected_customer_id and self.workshop:
            vehicle_field.queryset = Vehicle.objects.filter(workshop=self.workshop, customer_id=selected_customer_id).order_by("plate")
        else:
            vehicle_field.queryset = Vehicle.objects.none()

        customer_field.widget = SearchableSelectInput(choices=tuple(customer_field.choices), attrs={"id": "appointment-filter-customer", "data-source-url": reverse("scheduling:get_customers")})
        vehicle_field.widget = SearchableSelectInput(choices=tuple(vehicle_field.choices), attrs={"id": "appointment-filter-vehicle"})


class AppointmentMoveForm(CoreForm):
    starts_at = forms.DateTimeField()
    ends_at = forms.DateTimeField()

    def __init__(self, *args: Any, instance: Appointment, **kwargs: Any):
        self.instance = instance
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")

        if not starts_at or not ends_at:
            return cleaned_data

        self.instance.starts_at = starts_at
        self.instance.ends_at = ends_at

        try:
            self.instance.clean()
        except forms.ValidationError as exc:
            messages: list[str] = []
            if hasattr(exc, "message_dict"):
                for field_messages in exc.message_dict.values():
                    messages.extend(str(message) for message in field_messages)
            elif hasattr(exc, "messages"):
                messages.extend(str(message) for message in exc.messages)
            else:
                messages.append(str(exc))

            raise forms.ValidationError(" ".join(messages) or "Nao foi possivel validar a movimentacao do agendamento.")

        return cleaned_data


def build_budget_create_url(*, customer_id: int | None = None, vehicle_id: int | None = None, appointment_id: int | None = None) -> str:
    params: list[str] = []
    if customer_id:
        params.append(f"customer={customer_id}")
    if vehicle_id:
        params.append(f"vehicle={vehicle_id}")
    if appointment_id:
        params.append(f"appointment_id={appointment_id}")

    base_url = reverse("budget:budget_create")
    if not params:
        return base_url
    return f"{base_url}?{'&'.join(params)}"
