from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetStatus, BudgetType
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Save Perf {suffix}",
        cnpj=f"51.111.222/0001-{suffix:02d}",
        phone="+5511888888888",
        address="Rua Save, 10",
    )


class BudgetSavePerformanceTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 1),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.DRAFT,
            current_step=2,
        )
        Budget.objects.filter(pk=self.budget.pk).update(stored_total_amount=Money(25, "BRL"))
        self.budget.refresh_from_db()

    def test_metadata_only_save_skips_pricing_and_stored_refresh(self) -> None:
        self.budget.current_step = 3
        with (
            patch.object(Budget, "sync_discount_fields") as sync_mock,
            patch.object(Budget, "refresh_stored_total_amount") as refresh_mock,
            patch("apps.budget.pricing.build_pricing_snapshot") as pricing_mock,
        ):
            self.budget.save(update_fields=["current_step"])

        sync_mock.assert_not_called()
        refresh_mock.assert_not_called()
        pricing_mock.assert_not_called()
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.current_step, 3)
        self.assertEqual(self.budget.stored_total_amount.amount, Decimal("25.00"))

    def test_status_and_step_metadata_save_skips_pricing(self) -> None:
        self.budget.status = BudgetStatus.WAITING_APPROVAL
        self.budget.current_step = 4
        with patch("apps.budget.pricing.build_pricing_snapshot") as pricing_mock:
            self.budget.save(update_fields=["status", "current_step"])

        pricing_mock.assert_not_called()
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.WAITING_APPROVAL)
        self.assertEqual(self.budget.current_step, 4)

    def test_skip_flag_coalesces_item_batch_refresh(self) -> None:
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Peças")
        products = [
            Product.objects.create(
                workshop=self.workshop,
                group=group,
                code=f"SP-{index}",
                name=f"Produto {index}",
                unit=Product.Unit.UND,
                selling_price=Money(10, "BRL"),
                cost_price=Money(5, "BRL"),
            )
            for index in range(3)
        ]

        refresh_calls = {"count": 0}
        original_refresh = Budget.refresh_stored_total_amount

        def counting_refresh(budget_self: Budget) -> None:
            refresh_calls["count"] += 1
            return original_refresh(budget_self)

        self.budget._skip_stored_total_refresh = True
        try:
            with patch.object(Budget, "refresh_stored_total_amount", autospec=True, side_effect=counting_refresh):
                for product in products:
                    BudgetItem.objects.create(
                        workshop=self.workshop,
                        budget=self.budget,
                        product=product,
                        quantity=1,
                    )
                self.assertEqual(refresh_calls["count"], 0)
        finally:
            self.budget._skip_stored_total_refresh = False

        with patch.object(Budget, "refresh_stored_total_amount", autospec=True, side_effect=counting_refresh):
            self.budget.invalidate_pricing_snapshot_cache()
            self.budget.refresh_stored_total_amount()

        self.assertEqual(refresh_calls["count"], 1)
