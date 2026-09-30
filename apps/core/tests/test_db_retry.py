"""Tests for deadlock retry helper."""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.db import OperationalError
from django.test import SimpleTestCase

from apps.core.infrastructure.db import retry_on_deadlock


class RetryOnDeadlockTests(SimpleTestCase):
    def test_returns_result_on_first_success(self) -> None:
        self.assertEqual(retry_on_deadlock(lambda: "ok"), "ok")

    def test_retries_deadlock_then_succeeds(self) -> None:
        calls = {"n": 0}

        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise OperationalError("deadlock detected")
            return "recovered"

        with patch("apps.core.infrastructure.db.time.sleep") as sleep_mock:
            self.assertEqual(retry_on_deadlock(flaky, attempts=3, backoff_seconds=0.01), "recovered")

        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_raises_after_exhausted_deadlock_retries(self) -> None:
        always_deadlock = Mock(side_effect=OperationalError("deadlock detected"))

        with patch("apps.core.infrastructure.db.time.sleep"):
            with self.assertRaises(OperationalError):
                retry_on_deadlock(always_deadlock, attempts=2, backoff_seconds=0.01)

        self.assertEqual(always_deadlock.call_count, 2)

    def test_non_deadlock_operational_error_is_not_retried(self) -> None:
        boom = Mock(side_effect=OperationalError("connection refused"))

        with self.assertRaises(OperationalError):
            retry_on_deadlock(boom, attempts=3)

        self.assertEqual(boom.call_count, 1)
