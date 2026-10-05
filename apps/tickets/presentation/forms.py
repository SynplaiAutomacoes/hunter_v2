from crispy_forms.helper import FormHelper  # type: ignore[import-untyped]
from crispy_forms.layout import Div, Field, Layout  # type: ignore[import-untyped]
from django import forms

from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import TextareaInput, TextInput
from apps.tickets.models import TicketStatus


class TicketCreateForm(CoreForm):
    title = forms.CharField(label="Título", max_length=255, widget=TextInput(attrs={"placeholder": "Resumo do problema"}))
    problem = forms.CharField(label="Qual o problema", widget=TextareaInput(attrs={"rows": 4}))
    reproduction_steps = forms.CharField(label="Como repetir este problema", widget=TextareaInput(attrs={"rows": 4}))

    def __init__(self, *args, **kwargs):
        # CreateView passa instance=; este form não é ModelForm.
        kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("title", wrapper_class="col-span-12"),
                Field("problem", wrapper_class="col-span-12"),
                Field("reproduction_steps", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            )
        )


class TicketStatusUpdateForm(CoreForm):
    status = forms.ChoiceField(
        label="Novo status",
        choices=[
            (TicketStatus.EM_ANDAMENTO, "Em andamento"),
            (TicketStatus.VALIDACAO_INTERNA, "Validação interna"),
            (TicketStatus.AGUARDANDO_VALIDACAO, "Aguardando validação"),
            (TicketStatus.REPROVADO, "Reprovado"),
            (TicketStatus.CANCELADO, "Cancelado"),
        ],
    )
    cancellation_reason = forms.CharField(
        label="Motivo do cancelamento",
        required=False,
        widget=TextareaInput(attrs={"rows": 3}),
    )


class TicketRejectForm(CoreForm):
    reason = forms.CharField(label="Motivo da recusa", widget=TextareaInput(attrs={"rows": 4}))


class TicketReassignForm(CoreForm):
    assignee_id = forms.IntegerField(label="Novo responsável", min_value=1)


class TicketMessageForm(CoreForm):
    body = forms.CharField(label="Mensagem", max_length=4000, widget=TextareaInput(attrs={"rows": 2, "placeholder": "Escreva uma mensagem..."}))
