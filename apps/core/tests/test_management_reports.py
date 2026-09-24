from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.collaborators.models import WorkshopMember
from apps.core.infrastructure.services.management_reports import (
    build_management_report,
    build_management_report_excel,
    parse_report_period,
)
from apps.core.infrastructure.services.management_reports.period import ReportPeriod
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop
from djmoney.money import Money

User = get_user_model()


class ManagementReportsBuilderTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta Relatorios")
        self.user = User.objects.create_user(username="relatorios-user", password="secret", cpf="39053344705")
        self.user.account = account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Relatorios",
            cnpj="11.222.333/0001-81",
            phone="+5511988887777",
            address="Rua Teste, 10",
        )
        role = get_or_create_director_role(account=account)
        WorkshopMember.objects.create(workshop=self.workshop, user=self.user, role=role, is_active=True)
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Teste")
        product = Product.objects.create(
            workshop=self.workshop,
            code="P1",
            name="Produto Teste",
            description="Desc",
            unit="UND",
            group=group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        stock = product.stock_products
        stock.current_quantity = 1
        stock.minimum_quantity = 5
        stock.save(update_fields=["current_quantity", "minimum_quantity"])

    def test_build_estoque_minimo_and_excel(self) -> None:
        today = timezone.localdate()
        period = ReportPeriod(month=today.month, year=today.year)
        report = build_management_report(workshop=self.workshop, period=period, report_key="estoque_minimo")
        assert report is not None
        self.assertEqual(report.report_key, "estoque_minimo")
        self.assertEqual(report.record_count, 1)
        document = build_management_report_excel(report=report)
        self.assertTrue(document.filename.endswith(".xlsx"))
        self.assertGreater(len(document.content), 0)

    def test_management_report_urls_resolve(self) -> None:
        self.assertEqual(reverse("core:management_report"), "/core/reports/view/")
        self.assertEqual(reverse("core:management_report_excel"), "/core/reports/excel/")
        self.assertEqual(reverse("core:management_report_pdf"), "/core/reports/pdf/")

    def test_parse_report_period_from_request_like_mapping(self) -> None:
        class FakeRequest:
            GET = {"mes": "3", "ano": "2025"}

        period = parse_report_period(FakeRequest())  # type: ignore[arg-type]
        self.assertEqual(period.month, 3)
        self.assertEqual(period.year, 2025)
