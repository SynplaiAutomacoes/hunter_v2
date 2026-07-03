from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.observability import observe_dependency_call
from apps.core.presentation.middlewares import RequestIdMiddleware, RequestPerformanceLoggingMiddleware


class RequestIdMiddlewareTests(SimpleTestCase):
    def test_adds_request_id_header(self) -> None:
        request = RequestFactory().get("/accounts/login/")
        middleware = RequestIdMiddleware(lambda _: HttpResponse("ok"))

        response = middleware(request)

        self.assertIn("X-Request-ID", response)
        self.assertTrue(response["X-Request-ID"])


class RequestPerformanceLoggingMiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=False, PERF_LOG_MIN_MS=300)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_logs_info_for_fast_request(
        self,
        logger_mock: Mock,
        change_active_requests_mock: Mock,
        record_http_request_mock: Mock,
        annotate_current_span_mock: Mock,
    ) -> None:
        request = self.factory.get("/accounts/login/")
        setattr(request, "resolver_match", SimpleNamespace(view_name="accounts:login", route="accounts/login/"))
        setattr(request, "request_id", "req-123")
        middleware = RequestPerformanceLoggingMiddleware(lambda _: HttpResponse("ok", status=200))

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        logger_mock.info.assert_called_once()
        logger_mock.warning.assert_not_called()
        record_http_request_mock.assert_called_once()
        annotate_current_span_mock.assert_called_once()
        self.assertEqual(change_active_requests_mock.call_count, 2)

        _, info_kwargs = logger_mock.info.call_args
        self.assertEqual(info_kwargs["extra"]["route"], "accounts:login")
        self.assertEqual(info_kwargs["extra"]["status_code"], 200)

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=False, PERF_LOG_MIN_MS=300)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_logs_warning_for_server_error_request(
        self,
        logger_mock: Mock,
        change_active_requests_mock: Mock,
        record_http_request_mock: Mock,
        annotate_current_span_mock: Mock,
    ) -> None:
        request = self.factory.get("/finance/nfe/")
        setattr(request, "resolver_match", SimpleNamespace(view_name="finance:nfe_emit", route="finance/nfe/"))
        setattr(request, "request_id", "req-500")
        middleware = RequestPerformanceLoggingMiddleware(lambda _: HttpResponse("erro", status=503))

        response = middleware(request)

        self.assertEqual(response.status_code, 503)
        logger_mock.warning.assert_called_once()
        logger_mock.info.assert_not_called()
        annotate_current_span_mock.assert_called_once()
        self.assertEqual(change_active_requests_mock.call_count, 2)

        record_kwargs = record_http_request_mock.call_args.kwargs
        self.assertTrue(record_kwargs["attributes"]["error"])

        _, warning_kwargs = logger_mock.warning.call_args
        self.assertEqual(warning_kwargs["extra"]["route"], "finance:nfe_emit")
        self.assertEqual(warning_kwargs["extra"]["status_code"], 503)


class DependencyObservabilityTests(SimpleTestCase):
    @patch("apps.core.observability.record_dependency_call")
    def test_dependency_helper_records_success(self, record_dependency_call_mock: Mock) -> None:
        logger_mock = Mock()

        with observe_dependency_call(
            logger=logger_mock,
            dependency_type="http",
            dependency_name="viacep",
            operation="lookup_cep",
            log_context={"cep": "01001000"},
        ) as dependency_call:
            dependency_call.set_http_status_code(200)

        logger_mock.info.assert_called_once()
        logger_mock.exception.assert_not_called()
        record_kwargs = record_dependency_call_mock.call_args.kwargs
        self.assertEqual(record_kwargs["attributes"]["dependency.name"], "viacep")
        self.assertEqual(record_kwargs["attributes"]["result"], "success")

    @patch("apps.core.observability.record_dependency_call")
    def test_dependency_helper_records_error(self, record_dependency_call_mock: Mock) -> None:
        logger_mock = Mock()

        with self.assertRaises(ValueError):
            with observe_dependency_call(
                logger=logger_mock,
                dependency_type="http",
                dependency_name="fipe",
                operation="request_json",
            ) as dependency_call:
                dependency_call.set_http_status_code(503)
                raise ValueError("boom")

        logger_mock.exception.assert_called_once()
        logger_mock.info.assert_not_called()
        record_kwargs = record_dependency_call_mock.call_args.kwargs
        self.assertEqual(record_kwargs["attributes"]["dependency.name"], "fipe")
        self.assertEqual(record_kwargs["attributes"]["result"], "error")
