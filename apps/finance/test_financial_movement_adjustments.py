from decimal import Decimal

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.finance.forms.financial_movement import MovementStep3Form
from apps.finance.models.financial_movement import FinancialMovement


class FinancialMovementAdjustmentTests(SimpleTestCase):
    def test_surcharge_increases_the_net_amount(self):
        movement = FinancialMovement(
            gross_amount=Money(Decimal("100.00"), "BRL"),
            discount_mode=FinancialMovement.DiscountMode.SURCHARGE,
            discount_value=Money(Decimal("15.00"), "BRL"),
        )

        movement._sync_net_amount_from_discount()

        self.assertEqual(movement.amount, Money(Decimal("115.00"), "BRL"))
        self.assertEqual(movement.resolved_adjustment_amount, Money(Decimal("15.00"), "BRL"))
        self.assertEqual(movement.adjustment_label, "Acréscimo")

    def test_amount_discount_reduces_the_net_amount(self):
        movement = FinancialMovement(
            gross_amount=Money(Decimal("100.00"), "BRL"),
            discount_mode=FinancialMovement.DiscountMode.AMOUNT,
            discount_value=Money(Decimal("15.00"), "BRL"),
        )

        movement._sync_net_amount_from_discount()

        self.assertEqual(movement.amount, Money(Decimal("85.00"), "BRL"))
        self.assertEqual(movement.resolved_adjustment_amount, Money(Decimal("15.00"), "BRL"))
        self.assertEqual(movement.adjustment_label, "Desconto")

    def test_new_financial_movement_form_does_not_offer_percentage(self):
        form = MovementStep3Form()

        self.assertNotIn("discount_percentage", form.fields)
        self.assertEqual(
            dict(form.fields["discount_mode"].choices),
            {
                FinancialMovement.DiscountMode.NONE: "Sem desconto ou acréscimo",
                FinancialMovement.DiscountMode.AMOUNT: "Desconto",
                FinancialMovement.DiscountMode.SURCHARGE: "Acréscimo",
            },
        )
