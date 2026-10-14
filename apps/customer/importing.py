from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError

from apps.core.infrastructure.importing.base import BaseRowImportAdapter
from apps.core.infrastructure.importing.schema import FieldType, ImportEntitySchema, ImportField, ImportRowError
from apps.customer.cpf_cnpj_validator import is_valid_cnpj, is_valid_cpf, normalize_cpf_or_cnpj
from apps.customer.models import Customer
from apps.workshops.models.workshops import Workshop


class CustomerImportAdapter(BaseRowImportAdapter):
    entity_key = "customers"
    label = "Clientes"
    permission_app_label = "customer"
    permission_model = "customer"
    permission_codename = "add_customer"

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema:
        return ImportEntitySchema(
            entity_key=self.entity_key,
            label=self.label,
            description="Importa clientes (somente criação).",
            fields=(
                ImportField("customer_type", "Tipo (PF/PJ)", required=True, field_type=FieldType.CHOICE, choices=(("PF", "Pessoa Física"), ("PJ", "Pessoa Jurídica"))),
                ImportField("name", "Nome", required=True),
                ImportField("cpf_or_cnpj", "CPF/CNPJ", required=True, field_type=FieldType.DOCUMENT),
                ImportField("email", "E-mail", required=True, field_type=FieldType.EMAIL),
                ImportField("phone", "Telefone", field_type=FieldType.PHONE),
                ImportField("rg", "RG"),
                ImportField("birth_date", "Data de nascimento", field_type=FieldType.DATE),
                ImportField("sex", "Sexo", field_type=FieldType.CHOICE, choices=(("M", "Masculino"), ("F", "Feminino"), ("O", "Outro"))),
                ImportField("fantasy_name", "Nome fantasia"),
                ImportField("state_registration", "Inscrição estadual"),
                ImportField("municipal_registration", "Inscrição municipal"),
                ImportField("foundation_date", "Data de fundação", field_type=FieldType.DATE),
                ImportField("cep", "CEP"),
                ImportField("logradouro", "Logradouro"),
                ImportField("numero", "Número", field_type=FieldType.INTEGER),
                ImportField("complemento", "Complemento"),
                ImportField("bairro", "Bairro"),
                ImportField("cidade", "Cidade"),
                ImportField("estado", "Estado (UF)"),
                ImportField("is_active", "Ativo", field_type=FieldType.BOOLEAN),
                ImportField("accepts_messages", "Receber mensagens", field_type=FieldType.BOOLEAN),
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
        customer_type = str(mapped.get("customer_type") or "PF").upper()
        document = normalize_cpf_or_cnpj(mapped.get("cpf_or_cnpj"))
        if not document:
            raise ImportRowError("CPF/CNPJ é obrigatório.")

        if customer_type == "PF":
            if not is_valid_cpf(document):
                raise ImportRowError("CPF inválido.")
        elif customer_type == "PJ":
            if not is_valid_cnpj(document):
                raise ImportRowError("CNPJ inválido.")
        else:
            raise ImportRowError("Tipo deve ser PF ou PJ.")

        if Customer.objects.filter(workshop=workshop, cpf_or_cnpj=document).exists():
            raise ImportRowError("Já existe cliente com este CPF/CNPJ nesta oficina.")

        email = str(mapped.get("email") or "").strip()
        if not email:
            raise ImportRowError("E-mail é obrigatório.")

        name = str(mapped.get("name") or "").strip()
        if not name:
            raise ImportRowError("Nome é obrigatório.")

        kwargs: dict[str, Any] = {
            "workshop": workshop,
            "customer_type": customer_type,
            "name": name,
            "cpf_or_cnpj": document,
            "email": email,
            "phone": str(mapped.get("phone") or ""),
            "rg": mapped.get("rg") or None,
            "birth_date": mapped.get("birth_date"),
            "sex": mapped.get("sex") or None,
            "fantasy_name": mapped.get("fantasy_name") or None,
            "state_registration": mapped.get("state_registration") or None,
            "municipal_registration": mapped.get("municipal_registration") or None,
            "foundation_date": mapped.get("foundation_date"),
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
        if "accepts_messages" in mapped and mapped["accepts_messages"] is not None:
            kwargs["accepts_messages"] = bool(mapped["accepts_messages"])

        try:
            customer = Customer.objects.create(**kwargs)
        except IntegrityError as exc:
            raise ImportRowError("Já existe cliente com este CPF/CNPJ nesta oficina.") from exc

        return int(customer.pk)


def register_customer_import_adapter() -> None:
    from apps.core.infrastructure.importing.registry import register_adapter

    register_adapter(CustomerImportAdapter())
