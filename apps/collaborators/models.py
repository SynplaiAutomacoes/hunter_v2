from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from djmoney.models.fields import MoneyField
from localflavor.br.models import BRCPFField
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.models import TimeStampedModel


class WorkshopMember(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workshop_members",
    )
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="members",
    )
    role = models.ForeignKey(
        "iam.WorkshopRole",
        on_delete=models.PROTECT,
        related_name="workshop_members",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Membro da Oficina"
        verbose_name_plural = "Membros da Oficina"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "workshop"),
                name="unique_user_workshop_member",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.workshop} ({self.role})"


class WorkshopCollaborator(TimeStampedModel):
    class Sex(models.TextChoices):
        MALE = "M", "Masculino"
        FEMALE = "F", "Feminino"
        OTHER = "O", "Outro"

    class CollaboratorType(models.TextChoices):
        ADMINISTRATIVE = "A", "Administrativo"
        PRODUCTIVE = "P", "Produtivo"

    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="collaborators",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="workshop_collaborator",
        null=True,
        blank=True,
    )

    name = models.CharField(verbose_name="Nome", max_length=255)
    cpf = BRCPFField(verbose_name="CPF", null=False, blank=False)
    # TODO: Create specific field for RG
    rg = models.CharField(verbose_name="RG", max_length=9, blank=True, null=True)
    birth_date = models.DateField(verbose_name="Data de Nascimento", null=False, blank=False)
    sex = models.CharField(verbose_name="Sexo", max_length=1, choices=Sex.choices, blank=True)

    phone = PhoneNumberField(verbose_name="Telefone", blank=True)
    email = models.EmailField(verbose_name="E-mail", blank=True)

    position = models.CharField(verbose_name="Cargo", max_length=255, blank=True)
    salary = MoneyField(
        verbose_name="Salário",
        max_digits=14,
        decimal_places=2,
        null=False,
        blank=True,
    )

    admission_date = models.DateField(verbose_name="Data de Admissão", null=False, blank=False)
    termination_date = models.DateField(verbose_name="Data de Saída", null=True, blank=True)

    collaborator_type = models.CharField(verbose_name="Tipo", max_length=1, choices=CollaboratorType.choices, blank=False, null=False)

    receives_commission = models.BooleanField(verbose_name="Recebe Comissão", default=False)
    commission_percentage = models.DecimalField(
        verbose_name="Percentual de Comissão",
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    system_access = models.BooleanField(verbose_name="Acesso ao Sistema", default=False)

    class Meta:
        verbose_name = "Colaborador da Oficina"
        verbose_name_plural = "Colaboradores da Oficina"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "cpf"),
                name="unique_collaborator_cpf_per_workshop",
            ),
            models.CheckConstraint(
                condition=Q(commission_percentage__isnull=True) | (Q(commission_percentage__gte=0) & Q(commission_percentage__lte=1)),
                name="collaborator_commission_percentage_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_collaborator_type_display()})"
