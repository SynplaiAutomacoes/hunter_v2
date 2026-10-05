from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.billing.infrastructure.gateways.stripe import construct_webhook_event, create_incomplete_subscription, retrieve_price


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
