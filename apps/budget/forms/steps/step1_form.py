# ruff: noqa: F403,F405
from .base import BudgetStepBaseForm
from .common import *


class BudgetStep1Form(BudgetStepBaseForm):
    workshop = forms.CharField(label="Empresa", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    cost_estimator = forms.CharField(label="Orçamentista", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    vehicle = forms.ModelChoiceField(label="Veículo", queryset=Vehicle.objects.none(), required=False, widget=SearchableSelectInput())

    class Meta:
        model = Budget
        fields = ["workshop", "cost_estimator", "entry_date", "budget_type", "customer", "vehicle", "current_km", "fuel_level"]
        widgets = {
            "entry_date": CalendarDateInput(),
            "budget_type": SearchableSelectInput(),
            "customer": SearchableSelectInput(attrs={"x-model": "customerId", "@change": "customerId = $el.value; vehicleId = '';"}),
            "current_km": NumberInput(),
            "fuel_level": SearchableSelectInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        customer_field = cast(forms.ModelChoiceField, self.fields["customer"])
        vehicle_field = cast(forms.ModelChoiceField, self.fields["vehicle"])

        customer_field.widget.attrs.update(
            {
                "hx-get": reverse_lazy("budget:customer-detail"),
                "hx-trigger": "change",
                "hx-target": "#resumo-cliente",
            }
        )

        vehicle_field.widget.attrs.update(
            {
                "id": "id_vehicle",
                ":disabled": "!customerId",
                "hx-get": reverse_lazy("budget:vehicle-detail"),
                "hx-trigger": "change",
                "hx-target": "#resumo-veiculo",
                "hx-include": "[name='customer']",
            }
        )

        vehicle_field.widget.attrs.update({"id": "id_vehicle"})
        self.fields["fuel_level"].required = False
        self.fields["current_km"].error_messages["required"] = "Preencha o KM atual para continuar."

        selected_customer_id = ""
        selected_vehicle_id = ""
        selected_customer = None
        selected_vehicle = None

        # Preenchimento inicial
        if self.workshop:
            workshop_name = self.workshop.name
            self.fields["workshop"].initial = workshop_name
            self.initial["workshop"] = workshop_name
            customer_field.queryset = Customer.objects.filter(workshop=self.workshop).order_by("name")

            if not self.is_bound and (not self.instance or not self.instance.pk):
                requested_customer_id = (self.request.GET.get("customer") if self.request else "") or ""
                requested_vehicle_id = (self.request.GET.get("vehicle") if self.request else "") or ""

                requested_customer = Customer.objects.filter(workshop=self.workshop, pk=requested_customer_id).first() if requested_customer_id else None
                requested_vehicle = Vehicle.objects.filter(workshop=self.workshop, pk=requested_vehicle_id).first() if requested_vehicle_id else None

                if requested_customer is None and requested_vehicle is not None:
                    requested_customer = requested_vehicle.customer

                if requested_customer is not None:
                    self.initial["customer"] = requested_customer.pk
                    selected_customer = requested_customer
                    selected_customer_id = str(requested_customer.pk)

                if requested_vehicle is not None and (requested_customer is None or requested_vehicle.customer.pk == requested_customer.pk):
                    self.initial["vehicle"] = requested_vehicle.pk
                    selected_vehicle = requested_vehicle
                    selected_vehicle_id = str(requested_vehicle.pk)

        if self.instance:
            user = self.instance.cost_estimator
            if user:
                display_name = user.get_full_name() or user.username
                self.fields["cost_estimator"].initial = display_name
                self.initial["cost_estimator"] = display_name

        if not self.instance.pk:
            self.fields["entry_date"].initial = timezone.now().date()
            self.fields["current_km"].initial = None
            self.fields["fuel_level"].initial = None

        if self.request and self.request.user:
            user = self.request.user
            self.fields["cost_estimator"].initial = user.get_full_name() or user.username

        if self.is_bound:
            selected_customer_id = (self.data.get("customer") or "").strip()
            selected_vehicle_id = (self.data.get("vehicle") or "").strip()

        if not selected_customer_id and self.instance and self.instance.customer_id:
            selected_customer_id = str(self.instance.customer_id)

        if not selected_customer_id and self.initial.get("customer"):
            selected_customer_id = str(self.initial.get("customer"))

        if not selected_vehicle_id and self.instance and self.instance.vehicle_id:
            selected_vehicle_id = str(self.instance.vehicle_id)

        if not selected_vehicle_id and self.initial.get("vehicle"):
            selected_vehicle_id = str(self.initial.get("vehicle"))

        customer_queryset = Customer.objects.all()
        vehicle_queryset = Vehicle.objects.all()
        if self.workshop:
            customer_queryset = customer_queryset.filter(workshop=self.workshop)
            vehicle_queryset = vehicle_queryset.filter(workshop=self.workshop)

        if selected_customer_id:
            selected_customer = customer_queryset.filter(pk=selected_customer_id).first()
            vehicle_field.queryset = vehicle_queryset.filter(customer_id=selected_customer_id).order_by("plate")
        else:
            vehicle_field.queryset = Vehicle.objects.none()

        if selected_vehicle_id:
            selected_vehicle_queryset = vehicle_queryset.filter(pk=selected_vehicle_id)
            if selected_customer_id:
                selected_vehicle_queryset = selected_vehicle_queryset.filter(customer_id=selected_customer_id)
            selected_vehicle = selected_vehicle_queryset.first()

        is_locked = bool(getattr(self.instance, "is_status_locked", False))
        customer_vehicle_x_data = json.dumps({"customerId": selected_customer_id, "vehicleId": selected_vehicle_id, "isLocked": is_locked})

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(r"""
            <script>
                async function updateVehicleList(customerId, selectedVehicleId = null) {
                    const vehicleInput = document.querySelector('[name="vehicle"]');
                    if (!vehicleInput) return;

                    const vehicleContainer = vehicleInput.closest('[x-data]');
                    const vehicleData = Alpine.$data(vehicleContainer);
                    if (vehicleData && vehicleData.isLocked) {
                        return;
                    }
                    const optionsUl = vehicleContainer.querySelector('ul[role="listbox"]');

                    vehicleData.clear(); 
                
                    if (!customerId) {
                        optionsUl.querySelectorAll('li[data-value]').forEach(li => li.remove());
                        return;
                    }
                
                    try {
                        const response = await fetch(`/budget/get-vehicles/?customer=${customerId}`);
                        const vehicles = await response.json();
                        optionsUl.querySelectorAll('li[data-value]').forEach(li => li.remove());

                        vehicles.forEach(v => {
                            const li = document.createElement('li');
                            li.className = 'relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white transition-colors group';
                            li.setAttribute('data-value', String(v.id));
                            li.setAttribute('data-label', v.label);
                            li.setAttribute('x-show', `!search || '${v.label.replace(/'/g, "\\'")}'.toLowerCase().includes(search.toLowerCase())`);
                            li.innerHTML = `<span class="block truncate">${v.label}</span>`;
                            
                            // IMPORTANTE: Ao clicar, chama o método 'select' do Alpine do widget
                            li.addEventListener('click', () => {
                                vehicleData.select(li);
                            });
                            
                            optionsUl.appendChild(li);

                            // Se for um veículo específico (vindo de um Quick Create)
                            if (selectedVehicleId && String(v.id) === String(selectedVehicleId)) {
                                vehicleData.select(li);
                            }
                        });
                    } catch (error) {
                        console.error("Erro ao carregar veículos:", error);
                    }
                }

                function selectCustomerFromQuickForm(customer) {
                    if (!customer || !customer.id) return;

                    const customerInput = document.querySelector('[name="customer"]');
                    const customerEl = customerInput.closest('[x-data]');
                    const customerData = Alpine.$data(customerEl);
                    const optionsUl = customerEl.querySelector('ul[role="listbox"]');

                    const customerId = String(customer.id);
                    const customerName = customer.name || 'Cliente';
                    let option = optionsUl.querySelector(`li[data-value='${customerId}']`);

                    if (!option) {
                        option = document.createElement('li');
                        option.className = 'relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white group transition-colors';
                        option.setAttribute('data-value', customerId);
                        option.setAttribute('data-label', customerName);
                        option.setAttribute('x-show', `!search || '${customerName.replace(/'/g, "\\'")}'.toLowerCase().includes(search.toLowerCase())`);
                        option.innerHTML = `<span class="block truncate">${customerName}</span>`;
                        option.addEventListener('click', () => customerData.select(option));
                        optionsUl.appendChild(option);
                    }

                    // Crucial: Usar o método select do componente para sincronizar label e search
                    customerData.select(option);
                }

                if (!window.__budgetStep1CustomerSavedBound) {
                    window.__budgetStep1CustomerSavedBound = true;
                    document.body.addEventListener('customerSaved', function (evt) {
                        const modal = document.getElementById('form_modal');
                        if (modal) {
                            modal.close();
                        }

                        const customer = evt && evt.detail ? evt.detail : null;
                        selectCustomerFromQuickForm(customer);
                    });
                }

                if (!window.__budgetStep1VehicleSavedBound) {
                    window.__budgetStep1VehicleSavedBound = true;
                    document.body.addEventListener('vehicleSaved', function (evt) {
                        const modal = document.getElementById('form_modal');
                        if (modal) {
                            modal.close();
                        }

                        const vehicle = evt && evt.detail ? evt.detail : null;
                        if (!vehicle || !vehicle.id) {
                            return;
                        }

                        const customerInput = document.querySelector('[name="customer"]');
                        const customerId = customerInput && customerInput.value ? customerInput.value : (vehicle.customer_id || '');
                        if (!customerId) {
                            return;
                        }

                        updateVehicleList(customerId, vehicle.id);
                    });
                }
            </script>
            """),
            Div(
                # Coluna Esquerda
                Div(
                    # Tipo Orçamento
                    Div(
                        HTML("""
                            <div
                                class="mb-5 rounded-2xl border border-base-300/80 bg-base-200/30 p-4 shadow-sm"
                                x-data="{
                                    budgetType: '{{ form.budget_type.value|default:"sale" }}'
                                }"
                            >
                                <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                                    <div class="space-y-1">
                                        <div class="text-lg font-semibold text-base-content">Tipo do Orçamento</div>
                                        <p class="text-sm leading-relaxed text-base-content/70">
                                            Escolha entre as opções disponíveis.
                                        </p>
                                    </div>

                                    <div class="flex w-full items-center justify-between gap-4 bg-base-100 px-4 py-3 transition-all hover:border-primary/40 hover:shadow-sm lg:max-w-xs">
                                        <div class="flex w-full flex-col gap-2">
                                            <select
                                                name="budget_type"
                                                id="id_budget_type"
                                                class="select select-bordered w-full"
                                                x-model="budgetType"
                                            >
                                                <option value="sale" {% if form.budget_type.value == "sale" %}selected{% endif %}>Venda</option>
                                                <option value="warranty" {% if form.budget_type.value == "warranty" %}selected{% endif %}>Garantia</option>
                                                <option value="courtesy" {% if form.budget_type.value == "courtesy" %}selected{% endif %}>Cortesia</option>
                                            </select>
                                        </div>

                                        <span
                                            class="badge min-w-20 px-3 py-3 text-sm font-semibold transition-colors"
                                            :class="{
                                                'badge-success': budgetType === 'sale',
                                                'badge-error': budgetType === 'warranty',
                                                'badge-info': budgetType === 'courtesy'
                                            }"
                                            x-text="
                                                budgetType === 'warranty'
                                                    ? 'Garantia'
                                                    : budgetType === 'courtesy'
                                                        ? 'Cortesia'
                                                        : 'Venda'
                                            "
                                        >
                                            {% if form.budget_type.value == "warranty" %}
                                                Garantia
                                            {% elif form.budget_type.value == "courtesy" %}
                                                Cortesia
                                            {% else %}
                                                Venda
                                            {% endif %}
                                        </span>
                                    </div>
                                </div>

                                {% if form.budget_type.errors %}
                                    <span class="mt-3 block text-sm text-error">
                                        {{ form.budget_type.errors|join:', ' }}
                                    </span>
                                {% endif %}
                            </div>
                        """),
                        HTML('<h3 class="text-2xl font-bold mb-2">Orçamento</h3>'),
                        Div(
                            Field("workshop", wrapper_class="col-span-12 lg:col-span-12"),
                            Field("cost_estimator", wrapper_class="col-span-12 lg:col-span-12"),
                            Field("entry_date", wrapper_class="col-span-12 lg:col-span-12"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    # Cliente
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Cliente</h3>'),
                        Div(
                            Div(
                                Field("customer", wrapper_class="flex-1 mb-0"),
                                HTML("""<button type="button" class="btn btn-circle mb-2" :class="isLocked ? 'btn-disabled opacity-60 cursor-not-allowed' : (customerId ? 'btn-warning' : 'btn-primary')" :disabled="isLocked"
                                                                 @click="const url = customerId ? `/customer/quick-update/${customerId}/` : '/customer/quick-create/';
                                                                        if (isLocked) { return; }
                                                                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                                                        document.getElementById('form_modal').showModal();">
                                                                <span class="material-icons" x-text="customerId ? 'edit' : 'person_add'"></span>
                                                            </button>"""),
                                css_class="flex items-end gap-2 w-full",
                            ),
                            Div(
                                Field("vehicle", wrapper_class="flex-1 mb-0"),
                                HTML("""<button type="button" class="btn btn-circle mb-2" 
                                                                :class="isLocked ? 'btn-disabled opacity-60 cursor-not-allowed' : (!customerId ? 'btn-disabled opacity-50' : (vehicleId ? 'btn-warning' : 'btn-primary'))" 
                                                                :disabled="isLocked || !customerId"
                                                                @click="const url = vehicleId ? `/customer/vehicle/quick-update/${vehicleId}/` : `/customer/vehicle/quick-create/?customer_id=${customerId}`;
                                                                        if (isLocked) { return; }
                                                                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                                                        document.getElementById('form_modal').showModal();">
                                                                <span class="material-icons" x-text="vehicleId ? 'edit' : 'directions_car_filled'"></span>
                                                            </button>"""),
                                css_class="flex items-end gap-2 w-full",
                                **{":class": "{ 'pointer-events-none': !customerId }"},
                            ),
                            x_data=customer_vehicle_x_data,
                            **{
                                "@change": """
                                        if (isLocked) {
                                            return;
                                        }
                                        if ($event.target.name === 'customer') { 
                                            customerId = $event.target.value; 
                                            vehicleId = ''; // Reseta veículo se mudar cliente
                                            updateVehicleList($event.target.value);
                                        } else if ($event.target.name === 'vehicle') { 
                                            vehicleId = $event.target.value; 
                                        }
                                    """
                            },
                            css_class="grid grid-cols-1 gap-2",
                        ),
                        css_class="mb-6",
                    ),
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Veículo</h3>'),
                        Div(
                            Field("current_km", wrapper_class="col-span-12 lg:col-span-6"),
                            Field("fuel_level", wrapper_class="col-span-12 lg:col-span-6"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                Div(css_class="col-span-12 lg:col-span-2"),
                # Coluna Direita (Resumo)
                Div(
                    Div(
                        HTML('<h2 class="text-2xl font-bold mb-4 pb-2">Resumo</h2>'),
                        # Cliente
                        HTML('<h4 class="text-lg font-bold mb-2">Cliente</h4>'),
                        Div(HTML(render_to_string("budget/partials/components/customer_resume.html", {"customer": selected_customer})), id="resumo-cliente", css_class="mb-6 overflow-x-auto"),
                        # Veículo
                        HTML('<h4 class="text-lg font-bold mb-2">Veículo</h4>'),
                        Div(HTML(render_to_string("budget/partials/components/vehicle_resume.html", {"vehicle": selected_vehicle})), id="resumo-veiculo", css_class="overflow-x-auto"),
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12",
            ),
        )

    def clean(self):
        cleaned_data = super().clean() or {}

        current_km = cleaned_data.get("current_km")
        vehicle = cleaned_data.get("vehicle")

        if vehicle and current_km is not None and vehicle.km is not None and current_km < vehicle.km:
            formatted_previous_km = f"{vehicle.km:,}".replace(",", ".")
            self.add_error("current_km", f"O KM informado não pode ser menor que o KM anterior do veículo ({formatted_previous_km}).")

        cleaned_data["workshop"] = self.workshop
        if self.request and self.request.user:
            cleaned_data["cost_estimator"] = self.request.user

        return cleaned_data

    def clean_current_km(self) -> int:
        raw_value = self.data.get("current_km") if self.is_bound else self.cleaned_data.get("current_km")
        if raw_value in (None, ""):
            return 0

        digits = "".join(char for char in str(raw_value) if char.isdigit())
        if not digits:
            return 0

        return int(digits)
