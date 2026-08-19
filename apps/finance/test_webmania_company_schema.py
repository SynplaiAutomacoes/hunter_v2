from __future__ import annotations

from django.db import connection
from django.test import TestCase

from apps.finance.models.finance import WebmaniaCompany
from apps.workshops.models.workshops import Workshop


class WebmaniaCompanySchemaTests(TestCase):
    def test_nfce_enabled_column_exists(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s
                  AND column_name = %s
                """,
                ["finance_webmaniacompany", "nfce_enabled"],
            )
            self.assertIsNotNone(cursor.fetchone())

    def test_workshop_pdf_name_loads_webmania_company_from_db(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Schema",
            cnpj="41.222.333/0001-01",
            phone="+5511999999999",
            address="Rua Schema, 123",
        )
        WebmaniaCompany.objects.create(workshop=workshop, nome_fantasia="Fantasia Schema")

        reloaded = Workshop.objects.get(pk=workshop.pk)

        self.assertEqual(reloaded.pdf_name, "Fantasia Schema")
        self.assertIs(reloaded.webmania_company.nfce_enabled, False)
