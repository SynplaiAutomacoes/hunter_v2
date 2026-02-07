from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_exempt
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.workshops.util.workshops import get_active_workshop_or_404


@xframe_options_exempt
def visualizar_pdf(request, pk):
    workshop = get_active_workshop_or_404(request)
    budget = get_object_or_404(Budget, pk=pk, workshop=workshop)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    context = {"budget": budget, "produtos": produtos, "servicos": servicos, "total_produtos": budget.total_products_value, "total_servicos": budget.total_services_value, "desconto": budget.discount_value, "total_geral": budget.total_budget_value, "observacao": workshop.pdf_observation}

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
