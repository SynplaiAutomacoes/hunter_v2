from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django.urls import reverse

from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, CheckboxInput, EmailInput, PhoneInput, NumberInput, SelectInput
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        exclude = ["workshop", "criado_em", "atualizado_em"]
        fields = [
            "cnpj",
            "name",
            "contact_person",
            "phone",
            "mobile",
            "email",
            "registration_date",
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
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "name": TextInput(),
            "contact_person": TextInput(),
            "phone": PhoneInput(),
            "mobile": PhoneInput(),
            "email": EmailInput(),
            "registration_date": CalendarDateInput(),
            "is_active": CheckboxInput(),
            "cep": TextInput(),
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

        cancel_url = reverse("suppliers:supplier_list")

        self.helper.layout = Layout(
            Div(
                # Seção: Dados do Fornecedor
                HTML('<h3 class="col-span-12 text-lg font-bold">Dados do Fornecedor</h3>'),
                Field("cnpj", wrapper_class="col-span-12 lg:col-span-4"),
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                Field("contact_person", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("phone", wrapper_class="col-span-12 lg:col-span-4"),
                Field("mobile", wrapper_class="col-span-12 lg:col-span-4"),
                Field("email", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("registration_date", wrapper_class="col-span-12 lg:col-span-4"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-8"),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                # Seção: Endereço
                HTML('<h3 class="col-span-12 text-lg font-bold">Endereço</h3>'),
                Field("cep", wrapper_class="col-span-12 lg:col-span-4"),
                Field("logradouro", wrapper_class="col-span-12 lg:col-span-4"),
                Field("numero", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("complemento", wrapper_class="col-span-12 lg:col-span-4"),
                Field("bairro", wrapper_class="col-span-12 lg:col-span-4"),
                Field("cidade", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("estado", wrapper_class="col-span-12 lg:col-span-4"),
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