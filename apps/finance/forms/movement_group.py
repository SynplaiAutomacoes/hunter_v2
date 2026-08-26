from decimal import Decimal

from django import forms

from apps.core.presentation.forms import CoreForm, CoreModelForm
from apps.core.presentation.widgets import CalendarDateInput, NumberInput, SearchableSelectInput, TextInput, TextareaInput
from apps.core.text_normalization import sentence_case
from apps.finance.models import FinancialMovement, MovementGroup, PaymentMethod
from apps.finance.services.movement_grouping import InstallmentScheduleError, build_group_installments, parse_group_installment_schedule


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
    installments_count = forms.IntegerField(
        label="Número de parcelas",
        min_value=1,
        max_value=60,
        required=True,
        widget=NumberInput(attrs={"x-model.number": "installmentsCount", "min": "1", "max": "60"}),
        help_text="Sugestão da forma de pagamento. Você pode alterar quantidade, valor e vencimento de cada parcela.",
    )

    class Meta:
        model = MovementGroup
        fields = ["name", "description", "due_date"]
        widgets = {
            "name": TextInput(),
            "description": TextareaInput(attrs={"rows": 2}),
            "due_date": CalendarDateInput(),
        }
        labels = {
            "due_date": "Primeiro vencimento",
        }

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        direction = kwargs.pop("direction", None)
        total_amount = kwargs.pop("total_amount", Decimal("0.00"))
        data = args[0] if args else kwargs.get("data")
        if data is not None and "discount_mode" not in data:
            data = data.copy()
            data["discount_mode"] = "NONE"
            if args:
                args = (data, *args[1:])
            else:
                kwargs["data"] = data
        super().__init__(*args, **kwargs)
        self.total_amount = Decimal(str(getattr(total_amount, "amount", total_amount) or 0))

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
        self.fields["due_date"].label = "Primeiro vencimento"
        self.fields["due_date"].help_text = "Data da primeira parcela. As demais avançam um mês, e você pode editar depois."

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return sentence_case(value) if value else value

    def clean_description(self):
        value = self.cleaned_data.get("description")
        return sentence_case(value) if value else value

    def clean(self):
        cleaned_data = super().clean()
        installments_count = cleaned_data.get("installments_count")
        due_date = cleaned_data.get("due_date")
        payment_method = cleaned_data.get("payment_method")
        if installments_count is None and payment_method is not None:
            installments_count = max(int(payment_method.installments_count or 1), 1)
            cleaned_data["installments_count"] = installments_count

        getlist = getattr(self.data, "getlist", None)
        raw_due_dates = getlist("installment_due_date") if callable(getlist) else []
        raw_amounts = getlist("installment_amount") if callable(getlist) else []
        due_dates = [value for value in raw_due_dates if str(value).strip()]
        amounts = [value for value in raw_amounts if str(value).strip()]
        try:
            if due_dates or amounts:
                schedule = parse_group_installment_schedule(
                    due_dates=due_dates,
                    amounts=amounts,
                    expected_count=int(installments_count or 0),
                    expected_total=self.total_amount,
                )
            elif installments_count and due_date:
                schedule = build_group_installments(
                    total_amount=self.total_amount,
                    first_due_date=due_date,
                    installments_count=installments_count,
                )
            else:
                return cleaned_data
        except InstallmentScheduleError as exc:
            self.add_error(None, str(exc))
            return cleaned_data

        cleaned_data["installment_schedule"] = schedule
        if schedule:
            cleaned_data["due_date"] = schedule[0].due_date
        return cleaned_data

    def installment_schedule_payload(self) -> list[dict[str, str | int | float]]:
        schedule: list = []
        if hasattr(self, "cleaned_data"):
            schedule = self.cleaned_data.get("installment_schedule") or []
        if schedule:
            return [
                {
                    "number": installment.number,
                    "dueDate": installment.due_date.isoformat(),
                    "amount": float(installment.amount),
                }
                for installment in schedule
            ]

        getlist = getattr(self.data, "getlist", None)
        due_dates = getlist("installment_due_date") if callable(getlist) else []
        amounts = getlist("installment_amount") if callable(getlist) else []
        payload: list[dict[str, str | int | float]] = []
        for index, (raw_due_date, raw_amount) in enumerate(zip(due_dates, amounts)):
            payload.append({"number": index + 1, "dueDate": str(raw_due_date or ""), "amount": str(raw_amount or "")})
        return payload
