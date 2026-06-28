from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


LogicalOperator = Literal["all", "any"]

RuleType = Literal[
    "birthday",
    "last_visit",
    "budget_status",
    "workorder_status",
    "customer_field",
    "created_since",
    "budget_value",
]

BirthdayOperator = Literal["is_today", "is_this_month"]
DaysAgoOperator = Literal["days_ago_gte", "days_ago_lte"]
InOperator = Literal["in"]
FieldOperator = Literal["equals", "in", "icontains"]
ComparisonOperator = Literal["gte", "lte"]

SegmentOperator = BirthdayOperator | DaysAgoOperator | InOperator | FieldOperator | ComparisonOperator


@dataclass(frozen=True, slots=True)
class SegmentRule:
    rule_type: RuleType
    operator: SegmentOperator
    value: Any = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class FilterCriteria:
    logical_operator: LogicalOperator
    rules: tuple[SegmentRule, ...]

    @classmethod
    def from_dict(cls, data: dict) -> FilterCriteria:
        if not isinstance(data, dict):
            raise ValueError("filter_criteria must be a dict")

        logical_operator = data.get("logical_operator", "all")
        if logical_operator not in ("all", "any"):
            raise ValueError(f"Invalid logical_operator: {logical_operator}")

        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list) or not raw_rules:
            raise ValueError("filter_criteria must contain at least one rule")

        rules: list[SegmentRule] = []
        for idx, raw in enumerate(raw_rules):
            if not isinstance(raw, dict):
                raise ValueError(f"Rule at index {idx} must be a dict")

            rule_type = raw.get("type")
            operator = raw.get("operator")
            if not rule_type or not operator:
                raise ValueError(f"Rule at index {idx} must have 'type' and 'operator'")

            rules.append(
                SegmentRule(
                    rule_type=rule_type,
                    operator=operator,
                    value=raw.get("value"),
                    field=raw.get("field"),
                )
            )

        return cls(logical_operator=logical_operator, rules=tuple(rules))

    def to_dict(self) -> dict:
        return {
            "logical_operator": self.logical_operator,
            "rules": [
                {
                    "type": r.rule_type,
                    "operator": r.operator,
                    "value": r.value,
                    "field": r.field,
                }
                for r in self.rules
            ],
        }


@dataclass(frozen=True, slots=True)
class DispatchItem:
    group_id: int
    workshop_id: int
    customer_id: int
    phone: str
    message: str

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "workshop_id": self.workshop_id,
            "customer_id": self.customer_id,
            "phone": self.phone,
            "message": self.message,
        }
