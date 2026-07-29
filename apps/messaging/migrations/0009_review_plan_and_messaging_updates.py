# Generated manually — rename oil_change choices and backfill default message templates

from django.db import migrations, models


def rename_oil_change_choice_values(apps, schema_editor):
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")
    ScheduledOutboundMessage = apps.get_model("messaging", "ScheduledOutboundMessage")
    MessageDispatchBatch = apps.get_model("messaging", "MessageDispatchBatch")

    MessageTemplate.objects.filter(template_type="oil_change").update(template_type="review_plan")
    ScheduledOutboundMessage.objects.filter(source="oil_change_alert").update(source="review_plan_alert")
    MessageDispatchBatch.objects.filter(source="oil_change_alert").update(source="review_plan_alert")


def reverse_rename_oil_change_choice_values(apps, schema_editor):
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")
    ScheduledOutboundMessage = apps.get_model("messaging", "ScheduledOutboundMessage")
    MessageDispatchBatch = apps.get_model("messaging", "MessageDispatchBatch")

    MessageTemplate.objects.filter(template_type="review_plan").update(template_type="oil_change")
    ScheduledOutboundMessage.objects.filter(source="review_plan_alert").update(source="oil_change_alert")
    MessageDispatchBatch.objects.filter(source="review_plan_alert").update(source="oil_change_alert")


DEFAULT_BIRTHDAY_MESSAGE = """Oi %%nome%%, tudo bem?

Passando aqui para desejar um Feliz Aniversário!

A equipe da %%nome_oficina%% deseja a você um dia muito especial, cheio de alegria.

Conte com a gente sempre que precisar cuidar do seu veículo."""

DEFAULT_APPOINTMENT_MESSAGE = """Oi %%nome%%, tudo bem?

Passando para lembrar do seu agendamento na %%nome_oficina%%.

Data: %%data_agendamento%%
Horário: %%hora_agendamento%%

Até lá!"""

DEFAULT_REVIEW_PLAN_MESSAGE = """Oi %%nome%%, tudo bem?

A revisão do seu veículo %%modelo%% (placa %%placa%%) está chegando perto.

Agende um horário na %%nome_oficina%% para manter tudo em dia e rodar com segurança."""

DEFAULT_SATISFACTION_MESSAGE = """Oi %%nome%%, tudo bem?
Faz um tempinho que você esteve na %%nome_oficina%% para um serviço no seu carro, e ficamos curiosos: como foi?

Sua avaliação nos ajuda muito a melhorar cada vez mais.

Clique aqui: %%link-avaliacao%%"""

DEFAULT_MESSAGE_TEMPLATES = {
    "birthday": ("Aniversário", DEFAULT_BIRTHDAY_MESSAGE),
    "appointment": ("Agendamento", DEFAULT_APPOINTMENT_MESSAGE),
    "review_plan": ("Plano de revisão", DEFAULT_REVIEW_PLAN_MESSAGE),
    "satisfaction": ("Avaliação", DEFAULT_SATISFACTION_MESSAGE),
}


def backfill_default_message_templates(apps, schema_editor):
    Workshop = apps.get_model("workshops", "Workshop")
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")

    for workshop in Workshop.objects.all().iterator():
        existing_active_types = set(
            MessageTemplate.objects.filter(
                workshop_id=workshop.pk,
                template_type__in=DEFAULT_MESSAGE_TEMPLATES.keys(),
                is_active=True,
            ).values_list("template_type", flat=True)
        )
        for template_type, (name, message) in DEFAULT_MESSAGE_TEMPLATES.items():
            if template_type in existing_active_types:
                continue
            candidate_name = name
            suffix = 2
            while MessageTemplate.objects.filter(workshop_id=workshop.pk, name__iexact=candidate_name).exists():
                candidate_name = f"{name} {suffix}"
                suffix += 1
            MessageTemplate.objects.create(
                workshop_id=workshop.pk,
                name=candidate_name,
                message=message,
                template_type=template_type,
                is_active=True,
            )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("messaging", "0008_typed_templates_and_satisfaction_reviews"),
        ("workshops", "0038_review_plan_and_messaging_updates"),
    ]

    operations = [
        migrations.RunPython(rename_oil_change_choice_values, reverse_rename_oil_change_choice_values),
        migrations.AlterField(
            model_name="messagedispatchbatch",
            name="source",
            field=models.CharField(
                choices=[
                    ("group_manual", "Disparo manual de grupo"),
                    ("appointment_alert", "Alerta de agendamento"),
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
            model_name="messagetemplate",
            name="template_type",
            field=models.CharField(
                choices=[
                    ("generic", "Genérico"),
                    ("review_plan", "Plano de revisão"),
                    ("birthday", "Aniversário"),
                    ("appointment", "Agendamento"),
                    ("satisfaction", "Avaliação"),
                ],
                db_index=True,
                default="generic",
                max_length=32,
                verbose_name="Tipo",
            ),
        ),
        migrations.AlterField(
            model_name="scheduledoutboundmessage",
            name="source",
            field=models.CharField(
                choices=[
                    ("appointment_alert", "Alerta de agendamento"),
                    ("review_plan_alert", "Alerta de plano de revisão"),
                    ("birthday_alert", "Alerta de aniversário"),
                    ("satisfaction_survey", "Pesquisa de satisfação"),
                ],
                default="appointment_alert",
                max_length=32,
                verbose_name="Origem",
            ),
        ),
        migrations.RunPython(backfill_default_message_templates, noop_reverse),
    ]
