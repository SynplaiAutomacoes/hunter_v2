import logging
from math import ceil

from django.core import signing
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.core.pdf_playwright import render_pdf_from_url
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)

PRODUCTS_PER_PAGE = 4
SERVICES_PER_PAGE = 2


def _build_pdf_pages(produtos: list[BudgetItem], servicos: list[BudgetItem]) -> list[dict]:
    total_pages = max(ceil(len(produtos) / PRODUCTS_PER_PAGE) if produtos else 0, ceil(len(servicos) / SERVICES_PER_PAGE) if servicos else 0, 1)

    pages: list[dict] = []
    for index in range(total_pages):
        products_start = index * PRODUCTS_PER_PAGE
        services_start = index * SERVICES_PER_PAGE
        pages.append(
            {
                "produtos": produtos[products_start : products_start + PRODUCTS_PER_PAGE],
                "servicos": servicos[services_start : services_start + SERVICES_PER_PAGE],
                "page_number": index + 1,
                "total_pages": total_pages,
            }
        )

    return pages


def _build_budget_pdf_context(*, budget: Budget, observacao: str) -> dict:
    itens_all = BudgetItem.objects.filter(budget=budget).order_by("id")
    produtos = list(itens_all.filter(product__isnull=False))
    servicos = list(itens_all.filter(service__isnull=False))

    return {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "pages": _build_pdf_pages(produtos, servicos),
        "total_produtos": budget.total_products_value,
        "total_servicos": budget.total_services_value,
        "desconto": budget.discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": observacao,
    }


@xframe_options_exempt
def visualizar_pdf(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    context = _build_budget_pdf_context(budget=budget, observacao=workshop.pdf_observation)

    return render(request, "budget/partials/pdf/visualizarPDF.html", context)


@xframe_options_exempt
def visualizar_pdf_gestor(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    total_profit_product_value = Money(0, "BRL")
    for p in produtos:
        total_profit_product_value += p.profit_value

    total_profit_service_value = Money(0, "BRL")
    for s in servicos:
        total_profit_service_value += s.profit_value

    context = {"budget": budget, "produtos": produtos, "servicos": servicos, "observacao": workshop.pdf_observation, "total_profit_product_value": total_profit_product_value, "total_profit_service_value": total_profit_service_value}

    return render(request, "budget/partials/pdf/visualizarPDFGestor.html", context)


@xframe_options_exempt
def visualizar_pdf_mecanico(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    context = {"budget": budget, "produtos": produtos, "servicos": servicos, "observacao": workshop.pdf_observation}

    return render(request, "budget/partials/pdf/visualizarPDFMecanico.html", context)


def _get_budget_from_signature_token(token):
    try:
        payload = signing.loads(token, salt="budget-signature-file")
        budget_id = int(payload["budget_id"])
        token_version = int(payload["version"])

    except (signing.BadSignature, KeyError, ValueError, TypeError):
        raise Http404("Arquivo não encotrado")

    budget = get_object_or_404(Budget.objects.select_related("workshop", "customer", "vehicle"), pk=budget_id)

    if not budget.signature_token_active:
        raise Http404("Arquivo não encotrado")

    if budget.signature_token_version != token_version:
        raise Http404("Arquivo não encotrado")

    return budget


def signature_preview(request, token):
    budget = _get_budget_from_signature_token(token)
    context = _build_budget_pdf_context(budget=budget, observacao=budget.workshop.pdf_observation)

    return render(request, "budget/partials/pdf/visualizarPDF.html", context)


def signature_file(request, token):
    budget = _get_budget_from_signature_token(token)

    preview_path = reverse("budget:signature_preview", args=[token])
    preview_url = request.build_absolute_uri(preview_path)

    try:
        pdf_bytes = render_pdf_from_url(preview_url)
    except Exception:
        logger.exception("Falha ao gerar PDF via Playwright para assinatura", extra={"budget_id": budget.id})
        return HttpResponse("Erro ao gerar arquivo de assinatura", status=500)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="orcamento_{budget.id}.pdf"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"

    return response
