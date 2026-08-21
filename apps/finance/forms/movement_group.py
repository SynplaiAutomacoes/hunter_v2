from django import forms
from apps.core.presentation.widgets import CalendarDateInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models import FinancialMovement, MovementGroup, PaymentMethod
from apps.core.text_normalization import sentence_case
from apps.core.presentation.forms import CoreForm, CoreModelForm


class GroupMovementStep1Form(CoreForm):
    entity = forms.ChoiceField(label="Cliente, Fornecedor ou Colaborador", widget=SearchableSelectInput(), required=True)

    def __init__(self, *args, **kwargs):
        customers = kwargs.pop("customers", [])
        suppliers = kwargs.pop("suppliers", [])
        collaborators = kwargs.pop("collaborators", [])
        super().__init__(*args, **kwargs)

        choices = [("", "---------")]

        for c in customers:
            choices.append((f"customer_{c.id}", f"Cliente: {c.name}"))

        for s in suppliers:
            choices.append((f"supplier_{s.id}", f"Fornecedor: {s.name}"))

        for c in collaborators:
            choices.append((f"collaborator_{c.id}", f"Colaborador: {str(c)}"))

        self.fields["entity"].choices = choices


class GroupMovementStep3Form(CoreModelForm):
    class Meta:
        model = MovementGroup
        fields = ["name", "description", "due_date"]
        widgets = {
            "name": TextInput(),
            "description": TextareaInput(attrs={"rows": 3}),
            "due_date": CalendarDateInput(),
        }

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        direction = kwargs.pop("direction", None)
        super().__init__(*args, **kwargs)

        payment_methods = PaymentMethod.objects.none()
        if workshop is not None:
            payment_methods = PaymentMethod.objects.filter(workshop=workshop, is_active=True)
            if direction == FinancialMovement.MovementDirection.CREDIT:
                payment_methods = payment_methods.filter(
                    payment_type__in=[PaymentMethod.PaymentType.CREDIT, PaymentMethod.PaymentType.BOTH]
                )
            elif direction == FinancialMovement.MovementDirection.DEBIT:
                payment_methods = payment_methods.filter(
                    payment_type__in=[PaymentMethod.PaymentType.DEBIT, PaymentMethod.PaymentType.BOTH]
                )

        self.fields["payment_method"] = forms.ModelChoiceField(
            label="Forma de Pagamento",
            queryset=payment_methods.order_by("description"),
            required=True,
            widget=SearchableSelectInput(),
        )
        self.fields["payment_method"].widget.choices = [
            (payment_method.pk, str(payment_method)) for payment_method in payment_methods.order_by("description")
        ]
        self.payment_method_installments = {
            str(payment_method.pk): max(int(payment_method.installments_count or 1), 1)
            for payment_method in payment_methods
        }
        self.fields["name"].required = True
        self.fields["due_date"].required = True

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return sentence_case(value) if value else value

    def clean_description(self):
        value = self.cleaned_data.get("description")
        return sentence_case(value) if value else value
