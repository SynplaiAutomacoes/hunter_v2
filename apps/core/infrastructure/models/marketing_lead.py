from __future__ import annotations

import uuid

from django.db import models

from apps.core.infrastructure.models.abstract import TimeStampedModel


class MarketingLead(TimeStampedModel):
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name="ID da submissão")
    name = models.CharField(max_length=120, verbose_name="Nome")
    workshop = models.CharField(max_length=160, verbose_name="Oficina")
    email = models.EmailField(verbose_name="E-mail")
    whatsapp = models.CharField(max_length=11, verbose_name="WhatsApp")
    employees = models.CharField(max_length=40, verbose_name="Funcionários")
    revenue = models.CharField(max_length=60, verbose_name="Faturamento")
    consent = models.BooleanField(default=False, verbose_name="Consentimento")
    source = models.CharField(max_length=2048, blank=True, default="", verbose_name="Origem")
    utm = models.JSONField(default=dict, blank=True, verbose_name="UTMs")

    class Meta:
        verbose_name = "Lead comercial"
        verbose_name_plural = "Leads comerciais"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return f"{self.name} — {self.workshop}"
