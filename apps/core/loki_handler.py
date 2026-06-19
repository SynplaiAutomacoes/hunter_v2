from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from typing import Any

import requests


class LokiHandler(logging.Handler):
    def __init__(
        self,
        url: str,
        labels: dict[str, str],
        user: str = "",
        api_key: str = "",
        batch_size: int = 50,
        flush_interval: float = 5.0,
        timeout: float = 5.0,
        max_buffer_size: int = 1000,
    ) -> None:
        super().__init__()
        self.url = url
        self.labels = labels
        self.user = user
        self.api_key = api_key
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.timeout = timeout
        self.max_buffer_size = max_buffer_size

        self._buffer: deque[tuple[int, str, str]] = deque(maxlen=max_buffer_size)
        self._lock = threading.Lock()
        self._shutdown = threading.Event()

        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            msg = msg.strip().replace("\n", " ").replace("\r", " ")
            timestamp_ns = int(record.created * 1e9)
            level = record.levelname.lower()
            with self._lock:
                self._buffer.append((timestamp_ns, msg, level))
        except Exception:
            self.handleError(record)

    def _flush_loop(self) -> None:
        while not self._shutdown.is_set():
            self._shutdown.wait(self.flush_interval)
            self._flush()

    def _flush(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            entries = list(self._buffer)
            self._buffer.clear()

        payload = self._build_payload(entries)

        auth: tuple[str, str] | None = None
        if self.user and self.api_key:
            auth = (self.user, self.api_key)

        try:
            response = requests.post(
                self.url,
                json=payload,
                auth=auth,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code >= 400:
                self._retry(payload, auth)
        except requests.RequestException:
            self._retry(payload, auth)

    def _retry(
        self,
        payload: dict[str, Any],
        auth: tuple[str, str] | None,
    ) -> None:
        try:
            requests.post(
                self.url,
                json=payload,
                auth=auth,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException:
            pass

    def _build_payload(self, entries: list[tuple[int, str, str]]) -> dict[str, Any]:
        streams_by_level: dict[str, list[list[str]]] = defaultdict(list)

        for ts, msg, level in entries:
            streams_by_level[level].append([str(ts), msg])

        streams = []
        for level, values in streams_by_level.items():
            stream_labels = {**self.labels, "level": level}
            streams.append(
                {
                    "stream": stream_labels,
                    "values": values,
                }
            )

        return {"streams": streams}

    def close(self) -> None:
        self._shutdown.set()
        self._flush()
        super().close()
