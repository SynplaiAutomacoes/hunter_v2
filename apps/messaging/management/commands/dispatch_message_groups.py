from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.messaging.application.use_cases.dispatch_message_groups import (
    DispatchGroupsRequest,
    DispatchMessageGroupsUseCase,
)
from apps.messaging.infrastructure.queue.rabbitmq_publisher import RabbitMQPublisher
from apps.messaging.infrastructure.repositories.django_message_group_repository import (
    DjangoMessageGroupRepository,
)
from apps.messaging.infrastructure.services.segment_query_builder import resolve_segment

logger = logging.getLogger(__name__)


def _build_dispatch_use_case() -> DispatchMessageGroupsUseCase:
    queue_publisher = RabbitMQPublisher(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        username=settings.RABBITMQ_USER,
        password=settings.RABBITMQ_PASSWORD,
        queue_name=settings.RABBITMQ_QUEUE,
    )

    return DispatchMessageGroupsUseCase(
        group_repo=DjangoMessageGroupRepository(),
        segment_builder=resolve_segment,
        queue_publisher=queue_publisher,
    )


class Command(BaseCommand):
    help = "Dispara mensagens de todos os grupos ativos para o RabbitMQ"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--workshop-id",
            type=int,
            help="Filtrar o disparo para uma oficina especifica",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Iniciando disparo de grupos de mensagens...")

        try:
            use_case = _build_dispatch_use_case()
            request = DispatchGroupsRequest(workshop_id=options.get("workshop_id"))
            result = use_case.execute(request)

            self.stdout.write(f"Grupos processados: {result.total_groups}")
            self.stdout.write(f"Total de clientes na fila: {result.total_customers}")

            for group in result.groups:
                level = "WARNING" if group.error else "SUCCESS"
                self.stdout.write(self.style.WARNING(f"  [{level}] Grupo #{group.group_id} '{group.group_name}': {group.total_customers} clientes") if group.error else self.style.SUCCESS(f"  [OK] Grupo #{group.group_id} '{group.group_name}': {group.total_customers} clientes"))

            if result.errors:
                self.stderr.write(self.style.ERROR(f"\nErros encontrados ({len(result.errors)}):"))
                for error in result.errors:
                    self.stderr.write(self.style.ERROR(f"  - {error}"))

            self.stdout.write(self.style.SUCCESS("\nDisparo concluido com sucesso!"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Falha no disparo: {e}"))
            logger.exception("dispatch_message_groups_failed")
            raise
