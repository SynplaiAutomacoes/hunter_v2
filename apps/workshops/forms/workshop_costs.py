from __future__ import annotations

import calendar
import datetime
import json

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from django import forms
from django.urls import reverse
from djmoney.money import Money
import holidays

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from djmoney.forms import MoneyField

from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import (
    DecimalInput,
    DurationInput,
    NumberInput,
    MoneyInput,
    PercentageInput,
    SearchableSelectInput,
    TextInput,
)
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostWorkDay, WorkshopCostItem
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import ADMIN_SALARY_MONTHLY_COST_NAME, MECHANIC_SALARY_MONTHLY_COST_NAME

BRAZILIAN_STATE_CHOICES: list[tuple[str, str]] = [
    ("AC", "Acre (AC)"),
    ("AL", "Alagoas (AL)"),
    ("AP", "Amapá (AP)"),
    ("AM", "Amazonas (AM)"),
    ("BA", "Bahia (BA)"),
    ("CE", "Ceará (CE)"),
    ("DF", "Distrito Federal (DF)"),
    ("ES", "Espírito Santo (ES)"),
    ("GO", "Goiás (GO)"),
    ("MA", "Maranhão (MA)"),
    ("MT", "Mato Grosso (MT)"),
    ("MS", "Mato Grosso do Sul (MS)"),
    ("MG", "Minas Gerais (MG)"),
    ("PA", "Pará (PA)"),
    ("PB", "Paraíba (PB)"),
    ("PR", "Paraná (PR)"),
    ("PE", "Pernambuco (PE)"),
    ("PI", "Piauí (PI)"),
    ("RJ", "Rio de Janeiro (RJ)"),
    ("RN", "Rio Grande do Norte (RN)"),
    ("RS", "Rio Grande do Sul (RS)"),
    ("RO", "Rondônia (RO)"),
    ("RR", "Roraima (RR)"),
    ("SC", "Santa Catarina (SC)"),
    ("SP", "São Paulo (SP)"),
    ("SE", "Sergipe (SE)"),
    ("TO", "Tocantins (TO)"),
]


class WorkshopCostForm(CoreModelForm):
    EDIT_WARNING_MESSAGES = {
        MECHANIC_SALARY_MONTHLY_COST_NAME: "Esta é a soma total dos salários dos colaboradores produtivos, deseja manter?",
        ADMIN_SALARY_MONTHLY_COST_NAME: "Esta é a soma total dos salários dos colaboradores administrativos, deseja manter?",
    }
    work_day_dates = forms.CharField(required=False, widget=forms.HiddenInput())
    state = forms.ChoiceField(
        required=False,
        choices=BRAZILIAN_STATE_CHOICES,
        initial="SP",
        label="Estado",
        widget=SearchableSelectInput(choices=BRAZILIAN_STATE_CHOICES),
    )

    class Meta:
        model = WorkshopCost
        fields = [
            "month",
            "year",
            "mechanic_quantity",
            "work_hours_per_day",
            "work_days_per_month",
            "productivity_average",
            "card_rate",
            "tax_rate",
            "profit_margin",
            "commission_rate",
            "risk_coefficient",
            "parts_purchase_cap",
            "freight_cost",
            "third_party_service_cap",
            "total_value",
            "total_monthly_costs",
            "profit_target",
            "gross_revenue_target",
            "profitability_multiplier",
        ]
        widgets = {
            "month": SearchableSelectInput(),
            "year": TextInput(),
            "mechanic_quantity": NumberInput(),
            "work_hours_per_day": DurationInput(),
            "work_days_per_month": NumberInput(attrs={"type": "hidden"}),
            "productivity_average": PercentageInput(min_percent=50, max_percent=80, decimal_places=2),
            "card_rate": PercentageInput(decimal_places=2),
            "tax_rate": PercentageInput(decimal_places=2),
            "profit_margin": PercentageInput(decimal_places=2),
            "commission_rate": PercentageInput(max_percent=10, decimal_places=2),
            "risk_coefficient": DecimalInput(min_value=1.0, max_value=1.5, decimal_places=2),
            "parts_purchase_cap": MoneyInput(),
            "freight_cost": MoneyInput(),
            "third_party_service_cap": MoneyInput(),
            "total_value": MoneyInput(attrs={"readonly": True}),
            "total_monthly_costs": MoneyInput(attrs={"readonly": True}),
            "profit_target": MoneyInput(),
            "gross_revenue_target": MoneyInput(attrs={"readonly": True}),
            "profitability_multiplier": DecimalInput(decimal_places=2, attrs={"readonly": True}),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if not self.instance.pk and not self.data:
            today = datetime.date.today()
            self.fields["month"].initial = today.month
            self.fields["year"].initial = today.year

        self.active_costs = MonthlyCost.objects.filter(workshop=workshop, is_active=True)

        saved_values: dict[int, object] = {}
        if self.instance.pk:
            saved_values = {item.monthly_cost_id: item.amount for item in self.instance.items.all()}

        self.initial.setdefault("work_day_dates", self._serialize_work_day_dates())
        self.initial.setdefault("state", "SP")

        self.cost_fields_names = []
        for cost in self.active_costs:
            cost_id = cost.pk
            if cost_id is None:
                continue

            field_name = f"cost_item_{cost_id}"
            self.cost_fields_names.append(field_name)

            self.fields[field_name] = MoneyField(label=cost.name, required=False, widget=MoneyInput())

            if cost_id in saved_values:
                self.initial[field_name] = saved_values[cost_id]

            self._set_cost_field_restore_metadata(field_name=field_name, cost_name=cost.name, original_value=saved_values.get(cost_id))

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self) -> Layout:
        cancel_url = reverse("workshops:workshop_cost_list")
        calculate_url = reverse("workshops:workshop_cost_calculate")
        copy_modal_url = reverse("workshops:workshop_cost_copy_selection")

        cost_fields_layout = [Field(name, wrapper_class="col-span-12 lg:col-span-3") for name in self.cost_fields_names]

        copy_btn_html = ""
        if not self.instance.pk:
            copy_btn_html = f"""
                <button type="button"
                        class="btn btn-primary btn-base ml-auto d-flex align-items-center gap-2 px-3 shadow-sm"
                        hx-get="{copy_modal_url}"
                        hx-target="#modal-container"
                        hx-swap="innerHTML">
                    
                    <span class="material-icons" style="font-size:18px;">
                        content_copy
                    </span>
                
                    <span>Copiar Custos Mensais</span>
                </button>
            """

        return Layout(
            Div(
                Div(
                    HTML(f"""
                        <div class="col-span-12 flex items-center justify-between mb-2">
                            <h3 class="text-xl font-bold">Mês de Referência</h3>
                            {copy_btn_html}
                        </div>
                    """),
                    Field("month", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("year", wrapper_class="col-span-12 lg:col-span-6"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Mecânicos Produtivos</h3>'),
                    Field("mechanic_quantity", wrapper_class="col-span-6 lg:col-span-2"),
                    Field("work_hours_per_day", wrapper_class="col-span-6 lg:col-span-2"),
                    Field("work_days_per_month", type="hidden"),
                    Field("work_day_dates", type="hidden"),
                    Field("state", wrapper_class="col-span-12 lg:col-span-3"),
                    HTML(self._build_work_days_calendar_html()),
                    Field("productivity_average", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("profit_margin", wrapper_class="col-span-12 lg:col-span-6"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Despesas Mensais</h3>'),
                    Div(
                        *cost_fields_layout,
                        css_class="contents",
                    ),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Taxas e Impostos</h3>'),
                    Field("card_rate", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("tax_rate", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("commission_rate", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("risk_coefficient", wrapper_class="col-span-12 lg:col-span-12"),
                    Field("total_monthly_costs", wrapper_class="col-span-12 lg:col-span-12"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Teto de Compras</h3>'),
                    Field("parts_purchase_cap", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("freight_cost", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("third_party_service_cap", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("total_value", wrapper_class="col-span-12 lg:col-span-3"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start col-span-12",
                ),
                Div(
                    HTML('<div class="col-span-12 mb-4"><span class="badge badge-neutral">Metas e Indicadores</span></div>'),
                    Field("profit_target", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("gross_revenue_target", wrapper_class="col-span-12 lg:col-span-4"),
                    Div(
                        Field("profitability_multiplier"),
                        HTML('<p id="multiplier-warn" class="text-error text-xs mt-1 hidden">O Multiplicador de Lucratividade não pode ser menor que 3,0. Diminua o Teto de Compra de Peças ou Aumente a Meta de Lucro Mensal</p>'),
                        css_id="multiplier-feedback",
                        css_class="col-span-12 lg:col-span-4",
                    ),
                    css_id="calculation-results",
                    css_class="col-span-12 bg-success/10 border border-success/20 rounded-box p-6 grid grid-cols-1 lg:grid-cols-12 gap-4 items-start mt-4",
                ),
                hx_post=calculate_url,
                hx_trigger="input delay:100ms, change delay:100ms",
                hx_target="#calculation-results",
                hx_swap="innerHTML",
                hx_include="closest form",
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def _set_cost_field_restore_metadata(self, *, field_name: str, cost_name: str, original_value: object | None) -> None:
        if not self.instance.pk:
            return

        warning_message = self.EDIT_WARNING_MESSAGES.get(cost_name)
        if warning_message is None:
            return

        field = self.fields.get(field_name)
        if field is None:
            return

        field.widget.attrs["restore_original_value"] = self._serialize_money_value(original_value)
        field.widget.attrs["restore_warning_message"] = warning_message

    @staticmethod
    def _serialize_money_value(value: object | None) -> str:
        if value is None:
            return ""

        amount = getattr(value, "amount", value)
        return str(amount)

    def clean(self):
        cleaned_data = cast(dict[str, object], super().clean() or {})
        month = cleaned_data.get("month")
        year = cleaned_data.get("year")
        work_day_dates = self._parse_work_day_dates(cleaned_data.get("work_day_dates"), month=month, year=year)
        cleaned_data["work_day_dates"] = work_day_dates
        if month and year:
            cleaned_data["work_days_per_month"] = len(work_day_dates)
        self.instance.work_day_dates_override = work_day_dates

        if month and year and self.workshop:
            qs = WorkshopCost.objects.filter(workshop=self.workshop, month=month, year=year)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um custo mensal para este Mês/Ano.")

        self._validate_profitability_multiplier(cleaned_data)

        return cleaned_data

    def _validate_profitability_multiplier(self, cleaned_data: dict[str, object]) -> None:
        @dataclass
        class MockItem:
            amount: Money

        instance = self.instance
        for field_name in (
            "parts_purchase_cap",
            "freight_cost",
            "third_party_service_cap",
            "card_rate",
            "tax_rate",
            "commission_rate",
            "risk_coefficient",
        ):
            setattr(instance, field_name, cleaned_data.get(field_name))

        cost_items: list[MockItem] = []
        for cost in self.active_costs:
            cost_id = cost.pk
            if cost_id is None:
                continue
            amount = cleaned_data.get(f"cost_item_{cost_id}")
            if amount is None:
                amount = Money(0, "BRL")
            cost_items.append(MockItem(amount=amount))

        total_value = instance.calculate_total_value()
        total_monthly_costs = instance.calculate_total_monthly_costs(items=cost_items)
        profit_target = cleaned_data.get("profit_target")
        if profit_target is None:
            profit_target = Money(0, "BRL")
        gross_revenue_target = instance.calculate_gross_revenue_target(total_monthly_costs, profit_target, total_value)
        multiplier = instance.calculate_profitability_multiplier(gross_revenue_target, total_value)

        if multiplier < Decimal("3.0"):
            self.add_error(
                "profitability_multiplier",
                "O Multiplicador de Lucratividade não pode ser menor que 3,0. Diminua o Teto de Compra de Peças ou Aumente a Meta de Lucro Mensal",
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.workshop = self.workshop
        work_day_dates = cast(list[datetime.date], self.cleaned_data.get("work_day_dates", []))
        instance.work_day_dates_override = work_day_dates

        if commit:
            instance.save()

            for cost in self.active_costs:
                cost_id = cost.pk
                if cost_id is None:
                    continue

                field_name = f"cost_item_{cost_id}"
                amount = self.cleaned_data.get(field_name)

                if amount is not None:
                    WorkshopCostItem.objects.update_or_create(workshop_cost=instance, monthly_cost=cost, defaults={"amount": amount})

            self._sync_work_days(instance=instance, work_day_dates=work_day_dates)

            instance.calculate_all()
            instance.save()
        return instance

    def _serialize_work_day_dates(self) -> str:
        if not self.instance.pk:
            if self.is_bound:
                return str(self.data.get("work_day_dates") or "")
            month = self._resolve_selected_month(default=datetime.date.today().month)
            year = self._resolve_selected_year(default=datetime.date.today().year)
            state = self._resolve_selected_state(default="SP")
            work_days = self._get_work_day_dates_for_month(month=month, year=year, state=state)
            return ",".join(d.isoformat() for d in work_days)

        work_day_dates = self.instance.work_days.order_by("date").values_list("date", flat=True)
        return ",".join(d.isoformat() for d in work_day_dates)

    def _build_work_days_calendar_html(self) -> str:
        today = datetime.date.today()
        selected_month = self._resolve_selected_month(default=today.month)
        selected_year = self._resolve_selected_year(default=today.year)
        selected_state = self._resolve_selected_state(default="SP")
        default_holiday_dates = [d.isoformat() for d in self._get_holiday_dates(state=selected_state, month=selected_month, year=selected_year)]
        default_work_day_dates = [d.isoformat() for d in self._get_work_day_dates_for_month(month=selected_month, year=selected_year, state=selected_state)]
        weekday_labels = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"]

        return f"""
            <style>
                [data-theme="dark"] #work-day-calendar .cal-header {{
                    color: rgba(230, 230, 230, 0.85);
                }}
                [data-theme="dark"] #work-day-calendar .cal-day-selected {{
                    color: rgb(167, 243, 208);
                    background-color: rgba(52, 211, 153, 0.25);
                    border-color: rgba(52, 211, 153, 0.45);
                }}
                [data-theme="dark"] #work-day-calendar .cal-day-selected:hover {{
                    background-color: rgba(52, 211, 153, 0.40);
                }}
                [data-theme="dark"] #work-day-calendar .cal-day-unselected {{
                    color: rgb(253, 230, 138);
                    background-color: rgba(251, 191, 36, 0.22);
                    border-color: rgba(251, 191, 36, 0.40);
                }}
                [data-theme="dark"] #work-day-calendar .cal-day-unselected:hover {{
                    background-color: rgba(251, 191, 36, 0.35);
                }}
                [data-theme="dark"] #work-day-calendar .cal-day-weekend {{
                    color: rgba(200, 200, 200, 0.55);
                    background-color: rgba(60, 60, 65, 0.85);
                    border-color: rgba(90, 90, 95, 0.70);
                }}
                [data-theme="dark"] #work-day-calendar .cal-day-weekend:hover {{
                    color: rgb(167, 243, 208);
                    background-color: rgba(52, 211, 153, 0.18);
                    border-color: rgba(52, 211, 153, 0.35);
                }}
                [data-theme="dark"] #work-day-count-display {{
                    color: rgb(167, 243, 208);
                }}
            </style>
            <div class="col-span-12 lg:col-span-5 rounded-box border border-base-300 bg-base-200/40 p-3">
                <div class="flex flex-col gap-2">
                    <div class="flex items-start justify-between gap-2">
                        <div>
                            <h3 class="text-sm font-semibold text-base-content">Calendário de Dias Trabalhados</h3>
                            <p class="text-[10px] text-base-content/70">Clique em um dia útil para marcar ou desmarcar.</p>
                            <div class="mt-1.5 inline-flex items-center gap-1 rounded-full bg-success/20 px-2.5 py-1">
                                <span class="material-icons text-success text-[14px]">event_available</span>
                                <span id="work-day-count-display" class="text-[11px] font-semibold text-success-content">{len(default_work_day_dates)} dias trabalhados</span>
                            </div>
                        </div>
                        <button type="button" id="work-day-calendar-toggle" class="btn btn-xs btn-ghost text-base-content/80">Mostrar</button>
                    </div>
                    <div id="work-day-calendar-panel" class="hidden">
                        <div id="work-day-calendar"
                             class="grid grid-cols-7 gap-1 max-w-[260px]"
                             data-selected-month="{selected_month}"
                             data-selected-year="{selected_year}"
                             data-selected-state="{selected_state}"
                             data-default-holidays='{json.dumps(default_holiday_dates)}'
                             data-default-work-days='{json.dumps(default_work_day_dates)}'
                             data-weekday-labels='{json.dumps(weekday_labels)}'></div>
                    </div>
                </div>
            </div>
            <script>
                (function() {{
                    const hiddenInput = document.getElementById('id_work_day_dates');
                    const monthInput = document.getElementById('id_month');
                    const yearInput = document.getElementById('id_year');
                    const stateInput = document.getElementById('id_state');
                    const calendarRoot = document.getElementById('work-day-calendar');
                    const panel = document.getElementById('work-day-calendar-panel');
                    const toggleButton = document.getElementById('work-day-calendar-toggle');

                    if (!hiddenInput || !monthInput || !yearInput || !calendarRoot || !panel || !toggleButton) {{
                        return;
                    }}

                    const weekdayLabels = JSON.parse(calendarRoot.dataset.weekdayLabels || '[]');
                    const defaultHolidays = new Set(JSON.parse(calendarRoot.dataset.defaultHolidays || '[]'));
                    const defaultWorkDays = new Set(JSON.parse(calendarRoot.dataset.defaultWorkDays || '[]'));

                    function updateWorkDaysPerMonth(selectedDates) {{
                        const workDaysInput = document.getElementById('id_work_days_per_month');
                        const countDisplay = document.getElementById('work-day-count-display');
                        const calculated = selectedDates.size;
                        if (countDisplay) {{
                            countDisplay.textContent = calculated + ' dia' + (calculated !== 1 ? 's' : '') + ' trabalhado' + (calculated !== 1 ? 's' : '');
                        }}
                        if (!workDaysInput) {{
                            return;
                        }}
                        if (String(workDaysInput.value || '') !== String(calculated)) {{
                            workDaysInput.value = String(calculated);
                            workDaysInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            workDaysInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}

                    function parseSelectedDates() {{
                        return new Set((hiddenInput.value || '').split(',').map(value => value.trim()).filter(Boolean));
                    }}

                    function filterDatesForMonth(selectedDates, year, month) {{
                        return new Set(Array.from(selectedDates).filter(value => {{
                            const date = new Date(`${{value}}T00:00:00`);
                            return date.getFullYear() === year && (date.getMonth() + 1) === month;
                        }}));
                    }}

                    function formatDate(year, month, day) {{
                        return `${{year}}-${{String(month).padStart(2, '0')}}-${{String(day).padStart(2, '0')}}`;
                    }}

                    function renderCalendar() {{
                        const year = parseInt(yearInput.value || calendarRoot.dataset.selectedYear || '0', 10);
                        const month = parseInt(monthInput.value || calendarRoot.dataset.selectedMonth || '0', 10);
                        if (!year || !month) {{
                            return;
                        }}

                        calendarRoot.dataset.selectedYear = String(year);
                        calendarRoot.dataset.selectedMonth = String(month);
                        let selectedDates = filterDatesForMonth(parseSelectedDates(), year, month);
                        if (selectedDates.size === 0 && defaultWorkDays.size > 0) {{
                            selectedDates = filterDatesForMonth(defaultWorkDays, year, month);
                        }}
                        hiddenInput.value = Array.from(selectedDates).sort().join(',');
                        updateWorkDaysPerMonth(selectedDates);
                        const daysInMonth = new Date(year, month, 0).getDate();
                        const firstWeekday = new Date(year, month - 1, 1).getDay();
                        const weekdayOffset = firstWeekday;
                        calendarRoot.innerHTML = '';

                        weekdayLabels.forEach(label => {{
                            const header = document.createElement('div');
                            header.className = 'text-center text-[10px] font-semibold uppercase tracking-wide text-base-content/60 h-5';
                            header.textContent = label;
                            calendarRoot.appendChild(header);
                        }});

                        for (let index = 0; index < weekdayOffset; index += 1) {{
                            const spacer = document.createElement('div');
                            spacer.className = 'h-7 w-7 rounded-sm bg-transparent';
                            calendarRoot.appendChild(spacer);
                        }}

                        for (let day = 1; day <= daysInMonth; day += 1) {{
                            const dateValue = formatDate(year, month, day);
                            const date = new Date(`${{dateValue}}T00:00:00`);
                            const isWeekend = date.getDay() === 0 || date.getDay() === 6;
                            const isSelected = selectedDates.has(dateValue);
                            const button = document.createElement('button');
                            button.type = 'button';
                            button.textContent = String(day);
                            button.dataset.date = dateValue;

                            let buttonClass = 'h-7 w-7 rounded-sm border text-[11px] font-semibold transition cursor-pointer ';
                            if (isSelected) {{
                                buttonClass += 'cal-day-selected border-success bg-success/25 text-success-content hover:bg-success/35';
                            }} else if (isWeekend) {{
                                buttonClass += 'cal-day-weekend border-base-300 bg-base-200 text-base-content/50 hover:border-success hover:bg-success/10';
                            }} else {{
                                buttonClass += 'cal-day-unselected border-warning bg-warning/25 text-warning-content hover:bg-warning/35';
                            }}
                            button.className = buttonClass;

                            button.addEventListener('click', () => {{
                                const nextSelectedDates = parseSelectedDates();
                                if (nextSelectedDates.has(dateValue)) {{
                                    nextSelectedDates.delete(dateValue);
                                }} else {{
                                    nextSelectedDates.add(dateValue);
                                }}

                                hiddenInput.value = Array.from(nextSelectedDates).sort().join(',');
                                hiddenInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                renderCalendar();
                            }});

                            calendarRoot.appendChild(button);
                        }}
                    }}

                    toggleButton.addEventListener('click', () => {{
                        const isHidden = panel.classList.contains('hidden');
                        panel.classList.toggle('hidden');
                        toggleButton.textContent = isHidden ? 'Ocultar' : 'Mostrar';
                        if (isHidden) {{
                            renderCalendar();
                        }}
                    }});

                    monthInput.addEventListener('change', renderCalendar);
                    yearInput.addEventListener('input', renderCalendar);
                    yearInput.addEventListener('change', renderCalendar);

                    if (stateInput) {{
                        stateInput.addEventListener('change', () => {{
                            const state = stateInput.value;
                            const year = parseInt(yearInput.value || '0', 10);
                            const month = parseInt(monthInput.value || '0', 10);
                            if (!state || !year || !month) {{
                                return;
                            }}
                            fetch(`/workshops/workshops_costs/holidays/?state=${{state}}&month=${{month}}&year=${{year}}`)
                                .then(response => response.json())
                                .then(data => {{
                                    const holidays = new Set(data.holidays || []);
                                    const daysInMonth = new Date(year, month, 0).getDate();
                                    const workDays = new Set();
                                    for (let day = 1; day <= daysInMonth; day += 1) {{
                                        const dateValue = formatDate(year, month, day);
                                        const date = new Date(`${{dateValue}}T00:00:00`);
                                        const isWeekend = date.getDay() === 0 || date.getDay() === 6;
                                        if (!isWeekend && !holidays.has(dateValue)) {{
                                            workDays.add(dateValue);
                                        }}
                                    }}
                                    hiddenInput.value = Array.from(workDays).sort().join(',');
                                    hiddenInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    renderCalendar();
                                }})
                                .catch(() => {{
                                }});
                        }});
                    }}

                    if (!hiddenInput.value) {{
                        const initialDates = Array.from(defaultWorkDays).sort().join(',');
                        if (initialDates) {{
                            hiddenInput.value = initialDates;
                        }}
                    }}
                    updateWorkDaysPerMonth(parseSelectedDates());
                    renderCalendar();
                }})();
            </script>
        """

    def _resolve_selected_month(self, *, default: int) -> int:
        raw_month = self.data.get("month") if self.is_bound else getattr(self.instance, "month", None)
        if raw_month in (None, ""):
            raw_month = self.initial.get("month", default)
        return int(str(raw_month))

    def _resolve_selected_year(self, *, default: int) -> int:
        raw_year = self.data.get("year") if self.is_bound else getattr(self.instance, "year", None)
        if raw_year in (None, ""):
            raw_year = self.initial.get("year", default)
        return int(str(raw_year))

    def _resolve_selected_state(self, *, default: str) -> str:
        raw_state = self.data.get("state") if self.is_bound else None
        if raw_state in (None, ""):
            raw_state = self.initial.get("state", default)
        return str(raw_state)

    def _parse_work_day_dates(self, raw_value: object, *, month: object, year: object) -> list[datetime.date]:
        if not raw_value:
            return []

        if not month or not year:
            raise forms.ValidationError("Informe o mês e o ano antes de selecionar dias trabalhados.")

        selected_month = int(str(month))
        selected_year = int(str(year))
        last_day = calendar.monthrange(selected_year, selected_month)[1]
        parsed_dates: list[datetime.date] = []

        for raw_date in str(raw_value).split(","):
            normalized = raw_date.strip()
            if not normalized:
                continue

            try:
                parsed_date = datetime.date.fromisoformat(normalized)
            except ValueError as exc:
                raise forms.ValidationError("Existe um dia trabalhado inválido selecionado.") from exc

            if parsed_date.year != selected_year or parsed_date.month != selected_month:
                raise forms.ValidationError("Selecione apenas dias trabalhados dentro do mês de referência.")

            if parsed_date.day < 1 or parsed_date.day > last_day:
                raise forms.ValidationError("Selecione apenas dias válidos para o mês de referência.")

            if parsed_date not in parsed_dates:
                parsed_dates.append(parsed_date)

        return sorted(parsed_dates)

    def _sync_work_days(self, *, instance: WorkshopCost, work_day_dates: list[datetime.date]) -> None:
        existing_work_days = {work_day.date: work_day for work_day in instance.work_days.all()}
        selected_dates = set(work_day_dates)

        work_days_to_delete = [work_day.pk for current_date, work_day in existing_work_days.items() if current_date not in selected_dates and work_day.pk is not None]
        if work_days_to_delete:
            WorkshopCostWorkDay.objects.filter(pk__in=work_days_to_delete).delete()

        work_days_to_create = [WorkshopCostWorkDay(workshop_cost=instance, date=work_day_date) for work_day_date in work_day_dates if work_day_date not in existing_work_days]
        if work_days_to_create:
            WorkshopCostWorkDay.objects.bulk_create(work_days_to_create)

    def _get_holiday_dates(self, *, state: str, month: int, year: int) -> list[datetime.date]:
        holiday_calendar = holidays.Brazil(state=state, years=year)
        month_holidays: list[datetime.date] = []

        for holiday_date in holiday_calendar.keys():
            if holiday_date.year == year and holiday_date.month == month and holiday_date.weekday() < 5:
                month_holidays.append(holiday_date)

        good_friday_dates = [d for d in holiday_calendar.keys() if "Sexta" in str(holiday_calendar[d]) and d.year == year]
        if good_friday_dates:
            easter = good_friday_dates[0] + datetime.timedelta(days=2)

            movable_holidays = [
                easter - datetime.timedelta(days=48),
                easter - datetime.timedelta(days=47),
                easter - datetime.timedelta(days=46),
                easter + datetime.timedelta(days=60),
            ]

            for movable_date in movable_holidays:
                if movable_date.year == year and movable_date.month == month and movable_date.weekday() < 5:
                    month_holidays.append(movable_date)

        return sorted(set(month_holidays))

    def _get_work_day_dates_for_month(self, *, month: int, year: int, state: str) -> list[datetime.date]:
        holiday_dates = set(self._get_holiday_dates(state=state, month=month, year=year))
        days_in_month = calendar.monthrange(year, month)[1]
        work_days: list[datetime.date] = []
        for day in range(1, days_in_month + 1):
            current_date = datetime.date(year, month, day)
            if current_date.weekday() < 5 and current_date not in holiday_dates:
                work_days.append(current_date)
        return sorted(work_days)
