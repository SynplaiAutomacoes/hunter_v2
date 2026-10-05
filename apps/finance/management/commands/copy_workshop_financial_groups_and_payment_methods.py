from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.finance.models import FinancialGroup, PaymentMethod
from apps.workshops.models import Workshop


class Command(BaseCommand):
    help = (
        "Copia FinancialGroups (plano orçamentário hierárquico) e PaymentMethods "
        "de uma Workshop para outra. A origem é preservada: os registros passam a "
        "existir nas duas workshops de forma independente (novos PKs no destino). "
        "FinancialMovements NÃO são copiados."
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
                f"Copiando FinancialGroups e PaymentMethods da Workshop {source.pk} "
                f"para a Workshop {target.pk}..."
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Modo DRY-RUN: nada será gravado."))

        # ------------------------------------------------------------------
        # Copiar PaymentMethods (pula os que já existem por description)
        # ------------------------------------------------------------------
        payment_methods = PaymentMethod.objects.filter(workshop=source).order_by("pk")
        self.stdout.write(
            f"Encontradas {payment_methods.count()} formas de pagamento na origem."
        )

        copied_payment_methods = 0
        skipped_payment_methods = 0

        for payment_method in payment_methods:
            if PaymentMethod.objects.filter(
                workshop=target, description=payment_method.description
            ).exists():
                skipped_payment_methods += 1
                self.stdout.write(
                    f'PaymentMethod "{payment_method.description}" já existe no destino. Pulando.'
                )
                continue

            if dry_run:
                copied_payment_methods += 1
                continue

            new_payment_method = PaymentMethod.objects.create(
                workshop=target,
                description=payment_method.description,
                payment_type=payment_method.payment_type,
                installments_count=payment_method.installments_count,
                tax_percentage=payment_method.tax_percentage,
                tax_value=payment_method.tax_value,
                is_active=payment_method.is_active,
            )
            PaymentMethod.objects.filter(pk=new_payment_method.pk).update(
                criado_em=payment_method.criado_em,
                atualizado_em=payment_method.atualizado_em,
            )
            copied_payment_methods += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{copied_payment_methods} formas de pagamento "
                f"{'seriam copiadas' if dry_run else 'copiadas'} "
                f"({skipped_payment_methods} já existiam)."
            )
        )

        # ------------------------------------------------------------------
        # Copiar FinancialGroups preservando a hierarquia.
        # Ordem por level/sort_key garante que os pais sejam criados antes
        # dos filhos; code/sequence/sort_key/level são gerados pelo save().
        # Grupos cujo code já existe no destino são reutilizados.
        # ------------------------------------------------------------------
        groups = FinancialGroup.objects.filter(workshop=source).order_by(
            "level", "sort_key"
        )
        self.stdout.write(f"Encontrados {groups.count()} grupos financeiros na origem.")

        group_map: dict[int, FinancialGroup] = {}
        copied_groups = 0
        skipped_groups = 0

        for group in groups:
            existing = FinancialGroup.objects.filter(
                workshop=target, code=group.code
            ).first()
            if existing is not None:
                if existing.name != group.name:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Grupo code "{group.code}" já existe no destino com outro nome '
                            f'(origem: "{group.name}" / destino: "{existing.name}"). Reutilizando.'
                        )
                    )
                else:
                    self.stdout.write(
                        f'Grupo "{group.code} {group.name}" já existe no destino. Reutilizando.'
                    )
                group_map[group.pk] = existing
                skipped_groups += 1
                continue

            if dry_run:
                copied_groups += 1
                continue

            new_parent = None
            if group.parent_id is not None:
                new_parent = group_map.get(group.parent_id)
                if new_parent is None:
                    raise CommandError(
                        f"Pai do grupo id={group.pk} (parent_id={group.parent_id}) "
                        "ainda não foi copiado. A ordenação por level/sort_key foi quebrada."
                    )

            new_group = FinancialGroup.objects.create(
                workshop=target,
                parent=new_parent,
                name=group.name,
                is_active=group.is_active,
            )
            FinancialGroup.objects.filter(pk=new_group.pk).update(
                criado_em=group.criado_em,
                atualizado_em=group.atualizado_em,
            )
            group_map[group.pk] = new_group
            copied_groups += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Simulação concluída!' if dry_run else 'Concluído!'}\n"
                f"- {copied_payment_methods} PaymentMethods "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped_payment_methods} já existiam)\n"
                f"- {copied_groups} FinancialGroups "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped_groups} já existiam)\n"
                "- Nenhum FinancialMovement foi copiado.\n"
                "- Origem preservada (cópia, não movimentação)."
            )
        )
