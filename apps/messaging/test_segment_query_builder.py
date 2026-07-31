from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.budget.models import Budget, BudgetStatus
from apps.customer.models import Customer
from apps.messaging.domain.value_objects import FilterCriteria, SegmentRule
from apps.messaging.infrastructure.services.segment_query_builder import eligible_customers_queryset, resolve_segment
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Seg {suffix}",
        cnpj=f"51.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_customer(
    *,
    workshop: Workshop,
    suffix: int,
    is_active: bool = True,
    birth_date: date | None = None,
    criado_em: date | None = None,
    accepts_messages: bool = True,
) -> Customer:
    customer = Customer.objects.create(
        workshop=workshop,
        name=f"Cliente {suffix}",
        cpf_or_cnpj=f"1234567890{suffix:02d}",
        email=f"cliente{suffix}@example.com",
        phone="+5511999999999",
        is_active=is_active,
        birth_date=birth_date,
        accepts_messages=accepts_messages,
    )
    if criado_em:
        Customer.objects.filter(pk=customer.pk).update(criado_em=timezone.make_aware(timezone.datetime.combine(criado_em, timezone.datetime.min.time())))
    return Customer.objects.get(pk=customer.pk)


class BirthdayRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        today = timezone.localdate()
        self.birthday_customer = create_customer(workshop=self.workshop, suffix=1, birth_date=date(1990, today.month, today.day))
        self.other_customer = create_customer(workshop=self.workshop, suffix=2, birth_date=date(1990, 1, 1))

    def test_birthday_is_today_matches_customers(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="birthday", operator="is_today"),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.birthday_customer, qs)
        self.assertNotIn(self.other_customer, qs)

    def test_birthday_is_this_month_matches_customers(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="birthday", operator="is_this_month"),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.birthday_customer, qs)


class LastVisitRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=2)
        self.recent_customer = create_customer(workshop=self.workshop, suffix=1)
        self.no_visit_customer = create_customer(workshop=self.workshop, suffix=2)

        budget_recent = Budget.objects.create(workshop=self.workshop, customer=self.recent_customer, status=BudgetStatus.APPROVED, entry_date=date.today())

        from apps.workorder.models import WorkOrder

        WorkOrder.objects.create(workshop=self.workshop, budget=budget_recent, status="draft")

    def test_last_visit_days_ago_gte_includes_customers_without_visits(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="last_visit", operator="days_ago_gte", value=1),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.no_visit_customer, qs)
        self.assertNotIn(self.recent_customer, qs)

    def test_last_visit_days_ago_lte_finds_recent(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="last_visit", operator="days_ago_lte", value=30),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.recent_customer, qs)


class BudgetStatusRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=3)
        self.approved_customer = create_customer(workshop=self.workshop, suffix=1)
        self.draft_customer = create_customer(workshop=self.workshop, suffix=2)
        self.no_budget_customer = create_customer(workshop=self.workshop, suffix=3)

        Budget.objects.create(workshop=self.workshop, customer=self.approved_customer, status=BudgetStatus.APPROVED, entry_date=date.today())
        Budget.objects.create(workshop=self.workshop, customer=self.draft_customer, status=BudgetStatus.DRAFT, entry_date=date.today())

    def test_budget_status_in_finds_matching(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="budget_status", operator="in", value=["approved"]),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.approved_customer, qs)
        self.assertNotIn(self.draft_customer, qs)
        self.assertNotIn(self.no_budget_customer, qs)


class WorkOrderStatusRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=4)
        self.draft_customer = create_customer(workshop=self.workshop, suffix=1)
        self.no_wo_customer = create_customer(workshop=self.workshop, suffix=2)

        from apps.workorder.models import WorkOrder

        budget_draft = Budget.objects.create(workshop=self.workshop, customer=self.draft_customer, status=BudgetStatus.APPROVED, entry_date=date.today())

        WorkOrder.objects.create(workshop=self.workshop, budget=budget_draft, status="draft")

    def test_workorder_status_in_finds_matching(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="workorder_status", operator="in", value=["draft"]),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.draft_customer, qs)
        self.assertNotIn(self.no_wo_customer, qs)


class CustomerFieldRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=5)
        self.jose = create_customer(workshop=self.workshop, suffix=1, birth_date=date(1990, 5, 10))
        self.jose_two = create_customer(workshop=self.workshop, suffix=2, birth_date=date(1990, 5, 10))
        self.maria = create_customer(workshop=self.workshop, suffix=3, birth_date=date(1990, 1, 1))
        Customer.objects.filter(pk=self.jose.pk).update(name="José da Silva")

    def test_customer_field_equals(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="customer_field", operator="equals", field="birth_date", value="1990-05-10"),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.jose, qs)
        self.assertIn(self.jose_two, qs)
        self.assertNotIn(self.maria, qs)

    def test_customer_field_icontains(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="customer_field", operator="icontains", field="name", value="josé"),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.jose, qs)
        self.assertNotIn(self.maria, qs)


class CreatedSinceRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=6)
        self.old_customer = create_customer(workshop=self.workshop, suffix=1, criado_em=date.today() - timedelta(days=60))
        self.new_customer = create_customer(workshop=self.workshop, suffix=2, criado_em=date.today() - timedelta(days=5))

    def test_created_since_days_ago_gte(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="created_since", operator="days_ago_gte", value=30),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.old_customer, qs)
        self.assertNotIn(self.new_customer, qs)

    def test_created_since_days_ago_lte(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="created_since", operator="days_ago_lte", value=10),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.new_customer, qs)
        self.assertNotIn(self.old_customer, qs)


class BudgetValueRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=7)
        self.high_value_customer = create_customer(workshop=self.workshop, suffix=1)
        self.low_value_customer = create_customer(workshop=self.workshop, suffix=2)
        self.no_budget_customer = create_customer(workshop=self.workshop, suffix=3)

        from apps.catalog.models import CatalogGroup, Product

        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Teste")
        high_product = Product.objects.create(workshop=self.workshop, group=group, name="Produto Caro", code="CARO", cost_price=100, selling_price=500)
        low_product = Product.objects.create(workshop=self.workshop, group=group, name="Produto Barato", code="BARATO", cost_price=10, selling_price=50)

        high_budget = Budget.objects.create(workshop=self.workshop, customer=self.high_value_customer, status=BudgetStatus.APPROVED, entry_date=date.today())
        low_budget = Budget.objects.create(workshop=self.workshop, customer=self.low_value_customer, status=BudgetStatus.APPROVED, entry_date=date.today())

        high_budget.items.create(workshop=self.workshop, product=high_product, quantity=1)
        low_budget.items.create(workshop=self.workshop, product=low_product, quantity=1)

    def test_budget_value_gte(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="budget_value", operator="gte", value=100),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.high_value_customer, qs)
        self.assertNotIn(self.low_value_customer, qs)
        self.assertNotIn(self.no_budget_customer, qs)

    def test_budget_value_lte(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="budget_value", operator="lte", value=100),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.low_value_customer, qs)
        self.assertNotIn(self.high_value_customer, qs)


class CombinedRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=8)
        self.today = timezone.localdate()
        self.match_all_customer = create_customer(workshop=self.workshop, suffix=1, birth_date=date(1990, self.today.month, self.today.day))
        self.match_one_customer = create_customer(workshop=self.workshop, suffix=2, birth_date=date(1990, self.today.month, self.today.day))
        self.no_match_customer = create_customer(workshop=self.workshop, suffix=3)

        Budget.objects.create(workshop=self.workshop, customer=self.match_all_customer, status=BudgetStatus.APPROVED, entry_date=date.today())
        Budget.objects.create(workshop=self.workshop, customer=self.match_one_customer, status=BudgetStatus.DRAFT, entry_date=date.today())

    def test_all_logical_operator_requires_all_rules(self) -> None:
        criteria = FilterCriteria(
            logical_operator="all",
            rules=(
                SegmentRule(rule_type="birthday", operator="is_today"),
                SegmentRule(rule_type="budget_status", operator="in", value=["approved"]),
            ),
        )
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.match_all_customer, qs)
        self.assertNotIn(self.match_one_customer, qs)
        self.assertNotIn(self.no_match_customer, qs)

    def test_any_logical_operator_matches_any_rule(self) -> None:
        criteria = FilterCriteria(
            logical_operator="any",
            rules=(
                SegmentRule(rule_type="birthday", operator="is_today"),
                SegmentRule(rule_type="budget_status", operator="in", value=["approved"]),
            ),
        )
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertIn(self.match_all_customer, qs)
        self.assertIn(self.match_one_customer, qs)
        self.assertNotIn(self.no_match_customer, qs)

    def test_empty_filter_criteria_returns_all_eligible(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=())
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        eligible_count = eligible_customers_queryset(workshop=self.workshop).count()
        self.assertEqual(qs.count(), eligible_count)

    def test_unknown_rule_type_is_ignored(self) -> None:
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="nonexistent", operator="in", value=["x"]),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertEqual(qs.count(), eligible_customers_queryset(workshop=self.workshop).count())

    def test_inactive_customers_are_excluded(self) -> None:
        inactive = create_customer(workshop=self.workshop, suffix=9, is_active=False, birth_date=date(1990, self.today.month, self.today.day))
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="birthday", operator="is_today"),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertNotIn(inactive, qs)

    def test_customers_without_phone_are_excluded(self) -> None:
        today = timezone.localdate()
        without_phone = create_customer(
            workshop=self.workshop,
            suffix=10,
            birth_date=date(1990, today.month, today.day),
        )
        Customer.objects.filter(pk=without_phone.pk).update(phone="")
        without_phone.refresh_from_db()

        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="birthday", operator="is_today"),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertNotIn(without_phone, qs)

    def test_workshop_scoping_excludes_other_workshop(self) -> None:
        other_workshop = create_workshop(suffix=99)
        other_customer = create_customer(workshop=other_workshop, suffix=1, birth_date=date(1990, self.today.month, self.today.day))
        criteria = FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="birthday", operator="is_today"),))
        qs = resolve_segment(workshop=self.workshop, filter_criteria=criteria)
        self.assertNotIn(other_customer, qs)
