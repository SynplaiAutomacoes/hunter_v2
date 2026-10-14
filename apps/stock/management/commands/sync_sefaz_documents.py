from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.stock.services.sefaz_distribution import synchronize_workshop_sefaz_documents
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.files import workshop_has_certificate


class Command(BaseCommand):
    help = "Sincroniza automaticamente os documentos fiscais disponíveis na SEFAZ para as oficinas elegíveis."

    def handle(self, *args: Any, **options: Any) -> None:
        synchronized = 0
        skipped = 0
        failed = 0

        for workshop in Workshop.objects.filter(is_active=True).iterator():
            if not workshop_has_certificate(workshop) or not workshop.certificate_password:
                skipped += 1
                continue

            result = synchronize_workshop_sefaz_documents(workshop=workshop)
            if result.success:
                synchronized += 1
            elif not workshop.can_search_sefaz:
                skipped += 1
            else:
                failed += 1
                self.stderr.write(f"SEFAZ oficina {workshop.pk}: {result.message}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Sincronização SEFAZ concluída: sincronizadas={synchronized}, ignoradas={skipped}, falhas={failed}."
            )
        )
