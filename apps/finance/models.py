from django.db import models


class BatchStatus(models.TextChoices):
    PROCESSING = "PROCESSING", "Processando"
    PROCESSED = "PROCESSED", "Processado"
    SCHEDULED = "SCHEDULED", "Agendado"
    REPROVED = "REPROVED", "Reprovado"
    CANCELED = "CANCELED", "Cancelado"
    CONTINGENCY = "CONTINGENCY", "Contingência"


class NsfeItemStatus(models.TextChoices):
    PROCESSING = "PROCESSING", "Processando"
    PROCESSED = "PROCESSED", "Processado"
    SCHEDULED = "SCHEDULED", "Agendado"
    REPROVED = "REPROVED", "Reprovado"
    CANCELED = "CANCELED", "Cancelado"
    CONTINGENCY = "CONTINGENCY", "Contingência"


class NsfePdfStatus(models.TextChoices):
    PROCESSING = "PROCESSING", "Processando"
    PROCESSED = "PROCESSED", "Processado"
    UNAVAILABLE = "UNAVAILABLE", "Indisponível"


class NsfeBatch(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    uuid = models.UUIDField(db_index=True) # UUID do lote
    model = models.CharField(max_length=255, default="lote_rps")
    status = models.CharField(max_length=20, choices=BatchStatus.choices)
    reason = models.TextField(blank=True, default="")
    batch_number = models.CharField(max_length=40, blank=True, default="") # Número do lote
    batch_series = models.CharField(max_length=20, blank=True, default="") # Série do lote
    rps_quantity = models.PositiveIntegerField(default=0)
    protocol = models.CharField(max_length=60, blank=True, default="")
    log_payload = models.JSONField(blank=True, default=dict)
    raw_payload = models.JSONField(blank=True, default=dict)

    class Meta:
        models.UniqueConstraint(fields=["workorder", "uuid"], name="unique_nsfe_batch_per_workorder")

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]


class NsfeItem(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    batch = models.ForeignKey(NsfeBatch, verbose_name="Lote", related_name="items",on_delete=models.CASCADE)
    uuid = models.UUIDField(db_index=True) # UUID da NFS-e
    model = models.CharField(max_length=255, default="nfse")
    status = models.CharField(max_length=20, choices=NsfeItemStatus.choices)
    reason = models.TextField(blank=True, default="")
    number = models.CharField(max_length=40, blank=True, default="") # Número da NFS-e
    verification_code = models.CharField(max_length=60, blank=True, default="")
    rps_series = models.CharField(max_length=20, blank=True, default="") # Série do RPS
    rps_number = models.CharField(max_length=40, blank=True, default="") # Número do RPS
    xml_url = models.URLField(blank=True, default="")
    pdf_nsfe_url = models.URLField(blank=True, default="")
    pdf_nfse_status = models.CharField(max_length=20, choices=NsfePdfStatus.choices)
    pdf_rps_url = models.URLField(blank=True, default="")
    log_payload = models.JSONField(blank=True, default=dict)
    raw_payload = models.JSONField(blank=True, default=dict)

    class Meta:
        models.UniqueConstraint(fields=["workorder", "uuid"], name="unique_nsfe_item_per_workorder")

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]