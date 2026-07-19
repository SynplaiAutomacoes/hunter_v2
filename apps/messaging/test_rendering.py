from __future__ import annotations

from django.test import SimpleTestCase

from apps.messaging.rendering import render_message_template


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
