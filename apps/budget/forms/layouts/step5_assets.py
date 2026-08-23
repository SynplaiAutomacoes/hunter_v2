def build_step5_assets_html(*, metodo_precificacao: str, mark_step5_calculation_viewed_url: str, update_budget_discount_url: str) -> str:
    return f"""
                <style>
                    :root[data-theme="light"] {{
                      --step5-accent: #0f766e;
                      --step5-warning-soft: rgba(245, 158, 11, 0.16);
                    }}

                    :root[data-theme="dark"] {{
                      --step5-accent: #5eead4;
                      --step5-warning-soft: rgba(245, 158, 11, 0.22);
                    }}

                    input[type="range"].centered-range {{
                      -webkit-appearance: none;
                      -moz-appearance: none;
                      width: 100%;
                      height: 8px;
                      background: transparent;
                    }}

                    input[type="range"].centered-range::-webkit-slider-runnable-track {{
                      height: 8px;
                      border-radius: 999px;
                      background: linear-gradient(
                        to right,
                        #e5e7eb var(--left),
                        #2563eb var(--left),
                        #2563eb var(--right),
                        #e5e7eb var(--right)
                      );
                    }}

                    input[type="range"].centered-range::-webkit-slider-thumb {{
                      -webkit-appearance: none;
                      width: 24px;
                      height: 24px;
                      background: #007bff;
                      border-radius: 50%;
                      margin-top: -8px;
                      cursor: pointer;
                    }}

                    input[type="range"].centered-range::-moz-range-track {{
                      height: 8px;
                      border-radius: 999px;
                      background: linear-gradient(
                        to right,
                        #e5e7eb var(--left),
                        #2563eb var(--left),
                        #2563eb var(--right),
                        #e5e7eb var(--right)
                      );
                    }}

                    input[type="range"].centered-range::-moz-range-thumb {{
                      width: 24px;
                      height: 24px;
                      background: #007bff;
                      border-radius: 50%;
                      border: none;
                    }}

                    .step5-accent-text {{
                        color: var(--step5-accent);
                    }}

                    .step5-accent-border {{
                        border-color: var(--step5-accent);
                    }}

                    .step5-warning-surface {{
                        background-color: var(--step5-warning-soft);
                    }}

                    .step5-calculating-dot {{
                        animation: step5-loading-blink 1s infinite;
                    }}

                    .step5-calculating-dot:nth-child(2) {{
                        animation-delay: 0.2s;
                    }}

                    .step5-calculating-dot:nth-child(3) {{
                        animation-delay: 0.4s;
                    }}

                    @keyframes step5-loading-blink {{
                        0%, 80%, 100% {{
                            opacity: 0.2;
                        }}
                        40% {{
                            opacity: 1;
                        }}
                    }}
                    /* Cores de Rentabilidade */
                    .rentabilidade-bom {{ color: #22c55e !important; border-color: #22c55e !important; }}
                    .rentabilidade-medio {{ color: #f59e0b !important; border-color: #f59e0b !important; }} 
                    .rentabilidade-ruim {{ color: #ef4444 !important; border-color: #ef4444 !important; }}
                    
                    .bg-rentabilidade-bom {{ background-color: rgba(34, 197, 94, 0.1); }}
                    .bg-rentabilidade-medio {{ background-color: rgba(245, 158, 11, 0.1); }}
                    .bg-rentabilidade-ruim {{ background-color: rgba(239, 68, 68, 0.1); }}
                </style>
                <script>
                        (function() {{
                            console.log("Método de Precificação:", "{metodo_precificacao}");
                            let timeout = null;

                            function parseDotDecimal(value) {{
                                const normalized = String(value ?? '').trim().replace(',', '.');
                                if (!normalized) return 0;
                                const parsed = Number.parseFloat(normalized);
                                return Number.isFinite(parsed) ? parsed : 0;
                            }}

                            function clamp(value, min, max) {{
                                return Math.min(Math.max(value, min), max);
                            }}

                            function roundCurrency(value) {{
                                return Math.round((value + Number.EPSILON) * 100) / 100;
                            }}

                            function formatMoney(value) {{
                                return value.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                            }}

                            function formatFraction(fraction) {{
                                return fraction.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
                            }}

                            function formatPercentageDisplay(fraction) {{
                                return (fraction * 100).toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                            }}

                            function getDiscountElements() {{
                                const displayMoney = document.getElementById('id_discount_value_0_display');
                                const hiddenMoney = document.getElementById('id_discount_value_0');
                                const displayPercentage = document.getElementById('id_discount_percentage_display');
                                const hiddenPercentage = document.getElementById('id_discount_percentage');
                                const subtotalDisplay = document.getElementById('step5-subtotal-display');
                                const discountDisplay = document.getElementById('step5-discount-display');
                                const totalDisplay = document.getElementById('valor-final-display');

                                if (!displayMoney || !hiddenMoney || !displayPercentage || !hiddenPercentage || !subtotalDisplay || !discountDisplay || !totalDisplay) {{
                                    return null;
                                }}

                                return {{
                                    displayMoney,
                                    hiddenMoney,
                                    displayPercentage,
                                    hiddenPercentage,
                                    subtotalDisplay,
                                    discountDisplay,
                                    totalDisplay,
                                }};
                            }}

                            function getBaseTotal(elements) {{
                                return parseDotDecimal(elements.subtotalDisplay.dataset.baseTotal);
                            }}

                            function updateCardDiscounts(discountAmount) {{
                                const type = getDiscountTypeValue();
                                const products = parseDotDecimal(document.getElementById('display-venda-pecas')?.dataset.baseVal);
                                const labor = parseDotDecimal(document.getElementById('display-venda-mo')?.dataset.baseVal);
                                const thirdParty = parseDotDecimal(document.getElementById('display-venda-terceiros')?.dataset.baseVal);
                                const services = labor + thirdParty;
                                const total = products + services;
                                let discountProducts = 0;
                                let discountServices = 0;
                                if (type === 'products') {{
                                    discountProducts = discountAmount;
                                }} else if (type === 'services') {{
                                    discountServices = discountAmount;
                                }} else if (total > 0) {{
                                    discountProducts = roundCurrency(discountAmount * products / total);
                                    discountServices = roundCurrency(discountAmount - discountProducts);
                                }}
                                let discountLabor = 0;
                                let discountThird = 0;
                                if (discountServices > 0) {{
                                    if (services <= 0) {{
                                        discountLabor = discountServices;
                                    }} else {{
                                        discountLabor = roundCurrency(discountServices * labor / services);
                                        discountThird = roundCurrency(discountServices - discountLabor);
                                    }}
                                }}
                                applyDiscountRow('step5-discount-products-row', discountProducts);
                                applyDiscountRow('step5-discount-labor-row', discountLabor);
                                applyDiscountRow('step5-discount-third-party-row', discountThird);
                            }}

                            function applyDiscountRow(rowId, amount) {{
                                const row = document.getElementById(rowId);
                                if (!row) return;
                                const valueEl = row.querySelector('.font-semibold');
                                if (amount > 0.009) {{
                                    row.classList.remove('hidden');
                                    if (valueEl) valueEl.textContent = `- R$ ${{formatMoney(amount)}}`;
                                    return;
                                }}
                                row.classList.add('hidden');
                                if (valueEl) valueEl.textContent = '';
                            }}

                            function updateSummary(elements, discountAmount) {{
                                const baseTotal = getBaseTotal(elements);
                                const resolvedDiscount = clamp(roundCurrency(discountAmount), 0, baseTotal);
                                const totalValue = roundCurrency(baseTotal - resolvedDiscount);

                                elements.discountDisplay.textContent = `R$ ${{formatMoney(resolvedDiscount)}}`;
                                elements.totalDisplay.textContent = `R$ ${{formatMoney(totalValue)}}`;
                                updateCardDiscounts(resolvedDiscount);
                            }}

                            function syncFromPercentage(elements) {{
                                const baseTotal = getBaseTotal(elements);
                                const fraction = clamp(parseDotDecimal(elements.hiddenPercentage.value), 0, 1);
                                const amount = baseTotal > 0 ? clamp(roundCurrency(baseTotal * fraction), 0, baseTotal) : 0;

                                elements.hiddenMoney.value = amount.toFixed(2);
                                elements.displayMoney.value = formatMoney(amount);
                                elements.hiddenPercentage.value = formatFraction(fraction);
                                updateSummary(elements, amount);
                            }}

                            function syncFromValue(elements, updateSourceDisplay = true) {{
                                const baseTotal = getBaseTotal(elements);
                                const amount = clamp(roundCurrency(parseDotDecimal(elements.hiddenMoney.value)), 0, baseTotal);
                                const fraction = baseTotal > 0 ? clamp(amount / baseTotal, 0, 1) : 0;

                                elements.hiddenMoney.value = amount.toFixed(2);
                                if (updateSourceDisplay) {{
                                    elements.displayMoney.value = formatMoney(amount);
                                }}
                                elements.hiddenPercentage.value = formatFraction(fraction);
                                elements.displayPercentage.value = formatPercentageDisplay(fraction);
                                updateSummary(elements, amount);
                            }}

                            function getDiscountTypeValue() {{
                                const checked = document.querySelector('input[name="discount_type"]:checked');
                                return checked ? checked.value : 'both';
                            }}

                            function persistDiscount(elements) {{
                                clearTimeout(timeout);
                                timeout = setTimeout(() => {{
                                    htmx.ajax('POST', '{update_budget_discount_url}', {{
                                        values: {{
                                            "discount_value_0": elements.hiddenMoney.value,
                                            "discount_percentage": elements.hiddenPercentage.value,
                                            "discount_type": getDiscountTypeValue(),
                                        }},
                                        swap: 'none',
                                    }});
                                }}, 800);
                            }}

                            function bindDiscountSync() {{
                                const elements = getDiscountElements();
                                if (!elements) return;

                                if (elements.displayMoney.dataset.discountSyncBound !== 'true') {{
                                    const handleMoneyInput = () => {{
                                        window.setTimeout(() => {{
                                            syncFromValue(elements, false);
                                            persistDiscount(elements);
                                        }}, 0);
                                    }};
                                    elements.displayMoney.addEventListener('input', handleMoneyInput);
                                    elements.displayMoney.addEventListener('blur', handleMoneyInput);
                                    elements.displayMoney.dataset.discountSyncBound = 'true';
                                }}

                                if (elements.hiddenPercentage.dataset.discountSyncBound !== 'true') {{
                                    const handlePercentageInput = () => {{
                                        window.setTimeout(() => {{
                                            syncFromPercentage(elements);
                                            persistDiscount(elements);
                                        }}, 0);
                                    }};
                                    elements.hiddenPercentage.addEventListener('widget:formatted-change', handlePercentageInput);
                                    elements.hiddenPercentage.dataset.discountSyncBound = 'true';
                                }}

                                if (parseDotDecimal(elements.hiddenMoney.value) > 0) {{
                                    syncFromValue(elements);
                                    return;
                                }}

                                if (parseDotDecimal(elements.hiddenPercentage.value) > 0) {{
                                    syncFromPercentage(elements);
                                    return;
                                }}

                                syncFromValue(elements);
                            }}

                            if (document.documentElement.dataset.step5DiscountListeners !== 'true') {{
                                document.documentElement.dataset.step5DiscountListeners = 'true';
                                document.addEventListener('change', function(e) {{
                                    if (e.target && e.target.name === 'discount_type') {{
                                        const elements = getDiscountElements();
                                        if (elements) {{
                                            updateSummary(elements, parseDotDecimal(elements.hiddenMoney.value));
                                            persistDiscount(elements);
                                        }}
                                    }}
                                }});
                                document.addEventListener('DOMContentLoaded', bindDiscountSync);
                                document.body.addEventListener('htmx:afterSettle', bindDiscountSync);
                            }}
                            bindDiscountSync();
                        }})();

                        (function () {{
                            window.initBudgetStep5CalculationGate = function initCalculationGate() {{
                                const calculateButton = document.getElementById('step5-calculate-values-btn');
                                const calculationStatus = document.getElementById('step5-calculation-status');
                                const loadingCard = document.getElementById('step5-calc-loader-card');
                                const methodCard = document.getElementById('step5-method-card');
                                const controlsCard = document.getElementById('step5-controls-card');
                                const calculatedInput = document.getElementById('id_step5_calculated');

                                if (!calculateButton || !loadingCard || !methodCard || !controlsCard) {{
                                    if (typeof window.syncBudgetStep5SubmitButton === 'function') {{
                                        window.syncBudgetStep5SubmitButton();
                                    }}
                                    return;
                                }}

                                if (typeof window.syncBudgetStep5SubmitButton === 'function') {{
                                    window.syncBudgetStep5SubmitButton();
                                }}

                                if (calculateButton.dataset.initialized === 'true') {{
                                    return;
                                }}

                                calculateButton.dataset.initialized = 'true';

                                calculateButton.addEventListener('click', async () => {{
                                    if (calculateButton.disabled) return;

                                    if (calculatedInput) {{
                                        calculatedInput.value = '1';
                                    }}

                                    calculateButton.disabled = true;
                                    calculateButton.classList.add('btn-disabled');

                                    const label = calculateButton.querySelector('[data-step5-calc-label]');
                                    if (label) {{
                                        label.textContent = 'Calculando...';
                                    }}

                                    if (calculationStatus) {{
                                        calculationStatus.classList.remove('hidden');
                                        calculationStatus.classList.add('flex');
                                    }}

                                    try {{
                                        await fetch('{mark_step5_calculation_viewed_url}', {{
                                            method: 'POST',
                                            headers: {{
                                                'X-CSRFToken': '{{{{ csrf_token }}}}',
                                                'X-Requested-With': 'XMLHttpRequest',
                                            }},
                                        }});
                                    }} catch (error) {{
                                        console.error('Erro ao marcar calculo do step 5:', error);
                                    }}

                                    window.setTimeout(() => {{
                                        loadingCard.classList.add('hidden');
                                        methodCard.classList.remove('hidden');
                                        controlsCard.classList.remove('hidden');

                                        if (typeof window.syncBudgetStep5SubmitButton === 'function') {{
                                            window.syncBudgetStep5SubmitButton();
                                        }}

                                        if (typeof window.step5InitSlider === 'function') {{
                                            window.step5InitSlider();
                                        }}
                                    }}, 5000);
                                }});
                            }};

                            if (!window.__budgetStep5CalcGateBound) {{
                                window.__budgetStep5CalcGateBound = true;
                                document.addEventListener('DOMContentLoaded', window.initBudgetStep5CalculationGate);
                                document.body.addEventListener('htmx:afterSettle', window.initBudgetStep5CalculationGate);
                            }}

                            window.initBudgetStep5CalculationGate();
                        }})();

                        (function () {{
                            window.step5InitSlider = function initSlider() {{
                                const slider = document.querySelector('input[name="slider"]');
                                const labelPecaPct = document.getElementById('val-peca');
                                const labelMOPct = document.getElementById('val-mo');
                                const vendaPecaEl = document.getElementById('display-venda-pecas');
                                const vendaMOEl = document.getElementById('display-venda-mo');
                        
                                if (!slider || !vendaPecaEl || !vendaMOEl) return;
                        
                                const originPeca = parseFloat(vendaPecaEl.dataset.baseVal) || 0;
                                const originMO = parseFloat(vendaMOEl.dataset.baseVal) || 0;
                                const costPeca = parseFloat(vendaPecaEl.dataset.costVal) || 0;
                                const freightPeca = parseFloat(vendaPecaEl.dataset.freteVal || 0);
                                const floorPeca = Math.min(originPeca, Math.max(costPeca + freightPeca, 0));
                                const costMO = parseFloat(vendaMOEl.dataset.costVal) || 0;
                                const floorMO = Math.min(originMO, Math.max(costMO, 0));
                        
                                const format = (v) =>
                                    "R$ " + v.toLocaleString("pt-BR", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                                );
                        
                                function updateFill(val) {{
                                    const min = -100;
                                    const max = 100;
                                    const center = 50;
                                    const percent = ((val - min) / (max - min)) * 100;
                        
                                    if (val === 0) {{
                                        slider.style.setProperty('--left', `${{center}}%`);
                                        slider.style.setProperty('--right', `${{center}}%`);
                                    }} else if (val < 0) {{
                                        slider.style.setProperty('--left', `${{percent}}%`);
                                        slider.style.setProperty('--right', `${{center}}%`);
                                    }} else {{
                                        slider.style.setProperty('--left', `${{center}}%`);
                                        slider.style.setProperty('--right', `${{percent}}%`);
                                    }}
                                }}
                        
                                function update(val) {{
                                    const sliderValue = Number(val) || 0;
                                    labelPecaPct.textContent = sliderValue < 0 ? Math.abs(sliderValue) : 0;
                                    labelMOPct.textContent = sliderValue > 0 ? sliderValue : 0;

                                    const ratio = Math.abs(sliderValue) / 100;
                                    let peca = originPeca;
                                    let mo = originMO;
                                    if (sliderValue < 0) {{
                                        mo = floorMO + (originMO - floorMO) * (1 - ratio);
                                        peca = originPeca + (originMO - mo);
                                    }} else if (sliderValue > 0) {{
                                        peca = floorPeca + (originPeca - floorPeca) * (1 - ratio);
                                        mo = originMO + (originPeca - peca);
                                    }}
                                    vendaPecaEl.textContent = format(peca);
                                    vendaMOEl.textContent = format(mo);

                                    updateFill(sliderValue);
                                }}
                        
                                slider.addEventListener('input', e => update(e.target.value));
                                update(slider.value || 0);
                            }};
                        
                            document.addEventListener('DOMContentLoaded', window.step5InitSlider);
                            document.body.addEventListener('htmx:afterSettle', window.step5InitSlider);
                        }})();
                    </script>"""
