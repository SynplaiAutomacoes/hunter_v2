from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


class VehicleLookupError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class FipeValuation:
    """Item da tabela FIPE selecionado para o veículo."""

    codigo_fipe: str = ""
    texto_modelo: str = ""
    texto_valor: str = ""
    valor: Decimal | None = None
    mes_referencia: str = ""
    combustivel: str = ""
    ano_modelo: str = ""
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class VehicleLookupResult:
    """Dados consolidados do veículo a partir das APIs de placa."""

    brand: str | None = None
    model: str | None = None
    year_fabrication: str | None = None
    year_model: str | None = None
    color: str | None = None
    fuel: str | None = None
    engine: str | None = None
    type: str | None = None
    chassi: str | None = None
    renavam: str | None = None
    motor_registry: str | None = None
    fipe_value: Decimal | None = None
    fipe: FipeValuation | None = None
    sources: dict[str, str] = field(default_factory=dict)


class IVehiclePlateLookupService(ABC):
    @abstractmethod
    def lookup_plate(self, plate: str) -> VehicleLookupResult | None:
        """Consulta as APIs de placa e consolida os dados do veículo.

        Retorna None quando o veículo não é encontrado em nenhuma fonte.
        """
        ...
