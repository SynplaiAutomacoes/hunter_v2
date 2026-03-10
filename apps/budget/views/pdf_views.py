import logging

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_exempt

from apps.budget.documents.provider import render_budget_pdf_document
from apps.budget.models import Budget, SignatureStatus
from apps.budget.pdf_context import build_budget_pdf_context
from apps.budget.service import BUDGET_SIGNATURE_DOCUMENT_ID_KEY, BUDGET_SIGNATURE_TOKEN_SALT
from apps.checklist.models import Checklist
from apps.core.documents.contract import DocumentPayload
from apps.core.documents.http import build_pdf_http_response
from apps.core.documents.services import SignatureDeliveryServiceError, download_signed_document_content
from apps.core.documents.signature import SignatureTokenError, parse_document_signature_token
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)


@xframe_options_exempt
def visualizar_pdf(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    context = build_budget_pdf_context(budget=budget, observacao=workshop.pdf_observation, request=request)

    return render(request, "budget/partials/pdf/visualizarPDF.html", context)


@xframe_options_exempt
def visualizar_pdf_gestor(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    context = build_budget_pdf_context(budget=budget, observacao=workshop.pdf_observation, request=request)

    return render(request, "budget/partials/pdf/visualizarPDFGestor.html", context)


@xframe_options_exempt
def visualizar_pdf_mecanico(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    context = build_budget_pdf_context(budget=budget, observacao=workshop.pdf_observation, request=request)

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
        "phone": workshop.phone,
    }

    context = {
        "budget": budget,
        "checklist": checklist,
        "checklist_rows": checklist_rows,
        "workshop_header": workshop_header,
        "auto_print": request.GET.get("autoprint") == "1",
    }

    return render(request, "budget/partials/pdf/pdf_checklist.html", context)


def _get_budget_from_signature_token(token):
    try:
        payload = parse_document_signature_token(
            token=token,
            token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
            document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError:
        raise Http404("Arquivo não encotrado")

    budget = get_object_or_404(Budget.objects.select_related("workshop", "customer", "vehicle"), pk=payload.document_id)

    if not budget.signature_token_active:
        raise Http404("Arquivo não encotrado")

    if budget.signature_token_version != payload.version:
        raise Http404("Arquivo não encotrado")

    return budget


def signature_preview(request, token):
    budget = _get_budget_from_signature_token(token)
    context = build_budget_pdf_context(budget=budget, observacao=budget.workshop.pdf_observation, request=request)

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
        logger.exception("Falha ao gerar PDF via Playwright para assinatura", extra={"budget_id": budget.id})
        return HttpResponse("Erro ao gerar arquivo de assinatura", status=500)

    return build_pdf_http_response(document=document, download=False)


def _build_budget_pdf_file_response(*, budget: Budget, download: bool, use_signed_name: bool, pdf_bytes: bytes) -> HttpResponse:
    filename_suffix = "assinado" if use_signed_name else "base"
    document = DocumentPayload(
        content=pdf_bytes,
        filename=f"orcamento_{budget.id}_{filename_suffix}.pdf",
    )
    return build_pdf_http_response(document=document, download=download)


@xframe_options_exempt
def visualizar_pdf_assinatura(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget.objects.select_related("workshop"), pk=pk, workshop=workshop)
    should_download = request.GET.get("download") == "1"

    if (budget.signature_document_id or budget.signature_external_id) and budget.signature_request_status in {SignatureStatus.SENT, SignatureStatus.APPROVED}:
        try:
            signed_pdf = download_signed_document_content(
                document_id=budget.signature_document_id,
                envelope_id=budget.signature_external_id,
            )
            return _build_budget_pdf_file_response(
                budget=budget,
                download=should_download,
                use_signed_name=True,
                pdf_bytes=signed_pdf,
            )
        except SignatureDeliveryServiceError:
            logger.warning(
                "Falha ao carregar PDF assinado; retornando PDF base",
                extra={
                    "budget_id": budget.id,
                    "document_id": budget.signature_document_id,
                    "envelope_id": budget.signature_external_id,
                },
            )

    try:
        document = render_budget_pdf_document(
            budget=budget,
            request=request,
            filename=f"orcamento_{budget.id}_base.pdf",
        )
    except Exception:
        logger.exception("Falha ao gerar PDF base para visualizacao", extra={"budget_id": budget.id})
        return HttpResponse("Erro ao gerar PDF", status=500)

    return build_pdf_http_response(document=document, download=should_download)
