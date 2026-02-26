from __future__ import annotations

import base64
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account, User
from apps.collaborators.models import WorkshopMember
from apps.finance.models import WebmaniaCompany
from apps.finance.services.webmania_secrets import decrypt_secret
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"workshop_director{suffix}", password="123", cpf=f"22233344{suffix:03d}")
    account = Account.objects.create(name=f"Conta Workshop {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Workshop {suffix}",
        cnpj=f"21.222.444/0001-{suffix:02d}",
        phone="+5511988887777",
        address="Rua Oficina, 10",
        uf="SP",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)

    return user, workshop


class WorkshopWebmaniaIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=11)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_finance_requests_url_redirects_to_management_history(self) -> None:
        response = self.client.get(reverse("finance:webmania_requests"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("workshops:emission_history"))

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_sync_endpoint_blocks_outside_homolog_environment(self) -> None:
        with patch("apps.workshops.views.workshops.sync_b2b_companies_to_database") as sync_mock:
            response = self.client.post(reverse("workshops:webmania_company_sync"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("workshops:list"))
        sync_mock.assert_not_called()

    def test_workshop_update_page_renders_tabs_and_updates_company_data(self) -> None:
        response = self.client.get(reverse("workshops:update", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresa")
        self.assertContains(response, "Endereco")
        self.assertContains(response, "Nota Fiscal")
        self.assertContains(response, "Certificados")
        self.assertContains(response, "Opcionais")
        self.assertContains(response, "Credenciais")

        with patch("apps.workshops.views.workshops.update_webmania_company", return_value={"success": True}) as update_mock:
            post_response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={
                    "tab": "empresa",
                    "nf_tab": "nfe",
                    "tipo_tributacao": "simples_nacional",
                    "regime_tributario": "",
                    "cnpj": "11.222.333/0001-81",
                    "razao_social": "Empresa Integrada",
                    "cpf": "",
                    "nome_completo": "",
                    "nome_fantasia": "Empresa Integrada",
                    "ie": "",
                    "im": "",
                    "unidade_empresa": "matriz",
                    "email": "fiscal@empresa.com",
                    "telefone": "",
                    "contabilidade": "",
                    "logomarca": "",
                    "workshop_is_active": "on",
                },
            )

        self.assertEqual(post_response.status_code, 302)
        update_mock.assert_called_once()

        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.name, "Empresa Integrada")

    def test_credentials_tab_is_read_only_without_editable_fields(self) -> None:
        response = self.client.get(reverse("workshops:update", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="consumer_key"')
        self.assertNotContains(response, 'name="consumer_secret"')
        self.assertNotContains(response, 'name="access_token"')
        self.assertNotContains(response, 'name="nfse_password"')
        self.assertNotContains(response, 'name="nfse_token"')

    def test_sefaz_certificate_save_does_not_sync_webmania_certificate(self) -> None:
        with patch("apps.workshops.views.workshops.update_webmania_company") as update_mock:
            response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={
                    "tab": "certificado",
                    "certificate_scope": "sefaz",
                    "nf_tab": "nfe",
                    "certificate_password": "senha-sefaz",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), f"{reverse('workshops:update', kwargs={'pk': self.workshop.pk})}?tab=certificado&nf_tab=nfe")
        update_mock.assert_not_called()

        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.certificate_password, "senha-sefaz")

    def test_webmania_certificate_save_keeps_sefaz_separated(self) -> None:
        certificate_bytes = b"certificado-a1-binario"
        certificate_file = SimpleUploadedFile(
            "certificado.pfx",
            certificate_bytes,
            content_type="application/x-pkcs12",
        )

        with patch("apps.workshops.views.workshops.update_webmania_company", return_value={"success": True}) as update_mock:
            response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={
                    "tab": "certificado",
                    "certificate_scope": "webmania",
                    "nf_tab": "nfe",
                    "certificado_arquivo": certificate_file,
                    "certificado_senha": "senha-webmania",
                },
            )

        self.assertEqual(response.status_code, 302)
        update_mock.assert_called_once()
        payload = update_mock.call_args.kwargs["payload"]
        self.assertEqual(payload.get("certificado"), base64.b64encode(certificate_bytes).decode())

        company = WebmaniaCompany.objects.get(workshop=self.workshop)
        self.assertEqual(decrypt_secret(company.certificado), base64.b64encode(certificate_bytes).decode())
        self.assertEqual(decrypt_secret(company.certificado_senha), "senha-webmania")

        self.workshop.refresh_from_db()
        self.assertFalse(bool(self.workshop.certificate_password))
