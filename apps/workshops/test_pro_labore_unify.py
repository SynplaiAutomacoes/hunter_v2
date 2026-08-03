from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import (
    PRO_LABORE_MONTHLY_COST_NAME,
    TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
    create_default_monthly_costs,
    get_pro_labore_monthly_cost,
    unify_pro_labore_monthly_cost,
    unify_transport_allowance_monthly_cost,
)


class UnifyProLaboreMonthlyCostTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Pro Labore Unify",
            cnpj="12.345.678/0001-55",
            phone="+5511999999999",
            address="Rua Unify, 1",
        )

    def test_unify_renames_short_alias_to_canonical(self) -> None:
        alias = MonthlyCost.objects.create(
            workshop=self.workshop,
            name="Pró Labore",
            is_active=True,
            is_editable=True,
        )

        unified = unify_pro_labore_monthly_cost(workshop=self.workshop)

        self.assertEqual(unified.pk, alias.pk)
        self.assertEqual(unified.name, PRO_LABORE_MONTHLY_COST_NAME)
        self.assertFalse(unified.is_editable)
        self.assertEqual(MonthlyCost.objects.filter(workshop=self.workshop, name="Pró Labore").count(), 0)
        self.assertEqual(MonthlyCost.objects.filter(workshop=self.workshop, name=PRO_LABORE_MONTHLY_COST_NAME).count(), 1)

    def test_unify_merges_duplicate_alias_into_canonical(self) -> None:
        create_default_monthly_costs(workshop=self.workshop)
        canonical = MonthlyCost.objects.get(workshop=self.workshop, name=PRO_LABORE_MONTHLY_COST_NAME)
        alias = MonthlyCost.objects.create(
            workshop=self.workshop,
            name="Pró Labore",
            is_active=True,
            is_editable=True,
        )
        workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            year=2026,
            month=7,
            mechanic_quantity=1,
            work_days_per_month=22,
        )
        WorkshopCostItem.objects.create(
            workshop_cost=workshop_cost,
            monthly_cost=canonical,
            amount=Money(0, "BRL"),
        )
        WorkshopCostItem.objects.create(
            workshop_cost=workshop_cost,
            monthly_cost=alias,
            amount=Money(Decimal("5500.00"), "BRL"),
        )

        unified = unify_pro_labore_monthly_cost(workshop=self.workshop)

        self.assertEqual(unified.pk, canonical.pk)
        self.assertFalse(MonthlyCost.objects.filter(pk=alias.pk).exists())
        item = WorkshopCostItem.objects.get(workshop_cost=workshop_cost, monthly_cost=canonical)
        self.assertEqual(item.amount, Money("5500.00", "BRL"))
        self.assertEqual(WorkshopCostItem.objects.filter(workshop_cost=workshop_cost).count(), 1)

    def test_get_pro_labore_prefers_canonical_over_alias(self) -> None:
        create_default_monthly_costs(workshop=self.workshop)
        MonthlyCost.objects.create(workshop=self.workshop, name="Pró Labore", is_active=True, is_editable=True)
        found = get_pro_labore_monthly_cost(workshop=self.workshop)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.name, PRO_LABORE_MONTHLY_COST_NAME)


class UnifyTransportAllowanceMonthlyCostTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina VT Unify",
            cnpj="12.345.678/0001-66",
            phone="+5511999999999",
            address="Rua VT Unify, 1",
        )

    def test_unify_merges_valor_total_alias_into_canonical(self) -> None:
        create_default_monthly_costs(workshop=self.workshop)
        canonical = MonthlyCost.objects.get(workshop=self.workshop, name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)
        alias = MonthlyCost.objects.create(
            workshop=self.workshop,
            name="Valor Total do Vale Transporte",
            is_active=True,
            is_editable=True,
        )

        unified = unify_transport_allowance_monthly_cost(workshop=self.workshop)

        self.assertEqual(unified.pk, canonical.pk)
        self.assertEqual(unified.name, TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)
        self.assertFalse(MonthlyCost.objects.filter(pk=alias.pk).exists())
        self.assertEqual(
            MonthlyCost.objects.filter(workshop=self.workshop, name="Valor Total do Vale Transporte").count(),
            0,
        )
