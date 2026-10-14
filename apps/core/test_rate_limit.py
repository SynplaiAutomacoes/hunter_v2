from __future__ import annotations

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.infrastructure.rate_limit import check_rate_limit, client_ip_from_request
from apps.core.presentation.middlewares import BotProtectionMiddleware, RateLimitMiddleware


class RateLimitHelperTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_allows_until_limit_then_blocks(self) -> None:
        first = check_rate_limit(bucket="t", key="1.1.1.1", limit=2, window_seconds=60)
        second = check_rate_limit(bucket="t", key="1.1.1.1", limit=2, window_seconds=60)
        third = check_rate_limit(bucket="t", key="1.1.1.1", limit=2, window_seconds=60)
        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertFalse(third.allowed)
        self.assertGreater(third.retry_after, 0)

    def test_client_ip_prefers_forwarded_for(self) -> None:
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="9.9.9.9, 8.8.8.8")
        self.assertEqual(client_ip_from_request(request), "9.9.9.9")


@override_settings(
    RATE_LIMIT_ENABLED=True,
    RATE_LIMIT_WINDOW_SECONDS=60,
    RATE_LIMIT_GLOBAL_PER_MINUTE=2,
    RATE_LIMIT_AUTH_PER_MINUTE=100,
    BOT_PROTECTION_ENABLED=False,
)
class RateLimitMiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.factory = RequestFactory()

    def test_returns_429_when_global_limit_exceeded(self) -> None:
        def get_response(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = RateLimitMiddleware(get_response)
        request = self.factory.get("/core/")
        request.META["REMOTE_ADDR"] = "2.2.2.2"
        request.request_id = "req-1"

        self.assertEqual(middleware(request).status_code, 200)
        self.assertEqual(middleware(request).status_code, 200)
        blocked = middleware(request)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked["Retry-After"], blocked.get("Retry-After"))
        self.assertEqual(blocked["X-Request-ID"], "req-1")


@override_settings(BOT_PROTECTION_ENABLED=True, BOT_BLOCKED_USER_AGENTS=["scrapy", "ahrefs"])
class BotProtectionMiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_blocks_known_scraper_user_agent(self) -> None:
        def get_response(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = BotProtectionMiddleware(get_response)
        request = self.factory.get("/accounts/login/", HTTP_USER_AGENT="Scrapy/2.11")
        self.assertEqual(middleware(request).status_code, 403)

    def test_blocks_empty_user_agent_on_accounts(self) -> None:
        def get_response(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = BotProtectionMiddleware(get_response)
        request = self.factory.get("/accounts/login/")
        request.META.pop("HTTP_USER_AGENT", None)
        self.assertEqual(middleware(request).status_code, 403)

    def test_sets_x_robots_tag_on_html(self) -> None:
        def get_response(request):
            from django.http import HttpResponse

            return HttpResponse("<html></html>", content_type="text/html")

        middleware = BotProtectionMiddleware(get_response)
        request = self.factory.get("/core/", HTTP_USER_AGENT="Mozilla/5.0")
        response = middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
