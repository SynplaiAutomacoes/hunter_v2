from django.db import models


class MessageTemplate(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Data de Atualização")
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="message_templates")
    name = models.CharField(verbose_name="Nome", max_length=120)
    message = models.TextField(verbose_name="Mensagem")
    is_active = models.BooleanField(verbose_name="Ativa", default=True)

    class Meta:
        verbose_name = "Mensagem WhatsApp"
        verbose_name_plural = "Mensagens WhatsApp"
        constraints = [models.UniqueConstraint(fields=("workshop", "name"), name="unique_message_template_name_per_workshop")]

    @property
    def created_at_display(self) -> str:
        from django.utils import timezone

        return timezone.localtime(self.criado_em).strftime("%d/%m/%Y %H:%M")

    def __str__(self) -> str:
        return self.name
