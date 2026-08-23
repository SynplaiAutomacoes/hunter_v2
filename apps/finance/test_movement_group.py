from datetime import date
from decimal import Decimal

from django.http import QueryDict
from django.test import TestCase
from djmoney.money import Money

from apps.finance.forms.movement_group import GroupMovementStep3Form
from apps.finance.models import FinancialMovement, MovementGroup
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.movement_grouping import InstallmentScheduleError, parse_group_installment_schedule
from apps.finance.services.reports import build_financial_overview_with_open_workorder_credits, open_credits
from apps.workshops.models.workshops import Workshop


class GroupMovementStep3FormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Agrupamento",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua de Teste, 100",
        )
        self.other_workshop = Workshop.objects.create(
            name="Outra Oficina",
            cnpj="98.765.432/0001-10",
            phone="+5511988888888",
            address="Rua Alternativa, 200",
        )

    def _form(
        self,
        payment_method: object = "",
        *,
        installments_count: str = "1",
        extra: dict | None = None,
        total_amount: Decimal = Decimal("0.00"),
    ) -> GroupMovementStep3Form:
        data = QueryDict(mutable=True)
        data.update(
            {
                "name": "Fechamento fornecedor",
                "description": "Contas agrupadas",
                "due_date": date(2026, 9, 15).isoformat(),
                "payment_method": str(payment_method),
                "installments_count": installments_count,
            }
        )
        extra = extra or {}
        for key, value in extra.items():
            if isinstance(value, list):
                data.setlist(key, [str(item) for item in value])
            else:
                data[key] = str(value)
        return GroupMovementStep3Form(
            data=data,
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.DEBIT,
            total_amount=total_amount,
        )

    def test_payment_method_is_required(self) -> None:
        form = self._form()

        self.assertFalse(form.is_valid())
        self.assertIn("payment_method", form.errors)

    def test_accepts_active_payment_method_compatible_with_direction(self) -> None:
        payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Boleto",
            payment_type=PaymentMethod.PaymentType.DEBIT,
        )

        form = self._form(payment_method.pk)

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["payment_method"], payment_method)

    def test_rejects_payment_method_from_another_workshop_or_wrong_direction(self) -> None:
        wrong_direction = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Cartão de crédito",
            payment_type=PaymentMethod.PaymentType.CREDIT,
        )
        from_other_workshop = PaymentMethod.objects.create(
            workshop=self.other_workshop,
            description="Pix externo",
            payment_type=PaymentMethod.PaymentType.BOTH,
        )

        self.assertFalse(self._form(wrong_direction.pk).is_valid())
        self.assertFalse(self._form(from_other_workshop.pk).is_valid())

    def test_accepts_custom_installment_schedule(self) -> None:
        payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Boleto",
            payment_type=PaymentMethod.PaymentType.DEBIT,
            installments_count=1,
        )

        form = self._form(
            payment_method.pk,
            installments_count="3",
            total_amount=Decimal("1200.00"),
            extra={
                "installment_due_date": ["2026-09-15", "2026-10-15", "2026-11-15"],
                "installment_amount": ["400.00", "400.00", "400.00"],
            },
        )

        self.assertTrue(form.is_valid())
        schedule = form.cleaned_data["installment_schedule"]
        self.assertEqual(len(schedule), 3)
        self.assertEqual(schedule[0].amount, Decimal("400.00"))
        self.assertEqual(schedule[2].due_date, date(2026, 11, 15))

    def test_rejects_installment_schedule_that_does_not_sum_to_total(self) -> None:
        payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Boleto",
            payment_type=PaymentMethod.PaymentType.DEBIT,
        )

        form = self._form(
            payment_method.pk,
            installments_count="2",
            total_amount=Decimal("1200.00"),
            extra={
                "installment_due_date": ["2026-09-15", "2026-10-15"],
                "installment_amount": ["400.00", "400.00"],
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("A soma das parcelas deve ser igual ao total agrupado.", form.non_field_errors())


class GroupInstallmentScheduleServiceTests(TestCase):
    def test_parses_brazilian_amounts_and_uneven_dates(self) -> None:
        schedule = parse_group_installment_schedule(
            due_dates=["2026-09-15", "2026-10-15", "2026-11-15"],
            amounts=["400,00", "400,00", "400,00"],
            expected_count=3,
            expected_total=Decimal("1200.00"),
        )

        self.assertEqual([item.due_date for item in schedule], [date(2026, 9, 15), date(2026, 10, 15), date(2026, 11, 15)])
        self.assertEqual(sum((item.amount for item in schedule), Decimal("0.00")), Decimal("1200.00"))

    def test_rejects_wrong_count(self) -> None:
        with self.assertRaises(InstallmentScheduleError):
            parse_group_installment_schedule(
                due_dates=["2026-09-15"],
                amounts=["1200.00"],
                expected_count=3,
                expected_total=Decimal("1200.00"),
            )


class GroupedMovementsOverviewTests(TestCase):
    def test_grouped_children_do_not_duplicate_the_consolidated_installment(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Indicadores",
            cnpj="11.111.111/0001-11",
            phone="+5511977777777",
            address="Rua dos Indicadores, 300",
        )
        due_date = date(2026, 8, 21)
        group = MovementGroup.objects.create(workshop=workshop, name="Teste", due_date=due_date)
        FinancialMovement.objects.create(
            workshop=workshop,
            movement_group=group,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Lançamento original 1",
            amount=Money(10, "BRL"),
            due_date=due_date,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            movement_group=group,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Lançamento original 2",
            amount=Money(20, "BRL"),
            due_date=due_date,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            movement_group=group,
            movement_kind=FinancialMovement.MovementKind.GROUP_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Parcela 1/10",
            amount=Money(3, "BRL"),
            due_date=due_date,
        )

        overview = build_financial_overview_with_open_workorder_credits(
            workshop=workshop,
            start_date=due_date,
            end_date=due_date,
        )

        self.assertEqual(open_credits(overview), Money(3, "BRL"))
