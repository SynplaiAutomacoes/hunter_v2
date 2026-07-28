from __future__ import annotations

from typing import Any

from django.db import transaction
from django.test import TestCase

from apps.finance.models.financial_group import FinancialGroup
from apps.finance.services.financial_group import cascade_delete_with_renumber, collect_descendant_ids
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Teste {suffix}",
        cnpj=f"41.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_group_tree(workshop: Workshop, structure: dict[str, Any], *, parent: FinancialGroup | None = None) -> dict[str, FinancialGroup]:
    refs: dict[str, FinancialGroup] = {}
    for name, children in structure.items():
        group = FinancialGroup.objects.create(
            workshop=workshop,
            parent=parent,
            name=name,
        )
        refs[name] = group
        if children:
            child_refs = create_group_tree(workshop, children, parent=group)
            refs.update(child_refs)
    return refs


def assert_group_fields(group: FinancialGroup, *, sequence: int, code: str, sort_key: str, level: int) -> None:
    group.refresh_from_db()
    assert group.sequence == sequence, f"Expected sequence={sequence}, got {group.sequence}"
    assert group.code == code, f"Expected code={code!r}, got {group.code!r}"
    assert group.sort_key == sort_key, f"Expected sort_key={sort_key!r}, got {group.sort_key!r}"
    assert group.level == level, f"Expected level={level}, got {group.level}"


class CascadeDeleteRenumberTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop()

    def test_delete_leaf_group(self) -> None:
        refs = create_group_tree(self.workshop, {"A": {}, "B": {}, "C": {}})
        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["B"].pk],
        )
        self.assertEqual(count, 1)
        self.assertFalse(FinancialGroup.objects.filter(pk=refs["B"].pk).exists())
        assert_group_fields(refs["A"], sequence=1, code="1", sort_key="000001", level=1)
        assert_group_fields(refs["C"], sequence=2, code="2", sort_key="000002", level=1)

    def test_delete_parent_with_children(self) -> None:
        refs = create_group_tree(self.workshop, {"A": {}, "B": {"B1": {}, "B2": {}}, "C": {}})
        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["B"].pk],
        )
        self.assertEqual(count, 3)
        self.assertFalse(FinancialGroup.objects.filter(pk__in=[refs["B"].pk, refs["B1"].pk, refs["B2"].pk]).exists())
        assert_group_fields(refs["A"], sequence=1, code="1", sort_key="000001", level=1)
        assert_group_fields(refs["C"], sequence=2, code="2", sort_key="000002", level=1)

    def test_delete_middle_sibling_renumbers_remaining(self) -> None:
        refs = create_group_tree(self.workshop, {"A": {}, "B": {"B1": {}}, "C": {"C1": {}}})
        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["B"].pk],
        )
        self.assertEqual(count, 2)
        assert_group_fields(refs["A"], sequence=1, code="1", sort_key="000001", level=1)
        assert_group_fields(refs["C"], sequence=2, code="2", sort_key="000002", level=1)
        refs["C1"].refresh_from_db()
        self.assertEqual(refs["C1"].code, "2.1")
        self.assertEqual(refs["C1"].sort_key, "000002.000001")

    def test_deep_hierarchy_renumber_propagation(self) -> None:
        refs = create_group_tree(
            self.workshop,
            {
                "G1": {
                    "G1A": {
                        "G1A1": {},
                    },
                },
                "G2": {
                    "G2A": {
                        "G2A1": {},
                    },
                },
                "G3": {
                    "G3A": {},
                },
            },
        )
        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["G1"].pk],
        )
        self.assertEqual(count, 3)
        assert_group_fields(refs["G2"], sequence=1, code="1", sort_key="000001", level=1)
        assert_group_fields(refs["G3"], sequence=2, code="2", sort_key="000002", level=1)
        refs["G2A"].refresh_from_db()
        self.assertEqual(refs["G2A"].code, "1.1")
        self.assertEqual(refs["G2A"].sort_key, "000001.000001")
        refs["G2A1"].refresh_from_db()
        self.assertEqual(refs["G2A1"].code, "1.1.1")
        self.assertEqual(refs["G2A1"].sort_key, "000001.000001.000001")
        refs["G3A"].refresh_from_db()
        self.assertEqual(refs["G3A"].code, "2.1")
        self.assertEqual(refs["G3A"].sort_key, "000002.000001")

    def test_bulk_delete_multiple_roots(self) -> None:
        refs = create_group_tree(self.workshop, {"A": {"A1": {}}, "B": {"B1": {}}, "C": {"C1": {}}})
        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["A"].pk, refs["C"].pk],
        )
        self.assertEqual(count, 4)
        self.assertFalse(FinancialGroup.objects.filter(pk__in=[refs["A"].pk, refs["A1"].pk, refs["C"].pk, refs["C1"].pk]).exists())
        assert_group_fields(refs["B"], sequence=1, code="1", sort_key="000001", level=1)
        refs["B1"].refresh_from_db()
        self.assertEqual(refs["B1"].code, "1.1")

    def test_bulk_delete_mix_parents_and_leafs(self) -> None:
        refs = create_group_tree(self.workshop, {"A": {"A1": {}}, "B": {}, "C": {"C1": {}, "C2": {}}, "D": {}})
        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["A"].pk, refs["B"].pk],
        )
        self.assertEqual(count, 3)
        self.assertFalse(FinancialGroup.objects.filter(pk__in=[refs["A"].pk, refs["A1"].pk, refs["B"].pk]).exists())
        assert_group_fields(refs["C"], sequence=1, code="1", sort_key="000001", level=1)
        assert_group_fields(refs["D"], sequence=2, code="2", sort_key="000002", level=1)
        refs["C1"].refresh_from_db()
        self.assertEqual(refs["C1"].code, "1.1")

    def test_atomic_rollback_on_error(self) -> None:
        refs = create_group_tree(self.workshop, {"A": {"A1": {}}, "B": {}})
        original_count = FinancialGroup.objects.count()

        class FakeException(Exception):
            pass

        with self.assertRaises(FakeException):
            with transaction.atomic():
                cascade_delete_with_renumber(
                    workshop_id=self.workshop.pk,
                    group_ids=[refs["B"].pk],
                )
                raise FakeException("Forced rollback")

        self.assertEqual(FinancialGroup.objects.count(), original_count)

    def test_unique_constraints_after_renumber(self) -> None:
        refs = create_group_tree(
            self.workshop,
            {"X": {"X1": {}, "X2": {}}, "Y": {"Y1": {}}, "Z": {"Z1": {}}},
        )
        cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["X"].pk],
        )
        remaining = FinancialGroup.objects.filter(workshop=self.workshop)
        for group in remaining:
            duplicates = remaining.filter(code=group.code).exclude(pk=group.pk)
            self.assertEqual(duplicates.count(), 0, f"Duplicate code {group.code} for {group.pk}")
            duplicates_sk = remaining.filter(sort_key=group.sort_key).exclude(pk=group.pk)
            self.assertEqual(duplicates_sk.count(), 0, f"Duplicate sort_key {group.sort_key} for {group.pk}")

    def test_delete_with_no_siblings_does_not_renumber(self) -> None:
        refs = create_group_tree(self.workshop, {"A": {"A1": {}}})
        original_a = FinancialGroup.objects.get(pk=refs["A"].pk)
        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["A1"].pk],
        )
        self.assertEqual(count, 1)
        assert_group_fields(
            refs["A"],
            sequence=original_a.sequence,
            code=original_a.code,
            sort_key=original_a.sort_key,
            level=original_a.level,
        )

    def test_multiple_level_renumber_propagation(self) -> None:
        refs = create_group_tree(
            self.workshop,
            {
                "R1": {"R1A": {"R1A1": {}}},
                "R2": {"R2A": {"R2A1": {}}},
                "R3": {"R3A": {"R3A1": {}}},
            },
        )
        cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["R2"].pk],
        )
        assert_group_fields(refs["R3"], sequence=2, code="2", sort_key="000002", level=1)
        refs["R3A"].refresh_from_db()
        self.assertEqual(refs["R3A"].code, "2.1")
        self.assertEqual(refs["R3A"].sort_key, "000002.000001")
        refs["R3A1"].refresh_from_db()
        self.assertEqual(refs["R3A1"].code, "2.1.1")
        self.assertEqual(refs["R3A1"].sort_key, "000002.000001.000001")

    def test_cross_workshop_ids_are_ignored(self) -> None:
        other_workshop = create_workshop(suffix=2)
        refs = create_group_tree(self.workshop, {"A": {}, "B": {}})
        other_refs = create_group_tree(other_workshop, {"X": {}, "Y": {}})

        count = cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[refs["A"].pk, other_refs["X"].pk],
        )
        self.assertEqual(count, 1)
        self.assertFalse(FinancialGroup.objects.filter(pk=refs["A"].pk).exists())
        self.assertTrue(FinancialGroup.objects.filter(pk=other_refs["X"].pk).exists())

    def test_collect_descendant_ids_returns_empty_for_invalid_group(self) -> None:
        ids = collect_descendant_ids(99999)
        self.assertEqual(ids, [])
