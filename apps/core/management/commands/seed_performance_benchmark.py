from __future__ import annotations

import calendar
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_DNS, uuid5

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.budget.models import Budget, BudgetHistory, BudgetItem, BudgetStatus, BudgetType
from apps.catalog.models import CatalogGroup, Product, Service
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.finance.models import FinancialGroup, FinancialMovement, NfeItem, NfeRequest, NfseItem, NfseRequest, PaymentMethod
from apps.iam.models import WorkshopRole
from apps.stock.models import StockMovement, StockProduct
from apps.suppliers.models import Supplier
from apps.workorder.models import WorkOrder, WorkOrderHistory, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostWorkDay
from apps.workshops.models.workshops import Workshop


REFERENCE_DATE = date(2026, 7, 12)
BENCHMARK_DATABASE_PREFIX = "hunter_v2_perf_"

SCALE_VOLUMES: dict[str, dict[str, int]] = {
    "smoke": {
        "customers": 20,
        "products": 20,
        "services": 8,
        "suppliers": 5,
        "budgets": 40,
        "workorders": 30,
        "fiscal_each": 8,
        "stock_movements_per_product": 2,
    },
    "standard": {
        "customers": 600,
        "products": 250,
        "services": 80,
        "suppliers": 40,
        "budgets": 1_500,
        "workorders": 1_000,
        "fiscal_each": 300,
        "stock_movements_per_product": 8,
    },
}


def _distributed_date(index: int) -> date:
    return REFERENCE_DATE - timedelta(days=(index * 7) % 730)


def _aware_datetime(value: date) -> datetime:
    return timezone.make_aware(datetime.combine(value, time(hour=12)))


def _shift_timestamps(objects: list[Any], model: type[Any], dates: list[date]) -> None:
    for obj, value in zip(objects, dates, strict=True):
        timestamp = _aware_datetime(value)
        obj.criado_em = timestamp
        obj.atualizado_em = timestamp
    model.objects.bulk_update(objects, ["criado_em", "atualizado_em"], batch_size=1_000)


def _month_reference(offset: int) -> tuple[int, int]:
    absolute_month = REFERENCE_DATE.year * 12 + REFERENCE_DATE.month - 1 - offset
    return absolute_month // 12, absolute_month % 12 + 1


def validate_benchmark_target(*, database_name: str, benchmark_environment: bool) -> None:
    if not benchmark_environment:
        raise CommandError("Use DJANGO_SETTINGS_MODULE=config.settings_benchmark.")
    if database_name == "meu_crm" or not database_name.startswith(BENCHMARK_DATABASE_PREFIX):
        raise CommandError(f"Banco proibido para seed de benchmark: {database_name!r}.")


class Command(BaseCommand):
    help = "Cria dados sintéticos determinísticos exclusivamente em um banco isolado de benchmark."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--scale", choices=sorted(SCALE_VOLUMES), default="standard")

    def handle(self, *args: object, **options: object) -> None:
        database_name = str(connection.settings_dict.get("NAME") or "")
        validate_benchmark_target(
            database_name=database_name,
            benchmark_environment=bool(getattr(settings, "BENCHMARK_ENVIRONMENT", False)),
        )
        if Account.objects.exists():
            raise CommandError("O seed exige banco vazio. Recrie o banco descartável em vez de apagar dados parcialmente.")

        scale = str(options["scale"])
        volumes = SCALE_VOLUMES[scale]
        self.stdout.write(f"Seed determinístico scale={scale} database={database_name}")

        with transaction.atomic():
            summary = self._seed(volumes=volumes)

        self.stdout.write(self.style.SUCCESS(json.dumps(summary, indent=2, sort_keys=True)))

    def _seed(self, *, volumes: dict[str, int]) -> dict[str, int]:
        account = Account.objects.create(name="Conta Benchmark")
        user = User.objects.create_user(
            username="benchmark.owner",
            password="benchmark-only",
            email="benchmark@example.invalid",
            cpf="52998224725",
            account=account,
            is_account_owner=True,
        )
        account.owner = user
        account.save(update_fields=["owner"])

        workshops = [
            Workshop(
                account=account,
                name=f"Oficina Benchmark {index + 1}",
                cnpj=f"{index + 1:014d}",
                phone="+5511999990000",
                address=f"Rua Sintética, {index + 1}",
                uf="SP",
            )
            for index in range(2)
        ]
        Workshop.objects.bulk_create(workshops)
        primary_workshop = workshops[0]

        role = WorkshopRole.objects.create(account=account, name="Diretor Benchmark", is_system=True, is_editable=False)
        role.permissions.set(Permission.objects.all())
        WorkshopMember.objects.bulk_create([WorkshopMember(user=user, workshop=workshop, role=role, is_active=True) for workshop in workshops])

        catalog_group = CatalogGroup.objects.create(workshop=primary_workshop, name="Grupo Benchmark")
        payment_method = PaymentMethod.objects.create(workshop=primary_workshop, description="Pagamento Benchmark")
        financial_group = FinancialGroup.objects.create(workshop=primary_workshop, name="Vendas")

        customers = [
            Customer(
                workshop=primary_workshop,
                name=f"Cliente Benchmark {index:05d}",
                cpf_or_cnpj=f"{index + 1:011d}",
                email=f"cliente{index:05d}@example.invalid",
                birth_date=date(1970 + index % 35, index % 12 + 1, index % 27 + 1),
                cep="01001000",
                logradouro="Rua Sintética",
                numero=index + 1,
                bairro="Centro",
                cidade="São Paulo",
                estado="SP",
            )
            for index in range(volumes["customers"])
        ]
        Customer.objects.bulk_create(customers, batch_size=1_000)

        vehicles = [
            Vehicle(
                workshop=primary_workshop,
                customer=customer,
                plate=f"P{index:06d}",
                brand=f"Marca {index % 12}",
                model=f"Modelo {index % 40}",
                year_fabrication=str(2000 + index % 25),
                year_model=str(2001 + index % 25),
                color="Prata",
                km=10_000 + index * 100,
            )
            for index, customer in enumerate(customers)
        ]
        Vehicle.objects.bulk_create(vehicles, batch_size=1_000)

        suppliers = [
            Supplier(
                workshop=primary_workshop,
                cnpj=f"{index + 100:014d}",
                name=f"Fornecedor Benchmark {index:04d}",
                email=f"fornecedor{index:04d}@example.invalid",
                cep="01001000",
                logradouro="Avenida Sintética",
                numero=index + 1,
                bairro="Centro",
                cidade="São Paulo",
                estado="SP",
                registration_date=_distributed_date(index),
            )
            for index in range(volumes["suppliers"])
        ]
        Supplier.objects.bulk_create(suppliers, batch_size=1_000)

        products = [
            Product(
                workshop=primary_workshop,
                code=f"PRD-{index:05d}",
                name=f"Produto Benchmark {index:05d}",
                description="Produto sintético para benchmark",
                unit=Product.Unit.UND,
                group=catalog_group,
                brand=f"Marca {index % 20}",
                location=f"A-{index % 30:02d}",
                cost_price=Decimal("40.00") + index % 17,
                selling_price=Decimal("80.00") + index % 31,
                ncm="87089990",
            )
            for index in range(volumes["products"])
        ]
        Product.objects.bulk_create(products, batch_size=1_000)

        services = [
            Service(
                workshop=primary_workshop,
                name=f"Serviço Benchmark {index:04d}",
                description="Serviço sintético para benchmark",
                duration=timedelta(minutes=30 + index % 8 * 15),
                suggested_cost=Decimal("35.00") + index % 13,
                selling_price=Decimal("90.00") + index % 29,
                shipping=Decimal("5.00") if index % 5 == 0 else Decimal("0.00"),
                is_third_party=index % 9 == 0,
            )
            for index in range(volumes["services"])
        ]
        Service.objects.bulk_create(services, batch_size=1_000)

        budgets = self._create_budgets(
            workshop=primary_workshop,
            user=user,
            customers=customers,
            vehicles=vehicles,
            count=volumes["budgets"],
        )
        budget_items = self._create_budget_items(workshop=primary_workshop, budgets=budgets, products=products, services=services)
        budget_histories = self._create_budget_histories(budgets=budgets, user=user)

        workorders = self._create_workorders(workshop=primary_workshop, budgets=budgets[: volumes["workorders"]])
        workorder_items = self._create_workorder_items(workshop=primary_workshop, workorders=workorders, products=products, services=services)
        payments = self._create_payments(workorders=workorders, payment_method=payment_method)
        workorder_histories = self._create_workorder_histories(workorders=workorders, user=user)

        nfe_requests, nfe_items, nfse_requests, nfse_items = self._create_fiscal_documents(
            workshop=primary_workshop,
            workorders=workorders,
            each_count=min(volumes["fiscal_each"], len(workorders) // 2),
        )
        movements = self._create_financial_movements(
            workshop=primary_workshop,
            user=user,
            payments=payments,
            payment_method=payment_method,
            financial_group=financial_group,
        )
        stock_products, stock_movements = self._create_stock(
            workshop=primary_workshop,
            user=user,
            products=products,
            suppliers=suppliers,
            movements_per_product=volumes["stock_movements_per_product"],
        )
        workshop_costs = self._create_workshop_costs(workshop=primary_workshop)

        models_to_count = [
            Account,
            User,
            Workshop,
            Customer,
            Vehicle,
            Supplier,
            Product,
            Service,
            Budget,
            BudgetItem,
            BudgetHistory,
            WorkOrder,
            WorkOrderItem,
            WorkOrderPaymentMethod,
            WorkOrderHistory,
            NfeRequest,
            NfeItem,
            NfseRequest,
            NfseItem,
            FinancialMovement,
            StockProduct,
            StockMovement,
            WorkshopCost,
        ]
        summary = {model._meta.label: model.objects.count() for model in models_to_count}
        summary["seed.budget_items_created"] = len(budget_items)
        summary["seed.budget_histories_created"] = len(budget_histories)
        summary["seed.workorder_items_created"] = len(workorder_items)
        summary["seed.workorder_histories_created"] = len(workorder_histories)
        summary["seed.nfe_requests_created"] = len(nfe_requests)
        summary["seed.nfe_items_created"] = len(nfe_items)
        summary["seed.nfse_requests_created"] = len(nfse_requests)
        summary["seed.nfse_items_created"] = len(nfse_items)
        summary["seed.financial_movements_created"] = len(movements)
        summary["seed.stock_products_created"] = len(stock_products)
        summary["seed.stock_movements_created"] = len(stock_movements)
        summary["seed.workshop_costs_created"] = len(workshop_costs)
        return summary

    @staticmethod
    def _create_budgets(*, workshop: Workshop, user: User, customers: list[Customer], vehicles: list[Vehicle], count: int) -> list[Budget]:
        statuses = [
            BudgetStatus.APPROVED,
            BudgetStatus.WAITING_APPROVAL,
            BudgetStatus.REJECTED,
            BudgetStatus.DRAFT,
            BudgetStatus.CANCELLED,
            BudgetStatus.WAITING_ITEMS,
        ]
        budgets: list[Budget] = []
        dates: list[date] = []
        for index in range(count):
            entry_date = _distributed_date(index)
            budget_type = BudgetType.WARRANTY if index % 20 == 0 else BudgetType.COURTESY if index % 25 == 0 else BudgetType.SALE
            budgets.append(
                Budget(
                    workshop=workshop,
                    customer=customers[index % len(customers)],
                    vehicle=vehicles[index % len(vehicles)],
                    cost_estimator=user,
                    entry_date=entry_date,
                    expiration_date=entry_date + timedelta(days=15),
                    budget_type=budget_type,
                    is_warranty_budget=budget_type == BudgetType.WARRANTY,
                    status=statuses[index % len(statuses)],
                    current_step=6,
                    current_km=10_000 + index * 10,
                    problem_description="Relato sintético de benchmark",
                    technical_diagnosis="Diagnóstico sintético de benchmark",
                    pricing_method="hunter",
                )
            )
            dates.append(entry_date)
        Budget.objects.bulk_create(budgets, batch_size=1_000)
        _shift_timestamps(budgets, Budget, dates)
        return budgets

    @staticmethod
    def _create_budget_items(*, workshop: Workshop, budgets: list[Budget], products: list[Product], services: list[Service]) -> list[BudgetItem]:
        items: list[BudgetItem] = []
        for index, budget in enumerate(budgets):
            for position in range(2):
                product = products[(index * 2 + position) % len(products)]
                items.append(
                    BudgetItem(
                        workshop=workshop,
                        budget=budget,
                        product=product,
                        description=product.name,
                        quantity=position + 1,
                        product_cost_price=product.cost_price,
                        product_selling_price=product.selling_price,
                        shipping=Decimal("8.00") if position == 0 else Decimal("0.00"),
                    )
                )
            service = services[index % len(services)]
            items.append(
                BudgetItem(
                    workshop=workshop,
                    budget=budget,
                    service=service,
                    description=service.name,
                    quantity=1,
                    service_cost_price=service.suggested_cost or Decimal("0.00"),
                    service_selling_price=service.selling_price,
                    service_shipping=service.shipping or Decimal("0.00"),
                    duration=service.duration,
                )
            )
        BudgetItem.objects.bulk_create(items, batch_size=1_000)
        return items

    @staticmethod
    def _create_budget_histories(*, budgets: list[Budget], user: User) -> list[BudgetHistory]:
        histories = [
            BudgetHistory(budget=budget, user=user, action=BudgetHistory.Action.REOPENED, reason=f"Histórico sintético {position}", snapshot={"benchmark": True, "position": position})
            for budget in budgets
            for position in range(2)
        ]
        BudgetHistory.objects.bulk_create(histories, batch_size=1_000)
        dates = [_distributed_date(index // 2) + timedelta(days=index % 2) for index in range(len(histories))]
        _shift_timestamps(histories, BudgetHistory, dates)
        return histories

    @staticmethod
    def _create_workorders(*, workshop: Workshop, budgets: list[Budget]) -> list[WorkOrder]:
        workorders: list[WorkOrder] = []
        dates: list[date] = []
        for index, budget in enumerate(budgets):
            created_date = _distributed_date(index)
            status = WorkOrderStatus.DRAFT if index % 3 == 0 else WorkOrderStatus.APPROVED
            workorders.append(
                WorkOrder(
                    workshop=workshop,
                    budget=budget,
                    status=status,
                    budget_type=budget.budget_type,
                    pricing_method="hunter",
                    delivered_at=_aware_datetime(created_date + timedelta(days=3)) if status == WorkOrderStatus.APPROVED else None,
                )
            )
            dates.append(created_date)
        WorkOrder.objects.bulk_create(workorders, batch_size=1_000)
        _shift_timestamps(workorders, WorkOrder, dates)
        return workorders

    @staticmethod
    def _create_workorder_items(*, workshop: Workshop, workorders: list[WorkOrder], products: list[Product], services: list[Service]) -> list[WorkOrderItem]:
        items: list[WorkOrderItem] = []
        for index, workorder in enumerate(workorders):
            for position in range(2):
                product = products[(index * 2 + position) % len(products)]
                items.append(
                    WorkOrderItem(
                        workshop=workshop,
                        workorder=workorder,
                        product=product,
                        description=product.name,
                        quantity=position + 1,
                        product_cost_price=product.cost_price,
                        product_selling_price=product.selling_price,
                        shipping=Decimal("8.00") if position == 0 else Decimal("0.00"),
                    )
                )
            service = services[index % len(services)]
            items.append(
                WorkOrderItem(
                    workshop=workshop,
                    workorder=workorder,
                    service=service,
                    description=service.name,
                    quantity=1,
                    service_cost_price=service.suggested_cost or Decimal("0.00"),
                    service_selling_price=service.selling_price,
                    service_shipping=service.shipping or Decimal("0.00"),
                    duration=service.duration,
                )
            )
        WorkOrderItem.objects.bulk_create(items, batch_size=1_000)
        return items

    @staticmethod
    def _create_payments(*, workorders: list[WorkOrder], payment_method: PaymentMethod) -> list[WorkOrderPaymentMethod]:
        payments: list[WorkOrderPaymentMethod] = []
        for index, workorder in enumerate(workorders):
            due_date = _distributed_date(index)
            payments.append(
                WorkOrderPaymentMethod(
                    workorder=workorder,
                    payment_method=payment_method,
                    installments_count=2,
                    first_installment_amount=Decimal("250.00") + index % 50,
                    remaining_installments_amount=Decimal("250.00") + index % 50,
                    due_date=due_date,
                )
            )
            if index % 2 == 0:
                payments.append(
                    WorkOrderPaymentMethod(
                        workorder=workorder,
                        payment_method=payment_method,
                        installments_count=1,
                        first_installment_amount=Decimal("100.00") + index % 25,
                        due_date=due_date + timedelta(days=30),
                    )
                )
        WorkOrderPaymentMethod.objects.bulk_create(payments, batch_size=1_000)
        return payments

    @staticmethod
    def _create_workorder_histories(*, workorders: list[WorkOrder], user: User) -> list[WorkOrderHistory]:
        histories = [
            WorkOrderHistory(workorder=workorder, user=user, action=WorkOrderHistory.Action.REOPENED, reason=f"Histórico sintético {position}")
            for workorder in workorders
            for position in range(3)
        ]
        WorkOrderHistory.objects.bulk_create(histories, batch_size=1_000)
        dates = [_distributed_date(index // 3) + timedelta(days=index % 3) for index in range(len(histories))]
        _shift_timestamps(histories, WorkOrderHistory, dates)
        return histories

    @staticmethod
    def _create_fiscal_documents(*, workshop: Workshop, workorders: list[WorkOrder], each_count: int) -> tuple[list[NfeRequest], list[NfeItem], list[NfseRequest], list[NfseItem]]:
        nfe_workorders = workorders[:each_count]
        nfse_workorders = workorders[each_count : each_count * 2]
        nfe_requests = [NfeRequest(workshop=workshop, workorder=workorder, reserved_number=index + 1, reserved_series=1) for index, workorder in enumerate(nfe_workorders)]
        nfse_requests = [NfseRequest(workshop=workshop, workorder=workorder, reserved_rps_number=index + 1, reserved_rps_series="1") for index, workorder in enumerate(nfse_workorders)]
        NfeRequest.objects.bulk_create(nfe_requests, batch_size=1_000)
        NfseRequest.objects.bulk_create(nfse_requests, batch_size=1_000)
        _shift_timestamps(nfe_requests, NfeRequest, [_distributed_date(index) for index in range(len(nfe_requests))])
        _shift_timestamps(nfse_requests, NfseRequest, [_distributed_date(index + each_count) for index in range(len(nfse_requests))])

        nfe_items = [
            NfeItem(
                workshop=workshop,
                workorder=request.workorder,
                request=request,
                uuid=uuid5(NAMESPACE_DNS, f"hunter-v2-benchmark-nfe-{index}"),
                number=str(index + 1),
                series="1",
                access_key=f"{index + 1:044d}",
            )
            for index, request in enumerate(nfe_requests)
        ]
        nfse_items = [
            NfseItem(
                workshop=workshop,
                workorder=request.workorder,
                request=request,
                uuid=uuid5(NAMESPACE_DNS, f"hunter-v2-benchmark-nfse-{index}"),
                number=str(index + 1),
                rps_series="1",
                rps_number=str(index + 1),
            )
            for index, request in enumerate(nfse_requests)
        ]
        NfeItem.objects.bulk_create(nfe_items, batch_size=1_000)
        NfseItem.objects.bulk_create(nfse_items, batch_size=1_000)
        return nfe_requests, nfe_items, nfse_requests, nfse_items

    @staticmethod
    def _create_financial_movements(
        *,
        workshop: Workshop,
        user: User,
        payments: list[WorkOrderPaymentMethod],
        payment_method: PaymentMethod,
        financial_group: FinancialGroup,
    ) -> list[FinancialMovement]:
        movements = [
            FinancialMovement(
                workshop=workshop,
                user=user,
                workorder=payment.workorder,
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.DEFAULT,
                description=f"Movimento sintético {index}",
                direction=FinancialMovement.MovementDirection.CREDIT,
                payment_method=payment_method,
                amount=payment.first_installment_amount,
                due_date=payment.due_date,
                is_paid=index % 3 != 0,
                is_reconciled=index % 4 != 0,
                budget_plan=financial_group,
            )
            for index, payment in enumerate(payments)
        ]
        FinancialMovement.objects.bulk_create(movements, batch_size=1_000)
        _shift_timestamps(movements, FinancialMovement, [payment.due_date for payment in payments])
        return movements

    @staticmethod
    def _create_stock(
        *,
        workshop: Workshop,
        user: User,
        products: list[Product],
        suppliers: list[Supplier],
        movements_per_product: int,
    ) -> tuple[list[StockProduct], list[StockMovement]]:
        stock_products = [
            StockProduct(
                workshop=workshop,
                product=product,
                supplier=suppliers[index % len(suppliers)],
                current_quantity=20 + index % 80,
                minimum_quantity=5,
                restock_quantity=20,
                last_nf=f"NF-{index:06d}",
            )
            for index, product in enumerate(products)
        ]
        StockProduct.objects.bulk_create(stock_products, batch_size=1_000)
        movements = [
            StockMovement(
                workshop=workshop,
                stock_product=stock_product,
                type=StockMovement.MovementType.ENTRY if position % 2 == 0 else StockMovement.MovementType.EXIT,
                supplier=stock_product.supplier,
                transcation_by=user,
                quantity=position % 5 + 1,
                status=StockMovement.MovementStatus.APPROVED,
            )
            for stock_product in stock_products
            for position in range(movements_per_product)
        ]
        StockMovement.objects.bulk_create(movements, batch_size=1_000)
        _shift_timestamps(movements, StockMovement, [_distributed_date(index) for index in range(len(movements))])
        return stock_products, movements

    @staticmethod
    def _create_workshop_costs(*, workshop: Workshop) -> list[WorkshopCost]:
        costs: list[WorkshopCost] = []
        for offset in range(24):
            year, month = _month_reference(offset)
            costs.append(
                WorkshopCost(
                    workshop=workshop,
                    year=year,
                    month=month,
                    mechanic_quantity=5,
                    work_days_per_month=22,
                    productivity_average=Decimal("0.65"),
                    gross_revenue_target=Decimal("150000.00"),
                    working_hours_per_month=Decimal("572.00"),
                    minimum_hourly_cost=Decimal("80.00"),
                    hourly_cost_value=Decimal("120.00"),
                    profitability_multiplier=Decimal("1.50"),
                )
            )
        WorkshopCost.objects.bulk_create(costs)
        work_days: list[WorkshopCostWorkDay] = []
        for cost in costs:
            last_day = calendar.monthrange(cost.year, cost.month)[1]
            business_dates = [date(cost.year, cost.month, day) for day in range(1, last_day + 1) if date(cost.year, cost.month, day).weekday() < 5][:22]
            work_days.extend(WorkshopCostWorkDay(workshop_cost=cost, date=value) for value in business_dates)
        WorkshopCostWorkDay.objects.bulk_create(work_days, batch_size=1_000)
        return costs
