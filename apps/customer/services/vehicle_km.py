from __future__ import annotations

from apps.customer.models import Vehicle


def sync_vehicle_km_from_exit(*, vehicle: Vehicle, km_final: int | None) -> bool:
    """Update the vehicle odometer from a work order exit reading.

    The stored odometer is monotonic: an exit reading may initialize or
    increase it, but never decrease it.
    """
    if km_final is None:
        return False
    if vehicle.km is not None and km_final <= vehicle.km:
        return False

    vehicle.km = km_final
    vehicle.save(update_fields=["km"])
    return True
