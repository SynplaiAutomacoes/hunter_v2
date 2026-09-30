from __future__ import annotations

from django.test import TestCase

from apps.core.infrastructure.services.webmania.webmania_secrets import decrypt_secret, encrypt_secret
from apps.finance.models.finance import WebmaniaCompany
from apps.workshops.forms.workshops import WorkshopFiscalSectionForm
from apps.workshops.models.workshops import Workshop


class WorkshopFiscalNfseAccessFormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina NFS-e Access",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua Fiscal, 100",
        )
        self.company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            nfse_login="",
            nfse_password=encrypt_secret("senha-antiga"),
            nfse_token=encrypt_secret("token-antigo"),
            nfse_rps_serie="A",
            cnae="4520-0/01",
        )

    def _form_data(self, **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "informacoes_fisco": self.company.informacoes_fisco,
            "nfe_serie": self.company.nfe_serie or "",
            "nfe_numero": self.company.nfe_numero or "",
            "nfce_serie": self.company.nfce_serie or "",
            "nfce_numero": self.company.nfce_numero or "",
            "nfce_id_csc": self.company.nfce_id_csc,
            "nfce_codigo_csc": self.company.nfce_codigo_csc,
            "nfse_rps_serie": self.company.nfse_rps_serie,
            "nfse_rps_numero": self.company.nfse_rps_numero or "",
            "nfse_lote_rps_numero": self.company.nfse_lote_rps_numero or "",
            "cnae_issqn": self.company.cnae_issqn,
            "cnae": self.company.cnae,
            "regime_apuracao_sn": self.company.regime_apuracao_sn,
            "regime_especial_nacional": self.company.regime_especial_nacional,
            "regime_especial_municipal": self.company.regime_especial_municipal,
            "nfse_login": self.company.nfse_login,
            "nfse_password": "",
            "nfse_token": "",
        }
        data.update(overrides)
        return data

    def test_build_api_payload_includes_nfse_login_and_password_when_changed(self) -> None:
        form = WorkshopFiscalSectionForm(
            data=self._form_data(nfse_login="portal.user", nfse_password="nova-senha"),
            instance=self.company,
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)

        payload = form.build_api_payload()

        self.assertEqual(payload.get("nfse_login"), "portal.user")
        self.assertEqual(payload.get("nfse_password"), "nova-senha")
        self.assertNotIn("nfse_token", payload)

    def test_blank_password_does_not_clear_existing_secret_or_payload(self) -> None:
        form = WorkshopFiscalSectionForm(
            data=self._form_data(nfse_login="portal.user", nfse_password="", nfse_token=""),
            instance=self.company,
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)

        payload = form.build_api_payload()
        self.assertEqual(payload.get("nfse_login"), "portal.user")
        self.assertNotIn("nfse_password", payload)
        self.assertNotIn("nfse_token", payload)

        form.save()
        self.company.refresh_from_db()
        self.assertEqual(self.company.nfse_login, "portal.user")
        self.assertEqual(decrypt_secret(self.company.nfse_password), "senha-antiga")
        self.assertEqual(decrypt_secret(self.company.nfse_token), "token-antigo")

    def test_save_encrypts_new_nfse_password(self) -> None:
        form = WorkshopFiscalSectionForm(
            data=self._form_data(nfse_login="mei.login", nfse_password="senha-nova"),
            instance=self.company,
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.company.refresh_from_db()
        self.assertEqual(self.company.nfse_login, "mei.login")
        self.assertEqual(decrypt_secret(self.company.nfse_password), "senha-nova")
        self.assertTrue(str(self.company.nfse_password).startswith("enc::"))
