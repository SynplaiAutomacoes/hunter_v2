from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from djmoney.money import Money

from apps.accounts.models import Account, User
from apps.budget.models import (
    Budget,
    BudgetImage,
    BudgetItem,
    BudgetStatus,
    Defect,
)
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.checklist.models import Checklist, ChecklistItem
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.models import WorkshopRole
from apps.quote.models.investigative_questions import (
    InvestigativeQuestion,
    InvestigativeResponse,
)
from apps.stock.models import StockMovement, StockProduct
from apps.suppliers.models import Supplier
from apps.workorder.models import (
    WorkOrder,
    WorkOrderAttachment,
    WorkOrderPaymentMethod,
    WorkOrderStatus,
)
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import create_default_monthly_costs


class DryRunRollback(Exception):
    pass


class Command(BaseCommand):
    help = "Importa dados da V1 (CSV) para o schema V2"

    required_files = {
        "orcamento_oficina.csv",
        "orcamento_usuariocustomizado.csv",
        "orcamento_usuariocustomizado_oficinas.csv",
        "orcamento_colaborador.csv",
        "orcamento_fornecedor.csv",
        "orcamento_grupo.csv",
        "orcamento_produto.csv",
        "orcamento_servico.csv",
        "orcamento_kit.csv",
        "orcamento_kitproduto.csv",
        "orcamento_kitservico.csv",
        "orcamento_cliente.csv",
        "orcamento_veiculo.csv",
        "orcamento_checklist.csv",
        "orcamento_checklistitem.csv",
        "orcamento_perguntainvestigativa.csv",
        "orcamento_respostainvestigativa.csv",
        "orcamento_orcamento.csv",
        "orcamento_item_orcamento.csv",
        "orcamento_sintoma.csv",
        "orcamento_orcamento_sintomas_identificados.csv",
        "orcamento_orcamentoimagem.csv",
        "inventory_produtoestoque.csv",
        "inventory_movimentacaoestoque.csv",
        "orcamento_custofixo.csv",
        "orcamento_custooficina.csv",
        "orcamento_custofixovalor.csv",
        "vendas_ordemservico.csv",
        "vendas_ordemservicoplanopagamento.csv",
        "vendas_ordemservicoanexo.csv",
    }

    optional_files = {
        "orcamento_configuracao.csv",
    }

    def add_arguments(self, parser):
        parser.add_argument("--csv-dir", default="data_v1", help="Diretório com os CSVs da V1")
        parser.add_argument("--dry-run", action="store_true", help="Executa validação completa e rollback no final")
        parser.add_argument("--reset", action="store_true", help="Apaga dados V2 antes de importar")
        parser.add_argument("--verify-only", action="store_true", help="Somente valida contagens pós-import")
        parser.add_argument("--account-name", default="Conta Migrada V1", help="Nome da conta única da migração")
        parser.add_argument("--placeholder-domain", default="placeholder.local", help="Domínio para emails placeholder")

    def handle(self, *args, **options):
        self.csv_dir = Path(options["csv_dir"]).resolve()
        self.dry_run = bool(options["dry_run"])
        self.reset = bool(options["reset"])
        self.verify_only = bool(options["verify_only"])
        self.account_name = str(options["account_name"]).strip() or "Conta Migrada V1"
        self.placeholder_domain = str(options["placeholder_domain"]).strip() or "placeholder.local"

        self.stats: dict[str, dict[str, int]] = defaultdict(lambda: {"imported": 0, "adjusted": 0, "skipped": 0, "rejected": 0})
        self.rejects: list[dict[str, str]] = []

        self.data: dict[str, list[dict[str, str]]] = {}

        self.workshops_by_legacy: dict[str, Workshop] = {}
        self.legacy_workshop_by_pk: dict[int, str] = {}
        self.users_by_legacy: dict[str, User] = {}
        self.user_legacy_role: dict[str, str] = {}
        self.roles_by_name: dict[str, WorkshopRole] = {}
        self.collaborators_by_legacy: dict[str, WorkshopCollaborator] = {}
        self.suppliers_by_legacy: dict[str, Supplier] = {}
        self.groups_by_legacy: dict[str, CatalogGroup] = {}
        self.default_group_by_workshop_pk: dict[int, CatalogGroup] = {}
        self.products_by_legacy: dict[str, Product] = {}
        self.services_by_legacy: dict[str, Service] = {}
        self.kits_by_legacy: dict[str, Kit] = {}
        self.customers_by_legacy: dict[str, Customer] = {}
        self.vehicles_by_legacy: dict[str, Vehicle] = {}
        self.checklists_by_legacy: dict[str, Checklist] = {}
        self.questions_by_legacy_workshop: dict[tuple[str, str], InvestigativeQuestion] = {}
        self.questions_by_legacy_default: dict[str, InvestigativeQuestion] = {}
        self.budgets_by_legacy: dict[str, Budget] = {}
        self.defects_by_legacy: dict[str, Defect] = {}
        self.stock_by_legacy_stock_row: dict[str, StockProduct] = {}
        self.monthly_cost_by_legacy: dict[str, MonthlyCost] = {}
        self.workshop_cost_by_legacy: dict[str, WorkshopCost] = {}
        self.workorders_by_legacy: dict[str, WorkOrder] = {}

        self.used_workshop_cnpjs: set[str] = set()
        self.used_customer_docs_per_workshop: dict[int, set[str]] = defaultdict(set)
        self.used_user_cpfs: set[str] = set()
        self.used_collaborator_cpfs_per_workshop: dict[int, set[str]] = defaultdict(set)

        csv.field_size_limit(self._max_csv_field_limit())

        self._ensure_csv_dir()
        self._load_csvs()

        if self.verify_only:
            self._verify_only()
            return

        if not self.reset and not self.dry_run and self._has_existing_domain_data():
            raise CommandError("Base V2 já possui dados. Rode novamente com --reset para evitar conflitos.")

        try:
            with transaction.atomic():
                if self.reset:
                    self._reset_domain_data()

                self.account = Account.objects.create(name=self.account_name)
                self._mark("account", "imported")

                self._import_workshops()
                self._import_users()
                self._import_roles_and_memberships()
                self._import_collaborators()
                self._import_suppliers()

                self._import_catalog_groups()
                self._import_products()
                self._import_stock_products_and_movements()
                self._import_services()
                self._import_kits()

                self._import_customers()
                self._import_vehicles()

                self._import_checklists()
                self._import_questions()

                self._import_workshop_costs()

                self._import_budgets()
                self._import_defects()
                self._import_budget_items()
                self._import_budget_images()
                self._import_investigative_responses()

                self._import_workorders()
                self._import_workorder_payments()
                self._import_workorder_attachments()

                self._sync_workorders_from_budget()

                if self.dry_run:
                    raise DryRunRollback()

        except DryRunRollback:
            self.stdout.write(self.style.WARNING("Dry-run concluído: alterações foram revertidas."))

        self._write_reject_report()
        self._print_summary()

        if not self.dry_run:
            self.stdout.write(self.style.SUCCESS("Migração V1 -> V2 concluída."))

    # ---------------------------------------------------------------------
    # CSV + reporting
    # ---------------------------------------------------------------------
    def _ensure_csv_dir(self) -> None:
        if not self.csv_dir.exists() or not self.csv_dir.is_dir():
            raise CommandError(f"Diretório de CSV inválido: {self.csv_dir}")

    def _load_csvs(self) -> None:
        missing: list[str] = []
        for name in sorted(self.required_files):
            file_path = self.csv_dir / name
            if not file_path.exists():
                missing.append(name)
                continue
            self.data[name] = self._read_csv(file_path)

        for name in sorted(self.optional_files):
            file_path = self.csv_dir / name
            if file_path.exists():
                self.data[name] = self._read_csv(file_path)
            else:
                self.data[name] = []

        if missing:
            raise CommandError(f"CSV(s) obrigatório(s) ausente(s): {', '.join(missing)}")

    def _read_csv(self, file_path: Path) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        with file_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                normalized_row: dict[str, str] = {}
                for key, value in row.items():
                    if key is None:
                        continue
                    normalized_row[key.strip()] = (value or "").strip()
                if any(v != "" for v in normalized_row.values()):
                    rows.append(normalized_row)
        return rows

    def _write_reject_report(self) -> None:
        report_path = self.csv_dir / "_import_v1_rejects.csv"
        with report_path.open("w", encoding="utf-8", newline="") as report_file:
            writer = csv.DictWriter(report_file, fieldnames=["table", "legacy_id", "reason", "raw"])
            writer.writeheader()
            writer.writerows(self.rejects)
        self.stdout.write(f"Relatório de rejeições: {report_path}")

    def _print_summary(self) -> None:
        self.stdout.write("\nResumo da migração:")
        for table_name in sorted(self.stats):
            table_stats = self.stats[table_name]
            self.stdout.write(f"- {table_name}: imported={table_stats['imported']} adjusted={table_stats['adjusted']} skipped={table_stats['skipped']} rejected={table_stats['rejected']}")

        self.stdout.write(f"- rejects_total={len(self.rejects)}")

    def _verify_only(self) -> None:
        source_counts = {
            "workshops": len(self.data["orcamento_oficina.csv"]),
            "users": len(self.data["orcamento_usuariocustomizado.csv"]),
            "collaborators": len(self.data["orcamento_colaborador.csv"]),
            "suppliers": len(self.data["orcamento_fornecedor.csv"]),
            "groups": len(self.data["orcamento_grupo.csv"]),
            "products": len(self.data["orcamento_produto.csv"]),
            "services": len(self.data["orcamento_servico.csv"]),
            "kits": len(self.data["orcamento_kit.csv"]),
            "customers": len(self.data["orcamento_cliente.csv"]),
            "vehicles": len(self.data["orcamento_veiculo.csv"]),
            "checklists": len(self.data["orcamento_checklist.csv"]),
            "budgets": len(self.data["orcamento_orcamento.csv"]),
            "budget_items": len(self.data["orcamento_item_orcamento.csv"]),
            "stock_rows": len(self.data["inventory_produtoestoque.csv"]),
            "stock_movements": len(self.data["inventory_movimentacaoestoque.csv"]),
            "workshop_costs": len(self.data["orcamento_custooficina.csv"]),
            "workorders": len(self.data["vendas_ordemservico.csv"]),
        }

        target_counts = {
            "workshops": Workshop.objects.count(),
            "users": User.objects.count(),
            "collaborators": WorkshopCollaborator.objects.count(),
            "suppliers": Supplier.objects.count(),
            "groups": CatalogGroup.objects.count(),
            "products": Product.objects.count(),
            "services": Service.objects.count(),
            "kits": Kit.objects.count(),
            "customers": Customer.objects.count(),
            "vehicles": Vehicle.objects.count(),
            "checklists": Checklist.objects.count(),
            "budgets": Budget.objects.count(),
            "budget_items": BudgetItem.objects.count(),
            "stock_rows": StockProduct.objects.count(),
            "stock_movements": StockMovement.objects.count(),
            "workshop_costs": WorkshopCost.objects.count(),
            "workorders": WorkOrder.objects.count(),
        }

        self.stdout.write("\nVerificação rápida (source -> target):")
        for key in sorted(source_counts):
            self.stdout.write(f"- {key}: {source_counts[key]} -> {target_counts[key]}")

    # ---------------------------------------------------------------------
    # Reset
    # ---------------------------------------------------------------------
    def _reset_domain_data(self) -> None:
        self.stdout.write(self.style.WARNING("Executando reset de dados V2..."))

        WorkOrderAttachment.objects.all().delete()
        WorkOrderPaymentMethod.objects.all().delete()
        WorkOrder.objects.all().delete()

        BudgetImage.objects.all().delete()
        BudgetItem.objects.all().delete()
        Defect.objects.all().delete()
        Budget.objects.all().delete()

        InvestigativeResponse.objects.all().delete()
        InvestigativeQuestion.objects.all().delete()

        StockMovement.objects.all().delete()
        StockProduct.objects.all().delete()

        KitProduct.objects.all().delete()
        KitService.objects.all().delete()
        Kit.objects.all().delete()

        Product.objects.all().delete()
        Service.objects.all().delete()
        CatalogGroup.objects.all().delete()

        Vehicle.objects.all().delete()
        Customer.objects.all().delete()

        Supplier.objects.all().delete()

        WorkshopCostItem.objects.all().delete()
        WorkshopCost.objects.all().delete()
        MonthlyCost.objects.all().delete()

        ChecklistItem.objects.all().delete()
        Checklist.objects.all().delete()

        WorkshopCollaborator.objects.all().delete()
        WorkshopMember.objects.all().delete()
        WorkshopRole.objects.all().delete()

        Workshop.objects.all().delete()

        Account.objects.update(owner=None)
        User.objects.update(account=None, is_account_owner=False)
        User.objects.all().delete()
        Account.objects.all().delete()

        self.stdout.write(self.style.WARNING("Reset concluído."))

    # ---------------------------------------------------------------------
    # Import phases
    # ---------------------------------------------------------------------
    def _import_workshops(self) -> None:
        config_by_workshop: dict[str, dict[str, str]] = {row.get("oficina_id", ""): row for row in self.data["orcamento_configuracao.csv"] if row.get("oficina_id")}

        for row in self.data["orcamento_oficina.csv"]:
            legacy_id = row.get("id", "")
            if not legacy_id:
                self._reject("workshop", "", "Linha sem id", row)
                continue

            name = self._truncate(self._clean(row.get("nome")) or f"Oficina {legacy_id}", 255)
            uf = (self._clean(row.get("uf")) or "SP").upper()[:2]
            cnpj = self._normalized_cnpj(row.get("cnpj"), legacy_id)
            phone = self._normalized_phone(None, seed=f"workshop-{legacy_id}")
            address = self._truncate(f"Endereço pendente (oficina {legacy_id})", 255)
            config_row = config_by_workshop.get(legacy_id)
            pdf_observation = self._truncate(self._clean((config_row or {}).get("observacao_padrao")) or "", 250)

            workshop = Workshop.objects.create(
                account=self.account,
                name=name,
                cnpj=cnpj,
                phone=phone,
                address=address,
                uf=uf,
                pdf_observation=pdf_observation,
                is_active=True,
                certificate_password=self._clean(row.get("certificado_senha")) or None,
                last_nsu_sefaz=self._clean(row.get("ultimo_nsu_sefaz")) or "0",
                last_sefaz_search_date=self._parse_datetime(row.get("ultima_busca_sefaz_date")),
            )

            self.workshops_by_legacy[legacy_id] = workshop
            self.legacy_workshop_by_pk[workshop.pk] = legacy_id
            self._mark("workshop", "imported")

            create_default_monthly_costs(workshop=workshop)
            self._mark("monthly_cost", "imported")

    def _import_users(self) -> None:
        owner_candidate: User | None = None

        for row in self.data["orcamento_usuariocustomizado.csv"]:
            legacy_id = row.get("id", "")
            if not legacy_id:
                self._reject("user", "", "Linha sem id", row)
                continue

            username = self._clean(row.get("username")).lower()
            if not username:
                username = f"usuario_{legacy_id}"
                self._mark("user", "adjusted")

            username = self._unique_username(username)

            cpf = self._normalized_cpf(row.get("cpf"), seed=f"user-{legacy_id}", used=self.used_user_cpfs)
            self.used_user_cpfs.add(cpf)

            first_name = self._truncate(self._clean(row.get("first_name")), 150)
            last_name = self._truncate(self._clean(row.get("last_name")), 150)
            email = self._normalized_email(row.get("email"), fallback_prefix=f"user-{legacy_id}", required=False)
            is_active = self._parse_bool(row.get("is_active"), default=True)
            is_staff = self._parse_bool(row.get("is_staff"), default=False)
            is_superuser = self._parse_bool(row.get("is_superuser"), default=False)

            user = User.objects.create(
                username=username,
                password=self._clean(row.get("password")) or "!",
                first_name=first_name,
                last_name=last_name,
                email=email,
                is_active=is_active,
                is_staff=is_staff,
                is_superuser=is_superuser,
                cpf=cpf,
                account=self.account,
                is_account_owner=False,
                date_joined=self._parse_datetime(row.get("date_joined")) or timezone.now(),
                last_login=self._parse_datetime(row.get("last_login")),
            )

            self.users_by_legacy[legacy_id] = user
            role_name = self._clean(row.get("role")) or "Gerente"
            self.user_legacy_role[legacy_id] = role_name
            self._mark("user", "imported")

            if self._normalized_key(role_name) == "ADMINISTRADOR" and owner_candidate is None:
                owner_candidate = user

        if owner_candidate is None and self.users_by_legacy:
            owner_candidate = next(iter(self.users_by_legacy.values()))

        if owner_candidate is None:
            raise CommandError("Nenhum usuário importado da V1. Abortando.")

        owner_candidate.is_account_owner = True
        owner_candidate.save(update_fields=["is_account_owner"])
        self.account.owner = owner_candidate
        self.account.save(update_fields=["owner"])
        self._mark("account", "adjusted")

    def _import_roles_and_memberships(self) -> None:
        director_role, _ = WorkshopRole.objects.get_or_create(
            account=self.account,
            name="Diretor",
            defaults={
                "is_system": True,
                "is_editable": False,
            },
        )
        director_role.permissions.set(Permission.objects.all())
        self.roles_by_name["DIRETOR"] = director_role

        distinct_roles = {self._clean(name) for name in self.user_legacy_role.values() if self._clean(name)}
        for role_name in distinct_roles:
            normalized = self._normalized_key(role_name)
            if normalized == "ADMINISTRADOR":
                self.roles_by_name[normalized] = director_role
                continue

            role, _ = WorkshopRole.objects.get_or_create(
                account=self.account,
                name=self._truncate(role_name.title(), 255),
                defaults={
                    "is_system": False,
                    "is_editable": True,
                },
            )
            role.permissions.set(Permission.objects.all())
            self.roles_by_name[normalized] = role
            self._mark("role", "imported")

        for row in self.data["orcamento_usuariocustomizado_oficinas.csv"]:
            legacy_user_id = row.get("usuariocustomizado_id", "")
            legacy_workshop_id = row.get("oficina_id", "")

            user = self.users_by_legacy.get(legacy_user_id)
            workshop = self.workshops_by_legacy.get(legacy_workshop_id)
            if user is None or workshop is None:
                self._reject("workshop_member", row.get("id", ""), "Usuário ou oficina não encontrado", row)
                continue

            role_name = self._normalized_key(self.user_legacy_role.get(legacy_user_id, ""))
            role = self.roles_by_name.get(role_name) or director_role

            WorkshopMember.objects.update_or_create(
                user=user,
                workshop=workshop,
                defaults={
                    "role": role,
                    "is_active": True,
                },
            )
            self._mark("workshop_member", "imported")

    def _import_collaborators(self) -> None:
        user_by_cpf: dict[str, User] = {}
        for user in self.users_by_legacy.values():
            cpf = self._digits_only(user.cpf)
            if cpf:
                user_by_cpf[cpf] = user

        linked_users: set[int] = set()

        for row in self.data["orcamento_colaborador.csv"]:
            legacy_id = row.get("id", "")
            legacy_workshop_id = row.get("oficina_id", "")
            workshop = self.workshops_by_legacy.get(legacy_workshop_id)
            if workshop is None:
                self._reject("collaborator", legacy_id, "Oficina não encontrada", row)
                continue

            raw_cpf = row.get("cpf")
            cpf = self._normalized_cpf(raw_cpf, seed=f"collab-{legacy_id}", used=self.used_collaborator_cpfs_per_workshop[workshop.pk])
            self.used_collaborator_cpfs_per_workshop[workshop.pk].add(cpf)

            name = self._truncate(self._clean(row.get("nome")) or f"Colaborador {legacy_id}", 255)
            birth_date = self._parse_date(row.get("data_nascimento")) or date(1990, 1, 1)
            admission_date = self._parse_date(row.get("data_admissao")) or date(2000, 1, 1)
            termination_date = self._parse_date(row.get("data_saida"))
            sex = self._map_sex(row.get("sexo"), fallback="O")
            collab_type = self._map_collaborator_type(row.get("tipo"))
            salary = self._money(row.get("salario"))
            receives_commission = self._parse_bool(row.get("recebe_comissao"), default=False)
            commission_percentage = self._parse_commission(row.get("percentual_comissao"))

            system_access = self._parse_bool(row.get("acesso_ao_sistema"), default=False)
            user: User | None = None
            if system_access:
                user = user_by_cpf.get(self._digits_only(cpf))
                if user and user.pk in linked_users:
                    self._reject("collaborator", legacy_id, "Usuário já vinculado a outro colaborador", row)
                    user = None
                    system_access = False
                    self._mark("collaborator", "adjusted")

            collaborator = WorkshopCollaborator.objects.create(
                workshop=workshop,
                user=user,
                name=name,
                cpf=cpf,
                rg=self._normalized_rg(row.get("rg")),
                birth_date=birth_date,
                sex=sex,
                phone=self._normalized_phone(row.get("telefone"), seed=f"collab-{legacy_id}", required=False),
                email=self._normalized_email(row.get("email"), fallback_prefix=f"collab-{legacy_id}", required=False),
                position=self._truncate(self._clean(row.get("cargo")), 255),
                salary=salary,
                admission_date=admission_date,
                termination_date=termination_date,
                collaborator_type=collab_type,
                receives_commission=receives_commission,
                commission_percentage=commission_percentage,
                is_active=self._parse_bool(row.get("ativo"), default=True),
                system_access=system_access,
            )

            if user:
                linked_users.add(user.pk)
                role_name = self._normalized_key(self.user_legacy_role.get(next((k for k, v in self.users_by_legacy.items() if v.pk == user.pk), ""), ""))
                role = self.roles_by_name.get(role_name) or self.roles_by_name["DIRETOR"]
                WorkshopMember.objects.update_or_create(
                    user=user,
                    workshop=workshop,
                    defaults={
                        "role": role,
                        "is_active": collaborator.is_active,
                    },
                )
                self._mark("workshop_member", "adjusted")

            self.collaborators_by_legacy[legacy_id] = collaborator
            self._mark("collaborator", "imported")

    def _import_suppliers(self) -> None:
        address_by_supplier = self._addresses_by("fornecedor_id")

        for row in self.data["orcamento_fornecedor.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("supplier", legacy_id, "Oficina não encontrada", row)
                continue

            cnpj = self._normalized_cnpj(row.get("cnpj"), seed=f"supplier-{legacy_id}")
            name = self._truncate(self._clean(row.get("nome")) or f"Fornecedor {legacy_id}", 255)
            supplier = Supplier.objects.create(
                workshop=workshop,
                cnpj=cnpj,
                name=name,
                contact_person=self._truncate(self._clean(row.get("responsavel")), 255),
                phone=self._normalized_phone(row.get("telefone"), seed=f"supplier-phone-{legacy_id}", required=False),
                mobile=self._normalized_phone(row.get("celular"), seed=f"supplier-mobile-{legacy_id}", required=False),
                email=self._normalized_email(row.get("email"), fallback_prefix=f"supplier-{legacy_id}", required=False),
                registration_date=self._parse_date(row.get("data_cadastro")) or timezone.localdate(),
                is_active=self._parse_bool(row.get("ativo"), default=True),
            )

            self._apply_address(supplier, address_by_supplier.get(legacy_id))
            self.suppliers_by_legacy[legacy_id] = supplier
            self._mark("supplier", "imported")

    def _import_catalog_groups(self) -> None:
        used_names_per_workshop: dict[int, set[str]] = defaultdict(set)

        for row in self.data["orcamento_grupo.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("catalog_group", legacy_id, "Oficina não encontrada", row)
                continue

            base_name = self._truncate(self._clean(row.get("nome")) or f"Grupo {legacy_id}", 255)
            name = self._unique_name_for_workshop(base_name, used_names_per_workshop[workshop.pk], max_length=255)
            if name != base_name:
                self._mark("catalog_group", "adjusted")

            group = CatalogGroup.objects.create(
                workshop=workshop,
                name=name,
            )

            self.groups_by_legacy[legacy_id] = group
            self._mark("catalog_group", "imported")

        for workshop in self.workshops_by_legacy.values():
            default_group = CatalogGroup.objects.create(workshop=workshop, name="SEM GRUPO")
            self.default_group_by_workshop_pk[workshop.pk] = default_group
            self._mark("catalog_group", "imported")

    def _import_products(self) -> None:
        used_codes_per_workshop: dict[int, set[str]] = defaultdict(set)

        for row in self.data["orcamento_produto.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("product", legacy_id, "Oficina não encontrada", row)
                continue

            group = self.groups_by_legacy.get(row.get("grupo_id", ""))
            if group is None:
                group = self.default_group_by_workshop_pk[workshop.pk]
                self._mark("product", "adjusted")

            base_code = self._truncate(self._clean(row.get("referencia")) or f"PROD-{legacy_id}", 50)
            code = self._unique_code_for_workshop(base_code, used_codes_per_workshop[workshop.pk], fallback_suffix=legacy_id)
            if code != base_code:
                self._mark("product", "adjusted")

            name = self._truncate(self._clean(row.get("descricao")) or f"Produto {legacy_id}", 255)
            unit = self._map_product_unit(row.get("unidade"))
            purpose = self._map_product_purpose(row.get("finalidade"))
            origin_cst = self._parse_int(row.get("origem_cst_a"), default=0)

            product = Product.objects.create(
                workshop=workshop,
                code=code,
                name=name,
                description=self._truncate(self._clean(row.get("descricao")), 255),
                unit=unit,
                group=group,
                brand=self._truncate(self._clean(row.get("marca")), 100),
                model=self._truncate(self._clean(row.get("modelo")), 100),
                sku=self._truncate(self._clean(row.get("sku")), 50),
                barcode=self._truncate(self._digits_only(row.get("codigo_barras")), 14),
                location=self._truncate(self._clean(row.get("localizacao")), 100),
                cost_price=self._money(row.get("valor_custo")),
                selling_price=self._money(row.get("valor_venda")),
                profit_margin=self._calculate_profit_margin(row.get("valor_custo"), row.get("valor_venda")),
                ncm=self._truncate(self._clean(row.get("ncm")), 10),
                cest=self._truncate(self._clean(row.get("cest")), 10),
                origin_cst=origin_cst,
                purpose=purpose,
                application=self._clean(row.get("aplicacao")),
                is_active=self._parse_bool(row.get("ativo"), default=True),
            )

            self.products_by_legacy[legacy_id] = product
            self._mark("product", "imported")

    def _import_stock_products_and_movements(self) -> None:
        for row in self.data["inventory_produtoestoque.csv"]:
            legacy_stock_row_id = row.get("id", "")
            legacy_product_id = row.get("produto_id", "")
            legacy_workshop_id = row.get("oficina_id", "")

            product = self.products_by_legacy.get(legacy_product_id)
            workshop = self.workshops_by_legacy.get(legacy_workshop_id)
            if product is None or workshop is None:
                self._reject("stock_product", legacy_stock_row_id, "Produto ou oficina não encontrado", row)
                continue

            try:
                stock_product = StockProduct.objects.get(product=product)
            except StockProduct.DoesNotExist:
                stock_product = StockProduct.objects.create(product=product, workshop=workshop)
                self._mark("stock_product", "adjusted")

            stock_product.workshop = workshop
            stock_product.current_quantity = self._parse_int(row.get("estoque_atual"), default=0)
            stock_product.minimum_quantity = self._parse_int(row.get("estoque_minimo"), default=0)
            stock_product.restock_quantity = self._parse_int(row.get("estoque_reposicao"), default=0)
            stock_product.last_nf = self._truncate(self._clean(row.get("nf")) or "", 50) or None
            supplier = self.suppliers_by_legacy.get(row.get("fornecedor_id", ""))
            stock_product.supplier = supplier
            stock_product.save(update_fields=["workshop", "current_quantity", "minimum_quantity", "restock_quantity", "last_nf", "supplier"])

            updated_at = self._parse_datetime(row.get("update"))
            if updated_at:
                StockProduct.objects.filter(pk=stock_product.pk).update(atualizado_em=updated_at)

            self.stock_by_legacy_stock_row[legacy_stock_row_id] = stock_product
            self._mark("stock_product", "imported")

        for row in self.data["inventory_movimentacaoestoque.csv"]:
            legacy_id = row.get("id", "")
            legacy_stock_row_id = row.get("produto_id", "")
            stock_product = self.stock_by_legacy_stock_row.get(legacy_stock_row_id)
            if stock_product is None:
                self._reject("stock_movement", legacy_id, "StockProduct legado não encontrado", row)
                continue

            movement = StockMovement.objects.create(
                workshop=stock_product.workshop,
                stock_product=stock_product,
                type=self._map_stock_movement_type(row.get("tipo_movimentacao")),
                supplier=self.suppliers_by_legacy.get(row.get("fornecedor_id", "")),
                transcation_by=self.users_by_legacy.get(row.get("movimentado_por_id", "")),
                quantity=max(self._parse_int(row.get("quantidade"), default=1), 1),
                status=self._map_stock_movement_status(row.get("status")),
            )

            movement_dt = self._parse_datetime(row.get("data_movimentacao"))
            if movement_dt:
                StockMovement.objects.filter(pk=movement.pk).update(criado_em=movement_dt, atualizado_em=movement_dt)

            self._mark("stock_movement", "imported")

    def _import_services(self) -> None:
        used_names_per_workshop: dict[int, set[str]] = defaultdict(set)

        for row in self.data["orcamento_servico.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("service", legacy_id, "Oficina não encontrada", row)
                continue

            base_name = self._truncate(self._clean(row.get("descricao")) or f"Serviço {legacy_id}", 255)
            name = self._unique_name_for_workshop(base_name, used_names_per_workshop[workshop.pk], max_length=255, suffix=legacy_id)
            if name != base_name:
                self._mark("service", "adjusted")

            service = Service.objects.create(
                workshop=workshop,
                name=name,
                description=self._clean(row.get("descricao")),
                duration=self._parse_duration(row.get("duracao")) or timedelta(),
                suggested_cost=self._money(row.get("custo_servico_terceiro")),
                selling_price=self._money(row.get("valor_venda")),
                is_third_party=self._parse_bool(row.get("servico_terceiro"), default=False),
                is_active=True,
            )

            self.services_by_legacy[legacy_id] = service
            self._mark("service", "imported")

    def _import_kits(self) -> None:
        used_names_per_workshop: dict[int, set[str]] = defaultdict(set)

        for row in self.data["orcamento_kit.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("kit", legacy_id, "Oficina não encontrada", row)
                continue

            base_name = self._truncate(self._clean(row.get("nome")) or f"Kit {legacy_id}", 255)
            name = self._unique_name_for_workshop(base_name, used_names_per_workshop[workshop.pk], max_length=255, suffix=legacy_id)
            if name != base_name:
                self._mark("kit", "adjusted")

            kit = Kit.objects.create(
                workshop=workshop,
                name=name,
                description=self._clean(row.get("descricao")),
                is_active=True,
            )
            self.kits_by_legacy[legacy_id] = kit
            self._mark("kit", "imported")

        kit_product_links: dict[tuple[int, int], int] = defaultdict(int)
        for row in self.data["orcamento_kitproduto.csv"]:
            kit = self.kits_by_legacy.get(row.get("kit_id", ""))
            product = self.products_by_legacy.get(row.get("produto_id", ""))
            if kit is None or product is None:
                self._reject("kit_product", row.get("id", ""), "Kit ou produto não encontrado", row)
                continue

            key = (kit.pk, product.pk)
            kit_product_links[key] += max(self._parse_int(row.get("quantidade"), default=1), 1)

        kit_products = [
            KitProduct(
                kit_id=kit_id,
                product_id=product_id,
                quantity=quantity,
            )
            for (kit_id, product_id), quantity in kit_product_links.items()
        ]
        KitProduct.objects.bulk_create(kit_products)
        self._mark("kit_product", "imported", amount=len(kit_products))

        kit_service_links: dict[tuple[int, int], int] = defaultdict(int)
        for row in self.data["orcamento_kitservico.csv"]:
            kit = self.kits_by_legacy.get(row.get("kit_id", ""))
            service = self.services_by_legacy.get(row.get("servico_id", ""))
            if kit is None or service is None:
                self._reject("kit_service", row.get("id", ""), "Kit ou serviço não encontrado", row)
                continue

            key = (kit.pk, service.pk)
            kit_service_links[key] += max(self._parse_int(row.get("quantidade"), default=1), 1)

        service_duration_by_id = {service.pk: service.duration for service in self.services_by_legacy.values()}
        kit_services = [
            KitService(
                kit_id=kit_id,
                service_id=service_id,
                quantity=quantity,
                duration=service_duration_by_id.get(service_id, timedelta()),
            )
            for (kit_id, service_id), quantity in kit_service_links.items()
        ]
        KitService.objects.bulk_create(kit_services)
        self._mark("kit_service", "imported", amount=len(kit_services))

    def _import_customers(self) -> None:
        address_by_customer = self._addresses_by("cliente_id")

        for row in self.data["orcamento_cliente.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("customer", legacy_id, "Oficina não encontrada", row)
                continue

            cpf = self._normalized_cpf(row.get("cpf"), seed=f"customer-{legacy_id}", used=self.used_customer_docs_per_workshop[workshop.pk])
            self.used_customer_docs_per_workshop[workshop.pk].add(cpf)

            customer = Customer.objects.create(
                workshop=workshop,
                customer_type="PF",
                name=self._truncate(self._clean(row.get("nome")) or f"Cliente {legacy_id}", 255),
                cpf_or_cnpj=cpf,
                phone=self._normalized_phone(row.get("telefone"), seed=f"customer-{legacy_id}", required=False),
                email=self._normalized_email(row.get("email"), fallback_prefix=f"customer-{legacy_id}"),
                is_active=self._parse_bool(row.get("ativo"), default=True),
                rg=self._normalized_rg(row.get("rg")),
                birth_date=self._parse_date(row.get("data_nascimento")),
                sex=self._map_sex(row.get("sexo"), fallback=None),
            )

            self._apply_address(customer, address_by_customer.get(legacy_id))
            self.customers_by_legacy[legacy_id] = customer
            self._mark("customer", "imported")

    def _import_vehicles(self) -> None:
        for row in self.data["orcamento_veiculo.csv"]:
            legacy_id = row.get("id", "")
            customer = self.customers_by_legacy.get(row.get("cliente_id", ""))
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if customer is None or workshop is None:
                self._reject("vehicle", legacy_id, "Cliente ou oficina não encontrado", row)
                continue

            vehicle = Vehicle.objects.create(
                workshop=workshop,
                customer=customer,
                plate=self._truncate(self._clean(row.get("placa")).upper(), 20),
                brand=self._truncate(self._clean(row.get("marca")), 500),
                model=self._truncate(self._clean(row.get("modelo")), 500),
                year_fabrication=self._truncate(self._clean(row.get("ano_fabricacao")) or "0000", 4),
                year_model=self._truncate(self._clean(row.get("ano_modelo")) or "0000", 4),
                color=self._truncate(self._clean(row.get("cor")), 30),
                fuel=self._truncate(self._clean(row.get("combustivel")), 30),
                km=max(self._parse_int(row.get("km"), default=0), 0),
                engine=self._truncate(self._clean(row.get("motor")), 30),
                type=self._truncate(self._clean(row.get("tipo")), 50),
                renavam=self._truncate(self._clean(row.get("renavam")), 500),
                chassi=self._truncate(self._clean(row.get("chassi")), 500),
            )

            self.vehicles_by_legacy[legacy_id] = vehicle
            self._mark("vehicle", "imported")

    def _import_checklists(self) -> None:
        for row in self.data["orcamento_checklist.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("checklist", legacy_id, "Oficina não encontrada", row)
                continue

            checklist = Checklist.objects.create(
                workshop=workshop,
                name=self._truncate(self._clean(row.get("nome")) or f"Checklist {legacy_id}", 255),
            )
            created_at = self._parse_datetime(row.get("data_criacao"))
            if created_at:
                Checklist.objects.filter(pk=checklist.pk).update(criado_em=created_at, atualizado_em=created_at)

            self.checklists_by_legacy[legacy_id] = checklist
            self._mark("checklist", "imported")

        for row in self.data["orcamento_checklistitem.csv"]:
            checklist = self.checklists_by_legacy.get(row.get("checklist_id", ""))
            if checklist is None:
                self._reject("checklist_item", row.get("id", ""), "Checklist não encontrado", row)
                continue

            response_type = self._map_checklist_response_type(row.get("tipo_resposta"))
            ChecklistItem.objects.create(
                checklist=checklist,
                group=self._truncate(self._clean(row.get("agrupamento")), 100),
                description=self._truncate(self._clean(row.get("descricao")) or "Sem descrição", 500),
                response_type=response_type,
                order=max(self._parse_int(row.get("ordem"), default=0), 0),
            )
            self._mark("checklist_item", "imported")

    def _import_questions(self) -> None:
        for row in self.data["orcamento_perguntainvestigativa.csv"]:
            legacy_id = row.get("id", "")
            question_text = self._truncate(self._clean(row.get("pergunta")) or f"Pergunta {legacy_id}", 255)
            response_type = self._map_question_response_type(row.get("tipo"))
            options = self._parse_options(row.get("opcoes"))
            order = max(self._parse_int(row.get("ordem"), default=0), 0)
            is_active = self._parse_bool(row.get("ativo"), default=True)
            created_at = self._parse_datetime(row.get("data_criacao"))

            legacy_workshop_id = row.get("oficina_id", "")
            target_workshops: list[Workshop] = []

            if legacy_workshop_id:
                workshop = self.workshops_by_legacy.get(legacy_workshop_id)
                if workshop is None:
                    self._reject("question", legacy_id, "Oficina não encontrada", row)
                    continue
                target_workshops = [workshop]
            else:
                target_workshops = list(self.workshops_by_legacy.values())
                self._mark("question", "adjusted")

            for workshop in target_workshops:
                question = InvestigativeQuestion.objects.create(
                    workshop=workshop,
                    text=question_text,
                    response_type=response_type,
                    options=options,
                    order=order,
                    is_active=is_active,
                )
                if created_at:
                    InvestigativeQuestion.objects.filter(pk=question.pk).update(criado_em=created_at, atualizado_em=created_at)

                workshop_legacy_id = self.legacy_workshop_by_pk[workshop.pk]
                self.questions_by_legacy_workshop[(legacy_id, workshop_legacy_id)] = question
                self.questions_by_legacy_default.setdefault(legacy_id, question)
                self._mark("question", "imported")

    def _import_workshop_costs(self) -> None:
        monthly_cost_lookup_by_workshop: dict[int, dict[str, MonthlyCost]] = defaultdict(dict)

        for monthly_cost in MonthlyCost.objects.select_related("workshop").all():
            workshop_pk = getattr(monthly_cost, "workshop_id")
            monthly_cost_lookup_by_workshop[workshop_pk][self._normalized_key(monthly_cost.name)] = monthly_cost

        for row in self.data["orcamento_custofixo.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("monthly_cost", legacy_id, "Oficina não encontrada", row)
                continue

            legacy_name = self._clean(row.get("descricao")) or f"Custo {legacy_id}"
            canonical_name = self._canonical_monthly_cost_name(legacy_name)
            normalized = self._normalized_key(canonical_name)

            monthly_cost = monthly_cost_lookup_by_workshop[workshop.pk].get(normalized)
            if monthly_cost is None:
                monthly_cost = MonthlyCost.objects.create(
                    workshop=workshop,
                    name=self._truncate(canonical_name, 255),
                    is_active=self._parse_bool(row.get("ativo"), default=True),
                    is_editable=True,
                )
                monthly_cost_lookup_by_workshop[workshop.pk][normalized] = monthly_cost
                self._mark("monthly_cost", "imported")
            else:
                monthly_cost.is_active = self._parse_bool(row.get("ativo"), default=True)
                monthly_cost.save(update_fields=["is_active"])
                self._mark("monthly_cost", "adjusted")

            self.monthly_cost_by_legacy[legacy_id] = monthly_cost

        for row in self.data["orcamento_custooficina.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("workshop_cost", legacy_id, "Oficina não encontrada", row)
                continue

            month = self._month_number(row.get("mes"))
            if month is None:
                self._reject("workshop_cost", legacy_id, "Mês inválido", row)
                continue

            year = self._parse_int(row.get("ano"), default=timezone.localdate().year)
            mechanic_quantity = max(self._parse_int(row.get("mecanicos_produtivos"), default=0), 0)
            work_hours_per_day = self._hours_decimal_to_duration(row.get("horas_dia"))
            work_days_per_month = max(self._parse_int(row.get("dias_uteis"), default=0), 0)

            workshop_cost = WorkshopCost.objects.create(
                workshop=workshop,
                month=month,
                year=year,
                mechanic_quantity=mechanic_quantity,
                work_hours_per_day=work_hours_per_day,
                work_days_per_month=work_days_per_month,
                productivity_average=self._fraction_from_percent_or_ratio(row.get("produtividade"), fallback=Decimal("0.60")),
                card_rate=self._fraction_from_percent_or_ratio(row.get("taxa_cartao"), fallback=Decimal("0")),
                tax_rate=self._fraction_from_percent_or_ratio(row.get("imposto"), fallback=Decimal("0")),
                profit_margin=self._fraction_from_percent_or_ratio(row.get("margem_lucro"), fallback=Decimal("0")),
                commission_rate=self._fraction_from_percent_or_ratio(row.get("comissao"), fallback=Decimal("0")),
                risk_coefficient=self._to_decimal(row.get("coeficiente_risco"), default=Decimal("1.00")),
                parts_purchase_cap=self._money(row.get("teto_pecas")),
                freight_cost=self._money(row.get("frete")),
                third_party_service_cap=self._money(row.get("teto_servicos_terceiros")),
                total_monthly_costs=self._money(row.get("custo_mensal")),
            )

            created_at = self._parse_datetime(row.get("data_criacao"))
            updated_at = self._parse_datetime(row.get("data_atualizacao")) or created_at
            if created_at:
                WorkshopCost.objects.filter(pk=workshop_cost.pk).update(criado_em=created_at, atualizado_em=updated_at or created_at)

            self.workshop_cost_by_legacy[legacy_id] = workshop_cost
            self._mark("workshop_cost", "imported")

        for row in self.data["orcamento_custofixovalor.csv"]:
            legacy_id = row.get("id", "")
            workshop_cost = self.workshop_cost_by_legacy.get(row.get("custo_oficina_id", ""))
            monthly_cost = self.monthly_cost_by_legacy.get(row.get("custo_fixo_id", ""))
            if workshop_cost is None or monthly_cost is None:
                self._reject("workshop_cost_item", legacy_id, "Custo oficina ou custo fixo não encontrado", row)
                continue

            WorkshopCostItem.objects.update_or_create(
                workshop_cost=workshop_cost,
                monthly_cost=monthly_cost,
                defaults={
                    "amount": self._money(row.get("valor")),
                },
            )
            self._mark("workshop_cost_item", "imported")

        for workshop_cost in self.workshop_cost_by_legacy.values():
            workshop_cost.calculate_all()
            workshop_cost.save(
                update_fields=[
                    "total_value",
                    "total_monthly_costs",
                    "profit_target",
                    "gross_revenue_target",
                    "profitability_multiplier",
                    "working_hours_per_month",
                    "minimum_hourly_cost",
                    "hourly_cost_value",
                ]
            )
            self._mark("workshop_cost", "adjusted")

    def _import_budgets(self) -> None:
        for row in self.data["orcamento_orcamento.csv"]:
            legacy_id = row.get("id", "")
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if workshop is None:
                self._reject("budget", legacy_id, "Oficina não encontrada", row)
                continue

            customer = self.customers_by_legacy.get(row.get("cliente_id", ""))
            vehicle = self.vehicles_by_legacy.get(row.get("veiculo_id", ""))
            collaborator = self.collaborators_by_legacy.get(row.get("colaborador_id", ""))

            cost_estimator = collaborator.user if collaborator and collaborator.user else None

            budget = Budget(
                workshop=workshop,
                customer=customer,
                vehicle=vehicle,
                cost_estimator=cost_estimator,
                collaborator=collaborator,
                checklist=None,
                expiration_date=self._parse_date(row.get("data_validade")),
                entry_date=self._parse_date(row.get("data_criacao")) or timezone.localdate(),
                problem_description=self._clean(row.get("descricao_problema")) or None,
                technical_diagnosis=self._clean(row.get("diagnostico_tecnico")) or None,
                notes=self._clean(row.get("observacoes")) or None,
                current_km=max(self._parse_int(row.get("km_veiculo"), default=0), 0),
                discount_value=self._money(row.get("valor_desconto")),
                profit_margin_parts=self._to_decimal(row.get("percentual_lucro_pecas"), default=Decimal("0.00")),
                profit_margin_labor=self._to_decimal(row.get("percentual_lucro_mao_obra"), default=Decimal("0.00")),
                slider=self._parse_slider(row.get("etapa5_slider")),
                status=self._map_budget_status(row.get("status")),
                cancellation_reason=self._clean(row.get("cancelamento_motivo")) or None,
                current_step=1,
                step5_calculation_viewed=False,
            )
            budget.save()

            created_at = self._parse_datetime(row.get("data_criacao"))
            if created_at:
                Budget.objects.filter(pk=budget.pk).update(criado_em=created_at, atualizado_em=created_at)

            self.budgets_by_legacy[legacy_id] = budget
            self._mark("budget", "imported")

    def _import_defects(self) -> None:
        selected_by_budget: dict[str, list[str]] = defaultdict(list)
        for row in self.data["orcamento_orcamento_sintomas_identificados.csv"]:
            budget_id = row.get("orcamento_id", "")
            symptom_id = row.get("sintoma_id", "")
            if budget_id and symptom_id:
                selected_by_budget[budget_id].append(symptom_id)

        for row in self.data["orcamento_sintoma.csv"]:
            legacy_id = row.get("id", "")
            budget = self.budgets_by_legacy.get(row.get("orcamento_id", ""))
            workshop = self.workshops_by_legacy.get(row.get("oficina_id", ""))
            if budget is None or workshop is None:
                self._reject("defect", legacy_id, "Orçamento ou oficina não encontrado", row)
                continue

            defect_name = self._truncate(self._clean(row.get("nome")) or f"Defeito {legacy_id}", 100)
            base_name = defect_name
            suffix = 1
            while Defect.objects.filter(budget=budget, name=defect_name).exists():
                suffix += 1
                defect_name = self._truncate(f"{base_name} ({suffix})", 100)
                self._mark("defect", "adjusted")

            defect = Defect.objects.create(
                workshop=workshop,
                budget=budget,
                name=defect_name,
                is_active=self._parse_bool(row.get("ativo"), default=True),
            )
            self.defects_by_legacy[legacy_id] = defect
            self._mark("defect", "imported")

        for legacy_budget_id, symptom_ids in selected_by_budget.items():
            budget = self.budgets_by_legacy.get(legacy_budget_id)
            if budget is None:
                continue

            for symptom_id in symptom_ids:
                defect = self.defects_by_legacy.get(symptom_id)
                if defect is None:
                    continue
                budget.defect = defect
                budget.save(update_fields=["defect"])
                self._mark("budget", "adjusted")
                break

    def _import_budget_items(self) -> None:
        objects_to_create: list[BudgetItem] = []

        for row in self.data["orcamento_item_orcamento.csv"]:
            legacy_id = row.get("id", "")
            budget = self.budgets_by_legacy.get(row.get("orcamento_id", ""))
            if budget is None:
                self._reject("budget_item", legacy_id, "Orçamento não encontrado", row)
                continue

            product = self.products_by_legacy.get(row.get("produto_id", ""))
            service = self.services_by_legacy.get(row.get("servico_id", ""))
            kit = self.kits_by_legacy.get(row.get("kit_id", ""))

            quantity = max(self._parse_int(row.get("quantidade"), default=1), 1)
            unit_value = self._money(row.get("valor_unitario"))
            cost_value = self._money(row.get("valor_custo"))
            shipping = self._money(row.get("valor_frete"))

            description = self._truncate(self._clean(row.get("descricao")), 100)
            if not description:
                if product:
                    description = self._truncate(product.name, 100)
                elif service:
                    description = self._truncate(service.name, 100)
                elif kit:
                    description = self._truncate(kit.name, 100)
                else:
                    description = f"Item {legacy_id}"
                self._mark("budget_item", "adjusted")

            item = BudgetItem(
                workshop=budget.workshop,
                budget=budget,
                product=product,
                service=service,
                kit=kit,
                description=description,
                quantity=quantity,
                is_local=self._parse_bool(row.get("sem_cadastro"), default=False),
                shipping=shipping,
                product_cost_price=cost_value if product else Money(0, "BRL"),
                product_selling_price=unit_value if product else Money(0, "BRL"),
                service_cost_price=cost_value if service else Money(0, "BRL"),
                service_selling_price=unit_value if service else Money(0, "BRL"),
                duration=self._parse_duration(row.get("duracao")) if service else None,
            )
            objects_to_create.append(item)
            self._mark("budget_item", "imported")

        BudgetItem.objects.bulk_create(objects_to_create, batch_size=500)

    def _import_budget_images(self) -> None:
        for row in self.data["orcamento_orcamentoimagem.csv"]:
            legacy_id = row.get("id", "")
            budget = self.budgets_by_legacy.get(row.get("orcamento_id", ""))
            if budget is None:
                self._reject("budget_image", legacy_id, "Orçamento não encontrado", row)
                continue

            content = self._parse_hex_content(row.get("conteudo"))
            if content is None:
                self._reject("budget_image", legacy_id, "Conteúdo binário inválido", row)
                continue

            image = BudgetImage.objects.create(
                workshop=budget.workshop,
                budget=budget,
                content=content,
                content_name=self._truncate(self._clean(row.get("nome_arquivo")), 100),
                content_type=self._truncate(self._clean(row.get("content_type")), 100),
            )

            created_at = self._parse_datetime(row.get("criado_em"))
            if created_at:
                BudgetImage.objects.filter(pk=image.pk).update(criado_em=created_at, atualizado_em=created_at)

            self._mark("budget_image", "imported")

    def _import_investigative_responses(self) -> None:
        for row in self.data["orcamento_respostainvestigativa.csv"]:
            legacy_id = row.get("id", "")
            budget = self.budgets_by_legacy.get(row.get("orcamento_id", ""))
            if budget is None:
                self._reject("investigative_response", legacy_id, "Orçamento não encontrado", row)
                continue

            legacy_question_id = row.get("pergunta_id", "")
            workshop_legacy_id = self.legacy_workshop_by_pk.get(budget.workshop.pk, "")
            question = self.questions_by_legacy_workshop.get((legacy_question_id, workshop_legacy_id))
            if question is None:
                question = self.questions_by_legacy_default.get(legacy_question_id)

            if question is None:
                self._reject("investigative_response", legacy_id, "Pergunta investigativa não encontrada", row)
                continue

            response_text = self._clean(row.get("resposta")) or "-"
            response, created = InvestigativeResponse.objects.get_or_create(
                workshop=budget.workshop,
                budget=budget,
                question=question,
                defaults={
                    "response": response_text,
                },
            )
            if not created:
                response.response = response_text
                response.save(update_fields=["response"])
                self._mark("investigative_response", "adjusted")

            created_at = self._parse_datetime(row.get("data_resposta"))
            if created_at:
                InvestigativeResponse.objects.filter(pk=response.pk).update(criado_em=created_at, atualizado_em=created_at)

            self._mark("investigative_response", "imported")

    def _import_workorders(self) -> None:
        for row in self.data["vendas_ordemservico.csv"]:
            legacy_id = row.get("id", "")
            budget = self.budgets_by_legacy.get(row.get("orcamento_id", ""))
            if budget is None:
                self._reject("workorder", legacy_id, "Orçamento não encontrado", row)
                continue

            workorder, created = WorkOrder.objects.get_or_create(
                budget=budget,
                defaults={
                    "workshop": budget.workshop,
                    "status": self._map_workorder_status(row.get("status")),
                    "discount_value": budget.discount_value,
                },
            )

            if not created:
                workorder.workshop = budget.workshop
                workorder.status = self._map_workorder_status(row.get("status"))
                workorder.discount_value = budget.discount_value
                workorder.save(update_fields=["workshop", "status", "discount_value"])
                self._mark("workorder", "adjusted")

            created_at = self._parse_datetime(row.get("criado_em"))
            if created_at:
                WorkOrder.objects.filter(pk=workorder.pk).update(criado_em=created_at, atualizado_em=created_at)

            self.workorders_by_legacy[legacy_id] = workorder
            self._mark("workorder", "imported")

    def _import_workorder_payments(self) -> None:
        for row in self.data["vendas_ordemservicoplanopagamento.csv"]:
            legacy_id = row.get("id", "")
            workorder = self.workorders_by_legacy.get(row.get("ordem_servico_id", ""))
            if workorder is None:
                self._reject("workorder_payment", legacy_id, "Ordem de serviço não encontrada", row)
                continue

            payment = WorkOrderPaymentMethod.objects.create(
                workorder=workorder,
                payment_method=self._map_payment_method(row.get("forma_pagamento")),
                installments_count=max(self._parse_int(row.get("numero_parcelas"), default=1), 1),
                first_installment_amount=self._money(row.get("valor_primeira_parcela")),
                remaining_installments_amount=self._money(row.get("valor_parcelas_restantes")),
            )

            created_at = self._parse_datetime(row.get("criado_em"))
            updated_at = self._parse_datetime(row.get("atualizado_em")) or created_at
            if created_at:
                WorkOrderPaymentMethod.objects.filter(pk=payment.pk).update(criado_em=created_at, atualizado_em=updated_at or created_at)

            self._mark("workorder_payment", "imported")

    def _import_workorder_attachments(self) -> None:
        for row in self.data["vendas_ordemservicoanexo.csv"]:
            legacy_id = row.get("id", "")
            workorder = self.workorders_by_legacy.get(row.get("ordem_servico_id", ""))
            if workorder is None:
                self._reject("workorder_attachment", legacy_id, "Ordem de serviço não encontrada", row)
                continue

            content = self._parse_hex_content(row.get("arquivo"))
            if content is None:
                if self._clean(row.get("arquivo")):
                    self._reject("workorder_attachment", legacy_id, "Arquivo de anexo inválido", row)
                content = b""

            attachment = WorkOrderAttachment.objects.create(
                workorder=workorder,
                content=content,
                content_name=self._truncate(self._clean(row.get("nome_original")), 100),
                content_type=self._truncate(self._clean(row.get("content_type")), 100),
            )
            created_at = self._parse_datetime(row.get("criado_em"))
            if created_at:
                WorkOrderAttachment.objects.filter(pk=attachment.pk).update(criado_em=created_at, atualizado_em=created_at)

            self._mark("workorder_attachment", "imported")

    def _sync_workorders_from_budget(self) -> None:
        for workorder in WorkOrder.objects.select_related("budget").all():
            workorder.sync_from_budget()
            self._mark("workorder", "adjusted")

    # ---------------------------------------------------------------------
    # Parsing / normalization helpers
    # ---------------------------------------------------------------------
    def _clean(self, value: Any) -> str:
        return str(value or "").strip()

    def _truncate(self, value: str, max_length: int) -> str:
        return value[:max_length]

    def _digits_only(self, value: Any) -> str:
        return "".join(ch for ch in self._clean(value) if ch.isdigit())

    def _strip_accents(self, value: str) -> str:
        return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))

    def _normalized_key(self, value: Any) -> str:
        text = self._strip_accents(self._clean(value))
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^A-Za-z0-9 ]", "", text)
        return text.upper().strip()

    def _to_decimal(self, value: Any, *, default: Decimal = Decimal("0")) -> Decimal:
        raw = self._clean(value)
        if not raw:
            return default

        normalized = raw.replace(" ", "")
        if "," in normalized and "." in normalized:
            if normalized.rfind(",") > normalized.rfind("."):
                normalized = normalized.replace(".", "").replace(",", ".")
            else:
                normalized = normalized.replace(",", "")
        else:
            normalized = normalized.replace(",", ".")

        try:
            return Decimal(normalized)
        except (InvalidOperation, ValueError):
            return default

    def _parse_int(self, value: Any, *, default: int = 0) -> int:
        raw = self._clean(value)
        if not raw:
            return default
        try:
            return int(Decimal(raw.replace(",", ".")))
        except (InvalidOperation, ValueError):
            return default

    def _parse_bool(self, value: Any, *, default: bool = False) -> bool:
        raw = self._clean(value).lower()
        if not raw:
            return default
        if raw in {"1", "true", "t", "yes", "y", "sim"}:
            return True
        if raw in {"0", "false", "f", "no", "n", "nao", "não", "none"}:
            return False
        return default

    def _parse_date(self, value: Any) -> date | None:
        raw = self._clean(value)
        if not raw:
            return None

        candidate = raw.split(" ")[0]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue

        try:
            return date.fromisoformat(candidate)
        except ValueError:
            return None

    def _parse_datetime(self, value: Any) -> datetime | None:
        raw = self._clean(value)
        if not raw:
            return None

        candidate = raw.replace("Z", "+00:00")
        parsed: datetime | None = None
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(candidate, fmt)
                    break
                except ValueError:
                    parsed = None
                if parsed is not None:
                    break

        if parsed is None:
            return None

        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def _parse_duration(self, value: Any) -> timedelta | None:
        raw = self._clean(value)
        if not raw:
            return None

        if raw.isdigit():
            return timedelta(minutes=int(raw))

        total_days = 0.0
        total_seconds = 0.0

        pattern = re.compile(r"(-?\d+(?:\.\d+)?)\s*(years?|mons?|months?|days?|hours?|mins?|minutes?|secs?|seconds?)", re.IGNORECASE)
        for amount_str, unit in pattern.findall(raw):
            amount = float(amount_str)
            unit_key = unit.lower()
            if unit_key.startswith("year"):
                total_days += amount * 365
            elif unit_key.startswith("mon"):
                total_days += amount * 30
            elif unit_key.startswith("day"):
                total_days += amount
            elif unit_key.startswith("hour"):
                total_seconds += amount * 3600
            elif unit_key.startswith("min"):
                total_seconds += amount * 60
            elif unit_key.startswith("sec"):
                total_seconds += amount

        return timedelta(days=total_days, seconds=total_seconds)

    def _hours_decimal_to_duration(self, value: Any) -> timedelta:
        hours = self._to_decimal(value, default=Decimal("0"))
        if hours < 0:
            hours = Decimal("0")
        return timedelta(seconds=int(hours * Decimal("3600")))

    def _fraction_from_percent_or_ratio(self, value: Any, *, fallback: Decimal) -> Decimal:
        number = self._to_decimal(value, default=fallback)
        if number > 1:
            return (number / Decimal("100")).quantize(Decimal("0.000001"))
        return number.quantize(Decimal("0.000001"))

    def _parse_commission(self, value: Any) -> Decimal | None:
        raw = self._clean(value)
        if not raw or raw.lower() == "none":
            return None

        number = self._to_decimal(raw, default=Decimal("0"))
        if number > 1:
            number = number / Decimal("100")

        if number < 0:
            number = Decimal("0")
        if number > 1:
            number = Decimal("1")

        return number.quantize(Decimal("0.000001"))

    def _money(self, value: Any) -> Money:
        return Money(self._to_decimal(value, default=Decimal("0.00")), "BRL")

    def _normalized_email(self, value: Any, *, fallback_prefix: str, required: bool = True) -> str:
        raw = self._clean(value).lower()
        if raw and "@" in raw:
            return self._truncate(raw, 254)
        if not required:
            return ""
        fallback = f"{self._normalized_key(fallback_prefix).lower().replace(' ', '-') or 'email'}@{self.placeholder_domain}"
        self._mark("placeholder", "adjusted")
        return self._truncate(fallback, 254)

    def _normalized_phone(self, value: Any, *, seed: str, required: bool = True) -> str:
        digits = self._digits_only(value)
        if len(digits) >= 10:
            if len(digits) > 11:
                digits = digits[-11:]
            if len(digits) == 10:
                return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
            return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"

        if not required:
            return ""

        seed_number = abs(hash(seed)) % 10_0000
        suffix = f"{seed_number:05d}"
        return f"(11) 9{suffix[:4]}-{suffix[4:]}"

    def _normalized_rg(self, value: Any) -> str:
        raw = self._clean(value)
        if not raw:
            return ""
        compact = re.sub(r"[^0-9A-Za-z]", "", raw)
        return self._truncate(compact, 9)

    def _normalized_cpf(self, value: Any, seed: str, used: set[str]) -> str:
        digits = self._digits_only(value)
        if len(digits) == 11 and self._is_valid_cpf(digits) and digits not in used:
            return self._format_cpf(digits)

        generated = self._generate_unique_valid_cpf(seed=seed, used=used)
        self._mark("placeholder", "adjusted")
        return self._format_cpf(generated)

    def _normalized_cnpj(self, value: Any, seed: str) -> str:
        digits = self._digits_only(value)
        if len(digits) == 14 and self._is_valid_cnpj(digits) and digits not in self.used_workshop_cnpjs:
            self.used_workshop_cnpjs.add(digits)
            return self._format_cnpj(digits)

        generated = self._generate_unique_valid_cnpj(seed=seed, used=self.used_workshop_cnpjs)
        self._mark("placeholder", "adjusted")
        return self._format_cnpj(generated)

    def _is_valid_cpf(self, cpf: str) -> bool:
        if len(cpf) != 11 or len(set(cpf)) == 1:
            return False

        numbers = [int(ch) for ch in cpf]
        first_sum = sum(numbers[i] * (10 - i) for i in range(9))
        first_digit = 11 - (first_sum % 11)
        if first_digit >= 10:
            first_digit = 0

        second_sum = sum(numbers[i] * (11 - i) for i in range(10))
        second_digit = 11 - (second_sum % 11)
        if second_digit >= 10:
            second_digit = 0

        return numbers[9] == first_digit and numbers[10] == second_digit

    def _is_valid_cnpj(self, cnpj: str) -> bool:
        if len(cnpj) != 14 or len(set(cnpj)) == 1:
            return False

        def _digit(base: str, weights: list[int]) -> int:
            total = sum(int(num) * weight for num, weight in zip(base, weights, strict=False))
            remainder = total % 11
            return 0 if remainder < 2 else 11 - remainder

        first = _digit(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        second = _digit(cnpj[:12] + str(first), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        return cnpj[-2:] == f"{first}{second}"

    def _generate_unique_valid_cpf(self, *, seed: str, used: set[str]) -> str:
        base_seed = abs(hash(seed)) % 1_000_000_000
        while True:
            nine_digits = f"{base_seed:09d}"[-9:]
            first = self._cpf_digit(nine_digits, [10, 9, 8, 7, 6, 5, 4, 3, 2])
            second = self._cpf_digit(nine_digits + str(first), [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
            cpf = f"{nine_digits}{first}{second}"
            if cpf not in used:
                used.add(cpf)
                return cpf
            base_seed = (base_seed + 1) % 1_000_000_000

    def _cpf_digit(self, base: str, weights: list[int]) -> int:
        total = sum(int(num) * weight for num, weight in zip(base, weights, strict=False))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    def _generate_unique_valid_cnpj(self, *, seed: str, used: set[str]) -> str:
        base_seed = abs(hash(seed)) % 1_000_000_000_000
        while True:
            twelve = f"{base_seed:012d}"[-12:]
            first = self._cnpj_digit(twelve, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
            second = self._cnpj_digit(twelve + str(first), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
            cnpj = f"{twelve}{first}{second}"
            if cnpj not in used:
                used.add(cnpj)
                return cnpj
            base_seed = (base_seed + 1) % 1_000_000_000_000

    def _cnpj_digit(self, base: str, weights: list[int]) -> int:
        total = sum(int(num) * weight for num, weight in zip(base, weights, strict=False))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    def _format_cpf(self, cpf_digits: str) -> str:
        return f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"

    def _format_cnpj(self, cnpj_digits: str) -> str:
        return f"{cnpj_digits[:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/{cnpj_digits[8:12]}-{cnpj_digits[12:]}"

    def _parse_slider(self, value: Any) -> int:
        slider = self._parse_int(value, default=0)
        if slider < -100:
            return -100
        if slider > 100:
            return 100
        return slider

    def _calculate_profit_margin(self, cost_value: Any, selling_value: Any) -> Decimal:
        cost = self._to_decimal(cost_value, default=Decimal("0"))
        selling = self._to_decimal(selling_value, default=Decimal("0"))
        if cost <= 0:
            return Decimal("0")
        margin = (selling - cost) / cost
        if margin < 0:
            margin = Decimal("0")
        if margin > Decimal("9.999999"):
            margin = Decimal("9.999999")
            self._mark("product", "adjusted")
        return margin.quantize(Decimal("0.000001"))

    def _unique_name_for_workshop(self, base_name: str, used_names: set[str], *, max_length: int, suffix: str | None = None) -> str:
        candidate = self._truncate(base_name, max_length)
        normalized = self._normalized_key(candidate)
        if normalized not in used_names:
            used_names.add(normalized)
            return candidate

        suffix_value = suffix or "dup"
        candidate = self._truncate(f"{base_name} ({suffix_value})", max_length)
        normalized = self._normalized_key(candidate)
        counter = 2
        while normalized in used_names:
            candidate = self._truncate(f"{base_name} ({suffix_value}-{counter})", max_length)
            normalized = self._normalized_key(candidate)
            counter += 1

        used_names.add(normalized)
        return candidate

    def _unique_code_for_workshop(self, base_code: str, used_codes: set[str], *, fallback_suffix: str) -> str:
        candidate = self._truncate(base_code or f"P-{fallback_suffix}", 50)
        normalized = self._normalized_key(candidate)
        if normalized not in used_codes:
            used_codes.add(normalized)
            return candidate

        candidate = self._truncate(f"{candidate[:42]}-{fallback_suffix}", 50)
        normalized = self._normalized_key(candidate)
        counter = 2
        while normalized in used_codes:
            candidate = self._truncate(f"{base_code[:40]}-{fallback_suffix}-{counter}", 50)
            normalized = self._normalized_key(candidate)
            counter += 1

        used_codes.add(normalized)
        return candidate

    def _unique_username(self, username: str) -> str:
        candidate = username
        counter = 2
        while User.objects.filter(username=candidate).exists():
            candidate = self._truncate(f"{username}-{counter}", 150)
            counter += 1
            self._mark("user", "adjusted")
        return candidate

    def _map_product_unit(self, value: Any) -> str:
        key = self._normalized_key(value)
        mapping = {
            "UND": Product.Unit.UND,
            "PC": Product.Unit.PC,
            "JG": Product.Unit.JG,
            "GR": Product.Unit.GR,
            "LT": Product.Unit.LT,
            "KG": Product.Unit.KG,
        }
        if key in mapping:
            return mapping[key]
        self._mark("product", "adjusted")
        return Product.Unit.UND

    def _map_product_purpose(self, value: Any) -> str:
        key = self._normalized_key(value)
        mapping = {
            "REVENDA": Product.Purpose.RESALE,
            "APLICACAO": Product.Purpose.RESALE,
            "CONSUMO": Product.Purpose.CONSUMPTION,
            "ATIVO": Product.Purpose.ASSET,
        }
        return mapping.get(key, Product.Purpose.RESALE)

    def _map_sex(self, value: Any, *, fallback: str | None) -> str | None:
        key = self._normalized_key(value)
        if key in {"M", "MASCULINO"}:
            return "M"
        if key in {"F", "FEMININO"}:
            return "F"
        if fallback is None:
            return None
        return fallback

    def _map_collaborator_type(self, value: Any) -> str:
        key = self._normalized_key(value)
        if "PRODUT" in key:
            return WorkshopCollaborator.CollaboratorType.PRODUCTIVE
        if "ADMIN" in key:
            return WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE
        self._mark("collaborator", "adjusted")
        return WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE

    def _map_checklist_response_type(self, value: Any) -> str:
        key = self._normalized_key(value)
        mapping = {
            "BOM_REGULAR_RUIM": "BOM_REGULAR_RUIM",
            "SIM_NAO": "SIM_NAO",
            "TEXTO_LIVRE": "TEXTO_LIVRE",
            "NIVEL": "NIVEL",
        }
        return mapping.get(key, "TEXTO_LIVRE")

    def _map_question_response_type(self, value: Any) -> str:
        key = self._normalized_key(value)
        if "MULTIPLA" in key or "ESCOLHA" in key:
            return InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE
        if "SIM" in key or "NAO" in key or "BOOL" in key:
            return InvestigativeQuestion.ResponseType.BOOLEAN
        if "ESCALA" in key or "SCALE" in key:
            return InvestigativeQuestion.ResponseType.SCALE
        return InvestigativeQuestion.ResponseType.FREE_TEXT

    def _parse_options(self, value: Any) -> list[str]:
        raw = self._clean(value)
        if not raw:
            return []
        return [option.strip() for option in raw.split(",") if option.strip()]

    def _map_budget_status(self, value: Any) -> str:
        key = self._normalized_key(value)
        if "CANCEL" in key:
            return BudgetStatus.CANCELLED
        if "APROVADO" in key and "AGUARDANDO" not in key:
            return BudgetStatus.APPROVED
        if "REJEIT" in key or "REPROV" in key:
            return BudgetStatus.REJECTED
        if "METODO" in key and "PRECIFIC" in key:
            return BudgetStatus.WAITING_PRICING
        if "PECAS" in key or "SERVICOS" in key:
            return BudgetStatus.WAITING_ITEMS
        if "REVISAO" in key:
            return BudgetStatus.WAITING_REVIEW
        if "APROV" in key and "AGUARDANDO" in key:
            return BudgetStatus.WAITING_CLIENT
        return BudgetStatus.DRAFT

    def _map_workorder_status(self, value: Any) -> str:
        key = self._normalized_key(value)
        if "APROV" in key:
            return WorkOrderStatus.APPROVED
        return WorkOrderStatus.DRAFT

    def _map_stock_movement_type(self, value: Any) -> str:
        key = self._normalized_key(value)
        if "SAIDA" in key or "EXIT" in key:
            return StockMovement.MovementType.EXIT
        return StockMovement.MovementType.ENTRY

    def _map_stock_movement_status(self, value: Any) -> str:
        key = self._normalized_key(value)
        if "APROV" in key:
            return StockMovement.MovementStatus.APPROVED
        if "REJEIT" in key:
            return StockMovement.MovementStatus.REJECTED
        return StockMovement.MovementStatus.WAITING

    def _map_payment_method(self, value: Any) -> str:
        key = self._normalized_key(value)
        mapping = {
            "CREDITO": "CREDITO",
            "CARTAO DE CREDITO": "CREDITO",
            "DEBITO": "DEBITO",
            "CARTAO DE DEBITO": "DEBITO",
            "PIX": "PIX",
            "DINHEIRO": "DINHEIRO",
            "BOLETO": "BOLETO",
        }
        return mapping.get(key, "PIX")

    def _month_number(self, value: Any) -> int | None:
        key = self._normalized_key(value)
        mapping = {
            "JANEIRO": 1,
            "FEVEREIRO": 2,
            "MARCO": 3,
            "MARCOO": 3,
            "ABRIL": 4,
            "MAIO": 5,
            "JUNHO": 6,
            "JULHO": 7,
            "AGOSTO": 8,
            "SETEMBRO": 9,
            "OUTUBRO": 10,
            "NOVEMBRO": 11,
            "DEZEMBRO": 12,
        }
        return mapping.get(key)

    def _canonical_monthly_cost_name(self, legacy_name: str) -> str:
        key = self._normalized_key(legacy_name)
        aliases = {
            "ALUGUEL": "Aluguel",
            "AGUA": "Água",
            "PRO LABORE": "Pró Labore",
            "PROLABORE": "Pró Labore",
            "SALARIOS MECANICOS PRODUTIVOS": "Salários mecânicos produtivos",
            "SALARIOS": "Total de salários administrativo",
            "TOTAL DE SALARIOS ADMINISTRATIVO": "Total de salários administrativo",
            "TAXAS BANCARIAS": "Taxas bancárias",
            "EMPRESTIMO": "Empréstimo",
            "TREINAMENTOS": "Treinamentos",
            "CONTABILIDADE": "Contabilidade",
            "LUZ": "Luz",
            "INTERNET": "Internet",
            "SEGURO": "Seguro",
            "IPTU": "IPTU",
        }
        return aliases.get(key, legacy_name)

    def _parse_hex_content(self, value: Any) -> bytes | None:
        raw = self._clean(value)
        if not raw:
            return b""

        hex_data = raw[2:] if raw.lower().startswith("0x") else raw
        hex_data = re.sub(r"\s+", "", hex_data)
        if not hex_data:
            return b""

        try:
            return bytes.fromhex(hex_data)
        except ValueError:
            return None

    def _addresses_by(self, foreign_key_name: str) -> dict[str, dict[str, str]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.data.get("orcamento_endereco.csv", []):
            foreign_id = self._clean(row.get(foreign_key_name))
            if foreign_id:
                grouped[foreign_id].append(row)

        preferred: dict[str, dict[str, str]] = {}
        for foreign_id, rows in grouped.items():
            chosen = next((item for item in rows if self._parse_bool(item.get("preferencial"), default=False)), rows[0])
            preferred[foreign_id] = chosen
        return preferred

    def _apply_address(self, instance: Any, row: dict[str, str] | None) -> None:
        if not row:
            return

        instance.cep = self._truncate(self._clean(row.get("cep")), 9)
        instance.logradouro = self._truncate(self._clean(row.get("logradouro")), 225)
        instance.numero = max(self._parse_int(row.get("numero"), default=1), 1)
        instance.complemento = self._truncate(self._clean(row.get("complemento")), 255) or None
        instance.bairro = self._truncate(self._clean(row.get("bairro")), 20)
        instance.cidade = self._truncate(self._clean(row.get("cidade")), 20)
        instance.estado = self._truncate((self._clean(row.get("estado")) or "SP").upper(), 2)
        instance.save(update_fields=["cep", "logradouro", "numero", "complemento", "bairro", "cidade", "estado"])

    def _max_csv_field_limit(self) -> int:
        limit = 2**31 - 1
        while True:
            try:
                csv.field_size_limit(limit)
                return limit
            except OverflowError:
                limit = limit // 10

    # ---------------------------------------------------------------------
    # State/report helpers
    # ---------------------------------------------------------------------
    def _mark(self, table: str, field: str, *, amount: int = 1) -> None:
        self.stats[table][field] += amount

    def _reject(self, table: str, legacy_id: str, reason: str, raw: dict[str, str]) -> None:
        self.stats[table]["rejected"] += 1
        self.rejects.append(
            {
                "table": table,
                "legacy_id": legacy_id,
                "reason": reason,
                "raw": str(raw),
            }
        )

    def _has_existing_domain_data(self) -> bool:
        checks = [
            Account.objects.exists(),
            User.objects.exists(),
            Workshop.objects.exists(),
            WorkshopMember.objects.exists(),
            WorkshopCollaborator.objects.exists(),
            Supplier.objects.exists(),
            CatalogGroup.objects.exists(),
            Product.objects.exists(),
            Service.objects.exists(),
            Kit.objects.exists(),
            Customer.objects.exists(),
            Vehicle.objects.exists(),
            Checklist.objects.exists(),
            Budget.objects.exists(),
            WorkOrder.objects.exists(),
            StockProduct.objects.exists(),
            WorkshopCost.objects.exists(),
        ]
        return any(checks)
