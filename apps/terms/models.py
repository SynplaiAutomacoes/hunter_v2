from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone

from apps.budget.models import SignatureStatus
from apps.core.infrastructure.models.abstract import TimeStampedModel
from apps.terms.defaults import default_vehicle_receipt_content, default_warranty_content


class TermTemplateType(models.TextChoices):
    VEHICLE_RECEIPT = "vehicle_receipt", "Termo de Recebimento de Veículo"
    WARRANTY = "warranty", "Termo de Garantia"


class WorkshopTermTemplate(TimeStampedModel):
    workshop = models.ForeignKey(
        "workshops.Workshop",
        verbose_name="Oficina",
        on_delete=models.CASCADE,
        related_name="term_templates",
    )
    template_type = models.CharField(
        verbose_name="Tipo",
        max_length=32,
        choices=TermTemplateType.choices,
    )
    name = models.CharField(verbose_name="Nome interno", max_length=120)
    document_title = models.CharField(verbose_name="Título do documento", max_length=255)
    subtitle = models.CharField(verbose_name="Subtítulo", max_length=255, blank=True, default="")
    intro_text = models.TextField(verbose_name="Texto de introdução", blank=True, default="")
    primary_color = models.CharField(verbose_name="Cor principal", max_length=7, default="#000000")
    accent_color = models.CharField(verbose_name="Cor de destaque", max_length=7, default="#DC2626")
    text_color = models.CharField(verbose_name="Cor do texto", max_length=7, default="#111827")
    muted_color = models.CharField(verbose_name="Cor secundária", max_length=7, default="#6B7280")
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    is_default = models.BooleanField(verbose_name="Padrão", default=False)
    content = models.JSONField(verbose_name="Conteúdo", default=dict, blank=True)

    class Meta:
        verbose_name = "Termo da oficina"
        verbose_name_plural = "Termos da oficina"
        ordering = ("template_type", "name")
        indexes = [
            models.Index(fields=("workshop", "template_type", "is_active")),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def template_type_display(self) -> str:
        return self.get_template_type_display()

    @property
    def created_at_display(self) -> str:
        return timezone.localtime(self.criado_em).strftime("%d/%m/%Y %H:%M")

    def save(self, *args, **kwargs) -> None:
        if not self.content:
            if self.template_type == TermTemplateType.WARRANTY:
                self.content = default_warranty_content()
            else:
                self.content = default_vehicle_receipt_content()
        if not self.document_title:
            self.document_title = self.get_template_type_display().upper()

        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.is_default:
                WorkshopTermTemplate.objects.filter(
                    workshop_id=self.workshop_id,
                    template_type=self.template_type,
                ).exclude(pk=self.pk).update(is_default=False)


class TermSigningMixin(models.Model):
    signature_token_version = models.PositiveIntegerField(verbose_name="Versão do token", default=1)
    signature_token_active = models.BooleanField(verbose_name="Token ativo", default=True)
    signature_request_status = models.CharField(
        max_length=30,
        choices=SignatureStatus.choices,
        default=SignatureStatus.NOT_SENT,
    )
    signature_external_id = models.CharField(max_length=255, blank=True, null=True)
    signature_document_id = models.CharField(max_length=255, blank=True, null=True)
    signature_sent_at = models.DateTimeField(blank=True, null=True)
    content_snapshot = models.JSONField(verbose_name="Snapshot do conteúdo", default=dict, blank=True)

    class Meta:
        abstract = True

    @property
    def is_signature_locked(self) -> bool:
        return self.signature_request_status in {
            SignatureStatus.SENDING,
            SignatureStatus.SENT,
            SignatureStatus.APPROVED,
        }

    def mark_signature_sending(self) -> None:
        self.signature_request_status = SignatureStatus.SENDING
        self.save(update_fields=["signature_request_status"])

    def mark_signature_sent(self, external_id: str, *, document_id: str | None = None) -> None:
        self.signature_request_status = SignatureStatus.SENT
        self.signature_external_id = external_id
        self.signature_document_id = document_id
        self.signature_sent_at = timezone.now()
        self.save(
            update_fields=[
                "signature_request_status",
                "signature_external_id",
                "signature_document_id",
                "signature_sent_at",
            ]
        )

    def mark_signature_failed(self) -> None:
        self.signature_request_status = SignatureStatus.FAILED
        self.save(update_fields=["signature_request_status"])

    def mark_signature_approved(self) -> None:
        self.signature_request_status = SignatureStatus.APPROVED
        self.save(update_fields=["signature_request_status"])

    def regenerate_signature_token(self) -> None:
        self.signature_token_version += 1
        self.signature_token_active = True
        self.save(update_fields=["signature_token_version", "signature_token_active"])


class BudgetTermSigning(TermSigningMixin, TimeStampedModel):
    budget = models.OneToOneField(
        "budget.Budget",
        verbose_name="Orçamento",
        on_delete=models.CASCADE,
        related_name="term_signing",
    )
    term_template = models.ForeignKey(
        WorkshopTermTemplate,
        verbose_name="Termo selecionado",
        on_delete=models.PROTECT,
        related_name="budget_signings",
    )

    class Meta:
        verbose_name = "Assinatura de termo do orçamento"
        verbose_name_plural = "Assinaturas de termo do orçamento"

    def build_content_snapshot(self) -> dict:
        return {
            "name": self.term_template.name,
            "document_title": self.term_template.document_title,
            "subtitle": self.term_template.subtitle,
            "intro_text": self.term_template.intro_text,
            "primary_color": self.term_template.primary_color,
            "accent_color": self.term_template.accent_color,
            "text_color": self.term_template.text_color,
            "muted_color": self.term_template.muted_color,
            "content": self.term_template.content,
        }

    def freeze_snapshot(self) -> None:
        self.content_snapshot = self.build_content_snapshot()
        self.save(update_fields=["content_snapshot"])


class WorkOrderTermSigning(TermSigningMixin, TimeStampedModel):
    workorder = models.OneToOneField(
        "workorder.WorkOrder",
        verbose_name="Ordem de serviço",
        on_delete=models.CASCADE,
        related_name="term_signing",
    )
    term_template = models.ForeignKey(
        WorkshopTermTemplate,
        verbose_name="Termo selecionado",
        on_delete=models.PROTECT,
        related_name="workorder_signings",
    )

    class Meta:
        verbose_name = "Assinatura de termo da ordem de serviço"
        verbose_name_plural = "Assinaturas de termo da ordem de serviço"

    def build_content_snapshot(self) -> dict:
        return {
            "name": self.term_template.name,
            "document_title": self.term_template.document_title,
            "subtitle": self.term_template.subtitle,
            "intro_text": self.term_template.intro_text,
            "primary_color": self.term_template.primary_color,
            "accent_color": self.term_template.accent_color,
            "text_color": self.term_template.text_color,
            "muted_color": self.term_template.muted_color,
            "content": self.term_template.content,
        }

    def freeze_snapshot(self) -> None:
        self.content_snapshot = self.build_content_snapshot()
        self.save(update_fields=["content_snapshot"])
