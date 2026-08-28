# ruff: noqa: F403,F405
from apps.budget.forms.layouts.step4_assets import build_step4_assets_html
from .base import BudgetStepBaseForm
from .common import *


class BudgetStep4Form(BudgetStepBaseForm):
    class Meta:
        model = Budget
        fields = []
        widgets = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        budget = _get_budget_with_prefetched_items(self.instance)
        rows = _render_budget_items_rows(budget, step6=False)
        products_html = rows["product"]
        services_html = rows["service"]
        kits_html = rows["kit"]

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            alert_confirm_layout(),
            HTML(
                """
                <style>
                    .budget-step4-table {
                        table-layout: fixed;
                    }

                    .budget-step4-table :where(th, td) {
                        vertical-align: middle;
                    }

                    .budget-step4-table .budget-step4-description,
                    .budget-step4-table .budget-step4-application {
                        white-space: normal;
                        overflow-wrap: break-word;
                        word-break: normal;
                    }

                    .budget-step4-table .budget-step4-actions {
                        white-space: nowrap;
                    }

                    .budget-step4-table .budget-step4-select-col {
                        width: 3.25rem;
                    }

                    .budget-step4-table thead th {
                        font-size: 0.80rem;
                    }
                </style>
                """
            ),
            Div(
                # Coluna Esquerda: Seleção
                Div(
                    HTML(f'''
                        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6">
                            <h2 class="text-2xl font-bold">Seleção de Produtos, Serviços e Kits</h2>
                            <button
                                type="button"
                                class="btn btn-primary text-base btn-base mt-2 sm:mt-0"
                                hx-get="{reverse("budget:import_items_search_modal", kwargs={"pk": budget.pk})}"
                                hx-target="#modal-container"
                                onclick="form_modal.showModal()">
                                Importar de outro orçamento
                            </button>
                        </div>
                    '''),
                    # Seção de Produtos
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Produtos</h3>'),
                            HTML(f'''
                                <div class="flex flex-wrap gap-2 w-full sm:w-auto justify-end">
                                    <button
                                        type="button"
                                        id="delete-selected-products-btn"
                                        class="btn btn-error btn-outline w-full sm:w-auto hidden"
                                        disabled
                                        hx-post="{reverse("budget:remove_products_batch", kwargs={"budget_id": budget.pk})}"
                                        hx-include="#product-list-body input[name='selected_product_items']:checked"
                                        data-confirm="Deseja remover as peças selecionadas?">
                                        Deletar todos
                                    </button>
                                    <button
                                        type="button"
                                        class="btn btn-primary w-full sm:w-auto"
                                        hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "product"})}"
                                        hx-target="#modal-container"
                                        onclick="form_modal.showModal()">
                                        Inserir Produto
                                    </button>
                                </div>
                            '''),
                            css_class="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-sm table-zebra w-full budget-step4-table">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="budget-step4-select-col text-center">
                                                <input type="checkbox" id="select-all-products" class="checkbox text-white checkbox-sm" 
                                                       style="border-color: white; color: white;" aria-label="Selecionar todas as peças">
                                            </th>
                                            <th class="w-[16%] text-left">DESCRIÇÃO</th>
                                            <th class="w-[12%] text-left">APLICAÇÃO</th>
                                            <th class="w-[14%] text-center whitespace-normal break-words leading-tight">FORNECIDO PELO CLIENTE</th>
                                            <th class="w-[8%] text-center">QTD.</th>
                                            <th class="w-[10%] text-right">CUSTO</th>
                                            <th class="w-[10%] text-right">VALOR VENDA</th>
                                            <th class="w-[10%] text-right">CUSTO DE FRETE</th>
                                            <th class="w-[10%] text-right">TOTAL</th>
                                            <th class="w-[10%] text-center budget-step4-actions">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="product-list-body">
                                        {products_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="mb-8 rounded-lg shadow-md shadow-gray-300/50 overflow-x-auto",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Serviços
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Serviços</h3>'),
                            HTML(f'''
                                <div class="flex flex-wrap gap-2 w-full sm:w-auto justify-end">
                                    <button
                                        type="button"
                                        id="delete-selected-services-btn"
                                        class="btn btn-error btn-outline w-full sm:w-auto hidden"
                                        disabled
                                        hx-post="{reverse("budget:remove_services_batch", kwargs={"budget_id": budget.pk})}"
                                        hx-include="#service-list-body input[name='selected_service_items']:checked"
                                        data-confirm="Deseja remover os serviços selecionados?">
                                        Deletar todos
                                    </button>
                                    <button
                                        type="button"
                                        class="btn btn-primary w-full sm:w-auto"
                                        hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "service"})}"
                                        hx-target="#modal-container"
                                        onclick="form_modal.showModal()">
                                        Inserir Serviço
                                    </button>
                                </div>
                            '''),
                            css_class="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-sm table-zebra w-full budget-step4-table">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="budget-step4-select-col text-center">
                                                <input type="checkbox" id="select-all-services" class="checkbox text-white checkbox-sm" 
                                                       style="border-color: white; color: white;" aria-label="Selecionar todos os serviços">
                                            </th>
                                            <th class="w-[16%] text-left">DESCRIÇÃO</th>
                                            <th class="w-[8%] text-center">QTD.</th>
                                            <th class="w-[16%] text-right">CUSTO/MECÂNICO</th>
                                            <th class="w-[12%] text-right">VALOR VENDA</th>
                                            <th class="w-[12%] text-right">CUSTO DE FRETE</th>
                                            <th class="w-[12%] text-center">TEMPO</th>
                                            <th class="w-[12%] text-right">TOTAL</th>
                                            <th class="w-[12%] text-center budget-step4-actions">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="service-list-body">
                                        {services_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="mb-8 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Kits
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Kits</h3>'),
                            HTML(f'''
                                <div class="flex flex-wrap gap-2 w-full sm:w-auto justify-end">
                                    <button
                                        type="button"
                                        id="delete-selected-kits-btn"
                                        class="btn btn-error btn-outline w-full sm:w-auto hidden"
                                        disabled
                                        hx-post="{reverse("budget:remove_kits_batch", kwargs={"budget_id": budget.pk})}"
                                        hx-include="#kit-list-body input[name='selected_kit_items']:checked"
                                        data-confirm="Deseja remover os kits selecionados?">
                                        Deletar todos
                                    </button>
                                    <button
                                        type="button"
                                        class="btn btn-primary w-full sm:w-auto"
                                        hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "kit"})}"
                                        hx-target="#modal-container"
                                        onclick="form_modal.showModal()">
                                        Inserir Kit
                                    </button>
                                </div>
                            '''),
                            css_class="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-sm w-full budget-step4-table">
                                    <thead class="bg-primary text-primary-content">
                                        <tr>
                                            <th class="budget-step4-select-col text-center">
                                                <input type="checkbox" id="select-all-kits" class="checkbox text-white checkbox-sm" 
                                                       style="border-color: white; color: white;" aria-label="Selecionar todos os kits">
                                            </th>
                                            <th class="w-[22%] text-left">NOME</th>
                                            <th class="w-[8%] text-center">QTD.</th>
                                            <th class="w-[10%] text-center">PRODUTOS</th>
                                            <th class="w-[10%] text-center">SERVIÇOS</th>
                                            <th class="w-[14%] text-right">CUSTOS</th>
                                            <th class="w-[14%] text-right">PREÇO</th>
                                            <th class="w-[12%] text-center budget-step4-actions">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="kit-list-body">
                                        {kits_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="mb-4 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden",
                        ),
                        css_class="mb-6",
                    ),
                    css_class="col-span-12 xl:col-span-8",
                ),
                #
                # Coluna Direita
                Div(
                    Div(
                        HTML('<h2 class="text-2xl font-bold mb-4 mt-8">Resumo</h2>'),
                        Div(
                            HTML(render_to_string("budget/partials/components/budget_summary.html", {"budget": budget})),
                            css_class="sticky top-4",
                            css_id="budget-summary",
                        ),
                        css_class="p-6 h-fit text-lg",
                    ),
                    css_class="col-span-12 xl:col-span-4 mt-10 xl:mt-0",
                ),
                css_class="grid grid-cols-1 xl:grid-cols-12 gap-4",
            ),
        )

        # Adicionar listener para atualizar resumo dinamicamente
        self.helper.layout.append(
            HTML(build_step4_assets_html(budget_summary_url=reverse("budget:budget_summary", kwargs={"budget_id": budget.pk}))),
        )

    def save(self, commit=True):
        # Como este form é estrutural, o save lida com persistência de estado da etapa
        return super().save(commit=commit)
