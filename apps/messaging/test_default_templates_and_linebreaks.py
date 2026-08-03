from __future__ import annotations

from django.test import TestCase

from apps.customer.models import Customer
from apps.messaging.application.services.default_templates import (
    DEFAULT_APPOINTMENT_CONFIRMATION_MESSAGE,
    DEFAULT_APPOINTMENT_MESSAGE,
    DEFAULT_BIRTHDAY_MESSAGE,
    DEFAULT_MESSAGE_TEMPLATES,
    DEFAULT_REVIEW_PLAN_MESSAGE,
    DEFAULT_SATISFACTION_MESSAGE,
    backfill_missing_default_message_templates,
    create_default_message_templates,
)
from apps.messaging.infrastructure.forms.message_group_form import MessageTemplateForm
from apps.messaging.models import MessageTemplate
from apps.messaging.rendering import render_message_template
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Defaults {suffix}",
        cnpj=f"41.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class DefaultMessageTemplateTests(TestCase):
    def test_create_default_message_templates_creates_five_active_templates(self) -> None:
        workshop = create_workshop(suffix=1)

        create_default_message_templates(workshop=workshop)

        templates = list(MessageTemplate.objects.filter(workshop=workshop, is_active=True).order_by("template_type"))
        self.assertEqual(len(templates), 5)

        by_type = {row.template_type: row for row in templates}
        expected = {
            MessageTemplate.TemplateType.BIRTHDAY: ("Aniversário", DEFAULT_BIRTHDAY_MESSAGE),
            MessageTemplate.TemplateType.APPOINTMENT: ("Agendamento", DEFAULT_APPOINTMENT_MESSAGE),
            MessageTemplate.TemplateType.APPOINTMENT_CONFIRMATION: ("Confirmação de agendamento", DEFAULT_APPOINTMENT_CONFIRMATION_MESSAGE),
            MessageTemplate.TemplateType.REVIEW_PLAN: ("Plano de revisão", DEFAULT_REVIEW_PLAN_MESSAGE),
            MessageTemplate.TemplateType.SATISFACTION: ("Avaliação", DEFAULT_SATISFACTION_MESSAGE),
        }
        self.assertEqual(set(by_type), set(expected))
        for template_type, (name, message) in expected.items():
            self.assertEqual(by_type[template_type].name, name)
            self.assertEqual(by_type[template_type].message, message)
            self.assertIn("\n", by_type[template_type].message)

    def test_backfill_skips_types_that_already_have_active_template(self) -> None:
        workshop = create_workshop(suffix=2)
        custom_message = "Custom birthday %%nome%%"
        MessageTemplate.objects.create(
            workshop=workshop,
            name="Aniversário custom",
            message=custom_message,
            template_type=MessageTemplate.TemplateType.BIRTHDAY,
            is_active=True,
        )

        created = backfill_missing_default_message_templates(workshop=workshop)

        self.assertEqual(created, 4)
        birthday = MessageTemplate.objects.get(
            workshop=workshop,
            template_type=MessageTemplate.TemplateType.BIRTHDAY,
            is_active=True,
        )
        self.assertEqual(birthday.message, custom_message)
        self.assertEqual(
            MessageTemplate.objects.filter(
                workshop=workshop,
                template_type__in=DEFAULT_MESSAGE_TEMPLATES.keys(),
                is_active=True,
            ).count(),
            5,
        )


class MessageTemplateLinebreakTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=3)

    def test_clean_message_normalizes_crlf_and_preserves_blank_lines(self) -> None:
        form = MessageTemplateForm(
            data={
                "name": "Com quebras",
                "template_type": MessageTemplate.TemplateType.GENERIC,
                "message": "Linha 1\r\n\r\nLinha 3\r\n",
                "is_active": True,
            },
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        cleaned = form.cleaned_data["message"]
        self.assertNotIn("\r", cleaned)
        self.assertEqual(cleaned, "Linha 1\n\nlinha 3")
        self.assertIn("\n\n", cleaned)

    def test_render_message_template_preserves_line_breaks(self) -> None:
        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Linhas",
            cpf_or_cnpj="82345678901",
            email="linhas@example.com",
            phone="+5511988887777",
            accepts_messages=True,
        )
        rendered = render_message_template(
            DEFAULT_BIRTHDAY_MESSAGE,
            customer=customer,
            workshop=self.workshop,
        )
        self.assertIn("\n\n", rendered)
        self.assertIn("Cliente", rendered)
        self.assertNotIn("Cliente Linhas", rendered)
        self.assertIn(self.workshop.name, rendered)
        self.assertEqual(rendered.count("\n"), DEFAULT_BIRTHDAY_MESSAGE.count("\n"))
