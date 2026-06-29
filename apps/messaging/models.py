from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from apps.customer.models import Customer


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


class CustomerMessageGroup(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="customer_message_groups")
    name = models.CharField(verbose_name="Nome", max_length=120)
    description = models.TextField(verbose_name="Descrição", blank=True)
    message_template = models.ForeignKey(
        MessageTemplate,
        verbose_name="Mensagem cadastrada",
        on_delete=models.SET_NULL,
        related_name="customer_message_groups",
        null=True,
        blank=True,
    )
    message = models.TextField(verbose_name="Mensagem personalizada")
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    customers = models.ManyToManyField(Customer, through="CustomerMessageGroupMembership", related_name="message_groups", blank=True)
    filter_criteria = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Critérios de segmentação",
        help_text="Configuração JSON com regras para incluir clientes automaticamente no grupo. Deixe vazio para usar apenas seleção manual.",
    )

    class Meta:
        verbose_name = "Grupo de mensagem"
        verbose_name_plural = "Grupos de mensagens"
        constraints = [models.UniqueConstraint(fields=("workshop", "name"), name="unique_customer_message_group_name_per_workshop")]

    @property
    def created_at_display(self) -> str:
        from django.utils import timezone

        return timezone.localtime(self.criado_em).strftime("%d/%m/%Y %H:%M")

    def __str__(self) -> str:
        return self.name


class CustomerMessageGroupMembership(TimeStampedModel):
    group = models.ForeignKey(CustomerMessageGroup, verbose_name="Grupo", on_delete=models.CASCADE, related_name="memberships")
    customer = models.ForeignKey(Customer, verbose_name="Cliente", on_delete=models.CASCADE, related_name="message_group_memberships")

    class Meta:
        verbose_name = "Cliente do grupo de mensagem"
        verbose_name_plural = "Clientes do grupo de mensagem"
        constraints = [models.UniqueConstraint(fields=("group", "customer"), name="unique_customer_message_group_membership")]

    def __str__(self) -> str:
        return f"{self.group} - {self.customer}"
