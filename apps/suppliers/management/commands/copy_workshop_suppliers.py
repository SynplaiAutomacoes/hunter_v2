from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.suppliers.models import Supplier
from apps.workshops.models import Workshop


def _document_present(value) -> bool:
    return bool(value and str(value).strip())


class Command(BaseCommand):
    help = (
        "Copia Suppliers de uma Workshop para outra. A origem é preservada: "
        "os registros passam a existir nas duas workshops de forma independente "
        "(novos PKs no destino). Vínculos de estoque/financeiro que apontam para "
        "os fornecedores de origem NÃO são copiados."
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
                f"Copiando suppliers da Workshop {source.pk} para a Workshop {target.pk}..."
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Modo DRY-RUN: nada será gravado."))

        suppliers = Supplier.objects.filter(workshop=source).order_by("pk")
        self.stdout.write(f"Encontrados {suppliers.count()} suppliers na origem.")

        copied = 0
        skipped = 0

        for supplier in suppliers:
            # Chave de deduplicação: documento quando preenchido, senão o nome
            # (há registros com documento em branco, que não servem como chave).
            if _document_present(supplier.cnpj):
                exists = Supplier.objects.filter(
                    workshop=target, cnpj=supplier.cnpj
                ).exists()
                label = f'documento "{supplier.cnpj}"'
            else:
                exists = Supplier.objects.filter(
                    workshop=target, cnpj=supplier.cnpj, name=supplier.name
                ).exists()
                label = f'nome "{supplier.name}" (sem documento)'

            if exists:
                skipped += 1
                self.stdout.write(
                    f"Supplier com {label} já existe no destino. Pulando."
                )
                continue

            if dry_run:
                copied += 1
                continue

            new_supplier = Supplier.objects.create(
                workshop=target,
                cnpj=supplier.cnpj,
                name=supplier.name,
                contact_person=supplier.contact_person,
                phone=supplier.phone,
                mobile=supplier.mobile,
                email=supplier.email,
                registration_date=supplier.registration_date,
                is_active=supplier.is_active,
                cep=supplier.cep,
                logradouro=supplier.logradouro,
                numero=supplier.numero,
                complemento=supplier.complemento,
                bairro=supplier.bairro,
                cidade=supplier.cidade,
                estado=supplier.estado,
            )
            # Preserva auditoria original (auto_now_add/auto_now
            # sobrescreveriam no save).
            Supplier.objects.filter(pk=new_supplier.pk).update(
                criado_em=supplier.criado_em,
                atualizado_em=supplier.atualizado_em,
            )
            copied += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Simulação concluída!' if dry_run else 'Concluído!'}\n"
                f"- {copied} suppliers "
                f"{'seriam copiados' if dry_run else 'copiados'} "
                f"({skipped} já existiam)\n"
                "- Vínculos de estoque/financeiro não copiados.\n"
                "- Origem preservada (cópia, não movimentação)."
            )
        )
