# Generated manually — appointment confirmation template/source + backfill

from django.db import migrations, models


DEFAULT_APPOINTMENT_CONFIRMATION_MESSAGE = """Oi %%primeiro_nome%%, tudo bem?

Seu agendamento na %%nome_fantasia%% foi confirmado.

Data: %%data_agendamento%%
Horário: %%hora_agendamento%%

Qualquer dúvida, estamos à disposição."""


def backfill_appointment_confirmation_templates(apps, schema_editor):
    Workshop = apps.get_model("workshops", "Workshop")
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")
    template_type = "appointment_confirmation"
    name = "Confirmação de agendamento"

    for workshop in Workshop.objects.all().iterator():
        if MessageTemplate.objects.filter(workshop_id=workshop.pk, template_type=template_type, is_active=True).exists():
            continue
        candidate_name = name
        suffix = 2
        while MessageTemplate.objects.filter(workshop_id=workshop.pk, name__iexact=candidate_name).exists():
            candidate_name = f"{name} {suffix}"
            suffix += 1
        MessageTemplate.objects.create(
            workshop_id=workshop.pk,
            name=candidate_name,
            message=DEFAULT_APPOINTMENT_CONFIRMATION_MESSAGE,
            template_type=template_type,
            is_active=True,
        )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("messaging", "0011_default_templates_primeiro_nome"),
    ]

    operations = [
        migrations.AlterField(
            model_name="messagetemplate",
            name="template_type",
            field=models.CharField(
                choices=[
                    ("generic", "Genérico"),
                    ("review_plan", "Plano de revisão"),
                    ("birthday", "Aniversário"),
                    ("appointment", "Agendamento"),
                    ("appointment_confirmation", "Confirmação de agendamento"),
                    ("satisfaction", "Avaliação"),
                ],
                db_index=True,
                default="generic",
                max_length=32,
                verbose_name="Tipo",
            ),
        ),
        migrations.AlterField(
            model_name="messagedispatchbatch",
            name="source",
            field=models.CharField(
                choices=[
                    ("group_manual", "Disparo manual de grupo"),
                    ("appointment_alert", "Alerta de agendamento"),
                    ("appointment_confirmation", "Confirmação de agendamento"),
                    ("review_plan_alert", "Alerta de plano de revisão"),
                    ("birthday_alert", "Alerta de aniversário"),
                    ("satisfaction_survey", "Pesquisa de satisfação"),
                    ("command", "Comando"),
                ],
                max_length=32,
                verbose_name="Origem",
            ),
        ),
        migrations.AlterField(
            model_name="scheduledoutboundmessage",
            name="source",
            field=models.CharField(
                choices=[
                    ("appointment_alert", "Alerta de agendamento"),
                    ("appointment_confirmation", "Confirmação de agendamento"),
                    ("review_plan_alert", "Alerta de plano de revisão"),
                    ("birthday_alert", "Alerta de aniversário"),
                    ("satisfaction_survey", "Pesquisa de satisfação"),
                ],
                default="appointment_alert",
                max_length=32,
                verbose_name="Origem",
            ),
        ),
        migrations.RunPython(backfill_appointment_confirmation_templates, noop_reverse),
    ]
