"""Guards against reintroducing inconsistent workorder migration history."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _workorder_dependencies(migration_stem: str) -> list[str]:
    text = (MIGRATIONS_DIR / f"{migration_stem}.py").read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
    if not match:
        return []
    return re.findall(r"[(\"']workorder[\"'],\s*[\"']([^\"']+)[\"']\)", match.group(1))


class WorkorderMigrationHistoryTests(SimpleTestCase):
    def test_warranty_origin_leaf_is_merged_at_tip(self) -> None:
        deps = _workorder_dependencies("0055_merge_warranty_origin_and_os_tip")
        self.assertEqual(
            set(deps),
            {
                "0050_add_warranty_origin",
                "0054_merge_excluded_composition_and_os_tip",
            },
        )
