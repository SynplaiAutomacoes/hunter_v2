from django.core.validators import MinValueValidator
from django.db import models
from localflavor.br.models import BRPostalCodeField, BRStateField


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Address(models.Model):
    cep = BRPostalCodeField(verbose_name="CEP")
    logradouro = models.CharField(verbose_name="Logradouro", max_length=225)
    numero = models.CharField(verbose_name="Número", max_length=8, validators=[MinValueValidator(0)])
    complemento = models.CharField(verbose_name="Complemento", max_length=255, null=True, blank=True)
    bairro = models.CharField(verbose_name="Bairro", max_length=20)
    cidade = models.CharField(verbose_name="Cidade", max_length=20)
    estado = BRStateField(verbose_name="Estado")