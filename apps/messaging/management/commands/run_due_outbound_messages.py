from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.messaging.application.services.outbound_dispatch import process_due_outbound_messages


class Command(BaseCommand):
    help = "Processa mensagens outbound vencidas (alertas de agendamento) e publica no RabbitMQ."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: Any, **options: Any) -> None:
        limit = int(options.get("limit") or 100)
        result = process_due_outbound_messages(limit=limit)
        self.stdout.write(
            self.style.SUCCESS(
                f"Outbound processados: claimed={result.claimed} sent={result.sent} failed={result.failed}."
            )
        )
