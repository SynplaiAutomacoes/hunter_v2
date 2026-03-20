import base64
import json
from decimal import Decimal
from html import escape

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetImage, BudgetImageType, Defect
from apps.budget.pricing import resolve_discount_fields
from apps.checklist.models import Checklist
from apps.collaborators.models import WorkshopCollaborator
from apps.core.utils import alert_confirm_layout
from apps.core.widgets import CalendarDateInput, MoneyInput, NumberInput, PercentageInput, SearchableSelectInput, SelectInput, TextInput, TextareaInput
from apps.customer.models import Vehicle
from apps.quote.models.investigative_questions import InvestigativeQuestion, InvestigativeResponse

from .shared import MAX_BUDGET_IMAGES, _get_budget_with_prefetched_items, _render_budget_items_rows, _validate_uploaded_files, _validate_uploaded_images
from .widgets import MultipleFileField, MultipleFileInput


SLOT_IMAGE_TYPES = [
    BudgetImageType.PRINCIPAL,
    BudgetImageType.FRONTAL,
    BudgetImageType.TRASEIRA,
    BudgetImageType.DIREITA,
    BudgetImageType.ESQUERDA,
    BudgetImageType.PAINEL,
    BudgetImageType.CHASSI,
    BudgetImageType.MOTOR,
]

SLOT_LAYOUT_CONFIG = [
    {"type": BudgetImageType.PRINCIPAL, "label": "Principal", "full_width": True},
    {"type": BudgetImageType.FRONTAL, "label": "Frontal", "full_width": False},
    {"type": BudgetImageType.TRASEIRA, "label": "Traseira", "full_width": False},
    {"type": BudgetImageType.DIREITA, "label": "Direita", "full_width": False},
    {"type": BudgetImageType.ESQUERDA, "label": "Esquerda", "full_width": False},
    {"type": BudgetImageType.PAINEL, "label": "Painel", "full_width": True},
    {"type": BudgetImageType.CHASSI, "label": "Chassi", "full_width": True},
    {"type": BudgetImageType.MOTOR, "label": "Motor", "full_width": True},
]

SLOT_PLACEHOLDER_PATHS = {
    BudgetImageType.PRINCIPAL: "image/principal.png",
    BudgetImageType.FRONTAL: "image/frontal.png",
    BudgetImageType.TRASEIRA: "image/traseira.png",
    BudgetImageType.DIREITA: "image/direita.png",
    BudgetImageType.ESQUERDA: "image/esquerda.png",
    BudgetImageType.PAINEL: "image/painel.png",
    BudgetImageType.CHASSI: "image/chassi.png",
    BudgetImageType.MOTOR: "image/motor.png",
}


def _format_file_size(size_bytes: int) -> str:
    units = ["B", "kB", "MB", "GB", "TB"]
    size = float(max(size_bytes, 0))
    unit_index = 0

    while size >= 1000 and unit_index < len(units) - 1:
        size /= 1000
        unit_index += 1

    if size >= 999.5 and unit_index < len(units) - 1:
        size /= 1000
        unit_index += 1

    if unit_index == 0:
        formatted = str(int(size))
    elif size >= 100:
        formatted = str(int(round(size)))
    else:
        formatted = f"{size:.1f}".rstrip("0").rstrip(".")

    return f"{formatted} {units[unit_index]}"


def _build_step3_slot_fallback_html(slot_placeholder_urls):
    slots_html = []

    principal = SLOT_LAYOUT_CONFIG[0]
    principal_src = slot_placeholder_urls[principal["type"]]
    slots_html.append(
        f"""
        <div class="mb-4">
            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                 id="slot-{principal["type"]}"
                 onclick="document.getElementById('file-input-{principal["type"]}').click()">
                <div class="flex flex-col items-center justify-center h-48">
                    <img src="{principal_src}" alt="Placeholder {principal["label"]}" class="w-full h-32 object-contain rounded mb-2 opacity-40">
                    <p class="text-center text-sm font-semibold text-gray-600">{principal["label"]}</p>
                    <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                </div>
                <input type="file" id="file-input-{principal["type"]}" name="image_{principal["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{principal["type"]}', this)">
            </div>
        </div>
        """
    )

    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    for slot in SLOT_LAYOUT_CONFIG[1:3]:
        placeholder_src = slot_placeholder_urls[slot["type"]]
        slots_html.append(
            f"""
            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                 id="slot-{slot["type"]}"
                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                <div class="flex flex-col items-center justify-center h-32">
                    <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                    <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                    <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                </div>
                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot["type"]}', this)">
            </div>
            """
        )
    slots_html.append("</div>")

    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    for slot in SLOT_LAYOUT_CONFIG[3:5]:
        placeholder_src = slot_placeholder_urls[slot["type"]]
        slots_html.append(
            f"""
            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                 id="slot-{slot["type"]}"
                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                <div class="flex flex-col items-center justify-center h-32">
                    <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                    <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                    <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                </div>
                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot["type"]}', this)">
            </div>
            """
        )
    slots_html.append("</div>")

    for slot in SLOT_LAYOUT_CONFIG[5:]:
        placeholder_src = slot_placeholder_urls[slot["type"]]
        slots_html.append(
            f"""
            <div class="mb-4">
                <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                     id="slot-{slot["type"]}"
                     onclick="document.getElementById('file-input-{slot["type"]}').click()">
                    <div class="flex flex-col items-center justify-center h-40">
                        <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-24 object-contain rounded mb-2 opacity-40">
                        <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                        <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                    </div>
                    <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot["type"]}', this)">
                </div>
            </div>
            """
        )

    return "".join(slots_html)


def _build_step3_images_initial_html(budget, slot_placeholder_urls):
    images_by_type = {}
    additional_images = []

    if budget and getattr(budget, "pk", None):
        for existing_image in budget.ordered_images:
            if existing_image.image_type in SLOT_IMAGE_TYPES and existing_image.content and existing_image.image_type not in images_by_type:
                images_by_type[existing_image.image_type] = existing_image
            elif existing_image.content:
                additional_images.append(existing_image)

    def render_slot(slot):
        slot_type = slot["type"]
        slot_label = slot["label"]
        slot_image = images_by_type.get(slot_type)

        is_main = slot_type == BudgetImageType.PRINCIPAL
        is_bottom_full = slot_type in {BudgetImageType.PAINEL, BudgetImageType.CHASSI, BudgetImageType.MOTOR}

        padding = "p-4" if (is_main or is_bottom_full) else "p-3"
        height = "h-48" if is_main else ("h-40" if is_bottom_full else "h-32")
        empty_img_height = "h-32" if is_main else ("h-24" if is_bottom_full else "h-16")

        if slot_image and slot_image.content:
            img_data = base64.b64encode(slot_image.content).decode("utf-8")
            img_src = f"data:{slot_image.content_type or 'image/jpeg'};base64,{img_data}"
            return f"""
                <div class="mb-4">
                    <div class="relative border-2 border-gray-300 rounded-lg {padding} bg-white hover:border-primary transition-colors cursor-pointer group" 
                         id="slot-{slot_type}"
                         onclick="document.getElementById('file-input-{slot_type}').click()">
                        <img src="{img_src}" alt="{slot_label}" class="w-full {height} object-contain rounded mb-2">
                        <p class="text-center text-sm font-semibold text-gray-600">{slot_label}</p>
                        <input type="file" id="file-input-{slot_type}" name="image_{slot_type}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot_type}', this)">
                        <input type="hidden" id="delete-slot-{slot_type}" name="slot_to_delete" value="">
                        <button type="button" 
                                onclick="event.stopPropagation(); deleteSlotImage('{slot_type}', '{slot_image.id}')"
                                class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <span class="material-icons text-xs">delete</span>
                        </button>
                    </div>
                </div>
            """

        placeholder_src = slot_placeholder_urls[slot_type]
        hint_margin = " mt-1" if (is_main or is_bottom_full) else ""
        return f"""
            <div class="mb-4">
                <div class="relative border-2 border-dashed border-gray-300 rounded-lg {padding} bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                     id="slot-{slot_type}"
                     onclick="document.getElementById('file-input-{slot_type}').click()">
                    <div class="flex flex-col items-center justify-center {height}">
                        <img src="{placeholder_src}" alt="Placeholder {slot_label}" class="w-full {empty_img_height} object-contain rounded mb-1 opacity-40">
                        <p class="text-center text-sm font-semibold text-gray-600">{slot_label}</p>
                        <p class="text-center text-xs text-gray-400{hint_margin}">Clique para adicionar</p>
                    </div>
                    <input type="file" id="file-input-{slot_type}" name="image_{slot_type}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot_type}', this)">
                </div>
            </div>
        """

    slots_html = [render_slot(SLOT_LAYOUT_CONFIG[0])]
    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[1]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[2]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append("</div>")
    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[3]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[4]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append("</div>")
    for slot in SLOT_LAYOUT_CONFIG[5:]:
        slots_html.append(render_slot(slot))

    additional_html = []
    for img in additional_images:
        file_name = escape(img.content_name or f"Arquivo {img.id}")
        file_size = _format_file_size(len(img.content or b""))
        additional_html.append(
            f"""
            <div class="flex items-center justify-between gap-3 border border-gray-200 rounded-lg px-3 py-2 hover:border-primary transition-colors" id="additional-image-{img.id}">
                <div class="min-w-0 flex-1">
                    <p class="text-sm font-semibold text-gray-700 truncate" title="{file_name}">{file_name}</p>
                    <p class="text-xs text-gray-500">{file_size}</p>
                </div>
                <input type="hidden" name="images_to_delete" value="" id="delete-flag-{img.id}">
                <button type="button" 
                        onclick="document.getElementById('delete-flag-{img.id}').value='{img.id}'; document.getElementById('additional-image-{img.id}').classList.add('opacity-50'); this.disabled=true; this.textContent='Será excluído';"
                        class="btn btn-xs btn-error text-white"
                        title="Marcar para exclusão">
                    Excluir
                </button>
            </div>
            """
        )

    return "".join(slots_html), "".join(additional_html)


class BudgetStep1Form(forms.ModelForm):
    workshop = forms.CharField(label="Empresa", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    cost_estimator = forms.CharField(label="Orçamentista", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    vehicle = forms.ModelChoiceField(label="Veículo", queryset=Vehicle.objects.none(), required=False, widget=SearchableSelectInput())

    class Meta:
        model = Budget
        fields = ["workshop", "cost_estimator", "entry_date", "customer", "vehicle", "current_km", "fuel_level"]
        widgets = {
            "entry_date": CalendarDateInput(),
            "customer": SearchableSelectInput(attrs={"x-model": "customerId", "@change": "customerId = $el.value; vehicleId = '';"}),
            "current_km": NumberInput(),
            "fuel_level": SelectInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.fields["customer"].widget.attrs.update(
            {
                "x-model": "customerId",
                "hx-get": reverse_lazy("budget:customer-detail"),
                "hx-trigger": "change",
                "hx-target": "#resumo-cliente",
                "@change": "customerId = $el.value; vehicleId = ''; updateVehicleList($el.value);",
            }
        )

        self.fields["vehicle"].widget.attrs.update(
            {
                "x-model": "vehicleId",
                "id": "id_vehicle",
                ":disabled": "!customerId",
                ":class": "{ 'cursor-not-allowed': !customerId }",
                "hx-get": reverse_lazy("budget:vehicle-detail"),
                "hx-trigger": "change",
                "hx-target": "#resumo-veiculo",
                "hx-include": "[name='customer']",
            }
        )

        self.fields["vehicle"].widget.attrs.update({"id": "id_vehicle"})
        self.fields["fuel_level"].required = False
        self.fields["current_km"].error_messages["required"] = "Preencha o KM atual para continuar."

        # Preenchimento inicial
        if self.workshop:
            workshop_name = self.workshop.name
            self.fields["workshop"].initial = workshop_name
            self.initial["workshop"] = workshop_name
            self.fields["customer"].queryset = self.fields["customer"].queryset.filter(workshop=self.workshop)

        if self.instance:
            user = self.instance.cost_estimator
            if user:
                display_name = user.get_full_name() or user.username
                self.fields["cost_estimator"].initial = display_name
                self.initial["cost_estimator"] = display_name

            customer_id = self.data.get("customer") or (self.instance.customer_id if self.instance.customer else None)
            if customer_id:
                self.fields["vehicle"].queryset = Vehicle.objects.filter(customer_id=customer_id)
            else:
                self.fields["vehicle"].queryset = Vehicle.objects.none()

        if not self.instance.pk:
            self.fields["entry_date"].initial = timezone.now().date()
            self.fields["current_km"].initial = None
            self.fields["fuel_level"].initial = None

        if self.request and self.request.user:
            user = self.request.user
            self.fields["cost_estimator"].initial = user.get_full_name() or user.username

        selected_customer_id = ""
        selected_vehicle_id = ""
        if self.is_bound:
            selected_customer_id = (self.data.get("customer") or "").strip()
            selected_vehicle_id = (self.data.get("vehicle") or "").strip()

        if not selected_customer_id and self.instance and self.instance.customer_id:
            selected_customer_id = str(self.instance.customer_id)

        if not selected_vehicle_id and self.instance and self.instance.vehicle_id:
            selected_vehicle_id = str(self.instance.vehicle_id)

        customer_vehicle_x_data = json.dumps({"customerId": selected_customer_id, "vehicleId": selected_vehicle_id})

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(r"""
            <script>
                document.addEventListener('input', function (e) {
                    if (e.target && e.target.name === 'current_km') {
                        let value = e.target.value.replace(/\D/g, '');
                        e.target.value = value.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
                    }
                });
                
                async function updateVehicleList(customerId, selectedVehicleId = null) {
                    const vehicleInput = document.querySelector('[name="vehicle"]');
                    if (!vehicleInput) return;

                    const vehicleContainer = vehicleInput.closest('[x-data]');
                    const vehicleData = Alpine.$data(vehicleContainer);
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
                    # Orçamento
                    Div(
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
                                HTML("""<button type="button" class="btn btn-circle mb-2" :class="customerId ? 'btn-warning' : 'btn-primary'"
                                                                @click="const url = customerId ? `/customer/quick-update/${customerId}/` : '/customer/quick-create/';
                                                                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                                                        document.getElementById('form_modal').showModal();">
                                                                <span class="material-icons" x-text="customerId ? 'edit' : 'person_add'"></span>
                                                            </button>"""),
                                css_class="flex items-end gap-2 w-full",
                            ),
                            Div(
                                Field("vehicle", wrapper_class="flex-1 mb-0"),
                                HTML("""<button type="button" class="btn btn-circle mb-2" 
                                                                :class="!customerId ? 'btn-disabled opacity-50' : (vehicleId ? 'btn-warning' : 'btn-primary')" 
                                                                :disabled="!customerId"
                                                                @click="const url = vehicleId ? `/customer/vehicle/quick-update/${vehicleId}/` : `/customer/vehicle/quick-create/?customer_id=${customerId}`;
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
                        Div(HTML(render_to_string("budget/partials/components/customer_resume.html", {"customer": self.instance.customer})), id="resumo-cliente", css_class="mb-6 overflow-x-auto"),
                        # Veículo
                        HTML('<h4 class="text-lg font-bold mb-2">Veículo</h4>'),
                        Div(HTML(render_to_string("budget/partials/components/vehicle_resume.html", {"vehicle": self.instance.vehicle})), id="resumo-veiculo", css_class="overflow-x-auto"),
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


class BudgetStep2Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["problem_description", "notes"]
        widgets = {
            "problem_description": TextareaInput(
                attrs={
                    "rows": 4,
                    "cols": 40,
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none; height: 40vh; min-height: 40vh; max-height: 40vh; overflow-y: auto;",
                }
            ),
            "notes": TextareaInput(
                attrs={
                    "rows": 4,
                    "cols": 40,
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none;",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.investigative_questions = InvestigativeQuestion.objects.filter(workshop=self.workshop, is_active=True).order_by("order")

        responses_by_question_id: dict[int, str] = {}
        if self.instance.pk:
            responses_by_question_id = {response.question_id: response.response for response in InvestigativeResponse.objects.filter(budget=self.instance).only("question_id", "response")}

        self.question_field_names = []
        for q in self.investigative_questions:
            field_name = f"question_{q.id}"
            self.question_field_names.append(field_name)
            # Valor inicial (se estiver editando)
            initial_value = responses_by_question_id.get(q.id, "")
            # Definir o tipo de campo
            if q.response_type == InvestigativeQuestion.ResponseType.BOOLEAN:
                choices = [("", "Selecione..."), ("Sim", "Sim"), ("Não", "Não")]
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices, required=False, initial=initial_value, widget=SelectInput(choices=choices))
            elif q.response_type == InvestigativeQuestion.ResponseType.SCALE:
                display_id = f"display_{field_name}"
                self.fields[field_name] = forms.IntegerField(
                    label=q.text,
                    min_value=1,
                    max_value=10,
                    required=False,
                    initial=initial_value or 5,
                    widget=forms.NumberInput(attrs={"class": "range range-primary w-full", "type": "range", "step": "1", "min": "1", "max": "10", "oninput": f"document.getElementById('{display_id}').innerText = this.value"}),
                )
                self.fields[field_name].help_text = f'Valor selecionado: <span id="{display_id}" class="font-bold text-xs">{initial_value or 5}</span>'
            elif q.response_type == InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE:
                choices = [(opt, opt) for opt in q.options]
                choices1 = [("", "Selecione...")] + choices
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices1, required=False, initial=initial_value, widget=SelectInput(choices=choices1))
            else:  # FREE_TEXT
                self.fields[field_name] = forms.CharField(label=q.text, required=False, initial=initial_value, widget=TextInput())

        # 3. Configurar Layout dinâmico do Crispy
        question_layout_fields = [Field(name, wrapper_class="mb-4") for name in self.question_field_names]

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Relato do Cliente</h3>'),
                # Descrição do Problema
                Div(Field("problem_description", wrapper_class="flex flex-col h-full", css_class="flex-1"), css_class="col-span-12 lg:col-span-6 flex flex-col"),
                # Perguntas Investigativas
                Div(
                    HTML('<h5 class="font-bold mb-2">Perguntas Investigativas</h5>'),
                    Div(*question_layout_fields, css_class="border bg-base-200 px-4 py-2 rounded-lg pr-4 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-400", style="border-color: var(--color-input-ring); height: 40vh; min-height: 40vh; max-height: 40vh;"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                # Observações
                Div(Field("notes", wrapper_class="w-full", css_class="bg-base-200"), css_class="col-span-12"),
                css_class="budget-step2-client-report grid grid-cols-12 gap-6",
            ),
        )

    def save(self, commit=True):
        budget = super().save(commit=commit)

        # Salvar as respostas vinculadas
        for field_name in self.question_field_names:
            question_id = field_name.split("_")[1]
            response_text = self.cleaned_data.get(field_name)

            if response_text:
                InvestigativeResponse.objects.update_or_create(budget=budget, question_id=question_id, defaults={"workshop": self.workshop, "response": str(response_text)})
        return budget


class BudgetStep3Form(forms.ModelForm):
    new_defect = forms.CharField(label=False, required=False, widget=TextInput(attrs={"id": "id_new_defect", "placeholder": "Digite um defeito e clique em Adicionar", "onkeypress": "if(event.keyCode==13){ event.preventDefault(); addDefectRow(); }"}))
    checklist = forms.ModelChoiceField(label="Selecione o Checklist", queryset=Checklist.objects.none(), required=False, widget=SelectInput())
    collaborator = forms.ModelChoiceField(label="Selecione o colaborador que realizará o serviço", required=True, queryset=WorkshopCollaborator.objects.none(), widget=SelectInput())
    images = MultipleFileField(label=None, required=False, widget=MultipleFileInput(attrs={"class": "file-input file-input-bordered w-full"}))

    class Meta:
        model = Budget
        fields = ["collaborator", "checklist", "technical_diagnosis"]
        widgets = {
            "technical_diagnosis": TextareaInput(
                attrs={
                    "rows": 10,
                    "placeholder": "Descreva detalhadamente as observações técnicas, diagnósticos preliminares, testes realizados...",
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none;",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if self.workshop:
            self.fields["collaborator"].queryset = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            self.fields["checklist"].queryset = Checklist.objects.filter(workshop=self.workshop).order_by("name")

        self.fields["collaborator"].error_messages["required"] = "Selecione um colaborador para continuar."

        checklist_pdf_base_url = reverse("budget:visualizar_pdf_checklist", args=[self.instance.pk]) if self.instance.pk else ""

        initial_collab_id = ""
        if self.instance.pk and self.instance.collaborator:
            initial_collab_id = self.instance.collaborator.id

        self.fields["collaborator"].widget.attrs.update(
            {
                "x-model": "collaboratorId",
            }
        )

        slot_placeholder_urls = {slot_type: static(path) for slot_type, path in SLOT_PLACEHOLDER_PATHS.items()}
        slot_placeholder_urls_js = "{" + ", ".join([f"'{slot_type}': '{slot_placeholder_urls[slot_type]}'" for slot_type in SLOT_IMAGE_TYPES]) + "}"
        slots_initial_html, additional_initial_html = _build_step3_images_initial_html(self.instance, slot_placeholder_urls)
        if not slots_initial_html:
            slots_initial_html = _build_step3_slot_fallback_html(slot_placeholder_urls)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""<script>
                    function addDefectRow() {{
                        const input = document.getElementById('id_new_defect');
                        const container = document.getElementById('defect-list-container');
                        const text = input.value.trim();
                        if (text === "") return;
                        const id = 'new-' + Date.now();
                        const html = `<div class="badge badge-lg badge-ghost gap-2 py-5 mb-2 mr-2 pr-1" id="defect-${{id}}">
                                <input type="hidden" name="defects_list" value="${{text}}">
                                <span class="font-medium">${{text}}</span>
                                <button type="button" onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-error">
                                    X
                                </button>
                            </div>`;
                        container.insertAdjacentHTML('beforeend', html);
                        input.value = "";
                        input.focus();
                    }}

                    function printSelectedChecklist() {{
                        const checklistInput = document.getElementById('id_checklist');
                        const checklistId = checklistInput ? checklistInput.value.trim() : '';
                        if (!checklistId) {{
                            document.body.dispatchEvent(new CustomEvent('showToast', {{
                                detail: {{
                                    type: 'warning',
                                    message: 'Selecione um checklist antes de imprimir.',
                                }},
                            }}));
                            return;
                        }}

                        const checklistPdfBaseUrl = '{checklist_pdf_base_url}';
                        if (!checklistPdfBaseUrl) {{
                            document.body.dispatchEvent(new CustomEvent('showToast', {{
                                detail: {{
                                    type: 'error',
                                    message: 'Salve o orçamento para imprimir o checklist.',
                                }},
                            }}));
                            return;
                        }}

                        const checklistPrintUrl = checklistPdfBaseUrl + '?checklist=' + encodeURIComponent(checklistId);
                        window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ 
                            detail: {{ url: checklistPrintUrl }} 
                        }}));
                    }}
                     
                    document.body.addEventListener('collaboratorSaved', function(evt) {{
                        const modal = document.getElementById('form_modal');
                        if (modal) modal.close();

                        const eventDetail = evt && evt.detail ? evt.detail : null;
                        const createdCollaboratorId = eventDetail && eventDetail.id ? String(eventDetail.id) : '';

                        const selectElement = document.querySelector('#id_collaborator');
                        const currentValue = selectElement ? selectElement.value : '';

                        const collaboratorIdToSelect = createdCollaboratorId || currentValue;
                        if (collaboratorIdToSelect) {{
                            localStorage.setItem('budget_step3_collaborator', collaboratorIdToSelect);
                        }}

                        const budgetId = {self.instance.pk if self.instance.pk else "null"};
                        if (!budgetId) {{
                            localStorage.removeItem('budget_step3_collaborator');
                            return;
                        }}

                        const savedId = localStorage.getItem('budget_step3_collaborator');
                        const url = `/budget/${{budgetId}}/collaborator-field/` + (savedId ? `?selected=${{savedId}}` : '');

                        htmx.ajax('GET', url, {{
                            target: '#collaborator-field-container',
                            swap: 'outerHTML'
                        }}).then(() => {{
                            if (savedId) {{
                                setTimeout(() => {{
                                    const alpineContainer = document.querySelector('[x-data*="collaboratorId"]');
                                    if (alpineContainer && typeof Alpine !== 'undefined') {{
                                        const alpineData = Alpine.$data(alpineContainer);
                                        if (alpineData) {{
                                            alpineData.collaboratorId = savedId;
                                        }}
                                    }}
                                }}, 100);
                            }}

                            localStorage.removeItem('budget_step3_collaborator');
                        }});
                    }});
                </script>"""),
            Div(
                # Coluna Esquerda
                Div(
                    # Diagnóstico Técnico
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Diagnóstico Técnico</h3>'),
                        HTML(f'''
                            {{% include "budget/partials/components/collaborator_field.html" with field=form.collaborator initial_collab_id="{initial_collab_id}" %}}
                        '''),
                        #
                        HTML('<label class="block text-gray-700 font-bold mb-2">Adicione os defeitos encontrados durante a inspeção</label>'),
                        Div(id="defect-list-container", css_class="mb-4 p-4 border-2 border-dashed border-gray-200 rounded-lg min-h-[120px] flex flex-wrap content-start"),
                        Div(
                            Div(Field("new_defect", wrapper_class="mb-0"), css_class="flex-1"),
                            HTML("""<button type="button" class="btn btn-primary ml-2" onclick="addDefectRow()">
                                    Adicionar</button>"""),
                            css_class="flex items-end mb-8",
                        ),
                        css_class="mb-8",
                    ),
                    # Checklist para Impressão
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Checklist para Impressão</h3>'),
                        Div(
                            Div(Field("checklist", wrapper_class="mb-0"), css_class="flex-1"),
                            HTML("""<button type="button" class="btn btn-primary ml-2" onclick="printSelectedChecklist()">
                                            Imprimir</button>"""),
                            css_class="flex items-end mb-8",
                        ),
                        css_class="mb-8",
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                #
                Div(css_class="hidden lg:block lg:col-span-1"),
                #
                # Coluna Direita
                Div(
                    # Observações Técnicas
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Observações Técnicas</h3>'),
                        Field("technical_diagnosis", label=False, wrapper_class="mb-0"),
                        css_class="mb-8",
                    ),
                    # Imagens
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Anexar Imagens do Veículo</h3>'),
                        HTML(f'<div id="vehicle-images-slots">{slots_initial_html}</div>'),
                        HTML('<h4 class="text-lg font-semibold mt-6 mb-2">Arquivos Adicionais</h4>'),
                        HTML(f'<div id="additional-images-container" class="space-y-2 mb-4">{additional_initial_html}</div>'),
                        Field("images", label=False, wrapper_class="mb-0"),
                        HTML('<p class="text-sm text-gray-500 mt-2">Use os slots acima para fotos específicas do veículo. Aqui você pode adicionar arquivos adicionais.</p>'),
                        css_class="mb-6",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
            HTML("""
                <dialog id="pdfModal" class="modal" x-data="{ pdfUrl: '' }" @open-pdf-modal.window="pdfUrl = $event.detail.url; $el.showModal()">
                    <div class="modal-box max-w-5xl w-full h-[90vh] p-0 flex flex-col">
                        <div class="flex items-center justify-between px-6 py-4 border-b bg-base-200">
                            <h3 class="text-xl font-bold flex items-center gap-2">
                                <span class="material-icons">description</span>
                                Visualização do Checklist
                            </h3>
                            <div class="flex gap-2">
                                <button type="button" class="btn btn-sm btn-success"
                                    onclick="const frame = document.querySelector('#pdfModal iframe'); frame.contentWindow.focus(); frame.contentWindow.print();">
                                    Baixar PDF
                                </button>
                                <button type="button" class="btn btn-sm" onclick="document.getElementById('pdfModal').close()">
                                    Fechar
                                </button>
                            </div>
                        </div>
                        <div class="flex-1 bg-gray-100">
                            <template x-if="pdfUrl">
                                <iframe :src="pdfUrl" class="w-full h-full" frameborder="0"></iframe>
                            </template>
                        </div>
                    </div>
                    <form method="dialog" class="modal-backdrop"><button>close</button></form>
                </dialog>
            """),
        )
        self.helper.layout.append(
            HTML(
                """
                <style>
                    [data-theme="dark"] #vehicle-images-slots [id^="slot-"] {
                        background-color: rgb(31 41 55 / 0.75) !important;
                        border-color: rgb(75 85 99) !important;
                    }
                    [data-theme="dark"] #vehicle-images-slots [id^="slot-"] p {
                        color: rgb(229 231 235) !important;
                    }
                    [data-theme="dark"] #additional-images-container [id^="additional-image-"] {
                        background-color: rgb(31 41 55 / 0.75) !important;
                        border-color: rgb(75 85 99) !important;
                    }
                </style>
                """
            )
        )
        if self.instance.pk:
            existing_defects = self.instance.defects.all()
            if existing_defects.exists():
                defects_json = "".join(
                    [
                        f"""<div class="badge badge-lg badge-ghost gap-2 py-5 mb-2 mr-2 pr-1" id="defect-old-{d.id}">
                            <input type="hidden" name="defects_list" value="{d.name}">
                            <span class="font-medium">{d.name}</span>
                            <button type="button" onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-error">
                                X
                            </button>
                        </div>"""
                        for d in existing_defects
                    ]
                )
                # Injeta os defeitos existentes após a renderização do container
                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        document.getElementById('defect-list-container').innerHTML = `{defects_json}`;
                    </script>
                    """)
                )

            # Inject existing images organized by type (slots + additional)
            existing_images = self.instance.ordered_images
            if existing_images.exists():
                existing_images_list = list(existing_images)
                images_by_type = {}
                additional_images = []
                for existing_image in existing_images_list:
                    if existing_image.image_type in SLOT_IMAGE_TYPES and existing_image.content and existing_image.image_type not in images_by_type:
                        images_by_type[existing_image.image_type] = existing_image
                    elif existing_image.content:
                        additional_images.append(existing_image)

                # Define slots layout
                slots_config = SLOT_LAYOUT_CONFIG

                # Build slots HTML
                slots_html = []

                # Principal (full width)
                slot = slots_config[0]
                img = images_by_type.get(slot["type"])
                if img and img.content:
                    img_data = base64.b64encode(img.content).decode("utf-8")
                    img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                    slots_html.append(f"""
                    <div class="mb-4">
                        <div class="relative border-2 border-gray-300 rounded-lg p-4 bg-white hover:border-primary transition-colors cursor-pointer group" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <img src="{img_src}" alt="{slot["label"]}" class="w-full h-48 object-contain rounded mb-2">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                            <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                            <button type="button" 
                                    onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                    class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <span class="material-icons text-xs">delete</span>
                            </button>
                        </div>
                    </div>
                    """)
                else:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="mb-4">
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-48">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-32 object-contain rounded mb-2 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                    </div>
                    """)

                # Two columns for Frontal/Traseira
                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[1:3]:
                    img = images_by_type.get(slot["type"])
                    if img and img.content:
                        img_data = base64.b64encode(img.content).decode("utf-8")
                        img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                        slots_html.append(f"""
                        <div class="relative border-2 border-gray-300 rounded-lg p-3 bg-white hover:border-primary transition-colors cursor-pointer group" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <img src="{img_src}" alt="{slot["label"]}" class="w-full h-32 object-contain rounded mb-2">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                            <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                            <button type="button" 
                                    onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                    class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <span class="material-icons text-xs">delete</span>
                            </button>
                        </div>
                        """)
                    else:
                        placeholder_src = slot_placeholder_urls[slot["type"]]
                        slots_html.append(f"""
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-32">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                        """)
                slots_html.append("</div>")

                # Two columns for Direita/Esquerda
                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[3:5]:
                    img = images_by_type.get(slot["type"])
                    if img and img.content:
                        img_data = base64.b64encode(img.content).decode("utf-8")
                        img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                        slots_html.append(f"""
                        <div class="relative border-2 border-gray-300 rounded-lg p-3 bg-white hover:border-primary transition-colors cursor-pointer group" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <img src="{img_src}" alt="{slot["label"]}" class="w-full h-32 object-contain rounded mb-2">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                            <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                            <button type="button" 
                                    onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                    class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <span class="material-icons text-xs">delete</span>
                            </button>
                        </div>
                        """)
                    else:
                        placeholder_src = slot_placeholder_urls[slot["type"]]
                        slots_html.append(f"""
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-32">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                        """)
                slots_html.append("</div>")

                # Full width for Painel, Chassi, Motor
                for slot in slots_config[5:]:
                    img = images_by_type.get(slot["type"])
                    if img and img.content:
                        img_data = base64.b64encode(img.content).decode("utf-8")
                        img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                        slots_html.append(f"""
                        <div class="mb-4">
                            <div class="relative border-2 border-gray-300 rounded-lg p-4 bg-white hover:border-primary transition-colors cursor-pointer group" 
                                 id="slot-{slot["type"]}"
                                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                                <img src="{img_src}" alt="{slot["label"]}" class="w-full h-40 object-contain rounded mb-2">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                       onchange="previewSlotImage('{slot["type"]}', this)">
                                <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                                <button type="button" 
                                        onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                        class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <span class="material-icons text-xs">delete</span>
                                </button>
                            </div>
                        </div>
                        """)
                    else:
                        placeholder_src = slot_placeholder_urls[slot["type"]]
                        slots_html.append(f"""
                        <div class="mb-4">
                            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                                 id="slot-{slot["type"]}"
                                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                                <div class="flex flex-col items-center justify-center h-40">
                                    <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-24 object-contain rounded mb-2 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                    <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                                </div>
                                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                       onchange="previewSlotImage('{slot["type"]}', this)">
                            </div>
                        </div>
                        """)

                # Additional images (type=ADDITIONAL)
                additional_images_html = []
                for img in additional_images:
                    if img.content:
                        file_name = escape(img.content_name or f"Arquivo {img.id}")
                        file_size = _format_file_size(len(img.content or b""))
                        additional_images_html.append(f"""
                        <div class="flex items-center justify-between gap-3 border border-gray-200 rounded-lg px-3 py-2 hover:border-primary transition-colors" id="additional-image-{img.id}">
                            <div class="min-w-0 flex-1">
                                <p class="text-sm font-semibold text-gray-700 truncate" title="{file_name}">{file_name}</p>
                                <p class="text-xs text-gray-500">{file_size}</p>
                            </div>
                            <input type="hidden" name="images_to_delete" value="" id="delete-flag-{img.id}">
                            <button type="button" 
                                    onclick="document.getElementById('delete-flag-{img.id}').value='{img.id}'; document.getElementById('additional-image-{img.id}').classList.add('opacity-50'); this.disabled=true; this.textContent='Será excluído';"
                                    class="btn btn-xs btn-error text-white"
                                    title="Marcar para exclusão">
                                Excluir
                            </button>
                        </div>
                        """)

                # Inject JavaScript for image preview and deletion
                slots_html_joined = "".join(slots_html)
                additional_html_joined = "".join(additional_images_html)

                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        function renderBudgetStep3Images() {{
                            const slotsContainer = document.getElementById('vehicle-images-slots');
                            const additionalContainer = document.getElementById('additional-images-container');
                            if (!slotsContainer || !additionalContainer) {{
                                return;
                            }}
                            if (slotsContainer.children.length > 0) {{
                                return;
                            }}
                            slotsContainer.innerHTML = `{slots_html_joined}`;
                            if (additionalContainer.children.length === 0) {{
                                additionalContainer.innerHTML = `{additional_html_joined}`;
                            }}
                        }}

                        renderBudgetStep3Images();
                        window.setTimeout(renderBudgetStep3Images, 0);

                        const slotPlaceholders = {slot_placeholder_urls_js};
                        function getSlotHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-48';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-40';
                            return 'h-32';
                        }}

                        function getSlotEmptyImageHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-32';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-24';
                            return 'h-16';
                        }}

                        function getSlotHintMarginClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}' || slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return ' mt-1';
                            return '';
                        }}

                        function removeNewSlotImage(slotType) {{
                            const slotDiv = document.getElementById('slot-' + slotType);
                            const input = document.getElementById('file-input-' + slotType);
                            if (!slotDiv || !input) {{
                                return;
                            }}

                            const labelElement = slotDiv.querySelector('p');
                            const label = labelElement ? labelElement.textContent : '';
                            const height = getSlotHeightClass(slotType);
                            const imageHeight = getSlotEmptyImageHeightClass(slotType);
                            const hintMargin = getSlotHintMarginClass(slotType);
                            const placeholderSrc = slotPlaceholders[slotType] || '';

                            input.value = '';
                            slotDiv.classList.remove('bg-white', 'opacity-50');
                            slotDiv.classList.add('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');

                            slotDiv.innerHTML = `
                                <div class="flex flex-col items-center justify-center ${{height}}">
                                    <img src="${{placeholderSrc}}" alt="Placeholder ${{label}}" class="w-full ${{imageHeight}} object-contain rounded mb-1 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                    <p class="text-center text-xs text-gray-400${{hintMargin}}">Clique para adicionar</p>
                                </div>
                            `;

                            slotDiv.appendChild(input);
                        }}
                        
                        function previewSlotImage(slotType, input) {{
                            if (input.files && input.files[0]) {{
                                const reader = new FileReader();
                                reader.onload = function(e) {{
                                    const slotDiv = document.getElementById('slot-' + slotType);
                                    const label = slotDiv.querySelector('p').textContent;
                                    const height = getSlotHeightClass(slotType);
                                    slotDiv.innerHTML = `
                                        <img src="${{e.target.result}}" alt="${{label}}" class="w-full ${{height}} object-contain rounded mb-2">
                                        <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                        <button type="button"
                                                onclick="event.stopPropagation(); removeNewSlotImage('${{slotType}}')"
                                                class="absolute top-2 right-2 btn btn-xs btn-error text-white"
                                                title="Remover imagem">
                                            <span class="material-icons text-xs">delete</span>
                                        </button>
                                        <div class="absolute top-2 left-2 badge badge-success gap-1">
                                            <span class="material-icons text-xs">check</span>
                                            Nova
                                        </div>
                                    `;
                                    slotDiv.classList.remove('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');
                                    slotDiv.classList.add('border-gray-300', 'bg-white');
                                    slotDiv.classList.remove('opacity-50');
                                    
                                    // Re-attach the input element
                                    slotDiv.appendChild(input);
                                }};
                                reader.readAsDataURL(input.files[0]);
                            }}
                        }}
                        
                        function deleteSlotImage(slotType, imageId) {{
                            const slotDiv = document.getElementById('slot-' + slotType);
                            const label = slotDiv.querySelector('p').textContent;
                            
                            // Mark for deletion
                            const deleteInput = document.getElementById('delete-slot-' + slotType) || document.createElement('input');
                            deleteInput.type = 'hidden';
                            deleteInput.name = 'slot_to_delete';
                            deleteInput.id = 'delete-slot-' + slotType;
                            deleteInput.value = imageId;
                            slotDiv.appendChild(deleteInput);
                            
                            // Replace with empty slot
                            slotDiv.classList.add('border-dashed', 'bg-gray-50', 'hover:bg-gray-100', 'opacity-50');
                            const height = getSlotHeightClass(slotType);
                            const placeholderSrc = slotPlaceholders[slotType] || '';
                            slotDiv.innerHTML = `
                                <div class="flex flex-col items-center justify-center ${{height}}">
                                    <img src="${{placeholderSrc}}" alt="Placeholder ${{label}}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                    <p class="text-center text-xs text-error">Será removida (clique para substituir)</p>
                                </div>
                                <input type="file" id="file-input-${{slotType}}" name="image_${{slotType}}" accept="image/*" class="hidden" onchange="previewSlotImage('${{slotType}}', this)">
                            `;
                            slotDiv.appendChild(deleteInput);
                        }}
                    </script>
                    """)
                )
            else:
                # No existing images, show empty slots
                slots_config = SLOT_LAYOUT_CONFIG

                slots_html = []

                # Principal (full width)
                slot = slots_config[0]
                placeholder_src = slot_placeholder_urls[slot["type"]]
                slots_html.append(f"""
                <div class="mb-4">
                    <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                         id="slot-{slot["type"]}"
                         onclick="document.getElementById('file-input-{slot["type"]}').click()">
                        <div class="flex flex-col items-center justify-center h-48">
                            <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-32 object-contain rounded mb-2 opacity-40">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                        </div>
                        <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                               onchange="previewSlotImage('{slot["type"]}', this)">
                    </div>
                </div>
                """)

                # Two columns grid
                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[1:3]:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                         id="slot-{slot["type"]}"
                         onclick="document.getElementById('file-input-{slot["type"]}').click()">
                        <div class="flex flex-col items-center justify-center h-32">
                            <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                        </div>
                        <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                               onchange="previewSlotImage('{slot["type"]}', this)">
                    </div>
                    """)
                slots_html.append("</div>")

                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[3:5]:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                         id="slot-{slot["type"]}"
                         onclick="document.getElementById('file-input-{slot["type"]}').click()">
                        <div class="flex flex-col items-center justify-center h-32">
                            <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                        </div>
                        <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                               onchange="previewSlotImage('{slot["type"]}', this)">
                    </div>
                    """)
                slots_html.append("</div>")

                # Full width for remaining
                for slot in slots_config[5:]:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="mb-4">
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-40">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-24 object-contain rounded mb-2 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                    </div>
                    """)

                slots_html_joined = "".join(slots_html)

                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        function renderBudgetStep3EmptySlots() {{
                            const slotsContainer = document.getElementById('vehicle-images-slots');
                            if (!slotsContainer) {{
                                return;
                            }}
                            if (slotsContainer.children.length > 0) {{
                                return;
                            }}
                            slotsContainer.innerHTML = `{slots_html_joined}`;
                        }}

                        renderBudgetStep3EmptySlots();
                        window.setTimeout(renderBudgetStep3EmptySlots, 0);

                        const slotPlaceholders = {slot_placeholder_urls_js};
                        function getSlotHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-48';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-40';
                            return 'h-32';
                        }}

                        function getSlotEmptyImageHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-32';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-24';
                            return 'h-16';
                        }}

                        function getSlotHintMarginClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}' || slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return ' mt-1';
                            return '';
                        }}

                        function removeNewSlotImage(slotType) {{
                            const slotDiv = document.getElementById('slot-' + slotType);
                            const input = document.getElementById('file-input-' + slotType);
                            if (!slotDiv || !input) {{
                                return;
                            }}

                            const labelElement = slotDiv.querySelector('p');
                            const label = labelElement ? labelElement.textContent : '';
                            const height = getSlotHeightClass(slotType);
                            const imageHeight = getSlotEmptyImageHeightClass(slotType);
                            const hintMargin = getSlotHintMarginClass(slotType);
                            const placeholderSrc = slotPlaceholders[slotType] || '';

                            input.value = '';
                            slotDiv.classList.remove('bg-white', 'opacity-50');
                            slotDiv.classList.add('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');

                            slotDiv.innerHTML = `
                                <div class="flex flex-col items-center justify-center ${{height}}">
                                    <img src="${{placeholderSrc}}" alt="Placeholder ${{label}}" class="w-full ${{imageHeight}} object-contain rounded mb-1 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                    <p class="text-center text-xs text-gray-400${{hintMargin}}">Clique para adicionar</p>
                                </div>
                            `;

                            slotDiv.appendChild(input);
                        }}
                        
                        function previewSlotImage(slotType, input) {{
                            if (input.files && input.files[0]) {{
                                const reader = new FileReader();
                                reader.onload = function(e) {{
                                    const slotDiv = document.getElementById('slot-' + slotType);
                                    const label = slotDiv.querySelector('p').textContent;
                                    const height = getSlotHeightClass(slotType);
                                    
                                    slotDiv.innerHTML = `
                                        <img src="${{e.target.result}}" alt="${{label}}" class="w-full ${{height}} object-contain rounded mb-2">
                                        <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                        <button type="button"
                                                onclick="event.stopPropagation(); removeNewSlotImage('${{slotType}}')"
                                                class="absolute top-2 right-2 btn btn-xs btn-error text-white"
                                                title="Remover imagem">
                                            <span class="material-icons text-xs">delete</span>
                                        </button>
                                        <div class="absolute top-2 left-2 badge badge-success gap-1">
                                            <span class="material-icons text-xs">check</span>
                                            Nova
                                        </div>
                                    `;
                                    slotDiv.classList.remove('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');
                                    slotDiv.classList.add('border-gray-300', 'bg-white');
                                    slotDiv.classList.remove('opacity-50');
                                    
                                    // Re-attach the input element
                                    slotDiv.appendChild(input);
                                }};
                                reader.readAsDataURL(input.files[0]);
                            }}
                        }}
                    </script>
                    """)
                )

    def clean(self):
        cleaned_data = super().clean()

        if not self.files:
            return cleaned_data

        new_additional_images = self.files.getlist("images")
        if new_additional_images:
            _validate_uploaded_files(new_additional_images)

        uploaded_slot_files = []
        uploaded_slot_types = set()
        for slot_type in SLOT_IMAGE_TYPES:
            uploaded_file = self.files.get(f"image_{slot_type}")
            if uploaded_file:
                uploaded_slot_files.append(uploaded_file)
                uploaded_slot_types.add(slot_type)

        if uploaded_slot_files:
            _validate_uploaded_images(uploaded_slot_files)

        if self.instance and self.instance.pk:
            existing_images = self.instance.budget_image.all()
            existing_additional_count = existing_images.exclude(image_type__in=SLOT_IMAGE_TYPES).count()

            additional_delete_ids = [img_id for img_id in self.request.POST.getlist("images_to_delete") if img_id.strip()]
            additional_delete_count = existing_images.filter(id__in=additional_delete_ids).exclude(image_type__in=SLOT_IMAGE_TYPES).count()

            current_slot_types = set(existing_images.filter(image_type__in=SLOT_IMAGE_TYPES).values_list("image_type", flat=True))
            slot_delete_ids = [img_id for img_id in self.request.POST.getlist("slot_to_delete") if img_id.strip()]
            slot_types_to_delete = set(existing_images.filter(id__in=slot_delete_ids, image_type__in=SLOT_IMAGE_TYPES).values_list("image_type", flat=True))

            final_slot_types = (current_slot_types - slot_types_to_delete) | uploaded_slot_types
            final_additional_count = existing_additional_count - additional_delete_count + len(new_additional_images)
            final_count = len(final_slot_types) + final_additional_count
        else:
            final_count = len(uploaded_slot_types) + len(new_additional_images)

        if final_count > MAX_BUDGET_IMAGES:
            raise forms.ValidationError(f"Máximo de {MAX_BUDGET_IMAGES} anexos permitido. Você terá {final_count} anexos após esta operação.")

        return cleaned_data

    def save(self, commit=True):
        budget = super().save(commit=commit)

        # Processamento dos Defeitos (Somente no Save final)
        if "defects_list" in self.request.POST:
            defect_names = self.request.POST.getlist("defects_list")

            # Sincronização: remove antigos e adiciona novos
            budget.defects.all().delete()
            for name in defect_names:
                if name.strip():
                    Defect.objects.create(workshop=self.workshop, budget=budget, name=name.strip())

        # Handle slot image deletions
        slots_to_delete = self.request.POST.getlist("slot_to_delete")
        if slots_to_delete:
            image_ids = [img_id for img_id in slots_to_delete if img_id.strip()]
            if image_ids:
                BudgetImage.objects.filter(id__in=image_ids, budget=budget, image_type__in=SLOT_IMAGE_TYPES).delete()

        # Handle slot image uploads (update or create)
        slot_uploads = []
        for slot_type in SLOT_IMAGE_TYPES:
            file_key = f"image_{slot_type}"
            if file_key in self.request.FILES:
                uploaded_file = self.request.FILES[file_key]
                if uploaded_file:
                    slot_uploads.append((slot_type, uploaded_file))

        if slot_uploads:
            _validate_uploaded_images([uploaded_file for _, uploaded_file in slot_uploads])
            for slot_type, uploaded_file in slot_uploads:
                # Delete existing image of this type if exists (should be handled by unique constraint)
                BudgetImage.objects.filter(budget=budget, image_type=slot_type).delete()

                # Create new image
                BudgetImage.objects.create(workshop=self.workshop, budget=budget, content=uploaded_file.read(), content_name=uploaded_file.name, content_type=getattr(uploaded_file, "content_type", "image/jpeg"), image_type=slot_type)

        # Handle additional image deletion
        images_to_delete = self.request.POST.getlist("images_to_delete")
        if images_to_delete:
            image_ids = [img_id for img_id in images_to_delete if img_id.strip()]
            if image_ids:
                BudgetImage.objects.filter(id__in=image_ids, budget=budget).exclude(image_type__in=SLOT_IMAGE_TYPES).delete()

        # Handle new additional images upload
        new_images = self.request.FILES.getlist("images")
        if new_images:
            _validate_uploaded_files(new_images)

            for new_image in new_images:
                if new_image and hasattr(new_image, "read"):
                    BudgetImage.objects.create(workshop=self.workshop, budget=budget, content=new_image.read(), content_name=new_image.name, content_type=getattr(new_image, "content_type", "application/octet-stream"), image_type=BudgetImageType.ADDITIONAL)

        return budget


class BudgetStep4Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = []
        widgets = {}

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        budget = _get_budget_with_prefetched_items(self.instance)
        rows = _render_budget_items_rows(budget, step6=False)
        products_html = rows["product"]
        services_html = rows["service"]
        kits_html = rows["kit"]

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            alert_confirm_layout(),
            HTML(
                """
                <style>
                    .budget-step4-table {
                        table-layout: fixed;
                    }

                    .budget-step4-table :where(th, td) {
                        vertical-align: middle;
                    }

                    .budget-step4-table .budget-step4-description,
                    .budget-step4-table .budget-step4-application {
                        white-space: normal;
                        overflow-wrap: break-word;
                        word-break: normal;
                    }

                    .budget-step4-table .budget-step4-actions {
                        white-space: nowrap;
                    }

                    .budget-step4-table .budget-step4-select-col {
                        width: 3.25rem;
                    }
                </style>
                """
            ),
            Div(
                # Coluna Esquerda: Seleção
                Div(
                    HTML('<h2 class="text-2xl font-bold mb-6">Seleção de Produtos e Serviços</h2>'),
                    # Seção de Produtos
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Produtos</h3>'),
                            HTML(f'''
                                <div class="flex flex-wrap gap-2 w-full sm:w-auto justify-end">
                                    <button
                                        type="button"
                                        id="delete-selected-products-btn"
                                        class="btn btn-error btn-outline w-full sm:w-auto hidden"
                                        disabled
                                        hx-post="{reverse("budget:remove_products_batch", kwargs={"budget_id": budget.pk})}"
                                        hx-include="#product-list-body input[name='selected_product_items']:checked"
                                        data-confirm="Deseja remover as peças selecionadas?">
                                        Deletar todos
                                    </button>
                                    <button
                                        type="button"
                                        class="btn btn-primary w-full sm:w-auto"
                                        hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "product"})}"
                                        hx-target="#modal-container"
                                        onclick="form_modal.showModal()">
                                        Inserir Produto
                                    </button>
                                </div>
                            '''),
                            css_class="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-sm table-zebra w-full budget-step4-table">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="budget-step4-select-col text-center">
                                                <input type="checkbox" id="select-all-products" class="checkbox checkbox-primary checkbox-sm" aria-label="Selecionar todas as peças">
                                            </th>
                                            <th class="w-[18%] text-left">DESCRIÇÃO</th>
                                            <th class="w-[18%] text-left">APLICAÇÃO</th>
                                            <th class="w-[8%] text-center">QTD.</th>
                                            <th class="w-[10%] text-right">CUSTO</th>
                                            <th class="w-[12%] text-right">VALOR VENDA</th>
                                            <th class="w-[10%] text-right">FRETE</th>
                                            <th class="w-[12%] text-right">TOTAL</th>
                                            <th class="w-[12%] text-center budget-step4-actions">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="product-list-body">
                                        {products_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="mb-8 rounded-lg shadow-md shadow-gray-300/50 overflow-x-auto",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Serviços
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Serviços</h3>'),
                            HTML(f'''
                                <div class="flex flex-wrap gap-2 w-full sm:w-auto justify-end">
                                    <button
                                        type="button"
                                        id="delete-selected-services-btn"
                                        class="btn btn-error btn-outline w-full sm:w-auto hidden"
                                        disabled
                                        hx-post="{reverse("budget:remove_services_batch", kwargs={"budget_id": budget.pk})}"
                                        hx-include="#service-list-body input[name='selected_service_items']:checked"
                                        data-confirm="Deseja remover os serviços selecionados?">
                                        Deletar todos
                                    </button>
                                    <button
                                        type="button"
                                        class="btn btn-primary w-full sm:w-auto"
                                        hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "service"})}"
                                        hx-target="#modal-container"
                                        onclick="form_modal.showModal()">
                                        Inserir Serviço
                                    </button>
                                </div>
                            '''),
                            css_class="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-sm table-zebra w-full budget-step4-table">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="budget-step4-select-col text-center">
                                                <input type="checkbox" id="select-all-services" class="checkbox checkbox-primary checkbox-sm" aria-label="Selecionar todos os serviços">
                                            </th>
                                            <th class="w-[24%] text-left">DESCRIÇÃO</th>
                                            <th class="w-[8%] text-center">QTD.</th>
                                            <th class="w-[12%] text-right">CUSTO</th>
                                            <th class="w-[14%] text-right">VALOR VENDA</th>
                                            <th class="w-[10%] text-center">TEMPO</th>
                                            <th class="w-[14%] text-right">TOTAL</th>
                                            <th class="w-[12%] text-center budget-step4-actions">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="service-list-body">
                                        {services_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="mb-8 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Kits
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Kits</h3>'),
                            HTML(f'''
                                <div class="flex flex-wrap gap-2 w-full sm:w-auto justify-end">
                                    <button
                                        type="button"
                                        id="delete-selected-kits-btn"
                                        class="btn btn-error btn-outline w-full sm:w-auto hidden"
                                        disabled
                                        hx-post="{reverse("budget:remove_kits_batch", kwargs={"budget_id": budget.pk})}"
                                        hx-include="#kit-list-body input[name='selected_kit_items']:checked"
                                        data-confirm="Deseja remover os kits selecionados?">
                                        Deletar todos
                                    </button>
                                    <button
                                        type="button"
                                        class="btn btn-primary w-full sm:w-auto"
                                        hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "kit"})}"
                                        hx-target="#modal-container"
                                        onclick="form_modal.showModal()">
                                        Inserir Kit
                                    </button>
                                </div>
                            '''),
                            css_class="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-sm w-full budget-step4-table">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="budget-step4-select-col text-center">
                                                <input type="checkbox" id="select-all-kits" class="checkbox checkbox-primary checkbox-sm" aria-label="Selecionar todos os kits">
                                            </th>
                                            <th class="w-[22%] text-left">NOME</th>
                                            <th class="w-[8%] text-center">QTD.</th>
                                            <th class="w-[10%] text-center">PRODUTOS</th>
                                            <th class="w-[10%] text-center">SERVIÇOS</th>
                                            <th class="w-[14%] text-right">CUSTOS</th>
                                            <th class="w-[14%] text-right">PREÇO</th>
                                            <th class="w-[12%] text-center budget-step4-actions">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="kit-list-body">
                                        {kits_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="mb-4 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden",
                        ),
                        css_class="mb-6",
                    ),
                    css_class="col-span-12 xl:col-span-7",
                ),
                #
                Div(css_class="hidden xl:block xl:col-span-1"),
                #
                # Coluna Direita
                Div(
                    Div(
                        HTML('<h2 class="text-2xl font-bold mb-4 mt-8">Resumo</h2>'),
                        Div(
                            HTML(render_to_string("budget/partials/components/budget_summary.html", {"budget": budget})),
                            css_class="sticky top-4",
                            css_id="budget-summary",
                        ),
                        css_class="p-6 h-fit text-lg",
                    ),
                    css_class="col-span-12 xl:col-span-4 mt-10 xl:mt-0",
                ),
                css_class="grid grid-cols-1 xl:grid-cols-12 gap-4",
            ),
        )

        # Adicionar listener para atualizar resumo dinamicamente
        self.helper.layout.append(
            HTML(f"""
            <script>
            (function() {{
                document.body.addEventListener('update-summary', function() {{
                    // Recarrega apenas a coluna de resumo via HTMX
                    htmx.ajax('GET', '{reverse("budget:budget_summary", kwargs={"budget_id": budget.pk})}', {{
                        target: '#budget-summary',
                        swap: 'innerHTML'
                    }});
                }});

                function setupBatchDeleteSelection(config) {{
                    const listBody = document.getElementById(config.listBodyId);
                    const selectAll = document.getElementById(config.selectAllId);
                    const deleteBtn = document.getElementById(config.deleteBtnId);

                    if (!listBody || !selectAll || !deleteBtn) {{
                        return;
                    }}

                    function getCheckboxes() {{
                        return Array.from(listBody.querySelectorAll(config.checkboxSelector));
                    }}

                    function updateState() {{
                        const checkboxes = getCheckboxes();
                        const selectedCount = checkboxes.filter((cb) => cb.checked).length;

                        const canDeleteBatch = selectedCount > 1;
                        deleteBtn.classList.toggle('hidden', !canDeleteBatch);
                        deleteBtn.disabled = !canDeleteBatch;

                        if (checkboxes.length === 0) {{
                            selectAll.checked = false;
                            selectAll.indeterminate = false;
                            selectAll.disabled = true;
                            return;
                        }}

                        selectAll.disabled = false;
                        const allChecked = selectedCount === checkboxes.length;
                        const someChecked = selectedCount > 0 && !allChecked;
                        selectAll.checked = allChecked;
                        selectAll.indeterminate = someChecked;
                    }}

                    selectAll.addEventListener('change', function(event) {{
                        const checkboxes = getCheckboxes();
                        checkboxes.forEach((checkbox) => {{
                            checkbox.checked = event.target.checked;
                        }});
                        updateState();
                    }});

                    listBody.addEventListener('change', function(event) {{
                        if (!event.target.matches(config.checkboxSelector)) {{
                            return;
                        }}
                        updateState();
                    }});

                    listBody.addEventListener('htmx:afterSwap', function() {{
                        updateState();
                    }});

                    updateState();
                }}

                setupBatchDeleteSelection({{
                    listBodyId: 'product-list-body',
                    selectAllId: 'select-all-products',
                    deleteBtnId: 'delete-selected-products-btn',
                    checkboxSelector: '.budget-product-select',
                }});

                setupBatchDeleteSelection({{
                    listBodyId: 'service-list-body',
                    selectAllId: 'select-all-services',
                    deleteBtnId: 'delete-selected-services-btn',
                    checkboxSelector: '.budget-service-select',
                }});

                setupBatchDeleteSelection({{
                    listBodyId: 'kit-list-body',
                    selectAllId: 'select-all-kits',
                    deleteBtnId: 'delete-selected-kits-btn',
                    checkboxSelector: '.budget-kit-select',
                }});
            }})();
            </script>
            """)
        )

    def save(self, commit=True):
        # Como este form é estrutural, o save lida com persistência de estado da etapa
        return super().save(commit=commit)


class BudgetStep5Form(forms.ModelForm):
    slider = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={"class": "w-full centered-range", "type": "range", "min": "-100", "max": "100", "step": "5"}))

    class Meta:
        model = Budget
        fields = ["discount_percentage", "discount_value", "slider"]
        widgets = {
            "discount_percentage": PercentageInput(decimal_places=2, behavior="digit_stream"),
            "discount_value": MoneyInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.fields["slider"].label = ""
        self.fields["slider"].help_text = ""
        self.fields["discount_percentage"].required = False
        self.fields["discount_value"].required = False
        self.fields["slider"].widget.attrs.update({"hx-post": reverse("budget:update_slider", args=[self.instance.pk]), "hx-trigger": "change", "hx-swap": "none"})

        budget = _get_budget_with_prefetched_items(self.instance)

        dados = {}
        if budget.pk:
            self.fields["slider"].initial = budget.slider
            dados = budget.calculate_pricing_methods()

        zerado = Money(0, "BRL")

        # Custos baseados sempre nos itens do orçamento
        custo_pecas = budget.total_costs_products_value
        custo_frete_pecas = budget.total_products_shipping
        custo_servico_terceiros = budget.total_third_party_services_cost
        custo_hora_mecanico = dados.get("custo_hora_mecanico") or zerado

        duracao_total = budget.total_duration_display

        def parse_duracao_em_horas(duracao):
            try:
                h, m = duracao.replace("h", "").replace("m", "").split()
                return Decimal(h) + (Decimal(m) / Decimal(60))
            except Exception:
                return Decimal("0")

        duracao_em_horas = parse_duracao_em_horas(duracao_total)
        custo_total_mao_obra = custo_hora_mecanico * duracao_em_horas

        # Valores de venda baseados sempre nos itens do orçamento
        venda_servico_terceiros = budget.total_third_party_services_selling
        venda_pecas = budget.get_total_products_by_slider
        venda_mao_obra = budget.get_total_labor_by_slider

        # Extra
        metodo_precificacao = dados.get("method_name") or ""
        lucro_operacional = dados.get("lucro_operacional") or zerado
        rentabilidade = dados.get("rentabilidade") or 0
        mlr = budget.get_mlr
        mlo = budget.get_mlo

        if rentabilidade >= 70:
            status_texto = "Bom"
            rentabilidade_class = "rentabilidade-bom"
            rentabilidade_bg = "bg-rentabilidade-bom"
        elif rentabilidade < 60:
            status_texto = "Ruim"
            rentabilidade_class = "rentabilidade-ruim"
            rentabilidade_bg = "bg-rentabilidade-ruim"
        else:
            status_texto = "Médio"
            rentabilidade_class = "rentabilidade-medio"
            rentabilidade_bg = "bg-rentabilidade-medio"

        discount_amount = budget.resolved_discount_value.amount if budget.resolved_discount_value else Decimal("0")
        discount_display = budget.resolved_discount_value if discount_amount != Decimal("0") else Money(0, "BRL")
        self.initial["discount_percentage"] = budget.resolved_discount_percentage
        self.initial["discount_value"] = budget.resolved_discount_value
        step5_calculation_done = bool(budget.pk and (budget.step5_calculation_viewed or budget.current_step > 5))
        step5_loading_hidden_class = "hidden" if step5_calculation_done else ""
        step5_method_hidden_class = "" if step5_calculation_done else "hidden"
        step5_should_block_next_button = "true" if not step5_calculation_done else "false"
        step5_calculated_input_value = "1" if step5_calculation_done else "0"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
            <style>
                :root[data-theme="light"] {{
                  --step5-accent: #0f766e;
                  --step5-warning-soft: rgba(245, 158, 11, 0.16);
                }}

                :root[data-theme="dark"] {{
                  --step5-accent: #5eead4;
                  --step5-warning-soft: rgba(245, 158, 11, 0.22);
                }}

                input[type="range"].centered-range {{
                  -webkit-appearance: none;
                  -moz-appearance: none;
                  width: 100%;
                  height: 8px;
                  background: transparent;
                }}

                input[type="range"].centered-range::-webkit-slider-runnable-track {{
                  height: 8px;
                  border-radius: 999px;
                  background: linear-gradient(
                    to right,
                    #e5e7eb var(--left),
                    #2563eb var(--left),
                    #2563eb var(--right),
                    #e5e7eb var(--right)
                  );
                }}

                input[type="range"].centered-range::-webkit-slider-thumb {{
                  -webkit-appearance: none;
                  width: 24px;
                  height: 24px;
                  background: #007bff;
                  border-radius: 50%;
                  margin-top: -8px;
                  cursor: pointer;
                }}

                input[type="range"].centered-range::-moz-range-track {{
                  height: 8px;
                  border-radius: 999px;
                  background: linear-gradient(
                    to right,
                    #e5e7eb var(--left),
                    #2563eb var(--left),
                    #2563eb var(--right),
                    #e5e7eb var(--right)
                  );
                }}

                input[type="range"].centered-range::-moz-range-thumb {{
                  width: 24px;
                  height: 24px;
                  background: #007bff;
                  border-radius: 50%;
                  border: none;
                }}

                .step5-accent-text {{
                    color: var(--step5-accent);
                }}

                .step5-accent-border {{
                    border-color: var(--step5-accent);
                }}

                .step5-warning-surface {{
                    background-color: var(--step5-warning-soft);
                }}

                .step5-calculating-dot {{
                    animation: step5-loading-blink 1s infinite;
                }}

                .step5-calculating-dot:nth-child(2) {{
                    animation-delay: 0.2s;
                }}

                .step5-calculating-dot:nth-child(3) {{
                    animation-delay: 0.4s;
                }}

                @keyframes step5-loading-blink {{
                    0%, 80%, 100% {{
                        opacity: 0.2;
                    }}
                    40% {{
                        opacity: 1;
                    }}
                }}
                /* Cores de Rentabilidade */
                .rentabilidade-bom {{ color: #22c55e !important; border-color: #22c55e !important; }}
                .rentabilidade-medio {{ color: #f59e0b !important; border-color: #f59e0b !important; }} 
                .rentabilidade-ruim {{ color: #ef4444 !important; border-color: #ef4444 !important; }}
                
                .bg-rentabilidade-bom {{ background-color: rgba(34, 197, 94, 0.1); }}
                .bg-rentabilidade-medio {{ background-color: rgba(245, 158, 11, 0.1); }}
                .bg-rentabilidade-ruim {{ background-color: rgba(239, 68, 68, 0.1); }}
            </style>
            <script>
                    (function() {{
                        console.log("Método de Precificação:", "{metodo_precificacao}");
                        let timeout = null;

                        function parseDotDecimal(value) {{
                            const normalized = String(value ?? '').trim().replace(',', '.');
                            if (!normalized) return 0;
                            const parsed = Number.parseFloat(normalized);
                            return Number.isFinite(parsed) ? parsed : 0;
                        }}

                        function clamp(value, min, max) {{
                            return Math.min(Math.max(value, min), max);
                        }}

                        function roundCurrency(value) {{
                            return Math.round((value + Number.EPSILON) * 100) / 100;
                        }}

                        function formatMoney(value) {{
                            return value.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                        }}

                        function formatFraction(fraction) {{
                            return fraction.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
                        }}

                        function formatPercentageDisplay(fraction) {{
                            return (fraction * 100).toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                        }}

                        function getDiscountElements() {{
                            const displayMoney = document.getElementById('id_discount_value_0_display');
                            const hiddenMoney = document.getElementById('id_discount_value_0');
                            const displayPercentage = document.getElementById('id_discount_percentage_display');
                            const hiddenPercentage = document.getElementById('id_discount_percentage');
                            const subtotalDisplay = document.getElementById('step5-subtotal-display');
                            const discountDisplay = document.getElementById('step5-discount-display');
                            const totalDisplay = document.getElementById('valor-final-display');

                            if (!displayMoney || !hiddenMoney || !displayPercentage || !hiddenPercentage || !subtotalDisplay || !discountDisplay || !totalDisplay) {{
                                return null;
                            }}

                            return {{
                                displayMoney,
                                hiddenMoney,
                                displayPercentage,
                                hiddenPercentage,
                                subtotalDisplay,
                                discountDisplay,
                                totalDisplay,
                            }};
                        }}

                        function getBaseTotal(elements) {{
                            return parseDotDecimal(elements.subtotalDisplay.dataset.baseTotal);
                        }}

                        function updateSummary(elements, discountAmount) {{
                            const baseTotal = getBaseTotal(elements);
                            const resolvedDiscount = clamp(roundCurrency(discountAmount), 0, baseTotal);
                            const totalValue = roundCurrency(baseTotal - resolvedDiscount);

                            elements.discountDisplay.textContent = `R$ ${{formatMoney(resolvedDiscount)}}`;
                            elements.totalDisplay.textContent = `R$ ${{formatMoney(totalValue)}}`;
                        }}

                        function syncFromPercentage(elements) {{
                            const baseTotal = getBaseTotal(elements);
                            const fraction = clamp(parseDotDecimal(elements.hiddenPercentage.value), 0, 1);
                            const amount = baseTotal > 0 ? clamp(roundCurrency(baseTotal * fraction), 0, baseTotal) : 0;

                            elements.hiddenMoney.value = amount.toFixed(2);
                            elements.displayMoney.value = formatMoney(amount);
                            elements.hiddenPercentage.value = formatFraction(fraction);
                            updateSummary(elements, amount);
                        }}

                        function syncFromValue(elements, updateSourceDisplay = true) {{
                            const baseTotal = getBaseTotal(elements);
                            const amount = clamp(roundCurrency(parseDotDecimal(elements.hiddenMoney.value)), 0, baseTotal);
                            const fraction = baseTotal > 0 ? clamp(amount / baseTotal, 0, 1) : 0;

                            elements.hiddenMoney.value = amount.toFixed(2);
                            if (updateSourceDisplay) {{
                                elements.displayMoney.value = formatMoney(amount);
                            }}
                            elements.hiddenPercentage.value = formatFraction(fraction);
                            elements.displayPercentage.value = formatPercentageDisplay(fraction);
                            updateSummary(elements, amount);
                        }}

                        function persistDiscount(elements) {{
                            clearTimeout(timeout);
                            timeout = setTimeout(() => {{
                                htmx.ajax('POST', '{{% url "budget:update_budget_discount" {self.instance.pk} %}}', {{
                                    values: {{
                                        "discount_value_0": elements.hiddenMoney.value,
                                        "discount_percentage": elements.hiddenPercentage.value,
                                    }},
                                    swap: 'none',
                                }});
                            }}, 800);
                        }}

                        function bindDiscountSync() {{
                            const elements = getDiscountElements();
                            if (!elements) return;

                            if (elements.displayMoney.dataset.discountSyncBound !== 'true') {{
                                const handleMoneyInput = () => {{
                                    window.setTimeout(() => {{
                                        syncFromValue(elements, false);
                                        persistDiscount(elements);
                                    }}, 0);
                                }};
                                elements.displayMoney.addEventListener('input', handleMoneyInput);
                                elements.displayMoney.addEventListener('blur', handleMoneyInput);
                                elements.displayMoney.dataset.discountSyncBound = 'true';
                            }}

                            if (elements.hiddenPercentage.dataset.discountSyncBound !== 'true') {{
                                const handlePercentageInput = () => {{
                                    window.setTimeout(() => {{
                                        syncFromPercentage(elements);
                                        persistDiscount(elements);
                                    }}, 0);
                                }};
                                elements.hiddenPercentage.addEventListener('widget:formatted-change', handlePercentageInput);
                                elements.hiddenPercentage.dataset.discountSyncBound = 'true';
                            }}

                            if (parseDotDecimal(elements.hiddenPercentage.value) > 0) {{
                                syncFromPercentage(elements);
                                return;
                            }}

                            syncFromValue(elements);
                        }}

                        document.addEventListener('DOMContentLoaded', bindDiscountSync);
                        document.body.addEventListener('htmx:afterSettle', bindDiscountSync);
                    }})();

                    (function () {{
                        function initCalculationGate() {{
                            const calculateButton = document.getElementById('step5-calculate-values-btn');
                            const calculationStatus = document.getElementById('step5-calculation-status');
                            const loadingCard = document.getElementById('step5-calc-loader-card');
                            const methodCard = document.getElementById('step5-method-card');
                            const controlsCard = document.getElementById('step5-controls-card');
                            const submitButton = document.getElementById('budget-submit-btn');
                            const calculatedInput = document.getElementById('id_step5_calculated');
                            const shouldBlockNextStep = {step5_should_block_next_button};

                            if (!calculateButton || !loadingCard || !methodCard || !controlsCard || calculateButton.dataset.initialized === 'true') return;

                            if (submitButton && shouldBlockNextStep) {{
                                submitButton.disabled = true;
                                submitButton.classList.add('btn-disabled');
                            }}

                            calculateButton.dataset.initialized = 'true';

                            calculateButton.addEventListener('click', async () => {{
                                if (calculateButton.disabled) return;

                                if (calculatedInput) {{
                                    calculatedInput.value = '1';
                                }}

                                calculateButton.disabled = true;
                                calculateButton.classList.add('btn-disabled');

                                const label = calculateButton.querySelector('[data-step5-calc-label]');
                                if (label) {{
                                    label.textContent = 'Calculando...';
                                }}

                                if (calculationStatus) {{
                                    calculationStatus.classList.remove('hidden');
                                    calculationStatus.classList.add('flex');
                                }}

                                try {{
                                    await fetch('{reverse("budget:mark_step5_calculation_viewed", args=[self.instance.pk])}', {{
                                        method: 'POST',
                                        headers: {{
                                            'X-CSRFToken': '{{{{ csrf_token }}}}',
                                            'X-Requested-With': 'XMLHttpRequest',
                                        }},
                                    }});
                                }} catch (error) {{
                                    console.error('Erro ao marcar calculo do step 5:', error);
                                }}

                                window.setTimeout(() => {{
                                    loadingCard.classList.add('hidden');
                                    methodCard.classList.remove('hidden');
                                    controlsCard.classList.remove('hidden');

                                    if (submitButton) {{
                                        submitButton.disabled = false;
                                        submitButton.classList.remove('btn-disabled');
                                    }}

                                    if (typeof window.step5InitSlider === 'function') {{
                                        window.step5InitSlider();
                                    }}
                                }}, 5000);
                            }});
                        }}

                        document.addEventListener('DOMContentLoaded', initCalculationGate);
                        document.body.addEventListener('htmx:afterSettle', initCalculationGate);
                    }})();

                    (function () {{
                        window.step5InitSlider = function initSlider() {{
                            const slider = document.querySelector('input[name="slider"]');
                            const labelPecaPct = document.getElementById('val-peca');
                            const labelMOPct = document.getElementById('val-mo');
                            const vendaPecaEl = document.getElementById('display-venda-pecas');
                            const vendaMOEl = document.getElementById('display-venda-mo');
                    
                            if (!slider || !vendaPecaEl || !vendaMOEl) return;
                    
                            const basePeca = parseFloat(vendaPecaEl.dataset.baseVal);
                            const baseMO = parseFloat(vendaMOEl.dataset.baseVal);
                            const costPeca = parseFloat(vendaPecaEl.dataset.costVal);
                            const fretePeca = parseFloat(vendaPecaEl.dataset.freteVal || 0);
                            const minVendaPeca = costPeca + fretePeca;
                            const costMO = parseFloat(vendaMOEl.dataset.costVal);
                    
                            const totalLucro = Math.max(
                                (basePeca + baseMO) - (minVendaPeca + costMO),
                                0
                            );
                    
                            const format = (v) =>
                                "R$ " + v.toLocaleString("pt-BR", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                            );
                    
                            function updateFill(val) {{
                                const min = -100;
                                const max = 100;
                                const center = 50;
                                const percent = ((val - min) / (max - min)) * 100;
                    
                                if (val === 0) {{
                                    slider.style.setProperty('--left', `${{center}}%`);
                                    slider.style.setProperty('--right', `${{center}}%`);
                                }} else if (val < 0) {{
                                    slider.style.setProperty('--left', `${{percent}}%`);
                                    slider.style.setProperty('--right', `${{center}}%`);
                                }} else {{
                                    slider.style.setProperty('--left', `${{center}}%`);
                                    slider.style.setProperty('--right', `${{percent}}%`);
                                }}
                            }}
                    
                            function update(val) {{
                                labelPecaPct.textContent = val < 0 ? Math.abs(val) : 0;
                                labelMOPct.textContent = val > 0 ? val : 0;
                    
                                updateFill(val);
                            }}
                    
                            slider.addEventListener('input', e => update(e.target.value));
                            update(slider.value || 0);
                        }};
                    
                        document.addEventListener('DOMContentLoaded', window.step5InitSlider);
                        document.body.addEventListener('htmx:afterSettle', window.step5InitSlider);
                    }})();
                </script>"""),
            Div(
                HTML(f'<input type="hidden" name="step5_calculated" id="id_step5_calculated" value="{step5_calculated_input_value}">'),
                HTML('<h3 class="text-2xl font-bold col-span-12">Precificação</h3>'),
                Div(
                    HTML(
                        """
                        <div class="h-full max-w-2xl mx-auto flex flex-col items-center justify-center text-center gap-4 py-12">
                            <p class="text-xl font-semibold text-base-content">A precificação deste orçamento será exibida após o cálculo.</p>
                            <button type="button" id="step5-calculate-values-btn" class="btn btn-primary btn-lg min-w-52">
                                <span data-step5-calc-label>Calcular Valores</span>
                            </button>
                            <div id="step5-calculation-status" class="hidden items-center gap-1 text-base-content/70 font-semibold" aria-live="polite">
                                <span>Calculando</span>
                                <span class="step5-calculating-dot">.</span>
                                <span class="step5-calculating-dot">.</span>
                                <span class="step5-calculating-dot">.</span>
                            </div>
                        </div>
                        """
                    ),
                    id="step5-calc-loader-card",
                    css_class=f"col-span-12 bg-base-200 p-6 rounded-2xl border-2 border-base-300 h-full text-base-content {step5_loading_hidden_class}",
                ),
                # Coluna Esquerda
                Div(
                    Div(
                        HTML('<h3 class="text-3xl font-bold mb-2 border-b-3 step5-accent-border text-center step5-accent-text">Método Hunter</h3>'),
                        Div(
                            # Grid de Custos vs Vendas
                            Div(
                                HTML(f"""
                                <div class="grid grid-cols-1 md:grid-cols-2 mt-7 gap-x-8 gap-y-3 text-base text-base-content font-semibold">

                                    <!-- COLUNA ESQUERDA — CUSTOS -->
                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Peças</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{custo_pecas}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Peças</span>
                                        <span id="display-venda-pecas"
                                                class="col-span-4 p-2 border-l border-base-300 whitespace-nowrap step5-accent-text"
                                                data-base-val="{venda_pecas.amount}"
                                                data-cost-val="{custo_pecas.amount}"
                                                data-frete-val="{custo_frete_pecas.amount}">
                                            {venda_pecas}
                                        </span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Frete de Peças</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{custo_frete_pecas}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Serviço de Terceiros</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{venda_servico_terceiros}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Serviço de Terceiros</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{custo_servico_terceiros}</span>
                                    </div>

                                    <div class="grid grid-cols-12"></div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo da Hora do Mecânico</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{custo_hora_mecanico}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Mão de Obra</span>
                                        <span id="display-venda-mo"
                                              class="col-span-4 p-2 border-l border-base-300 step5-accent-text"
                                              data-base-val="{venda_mao_obra.amount}"
                                              data-cost-val="{custo_total_mao_obra.amount}">
                                            {venda_mao_obra}
                                        </span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-semibold">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo Total da Mão de Obra</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{custo_total_mao_obra}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Duração Total</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{duracao_total}</span>
                                    </div>

                                    <!-- RESULTADO (respiro visual) -->
                                    <div class="md:col-span-2 h-2"></div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-bold">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Lucro Operacional</span>
                                        <span class="col-span-4 p-2 border-l border-base-300 step5-accent-text">{lucro_operacional}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border {rentabilidade_class} {rentabilidade_bg}">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Rentabilidade</span>
                                        <span class="col-span-4 p-2 border-l {rentabilidade_class} font-bold">
                                            {rentabilidade:.2f}% ({status_texto})
                                        </span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLO</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{mlo:.2f}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                        <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLR</span>
                                        <span class="col-span-4 p-2 border-l border-base-300">{mlr:.2f}</span>
                                    </div>

                                </div>
                                """)
                            ),
                            css_class="h-full",
                        ),
                        Div(
                            HTML(f"""<div class="text-center text-base-content mt-6">
                                    <p class="text-2xl font-bold">Valor do Orçamento</p>
                                    <p class="text-3xl font-black step5-accent-text">{budget.total_base_value}</p>
                                </div>""")
                        ),
                        id="step5-method-card",
                        css_class=f"bg-base-200 p-6 rounded-2xl border-2 border-base-300 h-full flex flex-col text-base-content {step5_method_hidden_class}",
                    ),
                    css_class="col-span-12 lg:col-span-6 h-full",
                ),
                # Coluna Direita
                Div(
                    Div(
                        # Slider
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2">Margem de Lucro</h4>'),
                            HTML("""
                                <div class="flex justify-between mb-1">
                                    <span class="text-sm font-bold">Peça: <span id="val-peca">0</span>%</span>
                                    <span class="text-sm font-bold">Mão de Obra: <span id="val-mo">0</span>%</span>
                                </div>
                            """),
                            Field("slider", label=False, help_text=False, wrapper_class="w-full"),
                            HTML('<p class="text-sm text-gray-500 font-semibold italic">Deslize para a esquerda para aumentar Peça, ou para direita para aumentar Mão de obra</p>'),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        # Desconto
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2">Desconto</h4>'),
                            Div(
                                Field("discount_percentage", wrapper_class="col-span-12 lg:col-span-6"),
                                Field("discount_value", wrapper_class="col-span-12 lg:col-span-6"),
                                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                            ),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        # Valor Final
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2 text-center border-b-1 border-gray-300">Valor Final</h4>'),
                            HTML('<h5 class="font-semibold text-lg mb-2 text-center">Valor do Orçamento com desconto aplicado:</h5>'),
                            HTML(f"""<div class="space-y-3">
                                        <div class="flex justify-between text-xl font-semibold">
                                            <span>Subtotal:</span>
                                            <span id="step5-subtotal-display" data-base-total="{budget.total_base_value.amount}">{budget.total_base_value}</span>
                                        </div>
                                        <div class="flex justify-between text-xl font-semibold">
                                            <span>Desconto:</span>
                                            <span id="step5-discount-display">{discount_display}</span>
                                        </div>
                                        <div class="flex justify-between text-xl font-black">
                                            <span>Valor Final:</span>
                                            <span id="valor-final-display">{budget.total_budget_value}</span>
                                        </div>
                                    </div>"""),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        css_class="sticky top-4",
                    ),
                    id="step5-controls-card",
                    css_class=f"col-span-12 lg:col-span-6 {step5_method_hidden_class}",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch",
            ),
        )

    def clean_discount_value(self):
        discount_value = self.cleaned_data.get("discount_value")
        if discount_value is None:
            return Money(0, "BRL")
        return discount_value

    def clean_discount_percentage(self):
        discount_percentage = self.cleaned_data.get("discount_percentage")
        if discount_percentage is None:
            return Decimal("0")
        return discount_percentage

    def clean_slider(self):
        slider = self.cleaned_data.get("slider")
        if slider is None:
            return 0
        return slider

    def save(self, commit=True):
        budget = super().save(commit=False)
        budget.invalidate_pricing_snapshot_cache()
        resolved_discount_value, resolved_discount_percentage = resolve_discount_fields(
            total_base_value=budget.total_base_value,
            discount_value=budget.discount_value,
            discount_percentage=budget.discount_percentage,
        )
        budget.discount_value = resolved_discount_value
        budget.discount_percentage = resolved_discount_percentage
        budget.invalidate_pricing_snapshot_cache()

        if commit:
            budget.save()
        return budget


class BudgetStep6Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = []
        widgets = {}

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        budget = _get_budget_with_prefetched_items(self.instance)

        status_data = budget.budget_status_badge
        status_label = status_data["text"]
        status_class = status_data["class"]

        saved_observation = budget.pdf_observation or ""

        # Render das linhas (mantido)
        rows = _render_budget_items_rows(budget, step6=True)
        products_html = rows["product"]
        services_html = rows["service"]
        kits_html = rows["kit"]

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            # =========================
            # CSS utilitário obrigatório
            # =========================
            HTML("""
            <style>
                .table-fixed { table-layout: fixed; }
            </style>
            """),
            alert_confirm_layout(),
            # =========================
            # SCRIPTS (mantidos do código original)
            # =========================
            HTML("""
            <script>
                function saveObservation(budgetId) {
                    const observation = document.getElementById('budget-observation').value;

                    fetch('{reverse("budget:save_observation", args=[budget.pk])}', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': '{{ csrf_token }}'
                        },
                        body: JSON.stringify({
                            observation: observation,
                        })
                    });
                }
                
                function openKitModal(button) {
                        const modal = document.getElementById('kitModal');
                    
                        const title = document.getElementById('kit-modal-title');
                        const productsList = document.getElementById('kit-modal-products');
                        const servicesList = document.getElementById('kit-modal-services');
                    
                        const productsCount = document.getElementById('kit-products-count');
                        const servicesCount = document.getElementById('kit-services-count');
                    
                        const productsCountSide = document.getElementById('kit-products-count-side');
                        const servicesCountSide = document.getElementById('kit-services-count-side');
                    
                        title.textContent = button.dataset.kitName;
                    
                        productsList.innerHTML = '';
                        servicesList.innerHTML = '';
                    
                        const products = button.dataset.kitProductsList
                            .split('|').map(i => i.trim()).filter(Boolean);
                    
                        const services = button.dataset.kitServicesList
                            .split('|').map(i => i.trim()).filter(Boolean);
                    
                        productsCount.textContent = products.length;
                        servicesCount.textContent = services.length;
                    
                        productsCountSide.textContent = products.length;
                        servicesCountSide.textContent = services.length;
                    
                        products.forEach(s => {
                            const li = document.createElement('li');
                            li.className = "flex items-start gap-3";
                            li.innerHTML = `
                              <span class="material-icons text-info text-sm mt-0.5 flex-shrink-0">circle</span>
                              <span class="break-words break-all whitespace-normal">
                                ${s}
                              </span>
                            `;
                            productsList.appendChild(li);
                        });
                    
                        services.forEach(s => {
                            const li = document.createElement('li');
                            li.className = "flex items-start gap-3";
                            li.innerHTML = `
                              <span class="material-icons text-info text-sm mt-0.5 flex-shrink-0">circle</span>
                              <span class="break-words break-all whitespace-normal">
                                ${s}
                              </span>
                            `;
                            servicesList.appendChild(li);
                        });
                    
                        modal.showModal();
                    }
                    
                function closeKitModal() {
                        const modal = document.getElementById('kitModal');
                        if (modal) {
                            modal.close();
                        }
                    }

                async function updateBudgetStatus(budgetId, status) {
                    const confirmed = await customConfirm("Você tem certeza que deseja alterar o status deste orçamento?");
                    if (!confirmed) return;

                    fetch(`/budget/update-status/${budgetId}/${status}`, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': '{{ csrf_token }}' }
                    }).then(() => {
                        window.location.href = "{% url 'budget:budget_list' %}";
                    });
                }

                async function sendBudgetForSignature(buttonEl) {
                    const btn = buttonEl || document.getElementById('send-signature-btn');
                    const label = document.getElementById('send-signature-label');
                    const spinner = document.getElementById('send-signature-spinner');
                    const endpoint = btn ? btn.dataset.url : '';

                    if (!endpoint) {
                        document.body.dispatchEvent(new CustomEvent('showToast', {
                            detail: {
                                type: 'error',
                                message: 'Endpoint de assinatura não configurado.',
                            },
                        }));
                        return;
                    }

                    if (btn) btn.disabled = true;
                    if (label) label.textContent = 'Enviando...';
                    if (spinner) spinner.classList.remove('hidden');

                    try {
                        const response = await fetch(endpoint, {
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': '{{ csrf_token }}',
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                        });

                        const payload = await response.json().catch(() => ({}));
                        if (!response.ok) {
                            throw new Error(payload.message || 'Falha ao enviar para assinatura.');
                        }

                        const toastType = payload.type || (payload.success ? 'success' : 'error');
                        const toastMessage = payload.message || (payload.success ? 'Orçamento enviado para assinatura.' : 'Falha ao enviar para assinatura.');

                        document.body.dispatchEvent(new CustomEvent('showToast', {
                            detail: {
                                type: toastType,
                                message: toastMessage,
                            },
                        }));

                        if (payload.success) {
                            setTimeout(() => {
                                window.location.href = "{% url 'budget:budget_list' %}";
                            }, 900);
                        }
                    } catch (error) {
                        document.body.dispatchEvent(new CustomEvent('showToast', {
                            detail: {
                                type: 'error',
                                message: error && error.message ? error.message : 'Falha ao enviar para assinatura. Tente novamente.',
                            },
                        }));
                    } finally {
                        if (btn) btn.disabled = false;
                        if (label) label.textContent = 'Enviar para Assinatura';
                        if (spinner) spinner.classList.add('hidden');
                    }
                }
            </script>
            """),
            # =========================
            # TÍTULO
            # =========================
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Revisão e Confirmação</h3>'),
            ),
            # =========================
            # GRID PRINCIPAL
            # =========================
            Div(
                # ===== COLUNA ESQUERDA =====
                Div(
                    HTML('<div class="border-t-2 mb-6"></div>'),
                    # -------- PRODUTOS --------
                    Div(
                        HTML('<h3 class="text-xl font-semibold text-gray-700 mb-4">Peças Selecionadas</h3>'),
                        HTML(f"""
                        <div class="mb-10 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden">
                          <div class="overflow-x-auto">
                            <table class="table table-zebra table-fixed w-full">
                              <thead class="bg-primary text-primary-content">
                                <tr>
                                  <th class="w-[22%]">NOME</th>
                                  <th class="w-[22%]">APLICAÇÃO</th>
                                  <th class="w-[8%] text-center">QTD.</th>
                                  <th class="w-[12%]">CUSTO</th>
                                  <th class="w-[14%]">VALOR</th>
                                  <th class="w-[10%]">FRETE</th>
                                  <th class="w-[12%]">TOTAL</th>
                                </tr>
                              </thead>
                              <tbody id="product-list-body">
                                {products_html}
                              </tbody>
                            </table>
                          </div>
                        </div>
                        """),
                    ),
                    # -------- SERVIÇOS --------
                    Div(
                        HTML('<h3 class="text-xl font-semibold text-gray-700 mb-4">Serviços Selecionados</h3>'),
                        HTML(f"""
                        <div class="mb-10 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden">
                            <div class="overflow-x-auto">
                                <table class="table table-zebra table-fixed w-full">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="w-[32%] whitespace-nowrap text-left">
                                                NOME
                                            </th>
                                            
                                            <th class="w-[8%] whitespace-nowrap text-center">
                                                QTD.
                                            </th>
                                            
                                            <th class="w-[14%] whitespace-nowrap text-right">
                                                CUSTO
                                            </th>
                                            
                                            <th class="w-[16%] whitespace-nowrap text-right">
                                                VALOR
                                            </th>
                                            
                                            <th class="w-[10%] whitespace-nowrap text-center">
                                                TEMPO
                                            </th>
                                            
                                            <th class="w-[20%] whitespace-nowrap text-right">
                                                TOTAL
                                            </th>
                                        </tr>
                                        </thead>
                                
                                    <tbody id = "service-list-body">
                                        {services_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        """),
                    ),
                    # -------- KITS --------
                    Div(
                        HTML('<h3 class="text-xl font-semibold text-gray-700 mb-4">Kits Selecionados</h3>'),
                        HTML(f"""
                        <div class="mb-6 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden">
                            <div class="overflow-x-auto">
                                <table class="table table-compact table-fixed w-full">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="w-[40%] whitespace-nowrap text-left">
                                            NOME
                                            </th>
                                        
                                            <th class="w-[10%] whitespace-nowrap text-center">
                                            QTD.
                                            </th>
                                        
                                            <th class="w-[15%] whitespace-nowrap text-center">
                                            PRODUTOS
                                            </th>
                                        
                                            <th class="w-[15%] whitespace-nowrap text-center">
                                            SERVIÇOS
                                            </th>
                                        
                                            <th class="w-[20%] whitespace-nowrap text-center">
                                            AÇÕES
                                            </th>
                                        </tr>
                                    </thead>
                                
                                    <tbody id="kit-list-body">
                                    {kits_html}
                                    </tbody>
                                </table>
                            </div>

                        </div>
                        """),
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                Div(css_class="hidden lg:block lg:col-span-1"),
                # ===== COLUNA DIREITA =====
                Div(
                    Div(
                        HTML(f"""
                                <div class="w-full mb-4 py-3 px-4 rounded-lg flex items-center justify-between border-l-4 {status_class} bg-opacity-20">
                                    <span class="font-bold text-sm uppercase tracking-wider">Status do Orçamento</span>
                                    <span class="badge {status_class} font-bold p-3">{status_label}</span>
                                </div>
                                """),
                    ),
                    # -------- PDF (RESTORED 1:1) --------
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2 border-b">PDF</h4>'),
                        HTML(f"""
                        <div class="grid grid-cols-12 gap-3 text-center mb-8">
                            <button type="button" class="btn btn-success col-span-4"
                                onclick="window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ detail: {{ url: '{reverse("budget:visualizar_pdf_assinatura", args=[budget.pk])}', downloadUrl: '{reverse("budget:visualizar_pdf_assinatura", args=[budget.pk])}?download=1', showSignatureBtn: true }} }}))">
                                Visualizar PDF
                            </button>

                            <button type="button" class="btn btn-success col-span-4"
                                onclick="window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ detail: {{ url: '{reverse("budget:visualizar_pdf_gestor", args=[budget.pk])}', showSignatureBtn: false }} }}))">
                                PDF Gestor
                            </button>

                            <button type="button" class="btn btn-success col-span-4"
                                onclick="window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ detail: {{ url: '{reverse("budget:visualizar_pdf_mecanico", args=[budget.pk])}', showSignatureBtn: false }} }}))">
                                PDF Mecânico
                            </button>
                        </div>
                        """),
                        css_class="p-4 bg-base-200/50 rounded-lg",
                    ),
                    # -------- OBSERVAÇÃO --------
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2 border-b">Observação</h4>'),
                        HTML(f"""
                        <div class="flex flex-col gap-3 mb-8">
                            <textarea
                                class="textarea textarea-bordered w-full"
                                maxlength="250"
                                rows="4"
                                id="budget-observation"
                                placeholder="Digite uma observação para o PDF..."
                            >{saved_observation}</textarea>

                            <div class="flex justify-between items-center text-sm text-gray-500">
                                <span id="obs-counter">0 / 250</span>
                                <button type="button"
                                        class="btn btn-sm btn-primary"
                                        onclick="saveObservation({budget.pk})">
                                    Salvar observação
                                </button>
                            </div>
                        </div>

                        <script>
                            const textarea = document.getElementById('budget-observation');
                            const counter = document.getElementById('obs-counter');
                            if (textarea && counter) {{
                                counter.textContent = `${{textarea.value.length}} / 250`;
                                textarea.addEventListener('input', () => {{
                                    counter.textContent = `${{textarea.value.length}} / 250`;
                                }});
                            }}
                        </script>
                        """),
                        css_class="p-4 bg-base-200/50 rounded-lg",
                    ),
                    # -------- APROVAÇÃO --------
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2 border-b">Aprovação</h4>'),
                        HTML(f"""
                        <div class="grid grid-cols-12 gap-3">
                            <button type="button" class="btn btn-error col-span-4"
                                onclick="updateBudgetStatus({budget.pk}, 'cancel')">
                                Cancelar
                            </button>

                            <button type="button"
                                class="btn col-span-4
                                    {{% if form.instance.has_local_items %}}
                                        btn-disabled cursor-not-allowed
                                    {{% else %}}
                                        btn-success
                                    {{% endif %}}"
                                {{% if not form.instance.has_local_items %}}
                                    onclick="updateBudgetStatus({budget.pk}, 'approve')"
                                {{% endif %}}
                                {{% if form.instance.has_local_items %}}
                                    disabled
                                    title="Existem itens não cadastrados no sistema"
                                {{% endif %}}>
                                Aprovar
                            </button>

                            <button type="button" class="btn btn-warning col-span-4"
                                onclick="updateBudgetStatus({budget.pk}, 'reject')">
                                Reprovar
                            </button>
                        </div>
                        """),
                        css_class="p-4 bg-base-200/50 rounded-lg",
                    ),
                    css_class="col-span-12 lg:col-span-6 sticky top-4",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-8",
            ),
            # =========================
            # MODAL DE PDF (RESTAURADO)
            # =========================
            HTML("""
            <dialog id="pdfModal"
                    class="modal"
                    x-data="{ pdfUrl: '', pdfDownloadUrl: '', showSignatureBtn: false }"
                    @open-pdf-modal.window="pdfUrl = $event.detail.url; pdfDownloadUrl = $event.detail.downloadUrl || ''; showSignatureBtn = $event.detail.showSignatureBtn || false; $el.showModal()">

              <div class="modal-box max-w-5xl w-full h-[90vh] p-0 flex flex-col">

                <div class="flex items-center justify-between px-6 py-4 border-b bg-base-200">
                    <h3 class="text-xl font-bold flex items-center gap-2">
                        <span class="material-icons">description</span>
                        Visualização do PDF
                    </h3>

                    <div class="flex gap-2">
                        <button type="button"
                                class="btn btn-sm btn-primary"
                                id="send-signature-btn"
                                x-show="showSignatureBtn"
                                data-url="{% url 'budget:send_signature' form.instance.pk %}"
                                onclick="sendBudgetForSignature(this)">
                            <span class="loading loading-spinner loading-xs hidden" id="send-signature-spinner"></span>
                            <span id="send-signature-label">Enviar para Assinatura</span>
                        </button>

                        <button type="button"
                                class="btn btn-sm btn-success"
                                onclick="
                                  const frame = document.querySelector('#pdfModal iframe');
                                  const downloadUrl = frame ? frame.dataset.downloadUrl : '';
                                  if (downloadUrl) {
                                      window.open(downloadUrl, '_blank');
                                  } else if (frame && frame.contentWindow) {
                                      frame.contentWindow.focus();
                                      frame.contentWindow.print();
                                  }
                                ">
                            Baixar PDF
                        </button>

                        <button type="button"
                                class="btn btn-sm"
                                onclick="document.getElementById('pdfModal').close()">
                            Fechar
                        </button>
                    </div>
                </div>

                <div class="flex-1 bg-gray-100">
                    <template x-if="pdfUrl">
                        <iframe :src="pdfUrl"
                                :data-download-url="pdfDownloadUrl"
                                class="w-full h-full"
                                frameborder="0"></iframe>
                    </template>
                </div>

              </div>

              <form method="dialog" class="modal-backdrop">
                <button>close</button>
              </form>
            </dialog>
            """),
            HTML("""
                <dialog
                    id="kitModal"
                    class="modal"
                    onclick="if(event.target === this) closeKitModal()"
                >
                  <div class="modal-box max-w-5xl w-full max-h-[75vh] p-0 flex flex-col">

                    <!-- HEADER -->
                    <div class="flex items-center justify-between px-8 py-5 border-b bg-base-200">
                        <div class="flex items-center gap-4">
                            <div class="p-3 rounded-lg bg-primary/10">
                                <span class="material-icons text-primary text-3xl">inventory_2</span>
                            </div>

                            <div>
                                <h3 class="text-2xl font-bold leading-tight" id="kit-modal-title"></h3>
                                <span class="badge badge-primary badge-outline mt-1">
                                    Kit de Serviços
                                </span>
                            </div>
                        </div>
                    </div>

                    <!-- BODY -->
                    <div class="p-8 grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 overflow-y-auto">

                        <!-- PRODUTOS (CARD VERTICAL) -->
                        <div class="card bg-base-100 shadow-md border lg:col-span-1">
                            <div class="card-body gap-4">
                                <div class="flex items-center justify-between">
                                    <h4 class="font-semibold text-base flex items-center gap-2">
                                        <span class="material-icons text-info">build</span>
                                        Produtos
                                    </h4>
                                    <span id="kit-products-count" class="badge badge-info"></span>
                                </div>

                                <div class="divider my-1"></div>

                                <ul
                                    id="kit-modal-products"
                                    class="flex flex-col gap-3 text-sm
                                         max-h-64 overflow-y-auto pr-2
                                         overflow-x-hidden"
                                ></ul>
                            </div>
                        </div>

                        <!-- SERVIÇOS (CARD VERTICAL) -->
                        <div class="card bg-base-100 shadow-md border lg:col-span-1">
                            <div class="card-body gap-4">
                                <div class="flex items-center justify-between">
                                    <h4 class="font-semibold text-base flex items-center gap-2">
                                        <span class="material-icons text-success">engineering</span>
                                        Serviços
                                    </h4>
                                    <span id="kit-services-count" class="badge badge-success"></span>
                                </div>

                                <div class="divider my-1"></div>

                                <ul
                                    id="kit-modal-services"
                                    class="flex flex-col gap-3 text-sm
                                         max-h-64 overflow-y-auto pr-2
                                         overflow-x-hidden"
                                ></ul>
                            </div>
                        </div>

                        <!-- COLUNA DE CONTEXTO (PROFISSIONAL) -->
                        <div class="card bg-base-200/60 border lg:col-span-1">
                            <div class="card-body gap-4">
                                <h4 class="font-semibold text-base">
                                    Informações do Kit
                                </h4>

                                <div class="flex flex-col gap-3 text-sm text-base-content/80">
                                    <div class="flex justify-between">
                                        <span>Total de Produtos</span>
                                        <strong id="kit-products-count-side"></strong>
                                    </div>

                                    <div class="flex justify-between">
                                        <span>Total de Serviços</span>
                                        <strong id="kit-services-count-side"></strong>
                                    </div>
                                </div>

                                <div class="divider"></div>

                                <p class="text-xs text-base-content/60 leading-relaxed">
                                    Este kit agrupa produtos e serviços vinculados ao orçamento,
                                    facilitando a visualização e conferência antes da aprovação.
                                </p>
                            </div>
                        </div>

                    </div>

                    <!-- FOOTER -->
                    <div class="flex justify-end px-8 py-5 border-t bg-base-200">
                        <button
                            type="button"
                            class="btn btn-primary"
                            onclick="closeKitModal()"
                        >
                            <span class="material-icons text-sm">close</span>
                            Fechar
                        </button>
                    </div>

                  </div>
                </dialog>
            """),
        )
