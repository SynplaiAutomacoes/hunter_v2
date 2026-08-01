from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.budget.models import Budget
from apps.customer.domain.services.oil_change_forecast import (
    MileageReadingPoint,
    compute_daily_km_average,
    compute_oil_change_forecast,
)
from apps.customer.models import Customer, MileageReadingSource, Vehicle, VehicleMileageReading, VehicleOilChange
from apps.customer.services.oil_change import (
    handle_workorder_delivery_oil_and_mileage,
    recalculate_and_sync_oil_alert,
    recalculate_oil_forecasts_for_review_plan,
    reschedule_after_review_plan_alert_sent,
)
from apps.messaging.models import MessageTemplate, ScheduledOutboundMessage
from apps.workorder.models import WorkOrder
from apps.workshops.models.review_plans import ReviewPlan
from apps.workshops.models.workshops import Workshop


class OilChangeForecastDomainTests(SimpleTestCase):
    def test_forecast_by_days_when_no_km_average(self) -> None:
        forecast = compute_oil_change_forecast(
            last_oil_change_date=date(2026, 6, 30),
            last_oil_change_km=10_000,
            validity_days=180,
            validity_km=5_000,
            current_km=10_500,
            today=date(2026, 7, 1),
            daily_km_average=None,
        )
        self.assertEqual(forecast.limit_by_days, date(2026, 12, 27))
        self.assertIsNone(forecast.limit_by_km)
        self.assertEqual(forecast.next_change_date, date(2026, 12, 27))
        self.assertEqual(forecast.reason, "VALIDADE_POR_DIAS")
        self.assertFalse(forecast.is_expired)

    def test_forecast_by_km_when_km_limit_comes_first(self) -> None:
        forecast = compute_oil_change_forecast(
            last_oil_change_date=date(2026, 6, 30),
            last_oil_change_km=10_000,
            validity_days=180,
            validity_km=5_000,
            current_km=14_000,
            today=date(2026, 7, 23),
            daily_km_average=Decimal("50"),
        )
        # remaining = 1000 km / 50 = 20 days -> 2026-08-12
        self.assertEqual(forecast.limit_by_km, date(2026, 8, 12))
        self.assertEqual(forecast.next_change_date, date(2026, 8, 12))
        self.assertEqual(forecast.reason, "VALIDADE_POR_QUILOMETRAGEM")

    def test_expired_by_date_or_km(self) -> None:
        by_date = compute_oil_change_forecast(
            last_oil_change_date=date(2026, 1, 1),
            last_oil_change_km=1_000,
            validity_days=30,
            validity_km=5_000,
            current_km=1_100,
            today=date(2026, 3, 1),
            daily_km_average=None,
        )
        self.assertTrue(by_date.is_expired)

        by_km = compute_oil_change_forecast(
            last_oil_change_date=date(2026, 6, 1),
            last_oil_change_km=1_000,
            validity_days=180,
            validity_km=1_000,
            current_km=2_500,
            today=date(2026, 6, 15),
            daily_km_average=Decimal("10"),
        )
        self.assertTrue(by_km.is_expired)

    def test_daily_average_ignores_invalid_readings(self) -> None:
        readings = [
            MileageReadingPoint(read_at=date(2026, 1, 1), odometer_km=10_000),
            MileageReadingPoint(read_at=date(2026, 1, 1), odometer_km=10_000),  # duplicate
            MileageReadingPoint(read_at=date(2026, 1, 10), odometer_km=9_000),  # lower km
            MileageReadingPoint(read_at=date(2026, 1, 5), odometer_km=10_500),  # earlier than previous kept
            MileageReadingPoint(read_at=date(2026, 1, 21), odometer_km=11_000),
            MileageReadingPoint(read_at=date(2026, 1, 22), odometer_km=50_000),  # implausible jump
        ]
        average = compute_daily_km_average(readings)
        # Valid segment: 10000@01-01 -> 11000@01-21 = 1000km / 20 days = 50
        self.assertEqual(average, Decimal("50"))


class OilChangeIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Oleo",
            cnpj="11.222.333/0001-99",
            phone="+5511999999999",
            address="Rua Oleo, 1",
        )
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Oleo",
            cpf_or_cnpj="39053344720",
            email="oleo@example.com",
            phone="+5511988887777",
            is_active=True,
            accepts_messages=True,
        )
        self.review_plan = ReviewPlan.objects.create(
            workshop=self.workshop,
            name="Sintetico 5W30",
            validity_days=180,
            validity_km=5_000,
            notification_lead_days=7,
        )
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Plano de revisao",
            message="Ola %%nome%%, revisao do %%modelo%% (%%placa%%) na %%nome_oficina%%.",
            template_type=MessageTemplate.TemplateType.REVIEW_PLAN,
            is_active=True,
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="ABC1D23",
            brand="Fiat",
            model="Argo",
            year_fabrication="2022",
            year_model="2023",
            color="Branco",
            km=10_000,
        )

    def test_workorder_delivery_creates_history_updates_vehicle_and_schedules_trigger(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            entry_date=date(2026, 7, 20),
            current_km=12_000,
        )
        workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            km_final=12_050,
            last_oil_change_date=date(2026, 6, 30),
            last_oil_change_km=12_000,
            review_plan=self.review_plan,
        )
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["delivered_at"])

        handle_workorder_delivery_oil_and_mileage(workorder=workorder)

        self.vehicle.refresh_from_db()
        self.assertEqual(VehicleOilChange.objects.filter(vehicle=self.vehicle).count(), 1)
        oil_change = VehicleOilChange.objects.get(workorder=workorder)
        self.assertEqual(oil_change.odometer_km, 12_000)
        self.assertEqual(oil_change.validity_days, 180)
        self.assertEqual(self.vehicle.last_oil_change_date, date(2026, 6, 30))
        self.assertEqual(self.vehicle.last_oil_change_km, 12_000)
        self.assertEqual(self.vehicle.review_plan_id, self.review_plan.pk)
        self.assertEqual(self.vehicle.km, 12_050)
        self.assertEqual(VehicleMileageReading.objects.filter(vehicle=self.vehicle).count(), 1)
        self.assertIsNotNone(self.vehicle.next_oil_change_date)

        scheduled = ScheduledOutboundMessage.objects.filter(
            vehicle=self.vehicle,
            source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
            status=ScheduledOutboundMessage.Status.PENDING,
        )
        self.assertEqual(scheduled.count(), 1)

        # Idempotent second call
        handle_workorder_delivery_oil_and_mileage(workorder=workorder)
        self.assertEqual(VehicleOilChange.objects.filter(vehicle=self.vehicle).count(), 1)
        self.assertEqual(VehicleMileageReading.objects.filter(vehicle=self.vehicle, source=MileageReadingSource.WORKORDER_DELIVERY).count(), 1)
        self.assertEqual(scheduled.count(), 1)

    def test_expired_oil_schedules_immediate_run_at(self) -> None:
        self.vehicle.last_oil_change_date = date(2025, 1, 1)
        self.vehicle.last_oil_change_km = 1_000
        self.vehicle.review_plan = self.review_plan
        self.vehicle.km = 20_000
        self.vehicle.save()

        now = timezone.now()
        recalculate_and_sync_oil_alert(self.vehicle)
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.next_oil_change_date is not None and self.vehicle.next_oil_change_date <= timezone.localdate())

        scheduled = ScheduledOutboundMessage.objects.get(
            vehicle=self.vehicle,
            source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
            status=ScheduledOutboundMessage.Status.PENDING,
        )
        self.assertLessEqual(scheduled.run_at, now + timedelta(seconds=5))

    def test_review_plan_config_change_recalculates_trigger(self) -> None:
        self.vehicle.last_oil_change_date = date(2026, 6, 30)
        self.vehicle.last_oil_change_km = 10_000
        self.vehicle.review_plan = self.review_plan
        self.vehicle.km = 10_500
        self.vehicle.save()
        recalculate_and_sync_oil_alert(self.vehicle)
        first = ScheduledOutboundMessage.objects.get(
            vehicle=self.vehicle,
            source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
            status=ScheduledOutboundMessage.Status.PENDING,
        )
        first_run_at = first.run_at

        self.review_plan.validity_days = 30
        self.review_plan.notification_lead_days = 3
        self.review_plan.save(update_fields=["validity_days", "notification_lead_days", "atualizado_em"])
        recalculate_oil_forecasts_for_review_plan(review_plan=self.review_plan)

        pending = ScheduledOutboundMessage.objects.filter(
            vehicle=self.vehicle,
            source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
            status=ScheduledOutboundMessage.Status.PENDING,
        )
        self.assertEqual(pending.count(), 1)
        self.assertNotEqual(pending.get().run_at, first_run_at)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.next_oil_change_date, date(2026, 6, 30) + timedelta(days=30))

    def test_repeat_notification_advances_next_date_and_reschedules(self) -> None:
        self.review_plan.repeat_notification = True
        self.review_plan.save(update_fields=["repeat_notification", "atualizado_em"])
        self.vehicle.last_oil_change_date = date(2026, 1, 1)
        self.vehicle.last_oil_change_km = 1_000
        self.vehicle.review_plan = self.review_plan
        self.vehicle.next_oil_change_date = date(2026, 7, 1)
        self.vehicle.km = 5_000
        self.vehicle.save()

        reschedule_after_review_plan_alert_sent(self.vehicle)
        self.vehicle.refresh_from_db()
        today = timezone.localdate()
        expected_base = max(date(2026, 7, 1), today)
        self.assertEqual(self.vehicle.next_oil_change_date, expected_base + timedelta(days=180))

        pending = ScheduledOutboundMessage.objects.filter(
            vehicle=self.vehicle,
            source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
            status=ScheduledOutboundMessage.Status.PENDING,
        )
        self.assertEqual(pending.count(), 1)

    def test_repeat_notification_off_does_not_reschedule(self) -> None:
        self.vehicle.last_oil_change_date = date(2026, 1, 1)
        self.vehicle.last_oil_change_km = 1_000
        self.vehicle.review_plan = self.review_plan
        self.vehicle.next_oil_change_date = date(2026, 7, 1)
        self.vehicle.save()

        result = reschedule_after_review_plan_alert_sent(self.vehicle)
        self.assertIsNone(result)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.next_oil_change_date, date(2026, 7, 1))
        self.assertFalse(
            ScheduledOutboundMessage.objects.filter(
                vehicle=self.vehicle,
                source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
                status=ScheduledOutboundMessage.Status.PENDING,
            ).exists()
        )
