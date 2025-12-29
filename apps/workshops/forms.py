from crispy_forms.layout import Submit, Layout, Div, HTML, Field
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
        self.helper.layout = Layout(
            Div(Field("name", wrapper_class="w-full"), Field("cnpj", wrapper_class="w-full"), css_class="grid grid-cols-1 lg:grid-cols-2 gap-4"),
            HTML('<div class="divider"></div>'),
            Div(
                HTML('<a href="javascript:history.back()" class="btn btn-ghost text-base-content/70">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn btn-primary px-8"),
                css_class="flex items-center justify-end gap-2",
            ),
        )
