from __future__ import annotations

from django.db import models
from django.db.models import JSONField

from apps.core.infrastructure.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class InvestigativeQuestion(TimeStampedModel):
    class ResponseType(models.TextChoices):
        FREE_TEXT = "TEXT", "Texto livre"
        MULTIPLE_CHOICE = "CHOICE", "Múltipla escolha"
        BOOLEAN = "BOOL", "Sim/Não"
        SCALE = "SCALE", "Escala (1-10)"

    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="investigative_questions",
    )

    text = models.CharField(verbose_name="Pergunta", max_length=255)
    response_type = models.CharField(
        verbose_name="Tipo de resposta",
        max_length=10,
        choices=ResponseType.choices,
        default=ResponseType.FREE_TEXT,
    )

    # Options for multiple choice questions
    options = JSONField(verbose_name="Opções", default=list, blank=True)

    order = models.PositiveIntegerField(verbose_name="Ordem", default=0, help_text="Ordem em que a pergunta aparecerá (0 = primeiro)")

    is_active = models.BooleanField(verbose_name="Ativa", default=True)

    class Meta:
        verbose_name = "Pergunta investigativa"
        verbose_name_plural = "Perguntas investigativas"

    def __str__(self):
        return self.text


class InvestigativeResponse(TimeStampedModel):
    workshop = models.ForeignKey(Workshop, verbose_name="Oficina", on_delete=models.CASCADE, related_name="investigative_responses")
    budget = models.ForeignKey("budget.Budget", verbose_name="Orçamento", on_delete=models.CASCADE, related_name="investigative_responses")
    question = models.ForeignKey(InvestigativeQuestion, verbose_name="Pergunta investigativa", on_delete=models.CASCADE, related_name="investigative_responses")
    response = models.TextField(verbose_name="Resposta")

    class Meta:
        verbose_name = "Resposta da pergunta investigativa"
        verbose_name_plural = "Respostas das perguntas investigativas"
        unique_together = ["budget", "question"]

    def __str__(self):
        return f"{self.question}: {self.response}"
