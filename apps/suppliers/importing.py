from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError

from apps.core.infrastructure.importing.base import BaseRowImportAdapter
from apps.core.infrastructure.importing.schema import FieldType, ImportEntitySchema, ImportField, ImportRowError
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


class SupplierImportAdapter(BaseRowImportAdapter):
    entity_key = "suppliers"
    label = "Fornecedores"
    permission_app_label = "suppliers"
    permission_model = "supplier"
    permission_codename = "add_supplier"

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema:
        return ImportEntitySchema(
            entity_key=self.entity_key,
            label=self.label,
            description="Importa fornecedores (somente criação).",
            fields=(
                ImportField("name", "Razão social", required=True),
                ImportField("cnpj", "Documento (CPF/CNPJ)", field_type=FieldType.DOCUMENT),
                ImportField("contact_person", "Responsável"),
                ImportField("phone", "Telefone", field_type=FieldType.PHONE),
                ImportField("mobile", "Celular", field_type=FieldType.PHONE),
                ImportField("email", "E-mail", field_type=FieldType.EMAIL),
                ImportField("cep", "CEP"),
                ImportField("logradouro", "Logradouro"),
                ImportField("numero", "Número", field_type=FieldType.INTEGER),
                ImportField("complemento", "Complemento"),
                ImportField("bairro", "Bairro"),
                ImportField("cidade", "Cidade"),
                ImportField("estado", "Estado (UF)"),
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
            raise ImportRowError("Razão social é obrigatória.")

        cnpj = "".join(ch for ch in str(mapped.get("cnpj") or "") if ch.isdigit())
        if cnpj and Supplier.objects.filter(workshop=workshop, cnpj=cnpj).exists():
            raise ImportRowError("Já existe fornecedor com este documento nesta oficina.")

        kwargs: dict[str, Any] = {
            "workshop": workshop,
            "name": name,
            "cnpj": cnpj or "",
            "contact_person": str(mapped.get("contact_person") or ""),
            "phone": str(mapped.get("phone") or ""),
            "mobile": str(mapped.get("mobile") or ""),
            "email": str(mapped.get("email") or ""),
            "cep": str(mapped.get("cep") or ""),
            "logradouro": str(mapped.get("logradouro") or ""),
            "numero": mapped.get("numero") if mapped.get("numero") is not None else 1,
            "complemento": mapped.get("complemento") or None,
            "bairro": str(mapped.get("bairro") or ""),
            "cidade": str(mapped.get("cidade") or ""),
            "estado": str(mapped.get("estado") or ""),
        }
        if "is_active" in mapped and mapped["is_active"] is not None:
            kwargs["is_active"] = bool(mapped["is_active"])

        try:
            supplier = Supplier.objects.create(**kwargs)
        except IntegrityError as exc:
            raise ImportRowError("Já existe fornecedor com este documento nesta oficina.") from exc

        return int(supplier.pk)


def register_supplier_import_adapter() -> None:
    from apps.core.infrastructure.importing.registry import register_adapter

    register_adapter(SupplierImportAdapter())
