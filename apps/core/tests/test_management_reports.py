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

    def test_management_report_pdf_allows_iframe_embedding(self) -> None:
        from apps.core.domain.contracts.documents import DocumentPayload

        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        fake_document = DocumentPayload(content=b"%PDF-1.4", filename="relatorio.pdf", content_type="application/pdf")
        with patch(
            "apps.core.presentation.management_report_views.render_management_report_pdf",
            return_value=fake_document,
        ):
            response = self.client.get(
                reverse("core:management_report_pdf"),
                {"tipo": "estoque_minimo", "ano": "2026", "mes": "9"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.get("X-Frame-Options", "").upper(), "DENY")

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
        self.assertIn("whitespace-nowrap", content)
        self.assertIn("managementReportPdfModal", content)
        self.assertIn("open-pdf-modal", content)


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


class MecanicosRetrabalhoTests(SimpleTestCase):
    def test_workorder_cost_loss_labor_excludes_parts(self) -> None:
        from apps.core.infrastructure.services.management_reports.performance import _workorder_cost_loss
        from apps.workorder.models import WorkOrderCourtesyReasonType

        workorder = SimpleNamespace(
            total_costs_services_value=Money("80.00", "BRL"),
            total_third_party_services_cost=Money("20.00", "BRL"),
            total_costs_products_value=Money("500.00", "BRL"),
        )
        self.assertEqual(
            _workorder_cost_loss(workorder, reason_type=WorkOrderCourtesyReasonType.LABOR_FAILURE),  # type: ignore[arg-type]
            Decimal("100.00"),
        )
        self.assertEqual(
            _workorder_cost_loss(workorder, reason_type=WorkOrderCourtesyReasonType.BOTH),  # type: ignore[arg-type]
            Decimal("600.00"),
        )


class MecanicosRetrabalhoFilterTests(TestCase):
    def setUp(self) -> None:
        from datetime import datetime

        from apps.budget.models import Budget, BudgetStatus
        from apps.collaborators.test_commissions import create_collaborator
        from apps.workorder.models import WorkOrder, WorkOrderCourtesyReasonType, WorkOrderStatus

        account = Account.objects.create(name="Conta Retrabalho")
        self.user = User.objects.create_user(username="retrabalho-user", password="secret", cpf="39053344705")
        self.user.account = account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Retrabalho",
            cnpj="11.222.333/0001-99",
            phone="+5511988887777",
            address="Rua Teste, 10",
        )
        role = get_or_create_director_role(account=account)
        WorkshopMember.objects.create(workshop=self.workshop, user=self.user, role=role, is_active=True)
        self.mechanic = create_collaborator(workshop=self.workshop, suffix=77)

        def _create_benefit(*, budget_type: str, reason: str, day: int) -> WorkOrder:
            budget = Budget.objects.create(
                workshop=self.workshop,
                entry_date=timezone.localdate(),
                status=BudgetStatus.APPROVED,
                budget_type=budget_type,
            )
            wo = WorkOrder.objects.create(
                workshop=self.workshop,
                budget=budget,
                status=WorkOrderStatus.APPROVED,
                budget_type=budget_type,
                previous_mechanic=self.mechanic,
                courtesy_reason_type=reason,
            )
            WorkOrder.objects.filter(pk=wo.pk).update(
                delivered_at=timezone.make_aware(datetime(2026, 9, day)),
            )
            return WorkOrder.objects.get(pk=wo.pk)

        self.labor_wo = _create_benefit(budget_type="warranty", reason=WorkOrderCourtesyReasonType.LABOR_FAILURE, day=5)
        self.both_wo = _create_benefit(budget_type="courtesy", reason=WorkOrderCourtesyReasonType.BOTH, day=6)
        self.parts_wo = _create_benefit(budget_type="warranty", reason=WorkOrderCourtesyReasonType.PART_DEFECT, day=7)

    def test_build_excludes_part_defect_and_uses_os_cost(self) -> None:
        from apps.core.infrastructure.services.management_reports.performance import build_mecanicos_retrabalho

        period = ReportPeriod(month=9, year=2026)

        def fake_loss(workorder, *, reason_type):
            if workorder.pk == self.labor_wo.pk:
                return Decimal("100.00")
            if workorder.pk == self.both_wo.pk:
                return Decimal("250.00")
            return Decimal("999.00")

        with patch(
            "apps.core.infrastructure.services.management_reports.performance._workorder_cost_loss",
            side_effect=fake_loss,
        ):
            report = build_mecanicos_retrabalho(workshop=self.workshop, period=period)

        self.assertEqual(len(report.rows), 1)
        row = report.rows[0]
        self.assertEqual(row["qtd_veiculos"], 2)
        self.assertEqual(Decimal(str(row["perda"])), Decimal("350.00"))
        self.assertEqual(report.total_value, Decimal("350.00"))


class VendasModalidadeReportTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta Modalidade")
        self.user = User.objects.create_user(username="modalidade-user", password="secret", cpf="39053344706")
        self.user.account = account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Modalidade",
            cnpj="11.222.333/0001-82",
            phone="+5511988887778",
            address="Rua Modalidade, 10",
        )
        role = get_or_create_director_role(account=account)
        WorkshopMember.objects.create(workshop=self.workshop, user=self.user, role=role, is_active=True)

    def test_build_vendas_modalidade_does_not_raise_field_error(self) -> None:
        from apps.core.infrastructure.services.management_reports.sales import build_vendas_modalidade

        period = ReportPeriod(month=9, year=2026)
        report = build_vendas_modalidade(workshop=self.workshop, period=period)
        self.assertEqual(report.report_key, "vendas_modalidade")
        self.assertEqual(report.rows, [])


class RentabilidadeAcumuladaReportTests(TestCase):
    def setUp(self) -> None:
        from datetime import datetime

        from apps.budget.models import Budget, BudgetStatus
        from apps.workorder.models import WorkOrder, WorkOrderStatus

        account = Account.objects.create(name="Conta Rentabilidade")
        self.user = User.objects.create_user(username="rentabilidade-user", password="secret", cpf="39053344707")
        self.user.account = account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Rentabilidade",
            cnpj="11.222.333/0001-83",
            phone="+5511988887779",
            address="Rua Rentabilidade, 10",
        )
        role = get_or_create_director_role(account=account)
        WorkshopMember.objects.create(workshop=self.workshop, user=self.user, role=role, is_active=True)

        for day in (5, 6):
            budget = Budget.objects.create(
                workshop=self.workshop,
                entry_date=timezone.localdate(),
                status=BudgetStatus.APPROVED,
                budget_type="sale",
            )
            wo = WorkOrder.objects.create(
                workshop=self.workshop,
                budget=budget,
                status=WorkOrderStatus.APPROVED,
                budget_type="sale",
                stored_total_amount=Money("100.00", "BRL"),
            )
            WorkOrder.objects.filter(pk=wo.pk).update(
                delivered_at=timezone.make_aware(datetime(2026, 9, day)),
            )

    def test_build_rentabilidade_acumulada_completes_for_delivered_sales(self) -> None:
        from apps.core.infrastructure.services.management_reports.performance import build_rentabilidade_acumulada

        period = ReportPeriod(month=9, year=2026)
        report = build_rentabilidade_acumulada(workshop=self.workshop, period=period)
        self.assertEqual(report.report_key, "rentabilidade_acumulada")
        self.assertEqual(report.record_count, 2)
        self.assertTrue(all(Decimal(str(row["valor_bruto"])) == Decimal("100.00") for row in report.rows))
