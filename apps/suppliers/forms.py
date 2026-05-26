from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django.urls import reverse

from apps.core.forms import address_layout, AddressFormMixin, CoreModelForm
from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, CheckboxInput, EmailInput, PhoneInput
from apps.suppliers.models import Supplier
from apps.core.text_normalization import name_case, sentence_case
from apps.workshops.models.workshops import Workshop


class SupplierForm(AddressFormMixin, CoreModelForm):
    class Meta:
        model = Supplier
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
            "cnpj": CPForCNPJInput(mode="both"),
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
        self.setup_address_fields()
        self.helper = FormHelper()
        self.helper.form_method = "post"

        cancel_url = reverse("suppliers:supplier_list")

        self.helper.layout = Layout(
            Div(
                # Seção: Dados do Fornecedor
                HTML('<h3 class="col-span-12 text-xl font-bold">Dados do Fornecedor</h3>'),
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
                address_layout(),
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
        cnpj = cleaned_data.get("cnpj")

        # Só validamos se tivermos o CNPJ e a workshop disponível
        if cnpj and self.workshop:
            queryset = Supplier.objects.filter(workshop=self.workshop, cnpj=cnpj)

            # Se for edição (update), ignoramos o próprio objeto
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                # Adiciona o erro especificamente no campo CNPJ
                self.add_error("cnpj", "Já existe um fornecedor cadastrado com este CNPJ nesta oficina.")

        return cleaned_data

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return name_case(value) if value else value

    def clean_contact_person(self):
        value = self.cleaned_data.get("contact_person")
        return name_case(value) if value else value

    def clean_logradouro(self):
        value = self.cleaned_data.get("logradouro")
        return sentence_case(value) if value else value

    def clean_complemento(self):
        value = self.cleaned_data.get("complemento")
        return sentence_case(value) if value else value

    def clean_bairro(self):
        value = self.cleaned_data.get("bairro")
        return sentence_case(value) if value else value

    def clean_cidade(self):
        value = self.cleaned_data.get("cidade")
        return sentence_case(value) if value else value
