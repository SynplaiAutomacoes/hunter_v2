from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.customer.models import (
    Customer,
    Vehicle,
    VehicleMileageReading,
    VehicleOilChange,
)
from apps.workshops.models import Workshop


class Command(BaseCommand):
    help = (
        "Copia Customers (com Vehicles, VehicleOilChanges e VehicleMileageReadings) "
        "de uma Workshop para outra. A origem é preservada: os registros passam a "
        "existir nas duas workshops de forma independente (novos PKs no destino)."
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
                f"Copiando customers da Workshop {source.pk} para a Workshop {target.pk}..."
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Modo DRY-RUN: nada será gravado."))

        customers = (
            Customer.objects.filter(workshop=source)
            .order_by("pk")
            .prefetch_related("vehicles__oil_changes", "vehicles__mileage_readings")
        )
        self.stdout.write(f"Encontrados {customers.count()} customers na origem.")

        copied_customers = 0
        skipped_customers = 0
        copied_vehicles = 0
        skipped_vehicles = 0
        copied_oil_changes = 0
        copied_mileage_readings = 0

        for customer in customers:
            target_customer = Customer.objects.filter(
                workshop=target, cpf_or_cnpj=customer.cpf_or_cnpj
            ).first()
            if target_customer is not None:
                skipped_customers += 1
                self.stdout.write(
                    f'Customer "{customer.cpf_or_cnpj}" já existe no destino. '
                    "Reutilizando para os veículos."
                )
            else:
                target_customer = Customer(
                    workshop=target,
                    customer_type=customer.customer_type,
                    name=customer.name,
                    cpf_or_cnpj=customer.cpf_or_cnpj,
                    phone=customer.phone,
                    email=customer.email,
                    is_active=customer.is_active,
                    accepts_messages=customer.accepts_messages,
                    rg=customer.rg,
                    birth_date=customer.birth_date,
                    sex=customer.sex,
                    fantasy_name=customer.fantasy_name,
                    state_registration=customer.state_registration,
                    municipal_registration=customer.municipal_registration,
                    foundation_date=customer.foundation_date,
                    cep=customer.cep,
                    logradouro=customer.logradouro,
                    numero=customer.numero,
                    complemento=customer.complemento,
                    bairro=customer.bairro,
                    cidade=customer.cidade,
                    estado=customer.estado,
                )
                if not dry_run:
                    target_customer.save()
                    # Preserva auditoria original (auto_now_add/auto_now
                    # sobrescreveriam no save).
                    Customer.objects.filter(pk=target_customer.pk).update(
                        criado_em=customer.criado_em,
                        atualizado_em=customer.atualizado_em,
                    )
                copied_customers += 1

            for vehicle in customer.vehicles.all():
                if Vehicle.objects.filter(
                    workshop=target, plate=vehicle.plate
                ).exists():
                    skipped_vehicles += 1
                    self.stdout.write(
                        f'Veículo placa "{vehicle.plate}" já existe no destino. Pulando.'
                    )
                    continue

                target_vehicle = Vehicle(
                    workshop=target,
                    customer=target_customer,
                    plate=vehicle.plate,
                    brand=vehicle.brand,
                    model=vehicle.model,
                    year_fabrication=vehicle.year_fabrication,
                    year_model=vehicle.year_model,
                    color=vehicle.color,
                    fuel=vehicle.fuel,
                    km=vehicle.km,
                    engine=vehicle.engine,
                    type=vehicle.type,
                    renavam=vehicle.renavam,
                    chassi=vehicle.chassi,
                    last_oil_change_date=vehicle.last_oil_change_date,
                    last_oil_change_km=vehicle.last_oil_change_km,
                    # Vínculo com ReviewPlan da origem é zerado por decisão
                    # explícita: planos são por workshop.
                    review_plan=None,
                    next_oil_change_date=vehicle.next_oil_change_date,
                    oil_forecast_reason=vehicle.oil_forecast_reason,
                )
                if not dry_run:
                    target_vehicle.save()
                    Vehicle.objects.filter(pk=target_vehicle.pk).update(
                        criado_em=vehicle.criado_em,
                        atualizado_em=vehicle.atualizado_em,
                    )
                copied_vehicles += 1

                if dry_run:
                    copied_oil_changes += vehicle.oil_changes.count()
                    copied_mileage_readings += vehicle.mileage_readings.count()
                    continue

                for oil_change in vehicle.oil_changes.all():
                    new_oil_change = VehicleOilChange(
                        vehicle=target_vehicle,
                        changed_at=oil_change.changed_at,
                        odometer_km=oil_change.odometer_km,
                        # review_plan/budget/workorder não são copiados:
                        # pertencem à origem (outra workshop).
                        review_plan=None,
                        validity_days=oil_change.validity_days,
                        validity_km=oil_change.validity_km,
                        budget=None,
                        workorder=None,
                    )
                    new_oil_change.save()
                    VehicleOilChange.objects.filter(pk=new_oil_change.pk).update(
                        criado_em=oil_change.criado_em,
                        atualizado_em=oil_change.atualizado_em,
                    )
                    copied_oil_changes += 1

                for reading in vehicle.mileage_readings.all():
                    new_reading = VehicleMileageReading(
                        vehicle=target_vehicle,
                        read_at=reading.read_at,
                        odometer_km=reading.odometer_km,
                        source=reading.source,
                        budget=None,
                        workorder=None,
                    )
                    new_reading.save()
                    VehicleMileageReading.objects.filter(pk=new_reading.pk).update(
                        criado_em=reading.criado_em,
                        atualizado_em=reading.atualizado_em,
                    )
                    copied_mileage_readings += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Simulação concluída!' if dry_run else 'Concluído!'}\n"
                f"- {copied_customers} customers "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped_customers} já existiam)\n"
                f"- {copied_vehicles} veículos "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped_vehicles} já existiam)\n"
                f"- {copied_oil_changes} trocas de óleo "
                f"{'seriam copiadas' if dry_run else 'copiadas'}\n"
                f"- {copied_mileage_readings} leituras de KM "
                f"{'seriam copiadas' if dry_run else 'copiadas'}\n"
                "- ReviewPlan/budget/workorder zerados no destino.\n"
                "- Origem preservada (cópia, não movimentação)."
            )
        )
