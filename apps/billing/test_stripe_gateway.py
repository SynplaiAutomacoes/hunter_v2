from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.billing.domain.contracts import BillingServiceError
from apps.billing.infrastructure.gateways.stripe import (
    construct_webhook_event,
    create_incomplete_subscription,
    resolve_discount,
    resolve_promotion_code,
    retrieve_price,
    retrieve_product_plan,
)


@override_settings(STRIPE_SECRET_KEY="sk_test_example")
class StripeGatewayTests(SimpleTestCase):
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Price.retrieve")
    def test_retrieve_price_converts_stripe_resource_to_dict(self, retrieve: Mock) -> None:
        price_resource = Mock()
        price_resource.to_dict.return_value = {
            "id": "price_basic",
            "unit_amount": 9900,
            "currency": "brl",
            "recurring": {"interval": "month"},
            "product": {
                "name": "Hunter Orçamento",
                "description": "Plano para emissão de orçamentos.",
                "marketing_features": [{"name": "Clientes e veículos"}, {"name": "Orçamentos"}],
            },
        }
        retrieve.return_value = price_resource

        result = retrieve_price(price_id="price_basic")

        price_resource.to_dict.assert_called_once_with()
        self.assertEqual(result["id"], "price_basic")
        self.assertEqual(result["unit_amount"], 9900)
        self.assertEqual(result["interval"], "month")
        self.assertEqual(result["product_name"], "Hunter Orçamento")
        self.assertEqual(result["marketing_features"], ["Clientes e veículos", "Orçamentos"])
        self.assertEqual(result["product_id"], "")

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Product.retrieve")
    def test_retrieve_product_plan_uses_expanded_default_price(self, retrieve_product: Mock) -> None:
        product_resource = Mock()
        product_resource.to_dict.return_value = {
            "id": "prod_full",
            "name": "Hunter Completo",
            "description": "Sistema completo.",
            "marketing_features": [{"name": "OS"}, {"name": "Estoque"}],
            "default_price": {
                "id": "price_full_new",
                "unit_amount": 24900,
                "currency": "brl",
                "active": True,
                "recurring": {"interval": "month"},
            },
        }
        retrieve_product.return_value = product_resource

        result = retrieve_product_plan(product_id="prod_full")

        retrieve_product.assert_called_once_with("prod_full", expand=["default_price"])
        self.assertEqual(result["id"], "price_full_new")
        self.assertEqual(result["unit_amount"], 24900)
        self.assertEqual(result["product_id"], "prod_full")
        self.assertEqual(result["product_name"], "Hunter Completo")
        self.assertEqual(result["marketing_features"], ["OS", "Estoque"])

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Price.list")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Product.retrieve")
    def test_retrieve_product_plan_falls_back_to_latest_active_price(
        self,
        retrieve_product: Mock,
        list_prices: Mock,
    ) -> None:
        product_resource = Mock()
        product_resource.to_dict.return_value = {
            "id": "prod_full",
            "name": "Hunter Completo",
            "description": "",
            "marketing_features": [],
            "default_price": {"id": "price_inactive", "active": False, "unit_amount": 100},
        }
        retrieve_product.return_value = product_resource
        list_prices.return_value = Mock(
            data=[
                {
                    "id": "price_old",
                    "created": 100,
                    "unit_amount": 16000,
                    "currency": "brl",
                    "recurring": {"interval": "month"},
                },
                {
                    "id": "price_new",
                    "created": 200,
                    "unit_amount": 24900,
                    "currency": "brl",
                    "recurring": {"interval": "month"},
                },
            ]
        )

        result = retrieve_product_plan(product_id="prod_full")

        list_prices.assert_called_once_with(product="prod_full", active=True, type="recurring", limit=100)
        self.assertEqual(result["id"], "price_new")
        self.assertEqual(result["unit_amount"], 24900)

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Price.list")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Product.retrieve")
    def test_retrieve_product_plan_raises_without_prices(
        self,
        retrieve_product: Mock,
        list_prices: Mock,
    ) -> None:
        product_resource = Mock()
        product_resource.to_dict.return_value = {
            "id": "prod_empty",
            "name": "Vazio",
            "default_price": None,
            "marketing_features": [],
        }
        retrieve_product.return_value = product_resource
        list_prices.return_value = Mock(data=[])

        with self.assertRaises(BillingServiceError):
            retrieve_product_plan(product_id="prod_empty")

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.create")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Customer.create")
    def test_create_incomplete_subscription_reads_confirmation_secret(self, create_customer: Mock, create_subscription: Mock) -> None:
        create_customer.return_value = Mock(id="cus_1", to_dict=Mock(return_value={"id": "cus_1"}))
        subscription = Mock()
        subscription.to_dict.return_value = {
            "id": "sub_1",
            "latest_invoice": {
                "id": "in_1",
                "confirmation_secret": {"client_secret": "pi_secret_123", "type": "payment_intent"},
            },
        }
        create_subscription.return_value = subscription

        result = create_incomplete_subscription(
            email="ana@example.com",
            customer_name="Ana",
            plan="basic",
            price_id="price_basic",
            pending_signup_id=7,
        )

        self.assertEqual(result["client_secret"], "pi_secret_123")
        self.assertEqual(result["subscription_id"], "sub_1")
        expand = create_subscription.call_args.kwargs["expand"]
        self.assertIn("latest_invoice.confirmation_secret", expand)
        self.assertNotIn("discounts", create_subscription.call_args.kwargs)

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.PromotionCode.list")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.create")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Customer.create")
    def test_create_incomplete_subscription_applies_promotion_code(
        self,
        create_customer: Mock,
        create_subscription: Mock,
        list_promo: Mock,
    ) -> None:
        create_customer.return_value = Mock(id="cus_1", to_dict=Mock(return_value={"id": "cus_1"}))
        list_promo.return_value = Mock(data=[Mock(id="promo_abc")])
        subscription = Mock()
        subscription.to_dict.return_value = {
            "id": "sub_1",
            "latest_invoice": {
                "id": "in_1",
                "confirmation_secret": {"client_secret": "pi_secret_123", "type": "payment_intent"},
            },
        }
        create_subscription.return_value = subscription

        create_incomplete_subscription(
            email="ana@example.com",
            customer_name="Ana",
            plan="basic",
            price_id="price_basic",
            pending_signup_id=7,
            promotion_code="DESCONTO10",
        )

        self.assertEqual(create_subscription.call_args.kwargs["discounts"], [{"promotion_code": "promo_abc"}])

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.PromotionCode.list")
    def test_resolve_promotion_code_rejects_unknown(self, list_promo: Mock) -> None:
        list_promo.return_value = Mock(data=[])
        with self.assertRaises(BillingServiceError):
            resolve_promotion_code("INVALIDO")

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.PromotionCode.list")
    def test_resolve_discount_prefers_promotion_code(self, list_promo: Mock) -> None:
        list_promo.return_value = Mock(data=[Mock(id="promo_abc")])
        self.assertEqual(resolve_discount("HUNTER100"), {"promotion_code": "promo_abc"})

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Coupon.list")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Coupon.retrieve")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.PromotionCode.list")
    def test_resolve_discount_falls_back_to_coupon_by_name(
        self,
        list_promo: Mock,
        retrieve_coupon: Mock,
        list_coupon: Mock,
    ) -> None:
        import stripe as stripe_module

        list_promo.return_value = Mock(data=[])
        retrieve_coupon.side_effect = stripe_module.StripeError("not a coupon id")
        list_coupon.return_value = Mock(
            data=[{"id": "IaVK7htc", "name": "HUNTER100", "valid": True, "percent_off": 100}]
        )

        self.assertEqual(resolve_discount("HUNTER100"), {"coupon": "IaVK7htc"})

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Coupon.list")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Coupon.retrieve")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.PromotionCode.list")
    def test_resolve_discount_rejects_unknown_code(
        self,
        list_promo: Mock,
        retrieve_coupon: Mock,
        list_coupon: Mock,
    ) -> None:
        import stripe as stripe_module

        list_promo.return_value = Mock(data=[])
        retrieve_coupon.side_effect = stripe_module.StripeError("not a coupon id")
        list_coupon.return_value = Mock(data=[])

        with self.assertRaises(BillingServiceError):
            resolve_discount("NAOEXISTE")

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.create")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Customer.create")
    def test_create_incomplete_subscription_free_invoice_has_no_payment(self, create_customer: Mock, create_subscription: Mock) -> None:
        create_customer.return_value = Mock(id="cus_1", to_dict=Mock(return_value={"id": "cus_1"}))
        subscription = Mock()
        subscription.to_dict.return_value = {
            "id": "sub_1",
            "status": "active",
            "latest_invoice": {
                "id": "in_1",
                "status": "paid",
                "amount_due": 0,
                "total": 0,
                "confirmation_secret": None,
            },
        }
        create_subscription.return_value = subscription

        result = create_incomplete_subscription(
            email="ana@example.com",
            customer_name="Ana",
            plan="basic",
            price_id="price_basic",
            pending_signup_id=7,
            promotion_code="",
        )

        self.assertEqual(result["requires_payment"], False)
        self.assertEqual(result["client_secret"], "")
        self.assertEqual(result["subscription_id"], "sub_1")

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.create")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Customer.create")
    def test_create_incomplete_subscription_paid_invoice_still_raises_without_secret(self, create_customer: Mock, create_subscription: Mock) -> None:
        create_customer.return_value = Mock(id="cus_1", to_dict=Mock(return_value={"id": "cus_1"}))
        subscription = Mock()
        subscription.to_dict.return_value = {
            "id": "sub_1",
            "status": "incomplete",
            "latest_invoice": {
                "id": "in_1",
                "status": "open",
                "amount_due": 29990,
                "total": 29990,
                "confirmation_secret": {},
            },
        }
        create_subscription.return_value = subscription

        with self.assertRaises(BillingServiceError):
            create_incomplete_subscription(
                email="ana@example.com",
                customer_name="Ana",
                plan="basic",
                price_id="price_basic",
                pending_signup_id=7,
            )


class _StripeResource:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __getitem__(self, key: str):
        return self.payload[key]

    def to_dict(self) -> dict:
        return dict(self.payload)

    def __iter__(self):
        raise TypeError("Invoice is not iterable or a mapping; call .to_dict()")


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeWebhookGatewayTests(SimpleTestCase):
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Webhook.construct_event")
    def test_construct_webhook_event_converts_resource_to_dict(self, construct_event: Mock) -> None:
        invoice = _StripeResource({"id": "in_1", "customer": "cus_1", "subscription": "sub_1"})
        construct_event.return_value = _StripeResource(
            {
                "id": "evt_1",
                "type": "invoice.paid",
                "data": {"object": invoice},
            }
        )

        event = construct_webhook_event(payload=b"{}", signature_header="t=1,v1=abc")

        self.assertEqual(event["id"], "evt_1")
        self.assertEqual(event["type"], "invoice.paid")
        self.assertEqual(event["data"]["id"], "in_1")
        self.assertIsInstance(event["data"], dict)
