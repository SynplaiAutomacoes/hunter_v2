from __future__ import annotations

from django.test import SimpleTestCase

from apps.messaging.rendering import render_message_template
from apps.messaging.variables import get_variable_definition_map


class RenderMessageTemplateCaseInsensitiveTests(SimpleTestCase):
    def test_variable_tokens_are_matched_case_insensitively(self) -> None:
        class CustomerStub:
            name = "Maria Silva"
            email = "maria@example.com"

        customer = CustomerStub()
        rendered = render_message_template(
            "Ola %%Nome%%, email %%Email%% / %%email%% / %%NOME%%",
            customer=customer,
        )

        self.assertEqual(
            rendered,
            "Ola Maria Silva, email maria@example.com / maria@example.com / Maria Silva",
        )

    def test_unknown_token_is_left_unchanged(self) -> None:
        rendered = render_message_template("Token %%Desconhecido%% permanece")
        self.assertEqual(rendered, "Token %%Desconhecido%% permanece")


class WorkshopCompanyVariableTests(SimpleTestCase):
    def test_nome_oficina_variable_was_removed(self) -> None:
        self.assertNotIn("nome_oficina", get_variable_definition_map())

    def test_primeiro_nome_extracts_first_token_and_nome_keeps_full_name(self) -> None:
        class CustomerStub:
            name = "Maria Silva Santos"

        self.assertIn("primeiro_nome", get_variable_definition_map())
        self.assertIn("nome", get_variable_definition_map())
        rendered = render_message_template(
            "Oi %%primeiro_nome%% / %%nome%%",
            customer=CustomerStub(),
        )
        self.assertEqual(rendered, "Oi Maria / Maria Silva Santos")

    def test_primeiro_nome_handles_single_name_and_empty(self) -> None:
        class SingleNameStub:
            name = "Maria"

        class EmptyNameStub:
            name = "   "

        self.assertEqual(
            render_message_template("%%primeiro_nome%%", customer=SingleNameStub()),
            "Maria",
        )
        self.assertEqual(
            render_message_template("%%primeiro_nome%%", customer=EmptyNameStub()),
            "",
        )

    def test_razao_social_and_nome_fantasia_fall_back_to_workshop_name(self) -> None:
        class WorkshopStub:
            name = "Oficina Fallback"

            def _get_webmania_company(self):
                return None

        rendered = render_message_template(
            "RS: %%razao_social%% / NF: %%nome_fantasia%%",
            workshop=WorkshopStub(),
        )
        self.assertEqual(rendered, "RS: Oficina Fallback / NF: Oficina Fallback")

    def test_razao_social_and_nome_fantasia_use_company_fields(self) -> None:
        class CompanyStub:
            razao_social = "Razao Social LTDA"
            nome_fantasia = "Fantasia Auto"

        class WorkshopStub:
            name = "Oficina Fallback"

            def _get_webmania_company(self):
                return CompanyStub()

        rendered = render_message_template(
            "RS: %%razao_social%% / NF: %%nome_fantasia%%",
            workshop=WorkshopStub(),
        )
        self.assertEqual(rendered, "RS: Razao Social LTDA / NF: Fantasia Auto")
