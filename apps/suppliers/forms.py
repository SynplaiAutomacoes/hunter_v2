from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django.urls import reverse

from apps.core.widgets import CPForCNPJInput, CalendarDateInput, TextInput, CheckboxInput, EmailInput, PhoneInput, SelectInput, \
    CEPInput
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


class SupplierForm(forms.ModelForm):
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
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "name": TextInput(),
            "contact_person": TextInput(),
            "phone": PhoneInput(),
            "mobile": PhoneInput(),
            "email": EmailInput(),
            "registration_date": CalendarDateInput(),
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