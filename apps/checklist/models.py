from django.db import models
from apps.core.models import TimeStampedModel


class Checklist(TimeStampedModel):
    class ChecklistType(models.TextChoices):
        AUTOMOTIVE_DIAGNOSTIC = "AUTOMOTIVE_DIAGNOSTIC", "Checklist de Diagnóstico Automotivo"
        INTERNAL = "INTERNAL", "Checklists internos"
        STRUCTURAL = "STRUCTURAL", "Checklist Estruturais"
        PROCESS = "PROCESS", "Checklist de processos"

    class ChecklistSource(models.TextChoices):
        MANUAL = "MANUAL", "Crie seu Checklist"
        PDF = "PDF", "Importe seu Checklist"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="checklists")
    name = models.CharField(verbose_name="Nome do Checklist", max_length=255)
    checklist_type = models.CharField(verbose_name="Tipo de Checklist", max_length=40, choices=ChecklistType.choices, default=ChecklistType.AUTOMOTIVE_DIAGNOSTIC)
    source = models.CharField(verbose_name="Origem do Checklist", max_length=10, choices=ChecklistSource.choices, default=ChecklistSource.MANUAL)
    pdf_file_key = models.CharField(max_length=512, blank=True, default="")
    pdf_file_name = models.CharField(max_length=255, blank=True, default="")
    pdf_content_type = models.CharField(max_length=100, blank=True, default="")
    pdf_uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Checklist"
        verbose_name_plural = "Checklists"

    def __str__(self):
        return self.name

    @property
    def has_pdf_file(self) -> bool:
        return bool(self.pdf_file_key)


class ChecklistItem(models.Model):
    TIPO_RESPOSTA_CHOICES = [
        ("BOM_REGULAR_RUIM", "Bom / Regular / Ruim"),
        ("SIM_NAO", "Sim / Não"),
        ("TEXTO_LIVRE", "Texto Livre"),
        ("NIVEL", "Vazio | 1/4 | 1/2 | 3/4 | Cheio"),
    ]

    checklist = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name="items")
    group = models.CharField(verbose_name="Agrupamento", max_length=100)
    description = models.CharField(verbose_name="Descrição", max_length=500)
    response_type = models.CharField(verbose_name="Tipo de Resposta", max_length=30, choices=TIPO_RESPOSTA_CHOICES)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Item do Checklist"
        verbose_name_plural = "Itens do Checklist"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(group=""),
                name="checklist_item_group_not_blank",
            )
        ]

    def __str__(self):
        return f"{self.group} - {self.description}"
