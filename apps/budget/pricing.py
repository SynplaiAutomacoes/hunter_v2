from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from djmoney.money import Money


MONEY_CURRENCY = "BRL"
MONEY_QUANT = Decimal("0.01")
PERCENT_QUANT = Decimal("0.000001")


def zero_money() -> Money:
    return Money(0, MONEY_CURRENCY)


def _quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def money_from_decimal(value: Decimal) -> Money:
    return Money(_quantize_decimal(value), MONEY_CURRENCY)


def _quantize_percentage(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)


def money_div(total: Money, quantity: int) -> Money:
    if quantity <= 0:
        return zero_money()
    return money_from_decimal(total.amount / Decimal(quantity))


def format_duration_display(duration: timedelta) -> str:
    if not duration:
        return "00h 00m"

    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours:02d}h {minutes:02d}m"


@dataclass(slots=True)
class ConsolidatedPricingLine:
    line_id: str
    source_item_id: int | None
    kind: str
    entity_id: int | None
    description: str
    quantity: int
    raw_total: Money
    cost_total: Money
    original_cost_total: Money = field(default_factory=zero_money)
    shipping: Money = field(default_factory=zero_money)
    duration: timedelta = field(default_factory=timedelta)
    code: str = ""
    application: str = ""
    location: str = ""
    is_local: bool = False
    is_customer_supplied: bool = False
    has_direct_source: bool = False
    has_kit_source: bool = False
    third_party: bool = False
    source_object: Any | None = None
    fixed_cost_total: Money = field(default_factory=zero_money)
    adjusted_total: Money = field(default_factory=zero_money)
    stock_quantity: int | None = None
    excess_quantity: int = 0
    has_invalid_ncm: bool = False
    product_issue_messages: tuple[str, ...] = field(default_factory=tuple)
    product_issue_tooltip: str = ""
    has_product_issues: bool = False

    @property
    def id(self) -> int | str:
        if self.source_item_id is not None:
            return self.source_item_id
        return self.line_id

    @property
    def adjusted_unit_price(self) -> Money:
        if self.kind == "product":
            return money_div(self.adjusted_total - self.shipping, self.quantity)
        return money_div(self.adjusted_total, self.quantity)

    @property
    def unit_price(self) -> Money:
        return money_div(self.adjusted_total, self.quantity)

    @property
    def total_price(self) -> Money:
        return self.adjusted_total

    @property
    def product_cost_price(self) -> Money:
        return self.cost_total

    @property
    def service_cost_price(self) -> Money:
        return self.cost_total

    @property
    def profit_value(self) -> Money:
        return self.adjusted_total - self.cost_total

    @property
    def duration_display(self) -> str:
        return format_duration_display(self.duration)

    @property
    def show_kit_duplicate_warning(self) -> bool:
        return self.has_direct_source and self.has_kit_source and not self.is_local

    @property
    def product(self) -> Any:
        if self.kind != "product":
            return None
        if self.source_object is not None:
            return self.source_object
        return SimpleNamespace(code=self.code or "-", name=self.description, description=self.description, application=self.application or "-", location=self.location or "-")

    @property
    def service(self) -> Any:
        if self.kind != "service":
            return None
        if self.source_object is not None:
            return self.source_object
        return SimpleNamespace(name=self.description)


@dataclass(slots=True)
class PricingSnapshot:
    product_lines: list[ConsolidatedPricingLine]
    service_lines: list[ConsolidatedPricingLine]
    total_products_shipping: Money
    total_services_shipping: Money
    total_costs_products_value: Money
    total_products_value: Money
    total_duration: timedelta
    total_third_party_services_cost: Money
    total_third_party_services_selling: Money
    total_costs_services_value: Money
    total_services_value: Money
    total_labor_cost_value: Money
    total_labor_selling_value: Money
    total_labor_by_slider: Money
    total_products_by_slider: Money
    total_services_by_slider: Money
    total_third_party_by_slider: Money
    total_base_value: Money
    resolved_discount_value: Money
    resolved_discount_percentage: Decimal
    total_budget_value: Money


def resolve_discount_fields(
    *,
    total_base_value: Money,
    discount_value: Money | None = None,
    discount_percentage: Decimal | None = None,
) -> tuple[Money, Decimal]:
    total_amount = max(_quantize_decimal(total_base_value.amount), Decimal("0.00"))
    raw_discount_amount = max(
        _quantize_decimal((discount_value.amount if discount_value is not None else Decimal("0.00"))),
        Decimal("0.00"),
    )
    raw_discount_percentage = min(
        max(Decimal(discount_percentage or 0), Decimal("0.00")),
        Decimal("1.00"),
    )
    raw_discount_percentage = _quantize_percentage(raw_discount_percentage)

    if total_amount <= Decimal("0.00"):
        return zero_money(), Decimal("0.00")

    if raw_discount_amount > Decimal("0.00"):
        resolved_discount_amount = min(raw_discount_amount, total_amount)
        resolved_discount_percentage = _quantize_percentage(resolved_discount_amount / total_amount)
        return money_from_decimal(resolved_discount_amount), resolved_discount_percentage

    if raw_discount_percentage > Decimal("0.00"):
        resolved_discount_amount = min(_quantize_decimal(total_amount * raw_discount_percentage), total_amount)
        return money_from_decimal(resolved_discount_amount), raw_discount_percentage

    return zero_money(), Decimal("0.00")


def discount_by_pricing_section(
    *,
    discount_value: Money,
    discount_type: str,
    products_value: Money,
    labor_value: Money,
) -> tuple[Money, Money]:
    """Return the discount shown in the Parts and Labor pricing cards.

    A discount for both categories remains consolidated in the final total,
    as it must not be visually attributed to either card.
    """
    if discount_type == "products":
        return money_from_decimal(min(discount_value.amount, products_value.amount)), zero_money()

    if discount_type == "services":
        return zero_money(), money_from_decimal(min(discount_value.amount, labor_value.amount))

    return zero_money(), zero_money()


@dataclass(slots=True)
class _ProductAggregate:
    key: str
    entity_id: int | None
    description: str
    sort_order: int
    source_item_id: int | None = None
    code: str = ""
    application: str = ""
    location: str = ""
    is_local: bool = False
    is_customer_supplied: bool = False
    source_object: Any | None = None
    direct_description: str = ""
    direct_code: str = ""
    direct_application: str = ""
    direct_location: str = ""
    direct_source_object: Any | None = None
    kit_description: str = ""
    kit_code: str = ""
    kit_application: str = ""
    kit_location: str = ""
    kit_source_object: Any | None = None
    direct_quantity: int = 0
    direct_total: Money = field(default_factory=zero_money)
    direct_cost_total: Money = field(default_factory=zero_money)
    direct_shipping: Money = field(default_factory=zero_money)
    kit_quantity: int = 0
    kit_total: Money = field(default_factory=zero_money)
    kit_cost_total: Money = field(default_factory=zero_money)
    kit_shipping: Money = field(default_factory=zero_money)


@dataclass(slots=True)
class _ServiceAggregate:
    key: str
    entity_id: int | None
    description: str
    sort_order: int
    source_item_id: int | None = None
    is_local: bool = False
    source_object: Any | None = None
    direct_description: str = ""
    direct_source_object: Any | None = None
    kit_description: str = ""
    kit_source_object: Any | None = None
    direct_quantity: int = 0
    direct_raw_total: Money = field(default_factory=zero_money)
    direct_cost_total: Money = field(default_factory=zero_money)
    direct_shipping: Money = field(default_factory=zero_money)
    direct_duration: timedelta = field(default_factory=timedelta)
    kit_quantity: int = 0
    kit_raw_total: Money = field(default_factory=zero_money)
    kit_cost_total: Money = field(default_factory=zero_money)
    kit_shipping: Money = field(default_factory=zero_money)
    kit_fixed_cost_total: Money = field(default_factory=zero_money)
    kit_duration: timedelta = field(default_factory=timedelta)
    third_party: bool = False
    has_direct_source: bool = False
    has_kit_source: bool = False


def _distribute_totals(*, base_values: Iterable[Money], target_total: Money) -> list[Money]:
    bases = [_quantize_decimal(value.amount) for value in base_values]
    if not bases:
        return []

    target = _quantize_decimal(target_total.amount)
    if target <= 0:
        return [zero_money() for _ in bases]

    base_sum = _quantize_decimal(sum(bases, Decimal("0.00")))
    if base_sum <= 0:
        return [zero_money() for _ in bases]

    allocated: list[Decimal] = []
    running_total = Decimal("0.00")
    last_index = len(bases) - 1

    for index, base in enumerate(bases):
        if index == last_index:
            value = _quantize_decimal(target - running_total)
        else:
            value = _quantize_decimal((target * base) / base_sum)
            running_total = _quantize_decimal(running_total + value)
        allocated.append(value)

    residual = _quantize_decimal(target - sum(allocated, Decimal("0.00")))
    if residual and allocated:
        allocated[-1] = _quantize_decimal(allocated[-1] + residual)

    return [money_from_decimal(value) for value in allocated]


def _distribute_money_by_weights(*, weights: Iterable[Decimal], target_total: Money) -> list[Money]:
    normalized_weights = [_quantize_decimal(max(weight, Decimal("0.00"))) for weight in weights]
    if not normalized_weights:
        return []

    target = _quantize_decimal(target_total.amount)
    if target <= 0:
        return [zero_money() for _ in normalized_weights]

    total_weight = _quantize_decimal(sum(normalized_weights, Decimal("0.00")))
    if total_weight <= 0:
        return [zero_money() for _ in normalized_weights]

    allocated: list[Decimal] = []
    running_total = Decimal("0.00")
    last_index = len(normalized_weights) - 1

    for index, weight in enumerate(normalized_weights):
        if index == last_index:
            value = _quantize_decimal(target - running_total)
        else:
            value = _quantize_decimal((target * weight) / total_weight)
            running_total = _quantize_decimal(running_total + value)
        allocated.append(value)

    residual = _quantize_decimal(target - sum(allocated, Decimal("0.00")))
    if residual and allocated:
        allocated[-1] = _quantize_decimal(allocated[-1] + residual)

    return [money_from_decimal(value) for value in allocated]


def _coerce_money(value: Money | None) -> Money:
    return value if value is not None else zero_money()


def _is_better_source(*, candidate_quantity: int, candidate_total: Money, current_quantity: int, current_total: Money) -> bool:
    """Same winner rule used for avulso vs kit and kit vs kit: higher qty, then higher total."""
    if current_quantity <= 0:
        return True
    if candidate_quantity != current_quantity:
        return candidate_quantity > current_quantity
    return candidate_total.amount > current_total.amount


def _timedelta_seconds(duration: timedelta | None) -> int:
    if not duration:
        return 0
    return int(duration.total_seconds())


def _is_better_service_source(
    *,
    candidate_duration: timedelta,
    candidate_total: Money,
    current_duration: timedelta,
    current_total: Money,
) -> bool:
    """Winner for services: higher duration, then higher selling total."""
    current_seconds = _timedelta_seconds(current_duration)
    candidate_seconds = _timedelta_seconds(candidate_duration)
    if current_seconds <= 0 and current_total.amount <= 0:
        return True
    if candidate_seconds != current_seconds:
        return candidate_seconds > current_seconds
    return candidate_total.amount > current_total.amount


def build_pricing_snapshot(
    *,
    items: Iterable[Any],
    slider: int,
    discount_value: Money,
    discount_percentage: Decimal | None = None,
    labor_cost_value: Money | None = None,
    labor_selling_value_override: Money | None = None,
    is_local_product_item: Callable[[Any], bool] | None = None,
    is_local_service_item: Callable[[Any], bool] | None = None,
    include_benefit_items: bool = False,
) -> PricingSnapshot:
    local_product_check = is_local_product_item or (lambda _item: False)
    local_service_check = is_local_service_item or (lambda _item: False)

    product_aggregates: dict[str, _ProductAggregate] = {}
    service_aggregates: dict[str, _ServiceAggregate] = {}

    for sort_order, item in enumerate(items):
        item_quantity = int(getattr(item, "quantity", 0) or 0)
        if item_quantity <= 0:
            continue

        if not include_benefit_items and getattr(item, "item_benefit_type", "normal") not in ("normal", ""):
            continue

        item_id = getattr(item, "id", None)
        product_id = getattr(item, "product_id", None)
        service_id = getattr(item, "service_id", None)
        kit_id = getattr(item, "kit_id", None)

        if product_id is not None or local_product_check(item):
            key = f"product-{product_id}" if product_id is not None else f"local-product-{item_id or sort_order}"
            aggregate = product_aggregates.get(key)
            if aggregate is None:
                product = getattr(item, "product", None)
                aggregate = _ProductAggregate(
                    key=key,
                    entity_id=product_id,
                    description=str(getattr(item, "description", "") or getattr(product, "name", "Produto")),
                    sort_order=sort_order,
                    source_item_id=item_id if product_id is None else None,
                    code=str(getattr(product, "code", "") or ""),
                    application=str(getattr(product, "application", "") or ""),
                    location=str(getattr(product, "location", "") or ""),
                    is_local=bool(product_id is None),
                    source_object=product,
                    direct_description=str(getattr(item, "description", "") or getattr(product, "name", "Produto")),
                    direct_code=str(getattr(product, "code", "") or ""),
                    direct_application=str(getattr(product, "application", "") or ""),
                    direct_location=str(getattr(product, "location", "") or ""),
                    direct_source_object=product,
                )
                product_aggregates[key] = aggregate

            effective_selling = _coerce_money(getattr(item, "product_selling_price", None))
            direct_total = (effective_selling * item_quantity) + _coerce_money(getattr(item, "shipping", None))
            direct_cost_total = _coerce_money(getattr(item, "product_cost_price", None)) * item_quantity
            direct_shipping = _coerce_money(getattr(item, "shipping", None))
            should_replace_direct = product_id is not None and _is_better_source(
                candidate_quantity=item_quantity,
                candidate_total=direct_total,
                current_quantity=aggregate.direct_quantity,
                current_total=aggregate.direct_total,
            )
            if product_id is None:
                aggregate.direct_quantity += item_quantity
                aggregate.direct_total += direct_total
                aggregate.direct_cost_total += direct_cost_total
                aggregate.direct_shipping += direct_shipping
            elif should_replace_direct:
                aggregate.direct_quantity = item_quantity
                aggregate.direct_total = direct_total
                aggregate.direct_cost_total = direct_cost_total
                aggregate.direct_shipping = direct_shipping
                aggregate.direct_description = str(getattr(item, "description", "") or getattr(getattr(item, "product", None), "name", "Produto"))
                aggregate.direct_code = str(getattr(getattr(item, "product", None), "code", "") or "")
                aggregate.direct_application = str(getattr(getattr(item, "product", None), "application", "") or "")
                aggregate.direct_location = str(getattr(getattr(item, "product", None), "location", "") or "")
                aggregate.direct_source_object = getattr(item, "product", None)
            aggregate.is_customer_supplied = aggregate.is_customer_supplied or bool(getattr(item, "is_customer_supplied", False))
            continue

        if service_id is not None or local_service_check(item):
            key = f"service-{service_id}" if service_id is not None else f"local-service-{item_id or sort_order}"
            service_aggregate = service_aggregates.get(key)
            if service_aggregate is None:
                service = getattr(item, "service", None)
                service_aggregate = _ServiceAggregate(
                    key=key,
                    entity_id=service_id,
                    description=str(getattr(item, "description", "") or getattr(service, "name", "Servico")),
                    sort_order=sort_order,
                    source_item_id=item_id if service_id is None else None,
                    is_local=bool(service_id is None),
                    source_object=service,
                    direct_description=str(getattr(item, "description", "") or getattr(service, "name", "Servico")),
                    direct_source_object=service,
                    third_party=bool(getattr(service, "is_third_party", False)),
                )
                service_aggregates[key] = service_aggregate

            effective_selling = _coerce_money(getattr(item, "service_selling_price", None))
            direct_raw_total = effective_selling * item_quantity
            direct_cost_total = _coerce_money(getattr(item, "service_cost_price", None)) * item_quantity
            direct_shipping = _coerce_money(getattr(item, "service_shipping", None)) * item_quantity
            item_duration = getattr(item, "duration", None)
            direct_duration = (item_duration * item_quantity) if item_duration else timedelta()
            should_replace_direct = service_id is not None and _is_better_service_source(
                candidate_duration=direct_duration,
                candidate_total=direct_raw_total,
                current_duration=service_aggregate.direct_duration,
                current_total=service_aggregate.direct_raw_total,
            )
            if service_id is None:
                service_aggregate.direct_quantity += item_quantity
                service_aggregate.direct_raw_total += direct_raw_total
                service_aggregate.direct_cost_total += direct_cost_total
                service_aggregate.direct_shipping += direct_shipping
                service_aggregate.direct_duration += direct_duration
            elif should_replace_direct:
                service_aggregate.direct_quantity = item_quantity
                service_aggregate.direct_raw_total = direct_raw_total
                service_aggregate.direct_cost_total = direct_cost_total
                service_aggregate.direct_shipping = direct_shipping
                service_aggregate.direct_duration = direct_duration
                service_aggregate.direct_description = str(getattr(item, "description", "") or getattr(getattr(item, "service", None), "name", "Servico"))
                service_aggregate.direct_source_object = getattr(item, "service", None)
            service_aggregate.has_direct_source = True
            continue

        if kit_id is None:
            continue

        for override in item._iter_frozen_kit_product_overrides():
            product = override.product
            per_kit_quantity = override.quantity
            if per_kit_quantity <= 0:
                continue

            consolidated_quantity = per_kit_quantity * item_quantity
            if consolidated_quantity <= 0:
                continue

            key = f"product-{override.product_id}"
            aggregate = product_aggregates.get(key)
            if aggregate is None:
                aggregate = _ProductAggregate(
                    key=key,
                    entity_id=override.product_id,
                    description=str(getattr(product, "name", "Produto") or "Produto"),
                    sort_order=sort_order,
                    code=str(getattr(product, "code", "") or ""),
                    application=str(getattr(product, "application", "") or ""),
                    location=str(getattr(product, "location", "") or ""),
                    source_object=product,
                )
                product_aggregates[key] = aggregate

            shipping = override.shipping * item_quantity
            unit_price = override.product_selling_price
            unit_cost = override.product_cost_price
            kit_total = (unit_price * consolidated_quantity) + shipping

            if _is_better_source(
                candidate_quantity=consolidated_quantity,
                candidate_total=kit_total,
                current_quantity=aggregate.kit_quantity,
                current_total=aggregate.kit_total,
            ):
                aggregate.kit_quantity = consolidated_quantity
                aggregate.kit_total = kit_total
                aggregate.kit_cost_total = unit_cost * consolidated_quantity
                aggregate.kit_shipping = shipping
                aggregate.kit_code = str(getattr(product, "code", "") or "")
                aggregate.kit_application = str(getattr(product, "application", "") or "")
                aggregate.kit_location = str(getattr(product, "location", "") or "")
                aggregate.kit_source_object = product
                aggregate.kit_description = str(getattr(product, "name", aggregate.description) or aggregate.description)

        for override in item._iter_frozen_kit_service_overrides():
            service = override.service
            per_kit_quantity = override.quantity
            if per_kit_quantity <= 0:
                continue

            consolidated_quantity = per_kit_quantity * item_quantity
            if consolidated_quantity <= 0:
                continue

            key = f"service-{override.service_id}"
            service_aggregate = service_aggregates.get(key)
            if service_aggregate is None:
                service_aggregate = _ServiceAggregate(
                    key=key,
                    entity_id=override.service_id,
                    description=str(getattr(service, "name", "Servico") or "Servico"),
                    sort_order=sort_order,
                    source_object=service,
                    third_party=bool(getattr(service, "is_third_party", False)),
                )
                service_aggregates[key] = service_aggregate

            unit_price = override.service_selling_price
            unit_cost = override.service_cost_price
            kit_raw_total = unit_price * consolidated_quantity
            fixed_cost_total = unit_cost * consolidated_quantity
            service_duration = timedelta(0)
            if override.duration:
                service_duration = override.duration * consolidated_quantity

            if _is_better_service_source(
                candidate_duration=service_duration,
                candidate_total=kit_raw_total,
                current_duration=service_aggregate.kit_duration,
                current_total=service_aggregate.kit_raw_total,
            ):
                service_aggregate.kit_quantity = consolidated_quantity
                service_aggregate.kit_raw_total = kit_raw_total
                service_aggregate.kit_cost_total = unit_cost * consolidated_quantity
                service_aggregate.kit_fixed_cost_total = fixed_cost_total
                service_aggregate.kit_duration = service_duration
                service_aggregate.kit_description = str(getattr(service, "name", service_aggregate.description) or service_aggregate.description)
                service_aggregate.kit_source_object = service
                service_aggregate.third_party = bool(getattr(service, "is_third_party", False))

            service_aggregate.has_kit_source = True

    product_lines: list[ConsolidatedPricingLine] = []
    for product_aggregate in sorted(product_aggregates.values(), key=lambda value: (value.sort_order, value.description.lower())):
        has_direct_source = product_aggregate.direct_quantity > 0
        has_kit_source = product_aggregate.kit_quantity > 0

        if has_direct_source and has_kit_source:
            use_direct_source = _is_better_source(
                candidate_quantity=product_aggregate.direct_quantity,
                candidate_total=product_aggregate.direct_total,
                current_quantity=product_aggregate.kit_quantity,
                current_total=product_aggregate.kit_total,
            )

            if use_direct_source:
                quantity = product_aggregate.direct_quantity
                raw_total = product_aggregate.direct_total
                cost_total = product_aggregate.direct_cost_total
                shipping = product_aggregate.direct_shipping
                description = product_aggregate.direct_description or product_aggregate.description
                code = product_aggregate.direct_code
                application = product_aggregate.direct_application
                location = product_aggregate.direct_location
                source_object = product_aggregate.direct_source_object
            else:
                quantity = product_aggregate.kit_quantity
                raw_total = product_aggregate.kit_total
                cost_total = product_aggregate.kit_cost_total
                shipping = product_aggregate.kit_shipping
                description = product_aggregate.kit_description or product_aggregate.description
                code = product_aggregate.kit_code
                application = product_aggregate.kit_application
                location = product_aggregate.kit_location
                source_object = product_aggregate.kit_source_object
        else:
            quantity = product_aggregate.direct_quantity + product_aggregate.kit_quantity
            raw_total = product_aggregate.direct_total + product_aggregate.kit_total
            cost_total = product_aggregate.direct_cost_total + product_aggregate.kit_cost_total
            shipping = product_aggregate.direct_shipping + product_aggregate.kit_shipping
            description = product_aggregate.direct_description or product_aggregate.kit_description or product_aggregate.description
            code = product_aggregate.direct_code or product_aggregate.kit_code
            application = product_aggregate.direct_application or product_aggregate.kit_application
            location = product_aggregate.direct_location or product_aggregate.kit_location
            source_object = product_aggregate.direct_source_object or product_aggregate.kit_source_object

        if quantity <= 0 and raw_total.amount <= 0:
            continue

        product_lines.append(
            ConsolidatedPricingLine(
                line_id=product_aggregate.key,
                source_item_id=product_aggregate.source_item_id,
                kind="product",
                entity_id=product_aggregate.entity_id,
                description=description,
                quantity=quantity,
                raw_total=raw_total,
                cost_total=cost_total,
                shipping=shipping,
                code=code,
                application=application,
                location=location,
                is_local=product_aggregate.is_local,
                is_customer_supplied=product_aggregate.is_customer_supplied,
                has_direct_source=has_direct_source,
                has_kit_source=has_kit_source,
                source_object=source_object,
            )
        )

    chargeable_product_lines = [line for line in product_lines if not line.is_customer_supplied]
    customer_supplied_product_lines = [line for line in product_lines if line.is_customer_supplied]

    service_lines: list[ConsolidatedPricingLine] = []
    for service_aggregate in sorted(service_aggregates.values(), key=lambda value: (value.sort_order, value.description.lower())):
        has_direct_source = service_aggregate.direct_quantity > 0
        has_kit_source = service_aggregate.kit_quantity > 0

        if has_direct_source and has_kit_source:
            use_direct_source = _is_better_service_source(
                candidate_duration=service_aggregate.direct_duration,
                candidate_total=service_aggregate.direct_raw_total,
                current_duration=service_aggregate.kit_duration,
                current_total=service_aggregate.kit_raw_total,
            )

            if use_direct_source:
                quantity = service_aggregate.direct_quantity
                raw_total = service_aggregate.direct_raw_total
                cost_total = service_aggregate.direct_cost_total
                shipping = service_aggregate.direct_shipping
                duration = service_aggregate.direct_duration
                fixed_cost_total = zero_money()
                description = service_aggregate.direct_description or service_aggregate.description
                source_object = service_aggregate.direct_source_object
            else:
                quantity = service_aggregate.kit_quantity
                raw_total = service_aggregate.kit_raw_total
                cost_total = service_aggregate.kit_cost_total
                shipping = service_aggregate.kit_shipping
                duration = service_aggregate.kit_duration
                fixed_cost_total = service_aggregate.kit_fixed_cost_total
                description = service_aggregate.kit_description or service_aggregate.description
                source_object = service_aggregate.kit_source_object
        else:
            quantity = service_aggregate.direct_quantity + service_aggregate.kit_quantity
            raw_total = service_aggregate.direct_raw_total + service_aggregate.kit_raw_total
            cost_total = service_aggregate.direct_cost_total + service_aggregate.kit_cost_total
            shipping = service_aggregate.direct_shipping + service_aggregate.kit_shipping
            duration = service_aggregate.direct_duration + service_aggregate.kit_duration
            fixed_cost_total = service_aggregate.kit_fixed_cost_total
            description = service_aggregate.direct_description or service_aggregate.kit_description or service_aggregate.description
            source_object = service_aggregate.direct_source_object or service_aggregate.kit_source_object

        if quantity <= 0 and raw_total.amount <= 0:
            continue

        service_lines.append(
            ConsolidatedPricingLine(
                line_id=service_aggregate.key,
                source_item_id=service_aggregate.source_item_id,
                kind="service",
                entity_id=service_aggregate.entity_id,
                description=description,
                quantity=quantity,
                raw_total=raw_total,
                cost_total=cost_total,
                original_cost_total=cost_total,
                shipping=shipping,
                duration=duration,
                is_local=service_aggregate.is_local,
                has_direct_source=has_direct_source,
                has_kit_source=has_kit_source,
                third_party=service_aggregate.third_party,
                source_object=source_object,
                fixed_cost_total=fixed_cost_total,
            )
        )

    total_products_shipping = sum((line.shipping for line in chargeable_product_lines), zero_money())
    total_services_shipping = sum((line.shipping for line in service_lines), zero_money())
    total_costs_products_value = sum((line.cost_total for line in chargeable_product_lines), zero_money())
    total_products_value = sum((line.raw_total for line in chargeable_product_lines), zero_money())
    labor_service_lines = [line for line in service_lines if not line.third_party]
    third_party_service_lines = [line for line in service_lines if line.third_party]
    total_labor_services_shipping = sum((line.shipping for line in labor_service_lines), zero_money())
    total_duration = sum((line.duration for line in service_lines), timedelta())
    total_third_party_services_selling = sum((line.raw_total + line.shipping for line in third_party_service_lines), zero_money())
    total_services_value = sum((line.raw_total + line.shipping for line in service_lines), zero_money())

    total_third_party_services_cost = sum((line.cost_total for line in third_party_service_lines), zero_money())
    total_labor_selling_value = labor_selling_value_override if labor_selling_value_override is not None else sum((line.raw_total for line in labor_service_lines), zero_money())
    # Hunter labor cost (mechanic hour * duration). This is the slider floor shown in step 5.
    # Never fall back to sum(service_cost_price) for the floor — those can equal selling and block transfer.
    hunter_labor_cost_value = labor_cost_value if labor_cost_value is not None and labor_cost_value.amount > 0 else zero_money()
    resolved_labor_cost_value = hunter_labor_cost_value if hunter_labor_cost_value.amount > 0 else sum((line.cost_total for line in service_lines if not line.third_party), zero_money())
    fixed_labor_service_lines = [line for line in labor_service_lines if line.fixed_cost_total.amount > 0]
    variable_labor_service_lines = [line for line in labor_service_lines if line.fixed_cost_total.amount <= 0]
    preserved_labor_cost_value = sum((line.fixed_cost_total for line in fixed_labor_service_lines), zero_money())

    # Kit fixed costs must not raise the labor floor above the Hunter mechanic cost.
    if preserved_labor_cost_value.amount > hunter_labor_cost_value.amount and hunter_labor_cost_value.amount > 0:
        fixed_labor_service_lines = []
        variable_labor_service_lines = list(labor_service_lines)
        preserved_labor_cost_value = zero_money()

    for line in fixed_labor_service_lines:
        line.cost_total = line.fixed_cost_total

    labor_cost_allocation_target = hunter_labor_cost_value if hunter_labor_cost_value.amount > 0 else resolved_labor_cost_value
    remaining_labor_cost_value = max(labor_cost_allocation_target - preserved_labor_cost_value, zero_money())
    labor_cost_weights = [Decimal(int(line.duration.total_seconds())) for line in variable_labor_service_lines]
    if not any(weight > 0 for weight in labor_cost_weights):
        labor_cost_weights = [line.raw_total.amount for line in variable_labor_service_lines]
    if not any(weight > 0 for weight in labor_cost_weights):
        labor_cost_weights = [Decimal(max(line.quantity, 0)) for line in variable_labor_service_lines]

    for line, allocated_cost in zip(
        variable_labor_service_lines,
        _distribute_money_by_weights(weights=labor_cost_weights, target_total=remaining_labor_cost_value),
        strict=False,
    ):
        line.cost_total = allocated_cost

    effective_labor_cost_value = labor_cost_allocation_target
    total_costs_services_value = total_third_party_services_cost + effective_labor_cost_value

    slider_decimal = Decimal(int(slider or 0)) / Decimal(100)
    total_products_by_slider = total_products_value
    total_labor_by_slider = total_labor_selling_value
    total_third_party_shipping = sum((line.shipping for line in third_party_service_lines), zero_money())
    total_third_party_by_slider = total_third_party_services_selling

    if slider < 0:
        # 100% pecas: move labor + third-party profit to products; MO floor = Hunter cost (+ freight in display).
        available_labor = max(total_labor_selling_value - hunter_labor_cost_value, zero_money())
        third_party_floor = total_third_party_services_cost + total_third_party_shipping
        available_third_party = max(total_third_party_services_selling - third_party_floor, zero_money())
        transfer_labor = available_labor * abs(slider_decimal)
        transfer_third_party = available_third_party * abs(slider_decimal)
        total_products_by_slider = total_products_value + transfer_labor + transfer_third_party
        total_labor_by_slider = total_labor_selling_value - transfer_labor
        total_third_party_by_slider = total_third_party_services_selling - transfer_third_party
    elif slider > 0:
        available_products = max(total_products_value - (total_costs_products_value + total_products_shipping), zero_money())
        transfer = available_products * slider_decimal
        total_products_by_slider = total_products_value - transfer
        total_labor_by_slider = total_labor_selling_value + transfer

    total_services_by_slider = total_third_party_by_slider + total_labor_by_slider + total_labor_services_shipping

    for line, adjusted_subtotal in zip(
        chargeable_product_lines,
        _distribute_totals(
            base_values=[line.raw_total - line.shipping for line in chargeable_product_lines],
            target_total=total_products_by_slider - total_products_shipping,
        ),
        strict=False,
    ):
        line.adjusted_total = adjusted_subtotal + line.shipping

    for line in customer_supplied_product_lines:
        line.adjusted_total = line.raw_total

    for line, adjusted_total in zip(
        third_party_service_lines,
        _distribute_totals(
            base_values=[line.raw_total + line.shipping for line in third_party_service_lines],
            target_total=total_third_party_by_slider,
        ),
        strict=False,
    ):
        line.adjusted_total = adjusted_total

    remaining_labor_profit = max(total_labor_by_slider - effective_labor_cost_value, zero_money())
    labor_profit_weights = [max(line.raw_total.amount - line.cost_total.amount, Decimal("0.00")) for line in labor_service_lines]
    if not any(weight > 0 for weight in labor_profit_weights):
        labor_profit_weights = [line.raw_total.amount for line in labor_service_lines]
    if not any(weight > 0 for weight in labor_profit_weights):
        labor_profit_weights = [Decimal(max(line.quantity, 0)) for line in labor_service_lines]

    for line, adjusted_total in zip(
        labor_service_lines,
        _distribute_money_by_weights(weights=labor_profit_weights, target_total=remaining_labor_profit),
        strict=False,
    ):
        line.adjusted_total = line.cost_total + adjusted_total + line.shipping

    total_base_value = total_products_by_slider + total_services_by_slider

    resolved_discount_value, resolved_discount_percentage = resolve_discount_fields(
        total_base_value=total_base_value,
        discount_value=discount_value,
        discount_percentage=discount_percentage,
    )
    total_budget_value = total_base_value - resolved_discount_value

    return PricingSnapshot(
        product_lines=product_lines,
        service_lines=service_lines,
        total_products_shipping=total_products_shipping,
        total_services_shipping=total_services_shipping,
        total_costs_products_value=total_costs_products_value,
        total_products_value=total_products_value,
        total_duration=total_duration,
        total_third_party_services_cost=total_third_party_services_cost,
        total_third_party_services_selling=total_third_party_services_selling,
        total_costs_services_value=total_costs_services_value,
        total_services_value=total_services_value,
        total_labor_cost_value=effective_labor_cost_value,
        total_labor_selling_value=total_labor_selling_value,
        total_labor_by_slider=total_labor_by_slider,
        total_products_by_slider=total_products_by_slider,
        total_services_by_slider=total_services_by_slider,
        total_third_party_by_slider=total_third_party_by_slider,
        total_base_value=total_base_value,
        resolved_discount_value=resolved_discount_value,
        resolved_discount_percentage=resolved_discount_percentage,
        total_budget_value=total_budget_value,
    )
