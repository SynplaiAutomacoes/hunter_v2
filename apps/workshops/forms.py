from crispy_forms.layout import Layout, Div, Field, Submit
from django.forms import ModelForm

from crispy_forms.helper import FormHelper

from apps.workshops.models import Workshop
from apps.core.widgets import TextInput, CPForCNPJInput


class WorkshopCreateForm(ModelForm):
    class Meta:
        model = Workshop
        fields = ["name", "cnpj"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Oficina Hunter"}),
            "cnpj": CPForCNPJInput(mode="cnpj"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["name"].label = "Nome"
        self.fields["cnpj"].label = "CNPJ"

        self.helper = FormHelper()
        self.helper.attrs = {"class": "h-full flex flex-col"}

        self.helper.layout = Layout(
            Div(
                Field("name"),
                Field("cnpj"),
                css_class="grid grid-cols-1 lg:grid-cols-2 gap-4",
            ),
            Div(
                Submit("submit", "Salvar", css_class="btn btn-primary w-full lg:w-auto"),
                css_class="mt-auto pt-6 flex justify-end",
            ),
        )
