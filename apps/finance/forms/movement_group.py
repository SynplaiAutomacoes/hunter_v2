from decimal import Decimal

from django import forms
from djmoney.money import Money

from apps.core.presentation.widgets import CalendarDateInput, DecimalInput, MoneyInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models import FinancialMovement, MovementGroup, PaymentMethod
from apps.core.text_normalization import sentence_case
from apps.core.presentation.forms import CoreForm, CoreModelForm
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
        fields = ["name", "description", "due_date", "discount_mode", "discount_value", "discount_percentage"]
        widgets = {
            "name": TextInput(),
            "description": TextareaInput(attrs={"rows": 2}),
            "due_date": CalendarDateInput(),
            "discount_mode": SearchableSelectInput(),
            "discount_value": MoneyInput(),
            "discount_percentage": DecimalInput(min_value=0, max_value=100, decimal_places=2),
        }
        labels = {
            "due_date": "Primeiro vencimento",
        }

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        direction = kwargs.pop("direction", None)
        total_amount = kwargs.pop("total_amount", Decimal("0.00"))
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
        self.fields["discount_mode"].required = True
        self.fields["discount_value"].required = False
        self.fields["discount_percentage"].required = False
        if not self.is_bound:
            self.initial["discount_mode"] = ""

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return sentence_case(value) if value else value

    def clean_description(self):
        value = self.cleaned_data.get("description")
        return sentence_case(value) if value else value

    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get("discount_mode")
        discount_value = cleaned_data.get("discount_value")
        discount_percentage = cleaned_data.get("discount_percentage") or Decimal("0.00")
        discount_amount = Decimal("0.00")

        if mode == "AMOUNT":
            discount_amount = Decimal(str(discount_value.amount if discount_value else 0))
            if discount_amount <= 0:
                self.add_error("discount_value", "Informe o valor do desconto.")
            elif discount_amount > self.total_amount:
                self.add_error("discount_value", "O desconto não pode ser maior que o total agrupado.")
            cleaned_data["discount_percentage"] = Decimal("0.00")
        elif mode == "PERCENTAGE":
            if discount_percentage <= 0:
                self.add_error("discount_percentage", "Informe o percentual do desconto.")
            elif discount_percentage > Decimal("100"):
                self.add_error("discount_percentage", "O desconto percentual não pode ser maior que 100%.")
            discount_amount = self.total_amount * discount_percentage / Decimal("100")
            cleaned_data["discount_value"] = Money(Decimal("0.00"), "BRL")
        elif mode == "NONE":
            cleaned_data["discount_value"] = Money(Decimal("0.00"), "BRL")
            cleaned_data["discount_percentage"] = Decimal("0.00")
        else:
            self.add_error("discount_mode", "Informe se o agrupamento possui desconto.")

        net_total = max(self.total_amount - discount_amount, Decimal("0.00"))
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
                    expected_total=net_total,
                )
            elif installments_count and due_date:
                schedule = build_group_installments(
                    total_amount=net_total,
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.gross_amount = Money(self.total_amount, "BRL")
        instance.sync_net_amount()
        if commit:
            instance.save()
        return instance
