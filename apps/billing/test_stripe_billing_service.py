from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.billing.domain.contracts import BillingServiceError
from apps.billing.infrastructure.services.stripe_billing import (
    PUBLIC_PLANS_CACHE_KEY,
    StripeBillingService,
)


@override_settings(
    STRIPE_PRODUCT_ID_BASIC="",
    STRIPE_PRODUCT_ID_FULL="prod_full",
    STRIPE_PRICE_ID_BASIC="price_basic_legacy",
    STRIPE_PRICE_ID_FULL="price_full_legacy",
)
class StripeBillingServiceProductTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.delete(PUBLIC_PLANS_CACHE_KEY)
        self.service = StripeBillingService()

    def tearDown(self) -> None:
        cache.delete(PUBLIC_PLANS_CACHE_KEY)

    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.retrieve_price")
    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.retrieve_product_plan")
    def test_list_public_plans_uses_product_when_configured(
        self,
        retrieve_product_plan,
        retrieve_price,
    ) -> None:
        retrieve_product_plan.return_value = {
            "id": "price_full_new",
            "unit_amount": 24900,
            "currency": "brl",
            "interval": "month",
            "product_id": "prod_full",
            "product_name": "Completo",
            "product_description": "",
            "marketing_features": ["OS", "Estoque"],
        }
        retrieve_price.return_value = {
            "id": "price_basic_legacy",
            "unit_amount": 6000,
            "currency": "brl",
            "interval": "month",
            "product_id": "prod_basic",
            "product_name": "Orçamento",
            "product_description": "",
            "marketing_features": ["Orçamentos"],
        }

        plans = {card.key: card for card in self.service.list_public_plans()}

        self.assertEqual(plans["full"].stripe_price_id, "price_full_new")
        self.assertEqual(plans["full"].unit_amount, 24900)
        self.assertEqual(plans["full"].price_label, "R$ 249,00")
        self.assertEqual(plans["full"].features, ("OS", "Estoque"))
        retrieve_product_plan.assert_called_once_with(product_id="prod_full")
        retrieve_price.assert_called_once_with(price_id="price_basic_legacy")

    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.retrieve_price")
    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.retrieve_product_plan")
    def test_list_public_plans_falls_back_to_legacy_price(
        self,
        retrieve_product_plan,
        retrieve_price,
    ) -> None:
        with override_settings(STRIPE_PRODUCT_ID_FULL="", STRIPE_PRODUCT_ID_BASIC=""):
            cache.delete(PUBLIC_PLANS_CACHE_KEY)
            retrieve_price.side_effect = [
                {
                    "id": "price_basic_legacy",
                    "unit_amount": 6000,
                    "currency": "brl",
                    "interval": "month",
                    "product_id": "",
                    "product_name": "Orçamento",
                    "product_description": "",
                    "marketing_features": [],
                },
                {
                    "id": "price_full_legacy",
                    "unit_amount": 16000,
                    "currency": "brl",
                    "interval": "month",
                    "product_id": "",
                    "product_name": "Completo",
                    "product_description": "",
                    "marketing_features": [],
                },
            ]

            plans = {card.key: card for card in self.service.list_public_plans()}

        self.assertEqual(plans["full"].stripe_price_id, "price_full_legacy")
        self.assertEqual(plans["full"].unit_amount, 16000)
        retrieve_product_plan.assert_not_called()

    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.create_checkout_session")
    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.retrieve_product_plan")
    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.retrieve_price")
    def test_create_checkout_session_resolves_current_price(
        self,
        retrieve_price,
        retrieve_product_plan,
        create_checkout,
    ) -> None:
        retrieve_product_plan.return_value = {
            "id": "price_full_new",
            "unit_amount": 24900,
            "currency": "brl",
            "interval": "month",
            "product_id": "prod_full",
            "product_name": "Completo",
            "product_description": "",
            "marketing_features": [],
        }
        retrieve_price.return_value = {
            "id": "price_basic_legacy",
            "unit_amount": 6000,
            "currency": "brl",
            "interval": "month",
            "product_id": "",
            "product_name": "Orçamento",
            "product_description": "",
            "marketing_features": [],
        }
        create_checkout.return_value = {"id": "cs_1", "url": "https://checkout.example/1"}

        from apps.billing.domain.contracts import CheckoutSessionRequest

        self.service.create_checkout_session(
            CheckoutSessionRequest(
                plan="full",
                success_url="https://example.com/ok",
                cancel_url="https://example.com/cancel",
                customer_email="ana@example.com",
                account_id=1,
            )
        )

        self.assertEqual(create_checkout.call_args.kwargs["price_id"], "price_full_new")

    @patch("apps.billing.infrastructure.services.stripe_billing.stripe_gateway.retrieve_product_plan")
    def test_list_public_plans_keeps_fallback_on_stripe_error(self, retrieve_product_plan) -> None:
        retrieve_product_plan.side_effect = BillingServiceError("falha")

        with override_settings(STRIPE_PRODUCT_ID_BASIC="prod_basic"):
            cache.delete(PUBLIC_PLANS_CACHE_KEY)
            plans = {card.key: card for card in self.service.list_public_plans()}

        self.assertEqual(plans["full"].price_label, "Consulte")
        self.assertEqual(plans["full"].stripe_price_id, "price_full_legacy")
