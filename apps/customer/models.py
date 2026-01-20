from django.db import models
from localflavor.br.models import BRCPFField
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.models import TimeStampedModel, Address

class Customer(TimeStampedModel, Address):
    SEX_CHOICES = [("M", "Masculino"), ("F", "Feminino"), ("O", "Outro")]

    workshop = models.ForeignKey(
        "workshops.Workshop", on_delete=models.CASCADE, related_name="customers"
    )
    name = models.CharField("Nome", max_length=255)
    cpf = BRCPFField(verbose_name="CPF", null=False, blank=False)
    # TODO: Create specific field for RG
    rg = models.CharField(verbose_name="RG", max_length=9, blank=True, null=True)
    birth_date = models.DateField(verbose_name="Data de Nascimento", null=False, blank=False)
    sex = models.CharField("Sexo", max_length=1, choices=SEX_CHOICES, blank=True, null=True)
    phone = PhoneNumberField(verbose_name="Telefone", blank=True)
    email = models.EmailField("Email", blank=True, null=True)
    is_active = models.BooleanField("Ativo", default=True)

    @property
    def full_address(self) -> str:
        return f"{self.logradouro}, {self.numero} - {self.cidade}/{self.estado}"

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "cpf"), name="unique_customer_cpf_per_workshop"
            )
        ]

    def __str__(self):
        return self.name