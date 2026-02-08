from __future__ import annotations

from django.db import models
from django.db.models import CharField, BooleanField
from localflavor.br.models import BRCNPJField
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.models import TimeStampedModel


class Workshop(TimeStampedModel):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="workshops",
        null=True,
        blank=True,
    )
    name = CharField(verbose_name="Nome", max_length=255, null=False, blank=False)
    cnpj = BRCNPJField(verbose_name="CNPJ", null=True, blank=True, unique=True)
    phone = PhoneNumberField(region="BR", verbose_name="Telefone", max_length=20, blank=False)
    address = CharField(verbose_name="Endereço", max_length=255, null=False, blank=False)
    pdf_observation = CharField(verbose_name="Observação", max_length=250, null=False, blank=False, default="")
    is_active = BooleanField(verbose_name="Ativa", default=True)

    def __str__(self):
        return self.name
