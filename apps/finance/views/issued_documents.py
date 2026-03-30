from __future__ import annotations

import re
import zipfile
from datetime import date
from io import BytesIO
from typing import Any
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.models.finance import NfeItem, NfeRequest, NfseItem, NfseRequest
from apps.finance.services.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.workshops.mixin import WorkshopScopedMixin


class IssuedDocumentsFilterMixin:
    NOTE_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
        ("all", "Todas"),
        ("nfe", "NF-e"),
        ("nfse", "NFS-e"),
    )

    DOCUMENT_LABELS_BY_TYPE: dict[str, dict[str, list[tuple[str, str]]]] = {
        "nfe": {
            "xml": [("xml_url", "XML")],
            "pdfs": [
                ("danfe_url", "DANFE"),
                ("danfe_simple_url", "DANFE simples"),
                ("danfe_label_url", "DANFE etiqueta"),
            ],
        },
        "nfse": {
            "xml": [("xml_url", "XML")],
            "pdfs": [
                ("pdf_nfse_url", "PDF NFS-e"),
                ("pdf_rps_url", "PDF RPS"),
            ],
        },
    }

    ARCHIVE_TYPE_LABELS: dict[str, str] = {
        "all": "todas-as-notas",
        "nfe": "notas-fiscais-produto",
        "nfse": "notas-fiscais-servico",
    }

    DOCUMENT_GROUP_LABELS: dict[str, str] = {
        "xml": "xmls",
        "pdfs": "pdfs",
    }

    DOCUMENT_SPECS_BY_TYPE: dict[str, dict[str, list[tuple[str, str, str]]]] = {
        "nfe": {
            "xml": [("xml", "xml_url", "xml")],
            "pdfs": [
                ("danfe", "danfe_url", "pdf"),
                ("danfe-simples", "danfe_simple_url", "pdf"),
                ("danfe-etiqueta", "danfe_label_url", "pdf"),
            ],
        },
        "nfse": {
            "xml": [("xml", "xml_url", "xml")],
            "pdfs": [
                ("pdf-nfse", "pdf_nfse_url", "pdf"),
                ("pdf-rps", "pdf_rps_url", "pdf"),
            ],
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

    def _get_selected_note_type(self) -> str:
        raw_value = str(self.request.GET.get("tipo") or "all").strip().lower()
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
        filter_error = ""

        if start_raw or end_raw:
            if not start_raw or not end_raw:
                filter_error = "Selecione a data inicial e a data final para consultar as notas."
            elif start_date is None or end_date is None:
                filter_error = "Informe um periodo valido para consultar as notas."
            elif start_date > end_date:
                filter_error = "A data inicial nao pode ser maior que a data final."

        is_valid = bool(start_date and end_date and not filter_error)

        return {
            "start_raw": start_raw,
            "end_raw": end_raw,
            "start_date": start_date,
            "end_date": end_date,
            "selected_note_type": selected_note_type,
            "selected_note_type_label": dict(self.NOTE_TYPE_CHOICES).get(selected_note_type, "Todas"),
            "has_selected_period": bool(start_raw and end_raw),
            "is_valid": is_valid,
            "filter_error": filter_error,
        }

    @staticmethod
    def _sanitize_archive_fragment(value: object) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
        normalized = normalized.strip("-._")
        return normalized or "documento"

    def _build_nfe_queryset(self, *, start_date: date, end_date: date):
        return (
            NfeRequest.objects.filter(workshop=self.workshop, criado_em__date__range=(start_date, end_date))
            .select_related("workorder", "workorder__budget", "workorder__budget__customer")
            .prefetch_related(Prefetch("items", queryset=NfeItem.objects.order_by("-id"), to_attr="prefetched_items"))
            .order_by("-criado_em", "-pk")
        )

    def _build_nfse_queryset(self, *, start_date: date, end_date: date):
        return (
            NfseRequest.objects.filter(workshop=self.workshop, criado_em__date__range=(start_date, end_date))
            .select_related("workorder", "workorder__budget", "workorder__budget__customer")
            .prefetch_related(Prefetch("items", queryset=NfseItem.objects.order_by("-id"), to_attr="prefetched_items"))
            .order_by("-criado_em", "-pk")
        )

    def _get_filtered_requests(self, *, state: dict[str, Any]) -> tuple[list[NfeRequest], list[NfseRequest]]:
        if not state["is_valid"]:
            return [], []

        start_date = state["start_date"]
        end_date = state["end_date"]
        selected_note_type = str(state["selected_note_type"])

        nfe_requests = list(self._build_nfe_queryset(start_date=start_date, end_date=end_date)) if selected_note_type in {"all", "nfe"} else []
        nfse_requests = list(self._build_nfse_queryset(start_date=start_date, end_date=end_date)) if selected_note_type in {"all", "nfse"} else []
        return nfe_requests, nfse_requests

    @staticmethod
    def _get_latest_prefetched_item(request_obj: object) -> object | None:
        prefetched_items = getattr(request_obj, "prefetched_items", None)
        if not prefetched_items:
            return None
        return prefetched_items[0]

    def _build_available_document_labels(self, *, note_type: str, item: object | None) -> list[str]:
        if item is None:
            return []

        labels: list[str] = []
        for document_group in ("xml", "pdfs"):
            for field_name, label in self.DOCUMENT_LABELS_BY_TYPE[note_type][document_group]:
                if str(getattr(item, field_name, "") or "").strip():
                    labels.append(label)
        return labels

    def _build_nfe_row(self, request_obj: NfeRequest) -> dict[str, Any]:
        latest_item = self._get_latest_prefetched_item(request_obj)
        available_documents = self._build_available_document_labels(note_type="nfe", item=latest_item)
        latest_series = str(getattr(latest_item, "series", "") or "").strip() if latest_item is not None else ""
        series_value = latest_series or (str(request_obj.reserved_series) if request_obj.reserved_series is not None else "-")

        return {
            "note_type": "nfe",
            "note_type_label": "NF-e",
            "note_type_badge_class": "badge-soft badge-info",
            "request_id": request_obj.pk,
            "number": request_obj.number_display,
            "reference": f"Serie {series_value}",
            "workorder_id": request_obj.workorder_id,
            "customer_name": request_obj.customer_name,
            "created_at": request_obj.criado_em,
            "status_badge": request_obj.nfe_request_status_badge,
            "available_documents": available_documents,
            "detail_url": reverse("finance:nfe_detail", kwargs={"pk": request_obj.pk}),
        }

    def _build_nfse_row(self, request_obj: NfseRequest) -> dict[str, Any]:
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

        return {
            "note_type": "nfse",
            "note_type_label": "NFS-e",
            "note_type_badge_class": "badge-soft badge-success",
            "request_id": request_obj.pk,
            "number": note_number or request_obj.rps_number_display,
            "reference": " / ".join(reference_parts) if reference_parts else "-",
            "workorder_id": request_obj.workorder_id,
            "customer_name": request_obj.customer_name,
            "created_at": request_obj.criado_em,
            "status_badge": request_obj.nfse_request_status_badge,
            "available_documents": available_documents,
            "detail_url": reverse("finance:nfse_detail", kwargs={"pk": request_obj.pk}),
        }

    def _build_rows(self, *, nfe_requests: list[NfeRequest], nfse_requests: list[NfseRequest]) -> list[dict[str, Any]]:
        rows = [self._build_nfe_row(request_obj) for request_obj in nfe_requests]
        rows.extend(self._build_nfse_row(request_obj) for request_obj in nfse_requests)
        rows.sort(key=lambda row: (row["created_at"], row["request_id"]), reverse=True)
        return rows

    def _build_download_query_string(self, *, state: dict[str, Any]) -> str:
        if not state["is_valid"]:
            return ""

        return urlencode(
            {
                "data_inicial": state["start_raw"],
                "data_final": state["end_raw"],
                "tipo": state["selected_note_type"],
            }
        )

    def _build_archive_folder(self, *, note_type: str, request_pk: int, identifier: object) -> str:
        safe_identifier = self._sanitize_archive_fragment(identifier)
        note_type_label = "NF-e" if note_type == "nfe" else "NFS-e"
        return f"{note_type_label}/{safe_identifier}-solicitacao-{request_pk}"

    def _collect_document_entries(self, *, nfe_requests: list[NfeRequest], nfse_requests: list[NfseRequest], document_group: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []

        for request_obj in nfe_requests:
            latest_item = self._get_latest_prefetched_item(request_obj)
            if latest_item is None:
                continue

            folder = self._build_archive_folder(
                note_type="nfe",
                request_pk=request_obj.pk,
                identifier=getattr(latest_item, "number", "") or getattr(latest_item, "access_key", "") or request_obj.number_display,
            )
            for document_name, field_name, extension in self.DOCUMENT_SPECS_BY_TYPE["nfe"][document_group]:
                document_url = str(getattr(latest_item, field_name, "") or "").strip()
                if not document_url:
                    continue
                entries.append({"archive_name": f"{folder}/{self._build_document_filename(note_type='nfe', identifier=getattr(latest_item, 'number', '') or request_obj.number_display, document_name=document_name, extension=extension)}", "url": document_url})

        for request_obj in nfse_requests:
            latest_item = self._get_latest_prefetched_item(request_obj)
            if latest_item is None:
                continue

            folder = self._build_archive_folder(
                note_type="nfse",
                request_pk=request_obj.pk,
                identifier=getattr(latest_item, "number", "") or getattr(latest_item, "rps_number", "") or request_obj.rps_number_display,
            )
            for document_name, field_name, extension in self.DOCUMENT_SPECS_BY_TYPE["nfse"][document_group]:
                document_url = str(getattr(latest_item, field_name, "") or "").strip()
                if not document_url:
                    continue
                identifier = getattr(latest_item, "number", "") or getattr(latest_item, "rps_number", "") or request_obj.rps_number_display
                entries.append({"archive_name": f"{folder}/{self._build_document_filename(note_type='nfse', identifier=identifier, document_name=document_name, extension=extension)}", "url": document_url})

        return entries

    def _build_document_filename(self, *, note_type: str, identifier: object, document_name: str, extension: str) -> str:
        safe_identifier = self._sanitize_archive_fragment(identifier)
        label_map = {
            "nfe": {
                "xml": "xml-da-nf-e",
                "danfe": "danfe",
                "danfe-simples": "danfe-simples",
                "danfe-etiqueta": "danfe-etiqueta",
            },
            "nfse": {
                "xml": "xml-da-nfs-e",
                "pdf-nfse": "pdf-da-nfs-e",
                "pdf-rps": "pdf-do-rps",
            },
        }
        document_label = label_map[note_type].get(document_name, document_name)
        prefix = "nf-e" if note_type == "nfe" else "nfs-e"
        return f"{prefix}-{safe_identifier}-{document_label}.{extension}"


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
        rows = self._build_rows(nfe_requests=nfe_requests, nfse_requests=nfse_requests)
        download_query_string = self._build_download_query_string(state=state)
        xml_entries = self._collect_document_entries(nfe_requests=nfe_requests, nfse_requests=nfse_requests, document_group="xml") if state["is_valid"] else []
        pdf_entries = self._collect_document_entries(nfe_requests=nfe_requests, nfse_requests=nfse_requests, document_group="pdfs") if state["is_valid"] else []

        context.update(
            {
                "filter_state": state,
                "note_type_choices": self.NOTE_TYPE_CHOICES,
                "issued_note_rows": rows,
                "issued_notes_total": len(rows),
                "issued_nfe_total": len(nfe_requests),
                "issued_nfse_total": len(nfse_requests),
                "can_download_xml": bool(xml_entries),
                "can_download_pdfs": bool(pdf_entries),
                "download_xml_url": f"{reverse('finance:issued_documents_download', kwargs={'document_group': 'xml'})}?{download_query_string}" if download_query_string else "",
                "download_pdfs_url": f"{reverse('finance:issued_documents_download', kwargs={'document_group': 'pdfs'})}?{download_query_string}" if download_query_string else "",
            }
        )
        return context


class IssuedDocumentsArchiveDownloadView(LoginRequiredMixin, WorkshopScopedMixin, IssuedDocumentsFilterMixin, View):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    def get(self, request, *args, **kwargs):
        document_group = str(kwargs.get("document_group") or "").strip().lower()
        if document_group not in {"xml", "pdfs"}:
            raise Http404("Grupo de documentos nao suportado")

        state = self._get_filter_state()
        if not state["is_valid"]:
            return HttpResponse("Informe um periodo valido para gerar o arquivo ZIP.", status=400, content_type="text/plain; charset=utf-8")

        nfe_requests, nfse_requests = self._get_filtered_requests(state=state)
        entries = self._collect_document_entries(nfe_requests=nfe_requests, nfse_requests=nfse_requests, document_group=document_group)
        if not entries:
            return HttpResponse("Nenhum documento disponivel para o filtro selecionado.", status=404, content_type="text/plain; charset=utf-8")

        archive_buffer = BytesIO()
        try:
            with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive_file:
                for entry in entries:
                    downloaded = download_webmania_document(workshop=self.workshop, url=entry["url"])
                    archive_file.writestr(entry["archive_name"], downloaded.content)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        archive_filename = self._build_archive_filename(state=state, document_group=document_group)
        response = HttpResponse(archive_buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{archive_filename}"'
        return response

    def _build_archive_filename(self, *, state: dict[str, Any], document_group: str) -> str:
        selected_note_type = self.ARCHIVE_TYPE_LABELS.get(str(state["selected_note_type"]), "todas-as-notas")
        document_group_label = self.DOCUMENT_GROUP_LABELS.get(document_group, document_group)
        start_fragment = self._sanitize_archive_fragment(state["start_raw"])
        end_fragment = self._sanitize_archive_fragment(state["end_raw"])
        return f"{selected_note_type}-{document_group_label}-{start_fragment}-ate-{end_fragment}.zip"
