from __future__ import annotations

from decimal import Decimal

from apps.collaborators.models import CollaboratorCommissionRule


class WorkshopCommissionLimitsValidator:
    """Valida se a regra percentual respeita o limite da Workshop."""

    def __init__(self, workshop):
        self.workshop = workshop

    def validate(self, rule: CollaboratorCommissionRule) -> dict[str, str]:
        errors: dict[str, str] = {}
        if rule.modality != CollaboratorCommissionRule.Modality.PERCENTAGE:
            return errors
        if rule.percentage is None:
            return errors
        pct = Decimal(str(rule.percentage))
        if pct <= 0:
            return errors
        limit = None
        if rule.scope == CollaboratorCommissionRule.Scope.SERVICE:
            limit = getattr(self.workshop, "service_commission_max_percentage", None)
        elif rule.scope == CollaboratorCommissionRule.Scope.PRODUCT:
            limit = getattr(self.workshop, "product_commission_max_percentage", None)
        if limit is not None:
            limit_dec = Decimal(str(limit))
            if pct > limit_dec:
                limit_display = (limit_dec * Decimal("100")).quantize(Decimal("0.01"))
                errors["percentage"] = f"Percentual ultrapassa o limite máximo da oficina ({limit_display}%)."
        return errors
