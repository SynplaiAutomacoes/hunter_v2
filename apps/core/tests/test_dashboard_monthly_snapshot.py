from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Account
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.core.infrastructure.models.dashboard_monthly_snapshot import DashboardMonthlySnapshot
from apps.core.infrastructure.services.dashboard_snapshot_service import (
    SAO_PAULO_TZ,
    backfill_closed_snapshots,
    create_snapshot_if_missing,
    get_dashboard_metrics,
    is_month_closed,
    month_close_at,
)
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop


class MonthCloseCutoffTests(SimpleTestCase):
    def test_month_close_at_is_last_day_2359_sao_paulo(self) -> None:
        closed_at = month_close_at(2026, 8)
        self.assertEqual(closed_at.tzinfo, SAO_PAULO_TZ)
        self.assertEqual(closed_at.year, 2026)
        self.assertEqual(closed_at.month, 8)
        self.assertEqual(closed_at.day, 31)
        self.assertEqual(closed_at.hour, 23)
        self.assertEqual(closed_at.minute, 59)
        self.assertEqual(closed_at.second, 59)

    def test_august_still_open_before_cutoff(self) -> None:
        now = datetime(2026, 8, 31, 23, 58, 0, tzinfo=SAO_PAULO_TZ)
        self.assertFalse(is_month_closed(2026, 8, now=now))

    def test_august_closed_after_cutoff(self) -> None:
        now = datetime(2026, 9, 1, 0, 0, 0, tzinfo=SAO_PAULO_TZ)
        self.assertTrue(is_month_closed(2026, 8, now=now))

    def test_july_closed_during_august(self) -> None:
        now = datetime(2026, 8, 6, 10, 0, 0, tzinfo=SAO_PAULO_TZ)
        self.assertTrue(is_month_closed(2026, 7, now=now))
        self.assertFalse(is_month_closed(2026, 8, now=now))


class DashboardMonthlySnapshotServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        account = Account.objects.create(name="Conta snapshot")
        cls.workshop = Workshop.objects.create(account=account, name="Oficina snapshot", cnpj="20000000000001", uf="SP")
        WorkshopCost.objects.create(
            workshop=cls.workshop,
            month=7,
            year=2026,
            mechanic_quantity=1,
            work_days_per_month=23,
            gross_revenue_target=Decimal("100000.00"),
        )

    def test_create_snapshot_if_missing_is_idempotent(self) -> None:
        live = DashboardMetrics(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
            total_sold_to_date=Decimal("50.00"),
        )
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=live,
        ):
            first = create_snapshot_if_missing(self.workshop, 7, 2026)
        first.total_sold_to_date = Decimal("111.11")
        first.save(update_fields=["total_sold_to_date"])

        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=live,
        ) as compute_mock:
            second = create_snapshot_if_missing(self.workshop, 7, 2026)

        compute_mock.assert_not_called()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.total_sold_to_date, Decimal("111.11"))
        self.assertEqual(DashboardMonthlySnapshot.objects.filter(workshop=self.workshop, year=2026, month=7).count(), 1)

    @override_settings(DASHBOARD_USE_MONTHLY_SNAPSHOTS=True)
    def test_closed_month_uses_snapshot_even_if_live_compute_changes(self) -> None:
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=SAO_PAULO_TZ)
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=DashboardMetrics(
                workshop_id=self.workshop.pk,
                selected_month=7,
                selected_year=2026,
                total_sold_to_date=Decimal("222673.56"),
                approval_rate=Decimal("61.250000"),
            ),
        ):
            snapshot = create_snapshot_if_missing(self.workshop, 7, 2026, now=now)

        live = DashboardMetrics(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
            total_sold_to_date=Decimal("999999.00"),
            approval_rate=Decimal("1.00"),
        )
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=live,
        ) as compute_mock:
            metrics = get_dashboard_metrics(self.workshop, selected_month=7, selected_year=2026, now=now)

        compute_mock.assert_not_called()
        self.assertEqual(snapshot.pk, DashboardMonthlySnapshot.objects.get(workshop=self.workshop, year=2026, month=7).pk)
        self.assertEqual(metrics.total_sold_to_date, Decimal("222673.56"))
        self.assertEqual(metrics.approval_rate, Decimal("61.250000"))

    @override_settings(DASHBOARD_USE_MONTHLY_SNAPSHOTS=False)
    def test_closed_month_stays_live_when_snapshots_disabled(self) -> None:
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=SAO_PAULO_TZ)
        live = DashboardMetrics(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
            total_sold_to_date=Decimal("555.00"),
        )
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=live,
        ) as compute_mock:
            metrics = get_dashboard_metrics(self.workshop, selected_month=7, selected_year=2026, now=now)

        compute_mock.assert_called_once()
        self.assertEqual(metrics.total_sold_to_date, Decimal("555.00"))
        self.assertFalse(
            DashboardMonthlySnapshot.objects.filter(workshop=self.workshop, year=2026, month=7).exists()
        )

    def test_open_month_stays_live(self) -> None:
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=SAO_PAULO_TZ)
        live = DashboardMetrics(
            workshop_id=self.workshop.pk,
            selected_month=8,
            selected_year=2026,
            total_sold_to_date=Decimal("1234.56"),
        )
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=live,
        ) as compute_mock:
            metrics = get_dashboard_metrics(self.workshop, selected_month=8, selected_year=2026, now=now)

        compute_mock.assert_called_once()
        self.assertEqual(metrics.total_sold_to_date, Decimal("1234.56"))
        self.assertFalse(
            DashboardMonthlySnapshot.objects.filter(workshop=self.workshop, year=2026, month=8).exists()
        )

    def test_backfill_creates_snapshot_for_july_cost_month(self) -> None:
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=DashboardMetrics(
                workshop_id=self.workshop.pk,
                selected_month=7,
                selected_year=2026,
                total_sold_to_date=Decimal("10.00"),
            ),
        ):
            created = backfill_closed_snapshots(now=now)

        self.assertGreaterEqual(created, 1)
        self.assertTrue(
            DashboardMonthlySnapshot.objects.filter(workshop=self.workshop, year=2026, month=7).exists()
        )
        snap = DashboardMonthlySnapshot.objects.get(workshop=self.workshop, year=2026, month=7)
        self.assertEqual(timezone.localtime(snap.closed_at, SAO_PAULO_TZ).day, 31)
        self.assertEqual(timezone.localtime(snap.closed_at, SAO_PAULO_TZ).month, 7)
