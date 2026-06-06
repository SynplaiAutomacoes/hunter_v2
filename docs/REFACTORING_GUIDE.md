# Hunter V2 — Architectural Refactoring Guide

> **Goal**: Systematically evolve the monolith into a DDD-oriented, SOLID-compliant, Object-Calisthenic codebase with strict typing.
> **Strategy**: Refactor bottom-up — start with leaf dependencies (core, catalog, customer), finish with Budget/WorkOrder.
> **Language**: English for classes, interfaces, methods, types. Portuguese only for user-facing UI strings.

---

## Table of Contents

1. [Target Directory Structure](#1-target-directory-structure-per-app)
2. [DDD — Strategic Design](#2-ddd--strategic-design)
3. [DDD — Tactical Design](#3-ddd--tactical-design)
4. [SOLID Principles](#4-solid-principles)
5. [Object Calisthenics](#5-object-calisthenics)
6. [Strict Typing](#6-strict-typing)
7. [Repository Pattern](#7-repository-pattern)
8. [Application Layer (Use Cases)](#8-application-layer-use-cases)
9. [Refactoring Sequence](#9-refactoring-sequence-phase-details)
10. [Testing Strategy](#10-testing-strategy)
11. [Migration Strategy](#11-migration-strategy-no-big-bang)
12. [Non-Goals](#12-non-goals-out-of-scope-for-now)
13. [Key Constraints](#13-key-constraints-for-the-ai)

---

## 1. Target Directory Structure (per app)

Every app must follow this template after refactoring:

```
apps/<domain>/
├── domain/
│   ├── __init__.py
│   ├── entities/                    # Aggregate roots & entities, with django imports
│   │   ├── __init__.py
│   │   └── <entity>.py
│   ├── value_objects.py             # Small immutable types
│   ├── events.py                    # Domain events dataclasses
│   ├── services/                    # Domain services (pure business rules)
│   │   ├── __init__.py
│   │   └── <service>.py
├── application/                     # Use cases / application services
│   ├── __init__.py
│   └── use_cases/
│       ├── __init__.py
│       └── <use_case>.py
├── infrastructure/                  # Django coupling lives here
│   ├── __init__.py
│   ├── repositories/               # Concrete repository implementations (use this like a default, without a abstration)
│   │   ├── __init__.py
│   │   └── <repository>.py
│   ├── forms/
│   │   ├── __init__.py
│   │   └── <form>.py
│   └── migrations/
├── presentation/                    # Django views & templates
│   ├── __init__.py
│   ├── views/
│   │   ├── __init__.py
│   │   └── <view>.py
│   ├── templates/
│   │   └── <domain>/
│   └── urls.py
└── apps.py
```

**Exception**: Apps with genuine simplicity (e.g., `sources`, `suppliers`) may keep a flat structure temporarily, but must still separate domain from infrastructure.

---

## 2. DDD — Strategic Design

### 2.1 Bounded Contexts

| Bounded Context          | Apps            | Core Domain? | Relationship                               |
|--------------------------|-----------------|--------------|--------------------------------------------|
| **Workshop Management**  | `workshops`     | Supporting   | Defines multi-tenant boundaries            |
| **Catalog**              | `catalog`       | Supporting   | Products, services, kits as reference data |
| **Customer Management**  | `customer`      | Supporting   | Customers & vehicles                       |
| **Budgeting**            | `budget`        | **Core**     | Quoting & pricing — primary complexity     |
| **Work Order Execution** | `workorder`     | **Core**     | Service execution, payment                 |
| **Inventory**            | `stock`         | Supporting   | Stock tracking for products                |
| **Financial/Tax**        | `finance`       | Supporting   | NF-e/NFS-e, DRE, payment methods           |
| **Collaborators**        | `collaborators` | Supporting   | Payroll, commissions                       |
| **IAM**                  | `iam`           | Generic      | Roles & permissions                        |
| **Communications**       | `messaging`     | Generic      | WhatsApp templates                         |
| **Scheduling**           | `scheduling`    | Generic      | Appointments                               |

### 2.2 Aggregate Roots

| Aggregate Root | Context   | Key Rules                                                  |
|----------------|-----------|------------------------------------------------------------|
| `Workshop`     | Workshops | Owns all data. No other aggregate crosses workshops.       |
| `Budget`       | Budgeting | Status state machine. Pricing snapshot frozen on approval. |
| `WorkOrder`    | WorkOrder | Status transitions. Payment methods. Links to Budget.      |
| `Customer`     | Customer  | Owns vehicles. Shared across contexts (reference only).    |
| `StockProduct` | Inventory | Quantity can only change via `StockMovement`.              |

### 2.3 Ubiquitous Language (Key Terms)

| Term                   | Meaning                                                     | Covers              |
|------------------------|-------------------------------------------------------------|---------------------|
| `Budget`               | A quotation/proposal for vehicle repair                     | `apps/budget/`      |
| `WorkOrder`            | The actual service execution order                          | `apps/workorder/`   |
| `Item`                 | A line entry (product, service, or kit) in Budget/WorkOrder | Shared concept      |
| `Kit`                  | A bundle of products + services sold together               | `catalog`           |
| `PricingSnapshot`      | Frozen pricing data at time of calculation                  | Shared value object |
| `FrozenPricingContext` | Frozen workshop costs at calculation time                   | Shared value object |
| `Collaborator`         | A workshop employee who performs work                       | `collaborators`     |
| `FinancialMovement`    | Any money-in/money-out event                                | `finance`           |
| `Checklist`            | An inspection checklist template                            | `checklist`         |

**Rule**: Never use two words for the same concept. `Orcamento` → `Budget`, `Ordem de Servico` → `WorkOrder`, `Produto` → `Product`.

---

## 3. DDD — Tactical Design

### 3.1 Value Objects

All primitive wrappers must be:
- `@dataclass(frozen=True, slots=True)`
- Self-validating (raise `ValueError` on construction)
- Immutable
- No Django ORM dependencies

**Catalog of required Value Objects:**

```python
# core/domain/value_objects.py

@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "BRL"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Money cannot be negative")

    def __add__(self, other: Money) -> Money: ...
    def __sub__(self, other: Money) -> Money: ...
    def __mul__(self, factor: Decimal) -> Money: ...


@dataclass(frozen=True, slots=True)
class Percentage:
    value: Decimal  # 0.10 = 10%

    def apply_to(self, amount: Money) -> Money: ...


@dataclass(frozen=True, slots=True)
class CPF:
    number: str

    def __post_init__(self) -> None:
        if not self._is_valid():
            raise ValueError(f"Invalid CPF: {self.number}")

    def _is_valid(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class CNPJ:
    number: str

    def __post_init__(self) -> None:
        if not self._is_valid():
            raise ValueError(f"Invalid CNPJ: {self.number}")

    def _is_valid(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class HoursDuration:
    hours: Decimal

    def to_timedelta(self) -> timedelta: ...


@dataclass(frozen=True, slots=True)
class NCM:
    code: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) != 8:
            raise ValueError(f"Invalid NCM: {self.code}")


@dataclass(frozen=True, slots=True)
class Plate:
    value: str

    def __post_init__(self) -> None:
        # Mercosul or old format
        if not re.match(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$', self.value.upper()):
            raise ValueError(f"Invalid plate: {self.value}")
```

**Before:**
```python
# budget/models.py line 100+
discount_value = MoneyField(...)
discount_percentage = models.DecimalField(...)
# Calculating discounts everywhere with Decimal arithmetic
```

**After:**
```python
# domain/value_objects.py
@dataclass(frozen=True, slots=True)
class Discount:
    value: Money
    percentage: Percentage

    def apply(self, total: Money) -> Money:
        from_percentage = self.percentage.apply_to(total)
        return max(total - self.value - from_percentage, Money(0))
```

### 3.2 Entities

Entities have identity (`id`), can mutate over time, and are compared by identity rather than value.

**Before:**
```python
# budget/models.py — 1600-line GOD class
class Budget(TimeStampedModel):
    status = ...
    discount_value = ...
    # plus pricing, approval, signature, display properties...
```

**After:**
```python
# budget/domain/entities/budget.py
@dataclass
class Budget:
    id: int | None
    workshop_id: int
    customer_id: int
    vehicle_id: int | None
    status: BudgetStatus
    items: ItemCollection
    discount: Discount
    pricing_snapshot: PricingSnapshot | None
    type: BudgetType

    def can_approve(self) -> bool:
        return self.status == BudgetStatus.WAITING_APPROVAL

    def approve(self) -> None:
        if not self.can_approve():
            raise BudgetDomainError("Budget cannot be approved in current status")
        self.status = BudgetStatus.APPROVED
        self.pricing_snapshot = self.freeze_pricing()

    def freeze_pricing(self) -> PricingSnapshot: ...
```

### 3.3 Domain Events

```python
# budget/domain/events.py
@dataclass(frozen=True, slots=True)
class BudgetApproved:
    budget_id: int
    approved_at: datetime
    approved_by: int | None


@dataclass(frozen=True, slots=True)
class BudgetSentForSignature:
    budget_id: int
    external_id: str


@dataclass(frozen=True, slots=True)
class ItemAdded:
    budget_id: int
    item: Item
```

**Usage**: Events are raised by domain services, stored in memory during the transaction, and dispatched by the application layer after commit.

### 3.4 Domain Services

Pure business logic that doesn't fit on an entity.

```python
# budget/domain/services/pricing_service.py
class PricingService:
    def calculate(
        self,
        items: ItemCollection,
        labor_context: LaborCostContext,
        discount: Discount,
        slider: int,
    ) -> PricingSnapshot: ...


# catalog/domain/services/kit_service.py
class KitAssemblyService:
    def calculate_kit_price(self, kit: Kit, quantity: int) -> Money: ...
    def get_kit_components(self, kit: Kit) -> list[Component]: ...
```

**Before:**
```python
# budget/models.py — calculate_pricing_methods lives inside the Model
class Budget(TimeStampedModel):
    def calculate_pricing_methods(self) -> dict:
        # 150+ lines of pricing logic mixed with ORM
```

**After:**
```python
# Pure domain service, testable without Django
class PricingService:
    def calculate_methods(
        self,
        items: ItemCollection,
        context: FrozenPricingContext,
        discount: Discount,
    ) -> PricingCalculationResult: ...
```

---

## 4. SOLID Principles

### 4.1 Single Responsibility Principle

**Every class has exactly one reason to change.**

| Current File                                  | Violation                                               | Solution                                 |
|-----------------------------------------------|---------------------------------------------------------|------------------------------------------|
| `budget/models.py`                            | Data mapping + pricing + approval + signature + display | Split into 5+ files                      |
| `workorder/models.py`                         | Same as budget                                          | Split into 5+ files                      |
| `core/views.py` (600+ lines)                  | Mixins + dashboard + CEP + favorites                    | Each concern → own module                |
| `budget/views/workflow_views.py` (1213 lines) | All workflow views in one file                          | Each view → own file (like finance does) |

### 4.2 Open/Closed Principle

**Open for extension, closed for modification.**

```python
# domain/services/pricing_strategy.py
class PricingStrategy(Protocol):
    def name(self) -> str: ...
    def calculate(self, items: ItemCollection, context: LaborCostContext) -> PricingResult: ...


class TraditionalPricing(PricingStrategy):
    def calculate(self, items: ItemCollection, context: LaborCostContext) -> PricingResult: ...


class FixedMarginPricing(PricingStrategy):
    def calculate(self, items: ItemCollection, context: LaborCostContext) -> PricingResult: ...


# Add new strategies without touching existing code
```

### 4.3 Liskov Substitution Principle

**Subtypes must be substitutable for their base types.**

Create a common `BillableItem` abstraction shared by BudgetItem and WorkOrderItem:

```python
# domain/entities/item.py
@dataclass(frozen=True, slots=True)
class BillableItem:
    description: str
    quantity: int
    unit_price: Money
    cost_price: Money
    duration: HoursDuration
    kind: ItemKind  # product | service | kit

    @property
    def total_price(self) -> Money:
        return self.unit_price * Decimal(self.quantity)
```

### 4.4 Interface Segregation Principle

**Many specific interfaces > one general-purpose interface.**

```python
# Don't:
class BudgetRepository:
    def save(self, budget: Budget) -> None: ...
    def find_by_id(self, id: int) -> Budget | None: ...
    def find_by_workshop(self, workshop_id: int, filters: QueryFilters) -> list[Budget]: ...
    def find_open_by_customer(self, customer_id: int) -> list[Budget]: ...
    def get_dashboard_metrics(self, workshop_id: int) -> DashboardMetrics: ...
    def get_pending_signatures(self, workshop_id: int) -> list[Budget]: ...

# Do:
class BudgetRepository(Protocol):
    def save(self, budget: Budget) -> None: ...
    def find_by_id(self, id: int) -> Budget | None: ...


class BudgetQueryService(Protocol):
    def find_by_workshop(self, workshop_id: int, filters: QueryFilters) -> list[Budget]: ...
    def get_dashboard_metrics(self, workshop_id: int) -> DashboardMetrics: ...


class SignatureRepository(Protocol):
    def get_pending(self, workshop_id: int) -> list[Budget]: ...
```

### 4.5 Dependency Inversion Principle

**High-level modules should not depend on low-level modules. Both depend on abstractions.**

```python
# Application layer depends on Protocol, not on Django
class ApproveBudgetUseCase:
    def __init__(
        self,
        budget_repo: BudgetRepository,        # Protocol
        workorder_repo: WorkOrderRepository,  # Protocol
        unit_of_work: UnitOfWork,             # Protocol
    ): ...


# Concrete implementations live in infrastructure/
class DjangoBudgetRepository(BudgetRepository):
    def save(self, budget: Budget) -> None:
        # Translate domain Budget → ORM BudgetModel
        ...
```

---

## 5. Object Calisthenics

### 5.1 One Level of Indentation Per Method

**Before:**
```python
# budget/models.py
def _raw_labor_duration(self) -> timedelta:
    total = timedelta(0)
    for item in self._iter_items():                    # level 1
        if (item.service or ...):                      # level 2
            if item.service and item.service.is_third_party:  # level 3
                continue
            total += item.duration * item.quantity
            continue
        if not item.kit:                               # level 2
            continue
        _, service_overrides = ...
        for kit_service in item._iter_kit_services():  # level 2
            if kit_service.service.is_third_party:      # level 3
                continue
            ...
```

**After:**
```python
def _raw_labor_duration(self) -> timedelta:
    return sum(
        self._calculate_item_duration(item)
        for item in self._iter_items()
    )

def _calculate_item_duration(self, item: BudgetItem) -> timedelta:
    if self._is_external_service(item):
        return timedelta()
    if item.service or self._is_local_service_item(item):
        return self._service_duration(item)
    return self._kit_duration(item)
```

### 5.2 Don't Use `else`

Use early returns and guard clauses:

```python
# Bad:
def can_edit(self, user: User) -> bool:
    if self.status in (APPROVED, REJECTED):
        if user.is_account_owner:
            return True
        else:
            return False
    else:
        return True

# Good:
def can_edit(self, user: User) -> bool:
    if self.status not in (APPROVED, REJECTED):
        return True
    return user.is_account_owner
```

### 5.3 Wrap All Primitives

| Primitive                | Value Object    |
|--------------------------|-----------------|
| `str` for CPF/CNPJ       | `CPF`, `CNPJ`   |
| `str` for plate          | `Plate`         |
| `str` for UF             | `State`         |
| `Decimal` for money      | `Money`         |
| `Decimal` for percentage | `Percentage`    |
| `timedelta` for duration | `HoursDuration` |
| `str` for status         | `BudgetStatus`  |
| `str` for phone          | `PhoneNumber`   |
| `float`/`int` for KM     | `Kilometers`    |

### 5.4 First-Class Collections

```python
# domain/entities/item_collection.py
@dataclass(frozen=True, slots=True)
class ItemCollection:
    items: tuple[BillableItem, ...]

    def total_price(self) -> Money: ...
    def total_cost(self) -> Money: ...
    def total_duration(self) -> HoursDuration: ...
    def by_kind(self, kind: ItemKind) -> 'ItemCollection': ...
    def filter_local(self) -> 'ItemCollection': ...

    def __iter__(self): ...
    def __len__(self): ...
```

### 5.5 One Dot Per Line (Law of Demeter)

**Before:**
```python
budget.workshop.address.city
item.product.selling_price.amount
```

**After:**
```python
# Add helper properties to the outer object
budget.workshop_city
item.selling_price  # delegated
```

### 5.6 No Getters/Setters (Tell, Don't Ask)

**Before:**
```python
budget = repo.find(id)
if budget.status == "approved":
    budget.discount_value = Money(0)
    budget.discount_percentage = Decimal("0")
    budget.save()
```

**After:**
```python
budget = repo.find(id)
budget.clear_discount()  # encapsulates the rule
budget.save()
```

---

## 6. Strict Typing

### 6.1 Configuration

Gradually reduce disabled error codes in `pyproject.toml`:

```
# Phase 1 (after core refactor): re-enable these
disable_error_code = [
    "django-manager-missing",
    "import-untyped",
    "no-any-return",
    "no-any-unimported",
    "var-annotated",
]

# Phase 2 (after catalog/customer/collaborators): add back more
# Phase 3 (after budget/workorder): full strict mode
```

### 6.2 Typing Rules

- Every function must have type annotations (arguments + return type)
- Use `| None` instead of `Optional[T]` (already Python 3.11)
- Use `TypedDict` for complex dictionary return types
- Use `@dataclass` with `slots=True` for all DTOs/value objects
- Use `Protocol` for interfaces (repositories, services)
- Use `NewType` for branded types: `BudgetId = NewType("BudgetId", int)`
- Never use `Any` — use proper types or `object` + `isinstance`

**Before:**
```python
def calculate_pricing_methods(self) -> dict:
    ...
    return {
        "total_geral": Money(0),
        "rentabilidade": Money(0),
    }
```

**After:**
```python
class PricingCalculationResult(TypedDict):
    total_amount: Money
    profitability: Money
    labor_cost: Money
    parts_cost: Money
    discount: Money
    method_name: str


def calculate_pricing_methods(self) -> PricingCalculationResult:
    ...
```

---

## 7. Application Layer (Use Cases)

Use cases orchestrate domain services and infrastructure. They are the "transaction scripts" of DDD.

```python
# budget/application/use_cases/approve_budget.py
@dataclass
class ApproveBudgetRequest:
    budget_id: int
    user_id: int


class ApproveBudgetUseCase:
    def __init__(
        self,
        budget_repo: BudgetRepository,
        unit_of_work: UnitOfWork,
        event_dispatcher: EventDispatcher,
    ):
        self.budget_repo = budget_repo
        self.uow = unit_of_work
        self.events = event_dispatcher

    def execute(self, request: ApproveBudgetRequest) -> None:
        with self.uow:
            budget = self.budget_repo.find_by_id(request.budget_id)
            if budget is None:
                raise BudgetNotFoundError(request.budget_id)

            budget.approve()
            self.budget_repo.save(budget)
            self.uow.commit()

        self.events.dispatch(BudgetApproved(
            budget_id=request.budget_id,
            approved_at=datetime.now(),
            approved_by=request.user_id,
        ))
```

---

## 8. Refactoring Sequence (Phase Details)

### Phase 1: Foundation (`core/`)

**Duration**: Start here — everything depends on this

| Task                                                                    | Files                            | DDD/SOLID/Calisthenics                                                  |
|-------------------------------------------------------------------------|----------------------------------|-------------------------------------------------------------------------|
| Create `core/domain/value_objects.py`                                   | New file                         | `Money`, `Percentage`, `HoursDuration`, `CPF`, `CNPJ`, `Plate`, `State` |
| Create `core/domain/events.py`                                          | New file                         | `DomainEvent` base, `EventDispatcher` Protocol                          |
| Create `core/domain/interfaces.py`                                      | New file                         | `UnitOfWork`, `Repository` Protocols                                    |
| Extract dashboard metrics → `core/domain/services/dashboard_service.py` | Move from `core/views.py`        | SRP: view → service                                                     |
| Extract mixins → `core/presentation/mixins.py`                          | Move from `core/views.py`        | SRP                                                                     |
| Add TypedDicts for all dict returns                                     | `core/views.py`, `core/utils.py` | Typing                                                                  |

**Impact**: Budget/WorkOrder import from `core/` — no breaking changes if kept alongside old code.

---

### Phase 2: Catalog

| Task                                                       | Files                         | DDD/SOLID/Calisthenics      |
|------------------------------------------------------------|-------------------------------|-----------------------------|
| Create `catalog/domain/services/pricing_service.py`        | New file                      | Domain Service              |
| Create `catalog/domain/services/kit_service.py`            | New file                      | KitAssemblyService          |
| Create `catalog/domain/value_objects.py`                   | New file                      | `ItemKind`, `UnitOfMeasure` |
| Slim models to ORM-only                                    | `catalog/models/*.py`         | SRP                         |
| Extract `record_product_last_used_price` to domain service | Move from `price_tracking.py` | SRP                         |
| Extract `annotate_product_issues` to domain service        | Move from `product_issues.py` | SRP                         |

**Impact**: Budget imports `Product`, `Service`, `Kit` models — these still exist as thin ORM wrappers.

---

### Phase 3: Customer + Vehicles

| Task                                          | Files                   | DDD/SOLID/Calisthenics                               |
|-----------------------------------------------|-------------------------|------------------------------------------------------|
| Create `customer/domain/value_objects.py`     | New file                | CPF/CNPJ (use from core), VehiclePlate, Engine, Fuel |
| Extract CPF/CNPJ validation logic             | `cpf_cnpj_validator.py` | Wrap primitive                                       |
| Extract `vehicle_engine.py` to value objects  | `vehicle_engine.py`     | Wrap primitive                                       |
| Extract `vehicle_fuel.py` to value objects    | `vehicle_fuel.py`       | Wrap primitive                                       |
| Slim models                                   | `customer/models.py`    | SRP                                                  |

---

### Phase 4: Collaborators

| Task                                                         | Files     | DDD/SOLID/Calisthenics        |
|--------------------------------------------------------------|-----------|-------------------------------|
| Create `collaborators/domain/services/payroll_service.py`    | New file  | Payroll calculation           |
| Create `collaborators/domain/services/commission_service.py` | New file  | Commission calculation        |
| Extract payroll logic from `services.py`                     | Move      | SRP                           |
| Extract commission logic from `services.py`                  | Move      | SRP                           |

---

### Phase 5: Stock

| Task                                                | Files     | DDD/SOLID/Calisthenics            |
|-----------------------------------------------------|-----------|-----------------------------------|
| Create `stock/domain/services/inventory_service.py` | New file  | Stock reservation, reconciliation |
| Create `stock/domain/value_objects.py`              | New file  | StockQuantity, MovementType       |

---

### Phase 6: Workshops

| Task                                                   | Files     | DDD/SOLID/Calisthenics                                                                                         |
|--------------------------------------------------------|-----------|----------------------------------------------------------------------------------------------------------------|
| Create `workshops/domain/services/labor_calculator.py` | New file  | **Shared**: `calculate_mechanic_hour_cost()`, `calculate_labor_duration()` — used by BOTH Budget and WorkOrder |
| Create `workshops/domain/value_objects.py`             | New file  | `LaborCostContext`, `HourlyCost`                                                                               |

**Critical**: This Phase eliminates the duplication between Budget._raw_labor_duration() and WorkOrder._raw_labor_duration(). Both will delegate to `LaborDurationCalculator`.

---

### Phase 7: Finance

Already has the best structure (services/ directory). Needs:
- Domain entities extracted from models
- Value objects for TaxClass, Invoice
- Repository protocol for Webmania integration

---

### Phase 8: Budget (LAST)

| Task                                                 | Files              | DDD/SOLID/Calisthenics                              |
|------------------------------------------------------|--------------------|-----------------------------------------------------|
| Create `budget/domain/value_objects.py`              | New file           | BudgetStatus, SignatureStatus, BudgetType           |
| Create `budget/domain/services/pricing_service.py`   | New file           | PricingService (use catalog and workshops services) |
| Create `budget/domain/services/approval_service.py`  | New file           | Approval rules                                      |
| Create `budget/domain/services/signature_service.py` | New file           | Signature workflow                                  |
| Create `budget/domain/events.py`                     | New file           | BudgetApproved, BudgetSigned, etc.                  |
| Create `budget/application/use_cases/`               | New files          | ApproveBudgetUseCase, etc.                          |
| Create `budget/infrastructure/repositories/`         | New files          | DjangoBudgetRepository                              |
| Slim ORM model                                       | `budget/models.py` | Remove all business logic                           |
| Extract views into single files                      | `budget/views/`    | SRP + < 200 lines each                              |

---

### Phase 9: WorkOrder (LAST)

Same pattern as Budget. After this phase, WorkOrder's `_raw_labor_duration`, `pricing_snapshot`, `calculate_pricing_methods` all delegate to shared domain services.

---

## 9. Non-Goals (Out of Scope for Now)

- **Rewriting templates**: Templates remain as-is. DDD is backend-focused.
- **JS framework migration**: HTMX + vanilla JS stays.
- **Database changes**: Table structure stays. Only organization of Python code changes.
- **API creation**: No REST/GraphQL API. Django-HTTP-only still.
- **Performance optimization**: Not the primary goal (will come naturally with cleaner code).

---

## 10. Key Constraints for the AI

1. **Never mix Django imports in domain/ files.** Domain layer is `import`-free of Django.
2. **Every new file must have type annotations.** No `Any` except in test mocks.
3. **No circular imports.** Domain → Infrastructure → Presentation. Never the reverse.
4. **No `*` imports.** Explicit `__all__` only.
5. **One PR per phase.** Each phase produces working, deployable code.
6. **Signal handlers stay minimal.** They call domain services; they don't contain logic.
