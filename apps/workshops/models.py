from django.db.models import CharField, BooleanField
from localflavor.br.models import BRCNPJField

from apps.core.models import TimeStampedModel


class Workshop(TimeStampedModel):
    name = CharField(max_length=255, null=False, blank=False)
    cnpj = BRCNPJField(null=True, blank=True, unique=True)
    is_active = BooleanField(default=True)

    def __str__(self):
        return self.name
