from __future__ import annotations

import secrets
import string
from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.infrastructure.models.abstract import TimeStampedModel


class SignupEmailVerification(TimeStampedModel):
    email = models.EmailField(db_index=True, verbose_name="E-mail")
    code = models.CharField(max_length=6, db_index=True, verbose_name="Código")
    used = models.BooleanField(default=False, verbose_name="Usado")
    attempts = models.PositiveIntegerField(default=0, verbose_name="Tentativas")
    expires_at = models.DateTimeField(verbose_name="Expira em")

    class Meta:
        verbose_name = "Verificação de e-mail no cadastro"
        verbose_name_plural = "Verificações de e-mail no cadastro"
        indexes = [
            models.Index(fields=["email", "used"]),
        ]

    def __str__(self) -> str:
        return f"Verificação {self.email}"

    @classmethod
    def generate_code(cls) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(6))

    @classmethod
    def create_token(cls, *, email: str, expires_in_minutes: int = 15) -> SignupEmailVerification:
        normalized = email.lower().strip()
        cls.objects.filter(email__iexact=normalized, used=False).update(used=True)

        last_token = cls.objects.filter(email__iexact=normalized).order_by("-criado_em").first()
        if last_token and (timezone.now() - last_token.criado_em).total_seconds() < 60:
            raise ValueError("Aguarde 1 minuto antes de solicitar um novo código.")

        return cls.objects.create(
            email=normalized,
            code=cls.generate_code(),
            expires_at=timezone.now() + timedelta(minutes=expires_in_minutes),
        )

    def is_valid(self) -> bool:
        return not self.used and self.attempts < 3 and timezone.now() < self.expires_at
