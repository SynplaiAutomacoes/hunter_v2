from __future__ import annotations

from apps.billing.domain.contracts import IBillingService
from apps.billing.infrastructure.services.stripe_billing import StripeBillingService


class BillingServiceProvider:
    _instance: IBillingService | None = None

    @classmethod
    def get_service(cls) -> IBillingService:
        if cls._instance is None:
            cls._instance = StripeBillingService()
        return cls._instance

    @classmethod
    def set_service(cls, service: IBillingService) -> None:
        cls._instance = service


def get_billing_service() -> IBillingService:
    return BillingServiceProvider.get_service()


def set_billing_service(service: IBillingService) -> None:
    BillingServiceProvider.set_service(service)
