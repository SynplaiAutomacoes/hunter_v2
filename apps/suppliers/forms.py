from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, CheckboxInput, EmailInput, PhoneInput
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
            "is_active"
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
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            # Seção: Dados do Fornecedor
            HTML('<h3 class="text-lg font-bold mb-4">Dados do Fornecedor</h3>'),
            Div(
                Field("cnpj", wrapper_class="col-span-1"),
                Field("name", wrapper_class="col-span-2"),
                Field("contact_person", wrapper_class="col-span-1"),
                css_class="grid grid-cols-1 md:grid-cols-4 gap-4",
            ),
            Div(
                Field("phone", wrapper_class="col-span-1"),
                Field("mobile", wrapper_class="col-span-1"),
                Field("email", wrapper_class="col-span-2"),
                css_class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4",
            ),
            Div(
                Field("registration_date", wrapper_class="col-span-1"),
                Field("is_active", wrapper_class="col-span-1"),
                css_class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4",
            ),

            HTML('<div class="divider my-6"></div>'),

            # Seção: Endereço
            HTML('<h3 class="text-lg font-bold mb-4">Endereço</h3>'),
            Div(
                Field("cep", wrapper_class="col-span-1"),
                Field("logradouro", wrapper_class="col-span-2"),
                Field("numero", wrapper_class="col-span-1"),
                css_class="grid grid-cols-1 md:grid-cols-4 gap-4",
            ),
            Div(
                Field("complemento", wrapper_class="col-span-1"),
                Field("bairro", wrapper_class="col-span-1"),
                Field("cidade", wrapper_class="col-span-1"),
                Field("estado", wrapper_class="col-span-1"),
                css_class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4",
            ),

            HTML('<div class="divider my-6"></div>'),

            Div(
                HTML('<a href="{% url "catalog:supplier_list" %}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )