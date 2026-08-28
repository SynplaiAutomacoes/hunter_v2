from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.core.templatetags.table_tags import _resolve_attr


class ResolveAttrNestedRelationTests(SimpleTestCase):
    def test_missing_nested_relation_returns_empty_string(self) -> None:
        budget = SimpleNamespace(reference_budget=None)

        self.assertEqual(_resolve_attr(budget, "reference_budget.number"), "")

    def test_nested_relation_value_is_returned(self) -> None:
        budget = SimpleNamespace(reference_budget=SimpleNamespace(number=42))

        self.assertEqual(_resolve_attr(budget, "reference_budget.number"), 42)

    def test_missing_attribute_returns_empty_string(self) -> None:
        budget = SimpleNamespace()

        self.assertEqual(_resolve_attr(budget, "reference_budget.number"), "")
