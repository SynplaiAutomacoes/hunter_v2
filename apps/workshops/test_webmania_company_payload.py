from __future__ import annotations

from django.test import SimpleTestCase

from apps.finance.models.finance import WebmaniaCompany
from apps.workshops.forms.workshops import WorkshopAddressSectionForm, WorkshopCompanySectionForm
from apps.workshops.models.workshops import Workshop


class WorkshopWebmaniaCompanyPayloadTests(SimpleTestCase):
    def setUp(self) -> None:
        self.workshop = Workshop(
            name="Oficina Teste",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua A, 1",
            uf="SP",
        )

    def _company(self, **overrides: object) -> WebmaniaCompany:
        values: dict[str, object] = {
            "workshop": self.workshop,
            "cnpj": "12.345.678/0001-90",
            "razao_social": "Empresa Teste LTDA",
            "cpf": "",
            "nome_completo": "",
            "email": "a@b.com",
            "telefone": "11999999999",
            "cep": "01310100",
            "endereco": "Av Paulista",
            "numero": "1000",
            "bairro": "Bela Vista",
            "cidade": "Sao Paulo",
            "uf": "SP",
        }
        values.update(overrides)
        return WebmaniaCompany(**values)

    def _empresa_data(self, company: WebmaniaCompany, **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "tipo_tributacao": company.tipo_tributacao or "",
            "regime_tributario": company.regime_tributario or "",
            "cnpj": "12345678000190",
            "razao_social": company.razao_social or "",
            "cpf": "".join(ch for ch in str(company.cpf or "") if ch.isdigit())[:11],
            "nome_completo": company.nome_completo or "",
            "nome_fantasia": company.nome_fantasia or "",
            "ie": company.ie or "",
            "im": company.im or "",
            "unidade_empresa": company.unidade_empresa or "",
            "email": company.email or "a@b.com",
            "telefone": "+5511999999999",
            "contabilidade": company.contabilidade or "",
            "logomarca": company.logomarca or "",
            "workshop_is_active": "on",
            "whatsapp_phone": "",
            "cep": "".join(ch for ch in str(company.cep or "") if ch.isdigit())[:8],
            "endereco": company.endereco or "",
            "numero": company.numero or "",
            "complemento": company.complemento or "",
            "bairro": company.bairro or "",
            "cidade": company.cidade or "",
            "uf": company.uf or "",
        }
        data.update(overrides)
        return data

    def test_untouched_widget_fields_are_not_sent_to_webmania(self) -> None:
        company = self._company()
        data = self._empresa_data(company)

        company_form = WorkshopCompanySectionForm(data=data, instance=company, workshop=self.workshop)
        address_form = WorkshopAddressSectionForm(data=data, instance=company, workshop=self.workshop)

        self.assertTrue(company_form.is_valid(), company_form.errors)
        self.assertTrue(address_form.is_valid(), address_form.errors)
        self.assertEqual(company_form.build_api_payload(), {})
        self.assertEqual(address_form.build_api_payload(), {})

    def test_pj_update_clears_leftover_cpf_from_webmania_payload(self) -> None:
        company = self._company(cnpj="", razao_social="", cpf="390.533.447-05", nome_completo="Joao Silva")
        data = self._empresa_data(
            company,
            cnpj="12345678000190",
            razao_social="Empresa Teste LTDA",
            cpf="39053344705",
            nome_completo="Joao Silva",
        )

        form = WorkshopCompanySectionForm(data=data, instance=company, workshop=self.workshop)
        self.assertTrue(form.is_valid(), form.errors)

        payload = form.build_api_payload()
        self.assertEqual(payload.get("cnpj"), "12345678000190")
        self.assertEqual(payload.get("razao_social"), "Empresa Teste Ltda")
        self.assertEqual(payload.get("cpf"), "")
        self.assertEqual(payload.get("nome_completo"), "")
        self.assertNotIn("telefone", payload)

        saved = form.save(commit=False)
        self.assertEqual(saved.cpf, "")
        self.assertEqual(saved.nome_completo, "")
        self.assertEqual(saved.cnpj, "12345678000190")

    def test_truncated_cnpj_in_cpf_field_is_cleared_for_pj(self) -> None:
        company = self._company(cpf="12.345.678/0001-90", nome_completo="")
        data = self._empresa_data(company, cpf="12345678000", nome_completo="")

        form = WorkshopCompanySectionForm(data=data, instance=company, workshop=self.workshop)
        self.assertTrue(form.is_valid(), form.errors)

        payload = form.build_api_payload()
        self.assertEqual(payload.get("cpf"), "")
        self.assertEqual(payload.get("nome_completo"), "")
        self.assertNotIn("cnpj", payload)

        saved = form.save(commit=False)
        self.assertEqual(saved.cpf, "")
        self.assertEqual(saved.cnpj, "12.345.678/0001-90")
