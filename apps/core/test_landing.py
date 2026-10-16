from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.infrastructure.models import MarketingLead

User = get_user_model()


class LandingPageTests(TestCase):
    def test_root_renders_new_commercial_landing(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:login"))
        self.assertNotContains(response, "https://hunterapp.io")
        self.assertContains(response, reverse("crm_auth"))
        self.assertContains(response, "Entrar no CRM")
        self.assertContains(response, "Hunter Auto")
        self.assertContains(response, "Já sou cliente")
        self.assertContains(response, "Conhecer o Hunter Auto")
        self.assertContains(response, "Sidney Gomes")
        self.assertContains(response, "Para criá-lo, Sidney reuniu")
        self.assertContains(response, "Plus+Jakarta+Sans")
        self.assertNotContains(response, "Quero este plano")
        self.assertNotContains(response, reverse("billing:subscribe"))
        self.assertNotContains(response, "DOMINE OS MOTORES DA LINHA JEEP")
        self.assertNotContains(response, "Criar conta")

    def test_crm_auth_page_renders(self) -> None:
        response = self.client.get(reverse("crm_auth"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acesso ao CRM")
        self.assertContains(response, "ÁREA COMERCIAL")
        self.assertContains(response, "Entrar no CRM")

    def test_crm_auth_staff_redirects_to_leads(self) -> None:
        user = User.objects.create_user(username="crm.staff", password="SenhaForte123!", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("crm_auth"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("admin:core_marketinglead_changelist"))

    def test_lead_submit_creates_marketing_lead(self) -> None:
        response = self.client.post(
            reverse("marketing_lead_submit"),
            data={
                "submission_id": "11111111-1111-4111-8111-111111111111",
                "name": "Ana Silva",
                "workshop": "Oficina Ana",
                "email": "ana@example.com",
                "whatsapp": "11999998888",
                "employees": "2 a 5",
                "revenue": "Até R$ 20 mil",
                "consent": "on",
                "source": "http://testserver/",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        lead = MarketingLead.objects.get(email="ana@example.com")
        self.assertEqual(lead.workshop, "Oficina Ana")
        self.assertEqual(lead.whatsapp, "11999998888")

    def test_privacy_and_terms_pages_render(self) -> None:
        privacy = self.client.get(reverse("privacy"))
        terms = self.client.get(reverse("terms"))
        self.assertEqual(privacy.status_code, 200)
        self.assertEqual(terms.status_code, 200)
        self.assertContains(privacy, "Política de Privacidade")
        self.assertContains(terms, "Termos de Uso")
