from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase

from apps.accounts.models import Account
from apps.core.infrastructure.models.dashboard_monthly_snapshot import DashboardMonthlySnapshot
from apps.core.infrastructure.services.dashboard_query_service import calculate_markup_progress, resolve_markup_gauge_tone
from apps.core.infrastructure.services.dashboard_snapshot_service import metrics_from_snapshot
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop

SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


class MarkupGaugeHelperTests(SimpleTestCase):
    def test_progress_is_proportional_to_monthly_mlr_target(self) -> None:
        target = Decimal("3.4")
        self.assertEqual(calculate_markup_progress(Decimal("3.4"), target), 100)
        self.assertEqual(calculate_markup_progress(Decimal("1.7"), target), 50)
        self.assertEqual(calculate_markup_progress(Decimal("6.8"), target), 100)

    def test_progress_is_zero_without_valid_target(self) -> None:
        self.assertEqual(calculate_markup_progress(Decimal("3.4"), None), 0)
        self.assertEqual(calculate_markup_progress(Decimal("3.4"), Decimal("0")), 0)
        self.assertEqual(calculate_markup_progress(Decimal("3.4"), Decimal("-1")), 0)

    def test_tone_bands_use_absolute_distance_below_target(self) -> None:
        target = Decimal("3.4")
        self.assertEqual(resolve_markup_gauge_tone(Decimal("3.4"), target), "success")
        self.assertEqual(resolve_markup_gauge_tone(Decimal("4.0"), target), "success")
        self.assertEqual(resolve_markup_gauge_tone(Decimal("3.2"), target), "success")
        self.assertEqual(resolve_markup_gauge_tone(Decimal("3.19"), target), "warning")
        self.assertEqual(resolve_markup_gauge_tone(Decimal("2.8"), target), "warning")
        self.assertEqual(resolve_markup_gauge_tone(Decimal("2.79"), target), "error")

    def test_tone_is_error_without_valid_target(self) -> None:
        self.assertEqual(resolve_markup_gauge_tone(Decimal("3.4"), None), "error")
        self.assertEqual(resolve_markup_gauge_tone(Decimal("3.4"), Decimal("0")), "error")


class MarkupGaugeSnapshotTests(TestCase):
    def test_metrics_from_snapshot_recomputes_progress_and_tone_from_mlr_target(self) -> None:
        account = Account.objects.create(name="Conta markup gauge")
        workshop = Workshop.objects.create(account=account, name="Oficina markup", cnpj="30000000000001", uf="SP")
        WorkshopCost.objects.create(
            workshop=workshop,
            month=7,
            year=2026,
            mechanic_quantity=1,
            work_days_per_month=22,
            profitability_multiplier=Decimal("3.40"),
        )
        closed_at = datetime(2026, 7, 31, 23, 59, 59, 999999, tzinfo=SAO_PAULO_TZ)
        snapshot = DashboardMonthlySnapshot.objects.create(
            workshop=workshop,
            year=2026,
            month=7,
            closed_at=closed_at,
            captured_at=closed_at,
            accumulated_markup=Decimal("1.70"),
            accumulated_markup_progress=85,  # stale value from old formula
        )

        metrics = metrics_from_snapshot(snapshot)

        self.assertEqual(metrics.accumulated_markup_progress, 50)
        self.assertEqual(metrics.accumulated_markup_tone, "error")
        context = metrics.as_context()
        self.assertEqual(context["markup_acumulado_progresso"], 50)
        self.assertEqual(context["markup_acumulado_tom"], "error")
