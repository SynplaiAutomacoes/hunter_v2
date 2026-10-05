from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse

from apps.billing.domain.contracts import PublicPlanCard
from apps.billing.domain.plans import Plan


class LandingPageTests(SimpleTestCase):
    def test_root_renders_landing_with_login_link(self) -> None:
        plans = [
            PublicPlanCard(
                key=Plan.BASIC,
                name="Orçamento",
                description="Plano básico",
                features=("Clientes e veículos",),
                price_label="R$ 99,00",
                interval_label="/mês",
                currency="brl",
                unit_amount=9900,
                stripe_price_id="price_basic",
            ),
            PublicPlanCard(
                key=Plan.FULL,
                name="Completo",
                description="Plano completo",
                features=("Ordens de serviço",),
                price_label="R$ 199,00",
                interval_label="/mês",
                currency="brl",
                unit_amount=19900,
                stripe_price_id="price_full",
            ),
        ]

        with patch("apps.billing.infrastructure.providers.get_billing_service") as get_service:
            get_service.return_value.list_public_plans.return_value = plans
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, "DOMINE OS MOTORES DA LINHA JEEP")
        self.assertContains(response, "Entrar")
        self.assertContains(response, "SÓ DEPENDE DE VOCÊ")
        self.assertContains(response, "Orçamento")
        self.assertContains(response, "Completo")
        self.assertContains(response, "R$ 99,00")
        self.assertContains(response, "R$ 199,00")
        self.assertContains(response, "Quero este plano")
        self.assertContains(response, f"{reverse('billing:subscribe')}?plan=basic")
        self.assertContains(response, f"{reverse('billing:subscribe')}?plan=full")
        self.assertNotContains(response, f"{reverse('accounts:login')}?next=")
