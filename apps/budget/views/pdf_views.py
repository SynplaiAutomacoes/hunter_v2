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


def _build_pdf_pages(produtos: list[dict], servicos: list[dict]) -> list[dict]:
    total_pages = max(ceil(len(produtos) / PRODUCTS_PER_PAGE) if produtos else 0, ceil(len(servicos) / SERVICES_PER_PAGE) if servicos else 0, 1)

    pages: list[dict] = []
    for index in range(total_pages):
        products_start = index * PRODUCTS_PER_PAGE
        services_start = index * SERVICES_PER_PAGE
        page_products = produtos[products_start : products_start + PRODUCTS_PER_PAGE]
        page_services = servicos[services_start : services_start + SERVICES_PER_PAGE]

        pages.append(
            {
                "produtos": page_products,
                "servicos": page_services,
                "empty_product_rows": range(max(PRODUCTS_PER_PAGE - len(page_products), 0)),
                "empty_service_rows": range(max(SERVICES_PER_PAGE - len(page_services), 0)),
                "page_number": index + 1,
                "total_pages": total_pages,
            }
        )

    return pages


def _build_budget_pdf_context(*, budget: Budget, observacao: str) -> dict:
    itens_all = BudgetItem.objects.filter(budget=budget).select_related("product", "service", "kit").prefetch_related("kit__kit_products__product", "kit__kit_services__service", "kit_overrides").order_by("id")

    produtos: list[dict] = []
    servicos: list[dict] = []

    for item in itens_all:
        if item.product_id:
            produtos.append(
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "product_selling_price": item.product_selling_price,
                    "total_price": item.total_price,
                }
            )

        if item.service_id:
            servicos.append(
                {
                    "description": f"{item.description} x{item.quantity}" if item.quantity > 1 else item.description,
                }
            )

        if not item.kit_id:
            continue

        product_overrides, service_overrides = item._get_kit_override_maps()

        for kit_product in item.kit.kit_products.select_related("product").all():
            override = product_overrides.get(kit_product.product_id)
            quantity_per_kit = override.quantity if override else kit_product.quantity
            if quantity_per_kit <= 0:
                continue

            final_quantity = quantity_per_kit * item.quantity
            unit_price = override.product_selling_price if override else kit_product.product.selling_price
            shipping = override.shipping if override else Money(0, "BRL")
            line_total = ((unit_price * quantity_per_kit) + shipping) * item.quantity

            produtos.append(
                {
                    "description": f"{kit_product.product.name} (Kit: {item.kit.name})",
                    "quantity": final_quantity,
                    "product_selling_price": unit_price,
                    "total_price": line_total,
                }
            )

        for kit_service in item.kit.kit_services.select_related("service").all():
            override = service_overrides.get(kit_service.service_id)
            quantity_per_kit = override.quantity if override else kit_service.quantity
            if quantity_per_kit <= 0:
                continue

            final_quantity = quantity_per_kit * item.quantity
            label = f"{kit_service.service.name} (Kit: {item.kit.name})"
            servicos.append(
                {
                    "description": f"{label} x{final_quantity}" if final_quantity > 1 else label,
                }
            )

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
