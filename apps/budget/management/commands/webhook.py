from __future__ import annotations

from argparse import ArgumentParser
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.core.infrastructure.services import build_absolute_app_url
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.synplaisign import (
    WorkshopSynplaiSignError,
    get_workshop_synplaisign_api_key,
    get_workshop_synplaisign_owner_password,
    provision_workshop_synplaisign,
)

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
        parser.add_argument(
            "--force-recreate",
            action="store_true",
            help=(
                "Recria org/API key SynplaiSign mesmo se a oficina ja tiver chave local. "
                "Se outra oficina do mesmo owner ja tiver credenciais, reutiliza essa chave "
                "(SynplaiSign nao permite email de Owner duplicado)."
            ),
        )
        parser.add_argument(
            "--show-secrets",
            action="store_true",
            help="Exibe API key e senha aleatoria do OWNER SynplaiSign (texto puro) apos sincronizar.",
        )

    def handle(self, *args: object, **options: object) -> None:
        strict = bool(options["strict"])
        workshop_id = options.get("workshop_id")
        force_recreate = bool(options["force_recreate"])
        show_secrets = bool(options["show_secrets"])

        if force_recreate and workshop_id is None:
            raise CommandError("Use --workshop-id junto com --force-recreate (evita recriar todas as oficinas de uma vez).")

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
            previous_key_id = str(workshop.synplaisign_api_key_id or "").strip()
            had_key = bool(str(workshop.synplaisign_api_key or "").strip())
            try:
                provision_workshop_synplaisign(
                    workshop=workshop,
                    webhook_url=webhook_url,
                    force=force_recreate,
                )
                workshop.refresh_from_db(
                    fields=[
                        "synplaisign_api_key_id",
                        "synplaisign_api_key",
                        "synplaisign_owner_password",
                        "synplaisign_webhook_id",
                        "synplaisign_webhook_secret",
                    ]
                )
                synced += 1
                current_key_id = str(workshop.synplaisign_api_key_id or "").strip()
                sibling_shares_key = False
                if workshop.account_id and current_key_id:
                    sibling_shares_key = (
                        Workshop.objects.filter(account_id=workshop.account_id)
                        .exclude(pk=workshop.pk)
                        .filter(synplaisign_api_key_id=current_key_id)
                        .exclude(synplaisign_api_key_id="")
                        .exists()
                    )
                if force_recreate and had_key and current_key_id and current_key_id != previous_key_id:
                    action = "recriado"
                elif had_key:
                    action = "reutilizado"
                elif sibling_shares_key:
                    action = "reutilizado_owner"
                else:
                    action = "criado"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"SynplaiSign ok: workshop={workshop.pk} api_key={action} "
                        f"key_id={workshop.synplaisign_api_key_id or '-'} webhook={workshop.synplaisign_webhook_id or '-'}"
                    )
                )
                if show_secrets:
                    self._write_secrets(workshop)
            except WorkshopSynplaiSignError as exc:
                failed += 1
                message = f"SynplaiSign nao sincronizado para workshop={workshop.pk}: {exc}"
                logger.warning(message)
                self.stderr.write(self.style.WARNING(message))
                if strict:
                    raise CommandError(message) from exc

        self.stdout.write(self.style.SUCCESS(f"Concluido. sincronizados={synced} falhas={failed} url={webhook_url}"))

    def _write_secrets(self, workshop: Workshop) -> None:
        try:
            api_key = get_workshop_synplaisign_api_key(workshop)
        except WorkshopSynplaiSignError:
            api_key = "(ausente)"
        password = get_workshop_synplaisign_owner_password(workshop) or "(ausente)"
        self.stdout.write(f"  api_key={api_key}")
        self.stdout.write(f"  owner_password={password}")
