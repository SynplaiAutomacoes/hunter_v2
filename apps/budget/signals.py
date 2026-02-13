from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.budget.models import Budget
from apps.budget.realtime import publish_budget_status_changed


@receiver(pre_save, sender=Budget)
def budget_capture_previous_status(sender, instance: Budget, **kwargs):
    if instance.pk is None:
        instance._previous_status = None
        return

    instance._previous_status = Budget.objects.filter(pk=instance.pk).values_list("status", flat=True).first()


@receiver(post_save, sender=Budget)
def budget_status_changed_event(sender, instance: Budget, created: bool, **kwargs):
    previous_status = getattr(instance, "_previous_status", None)
    if created or previous_status != instance.status:
        publish_budget_status_changed()
