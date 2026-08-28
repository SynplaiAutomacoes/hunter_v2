"""
core/domain/value_objects.py

Pure Python value objects — no Django imports allowed here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum

__all__ = [
    "Money",
    "Percentage",
    "Discount",
    "CPF",
    "CNPJ",
    "HoursDuration",
    "NCM",
    "Plate",
    "State",
    "PhoneNumber",
    "Kilometers",
    "parse_brl_decimal",
]


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "BRL"

    def __post_init__(self) -> None:
        if self.amount < Decimal("0"):
            raise ValueError(f"Money cannot be negative: {self.amount}")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Cannot add different currencies: {self.currency} and {other.currency}")
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract different currencies: {self.currency} and {other.currency}")
        result = self.amount - other.amount
        return Money(amount=max(result, Decimal("0")), currency=self.currency)

    def __mul__(self, factor: Decimal) -> Money:
        return Money(amount=(self.amount * factor).quantize(Decimal("0.01")), currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        return self.amount >= other.amount

    def __bool__(self) -> bool:
        return self.amount > Decimal("0")

    def format_brl(self) -> str:
        integer_part, decimal_part = f"{self.amount:.2f}".split(".")
        grouped = f"{int(integer_part):,}".replace(",", ".")
        return f"R$ {grouped},{decimal_part}"


def parse_brl_decimal(raw_value: str) -> Decimal | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    normalized = value.replace("R$", "").replace("\xa0", "").replace(" ", "")
    if not normalized or normalized in {"-", ",", "."}:
        return None

    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(",", "")

    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None

    if amount < 0:
        return None

    return amount.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Percentage
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Percentage:
    """Represents a percentage as a fraction. E.g. 0.10 = 10%."""
    value: Decimal

    def __post_init__(self) -> None:
        if self.value < Decimal("0") or self.value > Decimal("1"):
            raise ValueError(f"Percentage must be between 0 and 1, got: {self.value}")

    def apply_to(self, amount: Money) -> Money:
        return amount * self.value

    @classmethod
    def from_percent(cls, percent: Decimal) -> Percentage:
        """Create from human-readable percent (e.g. Decimal('10') → 10%)."""
        return cls(value=(percent / Decimal("100")).quantize(Decimal("0.0001")))


# ---------------------------------------------------------------------------
# Discount
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Discount:
    value: Money
    percentage: Percentage

    def apply(self, total: Money) -> Money:
        from_percentage = self.percentage.apply_to(total)
        discounted = total.amount - self.value.amount - from_percentage.amount
        return Money(amount=max(discounted, Decimal("0")), currency=total.currency)

    @classmethod
    def zero(cls) -> Discount:
        return cls(
            value=Money(amount=Decimal("0")),
            percentage=Percentage(value=Decimal("0")),
        )


# ---------------------------------------------------------------------------
# CPF
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CPF:
    number: str

    def __post_init__(self) -> None:
        if not self._is_valid():
            raise ValueError(f"Invalid CPF: {self.number}")

    def _is_valid(self) -> bool:
        digits = "".join(c for c in self.number if c.isdigit())
        if len(digits) != 11:
            return False
        if digits == digits[0] * 11:
            return False
        total = sum(int(digits[i]) * (10 - i) for i in range(9))
        first = (total * 10 % 11) % 10
        total = sum(int(digits[i]) * (11 - i) for i in range(10))
        second = (total * 10 % 11) % 10
        return digits[-2:] == f"{first}{second}"

    def digits_only(self) -> str:
        return "".join(c for c in self.number if c.isdigit())


# ---------------------------------------------------------------------------
# CNPJ
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CNPJ:
    number: str

    def __post_init__(self) -> None:
        if not self._is_valid():
            raise ValueError(f"Invalid CNPJ: {self.number}")

    def _is_valid(self) -> bool:
        digits = "".join(c for c in self.number if c.isdigit())
        if len(digits) != 14:
            return False
        if digits == digits[0] * 14:
            return False
        weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        weights_second = [6, *weights_first]

        def _digit(partial: str, weights: list[int]) -> str:
            total = sum(int(d) * w for d, w in zip(partial, weights))
            remainder = total % 11
            return "0" if remainder < 2 else str(11 - remainder)

        first = _digit(digits[:12], weights_first)
        second = _digit(digits[:12] + first, weights_second)
        return digits[-2:] == first + second

    def digits_only(self) -> str:
        return "".join(c for c in self.number if c.isdigit())


# ---------------------------------------------------------------------------
# HoursDuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HoursDuration:
    hours: Decimal

    def __post_init__(self) -> None:
        if self.hours < Decimal("0"):
            raise ValueError(f"HoursDuration cannot be negative: {self.hours}")

    def to_timedelta(self) -> timedelta:
        total_seconds = int(self.hours * Decimal("3600"))
        return timedelta(seconds=total_seconds)

    def __add__(self, other: HoursDuration) -> HoursDuration:
        return HoursDuration(hours=self.hours + other.hours)

    def __mul__(self, factor: int | Decimal) -> HoursDuration:
        return HoursDuration(hours=self.hours * Decimal(str(factor)))

    @classmethod
    def zero(cls) -> HoursDuration:
        return cls(hours=Decimal("0"))

    @classmethod
    def from_timedelta(cls, delta: timedelta) -> HoursDuration:
        return cls(hours=Decimal(str(delta.total_seconds() / 3600)))


# ---------------------------------------------------------------------------
# NCM
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NCM:
    code: str

    def __post_init__(self) -> None:
        digits = re.sub(r"\D", "", self.code)
        if not digits or len(digits) != 8:
            raise ValueError(f"Invalid NCM (must have 8 digits): {self.code}")

    def digits_only(self) -> str:
        return re.sub(r"\D", "", self.code)


# ---------------------------------------------------------------------------
# Plate
# ---------------------------------------------------------------------------

_PLATE_PATTERN = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")


@dataclass(frozen=True, slots=True)
class Plate:
    """Vehicle plate in Mercosul (ABC1D23) or old Brazilian format (ABC1234)."""
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.upper().strip()
        object.__setattr__(self, "value", normalized)
        if not _PLATE_PATTERN.match(normalized):
            raise ValueError(f"Invalid plate: {self.value}")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class State(str, Enum):
    AC = "AC"
    AL = "AL"
    AP = "AP"
    AM = "AM"
    BA = "BA"
    CE = "CE"
    DF = "DF"
    ES = "ES"
    GO = "GO"
    MA = "MA"
    MT = "MT"
    MS = "MS"
    MG = "MG"
    PA = "PA"
    PB = "PB"
    PR = "PR"
    PE = "PE"
    PI = "PI"
    RJ = "RJ"
    RN = "RN"
    RS = "RS"
    RO = "RO"
    RR = "RR"
    SC = "SC"
    SP = "SP"
    SE = "SE"
    TO = "TO"


# ---------------------------------------------------------------------------
# PhoneNumber
# ---------------------------------------------------------------------------

_PHONE_DIGITS_PATTERN = re.compile(r"^\d{10,11}$")


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    number: str

    def __post_init__(self) -> None:
        digits = re.sub(r"\D", "", self.number)
        if not _PHONE_DIGITS_PATTERN.match(digits):
            raise ValueError(f"Invalid phone number (expected 10 or 11 digits): {self.number}")

    def digits_only(self) -> str:
        return re.sub(r"\D", "", self.number)


# ---------------------------------------------------------------------------
# Kilometers
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Kilometers:
    value: Decimal

    def __post_init__(self) -> None:
        if self.value < Decimal("0"):
            raise ValueError(f"Kilometers cannot be negative: {self.value}")
