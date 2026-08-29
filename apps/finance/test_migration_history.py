"""Guards against reintroducing inconsistent finance migration history."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from django.db import models
from django.db.migrations.state import ProjectState
from django.test import SimpleTestCase

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _load_idempotent_module():
    """Load migration helpers without importing apps.finance.models."""
    module_name = "apps.finance.migrations._idempotent_testload"
    if module_name in sys.modules:
        return sys.modules[module_name]
    # Ensure package parents exist for relative imports inside the module if any.
    pkg_name = "apps.finance.migrations"
    if pkg_name not in sys.modules:
        pkg = importlib.util.module_from_spec(
            importlib.util.spec_from_file_location(
                pkg_name,
                MIGRATIONS_DIR / "__init__.py",
                submodule_search_locations=[str(MIGRATIONS_DIR)],
            )
        )
        sys.modules[pkg_name] = pkg
    spec = importlib.util.spec_from_file_location(
        module_name,
        MIGRATIONS_DIR / "_idempotent.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _finance_dependencies(migration_stem: str) -> list[str]:
    text = (MIGRATIONS_DIR / f"{migration_stem}.py").read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
    if not match:
        return []
    return re.findall(r"[(\"']finance[\"'],\s*[\"']([^\"']+)[\"']\)", match.group(1))


class FinanceMigrationHistoryTests(SimpleTestCase):
    def test_0051_does_not_depend_on_late_merge(self) -> None:
        """0051 was applied on staging/prod before 0050_merge existed in the graph."""
        deps = _finance_dependencies("0051_nfe_transport_support")
        self.assertIn("0050_nfe_return_support", deps)
        self.assertNotIn("0050_merge_20260810_1742", deps)

    def test_feat_nf_leaf_is_merged_at_tip(self) -> None:
        deps = _finance_dependencies("0059_merge_feat_nf_and_purchase_return")
        self.assertEqual(
            set(deps),
            {
                "0050_merge_20260810_1742",
                "0058_repair_purchase_return_item_columns",
            },
        )

    def test_ticket240_discount_parents_exist_for_homol_merge(self) -> None:
        self.assertTrue((MIGRATIONS_DIR / "0052_financial_movement_discount_fields.py").exists())
        self.assertTrue((MIGRATIONS_DIR / "0053_movement_group_discount_fields.py").exists())
        deps = _finance_dependencies("0062_merge_ticket240_discounts_and_homol")
        self.assertEqual(
            set(deps),
            {
                "0053_movement_group_discount_fields",
                "0061_merge_feat_nf_and_standalone_emission",
            },
        )
        parent_deps = _finance_dependencies("0053_movement_group_discount_fields")
        self.assertIn("0052_financial_movement_discount_fields", parent_deps)

    def test_fiscaldocument_options_leaf_is_merged_at_tip(self) -> None:
        deps = _finance_dependencies("0066_merge_fiscaldocument_options_and_partial_payment")
        self.assertEqual(
            set(deps),
            {
                "0063_alter_fiscaldocument_options_and_more",
                "0065_merge_financial_movement_partial_payment",
            },
        )


class IdempotentMigrationStateTests(SimpleTestCase):
    def test_duplicate_create_add_index_constraint_are_state_safe(self) -> None:
        idempotent = _load_idempotent_module()
        state = ProjectState()
        create = idempotent.CreateModelIfMissing(
            name="Widget",
            fields=[("id", models.BigAutoField(primary_key=True))],
            options={},
        )
        create.state_forwards("finance", state)
        create.state_forwards("finance", state)

        add_field = idempotent.AddFieldIfMissing(
            "widget",
            "name",
            models.CharField(max_length=10, default=""),
        )
        add_field.state_forwards("finance", state)
        add_field.state_forwards("finance", state)

        index = models.Index(fields=["name"], name="finance_widget_name_idx")
        add_index = idempotent.AddIndexIfMissing("widget", index)
        add_index.state_forwards("finance", state)
        add_index.state_forwards("finance", state)

        constraint = models.UniqueConstraint(fields=["name"], name="uniq_widget_name")
        add_constraint = idempotent.AddConstraintIfMissing("widget", constraint)
        add_constraint.state_forwards("finance", state)
        add_constraint.state_forwards("finance", state)

        model_state = state.models[("finance", "widget")]
        self.assertIn("name", model_state.fields)
        self.assertEqual(len(model_state.options.get("indexes", [])), 1)
        self.assertEqual(len(model_state.options.get("constraints", [])), 1)
