from __future__ import annotations

from apps.messaging.models import MessageTemplate
from apps.workshops.models.workshops import Workshop

DEFAULT_BIRTHDAY_MESSAGE = """Oi %%primeiro_nome%%, tudo bem?

Passando aqui para desejar um Feliz Aniversário!

A equipe da %%nome_fantasia%% deseja a você um dia muito especial, cheio de alegria.

Conte com a gente sempre que precisar cuidar do seu veículo."""

DEFAULT_APPOINTMENT_MESSAGE = """Oi %%primeiro_nome%%, tudo bem?

Passando para lembrar do seu agendamento na %%nome_fantasia%%.

Data: %%data_agendamento%%
Horário: %%hora_agendamento%%

Até lá!"""

DEFAULT_APPOINTMENT_CONFIRMATION_MESSAGE = """Oi %%primeiro_nome%%, tudo bem?

Seu agendamento na %%nome_fantasia%% foi confirmado.

Data: %%data_agendamento%%
Horário: %%hora_agendamento%%

Qualquer dúvida, estamos à disposição."""

DEFAULT_REVIEW_PLAN_MESSAGE = """Oi %%primeiro_nome%%, tudo bem?

A revisão do seu veículo %%modelo%% (placa %%placa%%) está chegando perto.

Agende um horário na %%nome_fantasia%% para manter tudo em dia e rodar com segurança."""

DEFAULT_SATISFACTION_MESSAGE = """Oi %%primeiro_nome%%, tudo bem?
Faz um tempinho que você esteve na %%nome_fantasia%% para um serviço no seu carro, e ficamos curiosos: como foi?

Sua avaliação nos ajuda muito a melhorar cada vez mais.

Clique aqui: %%link-avaliacao%%"""

DEFAULT_MESSAGE_TEMPLATES: dict[str, tuple[str, str]] = {
    MessageTemplate.TemplateType.BIRTHDAY: ("Aniversário", DEFAULT_BIRTHDAY_MESSAGE),
    MessageTemplate.TemplateType.APPOINTMENT: ("Agendamento", DEFAULT_APPOINTMENT_MESSAGE),
    MessageTemplate.TemplateType.APPOINTMENT_CONFIRMATION: ("Confirmação de agendamento", DEFAULT_APPOINTMENT_CONFIRMATION_MESSAGE),
    MessageTemplate.TemplateType.REVIEW_PLAN: ("Plano de revisão", DEFAULT_REVIEW_PLAN_MESSAGE),
    MessageTemplate.TemplateType.SATISFACTION: ("Avaliação", DEFAULT_SATISFACTION_MESSAGE),
}


def create_default_message_templates(*, workshop: Workshop) -> None:
    """Cria as mensagens padrão (aniversário, agendamento, plano de revisão, avaliação) para uma nova oficina."""
    templates_to_create = [
        MessageTemplate(
            workshop=workshop,
            name=name,
            message=message,
            template_type=template_type,
            is_active=True,
        )
        for template_type, (name, message) in DEFAULT_MESSAGE_TEMPLATES.items()
    ]
    MessageTemplate.objects.bulk_create(templates_to_create)


def backfill_missing_default_message_templates(*, workshop: Workshop) -> int:
    """Seeds any special-type template a workshop doesn't already have an active copy of.

    Skips types that already have an active template so customized messages are preserved.
    """
    existing_active_types = set(
        MessageTemplate.objects.filter(
            workshop=workshop,
            template_type__in=DEFAULT_MESSAGE_TEMPLATES.keys(),
            is_active=True,
        ).values_list("template_type", flat=True)
    )

    missing_types = [template_type for template_type in DEFAULT_MESSAGE_TEMPLATES if template_type not in existing_active_types]
    if not missing_types:
        return 0

    templates_to_create = []
    for template_type in missing_types:
        name, message = DEFAULT_MESSAGE_TEMPLATES[template_type]
        candidate_name = name
        suffix = 2
        while MessageTemplate.objects.filter(workshop=workshop, name__iexact=candidate_name).exists():
            candidate_name = f"{name} {suffix}"
            suffix += 1
        templates_to_create.append(
            MessageTemplate(
                workshop=workshop,
                name=candidate_name,
                message=message,
                template_type=template_type,
                is_active=True,
            )
        )

    MessageTemplate.objects.bulk_create(templates_to_create)
    return len(templates_to_create)
