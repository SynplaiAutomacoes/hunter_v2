import logging

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_exempt

from apps.budget.documents.provider import render_budget_pdf_document
from apps.budget.models import Budget
from apps.budget.pdf_context import build_budget_pdf_context, build_workshop_logo_data_uri
from apps.budget.service import BUDGET_SIGNATURE_DOCUMENT_ID_KEY, BUDGET_SIGNATURE_TOKEN_SALT, can_use_signed_budget_pdf, should_default_to_signed_budget_pdf
from apps.checklist.models import Checklist
from apps.checklist.services.files import ChecklistFileStorageError, read_checklist_pdf_file
from apps.core.domain.contracts.documents import DocumentPayload
from apps.core.infrastructure.pdf import render_pdf_from_html
from apps.core.infrastructure.pdf.renderer import build_pdf_http_response
from apps.core.domain.contracts.signature import SignatureServiceError
from apps.core.domain.contracts.documents import SignatureTokenError
from apps.core.infrastructure.providers import get_signature_service
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)

SIGNED_PDF_VARIANT = "signed"
BASE_PDF_VARIANT = "base"


@xframe_options_exempt
def visualizar_pdf(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget.objects.select_related("customer", "vehicle", "workshop"), pk=pk, workshop=workshop)
    context = build_budget_pdf_context(budget=budget, request=request, presentation="selected_items")

    return render(request, "budget/partials/pdf/visualizarPDF.html", context)


@xframe_options_exempt
def visualizar_pdf_gestor(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget.objects.select_related("customer", "vehicle", "workshop"), pk=pk, workshop=workshop)
    context = build_budget_pdf_context(budget=budget, request=request, presentation="selected_items")

    return render(request, "budget/partials/pdf/visualizarPDFGestor.html", context)


@xframe_options_exempt
def download_pdf_gestor(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget.objects.select_related("customer", "vehicle", "workshop"), pk=pk, workshop=workshop)
    context = build_budget_pdf_context(budget=budget, request=request, presentation="selected_items")
    html = render_to_string("budget/partials/pdf/visualizarPDFGestor.html", context)
    pdf_bytes = render_pdf_from_html(html)
    document = DocumentPayload(content=pdf_bytes, filename=f"orcamento_{budget.id}_gestor.pdf")
    return build_pdf_http_response(document=document, download=True)


@xframe_options_exempt
def visualizar_pdf_mecanico(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget.objects.select_related("customer", "vehicle", "workshop"), pk=pk, workshop=workshop)
    context = build_budget_pdf_context(budget=budget, request=request, presentation="selected_items")

    return render(request, "budget/partials/pdf/visualizarPDFMecanico.html", context)


@xframe_options_exempt
def visualizar_pdf_checklist(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget.objects.select_related("customer", "vehicle"), pk=pk, workshop=workshop)

    checklist_id = request.GET.get("checklist")
    if not checklist_id:
        raise Http404("Checklist nao informado")

    try:
        checklist_id_int = int(checklist_id)
    except (TypeError, ValueError):
        raise Http404("Checklist invalido")

    checklist = get_object_or_404(Checklist.objects.prefetch_related("items"), pk=checklist_id_int, workshop=workshop)

    if checklist.source == Checklist.ChecklistSource.PDF:
        file_id = str(checklist.pdf_file_key or "").strip()
        if not file_id:
            raise Http404("Checklist sem PDF importado")
        try:
            stored_pdf = read_checklist_pdf_file(file_id=file_id)
        except ChecklistFileStorageError as exc:
            raise Http404(str(exc)) from exc

        response = HttpResponse(stored_pdf.content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{stored_pdf.filename}"'
        return response

    checklist_items = checklist.items.all().order_by("order", "id")
    checklist_rows = []
    group_number_by_name = {}
    item_counter_by_group = {}
    next_group_number = 1

    for checklist_item in checklist_items:
        group_name = (checklist_item.group or "").strip() or "Geral"
        item_description = (checklist_item.description or "").strip() or "-"

        if group_name not in group_number_by_name:
            group_number_by_name[group_name] = next_group_number
            item_counter_by_group[group_name] = 0
            next_group_number += 1

        item_counter_by_group[group_name] += 1
        group_number = group_number_by_name[group_name]
        item_number_in_group = item_counter_by_group[group_name]

        checklist_rows.append(
            {
                "index": f"{group_number}.{item_number_in_group}",
                "description": f"{group_name} - {item_description}",
                "response_type": checklist_item.response_type,
            }
        )

    try:
        webmania_company = workshop.webmania_company
    except ObjectDoesNotExist:
        webmania_company = None

    workshop_cep = (getattr(webmania_company, "cep", "") or "").strip()
    workshop_city = (getattr(webmania_company, "cidade", "") or "").strip()
    if workshop_cep and workshop_city:
        workshop_cep_city = f"{workshop_cep} - {workshop_city}"
    else:
        workshop_cep_city = workshop_cep or workshop_city or "-"

    workshop_header = {
        "name": workshop.name or "-",
        "address": workshop.address or "-",
        "cep_city": workshop_cep_city,
        "phone": workshop.pdf_phone,
    }

    context = {
        "budget": budget,
        "checklist": checklist,
        "checklist_rows": checklist_rows,
        "workshop_header": workshop_header,
        "workshop_logo_data_uri": build_workshop_logo_data_uri(workshop=workshop),
        "auto_print": request.GET.get("autoprint") == "1",
    }

    return render(request, "budget/partials/pdf/pdf_checklist.html", context)


def _get_budget_from_signature_token(token):
    try:
        payload = get_signature_service().parse_signature_token(
            token=token,
            token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
            document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError:
        raise Http404("Arquivo não encotrado")

    budget = get_object_or_404(Budget.objects.select_related("workshop", "customer", "vehicle"), pk=payload["document_id"])

    if not budget.signature_token_active:
        raise Http404("Arquivo não encotrado")

    if budget.signature_token_version != payload["version"]:
        raise Http404("Arquivo não encotrado")

    return budget


def signature_preview(request, token):
    budget = _get_budget_from_signature_token(token)
    context = build_budget_pdf_context(budget=budget, request=request, presentation="selected_items")

    return render(request, "budget/partials/pdf/visualizarPDF.html", context)


def signature_file(request, token):
    budget = _get_budget_from_signature_token(token)

    try:
        document = render_budget_pdf_document(
            budget=budget,
            request=request,
            filename=f"orcamento_{budget.id}.pdf",
        )
    except Exception:
        logger.exception("budget_pdf_playwright_failed", extra={"budget_id": budget.id, "pdf_type": "signature"})
        return HttpResponse("Erro ao gerar arquivo de assinatura", status=500)

    return build_pdf_http_response(document=document, download=False)


def _build_budget_pdf_file_response(*, budget: Budget, download: bool, use_signed_name: bool, pdf_bytes: bytes) -> HttpResponse:
    filename_suffix = "assinado" if use_signed_name else "base"
    document = DocumentPayload(
        content=pdf_bytes,
        filename=f"orcamento_{budget.id}_{filename_suffix}.pdf",
    )
    return build_pdf_http_response(document=document, download=download)


def _get_requested_pdf_variant(request) -> str | None:
    requested_variant = str(request.GET.get("variant") or "").strip().lower()
    if requested_variant == BASE_PDF_VARIANT:
        return BASE_PDF_VARIANT
    if requested_variant == SIGNED_PDF_VARIANT:
        return SIGNED_PDF_VARIANT
    return None


@xframe_options_exempt
def visualizar_pdf_assinatura(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget.objects.select_related("workshop"), pk=pk, workshop=workshop)
    should_download = request.GET.get("download") == "1"
    requested_variant = _get_requested_pdf_variant(request)

    if requested_variant is None:
        requested_variant = SIGNED_PDF_VARIANT if should_default_to_signed_budget_pdf(budget=budget) else BASE_PDF_VARIANT

    if requested_variant == SIGNED_PDF_VARIANT and can_use_signed_budget_pdf(budget=budget):
        try:
            signed_pdf = get_signature_service().download_signed_document(
                document_id=budget.signature_document_id,
                envelope_id=budget.signature_external_id,
            )
            return _build_budget_pdf_file_response(
                budget=budget,
                download=should_download,
                use_signed_name=True,
                pdf_bytes=signed_pdf,
            )
        except SignatureServiceError:
            logger.warning("budget_signed_pdf_load_failed", extra={"budget_id": budget.id, "document_id": budget.signature_document_id, "envelope_id": budget.signature_external_id})

    try:
        document = render_budget_pdf_document(
            budget=budget,
            request=request,
            filename=f"orcamento_{budget.id}_base.pdf",
        )
    except Exception:
        logger.exception("budget_pdf_base_generation_failed", extra={"budget_id": budget.id, "pdf_type": "view"})
        return HttpResponse("Erro ao gerar PDF", status=500)

    return build_pdf_http_response(document=document, download=should_download)
