from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.stock.services.sefaz_distribution import (
    is_workshop_eligible_for_sefaz_sync,
    mask_cnpj_for_log,
    sync_sefaz_distribution_for_workshop,
)
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)


def is_inside_sefaz_auto_window(now: datetime | None = None) -> bool:
    """Retorna True se `now` está na janela do auto-sync (meio-dia ± tolerância OU noturna).

    Janela default (`America/Sao_Paulo`): execução única ~12:00 (±15min) + ciclo
    noturno 19:00–06:00 (início inclusivo, fim exclusivo). Tudo configurável via
    `SEFAZ_AUTO_SYNC_*` no settings. A janela noturna atravessa a meia-noite.
    """
    tz_name = getattr(settings, "SEFAZ_AUTO_SYNC_TIMEZONE", "America/Sao_Paulo") or "America/Sao_Paulo"
    try:
        tz = ZoneInfo(str(tz_name))
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")
    current = now if now is not None else timezone.localtime()
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)

    midday_hour = int(getattr(settings, "SEFAZ_AUTO_SYNC_MIDDAY_HOUR", 12))
    tolerance = int(getattr(settings, "SEFAZ_AUTO_SYNC_MIDDAY_TOLERANCE_MINUTES", 15))
    night_start = int(getattr(settings, "SEFAZ_AUTO_SYNC_NIGHT_START_HOUR", 19))
    night_end = int(getattr(settings, "SEFAZ_AUTO_SYNC_NIGHT_END_HOUR", 6))

    midday_minutes = (midday_hour % 24) * 60
    current_minutes = current.hour * 60 + current.minute
    if abs(current_minutes - midday_minutes) <= max(0, tolerance):
        return True

    hour = current.hour
    if night_start <= night_end:
        return night_start <= hour < night_end
    return hour >= night_start or hour < night_end


class Command(BaseCommand):
    help = (
        "Sincroniza a lista de NF-e do SEFAZ (Distribuição DF-e) para o cache "
        "SefazZipCache das oficinas elegíveis. Respeita throttle de 1h/oficina e "
        "janela configurável (SEFAZ_AUTO_SYNC_*). Nunca cria StockImport/movimentos."
    )

    def add_arguments(self, parser):
        parser.add_argument("--workshop-id", type=int, help="Limita a uma oficina específica.")
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Máximo de oficinas por ciclo (default: SEFAZ_AUTO_SYNC_LIMIT).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Lista elegíveis sem chamar o SEFAZ e sem salvar.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignora a janela de execução (nunca ignora throttle de 1h nem ausência de certificado).",
        )

    def handle(self, *args, **options):
        workshop_id = options.get("workshop_id")
        dry_run = bool(options.get("dry_run"))
        force = bool(options.get("force"))
        limit = options.get("limit") or int(getattr(settings, "SEFAZ_AUTO_SYNC_LIMIT", 100))

        enabled = bool(getattr(settings, "SEFAZ_AUTO_SYNC_ENABLED", True))
        if not enabled and not force:
            message = "sefaz_auto_sync_summary result=skipped_disabled processed=0 skipped=0 failed=0"
            logger.info(message)
            self.stdout.write(message)
            return

        if not force and not is_inside_sefaz_auto_window():
            message = "sefaz_auto_sync_summary result=skipped_outside_window processed=0 skipped=0 failed=0"
            logger.info(message)
            self.stdout.write(message)
            return

        queryset = (
            Workshop.objects.filter(is_active=True)
            .exclude(certificate_file_key="")
            .exclude(certificate_password__isnull=True)
            .exclude(certificate_password="")
            .order_by(F("last_sefaz_search_date").asc(nulls_first=True), "id")
        )
        if workshop_id:
            queryset = queryset.filter(pk=workshop_id)
            if not Workshop.objects.filter(pk=workshop_id).exists():
                raise CommandError(f"Oficina {workshop_id} não encontrada.")

        workshops = list(queryset[: max(1, limit)])
        if not workshops:
            message = "sefaz_auto_sync_summary result=nothing_eligible processed=0 skipped=0 failed=0"
            logger.info(message)
            self.stdout.write(self.style.WARNING(message))
            return

        if dry_run:
            for workshop in workshops:
                eligible, reason = is_workshop_eligible_for_sefaz_sync(workshop)
                throttled = not workshop.can_search_sefaz
                self.stdout.write(
                    f"[DRY-RUN] oficina={workshop.pk} cnpj_mask={mask_cnpj_for_log(workshop.cnpj)} "
                    f"eligible={eligible} reason={reason or '-'} throttled={throttled}"
                )
            message = f"sefaz_auto_sync_summary result=dry_run processed=0 skipped={len(workshops)} failed=0"
            logger.info(message)
            self.stdout.write(message)
            return

        processed = 0
        skipped = 0
        failed = 0
        skipped_reasons: dict[str, int] = {}

        for workshop in workshops:
            try:
                with transaction.atomic():
                    try:
                        locked = Workshop.objects.select_for_update(skip_locked=True).get(pk=workshop.pk)
                    except Workshop.DoesNotExist:
                        skipped += 1
                        skipped_reasons["locked"] = skipped_reasons.get("locked", 0) + 1
                        logger.info("sefaz_auto_sync_workshop workshop_id=%s skipped_reason=locked", workshop.pk)
                        continue

                    if not locked.can_search_sefaz:
                        skipped += 1
                        skipped_reasons["throttle"] = skipped_reasons.get("throttle", 0) + 1
                        logger.info("sefaz_auto_sync_workshop workshop_id=%s skipped_reason=throttle", locked.pk)
                        continue

                    # `--force` ignora só a janela; throttle/certificado continuam valendo.
                    result = sync_sefaz_distribution_for_workshop(locked)

                    if result.success:
                        processed += 1
                    elif result.skipped_reason:
                        skipped += 1
                        skipped_reasons[result.skipped_reason] = skipped_reasons.get(result.skipped_reason, 0) + 1
                    else:
                        failed += 1
            except Exception as exc:  # falha isolada nunca aborta o lote
                failed += 1
                logger.warning("sefaz_auto_sync_workshop workshop_id=%s success=false error=%s", workshop.pk, exc)

        reasons = ",".join(f"{key}={value}" for key, value in sorted(skipped_reasons.items())) or "-"
        message = (
            f"sefaz_auto_sync_summary result=done processed={processed} skipped={skipped} "
            f"failed={failed} skipped_reasons={reasons}"
        )
        logger.info(message)
        if failed:
            self.stdout.write(self.style.WARNING(message))
        else:
            self.stdout.write(self.style.SUCCESS(message))
