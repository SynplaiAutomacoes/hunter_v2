from django.test import TestCase

from apps.accounts.models import Account
from apps.core.infrastructure.services.webmania.webmania import sync_workshop_from_company
from apps.finance.models.finance import WebmaniaCompany
from apps.workshops.models.workshops import Workshop


class WorkshopPdfHeaderIdentityTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta PDF")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Hunter Itapecerica da Serra",
            cnpj="22.501.102/0001-23",
            phone="+5511944712143",
            address="Av. Guacy Fernandes Domingues, 79",
        )

    def test_nome_fantasia_does_not_fall_back_to_razao_social(self) -> None:
        WebmaniaCompany.objects.create(
            workshop=self.workshop,
            razao_social="S.A Gomes Lubrificantes",
            nome_fantasia="",
        )
        workshop = Workshop.objects.get(pk=self.workshop.pk)

        self.assertEqual(workshop.nome_fantasia_display, "Hunter Itapecerica da Serra")
        self.assertEqual(workshop.razao_social_display, "S.A Gomes Lubrificantes")

    def test_prefers_company_nome_fantasia_over_workshop_name(self) -> None:
        WebmaniaCompany.objects.create(
            workshop=self.workshop,
            razao_social="S.A Gomes Lubrificantes",
            nome_fantasia="Hunter Itapecerica da Serra",
        )
        self.workshop.name = "S.A Gomes Lubrificantes"
        self.workshop.save(update_fields=["name"])
        workshop = Workshop.objects.get(pk=self.workshop.pk)

        self.assertEqual(workshop.nome_fantasia_display, "Hunter Itapecerica da Serra")
        self.assertEqual(workshop.razao_social_display, "S.A Gomes Lubrificantes")

    def test_sync_name_prefers_nome_fantasia(self) -> None:
        company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            razao_social="S.A Gomes Lubrificantes",
            nome_fantasia="Hunter Itapecerica da Serra",
        )
        self.workshop.name = "S.A Gomes Lubrificantes"
        self.workshop.save(update_fields=["name"])

        sync_workshop_from_company(self.workshop, company, sync_name=True)

        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.name, "Hunter Itapecerica da Serra")
