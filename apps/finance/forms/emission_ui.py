from __future__ import annotations

from decimal import Decimal
from typing import Any


def format_money(value: Any) -> str:
    amount: Decimal
    if hasattr(value, "amount"):
        amount = value.amount
    else:
        amount = Decimal(str(value or 0))
    return f"R$ {amount:.2f}".replace(".", ",")


def clamp_slider_value(value: object, default: int = 0) -> int:
    try:
        slider_source = default if value in (None, "") else str(value)
        return max(-100, min(100, int(slider_source)))
    except (TypeError, ValueError):
        return max(-100, min(100, int(default)))


def resolve_initial_slider(*, initial_value: object, persisted_slider: int | None = None, default_slider: int = 0) -> int:
    base_value = persisted_slider if persisted_slider is not None else default_slider
    return clamp_slider_value(initial_value, default=base_value)


def build_slider_widget_attrs(
    *,
    preview_url: str,
    target_selector: str,
    include_selector: str,
    swap: str,
    trigger: str = "input changed delay:250ms",
) -> dict[str, str]:
    attrs = {
        "type": "range",
        "min": "-100",
        "max": "100",
        "step": "1",
        "class": "w-full centered-range finance-emission-range",
    }
    if preview_url:
        attrs.update(
            {
                "hx-get": preview_url,
                "hx-trigger": trigger,
                "hx-target": target_selector,
                "hx-swap": swap,
                "hx-include": include_selector,
            }
        )
    return attrs


def build_slider_panel_html(*, prefix: str, selected_slider: int, description: str) -> str:
    return f"""
        <style>
            input[type="range"].finance-emission-range {{
                -webkit-appearance: none;
                -moz-appearance: none;
                width: 100%;
                height: 8px;
                background: transparent;
            }}

            input[type="range"].finance-emission-range::-webkit-slider-runnable-track {{
                height: 8px;
                border-radius: 999px;
                background: linear-gradient(
                    to right,
                    #dbeafe var(--left),
                    #0f766e var(--left),
                    #0f766e var(--right),
                    #fde68a var(--right)
                );
            }}

            input[type="range"].finance-emission-range::-webkit-slider-thumb {{
                -webkit-appearance: none;
                width: 24px;
                height: 24px;
                background: #0f172a;
                border: 3px solid #f8fafc;
                border-radius: 999px;
                margin-top: -8px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.22);
                cursor: pointer;
            }}

            input[type="range"].finance-emission-range::-moz-range-track {{
                height: 8px;
                border-radius: 999px;
                background: linear-gradient(
                    to right,
                    #dbeafe var(--left),
                    #0f766e var(--left),
                    #0f766e var(--right),
                    #fde68a var(--right)
                );
            }}

            input[type="range"].finance-emission-range::-moz-range-thumb {{
                width: 24px;
                height: 24px;
                background: #0f172a;
                border: 3px solid #f8fafc;
                border-radius: 999px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.22);
                cursor: pointer;
            }}
        </style>
        <div class="rounded-2xl border border-base-300 bg-base-100/90 p-5 shadow-sm">
            <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between mb-4">
                <div>
                    <p class="text-xs uppercase tracking-[0.24em] text-base-content/50">Ajuste fiscal</p>
                    <h3 class="text-lg font-semibold">Slider da emissao</h3>
                    <p class="text-sm text-base-content/70">{description}</p>
                </div>
                <div class="badge badge-outline badge-lg px-4 py-3" id="{prefix}-slider-value">{selected_slider}</div>
            </div>
            <div class="grid gap-3 sm:grid-cols-2 mb-4">
                <div class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-900">
                    <p class="text-xs uppercase tracking-wide text-emerald-700/80">Peso em produtos</p>
                    <p class="text-2xl font-black"><span id="{prefix}-val-produtos">{abs(selected_slider) if selected_slider < 0 else 0}</span>%</p>
                </div>
                <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900">
                    <p class="text-xs uppercase tracking-wide text-amber-700/80">Peso em servicos</p>
                    <p class="text-2xl font-black"><span id="{prefix}-val-servicos">{selected_slider if selected_slider > 0 else 0}</span>%</p>
                </div>
            </div>
        </div>
    """


def build_slider_script_html(*, prefix: str, form_selector: str) -> str:
    init_name = f"init_{prefix.replace('-', '_')}_slider"
    return f"""
        <script>
            (function () {{
                window.{init_name} = function {init_name}() {{
                    const slider = document.querySelector('{form_selector} input[name="pricing_slider"]');
                    const badge = document.getElementById('{prefix}-slider-value');
                    const productsLabel = document.getElementById('{prefix}-val-produtos');
                    const servicesLabel = document.getElementById('{prefix}-val-servicos');

                    if (!slider) return;

                    function update(rawValue) {{
                        const value = parseInt(rawValue || 0, 10) || 0;
                        const min = -100;
                        const max = 100;
                        const center = 50;
                        const percent = ((value - min) / (max - min)) * 100;

                        if (value === 0) {{
                            slider.style.setProperty('--left', center + '%');
                            slider.style.setProperty('--right', center + '%');
                        }} else if (value < 0) {{
                            slider.style.setProperty('--left', percent + '%');
                            slider.style.setProperty('--right', center + '%');
                        }} else {{
                            slider.style.setProperty('--left', center + '%');
                            slider.style.setProperty('--right', percent + '%');
                        }}

                        if (badge) badge.textContent = value;
                        if (productsLabel) productsLabel.textContent = value < 0 ? Math.abs(value) : 0;
                        if (servicesLabel) servicesLabel.textContent = value > 0 ? value : 0;
                    }}

                    slider.oninput = function () {{ update(slider.value); }};
                    update(slider.value || 0);
                }};

                document.addEventListener('DOMContentLoaded', window.{init_name});
                document.body.addEventListener('htmx:afterSettle', window.{init_name});
            }})();
        </script>
    """
