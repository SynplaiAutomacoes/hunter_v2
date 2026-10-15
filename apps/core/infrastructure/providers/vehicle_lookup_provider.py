from __future__ import annotations

from apps.core.domain.contracts.vehicle_lookup import IVehiclePlateLookupService
from apps.core.infrastructure.services.vehicle_lookup.service import VehiclePlateLookupService


class VehicleLookupServiceProvider:
    _instance: IVehiclePlateLookupService | None = None

    @classmethod
    def get_service(cls) -> IVehiclePlateLookupService:
        if cls._instance is None:
            cls._instance = VehiclePlateLookupService()
        return cls._instance

    @classmethod
    def set_service(cls, service: IVehiclePlateLookupService) -> None:
        cls._instance = service


def get_vehicle_lookup_service() -> IVehiclePlateLookupService:
    return VehicleLookupServiceProvider.get_service()


def set_vehicle_lookup_service(service: IVehiclePlateLookupService) -> None:
    VehicleLookupServiceProvider.set_service(service)
