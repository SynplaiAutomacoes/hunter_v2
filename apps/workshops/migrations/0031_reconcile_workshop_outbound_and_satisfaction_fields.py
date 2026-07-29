from __future__ import annotations

from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Aligns local/prod-synced DBs that already have messaging/satisfaction columns
    with this branch's model state. Uses IF NOT EXISTS so both fresh and synced DBs work.
    """

    dependencies = [
        ("workshops", "0030_unify_transport_allowance_monthly_cost"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="workshop",
                    name="outbound_business_hours_enabled",
                    field=models.BooleanField(default=True, verbose_name="Respeitar horário de disparo"),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="outbound_business_weekdays",
                    field=models.CharField(
                        default="0,1,2,3,4",
                        help_text="Dias da semana (Python: Mon=0 … Sun=6), separados por vírgula.",
                        max_length=32,
                        verbose_name="Dias de disparo",
                    ),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="outbound_business_start_time",
                    field=models.TimeField(
                        default=time(8, 0),
                        help_text="Horário inicial inclusivo da janela de envio.",
                        verbose_name="Hora inicial",
                    ),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="outbound_business_end_time",
                    field=models.TimeField(
                        default=time(18, 0),
                        help_text="Horário final exclusivo da janela de envio.",
                        verbose_name="Hora final",
                    ),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="satisfaction_survey_enabled",
                    field=models.BooleanField(default=False, verbose_name="Ativar pesquisa de satisfação"),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="satisfaction_survey_delay_days",
                    field=models.PositiveSmallIntegerField(
                        default=1,
                        help_text="Quantidade de dias após o fechamento da O.S. para enviar o link de avaliação.",
                        verbose_name="Dias após entrega para enviar pesquisa",
                    ),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="satisfaction_survey_send_immediately",
                    field=models.BooleanField(
                        default=False,
                        help_text="Disponível apenas fora de produção. Agenda o envio no momento do fechamento da O.S.",
                        verbose_name="Enviar pesquisa imediatamente",
                    ),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="google_review_url",
                    field=models.URLField(
                        blank=True,
                        default="",
                        help_text="URL do Google Maps / Place para pedir avaliação pública.",
                        max_length=500,
                        verbose_name="Link de avaliação no Google",
                    ),
                ),
                migrations.AddField(
                    model_name="workshop",
                    name="google_review_min_rating",
                    field=models.PositiveSmallIntegerField(
                        default=4,
                        help_text="Se a nota do cliente for igual ou maior que este valor (1–5), exibe o link do Google.",
                        verbose_name="Nota mínima para pedir avaliação no Google",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE workshops_workshop
                    ADD COLUMN IF NOT EXISTS outbound_business_hours_enabled boolean NOT NULL DEFAULT TRUE,
                    ADD COLUMN IF NOT EXISTS outbound_business_weekdays varchar(32) NOT NULL DEFAULT '0,1,2,3,4',
                    ADD COLUMN IF NOT EXISTS outbound_business_start_time time NOT NULL DEFAULT TIME '08:00:00',
                    ADD COLUMN IF NOT EXISTS outbound_business_end_time time NOT NULL DEFAULT TIME '18:00:00',
                    ADD COLUMN IF NOT EXISTS satisfaction_survey_enabled boolean NOT NULL DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS satisfaction_survey_delay_days smallint NOT NULL DEFAULT 1,
                    ADD COLUMN IF NOT EXISTS satisfaction_survey_send_immediately boolean NOT NULL DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS google_review_url varchar(500) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS google_review_min_rating smallint NOT NULL DEFAULT 4;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
