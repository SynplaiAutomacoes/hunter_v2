from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.core.management.commands.seed_performance_benchmark import (
    REFERENCE_DATE,
    _distributed_date,
    _month_reference,
    validate_benchmark_target,
)


class BenchmarkEnvironmentGuardTests(SimpleTestCase):
    def test_rejects_default_database(self) -> None:
        with self.assertRaises(CommandError):
            validate_benchmark_target(database_name="meu_crm", benchmark_environment=True)

    def test_rejects_benchmark_name_without_benchmark_settings(self) -> None:
        with self.assertRaises(CommandError):
            validate_benchmark_target(database_name="hunter_v2_perf_4a57a015", benchmark_environment=False)

    def test_accepts_isolated_benchmark_database(self) -> None:
        validate_benchmark_target(database_name="hunter_v2_perf_4a57a015", benchmark_environment=True)


class BenchmarkSeedDeterminismTests(SimpleTestCase):
    def test_distributed_dates_are_stable(self) -> None:
        self.assertEqual(_distributed_date(0), REFERENCE_DATE)
        self.assertEqual(_distributed_date(1), REFERENCE_DATE.replace(day=5))
        self.assertEqual(_distributed_date(730), REFERENCE_DATE)

    def test_month_references_are_stable_across_year_boundary(self) -> None:
        self.assertEqual(_month_reference(0), (2026, 7))
        self.assertEqual(_month_reference(7), (2025, 12))
