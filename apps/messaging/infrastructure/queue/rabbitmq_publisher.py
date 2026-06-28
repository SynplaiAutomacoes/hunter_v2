from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

import pika

from apps.messaging.domain.value_objects import DispatchItem

logger = logging.getLogger(__name__)


class RabbitMQPublisherError(Exception):
    pass


class RabbitMQPublisher:
    def __init__(self, host: str, port: int, username: str, password: str, queue_name: str) -> None:
        self._queue_name = queue_name
        self._connection: pika.BlockingConnection | None = None
        self._channel: Any = None
        self._connect(host, port, username, password)

    def _connect(self, host: str, port: int, username: str, password: str) -> None:
        try:
            credentials = pika.PlainCredentials(username, password)
            parameters = pika.ConnectionParameters(
                host=host,
                port=port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue=self._queue_name, durable=True)
            logger.info("rabbitmq_connected", extra={"queue": self._queue_name, "host": host})
        except Exception as e:
            raise RabbitMQPublisherError(f"Failed to connect to RabbitMQ at {host}:{port}: {e}") from e

    def publish_dispatch_item(self, item: DispatchItem) -> None:
        if self._channel is None or self._connection is None or self._connection.is_closed:
            raise RabbitMQPublisherError("RabbitMQ connection is closed")

        try:
            payload = json.dumps(asdict(item)).encode("utf-8")
            self._channel.basic_publish(
                exchange="",
                routing_key=self._queue_name,
                body=payload,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
        except Exception as e:
            raise RabbitMQPublisherError(f"Failed to publish message: {e}") from e

    def close(self) -> None:
        try:
            if self._connection and not self._connection.is_closed:
                self._connection.close()
        except Exception as e:
            logger.warning("rabbitmq_close_error", extra={"error": str(e)})
