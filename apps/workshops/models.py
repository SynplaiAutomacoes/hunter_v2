from django.db.models import CharField, BooleanField
from localflavor.br.models import BRCNPJField

from apps.core.models import TimeStampedModel


class Workshop(TimeStampedModel):
    name = CharField(verbose_name="Nome", max_length=255, null=False, blank=False)
    cnpj = BRCNPJField(verbose_name="CNPJ", null=True, blank=True, unique=True)
    is_active = BooleanField(verbose_name="Ativa", default=True)

    def __str__(self):
        return self.name
