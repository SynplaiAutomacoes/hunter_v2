from __future__ import annotations

BUDGET_KM_CADASTRO_MISMATCH_MESSAGE = (
    "O KM informado é diferente do KM cadastrado do cliente. Você pode continuar com este KM no orçamento sem alterar o cadastro do veículo."
)


def budget_entry_km_mismatches_cadastro(*, current_km: int | None, registered_km: int | None) -> bool:
    """Return True when the budget entry KM differs from the vehicle cadastro KM.

    The operator can confirm and continue; the cadastro KM is not updated from this step.
    """
    if current_km is None or registered_km is None:
        return False
    return int(current_km) != int(registered_km)
