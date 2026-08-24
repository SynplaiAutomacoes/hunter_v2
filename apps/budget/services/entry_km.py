from __future__ import annotations

BUDGET_KM_CADASTRO_MISMATCH_MESSAGE = (
    "O KM informado não pode ser menor que o KM cadastrado do cliente. Caso necessário, altere o KM nas informações do cadastro do cliente."
)


def budget_entry_km_mismatches_cadastro(*, current_km: int | None, registered_km: int | None) -> bool:
    """Return True when the budget entry KM cannot proceed against the vehicle cadastro KM.

    The cadastro KM is the source of truth. A different value (higher or lower) must be
    corrected on the customer/vehicle record before the budget step can continue.
    """
    if current_km is None or registered_km is None:
        return False
    return int(current_km) != int(registered_km)
