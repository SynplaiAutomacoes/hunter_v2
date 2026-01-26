from django.db import models
from apps.core.models import TimeStampedModel


class Checklist(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="checklists")
    name = models.CharField(verbose_name="Nome do Checklist", max_length=255)

    class Meta:
        verbose_name = "Checklist"
        verbose_name_plural = "Checklists"

    def __str__(self):
        return self.name


class ChecklistItem(models.Model):
    TIPO_RESPOSTA_CHOICES = [
        ("BOM_REGULAR_RUIM", "Bom / Regular / Ruim"),
        ("SIM_NAO", "Sim / Não"),
        ("TEXTO_LIVRE", "Texto Livre"),
        ("NIVEL", "Vazio | 1/4 | 1/2 | 3/4 | Cheio"),
    ]

    checklist = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name="items")
    group = models.CharField(verbose_name="Agrupamento", max_length=100, blank=True)
    description = models.CharField(verbose_name="Descrição", max_length=500)
    response_type = models.CharField(verbose_name="Tipo de Resposta", max_length=30, choices=TIPO_RESPOSTA_CHOICES)
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.group} - {self.description}"