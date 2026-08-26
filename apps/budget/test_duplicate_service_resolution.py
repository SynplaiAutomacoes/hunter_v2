from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetKitItemOverride, BudgetStatus, BudgetType
from apps.budget.pricing import build_pricing_snapshot, zero_money
from apps.budget.services.duplicate_service_resolution import (
    KitLoserAction,
    apply_duplicate_service_resolution,
    find_duplicate_service_conflicts,
)
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitService
from apps.catalog.models.services import Service
from apps.core.text_normalization import sentence_case
from apps.workshops.models.workshops import Workshop


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


def _create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina DupSvc {suffix}",
        cnpj=f"33.444.555/0001-{suffix:02d}",
        phone="+5511999999988",
        address=f"Rua DupSvc, {suffix}",
        uf="SP",
    )


class DuplicateServiceResolutionTests(TestCase):
    def setUp(self) -> None:
        self.workshop = _create_workshop(suffix=1)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo DupSvc")
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 26),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.DRAFT,
            current_step=4,
            slider=0,
        )
        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Troca de oleo",
            duration=timedelta(hours=1),
            selling_price=_money("100.00"),
            suggested_cost=_money("40.00"),
        )

    def _add_kit_with_service(
        self,
        *,
        kit_name: str,
        quantity: int = 1,
        selling: str = "80.00",
        duration: timedelta | None = None,
        service: Service | None = None,
    ) -> BudgetItem:
        service = service or self.service
        kit = Kit.objects.create(workshop=self.workshop, name=kit_name)
        KitService.objects.create(
            kit=kit,
            service=service,
            quantity=1,
            duration=duration or timedelta(hours=1),
            cost_price=_money("30.00"),
            selling_price=_money(selling),
        )
        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            kit=kit,
            quantity=1,
        )
        override = item.kit_overrides.get(service_id=service.pk)
        override.quantity = quantity
        override.service_selling_price = _money(selling)
        override.duration = duration or timedelta(hours=1)
        override.save(update_fields=["quantity", "service_selling_price", "duration"])
        item.refresh_kit_snapshot_totals()
        return item

    def _add_direct_service(self, *, selling: str = "120.00", duration: timedelta | None = None) -> BudgetItem:
        # BudgetItem.save overwrites selling/duration from the catalog Service on create.
        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=self.service,
            quantity=1,
            description=self.service.name,
        )
        item.service_selling_price = _money(selling)
        item.service_cost_price = _money("40.00")
        item.duration = duration or timedelta(hours=2)
        item.save(update_fields=["service_selling_price", "service_cost_price", "duration"])
        return item

    def test_detection_keeps_higher_selling_value_even_with_shorter_duration(self) -> None:
        kit_cheap_long = self._add_kit_with_service(kit_name="Kit Barato Longo", selling="80.00", duration=timedelta(hours=3))
        kit_expensive_short = self._add_kit_with_service(kit_name="Kit Caro Curto", selling="90.00", duration=timedelta(hours=1))
        kit_excluded = self._add_kit_with_service(kit_name="Kit Excluido", selling="70.00", duration=timedelta(hours=4))
        BudgetKitItemOverride.objects.filter(budget_item=kit_excluded, service=self.service).update(excluded_from_composition=True)
        kit_zero = self._add_kit_with_service(kit_name="Kit Zero", selling="60.00", duration=timedelta(hours=5))
        BudgetKitItemOverride.objects.filter(budget_item=kit_zero, service=self.service).update(quantity=0)

        conflicts = find_duplicate_service_conflicts(self.budget)
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict.service_id, self.service.pk)
        self.assertEqual({source.budget_item_id for source in conflict.sources}, {kit_cheap_long.pk, kit_expensive_short.pk})
        self.assertEqual(conflict.recommended_source_key, f"kit-{kit_expensive_short.pk}")
        self.assertEqual(conflict.kept_source.budget_item_id, kit_expensive_short.pk)
        self.assertEqual([loser.budget_item_id for loser in conflict.kit_losers], [kit_cheap_long.pk])
        self.assertEqual(conflict.removal_kit_names, [sentence_case("Kit Barato Longo")])
        self.assertTrue(conflict.requires_kit_action)

    def test_detection_ignores_local_service(self) -> None:
        kit_item = self._add_kit_with_service(kit_name="Kit Local", selling="80.00")
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            local_item_type="service",
            description="Servico local",
            quantity=1,
            service_selling_price=_money("50.00"),
            duration=timedelta(hours=1),
        )
        conflicts = find_duplicate_service_conflicts(self.budget)
        self.assertEqual(conflicts, [])

        direct = self._add_direct_service()
        conflicts = find_duplicate_service_conflicts(self.budget)
        self.assertEqual(len(conflicts), 1)
        source_ids = {source.budget_item_id for source in conflicts[0].sources}
        self.assertEqual(source_ids, {kit_item.pk, direct.pk})

    def test_kit_vs_kit_debit_removes_price_from_losing_kit(self) -> None:
        kit_a = self._add_kit_with_service(kit_name="Kit A", selling="80.00", duration=timedelta(hours=1))
        kit_b = self._add_kit_with_service(kit_name="Kit B", selling="90.00", duration=timedelta(hours=2))
        kit_a_before = kit_a.service_selling_price

        apply_duplicate_service_resolution(
            budget=self.budget,
            service_id=self.service.pk,
            keep_source_key=f"kit-{kit_b.pk}",
            kit_action=KitLoserAction.DEBIT.value,
        )

        kit_a.refresh_from_db()
        override = BudgetKitItemOverride.objects.get(budget_item=kit_a, service=self.service)
        self.assertEqual(override.quantity, 0)
        self.assertFalse(override.excluded_from_composition)
        self.assertEqual(kit_a.service_selling_price, _money("0.00"))
        self.assertNotEqual(kit_a.service_selling_price, kit_a_before)
        self.assertEqual(find_duplicate_service_conflicts(self.budget), [])

    def test_kit_vs_kit_keep_price_retains_kit_total_and_excludes_composition(self) -> None:
        kit_a = self._add_kit_with_service(kit_name="Kit A", selling="80.00", duration=timedelta(hours=1))
        kit_b = self._add_kit_with_service(kit_name="Kit B", selling="90.00", duration=timedelta(hours=2))
        kit_a_before = kit_a.service_selling_price
        duration_before = kit_a.duration

        apply_duplicate_service_resolution(
            budget=self.budget,
            service_id=self.service.pk,
            keep_source_key=f"kit-{kit_b.pk}",
            kit_action=KitLoserAction.KEEP_PRICE.value,
        )

        kit_a.refresh_from_db()
        override = BudgetKitItemOverride.objects.get(budget_item=kit_a, service=self.service)
        self.assertEqual(override.quantity, 1)
        self.assertTrue(override.excluded_from_composition)
        self.assertEqual(kit_a.service_selling_price, kit_a_before)
        self.assertEqual(kit_a.duration, timedelta(0))
        self.assertNotEqual(kit_a.duration, duration_before)
        self.assertEqual(find_duplicate_service_conflicts(self.budget), [])

        snapshot = build_pricing_snapshot(
            items=list(self.budget.items.prefetch_related("kit_overrides").all()),
            slider=0,
            discount_value=zero_money(),
            discount_percentage=Decimal("0"),
        )
        line = snapshot.service_lines[0]
        self.assertEqual(line.raw_total, _money("90.00"))
        self.assertFalse(line.has_direct_source)
        self.assertTrue(line.has_kit_source)

    def test_avulso_vs_kit_keep_avulso_debits_kit(self) -> None:
        kit_item = self._add_kit_with_service(kit_name="Kit X", selling="80.00", duration=timedelta(hours=1))
        direct = self._add_direct_service(selling="120.00", duration=timedelta(hours=2))

        apply_duplicate_service_resolution(
            budget=self.budget,
            service_id=self.service.pk,
            keep_source_key=f"direct-{direct.pk}",
            kit_action=KitLoserAction.DEBIT.value,
        )

        self.assertTrue(BudgetItem.objects.filter(pk=direct.pk).exists())
        kit_item.refresh_from_db()
        override = BudgetKitItemOverride.objects.get(budget_item=kit_item, service=self.service)
        self.assertEqual(override.quantity, 0)
        self.assertEqual(kit_item.service_selling_price, _money("0.00"))
        self.assertEqual(find_duplicate_service_conflicts(self.budget), [])

    def test_avulso_vs_kit_keep_avulso_without_debit(self) -> None:
        kit_item = self._add_kit_with_service(kit_name="Kit Y", selling="80.00", duration=timedelta(hours=1))
        direct = self._add_direct_service(selling="120.00", duration=timedelta(hours=2))
        kit_price_before = kit_item.service_selling_price

        apply_duplicate_service_resolution(
            budget=self.budget,
            service_id=self.service.pk,
            keep_source_key=f"direct-{direct.pk}",
            kit_action=KitLoserAction.KEEP_PRICE.value,
        )

        kit_item.refresh_from_db()
        override = BudgetKitItemOverride.objects.get(budget_item=kit_item, service=self.service)
        self.assertTrue(override.excluded_from_composition)
        self.assertEqual(kit_item.service_selling_price, kit_price_before)
        self.assertEqual(kit_item.duration, timedelta(0))

    def test_avulso_vs_kit_keep_kit_removes_avulso(self) -> None:
        kit_item = self._add_kit_with_service(kit_name="Kit Z", selling="80.00", duration=timedelta(hours=3))
        direct = self._add_direct_service(selling="50.00", duration=timedelta(hours=1))

        apply_duplicate_service_resolution(
            budget=self.budget,
            service_id=self.service.pk,
            keep_source_key=f"kit-{kit_item.pk}",
        )

        self.assertFalse(BudgetItem.objects.filter(pk=direct.pk).exists())
        self.assertTrue(BudgetItem.objects.filter(pk=kit_item.pk).exists())
        self.assertEqual(find_duplicate_service_conflicts(self.budget), [])


class DuplicateServiceModalViewTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        from apps.accounts.models import Account
        from apps.collaborators.models import WorkshopMember
        from apps.iam.utils import get_or_create_director_role

        User = get_user_model()
        self.account = Account.objects.create(name="Conta Dup Modal")
        self.user = User.objects.create_user(username="dup-modal-user", password="secret", cpf="39053344705")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Dup Modal",
            cnpj="11.222.333/0001-81",
            phone="+5511999999977",
            address="Rua Dup Modal, 1",
            uf="SP",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 26),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.DRAFT,
            current_step=4,
            slider=0,
        )
        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Alinhamento",
            duration=timedelta(hours=1),
            selling_price=_money("100.00"),
            suggested_cost=_money("40.00"),
        )
        self.kit_a = Kit.objects.create(workshop=self.workshop, name="Kit Alinhamento A")
        KitService.objects.create(
            kit=self.kit_a,
            service=self.service,
            quantity=1,
            duration=timedelta(hours=1),
            selling_price=_money("80.00"),
        )
        self.kit_b = Kit.objects.create(workshop=self.workshop, name="Kit Alinhamento B")
        KitService.objects.create(
            kit=self.kit_b,
            service=self.service,
            quantity=1,
            duration=timedelta(hours=2),
            selling_price=_money("90.00"),
        )

    def test_batch_add_kits_with_duplicate_service_opens_simplified_modal(self) -> None:
        from django.urls import reverse

        BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, kit=self.kit_a, quantity=1)
        url = reverse("budget:add_items_batch", kwargs={"budget_id": self.budget.pk, "item_type": "kit"})
        response = self.client.post(
            url,
            {"selected_items": [str(self.kit_b.pk)]},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Serviço duplicado", content)
        self.assertIn("O serviço", content)
        self.assertIn("Alinhamento", content)
        self.assertIn("aparece em mais de um kit", content)
        self.assertIn("Escolha como proceder", content)
        self.assertIn(sentence_case("Kit Alinhamento A"), content)
        self.assertIn("Valor do kit", content)
        self.assertIn("data-kit-preview", content)
        self.assertIn("Remover e manter o valor original do kit", content)
        self.assertIn("Remover e debitar o valor do serviço do kit", content)
        self.assertIn('name="kit_action"', content)
        self.assertNotIn('name="keep_source_key" type="radio"', content)
        self.assertNotIn("Sugerido", content)
        self.assertIn(f'name="service_id" value="{self.service.pk}"', content)
