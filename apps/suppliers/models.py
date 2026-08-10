from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.infrastructure.fields import BRCPFCNPJField
from apps.core.infrastructure.models import TimeStampedModel, Address
from django.utils import timezone

class Supplier(TimeStampedModel, Address):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="suppliers")
    cnpj = BRCPFCNPJField(verbose_name="Documento", max_length=18)
    name = models.CharField(verbose_name="Razão social", max_length=255)
    contact_person = models.CharField(verbose_name="Responsável", max_length=255, default="", blank=True)
    phone = PhoneNumberField(region="BR", verbose_name="Telefone", max_length=20, default="", blank=True)
    mobile = PhoneNumberField(region="BR", verbose_name="Celular", max_length=20, default="", blank=True)
    email = models.EmailField(verbose_name="E-mail", default="", blank=True)
    registration_date = models.DateField(verbose_name="Data de cadastro", default=timezone.now)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    @property
    def full_address(self) -> str:
        return f"{self.logradouro}, {self.numero} - {self.cidade}/{self.estado}"

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "cnpj"),
                name="unique_supplier_cnpj_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name
