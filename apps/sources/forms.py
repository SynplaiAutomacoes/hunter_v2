from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django.urls import reverse

from apps.core.widgets import CPForCNPJInput, TextInput, EmailInput, PhoneInput
from apps.sources.models import Source
from apps.workshops.models.workshops import Workshop


class SourceForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = [
            "cnpj",
            "name",
            "phone",
            "email",
        ]
        widgets = {
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "name": TextInput(),
            "phone": PhoneInput(),
            "email": EmailInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"

        cancel_url = reverse("sources:source_list")

        self.helper.layout = Layout(
            Div(
                HTML('<h3 class="col-span-12 text-xl font-bold">Dados da Origem</h3>'),
                Field("name", wrapper_class="col-span-12"),
                #
                Field("cnpj", wrapper_class="col-span-12 lg:col-span-4"),
                Field("phone", wrapper_class="col-span-12 lg:col-span-4"),
                Field("email", wrapper_class="col-span-12 lg:col-span-4"),
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
            queryset = Source.objects.filter(workshop=self.workshop, cnpj=cnpj)

            # Se for edição (update), ignoramos o próprio objeto
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                # Adiciona o erro especificamente no campo CNPJ
                self.add_error("cnpj", "Já existe uma origem cadastrada com este CNPJ nesta oficina.")

        return cleaned_data