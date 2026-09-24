from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
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
from apps.core.infrastructure.services.management_reports.stock_reports import build_curva_abc
from apps.core.infrastructure.services.management_reports.types import ManagementReport, ReportColumnDef
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

    def test_management_report_filter_year_is_unlocalized(self) -> None:
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        response = self.client.get(reverse("core:management_report"), {"tipo": "estoque_minimo", "ano": "2026", "mes": "9"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name="ano" value="2026"', content)
        self.assertNotIn('name="ano" value="2,026"', content)
        self.assertNotIn('name="ano" value="2.026"', content)


class CurvaAbcClassificationTests(SimpleTestCase):
    def _sales_report(self, rows: list[dict[str, object]]) -> ManagementReport:
        return ManagementReport(
            report_key="produtos_mais_vendidos",
            title="Produtos mais vendidos",
            period_label="Setembro de 2026",
            workshop_name="Oficina",
            columns=[ReportColumnDef("codigo", "Código")],
            rows=rows,
            total_value=sum((Decimal(str(r["faturamento"])) for r in rows), Decimal("0.00")),
        )

    def test_curva_abc_classifies_by_revenue_not_quantity(self) -> None:
        # Quantity-first order would put cheap bulk SKUs ahead and inflate class A.
        sales_rows = [
            {"codigo": "QTY", "produto": "Alto volume baixo valor", "quantidade": 100, "faturamento": Decimal("50.00")},
            {"codigo": "REV", "produto": "Baixo volume alto valor", "quantidade": 1, "faturamento": Decimal("750.00")},
            {"codigo": "MID", "produto": "Intermediario", "quantidade": 2, "faturamento": Decimal("100.00")},
            {"codigo": "C1", "produto": "Cauda 1", "quantidade": 20, "faturamento": Decimal("20.00")},
            {"codigo": "C2", "produto": "Cauda 2", "quantidade": 20, "faturamento": Decimal("20.00")},
            {"codigo": "C3", "produto": "Cauda 3", "quantidade": 20, "faturamento": Decimal("20.00")},
            {"codigo": "C4", "produto": "Cauda 4", "quantidade": 20, "faturamento": Decimal("20.00")},
            {"codigo": "C5", "produto": "Cauda 5", "quantidade": 20, "faturamento": Decimal("20.00")},
        ]
        period = ReportPeriod(month=9, year=2026)
        with patch(
            "apps.core.infrastructure.services.management_reports.stock_reports.build_produtos_mais_vendidos",
            return_value=self._sales_report(sales_rows),
        ):
            report = build_curva_abc(workshop=SimpleNamespace(pdf_name="", name="Oficina"), period=period)

        by_code = {str(row["codigo"]): str(row["classe"]) for row in report.rows}
        self.assertEqual(by_code["REV"], "A")
        self.assertNotEqual(by_code["QTY"], "A")
        self.assertEqual(report.rows[0]["codigo"], "REV")
        class_counts = {cls: sum(1 for row in report.rows if row["classe"] == cls) for cls in ("A", "B", "C")}
        self.assertEqual(class_counts["A"], 1)
        self.assertGreater(class_counts["C"], class_counts["A"])

    def test_curva_abc_zero_total_marks_all_as_c(self) -> None:
        sales_rows = [
            {"codigo": "Z1", "produto": "Zero 1", "quantidade": 1, "faturamento": Decimal("0.00")},
            {"codigo": "Z2", "produto": "Zero 2", "quantidade": 2, "faturamento": Decimal("0.00")},
        ]
        period = ReportPeriod(month=9, year=2026)
        with patch(
            "apps.core.infrastructure.services.management_reports.stock_reports.build_produtos_mais_vendidos",
            return_value=self._sales_report(sales_rows),
        ):
            report = build_curva_abc(workshop=SimpleNamespace(pdf_name="", name="Oficina"), period=period)

        self.assertTrue(all(row["classe"] == "C" for row in report.rows))
