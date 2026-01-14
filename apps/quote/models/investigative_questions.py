from __future__ import annotations

from django.db import models
from django.db.models import JSONField

from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class InvestigativeQuestion(TimeStampedModel):
    class ResponseType(models.TextChoices):
        FREE_TEXT = "TEXT", "Texto Livre"
        MULTIPLE_CHOICE = "CHOICE", "Múltipla Escolha"
        BOOLEAN = "BOOL", "Sim/Não"
        SCALE = "SCALE", "Escala (1-10)"

    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="investigative_questions",
    )

    text = models.CharField(verbose_name="Pergunta", max_length=255)
    response_type = models.CharField(
        verbose_name="Tipo de Resposta",
        max_length=10,
        choices=ResponseType.choices,
        default=ResponseType.FREE_TEXT,
    )

    # Options for multiple choice questions
    options = JSONField(verbose_name="Opções", default=list, blank=True)

    order = models.PositiveIntegerField(verbose_name="Ordem", default=0, help_text="Ordem em que a pergunta aparecerá (0 = Primeiro)")

    is_active = models.BooleanField(verbose_name="Ativa", default=True)

    class Meta:
        verbose_name = "Pergunta Investigativa"
        verbose_name_plural = "Perguntas Investigativas"

    def __str__(self):
        return self.text
