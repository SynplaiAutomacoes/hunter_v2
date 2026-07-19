from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.messaging.application.services.outbound_dispatch import process_due_outbound_messages


class Command(BaseCommand):
    help = "Processa mensagens outbound vencidas (alertas de agendamento) e publica no RabbitMQ."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignora a janela de horário comercial e processa mesmo fora do expediente.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit = int(options.get("limit") or 100)
        force = bool(options.get("force"))
        result = process_due_outbound_messages(limit=limit, force=force)
        if result.skipped_outside_hours:
            self.stdout.write(self.style.WARNING("Outbound ignorado: fora do horário comercial configurado."))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Outbound processados: claimed={result.claimed} sent={result.sent} failed={result.failed}."
            )
        )
