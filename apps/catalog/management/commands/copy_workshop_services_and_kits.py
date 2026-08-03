from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Service, Kit, KitApplication, KitService
from apps.workshops.models import Workshop


class Command(BaseCommand):
    help = (
        "Copia todos os Services e Kits de uma Workshop para outra. "
        "Os KitProducts NÃO são copiados."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        source_pk = 19 # PK da workshop de origem
        target_pk = 25 # PK da workshop de destino

        if source_pk == target_pk:
            raise CommandError("A workshop de origem e destino devem ser diferentes.")

        source = Workshop.objects.get(pk=source_pk)
        target = Workshop.objects.get(pk=target_pk)

        self.stdout.write(
            self.style.NOTICE(
                f"Copiando Services e Kits da Workshop {source.pk} para a Workshop {target.pk}..."
            )
        )

        # ------------------------------------------------------------------
        # Copiar Services
        # ------------------------------------------------------------------
        service_map: dict[int, Service] = {}

        services = Service.objects.filter(workshop=source)

        self.stdout.write(f"Encontrados {services.count()} serviços.")

        for service in services:
            if Service.objects.filter(
                workshop=target,
                name=service.name,
            ).exists():
                raise CommandError(
                    f'Já existe um Service chamado "{service.name}" '
                    f'na workshop {target.pk}.'
                )

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

            service_map[service.pk] = new_service

        self.stdout.write(
            self.style.SUCCESS(f"{len(service_map)} serviços copiados.")
        )

        # ------------------------------------------------------------------
        # Copiar Kits
        # ------------------------------------------------------------------
        kits = (
            Kit.objects.filter(workshop=source)
            .prefetch_related(
                "applications",
                "kit_services__service",
            )
        )

        self.stdout.write(f"Encontrados {kits.count()} kits.")

        copied_kits = 0

        for kit in kits:
            if Kit.objects.filter(
                workshop=target,
                name=kit.name,
            ).exists():
                raise CommandError(
                    f'Já existe um Kit chamado "{kit.name}" '
                    f'na workshop {target.pk}.'
                )

            new_kit = Kit.objects.create(
                workshop=target,
                name=kit.name,
                description=kit.description,
                is_active=kit.is_active,
                service_pricing_mode=kit.service_pricing_mode,
            )

            # -----------------------------
            # Aplicações
            # -----------------------------
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
                    for application in kit.applications.all()
                ]
            )

            # -----------------------------
            # Serviços do kit
            # -----------------------------
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
                    for item in kit.kit_services.all()
                ]
            )

            # Recalcula considerando apenas serviços
            new_kit.recalculate_total_price()

            copied_kits += 1

        self.stdout.write()
        self.stdout.write(
            self.style.SUCCESS(
                f"Concluído!\n"
                f"- {len(service_map)} Services copiados\n"
                f"- {copied_kits} Kits copiados\n"
                f"- Nenhum Product foi copiado."
            )
        )