from __future__ import annotations

import gc
import json
import math
import platform
import re
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import django
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.budget.models import Budget, BudgetHistory, BudgetItem
from apps.catalog.models import Product
from apps.core.management.commands.seed_performance_benchmark import validate_benchmark_target
from apps.customer.models import Customer
from apps.finance.models import FinancialMovement, NfeRequest, NfseRequest
from apps.stock.models import StockMovement, StockProduct
from apps.suppliers.models import Supplier
from apps.workorder.models import WorkOrder, WorkOrderHistory, WorkOrderItem, WorkOrderPaymentMethod
from apps.workshops.models.workshops import Workshop


DEFAULT_OUTPUT = Path("docs/performance-results/person-one-baseline.json")
SQL_WHITESPACE_RE = re.compile(r"\s+")
SQL_NUMERIC_LITERAL_RE = re.compile(r"(?<![\w])\d+(?:\.\d+)?(?![\w])")
SQL_STRING_LITERAL_RE = re.compile(r"'(?:''|[^'])*'")
TBODY_RE = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.IGNORECASE | re.DOTALL)
TR_RE = re.compile(r"<tr(?:\s|>)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    route_name: str
    path: str
    group: str
    params: dict[str, str]
    records_total: int | None = None
    notes: str = ""


@dataclass(slots=True)
class QueryRecord:
    sql: str
    params: Any
    duration_ms: float
    rowcount: int

    @property
    def normalized(self) -> str:
        return normalize_sql(self.sql)


@dataclass(slots=True)
class DependencyRecord:
    method: str
    url: str
    duration_ms: float
    result: str


def normalize_sql(sql: str) -> str:
    normalized = SQL_WHITESPACE_RE.sub(" ", str(sql or "")).strip()
    normalized = SQL_STRING_LITERAL_RE.sub("?", normalized)
    normalized = SQL_NUMERIC_LITERAL_RE.sub("?", normalized)
    return normalized


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(math.ceil(percentile_value * len(ordered)) - 1, 0)
    return ordered[index]


def median_int(values: list[int]) -> int:
    return int(statistics.median(values)) if values else 0


def rendered_desktop_rows(content: bytes) -> int | None:
    html = content.decode("utf-8", errors="ignore")
    match = TBODY_RE.search(html)
    if match is None:
        return None
    return len(TR_RE.findall(match.group(1)))


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return repr(value)


class Command(BaseCommand):
    help = "Coleta o baseline quantitativo da Pessoa 1 exclusivamente no banco protegido de benchmark."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--warmups", type=int, default=2)
        parser.add_argument("--runs", type=int, default=10)
        parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        parser.add_argument(
            "--scenario",
            action="append",
            dest="scenario_names",
            help="Limita a coleta a um ou mais cenários nomeados; útil para amostras de estabilidade.",
        )

    def handle(self, *args: object, **options: object) -> None:
        warmups = int(options["warmups"])
        measured_runs = int(options["runs"])
        output_path = Path(options["output"])
        if warmups < 1 or measured_runs < 5:
            raise CommandError("Use ao menos 1 warmup e 5 execuções medidas.")

        database_name = str(connection.settings_dict.get("NAME") or "")
        validate_benchmark_target(
            database_name=database_name,
            benchmark_environment=bool(getattr(settings, "BENCHMARK_ENVIRONMENT", False)),
        )
        if not database_name.startswith("hunter_v2_perf_"):
            raise CommandError(f"Baseline oficial exige banco isolado hunter_v2_perf_*; recebido {database_name!r}.")

        user = User.objects.get(username="benchmark.owner")
        workshop = Workshop.objects.order_by("pk").first()
        if workshop is None:
            raise CommandError("Dataset standard ausente: nenhuma oficina encontrada.")
        self._validate_dataset()

        client = Client(HTTP_HOST="localhost", raise_request_exception=False)
        client.force_login(user)
        session = client.session
        session["active_workshop_id"] = workshop.pk
        session.save()

        scenarios = self._build_scenarios(workshop=workshop)
        requested_scenarios = set(options.get("scenario_names") or [])
        if requested_scenarios:
            known_scenarios = {scenario.name for scenario in scenarios}
            unknown_scenarios = requested_scenarios - known_scenarios
            if unknown_scenarios:
                raise CommandError(f"Cenários desconhecidos: {sorted(unknown_scenarios)}")
            scenarios = [scenario for scenario in scenarios if scenario.name in requested_scenarios]
        route_results: list[dict[str, Any]] = []
        all_query_records: list[dict[str, Any]] = []
        all_dependency_records: list[dict[str, Any]] = []

        collection_started_at = timezone.now()
        self.stdout.write(
            f"Collecting {len(scenarios)} scenarios with {warmups} warmups + {measured_runs} runs "
            f"on {database_name}"
        )

        with override_settings(PERF_LOGGING_ENABLED=False, PERF_LOG_QUERIES=False):
            for position, scenario in enumerate(scenarios, start=1):
                self.stdout.write(f"[{position}/{len(scenarios)}] {scenario.name}")
                route_result, query_records, dependency_records = self._measure_scenario(
                    client=client,
                    scenario=scenario,
                    warmups=warmups,
                    measured_runs=measured_runs,
                )
                route_results.append(route_result)
                all_query_records.extend(query_records)
                all_dependency_records.extend(dependency_records)
                self.stdout.write(
                    f"  median={route_result['duration_ms']['median']:.2f}ms "
                    f"p95={route_result['duration_ms']['p95']:.2f}ms "
                    f"queries={route_result['queries']['median']} status={route_result['status_codes']}"
                )

        pattern_ranking = self._build_pattern_ranking(all_query_records)
        individual_ranking = [
            {key: value for key, value in record.items() if key not in {"sql", "params", "_raw_params"}}
            for record in sorted(all_query_records, key=lambda item: item["duration_ms"], reverse=True)[:10]
        ]
        explain_plans = self._explain_top_patterns(all_query_records=all_query_records, pattern_ranking=pattern_ranking[:10])
        n_plus_one = self._build_n_plus_one_candidates(route_results)
        for record in all_query_records:
            record.pop("_raw_params", None)

        result = {
            "metadata": {
                "phase": "Fase 1.2 - Pessoa 1",
                "collection_started_at": collection_started_at.isoformat(),
                "collection_finished_at": timezone.now().isoformat(),
                "warmups_per_scenario": warmups,
                "measured_runs_per_scenario": measured_runs,
                "execution_mode": "Django test Client in one process; warm application/cache state after warmups",
                "settings_module": settings.SETTINGS_MODULE,
                "database": database_name,
                "database_vendor": connection.vendor,
                "database_version": connection.pg_version,
                "python_version": platform.python_version(),
                "django_version": django.get_version(),
                "platform": platform.platform(),
                "git_sha": self._git_sha(),
                "functional_base_sha": "4a57a0157c5dd10f8ab65e051f35f46730d4abc9",
                "environment_checkpoint_sha": "64bd324f7183025e7bc55376d9a5f888f736daf7",
                "reference_date": "2026-07-12",
                "limitations": [
                    "Synthetic standard dataset; results describe this cardinality, not production.",
                    "Client runs in-process and does not include Gunicorn/network latency.",
                    "Caches remain warm after documented warmups; no cache clearing between measured runs.",
                    "External dependencies are observed only if invoked by measured GET routes.",
                    "Worker occupancy cannot be measured by a sequential in-process Client.",
                ],
            },
            "dataset": self._dataset_counts(),
            "routes": route_results,
            "rankings": {
                "slowest_routes_by_p95": self._route_ranking(route_results, sort_key="p95"),
                "routes_by_query_count": self._route_ranking(route_results, sort_key="queries"),
                "top_individual_queries": individual_ranking,
                "top_query_patterns": pattern_ranking[:20],
            },
            "explain_plans": explain_plans,
            "n_plus_one_candidates": n_plus_one,
            "dependencies": {
                "observed_calls": all_dependency_records,
                "count": len(all_dependency_records),
            },
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(json_safe(result), indent=2, ensure_ascii=False), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Baseline written to {output_path}"))

    @staticmethod
    def _git_sha() -> str:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    @staticmethod
    def _validate_dataset() -> None:
        expected = {
            Budget: 1_500,
            BudgetItem: 4_500,
            WorkOrder: 1_000,
            WorkOrderItem: 3_000,
            WorkOrderPaymentMethod: 1_500,
            FinancialMovement: 1_500,
            StockMovement: 2_000,
        }
        mismatches: dict[str, dict[str, int]] = {}
        for model, expected_count in expected.items():
            actual_count = model.objects.count()
            if actual_count != expected_count:
                mismatches[model._meta.label] = {"expected": expected_count, "actual": actual_count}
        if mismatches:
            raise CommandError(f"Dataset standard foi alterado: {mismatches}")

    @staticmethod
    def _dataset_counts() -> dict[str, int]:
        models = [
            Workshop,
            Customer,
            Product,
            Supplier,
            Budget,
            BudgetItem,
            BudgetHistory,
            WorkOrder,
            WorkOrderItem,
            WorkOrderPaymentMethod,
            WorkOrderHistory,
            NfeRequest,
            NfseRequest,
            FinancialMovement,
            StockProduct,
            StockMovement,
        ]
        return {model._meta.label: model.objects.count() for model in models}

    @staticmethod
    def _build_scenarios(*, workshop: Workshop) -> list[Scenario]:
        customer = Customer.objects.filter(workshop=workshop).annotate(related_count=Count("budgets")).order_by("-related_count", "pk").first()
        supplier = Supplier.objects.filter(workshop=workshop).annotate(related_count=Count("movements")).order_by("-related_count", "pk").first()
        workorder = WorkOrder.objects.filter(workshop=workshop).annotate(related_count=Count("history_entries")).order_by("-related_count", "pk").first()
        product = Product.objects.filter(workshop=workshop).order_by("pk").first()
        if any(item is None for item in (customer, supplier, workorder, product)):
            raise CommandError("Dataset incompleto para resolver IDs sintéticos das rotas.")

        customer_history_count = Budget.objects.filter(customer=customer).count()
        product_history_count = BudgetItem.objects.filter(product=product).count() + WorkOrderItem.objects.filter(product=product).count()
        supplier_history_count = StockMovement.objects.filter(supplier=supplier).count()
        workorder_history_count = WorkOrderHistory.objects.filter(workorder=workorder).count()

        return [
            Scenario("dashboard_current_month", "core:dashboard", reverse("core:dashboard"), "dashboard", {"mes": "7", "ano": "2026"}, notes="Dashboard no mês de referência"),
            Scenario("dashboard_previous_month", "core:dashboard", reverse("core:dashboard"), "dashboard", {"mes": "6", "ano": "2026"}, notes="Dashboard no mês anterior"),
            Scenario("budget_list_default", "budget:budget_list", reverse("budget:budget_list"), "table", {}, 1_500, "Queryset completo entregue ao helper"),
            Scenario("budget_list_page_2", "budget:budget_list", reverse("budget:budget_list"), "table", {"page": "2"}, 1_500, "Paginação posterior do helper"),
            Scenario("budget_list_search", "budget:budget_list", reverse("budget:budget_list"), "table", {"q": "Cliente Benchmark 00001"}, 1_500, "Busca ativa no helper"),
            Scenario("budget_list_filtered", "budget:budget_list", reverse("budget:budget_list"), "date_filter", {"status": "approved", "data_inicial": "2026-07-01", "data_final": "2026-07-31"}, 1_500, "Status e período ativos"),
            Scenario("workorder_list_default", "workorder:workorder_list", reverse("workorder:workorder_list"), "table", {}, 1_000, "Queryset completo entregue ao helper"),
            Scenario("workorder_list_page_2", "workorder:workorder_list", reverse("workorder:workorder_list"), "table", {"page": "2"}, 1_000, "Paginação posterior do helper"),
            Scenario("workorder_list_search", "workorder:workorder_list", reverse("workorder:workorder_list"), "table", {"q": "Cliente Benchmark 00001"}, 1_000, "Busca ativa no helper"),
            Scenario("workorder_list_date_filter", "workorder:workorder_list", reverse("workorder:workorder_list"), "date_filter", {"data_inicial": "2026-07-01", "data_final": "2026-07-31"}, 1_000, "Lookup delivered_at__date"),
            Scenario("customer_list_default", "customer:customer_list", reverse("customer:customer_list"), "table", {}, 600),
            Scenario("customer_list_page_2", "customer:customer_list", reverse("customer:customer_list"), "table", {"page": "2"}, 600),
            Scenario("customer_list_search", "customer:customer_list", reverse("customer:customer_list"), "table", {"q": "Cliente Benchmark 00500"}, 600),
            Scenario("product_list_default", "catalog:product_list", reverse("catalog:product_list"), "table", {}, 250),
            Scenario("product_list_page_2", "catalog:product_list", reverse("catalog:product_list"), "table", {"page": "2"}, 250),
            Scenario("product_list_search", "catalog:product_list", reverse("catalog:product_list"), "table", {"q": "Produto Benchmark 00200"}, 250),
            Scenario("customer_history_detail", "customer:customer_history_detail", reverse("customer:customer_history_detail", kwargs={"pk": customer.pk}), "overfetch", {}, customer_history_count, f"Cliente sintético #{customer.pk}"),
            Scenario("product_update_history", "catalog:product_update", reverse("catalog:product_update", kwargs={"pk": product.pk}), "overfetch", {}, product_history_count, f"Produto sintético #{product.pk}"),
            Scenario("issued_documents_default", "finance:issued_documents_list", reverse("finance:issued_documents_list"), "overfetch", {}, 600, "NF-e + NFS-e materializadas e mescladas"),
            Scenario("issued_documents_date_filter", "finance:issued_documents_list", reverse("finance:issued_documents_list"), "date_filter", {"data_inicial": "2026-06-01", "data_final": "2026-07-31"}, 600, "Lookup criado_em__date__range"),
            Scenario("supplier_update_history", "suppliers:supplier_update", reverse("suppliers:supplier_update", kwargs={"pk": supplier.pk}), "overfetch", {}, supplier_history_count, f"Fornecedor sintético #{supplier.pk}"),
            Scenario("workorder_detail_history", "workorder:workorder_detail", reverse("workorder:workorder_detail", kwargs={"pk": workorder.pk}), "overfetch", {}, workorder_history_count, f"OS sintética #{workorder.pk}"),
            Scenario("stock_report_default", "stock:report", reverse("stock:report"), "table", {}, 250),
            Scenario("stock_report_search", "stock:report", reverse("stock:report"), "table", {"piece": "Produto Benchmark 00200"}, 250),
            Scenario("financial_reports_home", "finance:reports_home", reverse("finance:reports_home"), "finance", {}, 1_500),
            Scenario("financial_movement_default", "finance:financial_movement_list", reverse("finance:financial_movement_list"), "table", {}, 1_500),
            Scenario("financial_movement_date_filter", "finance:financial_movement_list", reverse("finance:financial_movement_list"), "date_filter", {"data_inicial": "2026-07-01", "data_final": "2026-07-31"}, 1_500, "Range nativo em due_date"),
            Scenario("commission_date_filter", "finance:commission_report", reverse("finance:commission_report"), "date_filter", {"data_inicial": "2026-01-01", "data_final": "2026-07-31"}, 0, "Lookup criado_em__date em comissões"),
        ]

    def _measure_scenario(
        self,
        *,
        client: Client,
        scenario: Scenario,
        warmups: int,
        measured_runs: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        for _ in range(warmups):
            response = client.get(scenario.path, data=scenario.params)
            response.close()

        runs: list[dict[str, Any]] = []
        flattened_queries: list[dict[str, Any]] = []
        flattened_dependencies: list[dict[str, Any]] = []

        for run_number in range(1, measured_runs + 1):
            gc.collect()
            query_records: list[QueryRecord] = []
            dependency_records: list[DependencyRecord] = []
            with self._capture_queries(query_records), self._capture_dependencies(dependency_records):
                started_at = time.perf_counter()
                response = client.get(scenario.path, data=scenario.params)
                duration_ms = (time.perf_counter() - started_at) * 1_000

            patterns = Counter(record.normalized for record in query_records)
            duplicate_patterns = [
                {
                    "normalized_sql": pattern,
                    "executions": executions,
                }
                for pattern, executions in patterns.most_common()
                if executions > 1
            ]
            sql_time_ms = sum(record.duration_ms for record in query_records)
            select_rows = sum(max(record.rowcount, 0) for record in query_records if record.sql.lstrip().upper().startswith("SELECT"))
            count_records = [record for record in query_records if "COUNT(" in record.sql.upper()]
            slowest = max(query_records, key=lambda record: record.duration_ms, default=None)
            run = {
                "run": run_number,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 4),
                "sql_time_ms": round(sql_time_ms, 4),
                "non_sql_time_ms": round(max(duration_ms - sql_time_ms, 0.0), 4),
                "query_count": len(query_records),
                "unique_query_count": len(patterns),
                "duplicate_query_count": len(query_records) - len(patterns),
                "duplicate_patterns": duplicate_patterns[:20],
                "select_rows_observed": select_rows,
                "response_bytes": len(response.content),
                "rendered_desktop_rows": rendered_desktop_rows(response.content),
                "count_query_count": len(count_records),
                "count_time_ms": round(sum(record.duration_ms for record in count_records), 4),
                "slowest_query": self._serialize_query_record(slowest, include_sql=False) if slowest else None,
                "dependency_calls": [self._serialize_dependency_record(record) for record in dependency_records],
            }
            runs.append(run)
            for record in query_records:
                flattened_queries.append(
                    {
                        **self._serialize_query_record(record),
                        "_raw_params": record.params,
                        "scenario": scenario.name,
                        "route_name": scenario.route_name,
                        "run": run_number,
                    }
                )
            for record in dependency_records:
                flattened_dependencies.append(
                    {
                        **self._serialize_dependency_record(record),
                        "scenario": scenario.name,
                        "route_name": scenario.route_name,
                        "run": run_number,
                    }
                )
            response.close()

        duration_values = [float(run["duration_ms"]) for run in runs]
        sql_values = [float(run["sql_time_ms"]) for run in runs]
        non_sql_values = [float(run["non_sql_time_ms"]) for run in runs]
        query_counts = [int(run["query_count"]) for run in runs]
        unique_counts = [int(run["unique_query_count"]) for run in runs]
        duplicate_counts = [int(run["duplicate_query_count"]) for run in runs]
        response_sizes = [int(run["response_bytes"]) for run in runs]
        select_rows = [int(run["select_rows_observed"]) for run in runs]
        rendered_rows = [int(run["rendered_desktop_rows"]) for run in runs if run["rendered_desktop_rows"] is not None]
        count_times = [float(run["count_time_ms"]) for run in runs]
        count_counts = [int(run["count_query_count"]) for run in runs]

        route_result = {
            "scenario": scenario.name,
            "route_name": scenario.route_name,
            "path": scenario.path,
            "params": scenario.params,
            "group": scenario.group,
            "notes": scenario.notes,
            "status_codes": sorted({int(run["status_code"]) for run in runs}),
            "duration_ms": self._distribution(duration_values),
            "sql_time_ms": self._distribution(sql_values),
            "non_sql_time_ms": self._distribution(non_sql_values),
            "queries": {"median": median_int(query_counts), "min": min(query_counts), "max": max(query_counts)},
            "unique_queries": {"median": median_int(unique_counts), "min": min(unique_counts), "max": max(unique_counts)},
            "duplicate_queries": {"median": median_int(duplicate_counts), "min": min(duplicate_counts), "max": max(duplicate_counts)},
            "response_bytes": self._distribution([float(value) for value in response_sizes]),
            "records_total": scenario.records_total,
            "select_rows_observed": {"median": median_int(select_rows), "min": min(select_rows), "max": max(select_rows)},
            "rendered_desktop_rows": {"median": median_int(rendered_rows), "min": min(rendered_rows), "max": max(rendered_rows)} if rendered_rows else None,
            "count_queries": {"median": median_int(count_counts), "time_ms": self._distribution(count_times)},
            "most_frequent_duplicate_patterns": self._aggregate_route_duplicates(runs),
            "runs": runs,
        }
        return route_result, flattened_queries, flattened_dependencies

    @staticmethod
    def _distribution(values: list[float]) -> dict[str, float]:
        return {
            "min": round(min(values), 4) if values else 0.0,
            "median": round(statistics.median(values), 4) if values else 0.0,
            "p95": round(percentile(values, 0.95), 4),
            "max": round(max(values), 4) if values else 0.0,
        }

    @staticmethod
    def _serialize_query_record(record: QueryRecord, *, include_sql: bool = True) -> dict[str, Any]:
        serialized = {
            "normalized_sql": record.normalized,
            "duration_ms": round(record.duration_ms, 4),
            "rowcount": record.rowcount,
        }
        if include_sql:
            serialized["sql"] = record.sql
            serialized["params"] = json_safe(record.params)
        return serialized

    @staticmethod
    def _route_ranking(route_results: list[dict[str, Any]], *, sort_key: str) -> list[dict[str, Any]]:
        def ranking_value(route: dict[str, Any]) -> float:
            if sort_key == "queries":
                return float(route["queries"]["median"])
            return float(route["duration_ms"]["p95"])

        return [
            {
                "scenario": route["scenario"],
                "route_name": route["route_name"],
                "status_codes": route["status_codes"],
                "duration_ms": route["duration_ms"],
                "queries": route["queries"],
                "unique_queries": route["unique_queries"],
                "duplicate_queries": route["duplicate_queries"],
            }
            for route in sorted(route_results, key=ranking_value, reverse=True)
        ]

    @staticmethod
    def _serialize_dependency_record(record: DependencyRecord) -> dict[str, Any]:
        return {
            "method": record.method,
            "url": record.url,
            "duration_ms": record.duration_ms,
            "result": record.result,
        }

    @staticmethod
    def _aggregate_route_duplicates(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pattern_max: dict[str, int] = defaultdict(int)
        for run in runs:
            for pattern in run["duplicate_patterns"]:
                sql = str(pattern["normalized_sql"])
                pattern_max[sql] = max(pattern_max[sql], int(pattern["executions"]))
        return [
            {"normalized_sql": sql, "max_executions_in_one_request": executions}
            for sql, executions in sorted(pattern_max.items(), key=lambda item: item[1], reverse=True)[:20]
        ]

    @staticmethod
    @contextmanager
    def _capture_queries(records: list[QueryRecord]) -> Iterator[None]:
        def wrapper(execute, sql, params, many, context):
            started_at = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = (time.perf_counter() - started_at) * 1_000
                cursor = context.get("cursor")
                rowcount = int(getattr(cursor, "rowcount", -1) or -1)
                records.append(QueryRecord(sql=str(sql), params=params, duration_ms=duration_ms, rowcount=rowcount))

        with connection.execute_wrapper(wrapper):
            yield

    @staticmethod
    @contextmanager
    def _capture_dependencies(records: list[DependencyRecord]) -> Iterator[None]:
        original_request = requests.sessions.Session.request

        def measured_request(session, method, url, *args, **kwargs):
            started_at = time.perf_counter()
            result = "success"
            try:
                return original_request(session, method, url, *args, **kwargs)
            except Exception:
                result = "error"
                raise
            finally:
                records.append(
                    DependencyRecord(
                        method=str(method).upper(),
                        url=str(url),
                        duration_ms=round((time.perf_counter() - started_at) * 1_000, 4),
                        result=result,
                    )
                )

        with patch.object(requests.sessions.Session, "request", measured_request):
            yield

    @staticmethod
    def _build_pattern_ranking(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        aggregated: dict[str, dict[str, Any]] = {}
        for record in records:
            normalized = str(record["normalized_sql"])
            item = aggregated.setdefault(
                normalized,
                {
                    "normalized_sql": normalized,
                    "executions": 0,
                    "total_time_ms": 0.0,
                    "max_time_ms": 0.0,
                    "routes": set(),
                    "example_sql": record["sql"],
                    "example_params": record["params"],
                },
            )
            duration_ms = float(record["duration_ms"])
            item["executions"] += 1
            item["total_time_ms"] += duration_ms
            item["max_time_ms"] = max(item["max_time_ms"], duration_ms)
            item["routes"].add(record["scenario"])

        ranking: list[dict[str, Any]] = []
        for item in aggregated.values():
            executions = int(item["executions"])
            ranking.append(
                {
                    **item,
                    "routes": sorted(item["routes"]),
                    "total_time_ms": round(float(item["total_time_ms"]), 4),
                    "average_time_ms": round(float(item["total_time_ms"]) / executions, 4),
                    "max_time_ms": round(float(item["max_time_ms"]), 4),
                }
            )
        return sorted(ranking, key=lambda item: item["total_time_ms"], reverse=True)

    @staticmethod
    def _build_n_plus_one_candidates(route_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for route in route_results:
            for pattern in route["most_frequent_duplicate_patterns"]:
                executions = int(pattern["max_executions_in_one_request"])
                sql = str(pattern["normalized_sql"])
                if executions < 5 or not sql.upper().startswith("SELECT"):
                    continue
                candidates.append(
                    {
                        "scenario": route["scenario"],
                        "route_name": route["route_name"],
                        "normalized_sql": sql,
                        "repetitions_in_one_request": executions,
                        "classification": "probable",
                        "evidence": f"Mesmo padrão SELECT repetido {executions} vezes em uma request medida.",
                    }
                )
        return sorted(candidates, key=lambda item: item["repetitions_in_one_request"], reverse=True)

    @staticmethod
    def _explain_top_patterns(*, all_query_records: list[dict[str, Any]], pattern_ranking: list[dict[str, Any]]) -> list[dict[str, Any]]:
        records_by_pattern: dict[str, dict[str, Any]] = {}
        for record in sorted(all_query_records, key=lambda item: item["duration_ms"], reverse=True):
            normalized = str(record["normalized_sql"])
            if normalized not in records_by_pattern and str(record["sql"]).lstrip().upper().startswith("SELECT"):
                records_by_pattern[normalized] = record

        plans: list[dict[str, Any]] = []
        for pattern in pattern_ranking:
            normalized = str(pattern["normalized_sql"])
            record = records_by_pattern.get(normalized)
            if record is None:
                continue
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {record['sql']}", record["_raw_params"])
                    raw_plan = cursor.fetchone()[0][0]
                nodes: list[dict[str, Any]] = []
                Command._collect_plan_nodes(raw_plan["Plan"], nodes)
                plans.append(
                    {
                        "normalized_sql": normalized,
                        "planning_time_ms": raw_plan.get("Planning Time"),
                        "execution_time_ms": raw_plan.get("Execution Time"),
                        "nodes": nodes,
                    }
                )
            except Exception as exc:
                plans.append({"normalized_sql": normalized, "error": f"{type(exc).__name__}: {exc}"})
        return plans

    @staticmethod
    def _collect_plan_nodes(node: dict[str, Any], target: list[dict[str, Any]]) -> None:
        target.append(
            {
                "node_type": node.get("Node Type"),
                "relation_name": node.get("Relation Name"),
                "index_name": node.get("Index Name"),
                "actual_rows": node.get("Actual Rows"),
                "actual_loops": node.get("Actual Loops"),
                "actual_total_time_ms": node.get("Actual Total Time"),
                "shared_hit_blocks": node.get("Shared Hit Blocks"),
                "shared_read_blocks": node.get("Shared Read Blocks"),
            }
        )
        for child in node.get("Plans", []):
            Command._collect_plan_nodes(child, target)
