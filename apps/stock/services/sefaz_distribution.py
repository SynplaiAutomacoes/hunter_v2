from __future__ import annotations

import base64
import gzip
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.utils import timezone
from lxml.etree import fromstring

from apps.core.infrastructure.providers.sefaz_provider import get_sefaz_service
from apps.stock.models import SefazZipCache
from apps.stock.utils import SEFAZ_NFE_NAMESPACE, parse_sefaz_distribution_doc_metadata
from apps.workshops.services.files import workshop_certificate_temp_path, workshop_has_certificate

external_calls_logger = logging.getLogger("performance.external")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SefazSyncResult:
    workshop_id: int | None
    success: bool
    cached_count: int = 0
    cstat: str | None = None
    ult_nsu: str | None = None
    skipped_reason: str | None = None
    duration_ms: float = 0.0
    error: str | None = None


def mask_cnpj_for_log(cnpj: Any) -> str:
    """Mascara o CNPJ para logs (nunca expõe a raiz). Ex.: `**.***.***/0001-91`."""
    digits = re.sub(r"\D", "", str(cnpj or ""))
    if len(digits) == 14:
        return f"**.***.***/{digits[8:12]}-{digits[12:14]}"
    if digits:
        return "***-****/****-**"
    return "sem-cnpj"


def is_workshop_eligible_for_sefaz_sync(workshop: Any) -> tuple[bool, str]:
    """Valida elegibilidade estática da oficina (sem checar o throttle de 1h)."""
    if workshop is None:
        return False, "no_workshop"
    if not bool(getattr(workshop, "is_active", False)):
        return False, "inactive"
    if not workshop_has_certificate(workshop) or not getattr(workshop, "certificate_password", ""):
        return False, "missing_certificate"
    digits = re.sub(r"\D", "", str(getattr(workshop, "cnpj", "") or ""))
    if len(digits) != 14:
        return False, "invalid_cnpj"
    uf = str(getattr(workshop, "uf", "") or "").strip().upper()
    if len(uf) != 2 or not uf.isalpha():
        return False, "invalid_uf"
    return True, ""


def sync_sefaz_distribution_for_workshop(workshop: Any, *, force_throttle: bool = False) -> SefazSyncResult:
    """Sincroniza a distribuição SEFAZ (lista/resumos) persistindo só `SefazZipCache`.

    Mesmo comportamento do fluxo manual: respeita o throttle de 1h por oficina
    (`Workshop.can_search_sefaz`), carimba `last_sefaz_search_date` inclusive
    quando `cStat != 138`, e só avança `last_nsu_sefaz` quando `cStat == 138`.
    Nunca cria `StockImport`, movimentos ou documentos fiscais.
    """
    started_at = time.perf_counter()
    workshop_id = getattr(workshop, "pk", None) or getattr(workshop, "id", None)

    def _elapsed_ms() -> float:
        return (time.perf_counter() - started_at) * 1000

    if workshop is None:
        return SefazSyncResult(workshop_id=None, success=False, skipped_reason="no_workshop", duration_ms=_elapsed_ms())

    if not force_throttle and not workshop.can_search_sefaz:
        return SefazSyncResult(
            workshop_id=workshop_id,
            success=False,
            skipped_reason="throttle",
            duration_ms=_elapsed_ms(),
        )

    eligible, reason = is_workshop_eligible_for_sefaz_sync(workshop)
    if not eligible:
        return SefazSyncResult(
            workshop_id=workshop_id,
            success=False,
            skipped_reason=reason,
            duration_ms=_elapsed_ms(),
        )

    cnpj_mask = mask_cnpj_for_log(getattr(workshop, "cnpj", ""))
    try:
        cnpj = re.sub(r"\D", "", str(workshop.cnpj))
        nsu = workshop.last_nsu_sefaz or "0"

        with workshop_certificate_temp_path(workshop) as certificate_path:
            xml_content = get_sefaz_service().consultar_distribuicao(
                certificado_path=certificate_path,
                certificado_senha=workshop.certificate_password,
                uf=str(workshop.uf).upper(),
                cnpj=cnpj,
                nsu=nsu,
            )

        tree = fromstring(xml_content)
        cstat_nodes = tree.xpath("//ns:cStat/text()", namespaces=SEFAZ_NFE_NAMESPACE)
        cstat = str(cstat_nodes[0]).strip() if cstat_nodes else None
        ult_nsu: str | None = None
        cached_count = 0

        if cstat == "138":
            ult_nodes = tree.xpath("//ns:ultNSU/text()", namespaces=SEFAZ_NFE_NAMESPACE)
            ult_nsu = str(ult_nodes[0]).strip() if ult_nodes else None
            if ult_nsu:
                workshop.last_nsu_sefaz = ult_nsu

            docs = tree.xpath("//ns:docZip", namespaces=SEFAZ_NFE_NAMESPACE)
            for doc in docs:
                if not doc.text:
                    continue
                content = gzip.decompress(base64.b64decode(doc.text))
                dados = parse_sefaz_distribution_doc_metadata(content) or {}

                if dados.get("key"):
                    SefazZipCache.objects.update_or_create(
                        key=dados["key"],
                        workshop=workshop,
                        defaults={
                            "nf_number": dados.get("nf_number"),
                            "issuer_name": dados.get("nome"),
                            "issuer_cnpj": dados.get("cnpj"),
                            "total_value": dados.get("valor"),
                            "issue_date": dados.get("data"),
                        },
                    )
                    cached_count += 1

        workshop.last_sefaz_search_date = timezone.now()
        workshop.save(update_fields=["last_nsu_sefaz", "last_sefaz_search_date"])

        elapsed_ms = _elapsed_ms()
        if settings.PERF_LOGGING_ENABLED:
            external_calls_logger.warning(
                "external_call service=sefaz_consulta_distribuicao duration_ms=%.2f workshop_id=%s cnpj_mask=%s cStat=%s cached_count=%s success=true",
                elapsed_ms,
                workshop_id,
                cnpj_mask,
                cstat,
                cached_count,
            )
        logger.info(
            "sefaz_distribution_sync workshop_id=%s cnpj_mask=%s cStat=%s cached_count=%s duration_ms=%.2f success=true",
            workshop_id,
            cnpj_mask,
            cstat,
            cached_count,
            elapsed_ms,
        )
        return SefazSyncResult(
            workshop_id=workshop_id,
            success=True,
            cached_count=cached_count,
            cstat=cstat,
            ult_nsu=ult_nsu,
            duration_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = _elapsed_ms()
        if settings.PERF_LOGGING_ENABLED:
            external_calls_logger.warning(
                "external_call service=sefaz_consulta_distribuicao duration_ms=%.2f workshop_id=%s cnpj_mask=%s success=false",
                elapsed_ms,
                workshop_id,
                cnpj_mask,
            )
        logger.warning(
            "sefaz_distribution_sync workshop_id=%s cnpj_mask=%s duration_ms=%.2f success=false error=%s",
            workshop_id,
            cnpj_mask,
            elapsed_ms,
            exc,
        )
        return SefazSyncResult(
            workshop_id=workshop_id,
            success=False,
            duration_ms=elapsed_ms,
            error=str(exc),
        )
