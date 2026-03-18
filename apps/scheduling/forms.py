from __future__ import annotations

import json
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import Budget
from apps.core.widgets import CheckboxInput, SearchableSelectInput, SelectInput, TextInput, TextareaInput
from apps.customer.models import Customer, Vehicle
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


class AppointmentForm(forms.ModelForm):
    customer = forms.ModelChoiceField(label="Cliente", queryset=Customer.objects.none(), widget=SearchableSelectInput())
    vehicle = forms.ModelChoiceField(label="Veiculo", queryset=Vehicle.objects.none(), widget=SearchableSelectInput(), required=False)
    budget = forms.ModelChoiceField(label="Orcamento vinculado", queryset=Budget.objects.none(), widget=SearchableSelectInput(), required=False)
    workorder = forms.ModelChoiceField(label="Ordem de servico vinculada", queryset=WorkOrder.objects.none(), widget=SearchableSelectInput(), required=False)

    class Meta:
        model = Appointment
        fields = ["title", "customer", "vehicle", "starts_at", "ends_at", "block_color", "alert_customer", "status", "budget", "workorder", "notes"]
        widgets = {
            "title": TextInput(),
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

        selected_customer_id = ""
        selected_vehicle_id = ""
        if self.is_bound:
            selected_customer_id = (self.data.get("customer") or "").strip()
            selected_vehicle_id = (self.data.get("vehicle") or "").strip()
        elif self.instance and self.instance.pk:
            selected_customer_id = str(self.instance.customer_id)
            selected_vehicle_id = str(self.instance.vehicle_id)

        if not selected_customer_id and self.initial.get("customer"):
            selected_customer_id = str(self.initial.get("customer"))

        if not selected_vehicle_id and self.initial.get("vehicle"):
            selected_vehicle_id = str(self.initial.get("vehicle"))

        if selected_customer_id and self.workshop:
            vehicle_field.queryset = Vehicle.objects.filter(workshop=self.workshop, customer_id=selected_customer_id).order_by("plate")
        else:
            vehicle_field.queryset = Vehicle.objects.none()

        if self.instance and self.instance.pk:
            if self.instance.starts_at:
                self.initial["starts_at"] = timezone.localtime(self.instance.starts_at).strftime("%Y-%m-%dT%H:%M")
            if self.instance.ends_at:
                self.initial["ends_at"] = timezone.localtime(self.instance.ends_at).strftime("%Y-%m-%dT%H:%M")

        self.helper = FormHelper()
        self.helper.form_tag = False

        customer_vehicle_x_data = json.dumps({"customerId": selected_customer_id, "vehicleId": selected_vehicle_id})

        self.helper.layout = Layout(
            HTML(
                r"""
                <script>
                    function syncAppointmentContextFromInput(name, value) {
                        const shell = document.querySelector('[data-appointment-form-shell]');
                        if (!shell || !shell.__x) return;
                        const data = Alpine.$data(shell);
                        if (!data) return;

                        if (name === 'customer') {
                            data.customerId = value || '';
                            data.vehicleId = '';
                        }

                        if (name === 'vehicle') {
                            data.vehicleId = value || '';
                        }
                    }

                    async function updateVehicleList(customerId, selectedVehicleId = null) {
                        const vehicleInput = document.querySelector('#id_vehicle');
                        if (!vehicleInput) return;

                        const vehicleContainer = vehicleInput.closest('[x-data]');
                        if (!vehicleContainer) return;

                        const vehicleData = Alpine.$data(vehicleContainer);
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
                                li.setAttribute('x-show', `!search || '${v.label.replace(/'/g, "\\'")}'.toLowerCase().includes(search.toLowerCase())`);
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

                    function selectCustomerFromQuickForm(customer) {
                        if (!customer || !customer.id) return;
                        const customerInput = document.querySelector('#id_customer');
                        if (!customerInput) return;

                        const customerEl = customerInput.closest('[x-data]');
                        const customerData = Alpine.$data(customerEl);
                        const optionsUl = customerEl.querySelector('ul[role="listbox"]');

                        const customerId = String(customer.id);
                        const customerName = customer.name || 'Cliente';
                        let option = optionsUl.querySelector(`li[data-value='${customerId}']`);

                        if (!option) {
                            option = document.createElement('li');
                            option.className = 'relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white transition-colors group';
                            option.setAttribute('data-value', customerId);
                            option.setAttribute('data-label', customerName);
                            option.setAttribute('x-show', `!search || '${customerName.replace(/'/g, "\\'")}'.toLowerCase().includes(search.toLowerCase())`);
                            option.innerHTML = `<span class="block truncate">${customerName}</span>`;
                            option.addEventListener('click', () => customerData.select(option));
                            optionsUl.appendChild(option);
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
                    css_class="col-span-12 flex items-end gap-2",
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
                        if ($event.target && $event.target.name === 'customer') {
                            customerId = $event.target.value || '';
                            vehicleId = '';
                            updateVehicleList(customerId);
                        } else if ($event.target && $event.target.name === 'vehicle') {
                            vehicleId = $event.target.value || '';
                        }
                    """,
                },
                css_class="grid grid-cols-12 gap-4",
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}

        customer = cleaned_data.get("customer")
        vehicle = cleaned_data.get("vehicle")
        if customer and vehicle and vehicle.customer_id != customer.id:
            self.add_error("vehicle", "O veiculo deve pertencer ao cliente selecionado.")

        return cleaned_data

    def save(self, commit: bool = True):
        self.instance.workshop = self.workshop
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


def build_budget_create_url(*, customer_id: int, vehicle_id: int) -> str:
    return f"{reverse('budget:budget_create')}?customer={customer_id}&vehicle={vehicle_id}"
