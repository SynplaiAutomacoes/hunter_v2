from __future__ import annotations

BUDGET_KM_BELOW_CADASTRO_MESSAGE = (
    "O KM informado não pode ser menor que o KM cadastrado do cliente. "
    "Caso necessário, altere o KM nas informações do cadastro do cliente."
)


def budget_entry_km_is_below_cadastro(*, current_km: int | None, registered_km: int | None) -> bool:
    """Return True when the budget entry KM is below the vehicle cadastro KM."""
    if current_km is None or registered_km is None:
        return False
    return int(current_km) < int(registered_km)
