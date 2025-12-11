from django.db import models
from localflavor.br.models import BRCNPJField


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Workshop(TimeStampedModel):
    name = models.CharField(max_length=255, null=False, blank=False)
    cnpj = BRCNPJField(null=True, blank=True, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


