from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit
from django.urls import reverse

from .models import Customer, Vehicle
from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, SelectInput, RGInput, PhoneInput, EmailInput, CheckboxInput, CEPInput, \
    NumberInput
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
    can_delete=True,
    widgets = {
        "plate": TextInput(),
        "brand": TextInput(),
        "model": TextInput(),
        "year_fabrication": CalendarDateInput(),
        "year_model": CalendarDateInput(),
        "color": TextInput(),
        "fuel": TextInput(),
        "engine": TextInput(),
        "type": TextInput(),
        "renavam": TextInput(),
        "chassi": TextInput(),
        "km": NumberInput(),
    },
)


class CustomerForm(forms.ModelForm):
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
            "cep": CEPInput(),
            "logradouro": TextInput(),
            "numero": TextInput(),
            "complemento": TextInput(),
            "bairro": TextInput(),
            "cidade": TextInput(),
            "estado": SelectInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"

        address_fields = ["logradouro", "bairro", "cidade"]
        for field in address_fields:
            self.fields[field].widget.attrs["readonly"] = True
            self.fields[field].widget.attrs["class"] = self.fields[field].widget.attrs.get("class", "")
            self.fields[field].widget.attrs["style"] = "cursor: not-allowed;"
            self.fields[field].widget.attrs["title"] = "Preencha o campo de CEP"

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
                HTML("""
                        <div class="col-span-12" style="display: flex; align-items: center; gap: 25px;">
                            <h3 class="col-span-12 text-xl font-bold">Endereço</h3>

                            <h5 id="cep-loader" class="htmx-indicator" style="margin:0;">
                                <span class="text-lg font-semibold">
                                    (Buscando endereço...)
                                </span>
                            </h5>
                        </div>
                        """),
                Field("cep", wrapper_class="col-span-12 lg:col-span-4", hx_get=reverse("core:cep_lookup"), hx_trigger="blur", hx_target="this", hx_swap="none", hx_include="[name='cep']", hx_indicator="#cep-loader"),
                Field("logradouro", wrapper_class="col-span-12 lg:col-span-4"),
                Field("numero", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("complemento", wrapper_class="col-span-12 lg:col-span-4"),
                Field("bairro", wrapper_class="col-span-12 lg:col-span-4"),
                Field("cidade", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("estado", wrapper_class="col-span-12 lg:col-span-4"),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                # Seção: Veículo
                HTML(f"""
                    <div class="col-span-12">
                        <div class="flex items-center justify-between mb-4 border-b pb-2">
                            <h3 class="text-xl font-bold">Veículos</h3>
                            <button type="button"
                                class="btn btn-sm btn-secondary"
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