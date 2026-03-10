from django.db import models
from localflavor.br.models import BRPostalCodeField, BRStateField


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Data de Atualização")

    class Meta:
        abstract = True


class Address(models.Model):
    cep = BRPostalCodeField(verbose_name="CEP", default="")
    logradouro = models.CharField(verbose_name="Logradouro", max_length=225, default="")
    numero = models.PositiveIntegerField(verbose_name="Número", default=1)
    complemento = models.CharField(verbose_name="Complemento", max_length=255, null=True, blank=True)
    bairro = models.CharField(verbose_name="Bairro", max_length=255, default="")
    cidade = models.CharField(verbose_name="Cidade", max_length=255, default="")
    estado = BRStateField(verbose_name="Estado", default="")

    class Meta:
        abstract = True