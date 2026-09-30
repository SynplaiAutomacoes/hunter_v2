from __future__ import annotations

from django.test import SimpleTestCase

from apps.billing.domain.plans import Plan, route_requires_full_plan
from apps.billing.access import feature_for_route, route_allowed_for_subscription


class PlanFeatureMapTests(SimpleTestCase):
    def test_full_only_namespaces_require_full_plan(self) -> None:
        for namespace in ("finance", "workorder", "stock", "scheduling", "messaging", "suppliers"):
            self.assertTrue(route_requires_full_plan(namespace=namespace, route=f"{namespace}:list"))
            self.assertEqual(feature_for_route(namespace=namespace, route=f"{namespace}:list"), Plan.FULL)

    def test_budget_catalog_terms_are_basic(self) -> None:
        for namespace, route in (
            ("budget", "budget:budget_list"),
            ("catalog", "catalog:product_list"),
            ("terms", "terms:term_template_list"),
            ("customer", "customer:customer_list"),
            ("checklist", "checklist:checklist_list"),
            ("quote", "quote:investigative_question_list"),
        ):
            self.assertFalse(route_requires_full_plan(namespace=namespace, route=route))
            self.assertEqual(feature_for_route(namespace=namespace, route=route), Plan.BASIC)

    def test_dashboard_requires_full_plan(self) -> None:
        self.assertTrue(route_requires_full_plan(namespace="core", route="core:dashboard"))

    def test_route_allowed_for_subscription(self) -> None:
        self.assertTrue(route_allowed_for_subscription(namespace="budget", route="budget:budget_list", plan=Plan.BASIC, is_active=True))
        self.assertFalse(route_allowed_for_subscription(namespace="finance", route="finance:reports_home", plan=Plan.BASIC, is_active=True))
        self.assertTrue(route_allowed_for_subscription(namespace="finance", route="finance:reports_home", plan=Plan.FULL, is_active=True))
        self.assertFalse(route_allowed_for_subscription(namespace="budget", route="budget:budget_list", plan=Plan.FULL, is_active=False))
