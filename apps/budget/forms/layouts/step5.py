# ruff: noqa: F403,F405
from apps.budget.forms.layouts.step5_assets import build_step5_assets_html
from apps.budget.forms.presenters.step5_context import build_step5_context
from apps.budget.forms.steps.common import *


def configure_budget_step5_form(form):
    form.fields["slider"].label = ""
    form.fields["slider"].help_text = ""
    form.fields["discount_percentage"].required = False
    form.fields["discount_value"].required = False
    form.fields["discount_type"].required = False
    form.fields["slider"].widget.attrs.update({"hx-post": reverse("budget:update_slider", args=[form.instance.pk]), "hx-trigger": "change", "hx-swap": "none"})

    budget = _get_budget_with_prefetched_items(form.instance)
    if budget.pk:
        form.fields["slider"].initial = budget.slider

    ctx = build_step5_context(budget)

    form.initial["discount_percentage"] = budget.display_resolved_discount_percentage
    form.initial["discount_value"] = budget.display_resolved_discount_value
    form.initial["discount_type"] = budget.discount_type or WorkOrderDiscountType.BOTH

    custo_pecas = ctx.custo_pecas
    custo_frete_pecas = ctx.custo_frete_pecas
    custo_frete_servicos = ctx.custo_frete_servicos
    custo_servico_terceiros = ctx.custo_servico_terceiros
    custo_hora_mecanico = ctx.custo_hora_mecanico
    custo_total_mao_obra = ctx.custo_total_mao_obra
    duracao_total = ctx.duracao_total
    venda_servico_terceiros = ctx.venda_servico_terceiros
    venda_pecas = ctx.venda_pecas
    venda_mao_obra = ctx.venda_mao_obra
    metodo_precificacao = ctx.metodo_precificacao
    lucro_operacional = ctx.lucro_operacional
    rentabilidade = ctx.rentabilidade
    rentabilidade_class = ctx.rentabilidade_class
    rentabilidade_bg = ctx.rentabilidade_bg
    status_texto = ctx.status_texto
    mlr = ctx.mlr
    mlo = ctx.mlo
    discount_display = ctx.discount_display
    step5_loading_hidden_class = ctx.step5_loading_hidden_class
    step5_method_hidden_class = ctx.step5_method_hidden_class
    step5_should_block_next_button = ctx.step5_should_block_next_button
    step5_calculated_input_value = ctx.step5_calculated_input_value

    form.helper = FormHelper()
    form.helper.form_tag = False
    form.helper.layout = Layout(
        HTML(
            build_step5_assets_html(
                metodo_precificacao=metodo_precificacao,
                step5_should_block_next_button=step5_should_block_next_button,
                mark_step5_calculation_viewed_url=reverse("budget:mark_step5_calculation_viewed", args=[form.instance.pk]),
                update_budget_discount_url=reverse("budget:update_budget_discount", args=[form.instance.pk]),
            )
        ),
        Div(
            HTML(f'<input type="hidden" name="step5_calculated" id="id_step5_calculated" value="{step5_calculated_input_value}">'),
            HTML('<h3 class="text-2xl font-bold col-span-12">Precificação</h3>'),
            Div(
                HTML(
                    """
                            <div class="h-full max-w-2xl mx-auto flex flex-col items-center justify-center text-center gap-4 py-12">
                                <p class="text-xl font-semibold text-base-content">A precificação deste orçamento será exibida após o cálculo.</p>
                                <button type="button" id="step5-calculate-values-btn" class="btn btn-primary btn-lg min-w-52">
                                    <span data-step5-calc-label>Calcular Valores</span>
                                </button>
                                <div id="step5-calculation-status" class="hidden items-center gap-1 text-base-content/70 font-semibold" aria-live="polite">
                                    <span>Calculando</span>
                                    <span class="step5-calculating-dot">.</span>
                                    <span class="step5-calculating-dot">.</span>
                                    <span class="step5-calculating-dot">.</span>
                                </div>
                            </div>
                            """
                ),
                id="step5-calc-loader-card",
                css_class=f"col-span-12 bg-base-200 p-6 rounded-2xl border-2 border-base-300 h-full text-base-content {step5_loading_hidden_class}",
            ),
            # Coluna Esquerda
            Div(
                Div(
                    HTML('<h3 class="text-3xl font-bold mb-2 border-b-3 step5-accent-border text-center step5-accent-text">Método Hunter</h3>'),
                    Div(
                        # Grid de Custos vs Vendas
                        Div(
                            HTML(f"""
                                    <div class="grid grid-cols-1 md:grid-cols-2 mt-7 gap-x-8 gap-y-3 text-base text-base-content font-semibold">

                                        <!-- COLUNA ESQUERDA — CUSTOS -->
                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Peças</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{custo_pecas}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Peças</span>
                                            <span id="display-venda-pecas"
                                                    class="col-span-4 p-2 border-l border-base-300 whitespace-nowrap step5-accent-text"
                                                    data-base-val="{venda_pecas.amount}"
                                                    data-cost-val="{custo_pecas.amount}"
                                                    data-frete-val="{custo_frete_pecas.amount}">
                                                {venda_pecas}
                                            </span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Frete de Peças</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{custo_frete_pecas}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Frete de Serviços</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{custo_frete_servicos}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Serviço de Terceiros</span>
                                            <span id="display-venda-terceiros" class="col-span-4 p-2 border-l border-base-300">{venda_servico_terceiros}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Serviço de Terceiros</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{custo_servico_terceiros}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo da Hora do Mecânico</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{custo_hora_mecanico}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Mão de Obra</span>
                                            <span id="display-venda-mo"
                                                  class="col-span-4 p-2 border-l border-base-300 step5-accent-text"
                                                  data-base-val="{venda_mao_obra.amount}"
                                                  data-cost-val="{custo_total_mao_obra.amount}">
                                                {venda_mao_obra}
                                            </span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-semibold">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo Total da Mão de Obra</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{custo_total_mao_obra}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Duração Total</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{duracao_total}</span>
                                        </div>

                                        <!-- RESULTADO (respiro visual) -->
                                        <div class="md:col-span-2 h-2"></div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-bold">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Lucro Operacional</span>
                                            <span class="col-span-4 p-2 border-l border-base-300 step5-accent-text">{lucro_operacional}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border {rentabilidade_class} {rentabilidade_bg}">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Rentabilidade</span>
                                            <span class="col-span-4 p-2 border-l {rentabilidade_class} font-bold">
                                                {rentabilidade:.2f}% ({status_texto})
                                            </span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLO</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{mlo:.2f}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                            <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLR</span>
                                            <span class="col-span-4 p-2 border-l border-base-300">{mlr:.2f}</span>
                                        </div>

                                    </div>
                                    """)
                        ),
                        css_class="h-full",
                    ),
                    Div(
                        HTML(f"""<div class="text-center text-base-content mt-6">
                                        <p class="text-2xl font-bold">Valor do Orçamento</p>
                                        <p class="text-3xl font-black step5-accent-text">{budget.display_total_base_value}</p>
                                    </div>""")
                    ),
                    id="step5-method-card",
                    css_class=f"bg-base-200 p-6 rounded-2xl border-2 border-base-300 h-full flex flex-col text-base-content {step5_method_hidden_class}",
                ),
                css_class="col-span-12 lg:col-span-6 h-full",
            ),
            # Coluna Direita
            Div(
                Div(
                    # Slider
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2">Margem de Lucro</h4>'),
                        HTML("""
                                    <div class="flex justify-between mb-1">
                                        <span class="text-sm font-bold">Peça: <span id="val-peca">0</span>%</span>
                                        <span class="text-sm font-bold">Mão de Obra: <span id="val-mo">0</span>%</span>
                                    </div>
                                """),
                        Field("slider", label=False, help_text=False, wrapper_class="w-full"),
                        HTML('<p class="text-sm text-gray-500 font-semibold italic">Deslize para a esquerda para aumentar Peça, ou para a direita para aumentar Mão de obra</p>'),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    # Desconto
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2">Desconto</h4>'),
                        HTML("""
                                <div class="grid grid-cols-1 gap-3 mb-5 xl:grid-cols-3">
                                """),
                        Div(
                            HTML("""
                                    <div id="discount-value-card-body" class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
                                        <div class="mb-3 flex items-center justify-between gap-3">
                                            <div>
                                                <p class="text-sm font-bold text-base-content">Desconto em valor</p>
                                                <p class="text-xs text-base-content/60">Use quando a negociação foi fechada em valor exato.</p>
                                            </div>
                                            <span class="material-icons text-base-content/40">payments</span>
                                        </div>
                                    """),
                            Field("discount_value", wrapper_class="mb-0"),
                            HTML("</div>"),
                            css_class="h-full",
                        ),
                        Div(
                            HTML("""
                                    <div class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
                                        <div class="mb-3 flex items-center justify-between gap-3">
                                            <div>
                                                <p class="text-sm font-bold text-base-content">Tipo de desconto</p>
                                                <p class="text-xs text-base-content/60">Selecione onde o desconto será aplicado.</p>
                                            </div>
                                            <span class="material-icons text-base-content/40">filter_alt</span>
                                        </div>
                                    """),
                            Field("discount_type", wrapper_class="mb-0"),
                            HTML("</div>"),
                            css_class="h-full",
                        ),
                        Div(
                            HTML("""
                                    <div id="discount-percentage-card-body" class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
                                        <div class="mb-3 flex items-center justify-between gap-3">
                                            <div>
                                                <p class="text-sm font-bold text-base-content">Desconto em percentual</p>
                                                <p class="text-xs text-base-content/60">Ideal para manter a mesma política comercial em diferentes totais.</p>
                                            </div>
                                            <span class="material-icons text-base-content/40">percent</span>
                                        </div>
                                    """),
                            Field("discount_percentage", wrapper_class="mb-0"),
                            HTML("</div>"),
                            css_class="h-full",
                        ),
                        HTML("</div>"),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    # Valor Final
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2 text-center border-b-1 border-gray-300">Valor Final</h4>'),
                        HTML('<h5 class="font-semibold text-lg mb-2 text-center">Valor do Orçamento com desconto aplicado:</h5>'),
                        HTML(f"""<div class="space-y-3">
                                            <div class="flex justify-between text-xl font-semibold">
                                                <span>Subtotal:</span>
                                                <span id="step5-subtotal-display" data-base-total="{budget.display_total_base_value.amount}">{budget.display_total_base_value}</span>
                                            </div>
                                            <div class="flex justify-between text-xl font-semibold">
                                                <span>Desconto:</span>
                                                <span id="step5-discount-display">{discount_display}</span>
                                            </div>
                                            <div class="flex justify-between text-xl font-black">
                                                <span>Valor Final:</span>
                                                <span id="valor-final-display">{budget.display_total_budget_value}</span>
                                            </div>
                                        </div>"""),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    css_class="sticky top-4",
                ),
                id="step5-controls-card",
                css_class=f"col-span-12 lg:col-span-6 {step5_method_hidden_class}",
            ),
            css_class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch",
        ),
    )
