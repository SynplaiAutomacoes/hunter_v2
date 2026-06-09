from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class EditingLock(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Usuário",
    )
    session_key = models.CharField(max_length=255, verbose_name="Chave da Sessão")
    locked_at = models.DateTimeField(auto_now_add=True, verbose_name="Bloqueado em")

    class Meta:
        verbose_name = "Bloqueio de Edição"
        verbose_name_plural = "Bloqueios de Edição"
        unique_together = ("content_type", "object_id")
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.content_type} #{self.object_id} bloqueado por {self.user}"
