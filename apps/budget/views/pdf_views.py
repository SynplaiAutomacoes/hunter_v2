import logging

from django.core import signing
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_exempt
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.core.utils import render_to_pdf
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)

@xframe_options_exempt
def visualizar_pdf(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    context = {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "total_produtos": budget.total_products_value,
        "total_servicos": budget.total_services_value,
        "desconto": budget.discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": workshop.pdf_observation
    }

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
        "total_profit_service_value": total_profit_service_value
    }

    return render(request, "budget/partials/pdf/visualizarPDFGestor.html", context)


@xframe_options_exempt
def visualizar_pdf_mecanico(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    context = {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "observacao": workshop.pdf_observation
    }

    return render(request, "budget/partials/pdf/visualizarPDFMecanico.html", context)


def signature_file(request, token):
    try:
        payload = signing.loads(token, salt="budget-signature-file")
        budget_id = int(payload.get("budget_id"))
        token_version = int(payload.get("version"))

    except (signing.BadSignature, KeyError, ValueError, TypeError):
        raise Http404("Arquivo não encotrado")

    budget = get_object_or_404(Budget.objects.select_related("workshop", "customer", "vehicle"), pk=budget_id)

    if not budget.signature_token_active:
        raise Http404("Arquivo não encotrado")

    if budget.signature_token_version != token_version:
        raise Http404("Arquivo não encotrado")

    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    context = {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "total_produtos": budget.total_products_value,
        "total_servicos": budget.total_services_value,
        "desconto": budget.discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": budget.workshop.pdf_observation
    }

    pdf_buffer = render_to_pdf("budget/partials/pdf/visualizarPDF.html", context)
    if not pdf_buffer:
        logger.exception("Falha ao gerar PDF para assinatura", extra={"budget_id": budget.id})
        return HttpResponse("Erro ao gerar arquivo de assinatura", status=500)

    response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
    response['Content-Disposition'] = f'inline; filename="orcamento_{budget.id}.pdf"'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'no-store'

    return response
