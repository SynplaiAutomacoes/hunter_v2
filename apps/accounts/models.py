from __future__ import annotations

import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone
from localflavor.br.models import BRCPFField

from apps.core.models import TimeStampedModel


class Account(TimeStampedModel):
    name = models.CharField(verbose_name="Conta", max_length=255)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_account",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Conta"
        verbose_name_plural = "Contas"

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    is_account_owner = models.BooleanField(default=False)
    cpf = BRCPFField(unique=False, null=False, blank=False)
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Telefone (WhatsApp)",
        help_text="Número com DDI para envio de mensagens via WhatsApp",
    )
    workshops = models.ManyToManyField(
        "workshops.Workshop",
        through="collaborators.WorkshopMember",
        related_name="users",
        blank=True,
    )

    class Meta(AbstractUser.Meta):
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        constraints = [
            models.UniqueConstraint(
                fields=("cpf",),
                condition=Q(is_account_owner=True),
                name="unique_owner_cpf",
            ),
        ]


class PasswordResetToken(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    code = models.CharField(max_length=6, db_index=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "Token de redefinição de senha"
        verbose_name_plural = "Tokens de redefinição de senha"

    def __str__(self) -> str:
        return f"Token para {self.user.username}"

    @classmethod
    def generate_code(cls) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(6))

    @classmethod
    def create_token(cls, user: User, expires_in_minutes: int = 15) -> PasswordResetToken:
        code = cls.generate_code()
        expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)
        return cls.objects.create(
            user=user,
            code=code,
            expires_at=expires_at,
        )

    def is_valid(self) -> bool:
        return not self.used and timezone.now() < self.expires_at


class FavoritePage(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_pages")
    url = models.CharField(max_length=500, verbose_name="URL da Página")
    position = models.PositiveIntegerField(default=1, verbose_name="Posição")

    class Meta:
        verbose_name = "Página Favorita"
        verbose_name_plural = "Páginas Favoritas"
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=("user", "url"), name="unique_user_favorite_page_url"),
        ]
        indexes = [
            models.Index(fields=("user", "position"), name="favpage_user_pos_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.url}"
