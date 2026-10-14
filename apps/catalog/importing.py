from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import Q
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.infrastructure.importing.base import BaseRowImportAdapter
from apps.core.infrastructure.importing.schema import (
    FieldType,
    ImportBatchResult,
    ImportEntitySchema,
    ImportField,
    ImportRowError,
    ImportRowResult,
)
from apps.stock.models import StockProduct
from apps.stock.services.adjust_stock import adjust_stock_quantity
from apps.workshops.models.workshops import Workshop


DEFAULT_IMPORT_GROUP_NAME = "Importação"


def _money(value: Decimal | None) -> Money:
    if value is None:
        return Money(Decimal("0.00"), "BRL")
    return Money(Decimal(str(value)), "BRL")


def _resolve_group(workshop: Workshop, name: str | None) -> CatalogGroup:
    cleaned = str(name or "").strip()
    if cleaned:
        group = CatalogGroup.objects.filter(workshop=workshop, name__iexact=cleaned).first()
        if group is not None:
            return group
    group, _ = CatalogGroup.objects.get_or_create(workshop=workshop, name=DEFAULT_IMPORT_GROUP_NAME)
    return group


class ProductImportAdapter(BaseRowImportAdapter):
    entity_key = "products"
    label = "Produtos"
    permission_app_label = "catalog"
    permission_model = "product"
    permission_codename = "add_product"

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema:
        options = options or {}
        fields: list[ImportField] = [
            ImportField("code", "Código", required=True),
            ImportField("name", "Produto", required=True, field_type=FieldType.TEXT),
            ImportField("unit", "Unidade", required=True, field_type=FieldType.CHOICE, choices=tuple(Product.Unit.choices), help_text="Se ignorado, usa UND"),
            ImportField("group", "Grupo", required=True, help_text="Se ignorado ou inexistente, usa o grupo «Importação»"),
            ImportField("cost_price", "Valor de custo", required=True, field_type=FieldType.MONEY, help_text="Se vazio ou inválido, usa R$ 0,00"),
            ImportField("selling_price", "Valor de venda", required=True, field_type=FieldType.MONEY, help_text="Se vazio ou inválido, usa R$ 0,00"),
            ImportField("description", "Descrição", field_type=FieldType.TEXT),
            ImportField("brand", "Marca"),
            ImportField("model", "Modelo"),
            ImportField("sku", "SKU"),
            ImportField("barcode", "Código de barras"),
            ImportField("location", "Localização"),
            ImportField("ncm", "NCM"),
            ImportField("cest", "CEST"),
            ImportField("purpose", "Finalidade", field_type=FieldType.CHOICE, choices=tuple(Product.Purpose.choices)),
            ImportField("is_active", "Ativo", field_type=FieldType.BOOLEAN),
        ]
        if options.get("include_stock"):
            fields.extend(
                [
                    ImportField("stock_quantity", "Quantidade em estoque", field_type=FieldType.DECIMAL),
                    ImportField("stock_minimum", "Estoque mínimo", field_type=FieldType.INTEGER),
                    ImportField("stock_restock", "Estoque reposição", field_type=FieldType.INTEGER),
                ]
            )
        return ImportEntitySchema(
            entity_key=self.entity_key,
            label=self.label,
            description="Importa produtos; opcionalmente ajusta estoque.",
            fields=tuple(fields),
        )

    def create_row(
        self,
        workshop: Workshop,
        mapped: dict[str, Any],
        *,
        user: AbstractBaseUser | None = None,
        options: dict[str, Any] | None = None,
    ) -> int | None:
        options = options or {}
        code = str(mapped.get("code") or "").strip()
        name = str(mapped.get("name") or "").strip()
        if not code and not name:
            raise ImportRowError("Linha vazia ignorada (sem código e sem produto).")
        if not code:
            raise ImportRowError("Código está vazio nesta linha.")
        if not name:
            # Planilhas de estoque às vezes só trazem referência; usa o código como nome.
            name = code

        if Product.objects.filter(workshop=workshop, code=code).exists():
            raise ImportRowError(f"Já existe produto com código '{code}'.")
        # Nome pode repetir na planilha (ex.: vários \"FILTRO DE AR\"); unicidade real é o código.

        group = _resolve_group(workshop, mapped.get("group"))

        cost = mapped.get("cost_price")
        sell = mapped.get("selling_price")
        cost_decimal = Decimal(str(cost)) if cost is not None else Decimal("0.00")
        sell_decimal = Decimal(str(sell)) if sell is not None else Decimal("0.00")
        if sell_decimal < cost_decimal:
            # Com defaults em zero isso não acontece; se vier invertido, iguala venda ao custo.
            sell_decimal = cost_decimal

        unit = str(mapped.get("unit") or "").strip().upper()
        if unit not in Product.Unit.values:
            unit = Product.Unit.UND

        kwargs: dict[str, Any] = {
            "workshop": workshop,
            "code": code,
            "name": name,
            "unit": unit,
            "group": group,
            "cost_price": _money(cost_decimal),
            "selling_price": _money(sell_decimal),
            "description": str(mapped.get("description") or ""),
            "brand": str(mapped.get("brand") or ""),
            "model": str(mapped.get("model") or ""),
            "sku": str(mapped.get("sku") or ""),
            "barcode": str(mapped.get("barcode") or ""),
            "location": str(mapped.get("location") or ""),
            "ncm": str(mapped.get("ncm") or ""),
            "cest": str(mapped.get("cest") or ""),
        }
        if mapped.get("purpose"):
            kwargs["purpose"] = mapped["purpose"]
        if "is_active" in mapped and mapped["is_active"] is not None:
            kwargs["is_active"] = bool(mapped["is_active"])

        try:
            product = Product.objects.create(**kwargs)
        except IntegrityError as exc:
            raise ImportRowError("Conflito de unicidade ao criar o produto.") from exc

        if options.get("include_stock"):
            stock = StockProduct.objects.filter(product=product).first()
            if stock is None:
                stock, _ = StockProduct.objects.get_or_create(workshop=workshop, product=product)

            update_fields: list[str] = []
            if mapped.get("stock_minimum") is not None:
                stock.minimum_quantity = int(mapped["stock_minimum"])
                update_fields.append("minimum_quantity")
            if mapped.get("stock_restock") is not None:
                stock.restock_quantity = int(mapped["stock_restock"])
                update_fields.append("restock_quantity")
            if update_fields:
                stock.save(update_fields=update_fields)

            qty = mapped.get("stock_quantity")
            if qty is not None:
                target = max(0, int(Decimal(str(qty))))
                if target != int(stock.current_quantity):
                    adjust_stock_quantity(
                        stock_product=stock,
                        new_quantity=target,
                        reason="Importação de planilha",
                        user=user,
                    )

        return int(product.pk)


class ServiceImportAdapter(BaseRowImportAdapter):
    entity_key = "services"
    label = "Serviços"
    permission_app_label = "catalog"
    permission_model = "service"
    permission_codename = "add_service"

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema:
        return ImportEntitySchema(
            entity_key=self.entity_key,
            label=self.label,
            fields=(
                ImportField("name", "Serviço", required=True, field_type=FieldType.TEXT),
                ImportField("duration", "Duração", required=True, field_type=FieldType.DURATION, help_text="HH:MM, minutos ou 1h30m. Se ignorado, usa 00:00"),
                ImportField("selling_price", "Valor de venda", required=True, field_type=FieldType.MONEY, help_text="Se vazio ou inválido, usa R$ 0,00"),
                ImportField("description", "Descrição", field_type=FieldType.TEXT),
                ImportField("suggested_cost", "Custo do tempo", field_type=FieldType.MONEY, help_text="Se vazio ou inválido, usa R$ 0,00"),
                ImportField("shipping", "Frete", field_type=FieldType.MONEY, help_text="Se vazio ou inválido, usa R$ 0,00"),
                ImportField("is_third_party", "Serviço de terceiro", field_type=FieldType.BOOLEAN),
                ImportField("is_active", "Ativo", field_type=FieldType.BOOLEAN),
            ),
        )

    def create_row(
        self,
        workshop: Workshop,
        mapped: dict[str, Any],
        *,
        user: AbstractBaseUser | None = None,
        options: dict[str, Any] | None = None,
    ) -> int | None:
        name = str(mapped.get("name") or "").strip()
        if not name:
            raise ImportRowError("Nome do serviço é obrigatório.")
        if Service.objects.filter(workshop=workshop, name__iexact=name).exists():
            raise ImportRowError(f"Já existe serviço com nome '{name}'.")

        duration = mapped.get("duration")
        if not isinstance(duration, timedelta):
            duration = timedelta()

        kwargs: dict[str, Any] = {
            "workshop": workshop,
            "name": name,
            "duration": duration,
            "selling_price": _money(mapped.get("selling_price")),
            "description": str(mapped.get("description") or ""),
            "suggested_cost": _money(mapped["suggested_cost"]) if mapped.get("suggested_cost") is not None else None,
            "shipping": _money(mapped["shipping"]) if mapped.get("shipping") is not None else None,
        }
        if "is_third_party" in mapped and mapped["is_third_party"] is not None:
            kwargs["is_third_party"] = bool(mapped["is_third_party"])
        if "is_active" in mapped and mapped["is_active"] is not None:
            kwargs["is_active"] = bool(mapped["is_active"])

        try:
            service = Service.objects.create(**kwargs)
        except IntegrityError as exc:
            raise ImportRowError("Conflito de unicidade ao criar o serviço.") from exc
        return int(service.pk)


class KitImportAdapter:
    entity_key = "kits"
    label = "Kits"
    permission_app_label = "catalog"
    permission_model = "kit"
    permission_codename = "add_kit"

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema:
        return ImportEntitySchema(
            entity_key=self.entity_key,
            label=self.label,
            description="Várias linhas com o mesmo nome de kit formam a composição.",
            fields=(
                ImportField("name", "Nome do kit", required=True, field_type=FieldType.TEXT),
                ImportField("description", "Descrição", field_type=FieldType.TEXT),
                ImportField(
                    "item_type",
                    "Tipo do item",
                    required=True,
                    field_type=FieldType.CHOICE,
                    choices=(("product", "Produto"), ("service", "Serviço")),
                    help_text="produto ou serviço",
                ),
                ImportField("item_ref", "Código ou nome do item", required=True, help_text="Código do produto ou nome do serviço"),
                ImportField("quantity", "Quantidade", required=True, field_type=FieldType.INTEGER),
                ImportField("is_active", "Ativo", field_type=FieldType.BOOLEAN),
            ),
        )

    def import_rows(
        self,
        workshop: Workshop,
        mapped_rows: list[tuple[int, dict[str, Any]]],
        *,
        user: AbstractBaseUser | None = None,
        options: dict[str, Any] | None = None,
    ) -> ImportBatchResult:
        batch = ImportBatchResult()
        groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        order: list[str] = []
        for row_number, mapped in mapped_rows:
            kit_name = str(mapped.get("name") or "").strip()
            if not kit_name:
                batch.add(ImportRowResult(row_number=row_number, success=False, message="Nome do kit é obrigatório."))
                continue
            key = kit_name.casefold()
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((row_number, mapped))

        for key in order:
            rows = groups[key]
            first_row_number = rows[0][0]
            try:
                with transaction.atomic():
                    kit_id = self._create_kit_group(workshop, rows)
                for row_number, _ in rows:
                    batch.add(
                        ImportRowResult(
                            row_number=row_number,
                            success=True,
                            message="Kit criado com sucesso.",
                            created_id=kit_id,
                        )
                    )
            except ImportRowError as exc:
                for row_number, _ in rows:
                    batch.add(ImportRowResult(row_number=row_number, success=False, message=exc.message))
            except IntegrityError:
                batch.add(
                    ImportRowResult(
                        row_number=first_row_number,
                        success=False,
                        message="Já existe kit com este nome nesta oficina.",
                    )
                )
                for row_number, _ in rows[1:]:
                    batch.add(ImportRowResult(row_number=row_number, success=False, message="Kit não criado (grupo rejeitado)."))
            except Exception as exc:  # noqa: BLE001
                for row_number, _ in rows:
                    batch.add(ImportRowResult(row_number=row_number, success=False, message=str(exc) or "Erro inesperado."))
        return batch

    def _create_kit_group(self, workshop: Workshop, rows: list[tuple[int, dict[str, Any]]]) -> int:
        first = rows[0][1]
        name = str(first.get("name") or "").strip()
        if Kit.objects.filter(workshop=workshop, name__iexact=name).exists():
            raise ImportRowError(f"Já existe kit com nome '{name}'.")

        kit = Kit.objects.create(
            workshop=workshop,
            name=name,
            description=str(first.get("description") or ""),
            is_active=bool(first["is_active"]) if first.get("is_active") is not None else True,
        )

        for row_number, mapped in rows:
            item_type = str(mapped.get("item_type") or "").strip().lower()
            item_ref = str(mapped.get("item_ref") or "").strip()
            quantity = mapped.get("quantity")
            if quantity is None or int(quantity) < 1:
                raise ImportRowError(f"Linha {row_number}: quantidade inválida.")
            qty = int(quantity)

            if item_type in {"product", "produto"}:
                product = Product.objects.filter(workshop=workshop).filter(Q(code__iexact=item_ref) | Q(name__iexact=item_ref)).first()
                if product is None:
                    raise ImportRowError(f"Linha {row_number}: produto '{item_ref}' não encontrado.")
                KitProduct.objects.get_or_create(kit=kit, product=product, defaults={"quantity": qty})
            elif item_type in {"service", "servico", "serviço"}:
                service = Service.objects.filter(workshop=workshop, name__iexact=item_ref).first()
                if service is None:
                    raise ImportRowError(f"Linha {row_number}: serviço '{item_ref}' não encontrado.")
                KitService.objects.get_or_create(
                    kit=kit,
                    service=service,
                    defaults={
                        "quantity": qty,
                        "duration": service.duration or timedelta(),
                        "selling_price": service.selling_price,
                        "duration_selling_price": service.selling_price,
                        "cost_price": service.suggested_cost,
                    },
                )
            else:
                raise ImportRowError(f"Linha {row_number}: tipo de item inválido '{item_type}'.")

        kit.recalculate_total_price()
        return int(kit.pk)


def register_catalog_import_adapters() -> None:
    from apps.core.infrastructure.importing.registry import register_adapter

    register_adapter(ProductImportAdapter())
    register_adapter(ServiceImportAdapter())
    register_adapter(KitImportAdapter())
