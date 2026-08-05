from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.customer.models import Customer
from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalDocumentEventType,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    NfeEmissionOrigin,
    NfeFreightMode,
    NfeItem,
    NfeItemStatus,
    NfeRequest,
    NfeRequestManualItem,
    NfeRequestStatus,
)
from apps.workshops.models.workshops import Workshop


DEMO_MARKER = "[DEMO FISCAL]"
DEMO_SERIES = 999


@dataclass(frozen=True, slots=True)
class ProductSpec:
    code: str
    name: str
    unit: str
    ncm: str
    cost_price: Decimal
    selling_price: Decimal


@dataclass(frozen=True, slots=True)
class NoteItemSpec:
    product_code: str
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class NoteSpec:
    number: int
    customer_document: str
    age_days: int
    canceled: bool
    items: tuple[NoteItemSpec, ...]


PRODUCT_SPECS = (
    ProductSpec("FISCAL-DEMO-001", f"{DEMO_MARKER} Filtro de óleo", Product.Unit.UND, "84212300", Decimal("18.00"), Decimal("39.90")),
    ProductSpec("FISCAL-DEMO-002", f"{DEMO_MARKER} Óleo de motor 5W30", Product.Unit.LT, "27101932", Decimal("31.50"), Decimal("59.90")),
    ProductSpec("FISCAL-DEMO-003", f"{DEMO_MARKER} Bateria automotiva 60Ah", Product.Unit.UND, "85071090", Decimal("310.00"), Decimal("489.00")),
    ProductSpec("FISCAL-DEMO-004", f"{DEMO_MARKER} Pneu 195/65 R15", Product.Unit.UND, "40111000", Decimal("295.00"), Decimal("429.90")),
)

NOTE_SPECS = (
    NoteSpec(990001, "52998224725", 35, False, (NoteItemSpec("FISCAL-DEMO-001", Decimal("1"), Decimal("39.90")),)),
    NoteSpec(
        990002,
        "11222333000181",
        22,
        False,
        (
            NoteItemSpec("FISCAL-DEMO-001", Decimal("1"), Decimal("39.90")),
            NoteItemSpec("FISCAL-DEMO-002", Decimal("4"), Decimal("57.50")),
            NoteItemSpec("FISCAL-DEMO-003", Decimal("1"), Decimal("479.00")),
        ),
    ),
    NoteSpec(
        990003,
        "52998224725",
        14,
        False,
        (
            NoteItemSpec("FISCAL-DEMO-003", Decimal("1"), Decimal("489.00")),
            NoteItemSpec("FISCAL-DEMO-004", Decimal("2"), Decimal("419.90")),
        ),
    ),
    NoteSpec(
        990004,
        "11222333000181",
        7,
        False,
        (
            NoteItemSpec("FISCAL-DEMO-002", Decimal("5"), Decimal("59.90")),
            NoteItemSpec("FISCAL-DEMO-004", Decimal("4"), Decimal("429.90")),
        ),
    ),
    NoteSpec(990005, "52998224725", 3, True, (NoteItemSpec("FISCAL-DEMO-002", Decimal("2"), Decimal("59.90")),)),
)


class Command(BaseCommand):
    help = "Cria uma massa fiscal ficticia, local e idempotente para homologacao visual."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--workshop-id", type=int, required=True, help="ID da oficina local que recebera os dados ficticios.")

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError("A massa fiscal ficticia so pode ser criada com DEBUG=True.")

        workshop = Workshop.objects.select_related("account").filter(pk=options["workshop_id"]).first()
        if workshop is None:
            raise CommandError("Oficina nao encontrada.")

        with transaction.atomic():
            customers = self._seed_customers(workshop)
            products = self._seed_products(workshop)
            self._seed_notes(workshop, customers, products)

        self.stdout.write(
            self.style.SUCCESS(
                "Massa fiscal ficticia pronta: 2 clientes, 4 produtos, 5 NF-e "
                "(4 aprovadas e 1 cancelada), 9 itens manuais, 5 documentos fiscais "
                "e 1 evento historico de CC-e. A reexecucao nao duplica registros."
            )
        )

    def _seed_customers(self, workshop: Workshop) -> dict[str, Customer]:
        common_address = {
            "cep": "01001000",
            "logradouro": f"{DEMO_MARKER} Rua de Homologação",
            "numero": "100",
            "complemento": "Dados exclusivamente fictícios",
            "bairro": "Centro",
            "cidade": "São Paulo",
            "estado": "SP",
            "is_active": True,
            "accepts_messages": False,
        }
        specs = (
            (
                "52998224725",
                {
                    **common_address,
                    "customer_type": "PF",
                    "name": f"{DEMO_MARKER} Pessoa Física",
                    "email": "pessoa-fisica@demo.invalid",
                    "phone": "+5511999990001",
                },
            ),
            (
                "11222333000181",
                {
                    **common_address,
                    "customer_type": "PJ",
                    "name": f"{DEMO_MARKER} Empresa Ltda",
                    "fantasy_name": f"{DEMO_MARKER} Autopeças Fictícias",
                    "state_registration": "ISENTO",
                    "email": "empresa@demo.invalid",
                    "phone": "+5511999990002",
                },
            ),
        )
        customers: dict[str, Customer] = {}
        for document, defaults in specs:
            customer, _ = Customer.objects.update_or_create(workshop=workshop, cpf_or_cnpj=document, defaults=defaults)
            customers[document] = customer
        return customers

    def _seed_products(self, workshop: Workshop) -> dict[str, Product]:
        group, _ = CatalogGroup.objects.get_or_create(workshop=workshop, name=f"{DEMO_MARKER} Produtos de homologação")
        products: dict[str, Product] = {}
        for spec in PRODUCT_SPECS:
            product, _ = Product.objects.update_or_create(
                workshop=workshop,
                code=spec.code,
                defaults={
                    "name": spec.name,
                    "description": "Produto fictício para homologação dos fluxos fiscais.",
                    "unit": spec.unit,
                    "group": group,
                    "cost_price": spec.cost_price,
                    "selling_price": spec.selling_price,
                    "ncm": spec.ncm,
                    "origin_cst": Product.OriginCST.NACIONAL,
                    "purpose": Product.Purpose.RESALE,
                    "is_active": True,
                },
            )
            products[spec.code] = product
        return products

    def _seed_notes(self, workshop: Workshop, customers: dict[str, Customer], products: dict[str, Product]) -> None:
        for spec in NOTE_SPECS:
            request = self._upsert_request(workshop, customers[spec.customer_document], spec)
            product_rows = self._upsert_manual_items(request, products, spec.items)
            item = self._upsert_nfe_item(workshop, request, spec, product_rows)
            document = self._upsert_fiscal_document(workshop, item, spec, product_rows)
            if spec.number == 990004:
                self._upsert_correction_event(document, workshop.pk, spec.number)

    def _upsert_request(self, workshop: Workshop, customer: Customer, spec: NoteSpec) -> NfeRequest:
        existing = NfeRequest.objects.filter(workshop=workshop, reserved_series=DEMO_SERIES, reserved_number=spec.number).first()
        if existing is not None and DEMO_MARKER not in existing.additional_information:
            raise CommandError(f"A numeracao reservada {DEMO_SERIES}/{spec.number} ja pertence a uma NF-e que nao e da massa demo.")

        status = NfeRequestStatus.CANCELED if spec.canceled else NfeRequestStatus.APPROVED
        request, _ = NfeRequest.objects.update_or_create(
            workshop=workshop,
            reserved_series=DEMO_SERIES,
            reserved_number=spec.number,
            defaults={
                "workorder": None,
                "manual_recipient": customer,
                "emission_origin": NfeEmissionOrigin.MANUAL,
                "current_step": 4,
                "status": status,
                "additional_information": f"{DEMO_MARKER} Documento fictício. Não possui validade fiscal.",
                "tax_class": "REF000000",
                "freight_mode": NfeFreightMode.NO_TRANSPORT,
                "transport_snapshot": {},
            },
        )
        NfeRequest.objects.filter(pk=request.pk).update(criado_em=timezone.now() - timedelta(days=spec.age_days))
        return request

    def _upsert_manual_items(self, request: NfeRequest, products: dict[str, Product], items: tuple[NoteItemSpec, ...]) -> list[dict[str, str | int]]:
        desired_product_ids: list[int] = []
        rows: list[dict[str, str | int]] = []
        for sequence, item_spec in enumerate(items, start=1):
            product = products[item_spec.product_code]
            desired_product_ids.append(product.pk)
            NfeRequestManualItem.objects.update_or_create(
                request=request,
                product=product,
                defaults={"quantity": item_spec.quantity, "unit_price": item_spec.unit_price},
            )
            rows.append(
                {
                    "sequencial": sequence,
                    "codigo": product.code,
                    "nome": product.name,
                    "descricao": product.description,
                    "quantidade": str(item_spec.quantity),
                    "valor_unitario": str(item_spec.unit_price),
                    "valor_total": str(item_spec.quantity * item_spec.unit_price),
                    "ncm": product.ncm,
                    "unidade": product.unit,
                    "cfop": "5102",
                }
            )
        request.manual_items.exclude(product_id__in=desired_product_ids).delete()
        return rows

    def _upsert_nfe_item(self, workshop: Workshop, request: NfeRequest, spec: NoteSpec, product_rows: list[dict[str, str | int]]) -> NfeItem:
        item_uuid = self._stable_uuid(workshop.pk, spec.number, "nfe")
        access_key = self._access_key(workshop.pk, spec.number)
        status = NfeItemStatus.cancelado if spec.canceled else NfeItemStatus.aprovado
        payload = self._payload(spec.number, product_rows)
        item, _ = NfeItem.objects.update_or_create(
            request=request,
            uuid=item_uuid,
            defaults={
                "workshop": workshop,
                "workorder": None,
                "model": "nfe",
                "status": status,
                "reason": f"{DEMO_MARKER} Cancelamento fictício" if spec.canceled else "",
                "number": str(spec.number),
                "series": str(DEMO_SERIES),
                "receipt": f"DEMO-{spec.number}",
                "access_key": access_key,
                "xml_url": f"https://demo.invalid/fiscal/{spec.number}.xml",
                "danfe_url": f"https://demo.invalid/fiscal/{spec.number}.pdf",
                "log_payload": payload,
                "raw_payload": payload,
            },
        )
        return item

    def _upsert_fiscal_document(self, workshop: Workshop, item: NfeItem, spec: NoteSpec, product_rows: list[dict[str, str | int]]) -> FiscalDocument:
        status = FiscalDocumentStatus.CANCELED if spec.canceled else FiscalDocumentStatus.APPROVED
        payload = self._payload(spec.number, product_rows)
        document, _ = FiscalDocument.objects.update_or_create(
            workshop=workshop,
            legacy_nfe_item=item,
            defaults={
                "account": workshop.account,
                "document_type": FiscalDocumentType.NFE,
                "origin": FiscalDocumentOrigin.MANUAL,
                "purpose": FiscalDocumentPurpose.NORMAL,
                "remote_uuid": str(self._stable_uuid(workshop.pk, spec.number, "document")),
                "access_key": item.access_key,
                "series": str(DEMO_SERIES),
                "number": str(spec.number),
                "receipt": item.receipt,
                "environment": "demo",
                "status": status,
                "remote_status": "cancelado" if spec.canceled else "aprovado",
                "request_payload": payload,
                "response_payload": {"demo_data": True, "status": status, "message": f"{DEMO_MARKER} Resposta simulada localmente."},
                "xml_url": item.xml_url,
                "danfe_url": item.danfe_url,
                "external_confirmation": False,
            },
        )
        return document

    def _upsert_correction_event(self, document: FiscalDocument, workshop_id: int, number: int) -> None:
        FiscalDocumentEvent.objects.update_or_create(
            document=document,
            event_type=FiscalDocumentEventType.CCE,
            event_sequence=1,
            defaults={
                "event_code": "110110",
                "event_payload_type": "cce",
                "status": FiscalDocumentEventStatus.SUCCEEDED,
                "remote_uuid": str(self._stable_uuid(workshop_id, number, "cce")),
                "remote_event_id": f"DEMO-CCE-{number}",
                "remote_model": "cce",
                "correction_text": f"{DEMO_MARKER} Histórico fictício de Carta de Correção para homologação.",
                "request_payload": {"demo_data": True},
                "response_payload": {"demo_data": True, "status": "succeeded"},
                "xml_url": f"https://demo.invalid/fiscal/{number}-cce.xml",
                "dacce_url": f"https://demo.invalid/fiscal/{number}-dacce.pdf",
                "legal_confirmation": True,
                "confirmed_at": timezone.now() - timedelta(days=5),
            },
        )

    @staticmethod
    def _payload(number: int, product_rows: list[dict[str, str | int]]) -> dict[str, object]:
        return {
            "demo_data": True,
            "ambiente": "homologacao-ficticia",
            "observacao": f"{DEMO_MARKER} Não transmitir.",
            "numero": number,
            "serie": DEMO_SERIES,
            "produtos": product_rows,
        }

    @staticmethod
    def _stable_uuid(workshop_id: int, number: int, kind: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"hunter-v2:fiscal-demo:{workshop_id}:{number}:{kind}")

    @staticmethod
    def _access_key(workshop_id: int, number: int) -> str:
        return f"35{workshop_id:010d}{number:032d}"[-44:]
