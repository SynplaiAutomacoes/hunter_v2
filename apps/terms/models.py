from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.infrastructure.models import TimeStampedModel

TERM_DEFAULT_PRIMARY_COLOR = "#000000"
TERM_DEFAULT_ACCENT_COLOR = "#e30613"


class TermKind(models.TextChoices):
    RECEIPT = "receipt", "Termo de Recebimento"
    WARRANTY = "warranty", "Termo de Garantia"
    OTHER = "other", "Outro"


class TermSource(models.TextChoices):
    HTML = "html", "Texto na plataforma"
    PDF = "pdf", "Arquivo PDF"


class TermSignatureStatus(models.TextChoices):
    NOT_SENT = "not_sent", "Não Enviado"
    SENDING = "sending", "Enviando"
    SENT = "sent", "Enviado"
    FAILED = "failed", "Falha no Envio"
    APPROVED = "approved", "Assinado"
    DECLINED = "declined", "Recusado"


class TermTemplate(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="term_templates")
    name = models.CharField(verbose_name="Nome do termo", max_length=255)
    kind = models.CharField(verbose_name="Tipo", max_length=20, choices=TermKind.choices, default=TermKind.RECEIPT)
    source = models.CharField(verbose_name="Origem", max_length=10, choices=TermSource.choices, default=TermSource.HTML)
    body_html = models.TextField(verbose_name="Conteúdo", blank=True, default="")
    intro_text = models.TextField(
        verbose_name="Texto de introdução",
        blank=True,
        default="",
        help_text="Aparece após os dados do veículo. Use linguagem simples; os dados do cliente e do veículo entram sozinhos no documento.",
    )
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    primary_color = models.CharField(
        verbose_name="Cor principal",
        max_length=7,
        default=TERM_DEFAULT_PRIMARY_COLOR,
        help_text="Usada no cabeçalho e barras escuras do documento.",
    )
    accent_color = models.CharField(
        verbose_name="Cor de destaque",
        max_length=7,
        default=TERM_DEFAULT_ACCENT_COLOR,
        help_text="Usada em faixas, numeração e marcadores do documento.",
    )
    pdf_file_key = models.CharField(max_length=512, blank=True, default="")
    pdf_file_name = models.CharField(max_length=255, blank=True, default="")
    pdf_content_type = models.CharField(max_length=100, blank=True, default="")
    pdf_uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Termo"
        verbose_name_plural = "Termos"
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return self.name

    @property
    def has_pdf_file(self) -> bool:
        return bool(self.pdf_file_key)

    @property
    def can_send_for_signature(self) -> bool:
        if self.source != TermSource.HTML:
            return False
        return self.topics.filter(bullets__isnull=False).distinct().exists()


class BudgetTermSigning(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="budget_term_signings")
    budget = models.ForeignKey("budget.Budget", on_delete=models.CASCADE, related_name="term_signings")
    template = models.ForeignKey(TermTemplate, on_delete=models.PROTECT, related_name="signings")
    rendered_html = models.TextField(blank=True, default="")
    signature_request_status = models.CharField(
        max_length=20,
        choices=TermSignatureStatus.choices,
        default=TermSignatureStatus.NOT_SENT,
    )
    signature_external_id = models.CharField(max_length=255, blank=True, default="")
    signature_document_id = models.CharField(max_length=255, blank=True, default="")
    signature_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Assinatura de termo"
        verbose_name_plural = "Assinaturas de termos"
        constraints = [
            models.UniqueConstraint(fields=("budget", "template"), name="unique_budget_term_template_signing"),
        ]

    def __str__(self) -> str:
        return f"{self.template} #{self.budget_id}"

    def mark_signature_sending(self) -> None:
        self.signature_request_status = TermSignatureStatus.SENDING
        self.save(update_fields=["signature_request_status"])

    def mark_signature_sent(self, external_id: str, *, document_id: str | None = None) -> None:
        self.signature_request_status = TermSignatureStatus.SENT
        self.signature_external_id = external_id
        self.signature_document_id = document_id or ""
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
        self.signature_request_status = TermSignatureStatus.FAILED
        self.save(update_fields=["signature_request_status"])

    def mark_signature_approved(self) -> None:
        self.signature_request_status = TermSignatureStatus.APPROVED
        self.save(update_fields=["signature_request_status"])

    def mark_signature_declined(self) -> None:
        self.signature_request_status = TermSignatureStatus.DECLINED
        self.save(update_fields=["signature_request_status"])

    @property
    def can_resend(self) -> bool:
        return self.signature_request_status in {
            TermSignatureStatus.SENT,
            TermSignatureStatus.FAILED,
            TermSignatureStatus.DECLINED,
        }

    @property
    def is_signed(self) -> bool:
        return self.signature_request_status == TermSignatureStatus.APPROVED


class TermTopic(models.Model):
    template = models.ForeignKey(TermTemplate, on_delete=models.CASCADE, related_name="topics")
    title = models.CharField(verbose_name="Tópico", max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Tópico do termo"
        verbose_name_plural = "Tópicos do termo"
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.title


class TermBullet(models.Model):
    topic = models.ForeignKey(TermTopic, on_delete=models.CASCADE, related_name="bullets")
    text = models.TextField(verbose_name="Texto")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Texto do tópico"
        verbose_name_plural = "Textos do tópico"
        ordering = ("order", "id")

    def __str__(self) -> str:
        return self.text[:80]
