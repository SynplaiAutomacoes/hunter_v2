from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
import zipfile
from datetime import date
from io import BytesIO
from typing import Any

from functools import reduce

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.finance.models.finance import NfeItem, NfeRequest, NfseItem, NfseRequest
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.finance.views.navigation import append_query_params, build_issued_documents_origin_params
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)

ARCHIVE_DOWNLOAD_MAX_WORKERS = 5


class IssuedDocumentsFilterMixin:
    NOTE_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
        ("all", "Todas"),
        ("nfe", "Nota Fiscal de Produto"),
        ("nfse", "Nota Fiscal Serviço"),
    )

    DOCUMENT_LABELS_BY_TYPE: dict[str, dict[str, list[tuple[str, str]]]] = {
        "nfe": {
            "xml": [("xml_url", "XML")],
            "pdfs": [("danfe_url", "DANFE")],
        },
        "nfse": {
            "xml": [("xml_url", "XML")],
            "pdfs": [("pdf_nfse_url", "PDF da Nota Fiscal de Serviço")],
        },
    }

    ARCHIVE_TYPE_LABELS: dict[str, str] = {
        "all": "todas",
        "nfe": "nf",
        "nfse": "nfs",
    }

    DOCUMENT_GROUP_LABELS: dict[str, str] = {
        "xml": "xml",
        "pdfs": "pdf",
    }

    DOCUMENT_SPECS_BY_TYPE: dict[str, dict[str, list[tuple[str, str, str]]]] = {
        "nfe": {
            "xml": [("xml", "xml_url", "xml")],
            "pdfs": [("danfe", "danfe_url", "pdf")],
        },
        "nfse": {
            "xml": [("xml", "xml_url", "xml")],
            "pdfs": [("pdf-nfse", "pdf_nfse_url", "pdf")],
        },
    }

    @staticmethod
    def _parse_date_param(raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_request_param(self, name: str, default: str = "") -> str:
        if self.request.method == "POST" and name in self.request.POST:
            return str(self.request.POST.get(name) or default).strip()
        return str(self.request.GET.get(name) or default).strip()

    def _get_selected_note_type(self) -> str:
        raw_value = self._get_request_param("tipo", "all").lower()
        allowed_values = {value for value, _label in self.NOTE_TYPE_CHOICES}
        if raw_value not in allowed_values:
            return "all"
        return raw_value

    def _get_filter_state(self) -> dict[str, Any]:
        start_raw = str(self.request.GET.get("data_inicial") or "").strip()
        end_raw = str(self.request.GET.get("data_final") or "").strip()
        start_date = self._parse_date_param(start_raw)
        end_date = self._parse_date_param(end_raw)
        selected_note_type = self._get_selected_note_type()
        search_raw = str(self.request.GET.get("search") or "").strip()
        filter_error = ""

        if start_raw or end_raw:
            if not start_raw or not end_raw:
                filter_error = "Selecione a data inicial e a data final para consultar as notas."
            elif start_date is None or end_date is None:
                filter_error = "Informe um periodo valido para consultar as notas."
            elif start_date > end_date:
                filter_error = "A data inicial nao pode ser maior que a data final."

        is_valid = not bool(filter_error)

        return {
            "start_raw": start_raw,
            "end_raw": end_raw,
            "start_date": start_date,
            "end_date": end_date,
            "selected_note_type": selected_note_type,
            "selected_note_type_label": dict(self.NOTE_TYPE_CHOICES).get(selected_note_type, "Todas"),
            "has_selected_period": bool(start_raw and end_raw),
            "search_raw": search_raw,
            "is_valid": is_valid,
            "filter_error": filter_error,
        }

    @staticmethod
    def _parse_id_list(raw_values: list[str]) -> list[int]:
        ids: list[int] = []
        seen: set[int] = set()
        for raw_value in raw_values:
            value = str(raw_value or "").strip()
            if not value.isdigit():
                continue
            parsed = int(value)
            if parsed in seen:
                continue
            seen.add(parsed)
            ids.append(parsed)
        return ids

    def _get_selected_request_ids(self) -> tuple[list[int], list[int]]:
        source = self.request.POST if self.request.method == "POST" else self.request.GET
        return (
            self._parse_id_list(source.getlist("nfe_ids")),
            self._parse_id_list(source.getlist("nfse_ids")),
        )

    def _get_selected_requests(self, *, nfe_ids: list[int], nfse_ids: list[int]) -> tuple[list[NfeRequest], list[NfseRequest]]:
        nfe_requests = list(self._build_nfe_queryset(start_date=None, end_date=None).filter(pk__in=nfe_ids)) if nfe_ids else []
        nfse_requests = list(self._build_nfse_queryset(start_date=None, end_date=None).filter(pk__in=nfse_ids)) if nfse_ids else []
        return nfe_requests, nfse_requests

    def _item_has_document_group(self, *, note_type: str, item: object | None, document_group: str) -> bool:
        if item is None:
            return False

        for field_name, _label in self.DOCUMENT_LABELS_BY_TYPE[note_type][document_group]:
            if str(getattr(item, field_name, "") or "").strip():
                return True
        return False

    @staticmethod
    def _sanitize_archive_fragment(value: object) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
        normalized = normalized.strip("-._")
        return normalized or "documento"

    def _build_nfe_queryset(self, *, start_date: date | None, end_date: date | None, search_raw: str = ""):
        qs = NfeRequest.objects.filter(workshop=self.workshop)
        if start_date and end_date:
            qs = qs.filter(criado_em__date__range=(start_date, end_date))
        if search_raw:
            search_filters = [
                Q(workorder__budget__customer__name__icontains=search_raw),
                Q(items__number__icontains=search_raw),
            ]
            if search_raw.isdigit():
                search_int = int(search_raw)
                search_filters.append(Q(workorder__budget_id=search_int))
                search_filters.append(Q(reserved_number=search_int))
            qs = qs.filter(reduce(lambda a, b: a | b, search_filters)).distinct()

        return qs.select_related("workorder", "workorder__budget", "workorder__budget__customer").prefetch_related(Prefetch("items", queryset=NfeItem.objects.order_by("-id"), to_attr="prefetched_items")).order_by("-criado_em", "-pk")

    def _build_nfse_queryset(self, *, start_date: date | None, end_date: date | None, search_raw: str = ""):
        qs = NfseRequest.objects.filter(workshop=self.workshop)
        if start_date and end_date:
            qs = qs.filter(criado_em__date__range=(start_date, end_date))
        if search_raw:
            search_filters = [
                Q(workorder__budget__customer__name__icontains=search_raw),
                Q(items__rps_number__icontains=search_raw),
                Q(items__number__icontains=search_raw),
            ]
            if search_raw.isdigit():
                search_int = int(search_raw)
                search_filters.append(Q(workorder_id=search_int))
                search_filters.append(Q(reserved_rps_number=search_int))
            qs = qs.filter(reduce(lambda a, b: a | b, search_filters)).distinct()

        return qs.select_related("workorder", "workorder__budget", "workorder__budget__customer").prefetch_related(Prefetch("items", queryset=NfseItem.objects.order_by("-id"), to_attr="prefetched_items")).order_by("-criado_em", "-pk")

    def _get_filtered_requests(self, *, state: dict[str, Any]) -> tuple[list[NfeRequest], list[NfseRequest]]:
        if not state["is_valid"]:
            return [], []

        start_date = state["start_date"]
        end_date = state["end_date"]
        selected_note_type = str(state["selected_note_type"])

        nfe_requests = list(self._build_nfe_queryset(start_date=start_date, end_date=end_date, search_raw=state["search_raw"])) if selected_note_type in {"all", "nfe"} else []
        nfse_requests = list(self._build_nfse_queryset(start_date=start_date, end_date=end_date, search_raw=state["search_raw"])) if selected_note_type in {"all", "nfse"} else []
        return nfe_requests, nfse_requests

    @staticmethod
    def _get_latest_prefetched_item(request_obj: object) -> object | None:
        prefetched_items = getattr(request_obj, "prefetched_items", None)
        if not prefetched_items:
            return None
        latest_item: object = prefetched_items[0]
        return latest_item

    def _build_available_document_labels(self, *, note_type: str, item: object | None) -> list[str]:
        if item is None:
            return []

        labels: list[str] = []
        for document_group in ("xml", "pdfs"):
            for field_name, label in self.DOCUMENT_LABELS_BY_TYPE[note_type][document_group]:
                if str(getattr(item, field_name, "") or "").strip():
                    labels.append(label)
        return labels

    def _build_detail_url(self, *, view_name: str, pk: int, state: dict[str, Any]) -> str:
        return append_query_params(
            url=reverse(view_name, kwargs={"pk": pk}),
            params=build_issued_documents_origin_params(
                data_inicial=state["start_raw"],
                data_final=state["end_raw"],
                tipo=state["selected_note_type"],
                search=state["search_raw"],
            ),
        )

    def _build_nfe_row(self, request_obj: NfeRequest, *, state: dict[str, Any]) -> dict[str, Any]:
        latest_item = self._get_latest_prefetched_item(request_obj)
        available_documents = self._build_available_document_labels(note_type="nfe", item=latest_item)
        latest_series = str(getattr(latest_item, "series", "") or "").strip() if latest_item is not None else ""
        series_value = latest_series or (str(request_obj.reserved_series) if request_obj.reserved_series is not None else "-")
        has_xml = self._item_has_document_group(note_type="nfe", item=latest_item, document_group="xml")
        has_pdf = self._item_has_document_group(note_type="nfe", item=latest_item, document_group="pdfs")

        return {
            "note_type": "nfe",
            "note_type_label": "Nota Fiscal de Produto",
            "note_type_badge_class": "badge-soft badge-info",
            "request_id": request_obj.pk,
            "selection_key": f"nfe:{request_obj.pk}",
            "has_xml": has_xml,
            "has_pdf": has_pdf,
            "is_selectable": has_xml or has_pdf,
            "number": request_obj.number_display,
            "reference": f"Serie {series_value}",
            "workorder_id": request_obj.workorder.get_id,
            "customer_name": request_obj.customer_name,
            "created_at": request_obj.criado_em,
            "status_badge": request_obj.nfe_request_status_badge,
            "available_documents": available_documents,
            "detail_url": self._build_detail_url(view_name="finance:nfe_detail", pk=request_obj.pk, state=state),
        }

    def _build_nfse_row(self, request_obj: NfseRequest, *, state: dict[str, Any]) -> dict[str, Any]:
        latest_item = self._get_latest_prefetched_item(request_obj)
        available_documents = self._build_available_document_labels(note_type="nfse", item=latest_item)
        note_number = str(getattr(latest_item, "number", "") or "").strip() if latest_item is not None else ""
        rps_number = str(getattr(latest_item, "rps_number", "") or "").strip() if latest_item is not None else ""
        rps_series = str(getattr(latest_item, "rps_series", "") or "").strip() if latest_item is not None else ""
        reference_parts = []
        if rps_number:
            reference_parts.append(f"RPS {rps_number}")
        if rps_series:
            reference_parts.append(f"Serie {rps_series}")
        has_xml = self._item_has_document_group(note_type="nfse", item=latest_item, document_group="xml")
        has_pdf = self._item_has_document_group(note_type="nfse", item=latest_item, document_group="pdfs")

        return {
            "note_type": "nfse",
            "note_type_label": "Nota Fiscal Serviço",
            "note_type_badge_class": "badge-soft badge-success",
            "request_id": request_obj.pk,
            "selection_key": f"nfse:{request_obj.pk}",
            "has_xml": has_xml,
            "has_pdf": has_pdf,
            "is_selectable": has_xml or has_pdf,
            "number": note_number or request_obj.rps_number_display,
            "reference": " / ".join(reference_parts) if reference_parts else "-",
            "workorder_id": request_obj.workorder.get_id,
            "customer_name": request_obj.customer_name,
            "created_at": request_obj.criado_em,
            "status_badge": request_obj.nfse_request_status_badge,
            "available_documents": available_documents,
            "detail_url": self._build_detail_url(view_name="finance:nfse_detail", pk=request_obj.pk, state=state),
        }

    def _build_rows(self, *, nfe_requests: list[NfeRequest], nfse_requests: list[NfseRequest], state: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [self._build_nfe_row(request_obj, state=state) for request_obj in nfe_requests]
        rows.extend(self._build_nfse_row(request_obj, state=state) for request_obj in nfse_requests)
        rows.sort(key=lambda row: (row["created_at"], row["request_id"]), reverse=True)
        return rows

    def _collect_document_entries(self, *, nfe_requests: list[NfeRequest], nfse_requests: list[NfseRequest], document_group: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []

        for request_obj in nfe_requests:
            latest_item = self._get_latest_prefetched_item(request_obj)
            if latest_item is None:
                continue

            for _document_name, field_name, extension in self.DOCUMENT_SPECS_BY_TYPE["nfe"][document_group]:
                document_url = str(getattr(latest_item, field_name, "") or "").strip()
                if not document_url:
                    continue
                entries.append(
                    {
                        "archive_name": self._build_document_filename(
                            identifier=self._build_nfe_archive_identifier(item=latest_item, request_obj=request_obj),
                            extension=extension,
                        ),
                        "url": document_url,
                    }
                )

        for request_obj in nfse_requests:
            latest_item = self._get_latest_prefetched_item(request_obj)
            if latest_item is None:
                continue

            for _document_name, field_name, extension in self.DOCUMENT_SPECS_BY_TYPE["nfse"][document_group]:
                document_url = str(getattr(latest_item, field_name, "") or "").strip()
                if not document_url:
                    continue
                identifier = getattr(latest_item, "number", "") or getattr(latest_item, "rps_number", "") or request_obj.rps_number_display
                entries.append(
                    {
                        "archive_name": self._build_document_filename(
                            identifier=identifier,
                            extension=extension,
                        ),
                        "url": document_url,
                    }
                )

        return self._ensure_unique_archive_names(entries)

    @staticmethod
    def _build_nfe_archive_identifier(*, item: object, request_obj: NfeRequest) -> object:
        access_key = str(getattr(item, "access_key", "") or "").strip()
        if access_key:
            return f"NFe{access_key}"
        return getattr(item, "number", "") or request_obj.number_display

    @staticmethod
    def _ensure_unique_archive_names(entries: list[dict[str, str]]) -> list[dict[str, str]]:
        seen_names: dict[str, int] = {}
        unique_entries: list[dict[str, str]] = []

        for entry in entries:
            archive_name = entry["archive_name"]
            seen_count = seen_names.get(archive_name, 0) + 1
            seen_names[archive_name] = seen_count

            if seen_count == 1:
                unique_entries.append(entry)
                continue

            base_name, separator, suffix = archive_name.rpartition(".")
            if not separator:
                base_name = archive_name
                suffix = ""

            deduplicated_name = f"{base_name}-{seen_count}"
            if suffix:
                deduplicated_name = f"{deduplicated_name}.{suffix}"

            unique_entries.append({**entry, "archive_name": deduplicated_name})

        return unique_entries

    def _build_document_filename(self, *, identifier: object, extension: str) -> str:
        safe_identifier = self._sanitize_archive_fragment(identifier)
        return f"{safe_identifier}.{extension}"


class IssuedDocumentsListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, IssuedDocumentsFilterMixin, TemplateView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/issued_documents_list.html"
    htmx_template_name = "finance/partials/issued_documents_results.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        state = self._get_filter_state()
        nfe_requests, nfse_requests = self._get_filtered_requests(state=state)
        rows = self._build_rows(nfe_requests=nfe_requests, nfse_requests=nfse_requests, state=state)

        context.update(
            {
                "filter_state": state,
                "note_type_choices": self.NOTE_TYPE_CHOICES,
                "issued_note_rows": rows,
                "issued_notes_total": len(rows),
                "issued_nfe_total": len(nfe_requests),
                "issued_nfse_total": len(nfse_requests),
                "download_xml_url": reverse("finance:issued_documents_download", kwargs={"document_group": "xml"}),
                "download_pdfs_url": reverse("finance:issued_documents_download", kwargs={"document_group": "pdfs"}),
            }
        )
        return context


class IssuedDocumentsArchiveDownloadView(LoginRequiredMixin, WorkshopScopedMixin, IssuedDocumentsFilterMixin, View):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    def post(self, request, *args, **kwargs):
        document_group = str(kwargs.get("document_group") or "").strip().lower()
        if document_group not in {"xml", "pdfs"}:
            raise Http404("Grupo de documentos nao suportado")

        nfe_ids, nfse_ids = self._get_selected_request_ids()
        if not nfe_ids and not nfse_ids:
            return HttpResponse("Selecione ao menos uma nota para baixar.", status=400, content_type="text/plain; charset=utf-8")

        nfe_requests, nfse_requests = self._get_selected_requests(nfe_ids=nfe_ids, nfse_ids=nfse_ids)
        entries = self._collect_document_entries(nfe_requests=nfe_requests, nfse_requests=nfse_requests, document_group=document_group)
        if not entries:
            return HttpResponse("Nenhum documento disponivel para as notas selecionadas.", status=404, content_type="text/plain; charset=utf-8")

        archive_buffer = BytesIO()
        try:
            downloaded_entries = self._download_document_entries(entries=entries)
            with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive_file:
                for entry, downloaded in downloaded_entries:
                    archive_file.writestr(entry["archive_name"], downloaded.content)
        except FiscalServiceError as exc:
            logger.exception(
                "issued_documents_archive_download_failed",
                extra={"workshop_id": self.workshop.pk, "document_group": document_group},
            )
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        archive_filename = self._build_archive_filename(document_group=document_group)
        response = HttpResponse(archive_buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{archive_filename}"'
        return response

    def _build_archive_filename(self, *, document_group: str) -> str:
        selected_note_type = self.ARCHIVE_TYPE_LABELS.get(self._get_selected_note_type(), "todas")
        document_group_label = self.DOCUMENT_GROUP_LABELS.get(document_group, document_group)
        return f"{selected_note_type}-{document_group_label}.zip"

    def _download_document_entries(self, *, entries: list[dict[str, str]]) -> list[tuple[dict[str, str], Any]]:
        if len(entries) == 1:
            entry = entries[0]
            return [(entry, get_fiscal_service().download_document(workshop=self.workshop, url=entry["url"]))]

        downloaded_entries: list[tuple[dict[str, str], Any]] = []
        max_workers = min(ARCHIVE_DOWNLOAD_MAX_WORKERS, len(entries))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(get_fiscal_service().download_document, workshop=self.workshop, url=entry["url"]): entry for entry in entries
            }
            for future in as_completed(future_map):
                entry = future_map[future]
                downloaded_entries.append((entry, future.result()))

        downloaded_entries.sort(key=lambda item: item[0]["archive_name"])
        return downloaded_entries
