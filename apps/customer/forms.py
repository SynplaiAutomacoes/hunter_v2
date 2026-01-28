from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit, Button
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
        add_vehicle_url = reverse("customer:add-vehicle-form")

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


class QuickCustomerForm(AddressFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["cpf","name","birth_date","cep","logradouro","numero","complemento","bairro","cidade","estado"]
        widgets = {
            "cpf": CPForCNPJInput(mode="cpf"),
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
                Field("cpf", wrapper_class="col-span-12"),
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