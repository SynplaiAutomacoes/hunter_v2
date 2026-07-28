# Generated manually for Fase 3.6.1 on 2026-06-26

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0064_alter_fiscalemissionattempt_operation_type_and_more"),
        ("workshops", "0023_workshopcostholiday"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="fiscalemissionattempt",
            name="operation_type",
            field=models.CharField(
                choices=[
                    ("emission", "Emissao"),
                    ("cce", "Carta de correcao"),
                    ("return", "Devolucao"),
                    ("reversal", "Estorno"),
                    ("complementary_price_quantity", "Complementar preco/quantidade"),
                    ("adjustment", "Ajuste"),
                    ("nfce_emission", "Emissao NFC-e"),
                    ("nfce_cancellation", "Cancelamento NFC-e"),
                    ("nfce_inutilization", "Inutilizacao NFC-e"),
                    ("nfe_ibs_cbs_event", "Evento IBS/CBS"),
                    ("nfe_ibs_cbs_event_cancellation", "Cancelamento de evento IBS/CBS"),
                    ("nfe_credit_emission", "Emissao NF-e de credito"),
                    ("nfe_credit_cancellation", "Cancelamento NF-e de credito"),
                    ("nfe_debit_emission", "Emissao NF-e de debito"),
                    ("nfe_debit_cancellation", "Cancelamento NF-e de debito"),
                    ("nfse_cancellation", "Cancelamento NFS-e"),
                    ("nfse_substitution", "Substituicao NFS-e"),
                    ("nfse_manifestation", "Manifestacao NFS-e"),
                ],
                db_index=True,
                default="emission",
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="NfseManifestation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="Data de Atualização")),
                ("manifestation_type", models.CharField(choices=[("confirmation", "Confirmacao"), ("rejection", "Rejeicao")], db_index=True, max_length=16, verbose_name="Tipo")),
                ("manifestation_code", models.PositiveSmallIntegerField(verbose_name="Evento")),
                ("manifestation_role", models.CharField(choices=[("taker", "Tomador"), ("intermediary", "Intermediario")], db_index=True, max_length=16, verbose_name="Manifestador")),
                ("manifestor", models.PositiveSmallIntegerField(verbose_name="Codigo do manifestador")),
                ("rejection_reason", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Motivo de rejeicao")),
                ("rejection_justification", models.CharField(blank=True, default="", max_length=255, verbose_name="Justificativa de rejeicao")),
                ("request_payload", models.JSONField(default=dict, verbose_name="Payload enviado")),
                ("response_payload", models.JSONField(blank=True, default=dict, verbose_name="Resposta remota")),
                ("remote_uuid", models.UUIDField(blank=True, db_index=True, null=True, verbose_name="UUID remoto da manifestacao")),
                ("remote_status", models.CharField(blank=True, default="", max_length=40, verbose_name="Status remoto")),
                ("xml_manifestation", models.URLField(blank=True, default="", verbose_name="XML/artefato da manifestacao")),
                ("status", models.CharField(choices=[("started", "Iniciada"), ("sent", "Enviada"), ("succeeded", "Concluida"), ("failed", "Falhou"), ("uncertain", "Incerta")], db_index=True, default="started", max_length=20)),
                ("is_uncertain", models.BooleanField(db_index=True, default=False)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="nfse_manifestations", to=settings.AUTH_USER_MODEL, verbose_name="Criada por")),
                ("nfse_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="manifestations", to="finance.nfseitem", verbose_name="NFS-e")),
                ("workshop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nfse_manifestations", to="workshops.workshop", verbose_name="Oficina")),
            ],
            options={
                "permissions": [
                    ("issue_nfse_manifestation", "Pode manifestar NFS-e"),
                    ("view_nfse_manifestation", "Pode visualizar manifestacao NFS-e"),
                    ("download_nfse_manifestation", "Pode baixar documentos da manifestacao NFS-e"),
                    ("view_nfse_manifestation_payload", "Pode visualizar payload da manifestacao NFS-e"),
                ],
                "abstract": False,
                "indexes": [
                    models.Index(fields=["workshop", "status"], name="nfse_manifest_scope_status_idx"),
                    models.Index(fields=["nfse_item", "manifestation_code", "manifestor"], name="nfse_manifest_item_type_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("status__in", ["started", "sent", "succeeded", "uncertain"])), fields=("nfse_item", "manifestation_code", "manifestor"), name="unique_active_nfse_manifestation"),
                ],
            },
        ),
    ]
