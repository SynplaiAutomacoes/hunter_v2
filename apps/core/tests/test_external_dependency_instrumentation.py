from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.infrastructure.gateways.synplaisign import get_signed_document_download_url
from apps.core.infrastructure.services.webmania.nfe_consulta import consult_nfe_item
from apps.core.infrastructure.services.webmania.webmania_documents import download_webmania_document


@contextmanager
def _dependency_call_context(manager_mock: Mock):
    yield manager_mock


class ExternalDependencyInstrumentationTests(SimpleTestCase):
    @override_settings(SYNPLAISIGN_BASE_URL="https://synplaisign.example", SYNPLAISIGN_API_KEY="secret")
    @patch("apps.core.infrastructure.gateways.synplaisign.observe_dependency_call")
    @patch("apps.core.infrastructure.gateways.synplaisign.requests.get")
    def test_synplaisign_download_url_records_status_code(self, requests_get_mock: Mock, observe_dependency_call_mock: Mock) -> None:
        dependency_call_mock = Mock()
        observe_dependency_call_mock.side_effect = lambda **_: _dependency_call_context(dependency_call_mock)
        response_mock = Mock()
        response_mock.status_code = 200
        response_mock.json.return_value = {"url": "https://files.example/doc.pdf", "expiresIn": 3600}
        response_mock.raise_for_status.return_value = None
        requests_get_mock.return_value = response_mock

        result = get_signed_document_download_url(api_key="sk_live_workshop", envelope_id="env-1")

        self.assertEqual(result, "https://files.example/doc.pdf")
        dependency_call_mock.set_http_status_code.assert_called_once_with(200)

    @patch("apps.core.infrastructure.services.webmania.webmania_documents.build_webmania_headers", return_value={"Authorization": "Bearer x"})
    @patch("apps.core.infrastructure.services.webmania.webmania_documents.observe_dependency_call")
    @patch("apps.core.infrastructure.services.webmania.webmania_documents.requests.get")
    def test_webmania_document_download_records_status_code(
        self,
        requests_get_mock: Mock,
        observe_dependency_call_mock: Mock,
        _headers_mock: Mock,
    ) -> None:
        dependency_call_mock = Mock()
        observe_dependency_call_mock.side_effect = lambda **_: _dependency_call_context(dependency_call_mock)
        response_mock = Mock()
        response_mock.status_code = 200
        response_mock.content = b"pdf-bytes"
        response_mock.headers = {"Content-Type": "application/pdf", "Content-Disposition": "inline"}
        response_mock.raise_for_status.return_value = None
        requests_get_mock.return_value = response_mock

        result = download_webmania_document(workshop=SimpleNamespace(pk=1), url="https://webmania/doc.pdf")

        self.assertEqual(result.content, b"pdf-bytes")
        dependency_call_mock.set_http_status_code.assert_called_once_with(200)

    @patch("apps.core.infrastructure.services.webmania.nfe_consulta._build_headers", return_value={"Authorization": "Bearer x"})
    @patch("apps.core.infrastructure.services.webmania.nfe_consulta.observe_dependency_call")
    @patch("apps.core.infrastructure.services.webmania.nfe_consulta.requests.get")
    def test_nfe_consulta_records_status_code(
        self,
        requests_get_mock: Mock,
        observe_dependency_call_mock: Mock,
        _headers_mock: Mock,
    ) -> None:
        dependency_call_mock = Mock()
        observe_dependency_call_mock.side_effect = lambda **_: _dependency_call_context(dependency_call_mock)
        response_mock = Mock()
        response_mock.status_code = 200
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = {"status": "emitida"}
        requests_get_mock.return_value = response_mock
        item = SimpleNamespace(uuid="uuid-1", access_key="", workshop=SimpleNamespace(pk=10))

        result = consult_nfe_item(item=item)

        self.assertEqual(result["status"], "emitida")
        dependency_call_mock.set_http_status_code.assert_called_once_with(200)
