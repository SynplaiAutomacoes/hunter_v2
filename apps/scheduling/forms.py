from __future__ import annotations

import json
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone

from apps.budget.models import Budget
from apps.core.widgets import CPForCNPJInput, CheckboxInput, PhoneInput, PlateInput, SearchableSelectInput, SelectInput, TextInput, TextareaInput
from apps.customer.cpf_cnpj_validator import is_valid_cpf
from apps.customer.vehicle_engine import normalize_vehicle_engine_choice, vehicle_engine_form_choices
from apps.customer.models import Customer, Vehicle
from apps.customer.vehicle_fuel import normalize_vehicle_fuel_choice, vehicle_fuel_form_choices
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


def _uppercase_text_input() -> TextInput:
    return TextInput(attrs={"oninput": "this.value = this.value.toUpperCase()", "autocapitalize": "characters"})


def _year_text_input() -> TextInput:
    return TextInput(attrs={"inputmode": "numeric", "maxlength": "4"})


def _normalize_upper_text(value: object) -> str:
    return str(value or "").strip().upper()


def _digits_only(value: object) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


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


class AppointmentForm(forms.ModelForm):
    is_customer_registered = forms.BooleanField(label="Cliente cadastrado", required=False, initial=True, widget=CheckboxInput())
    customer = forms.ModelChoiceField(label="Cliente", queryset=Customer.objects.none(), widget=SearchableSelectInput(), required=False)
    vehicle = forms.ModelChoiceField(label="Veiculo", queryset=Vehicle.objects.none(), widget=SearchableSelectInput(), required=False)
    guest_customer_name = forms.CharField(label="Nome", required=False, widget=_uppercase_text_input())
    guest_customer_cpf = forms.CharField(label="CPF", required=False, widget=CPForCNPJInput(mode="cpf"))
    guest_customer_phone = forms.CharField(label="Telefone", required=False, widget=PhoneInput())
    guest_vehicle_plate = forms.CharField(label="Placa", required=False, widget=PlateInput())
    guest_vehicle_brand = forms.CharField(label="Marca", required=False, widget=_uppercase_text_input())
    guest_vehicle_model = forms.CharField(label="Modelo", required=False, widget=_uppercase_text_input())
    guest_vehicle_year_fabrication = forms.CharField(label="Ano Fabricacao", required=False, widget=_year_text_input())
    guest_vehicle_year_model = forms.CharField(label="Ano Modelo", required=False, widget=_year_text_input())
    guest_vehicle_engine = forms.CharField(label="Motorizacao", required=False, widget=SelectInput(choices=vehicle_engine_form_choices()))
    guest_vehicle_fuel = forms.CharField(label="Combustivel", required=False, widget=SelectInput(choices=vehicle_fuel_form_choices()))
    budget = forms.ModelChoiceField(label="Orcamento vinculado", queryset=Budget.objects.none(), widget=SearchableSelectInput(), required=False)
    workorder = forms.ModelChoiceField(label="Ordem de servico vinculada", queryset=WorkOrder.objects.none(), widget=SearchableSelectInput(), required=False)

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
            "guest_vehicle_brand": _uppercase_text_input(),
            "guest_vehicle_model": _uppercase_text_input(),
            "guest_vehicle_year_fabrication": _year_text_input(),
            "guest_vehicle_year_model": _year_text_input(),
            "guest_vehicle_engine": SelectInput(choices=vehicle_engine_form_choices()),
            "guest_vehicle_fuel": SelectInput(choices=vehicle_fuel_form_choices()),
            "starts_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "input-theme h-12"}),
            "ends_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "input-theme h-12"}),
            "block_color": forms.HiddenInput(),
            "alert_customer": CheckboxInput(),
            "status": SelectInput(attrs={"class": "h-12"}),
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
            budget_field.queryset = Budget.objects.filter(workshop=self.workshop).select_related("customer", "vehicle").order_by("-criado_em")
            workorder_field.queryset = WorkOrder.objects.filter(workshop=self.workshop).select_related("budget", "budget__customer", "budget__vehicle").order_by("-criado_em")

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

        if is_customer_registered and selected_customer_id and self.workshop:
            vehicle_field.queryset = Vehicle.objects.filter(workshop=self.workshop, customer_id=selected_customer_id).order_by("plate")
        else:
            vehicle_field.queryset = Vehicle.objects.none()

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

        if self.instance and self.instance.pk:
            if self.instance.starts_at:
                self.initial["starts_at"] = timezone.localtime(self.instance.starts_at).strftime("%Y-%m-%dT%H:%M")
            if self.instance.ends_at:
                self.initial["ends_at"] = timezone.localtime(self.instance.ends_at).strftime("%Y-%m-%dT%H:%M")

        self.helper = FormHelper()
        self.helper.form_tag = False

        customer_vehicle_x_data = json.dumps({"customerId": selected_customer_id, "vehicleId": selected_vehicle_id, "isCustomerRegistered": is_customer_registered})
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
                        input.value = normalizedValue;

                        const widgetContainer = input.closest('[x-data]');
                        if (widgetContainer && window.Alpine) {
                            try {
                                const widgetData = Alpine.$data(widgetContainer);
                                if (widgetData && Object.prototype.hasOwnProperty.call(widgetData, 'value')) {
                                    widgetData.value = normalizedValue;
                                    if (typeof widgetData.updateLabelFromValue === 'function') {
                                        widgetData.updateLabelFromValue();
                                    }
                                }
                            } catch (syncError) {
                                console.warn('Erro ao sincronizar campo com select customizado:', syncError);
                            }
                        }

                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    function setReadonlyFieldValue(inputId, value) {
                        const input = document.getElementById(inputId);
                        if (!input) return;
                        input.value = value === null || value === undefined ? '' : String(value);
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
                            const fieldsMap = {
                                id_guest_vehicle_brand: data.brand,
                                id_guest_vehicle_model: data.model,
                                id_guest_vehicle_year_fabrication: data.year_fabrication,
                                id_guest_vehicle_year_model: data.year_model,
                                id_guest_vehicle_engine: data.engine,
                                id_guest_vehicle_fuel: data.fuel,
                            };

                            Object.entries(fieldsMap).forEach(([inputId, value]) => {
                                setInputValue(inputId, value, { uppercase: !['id_guest_vehicle_year_fabrication', 'id_guest_vehicle_year_model', 'id_guest_vehicle_engine', 'id_guest_vehicle_fuel'].includes(inputId) });
                            });
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
                Field("alert_customer", wrapper_class="col-span-12 lg:col-span-6"),
                Field("status", wrapper_class="col-span-12 lg:col-span-6"),
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
                                clearRegisteredVehicleDetails();
                            }
                        } else if ($event.target && $event.target.name === 'customer') {
                            customerId = $event.target.value || '';
                            vehicleId = '';
                            updateVehicleList(customerId);
                            clearRegisteredVehicleDetails();
                        } else if ($event.target && $event.target.name === 'vehicle') {
                            vehicleId = $event.target.value || '';
                            if (isCustomerRegistered) {
                                updateRegisteredVehicleDetails(vehicleId);
                            }
                        } else if ($event.target && $event.target.name === 'guest_vehicle_plate' && !isCustomerRegistered) {
                            updateGuestVehicleFields($event.target.value || '');
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

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}

        customer = cleaned_data.get("customer")
        vehicle = cleaned_data.get("vehicle")
        is_customer_registered = bool(cleaned_data.get("is_customer_registered"))
        guest_customer_name = _normalize_upper_text(cleaned_data.get("guest_customer_name"))
        guest_customer_cpf = _digits_only(cleaned_data.get("guest_customer_cpf"))[:11]
        guest_customer_phone = (cleaned_data.get("guest_customer_phone") or "").strip()
        guest_vehicle_plate = _normalize_upper_text(cleaned_data.get("guest_vehicle_plate"))
        guest_vehicle_brand = _normalize_upper_text(cleaned_data.get("guest_vehicle_brand"))
        guest_vehicle_model = _normalize_upper_text(cleaned_data.get("guest_vehicle_model"))
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

        if is_customer_registered:
            if customer is None:
                self.add_error("customer", "Selecione um cliente cadastrado para continuar.")
            cleaned_data["guest_customer_name"] = ""
            cleaned_data["guest_customer_cpf"] = ""
            cleaned_data["guest_customer_phone"] = ""
            cleaned_data["guest_vehicle_plate"] = ""
            cleaned_data["guest_vehicle_brand"] = ""
            cleaned_data["guest_vehicle_model"] = ""
            cleaned_data["guest_vehicle_year_fabrication"] = ""
            cleaned_data["guest_vehicle_year_model"] = ""
            cleaned_data["guest_vehicle_engine"] = ""
            cleaned_data["guest_vehicle_fuel"] = ""
        else:
            if not guest_customer_name:
                self.add_error("guest_customer_name", "Informe o nome do cliente.")
            if not guest_customer_cpf:
                self.add_error("guest_customer_cpf", "Informe o CPF do cliente.")
            elif not is_valid_cpf(guest_customer_cpf):
                self.add_error("guest_customer_cpf", "Informe um CPF valido.")
            if not guest_customer_phone:
                self.add_error("guest_customer_phone", "Informe o telefone do cliente.")
            if not guest_vehicle_plate:
                self.add_error("guest_vehicle_plate", "Informe a placa do veiculo.")
            if not guest_vehicle_brand:
                self.add_error("guest_vehicle_brand", "Informe a marca do veiculo.")
            if not guest_vehicle_model:
                self.add_error("guest_vehicle_model", "Informe o modelo do veiculo.")
            if not guest_vehicle_year_fabrication:
                self.add_error("guest_vehicle_year_fabrication", "Informe o ano de fabricacao.")
            if not guest_vehicle_year_model:
                self.add_error("guest_vehicle_year_model", "Informe o ano do modelo.")
            if not guest_vehicle_engine and "guest_vehicle_engine" not in self.errors:
                self.add_error("guest_vehicle_engine", "Informe a motorizacao.")
            cleaned_data["customer"] = None
            cleaned_data["vehicle"] = None
            cleaned_data["budget"] = None
            cleaned_data["workorder"] = None

        if customer and vehicle and vehicle.customer_id != customer.id:
            self.add_error("vehicle", "O veiculo deve pertencer ao cliente selecionado.")

        if vehicle and customer is None:
            self.add_error("vehicle", "Selecione um cliente cadastrado para vincular um veiculo.")

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
        return super().save(commit=commit)


class AppointmentCalendarFilterForm(forms.Form):
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

        if self.workshop:
            customer_field.queryset = Customer.objects.filter(workshop=self.workshop, is_active=True).order_by("name")

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


class AppointmentMoveForm(forms.Form):
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
