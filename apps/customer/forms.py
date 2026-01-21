from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit
from django.urls import reverse

from .models import Customer, Vehicle
from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, SelectInput, RGInput, PhoneInput, EmailInput, CheckboxInput, CEPInput, \
    NumberInput
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
    extra=1,
    can_delete=False,
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
            "cpf",
            "name",
            "rg",
            "birth_date",
            "sex",
            "phone",
            "email",
            "is_active",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "estado",
        ]
        widgets = {
            "cpf": CPForCNPJInput(mode="cpf"),
            "name": TextInput(),
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

        self.helper.layout = Layout(
            Div(
                # Dados do Cliente
                HTML('<h3 class="text-xl font-bold col-span-12">Dados Gerais</h3>'),
                Field("cpf", wrapper_class="col-span-12 lg:col-span-4"),
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                Field("rg", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("birth_date", wrapper_class="col-span-12 lg:col-span-4"),
                Field("sex", wrapper_class="col-span-12 lg:col-span-4"),
                Field("phone", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("email", wrapper_class="col-span-12 lg:col-span-4"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-8"),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                # Seção: Endereço
                address_layout(),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                # Seção: Veículo
                HTML(f"""
                    <div class="col-span-12">
                        <div class="flex items-center justify-between mb-4 border-b pb-2">
                            <h3 class="text-xl font-bold">Veículos</h3>
                            <button type="button"
                                style="background-color: #491eff; 
                                    color: white; 
                                    padding: 6px 12px; 
                                    border-radius: 8px; 
                                    font-size: 0.875rem; 
                                    font-weight: 600; 
                                    border: none; 
                                    cursor: pointer;
                                    transition: filter 0.2s;"
                                onmouseover="this.style.filter='brightness(0.9)'"
                                onmouseout="this.style.filter='brightness(1)'"
                                hx-get="{reverse('customer:add-vehicle-form')}"
                                hx-target="#vehicle-list"
                                hx-swap="beforeend"
                                hx-vals='js:{{index: document.querySelectorAll(".vehicle-item").length}}'>
                            + Adicionar Veículo
                            </button>
                        </div>
                    </div>
                """),
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
        cleaned_data = super().clean()
        cpf = cleaned_data.get("cpf")
        rg = cleaned_data.get("rg")

        # Só validamos se tivermos a workshop disponível
        if self.workshop:
            if rg:
                queryset = Customer.objects.filter(workshop=self.workshop, rg=rg)

                # Se for edição (update), ignoramos o próprio objeto
                if self.instance.pk:
                    queryset = queryset.exclude(pk=self.instance.pk)

                if queryset.exists():
                    # Adiciona o erro especificamente no campo RG
                    self.add_error("rg", "Já existe um cliente cadastrado com este RG nesta oficina.")

            elif cpf:
                queryset = Customer.objects.filter(workshop=self.workshop, cpf=cpf)

                # Se for edição (update), ignoramos o próprio objeto
                if self.instance.pk:
                    queryset = queryset.exclude(pk=self.instance.pk)

                if queryset.exists():
                    # Adiciona o erro especificamente no campo CPF
                    self.add_error("cpf", "Já existe um cliente cadastrado com este CPF nesta oficina.")

        return cleaned_data