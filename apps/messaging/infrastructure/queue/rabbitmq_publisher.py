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
    _CONTROL_QUEUE = "hunter.workshops.control"

    def __init__(self, host: str, port: int, username: str, password: str) -> None:
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
            logger.info("rabbitmq_connected", extra={"host": host, "port": port})
        except Exception as e:
            raise RabbitMQPublisherError(f"Failed to connect to RabbitMQ at {host}:{port}: {e}") from e

    @staticmethod
    def _queue_name_for(workshop_id: int) -> str:
        return f"hunter.message.dispatch.workshop.{workshop_id}"

    def publish_dispatch_item(self, item: DispatchItem, workshop_id: int) -> None:
        if self._channel is None or self._connection is None or self._connection.is_closed:
            raise RabbitMQPublisherError("RabbitMQ connection is closed")

        queue = self._queue_name_for(workshop_id)

        try:
            self._channel.queue_declare(queue=queue, durable=True)
            payload = json.dumps(asdict(item)).encode("utf-8")
            self._channel.basic_publish(
                exchange="",
                routing_key=queue,
                body=payload,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
        except Exception as e:
            raise RabbitMQPublisherError(f"Failed to publish message: {e}") from e

    def publish_workshop_control(self, workshop_id: int, whatsapp_instance_name: str = "") -> None:
        if self._channel is None or self._connection is None or self._connection.is_closed:
            raise RabbitMQPublisherError("RabbitMQ connection is closed")

        try:
            self._channel.queue_declare(queue=self._CONTROL_QUEUE, durable=True)
            payload = json.dumps(
                {
                    "workshop_id": workshop_id,
                    "whatsapp_instance_name": whatsapp_instance_name,
                }
            ).encode("utf-8")
            self._channel.basic_publish(
                exchange="",
                routing_key=self._CONTROL_QUEUE,
                body=payload,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
        except Exception as e:
            raise RabbitMQPublisherError(f"Failed to publish control message: {e}") from e

    def close(self) -> None:
        try:
            if self._connection and not self._connection.is_closed:
                self._connection.close()
        except Exception as e:
            logger.warning("rabbitmq_close_error", extra={"error": str(e)})
