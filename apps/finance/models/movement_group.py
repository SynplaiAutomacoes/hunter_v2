from django.db import models
from django.conf import settings
from apps.core.infrastructure.models import TimeStampedModel


class MovementGroup(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    name = models.CharField(verbose_name="Nome", max_length=255)
    description = models.TextField(verbose_name="Descrição", blank=True, null=True)
    due_date = models.DateField(verbose_name="Data de Vencimento")
    
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.SET_NULL, null=True, blank=True, related_name="movement_groups")
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", on_delete=models.SET_NULL, null=True, blank=True, related_name="movement_groups")

    def __str__(self):
        return self.name
