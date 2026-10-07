from __future__ import annotations

from django.test import SimpleTestCase

from apps.billing.catalog import description_for_plan_card, features_from_stripe_product, format_money_label, interval_label_for


class BillingCatalogHelpersTests(SimpleTestCase):
    def test_format_money_label_brl(self) -> None:
        self.assertEqual(format_money_label(unit_amount=9900, currency="brl"), "R$ 99,00")

    def test_format_money_label_missing_amount(self) -> None:
        self.assertEqual(format_money_label(unit_amount=None, currency="brl"), "Consulte")

    def test_interval_label_for_month(self) -> None:
        self.assertEqual(interval_label_for("month"), "/mês")

    def test_marketing_features_become_bullets(self) -> None:
        features = features_from_stripe_product(
            description="Texto introdutório",
            marketing_features=["Clientes", "Orçamentos"],
        )
        self.assertEqual(features, ("Clientes", "Orçamentos"))
        self.assertEqual(
            description_for_plan_card(
                description="Texto introdutório",
                features=features,
                used_marketing_features=True,
            ),
            "Texto introdutório",
        )

    def test_description_lines_become_bullets_when_product_has_no_features(self) -> None:
        description = "Clientes e veículos\n- Orçamentos\n• Termos"
        features = features_from_stripe_product(description=description, marketing_features=[])
        self.assertEqual(features, ("Clientes e veículos", "Orçamentos", "Termos"))
        self.assertEqual(
            description_for_plan_card(description=description, features=features, used_marketing_features=False),
            "",
        )
