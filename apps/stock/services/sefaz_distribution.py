from __future__ import annotations

import base64
import gzip
import re
from dataclasses import dataclass
from typing import Any

from django.utils import timezone
from lxml.etree import fromstring

from apps.core.infrastructure.providers.sefaz_provider import get_sefaz_service
from apps.stock.models import SefazZipCache
from apps.stock.utils import parse_sefaz_distribution_doc_metadata
from apps.workshops.services.files import workshop_certificate_temp_path, workshop_has_certificate


SEFAZ_NAMESPACE = {"ns": "http://www.portalfiscal.inf.br/nfe"}
DOCUMENTS_LOCATED_STATUS = "138"
NO_DOCUMENTS_STATUS = "137"
IMPROPER_CONSUMPTION_STATUS = "656"


@dataclass(frozen=True)
class SefazSynchronizationResult:
    success: bool
    message: str
    cached_count: int = 0
    requests: int = 0


def _record_synchronization_status(*, workshop: Any, status: str, message: str, start_cooldown: bool = False) -> None:
    workshop.last_sefaz_sync_status = status
    workshop.last_sefaz_sync_message = message
    workshop.last_sefaz_sync_attempt_at = timezone.now()
    update_fields = ["last_sefaz_sync_status", "last_sefaz_sync_message", "last_sefaz_sync_attempt_at", "atualizado_em"]
    if start_cooldown:
        workshop.last_sefaz_search_date = workshop.last_sefaz_sync_attempt_at
        update_fields.append("last_sefaz_search_date")
    workshop.save(update_fields=update_fields)


def synchronize_workshop_sefaz_documents(*, workshop: Any) -> SefazSynchronizationResult:
    """Synchronize all currently available DF-e batches for a workshop.

    ``ultNSU`` must be consumed in sequence.  The SEFAZ only requires the
    one-hour pause once the returned ``ultNSU`` catches up with ``maxNSU`` (or
    when it returns 137), so pending batches are fetched in the same run.
    """
    if not workshop_has_certificate(workshop) or not workshop.certificate_password:
        message = "Configure certificado e senha da oficina antes de buscar notas na SEFAZ."
        _record_synchronization_status(workshop=workshop, status="ERROR", message=message)
        return SefazSynchronizationResult(False, message)

    if not workshop.can_search_sefaz:
        return SefazSynchronizationResult(False, "A busca da SEFAZ foi executada recentemente. Aguarde até a próxima sincronização automática.")

    cnpj = re.sub(r"\D", "", workshop.cnpj)
    nsu = str(workshop.last_nsu_sefaz or "0")
    cached_count = 0
    requests = 0

    try:
        with workshop_certificate_temp_path(workshop) as certificate_path:
            while True:
                xml_content = get_sefaz_service().consultar_distribuicao(
                    certificado_path=certificate_path,
                    certificado_senha=workshop.certificate_password,
                    uf=workshop.uf.upper(),
                    cnpj=cnpj,
                    nsu=nsu,
                )
                requests += 1
                tree = fromstring(xml_content)
                status_values = tree.xpath("//ns:cStat/text()", namespaces=SEFAZ_NAMESPACE)
                if not status_values:
                    message = "A SEFAZ retornou uma resposta sem código de status."
                    _record_synchronization_status(workshop=workshop, status="ERROR", message=message)
                    return SefazSynchronizationResult(False, message, cached_count, requests)

                status = str(status_values[0])
                if status == NO_DOCUMENTS_STATUS:
                    message = f"Lista da SEFAZ sincronizada ({cached_count} nota(s) processada(s))."
                    _record_synchronization_status(workshop=workshop, status="SUCCESS", message=message, start_cooldown=True)
                    return SefazSynchronizationResult(True, message, cached_count, requests)

                if status != DOCUMENTS_LOCATED_STATUS:
                    reason_values = tree.xpath("//ns:xMotivo/text()", namespaces=SEFAZ_NAMESPACE)
                    reason = str(reason_values[0]) if reason_values else "status não reconhecido"
                    if status == IMPROPER_CONSUMPTION_STATUS:
                        _record_synchronization_status(workshop=workshop, status="ERROR", message=f"A SEFAZ recusou a sincronização ({status}: {reason}).", start_cooldown=True)
                    else:
                        _record_synchronization_status(workshop=workshop, status="ERROR", message=f"A SEFAZ recusou a sincronização ({status}: {reason}).")
                    return SefazSynchronizationResult(False, f"A SEFAZ recusou a sincronização ({status}: {reason}).", cached_count, requests)

                current_nsu_values = tree.xpath("//ns:ultNSU/text()", namespaces=SEFAZ_NAMESPACE)
                max_nsu_values = tree.xpath("//ns:maxNSU/text()", namespaces=SEFAZ_NAMESPACE)
                if not current_nsu_values or not max_nsu_values:
                    message = "A SEFAZ retornou documentos sem ultNSU/maxNSU."
                    _record_synchronization_status(workshop=workshop, status="ERROR", message=message)
                    return SefazSynchronizationResult(False, message, cached_count, requests)

                next_nsu = str(current_nsu_values[0])
                max_nsu = str(max_nsu_values[0])
                if next_nsu == nsu:
                    message = "A SEFAZ não avançou o NSU da consulta; a sincronização foi interrompida para evitar consumo indevido."
                    _record_synchronization_status(workshop=workshop, status="ERROR", message=message)
                    return SefazSynchronizationResult(False, message, cached_count, requests)

                for doc in tree.xpath("//ns:docZip", namespaces=SEFAZ_NAMESPACE):
                    if not doc.text:
                        continue
                    content = gzip.decompress(base64.b64decode(doc.text))
                    data = parse_sefaz_distribution_doc_metadata(content) or {}
                    if not data.get("key"):
                        continue
                    SefazZipCache.objects.update_or_create(
                        key=data["key"],
                        workshop=workshop,
                        defaults={
                            "nf_number": data.get("nf_number"),
                            "issuer_name": data.get("nome"),
                            "issuer_cnpj": data.get("cnpj"),
                            "total_value": data.get("valor"),
                            "issue_date": data.get("data"),
                        },
                    )
                    cached_count += 1

                workshop.last_nsu_sefaz = next_nsu
                workshop.save(update_fields=["last_nsu_sefaz", "atualizado_em"])
                nsu = next_nsu

                if next_nsu == max_nsu:
                    message = f"Lista da SEFAZ sincronizada ({cached_count} nota(s) processada(s))."
                    _record_synchronization_status(workshop=workshop, status="SUCCESS", message=message, start_cooldown=True)
                    return SefazSynchronizationResult(True, message, cached_count, requests)
    except Exception as exc:
        message = f"Erro ao atualizar lista da SEFAZ: {exc}"
        _record_synchronization_status(workshop=workshop, status="ERROR", message=message)
        return SefazSynchronizationResult(False, message, cached_count, requests)
