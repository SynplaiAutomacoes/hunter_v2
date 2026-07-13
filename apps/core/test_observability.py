from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.logging_filters import clear_request_context, get_dependency_timing, record_dependency_timing, reset_dependency_timing
from apps.core.observability import observe_dependency_call
from apps.core.presentation.middlewares import RequestIdMiddleware, RequestPerformanceLoggingMiddleware


class RequestIdMiddlewareTests(SimpleTestCase):
    def test_adds_request_id_header(self) -> None:
        request = RequestFactory().get("/accounts/login/")
        middleware = RequestIdMiddleware(lambda _: HttpResponse("ok"))

        response = middleware(request)

        self.assertIn("X-Request-ID", response)
        self.assertTrue(response["X-Request-ID"])
        self.assertTrue(getattr(request, "request_id", None))


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
        logger_mock.error.assert_not_called()
        record_http_request_mock.assert_called_once()
        annotate_current_span_mock.assert_called_once()
        self.assertEqual(change_active_requests_mock.call_count, 2)

        _, info_kwargs = logger_mock.info.call_args
        self.assertEqual(info_kwargs["extra"]["route"], "accounts:login")
        self.assertEqual(info_kwargs["extra"]["status_code"], 200)
        self.assertIn("dependency_time_ms", info_kwargs["extra"])
        self.assertIn("dependency_call_count", info_kwargs["extra"])

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=False, PERF_LOG_MIN_MS=300)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_logs_error_for_server_error_request(
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
        logger_mock.error.assert_called_once()
        logger_mock.warning.assert_not_called()
        logger_mock.info.assert_not_called()
        annotate_current_span_mock.assert_called_once()
        self.assertEqual(change_active_requests_mock.call_count, 2)

        record_kwargs = record_http_request_mock.call_args.kwargs
        self.assertTrue(record_kwargs["attributes"]["error"])

        _, error_kwargs = logger_mock.error.call_args
        self.assertEqual(error_kwargs["extra"]["route"], "finance:nfe_emit")
        self.assertEqual(error_kwargs["extra"]["status_code"], 503)
        self.assertNotIn("exc_info", error_kwargs)

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=False, PERF_LOG_MIN_MS=300)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_logs_error_with_exc_info_when_request_raises(
        self,
        logger_mock: Mock,
        change_active_requests_mock: Mock,
        record_http_request_mock: Mock,
        annotate_current_span_mock: Mock,
    ) -> None:
        request = self.factory.get("/collaborators/1/update/")
        setattr(
            request,
            "resolver_match",
            SimpleNamespace(view_name="collaborators:collaborator_update", route="collaborators/<int:pk>/update/"),
        )
        setattr(request, "request_id", "req-exc")

        def _raise(_request: object) -> HttpResponse:
            raise RuntimeError("boom")

        middleware = RequestPerformanceLoggingMiddleware(_raise)

        with self.assertRaises(RuntimeError):
            middleware(request)

        logger_mock.error.assert_called_once()
        logger_mock.warning.assert_not_called()
        logger_mock.info.assert_not_called()

        _, error_kwargs = logger_mock.error.call_args
        self.assertEqual(error_kwargs["extra"]["route"], "collaborators:collaborator_update")
        self.assertEqual(error_kwargs["extra"]["status_code"], 500)
        self.assertIsInstance(error_kwargs["exc_info"], RuntimeError)
        self.assertEqual(str(error_kwargs["exc_info"]), "boom")

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=False, PERF_LOG_MIN_MS=300)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_logs_error_with_exc_info_when_django_converts_exception_to_500(
        self,
        logger_mock: Mock,
        change_active_requests_mock: Mock,
        record_http_request_mock: Mock,
        annotate_current_span_mock: Mock,
    ) -> None:
        """Mirrors Django convert_exception_to_response: exception becomes 500 without re-raising."""
        request = self.factory.post("/collaborators/50/edit/")
        setattr(
            request,
            "resolver_match",
            SimpleNamespace(view_name="collaborators:collaborator_update", route="collaborators/<int:pk>/edit/"),
        )
        setattr(request, "request_id", "req-django-500")
        boom = RuntimeError("null value in column transport_allowance_daily")

        middleware = RequestPerformanceLoggingMiddleware(lambda _: HttpResponse("erro", status=500))
        middleware.process_exception(request, boom)

        response = middleware(request)

        self.assertEqual(response.status_code, 500)
        logger_mock.error.assert_called_once()
        _, error_kwargs = logger_mock.error.call_args
        self.assertIs(error_kwargs["exc_info"], boom)
        self.assertEqual(error_kwargs["extra"]["status_code"], 500)

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=False, PERF_LOG_MIN_MS=50)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_logs_warning_for_slow_successful_request(
        self,
        logger_mock: Mock,
        change_active_requests_mock: Mock,
        record_http_request_mock: Mock,
        annotate_current_span_mock: Mock,
    ) -> None:
        request = self.factory.get("/accounts/login/")
        setattr(request, "resolver_match", SimpleNamespace(view_name="accounts:login", route="accounts/login/"))
        setattr(request, "request_id", "req-slow")

        def _slow_ok(_request: object) -> HttpResponse:
            time.sleep(0.06)
            return HttpResponse("ok", status=200)

        middleware = RequestPerformanceLoggingMiddleware(_slow_ok)

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        logger_mock.warning.assert_called_once()
        logger_mock.error.assert_not_called()
        logger_mock.info.assert_not_called()

        _, warning_kwargs = logger_mock.warning.call_args
        self.assertEqual(warning_kwargs["extra"]["status_code"], 200)
        self.assertGreaterEqual(warning_kwargs["extra"]["duration_ms"], 50)

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=False, PERF_LOG_MIN_MS=300)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_includes_workshop_id_from_session(
        self,
        logger_mock: Mock,
        change_active_requests_mock: Mock,
        record_http_request_mock: Mock,
        annotate_current_span_mock: Mock,
    ) -> None:
        request = self.factory.get("/budget/")
        setattr(request, "resolver_match", SimpleNamespace(view_name="budget:list", route="budget/"))
        setattr(request, "request_id", "req-workshop")
        request.session = {"active_workshop_id": 42}
        middleware = RequestPerformanceLoggingMiddleware(lambda _: HttpResponse("ok", status=200))

        middleware(request)

        _, info_kwargs = logger_mock.info.call_args
        self.assertEqual(info_kwargs["extra"]["workshop_id"], 42)

    @override_settings(PERF_LOGGING_ENABLED=True, PERF_LOG_QUERIES=True, PERF_LOG_MIN_MS=300)
    @patch("apps.core.presentation.middlewares.annotate_current_span")
    @patch("apps.core.presentation.middlewares.record_http_request")
    @patch("apps.core.presentation.middlewares.change_active_requests")
    @patch("apps.core.presentation.middlewares.logger")
    def test_captures_sql_timing_when_enabled(
        self,
        logger_mock: Mock,
        change_active_requests_mock: Mock,
        record_http_request_mock: Mock,
        annotate_current_span_mock: Mock,
    ) -> None:
        request = self.factory.get("/accounts/login/")
        setattr(request, "resolver_match", SimpleNamespace(view_name="accounts:login", route="accounts/login/"))
        setattr(request, "request_id", "req-sql")

        with patch("apps.core.presentation.middlewares.SqlTimingWrapper") as sql_wrapper_cls:
            sql_wrapper = Mock()
            sql_wrapper.collect.return_value = SimpleNamespace(query_count=3, sql_time_ms=12.5)
            sql_wrapper_cls.return_value = sql_wrapper
            middleware = RequestPerformanceLoggingMiddleware(lambda _: HttpResponse("ok", status=200))
            middleware(request)

        _, info_kwargs = logger_mock.info.call_args
        self.assertEqual(info_kwargs["extra"]["query_count"], 3)
        self.assertEqual(info_kwargs["extra"]["sql_time_ms"], 12.5)


class DependencyTimingAccumulatorTests(SimpleTestCase):
    def tearDown(self) -> None:
        clear_request_context()

    def test_records_dependency_timing_totals(self) -> None:
        reset_dependency_timing()
        record_dependency_timing(10.5)
        record_dependency_timing(4.5)
        dependency_time_ms, dependency_call_count = get_dependency_timing()
        self.assertEqual(dependency_time_ms, 15.0)
        self.assertEqual(dependency_call_count, 2)


class DependencyObservabilityTests(SimpleTestCase):
    def tearDown(self) -> None:
        clear_request_context()

    @patch("apps.core.observability.record_dependency_call")
    def test_dependency_helper_records_success(self, record_dependency_call_mock: Mock) -> None:
        logger_mock = Mock()
        reset_dependency_timing()

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
        dependency_time_ms, dependency_call_count = get_dependency_timing()
        self.assertEqual(dependency_call_count, 1)
        self.assertGreaterEqual(dependency_time_ms, 0.0)

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
