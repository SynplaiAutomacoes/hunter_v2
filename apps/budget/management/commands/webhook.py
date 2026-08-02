from __future__ import annotations

from argparse import ArgumentParser
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.core.infrastructure.services import build_absolute_app_url
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.synplaisign import WorkshopSynplaiSignError, provision_workshop_synplaisign

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Provision/ensure SynplaiSign API keys and webhooks for workshops"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Falha o comando caso alguma oficina nao possa ser sincronizada.",
        )
        parser.add_argument(
            "--workshop-id",
            type=int,
            default=None,
            help="Provisiona apenas a oficina informada.",
        )

    def handle(self, *args: object, **options: object) -> None:
        strict = bool(options["strict"])
        workshop_id = options.get("workshop_id")

        if not getattr(settings, "APP_BASE_URL", "").rstrip("/"):
            warning_message = "APP_BASE_URL nao configurado; usando fallback local para sincronizar webhook"
            logger.warning(warning_message)
            self.stderr.write(self.style.WARNING(warning_message))

        if not str(getattr(settings, "SYNPLAISIGN_MASTER_KEY", "") or "").strip():
            message = "SYNPLAISIGN_MASTER_KEY nao configurado; nenhuma oficina sera provisionada"
            logger.warning(message)
            if strict:
                raise CommandError(message)
            self.stderr.write(self.style.WARNING(message))
            return

        webhook_url = build_absolute_app_url(path=reverse("budget:signature_webhook"))
        workshops = Workshop.objects.all().order_by("pk")
        if workshop_id is not None:
            workshops = workshops.filter(pk=workshop_id)

        synced = 0
        failed = 0
        for workshop in workshops.iterator():
            try:
                provision_workshop_synplaisign(workshop=workshop, webhook_url=webhook_url)
                synced += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"SynplaiSign provisionado: workshop={workshop.pk} key_id={workshop.synplaisign_api_key_id or '-'} webhook={workshop.synplaisign_webhook_id or '-'}"
                    )
                )
            except WorkshopSynplaiSignError as exc:
                failed += 1
                message = f"SynplaiSign nao sincronizado para workshop={workshop.pk}: {exc}"
                logger.warning(message)
                self.stderr.write(self.style.WARNING(message))
                if strict:
                    raise CommandError(message) from exc

        self.stdout.write(self.style.SUCCESS(f"Concluido. sincronizados={synced} falhas={failed} url={webhook_url}"))
