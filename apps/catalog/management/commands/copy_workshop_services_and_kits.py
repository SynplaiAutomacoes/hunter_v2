from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Kit, KitApplication, KitService, Service
from apps.workshops.models import Workshop


class Command(BaseCommand):
    help = (
        "Copia Services e Kits (com KitApplication e KitService) de uma Workshop "
        "para outra. A origem é preservada: os registros passam a existir nas duas "
        "workshops de forma independente (novos PKs no destino). "
        "KitProducts NÃO são copiados."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=int,
            help="PK da workshop de origem",
        )
        parser.add_argument(
            "--target",
            type=int,
            help="PK da workshop de destino",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas conta o que seria copiado, sem gravar nada.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        source_pk = options["source"]
        target_pk = options["target"]
        dry_run = options["dry_run"]

        if source_pk == target_pk:
            raise CommandError("A workshop de origem e destino devem ser diferentes.")

        try:
            source = Workshop.objects.get(pk=source_pk)
        except Workshop.DoesNotExist:
            raise CommandError(f"Workshop de origem pk={source_pk} não encontrada.")
        try:
            target = Workshop.objects.get(pk=target_pk)
        except Workshop.DoesNotExist:
            raise CommandError(f"Workshop de destino pk={target_pk} não encontrada.")

        self.stdout.write(
            self.style.NOTICE(
                f"Copiando Services e Kits da Workshop {source.pk} para a Workshop {target.pk}..."
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Modo DRY-RUN: nada será gravado."))

        # ------------------------------------------------------------------
        # Copiar Services (pula os que já existem por nome no destino)
        # ------------------------------------------------------------------
        service_map: dict[int, Service] = {}
        copied_services = 0
        skipped_services = 0

        services = Service.objects.filter(workshop=source).order_by("pk")
        self.stdout.write(f"Encontrados {services.count()} serviços na origem.")

        for service in services:
            existing = Service.objects.filter(
                workshop=target, name=service.name
            ).first()
            if existing is not None:
                service_map[service.pk] = existing
                skipped_services += 1
                self.stdout.write(
                    f'Service "{service.name}" já existe no destino. Reutilizando.'
                )
                continue

            if dry_run:
                copied_services += 1
                continue

            new_service = Service.objects.create(
                workshop=target,
                name=service.name,
                description=service.description,
                duration=service.duration,
                suggested_cost=service.suggested_cost,
                shipping=service.shipping,
                selling_price=service.selling_price,
                last_used_price=service.last_used_price,
                is_third_party=service.is_third_party,
                is_active=service.is_active,
            )
            Service.objects.filter(pk=new_service.pk).update(
                criado_em=service.criado_em,
                atualizado_em=service.atualizado_em,
            )
            service_map[service.pk] = new_service
            copied_services += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{copied_services} serviços "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped_services} já existiam)."
            )
        )

        # ------------------------------------------------------------------
        # Copiar Kits (pula os que já existem por nome no destino)
        # ------------------------------------------------------------------
        kits = (
            Kit.objects.filter(workshop=source)
            .order_by("pk")
            .prefetch_related("applications", "kit_services__service")
        )
        self.stdout.write(f"Encontrados {kits.count()} kits na origem.")

        copied_kits = 0
        skipped_kits = 0
        copied_applications = 0
        copied_kit_services = 0

        for kit in kits:
            if Kit.objects.filter(workshop=target, name=kit.name).exists():
                skipped_kits += 1
                self.stdout.write(
                    f'Kit "{kit.name}" já existe no destino. Pulando.'
                )
                continue

            applications = list(kit.applications.all())
            kit_services = list(kit.kit_services.all())

            if dry_run:
                copied_kits += 1
                copied_applications += len(applications)
                copied_kit_services += len(kit_services)
                continue

            new_kit = Kit.objects.create(
                workshop=target,
                name=kit.name,
                description=kit.description,
                is_active=kit.is_active,
                service_pricing_mode=kit.service_pricing_mode,
            )

            KitApplication.objects.bulk_create(
                [
                    KitApplication(
                        kit=new_kit,
                        brand=application.brand,
                        model=application.model,
                        engine=application.engine,
                        fuel=application.fuel,
                        year_start=application.year_start,
                        year_end=application.year_end,
                    )
                    for application in applications
                ]
            )
            copied_applications += len(applications)

            KitService.objects.bulk_create(
                [
                    KitService(
                        kit=new_kit,
                        service=service_map[item.service_id],
                        quantity=item.quantity,
                        duration=item.duration,
                        cost_price=item.cost_price,
                        duration_selling_price=item.duration_selling_price,
                        selling_price=item.selling_price,
                    )
                    for item in kit_services
                ]
            )
            copied_kit_services += len(kit_services)

            Kit.objects.filter(pk=new_kit.pk).update(
                criado_em=kit.criado_em,
                atualizado_em=kit.atualizado_em,
            )

            # Recalcula considerando apenas serviços (products não copiados).
            new_kit.recalculate_total_price()

            copied_kits += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Simulação concluída!' if dry_run else 'Concluído!'}\n"
                f"- {copied_services} Services "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped_services} já existiam)\n"
                f"- {copied_kits} Kits "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped_kits} já existiam)\n"
                f"- {copied_applications} KitApplications "
                f"{'seriam copiadas' if dry_run else 'copiadas'}\n"
                f"- {copied_kit_services} KitServices "
                f"{'seriam copiados' if dry_run else 'copiados'}\n"
                "- Nenhum Product/KitProduct foi copiado.\n"
                "- Origem preservada (cópia, não movimentação)."
            )
        )
