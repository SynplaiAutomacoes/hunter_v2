from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.core.infrastructure.services.webmania.webmania import sync_workshop_from_company
from apps.workshops.models.workshops import Workshop


class WorkshopPdfNameTests(SimpleTestCase):
    def test_pdf_name_prefers_nome_fantasia(self) -> None:
        workshop = Workshop(name="Razao Social LTDA")
        workshop._cached_webmania_company = SimpleNamespace(nome_fantasia="Oficina Fantasia", telefone="")

        self.assertEqual(workshop.pdf_name, "Oficina Fantasia")

    def test_pdf_name_falls_back_to_workshop_name(self) -> None:
        workshop = Workshop(name="Oficina Sem Fantasia")
        workshop._cached_webmania_company = SimpleNamespace(nome_fantasia="", telefone="")

        self.assertEqual(workshop.pdf_name, "Oficina Sem Fantasia")

    def test_pdf_name_without_company_uses_workshop_name(self) -> None:
        workshop = Workshop(name="Oficina Local")
        workshop._cached_webmania_company = None

        self.assertEqual(workshop.pdf_name, "Oficina Local")


class SyncWorkshopNameFromCompanyTests(SimpleTestCase):
    def test_sync_name_prefers_nome_fantasia_over_razao_social(self) -> None:
        workshop = Workshop(name="Antigo")
        company = SimpleNamespace(
            nome_fantasia="Nome Fantasia",
            razao_social="Razao Social LTDA",
            nome_completo="",
            endereco="",
            numero="",
            uf="",
        )
        saved: list[list[str]] = []

        def fake_save(*, update_fields: list[str]) -> None:
            saved.append(list(update_fields))

        workshop.save = fake_save  # type: ignore[method-assign]

        sync_workshop_from_company(workshop, company, sync_name=True)

        self.assertEqual(workshop.name, "Nome Fantasia")
        self.assertEqual(saved, [["name"]])
