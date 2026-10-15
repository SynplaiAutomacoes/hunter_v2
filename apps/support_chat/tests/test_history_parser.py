from django.test import SimpleTestCase

from apps.support_chat.infrastructure.history_parser import normalize_role, parse_history_payload


class HistoryParserTests(SimpleTestCase):
    def test_parses_confirmed_envelope(self) -> None:
        payload = {
            "id_oficina": 19,
            "id_usuario": 20,
            "session_id": "abc",
            "mensagens": [
                {"role": "user", "content": "qual é a os de cortesia?"},
                {"role": "assistant", "content": "Foi a OS 123."},
            ],
            "atualizado_em": "2026-10-13T00:00:00Z",
        }
        messages = parse_history_payload(payload)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].text, "Foi a OS 123.")

    def test_tolerates_aliases_and_empty(self) -> None:
        self.assertEqual(normalize_role("human"), "user")
        self.assertEqual(normalize_role("ai"), "assistant")
        self.assertEqual(parse_history_payload({"mensagens": "invalido"}), [])
        self.assertEqual(parse_history_payload({"mensagens": [{"role": "user", "content": "  "}]}), [])
