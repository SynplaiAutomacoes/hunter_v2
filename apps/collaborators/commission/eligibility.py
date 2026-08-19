from __future__ import annotations

from datetime import date

from apps.collaborators.models import CollaboratorCommissionRule, WorkshopCollaborator
from apps.workorder.models import WorkOrder


class CollaboratorEligibilityChecker:
    """Decide qual configuração de comissão se aplica a um colaborador numa OS."""

    def _is_workorder_after_rule_creation(self, *, workorder: WorkOrder, rule: CollaboratorCommissionRule) -> bool:
        """Verifica se a OS foi criada após a regra de comissão."""
        rule_created = rule.criado_em.date() if rule.criado_em else None
        if not rule_created:
            return True
        workorder_created = workorder.criado_em.date() if workorder.criado_em else None
        if not workorder_created:
            return False
        return workorder_created >= rule_created

    def get_effective_rules(self, *, collaborator: WorkshopCollaborator) -> list[CollaboratorCommissionRule]:
        """Regras manuais ativas do collaborator.

        Fallback de compatibilidade: collaborators legados (``receives_commission``
        + ``commission_percentage`` sem regras) são tratados como uma regra manual
        de Serviço (percentual, venda bruta, por participação) — comportamento de
        facto antigo, válido até a data migration de legado ser executada.
        """
        rules = list(collaborator.commission_rules.filter(is_active=True).order_by("id"))
        if rules and collaborator.receives_commission:
            return rules

        legacy_percentage = getattr(collaborator, "commission_percentage", None)
        if collaborator.receives_commission and legacy_percentage is not None:
            return [
                CollaboratorCommissionRule(
                    collaborator=collaborator,
                    scope=CollaboratorCommissionRule.Scope.SERVICE,
                    modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
                    apply_scope=CollaboratorCommissionRule.ApplyScope.PARTICIPATION,
                    base=CollaboratorCommissionRule.Base.GROSS_SALE,
                    percentage=legacy_percentage,
                    is_active=True,
                )
            ]
        return []

    def is_rule_eligible_for_workorder(self, *, rule: CollaboratorCommissionRule, collaborator: WorkshopCollaborator, workorder: WorkOrder) -> bool:
        """RN-07 (por participação) e RN-08 (global exige is_active) e OS após criação da regra."""
        if rule.apply_scope == CollaboratorCommissionRule.ApplyScope.GLOBAL:
            return collaborator.is_active and self._is_workorder_after_rule_creation(workorder=workorder, rule=rule)
        return workorder.collaborators.filter(pk=collaborator.pk).exists()

    def get_eligible_rules_for_workorder(self, *, collaborator: WorkshopCollaborator, workorder: WorkOrder) -> list[CollaboratorCommissionRule]:
        return [
            rule
            for rule in self.get_effective_rules(collaborator=collaborator)
            if self.is_rule_eligible_for_workorder(rule=rule, collaborator=collaborator, workorder=workorder)
        ]

    def is_eligible_for_workorder_rate(self, *, collaborator: WorkshopCollaborator, workorder: WorkOrder, settings) -> bool:
        """RN-10/RN-11: somente participantes, com comissão ativa e sem configuração manual."""
        if settings is None or not settings.workorder_commission_enabled:
            return False
        if not collaborator.receives_commission:
            return False
        if self.get_effective_rules(collaborator=collaborator):
            return False
        return workorder.collaborators.filter(pk=collaborator.pk).exists()