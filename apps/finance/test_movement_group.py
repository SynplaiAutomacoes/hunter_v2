from datetime import date

from django.test import TestCase

from apps.finance.forms.movement_group import GroupMovementStep3Form
from apps.finance.models import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
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

    def _form(self, payment_method: object = "") -> GroupMovementStep3Form:
        return GroupMovementStep3Form(
            data={
                "name": "Fechamento fornecedor",
                "description": "Contas agrupadas",
                "due_date": date(2026, 9, 15).isoformat(),
                "payment_method": payment_method,
            },
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.DEBIT,
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
