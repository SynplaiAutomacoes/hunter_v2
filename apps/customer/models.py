from django.db import models
from localflavor.br.models import BRCPFField
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.models import TimeStampedModel, Address

class Customer(TimeStampedModel, Address):
    SEX_CHOICES = [("M", "Masculino"), ("F", "Feminino"), ("O", "Outro")]

    workshop = models.ForeignKey(
        "workshops.Workshop", on_delete=models.CASCADE, related_name="customers"
    )

    customer_type = models.CharField(
        max_length=2,
        choices=[
            ("PF", "Pessoa Física"),
            ("PJ", "Pessoa Jurídica"),
        ],
        default="PF"
    )

    # CAMPOS COMUNS
    name = models.CharField(verbose_name="Nome", max_length=255, null=False, blank=False)
    cpf_or_cnpj = models.CharField(verbose_name="CPF/CNPJ", max_length=18, null=False, blank=False)
    phone = PhoneNumberField(verbose_name="Telefone", blank=True)
    email = models.EmailField(verbose_name="Email", blank=True, null=True)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    # CAMPOS PESSOA FISICA
    rg = models.CharField(verbose_name="RG", max_length=9, blank=True, null=True)
    birth_date = models.DateField(verbose_name="Data de Nascimento", null=True, blank=True)
    sex = models.CharField(verbose_name="Sexo", max_length=1, choices=SEX_CHOICES, blank=True, null=True)

    # CAMPOS PESSOA JURÍDICA
    fantasy_name = models.CharField(verbose_name="Nome Fantasia", max_length=255, blank=True, null=True)
    state_registration = models.CharField(verbose_name="Inscrição Estadual", max_length=255, blank=True, null=True)
    municipal_registration = models.CharField(verbose_name="Inscrição Municipal", max_length=255, blank=True, null=True)
    foundation_date = models.DateField(verbose_name="Data de Fundação", blank=True, null=True)

    @property
    def full_address(self) -> str:
        return f"{self.logradouro}, {self.numero} - {self.cidade}/{self.estado}"

    @property
    def cpf_or_cnpj_formatted(self):
        value = ''.join(filter(str.isdigit, self.cpf_or_cnpj))

        if len(value) == 11:  # CPF
            return f"{value[:3]}.{value[3:6]}.{value[6:9]}-{value[9:]}"
        elif len(value) == 14:  # CNPJ
            return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"
        return self.cpf_or_cnpj
      
    def vehicles_count(self) -> str:
        return str(self.vehicles.count())

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "cpf_or_cnpj"), name="unique_customer_document_per_workshop"
            )
        ]

    def __str__(self):
        return self.name


class Vehicle(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="vehicles")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="vehicles")
    plate = models.CharField(verbose_name="Placa", max_length=20)
    brand = models.CharField(verbose_name="Marca", max_length=500)
    model = models.CharField(verbose_name="Modelo", max_length=500)
    year_fabrication = models.CharField(verbose_name="Ano de Fabricação", max_length=4)
    year_model = models.CharField(verbose_name="Ano do Modelo", max_length=4)
    color = models.CharField(verbose_name="Cor", max_length=30)
    fuel = models.CharField(verbose_name="Combustível", max_length=30, null=True, blank=True)
    km = models.PositiveIntegerField(verbose_name="Quilometragem", default=0)
    engine = models.CharField(verbose_name="Motor", max_length=30, null=True, blank=True)
    type = models.CharField(verbose_name="Tipo", max_length=50, null=True, blank=True)
    renavam = models.CharField(verbose_name="Renavam", max_length=500, null=True, blank=True)
    chassi = models.CharField(verbose_name="Chassi", max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.plate} - {self.model}"