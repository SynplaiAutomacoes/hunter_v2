import logging

from django.core import signing
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_exempt
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.budget.pdf_context import build_budget_pdf_context
from apps.checklist.models import Checklist
from apps.core.pdf_playwright import render_pdf_from_html
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
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    total_profit_product_value = Money(0, "BRL")
    for p in produtos:
        total_profit_product_value += p.profit_value

    total_profit_service_value = Money(0, "BRL")
    for s in servicos:
        total_profit_service_value += s.profit_value

    context = {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "observacao": workshop.pdf_observation,
        "total_profit_product_value": total_profit_product_value,
        "total_profit_service_value": total_profit_service_value,
    }

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


@xframe_options_exempt
def visualizar_pdf_checklist(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)

    checklist_id = request.GET.get("checklist")
    if not checklist_id:
        raise Http404("Checklist nao informado")

    try:
        checklist_id_int = int(checklist_id)
    except (TypeError, ValueError):
        raise Http404("Checklist invalido")

    checklist = get_object_or_404(Checklist.objects.prefetch_related("items"), pk=checklist_id_int, workshop=workshop)
    checklist_items = checklist.items.all().order_by("order", "id")

    context = {
        "budget": budget,
        "checklist": checklist,
        "checklist_items": checklist_items,
        "auto_print": request.GET.get("autoprint") == "1",
    }

    return render(request, "budget/partials/pdf/pdf_checklist.html", context)


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
    context = build_budget_pdf_context(budget=budget, observacao=budget.workshop.pdf_observation, request=request)

    return render(request, "budget/partials/pdf/visualizarPDF.html", context)


def signature_file(request, token):
    budget = _get_budget_from_signature_token(token)
    context = build_budget_pdf_context(budget=budget, observacao=budget.workshop.pdf_observation)
    html = render_to_string("budget/partials/pdf/visualizarPDF.html", context)

    try:
        pdf_bytes = render_pdf_from_html(html)
    except Exception:
        logger.exception("Falha ao gerar PDF via Playwright para assinatura", extra={"budget_id": budget.id})
        return HttpResponse("Erro ao gerar arquivo de assinatura", status=500)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="orcamento_{budget.id}.pdf"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"

    return response
