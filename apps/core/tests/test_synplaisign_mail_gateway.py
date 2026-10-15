from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.infrastructure.gateways.synplaisign import SynplaiSignGatewayError, send_mail


@override_settings(SYNPLAISIGN_BASE_URL="https://synplaisign.example")
class SynplaiSignMailGatewayTests(SimpleTestCase):
    @patch("apps.core.infrastructure.gateways.synplaisign.requests.post")
    def test_send_mail_posts_json_payload(self, post: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {"ok": True, "id": "re_1"}
        post.return_value = response

        result = send_mail(
            api_key="sk_live_test",
            to="cliente@oficina.com",
            subject="Orçamento #938",
            html="<p>Segue o orçamento.</p>",
            from_email="Oficina <noreply@oficina.com>",
        )

        self.assertEqual(result["id"], "re_1")
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://synplaisign.example/mail")
        self.assertEqual(post.call_args.kwargs["headers"]["x-api-key"], "sk_live_test")
        self.assertEqual(
            post.call_args.kwargs["json"],
            {
                "to": "cliente@oficina.com",
                "subject": "Orçamento #938",
                "html": "<p>Segue o orçamento.</p>",
                "from": "Oficina <noreply@oficina.com>",
            },
        )

    @patch("apps.core.infrastructure.gateways.synplaisign.requests.post")
    def test_send_mail_omits_from_when_empty(self, post: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {"ok": True, "id": None}
        post.return_value = response

        send_mail(api_key="sk_live_test", to=["a@x.com"], subject="Hi", html="<p>x</p>")
        self.assertNotIn("from", post.call_args.kwargs["json"])

    def test_send_mail_rejects_long_subject(self) -> None:
        with self.assertRaises(SynplaiSignGatewayError):
            send_mail(api_key="sk_live_test", to="a@x.com", subject="x" * 201, html="<p>x</p>")
