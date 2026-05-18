from __future__ import annotations

import calendar
import datetime
import json
from typing import cast

from django import forms
from django.urls import reverse
import holidays

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from djmoney.forms import MoneyField

from apps.core.forms import CoreModelForm
from apps.core.widgets import (
    DecimalInput,
    DurationInput,
    NumberInput,
    MoneyInput,
    PercentageInput,
    SearchableSelectInput,
    TextInput,
)
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostHoliday, WorkshopCostItem
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import ADMIN_SALARY_MONTHLY_COST_NAME, MECHANIC_SALARY_MONTHLY_COST_NAME


class WorkshopCostForm(CoreModelForm):
    EDIT_WARNING_MESSAGES = {
        MECHANIC_SALARY_MONTHLY_COST_NAME: "Esta é a soma total dos salários dos colaboradores produtivos, deseja manter?",
        ADMIN_SALARY_MONTHLY_COST_NAME: "Esta é a soma total dos salários dos colaboradores administrativos, deseja manter?",
    }
    holiday_dates = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = WorkshopCost
        fields = [
            # Referência
            "month",
            "year",
            # Mecânicos
            "mechanic_quantity",
            "work_hours_per_day",
            "work_days_per_month",
            "productivity_average",
            # Taxas
            "card_rate",
            "tax_rate",
            "profit_margin",
            "commission_rate",
            "risk_coefficient",
            # Metas Inputs
            "parts_purchase_cap",
            "freight_cost",
            "third_party_service_cap",
            # Calculados (Readonly)
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
            "work_days_per_month": NumberInput(),
            "productivity_average": PercentageInput(min_percent=50, max_percent=80, decimal_places=2),
            "card_rate": PercentageInput(decimal_places=2),
            "tax_rate": PercentageInput(decimal_places=2),
            "profit_margin": PercentageInput(decimal_places=2),
            "commission_rate": PercentageInput(max_percent=10, decimal_places=2),
            "risk_coefficient": DecimalInput(min_value=1.0, max_value=1.5, decimal_places=2),
            "parts_purchase_cap": MoneyInput(),
            "freight_cost": MoneyInput(),
            "third_party_service_cap": MoneyInput(),
            # Readonly widgets
            "total_value": MoneyInput(attrs={"readonly": True}),
            "total_monthly_costs": MoneyInput(attrs={"readonly": True}),
            "profit_target": MoneyInput(attrs={"readonly": True}),
            "gross_revenue_target": MoneyInput(attrs={"readonly": True}),
            "profitability_multiplier": DecimalInput(decimal_places=2, attrs={"readonly": True}),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        # Preenchimento automático de Data se for criação
        if not self.instance.pk and not self.data:
            today = datetime.date.today()
            self.fields["month"].initial = today.month
            self.fields["year"].initial = today.year

        self.active_costs = MonthlyCost.objects.filter(workshop=workshop, is_active=True)

        # Se for edição, busca os valores já salvos nos Items
        saved_values: dict[int, object] = {}
        if self.instance.pk:
            saved_values = {item.monthly_cost_id: item.amount for item in self.instance.items.all()}

        self.initial.setdefault("holiday_dates", self._serialize_holiday_dates())

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

        # Gera os campos dinâmicos de custo para o Layout
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
                # Envoltório com HTMX Trigger. Qualquer mudança (change) ou digitação (keyup) nestes campos dispara o recálculo.
                Div(
                    # --- SEÇÃO 1: Referência ---
                    HTML(f"""
                        <div class="col-span-12 flex items-center justify-between mb-2">
                            <h3 class="text-xl font-bold">Mês de Referência</h3>
                            {copy_btn_html}
                        </div>
                    """),
                    Field("month", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("year", wrapper_class="col-span-12 lg:col-span-6"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 2: Mecânicos ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Mecânicos Produtivos</h3>'),
                    Field("mechanic_quantity", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("work_hours_per_day", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("work_days_per_month", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("holiday_dates", type="hidden"),
                    HTML(self._build_holiday_calendar_html()),
                    Field("productivity_average", wrapper_class="col-span-12 lg:col-span-12"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 3: Despesas Mensais (Dinâmico) ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Despesas Mensais</h3>'),
                    Div(
                        *cost_fields_layout,
                        css_class="contents",  # Permite que os filhos obedeçam ao Grid pai
                    ),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 4: Taxas e Impostos ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Taxas e Impostos</h3>'),
                    Field("card_rate", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("tax_rate", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("profit_margin", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("commission_rate", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("risk_coefficient", wrapper_class="col-span-12 lg:col-span-12"),
                    HTML('<div class="col-span-12 divider my-2"></div>'),
                    # --- SEÇÃO 5: Metas e Indicadores ---
                    HTML('<h3 class="col-span-12 text-xl font-bold mb-2">Metas e Indicadores</h3>'),
                    Field("parts_purchase_cap", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("freight_cost", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("third_party_service_cap", wrapper_class="col-span-12 lg:col-span-4"),
                    # Atributos HTMX no container de inputs
                    # hx-include="closest form": Garante que todos os dados do form sejam enviados
                    hx_post=calculate_url,
                    hx_trigger="input delay:100ms, change delay:100ms",
                    hx_target="#calculation-results",
                    hx_include="closest form",
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start col-span-12",
                ),
                # Campos calculados (Desabilitados visualmente)
                Div(
                    HTML('<div class="col-span-12 mb-4"><span class="badge badge-neutral">Cálculos Automáticos</span></div>'),
                    Field("total_value", wrapper_class="col-span-12"),
                    Field("total_monthly_costs", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("profit_target", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("gross_revenue_target", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("profitability_multiplier", wrapper_class="col-span-12 lg:col-span-6"),
                    css_id="calculation-results",
                    css_class="col-span-12 bg-base-300 p-6 rounded-box grid grid-cols-1 lg:grid-cols-12 gap-4 items-start mt-4",
                ),
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
        holiday_dates = self._parse_holiday_dates(cleaned_data.get("holiday_dates"), month=month, year=year)
        cleaned_data["holiday_dates"] = holiday_dates
        if month and year:
            cleaned_data["work_days_per_month"] = self._calculate_work_days_per_month(month=int(str(month)), year=int(str(year)), holiday_dates=holiday_dates)
        self.instance.holiday_dates_override = holiday_dates

        if month and year and self.workshop:
            qs = WorkshopCost.objects.filter(workshop=self.workshop, month=month, year=year)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um custo mensal para este Mês/Ano.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.workshop = self.workshop
        holiday_dates = cast(list[datetime.date], self.cleaned_data.get("holiday_dates", []))
        instance.holiday_dates_override = holiday_dates

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

            self._sync_holidays(instance=instance, holiday_dates=holiday_dates)

            instance.calculate_all()
            instance.save()
        return instance

    def _serialize_holiday_dates(self) -> str:
        if not self.instance.pk:
            if self.is_bound:
                return str(self.data.get("holiday_dates") or "")
            month = self._resolve_selected_month(default=datetime.date.today().month)
            year = self._resolve_selected_year(default=datetime.date.today().year)
            auto_holidays = self._get_sp_holiday_dates(month=month, year=year)
            return ",".join(holiday_date.isoformat() for holiday_date in auto_holidays)

        holiday_dates = self.instance.holidays.order_by("date").values_list("date", flat=True)
        return ",".join(holiday_date.isoformat() for holiday_date in holiday_dates)

    def _build_holiday_calendar_html(self) -> str:
        today = datetime.date.today()
        selected_month = self._resolve_selected_month(default=today.month)
        selected_year = self._resolve_selected_year(default=today.year)
        default_holiday_dates = [holiday_date.isoformat() for holiday_date in self._get_sp_holiday_dates(month=selected_month, year=selected_year)]
        weekday_labels = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"]

        return f"""
            <div class="col-span-12 rounded-box border border-base-300 bg-base-200/40 p-2 w-fit lg:justify-self-end">
                <div class="flex flex-col gap-1">
                    <div class="flex items-start justify-between gap-2">
                        <div>
                            <h3 class="text-sm font-semibold">Calendário de Feriados</h3>
                            <p class="text-[10px] text-base-content/70">Clique em um dia útil para marcar ou desmarcar feriado.</p>
                        </div>
                        <button type="button" id="holiday-calendar-toggle" class="btn btn-xs btn-ghost">Mostrar</button>
                    </div>
                    <div id="holiday-calendar-panel" class="hidden">
                        <div id="holiday-calendar"
                             class="grid grid-cols-7 gap-1 max-w-[260px]"
                             data-selected-month="{selected_month}"
                             data-selected-year="{selected_year}"
                             data-default-holidays='{json.dumps(default_holiday_dates)}'
                             data-weekday-labels='{json.dumps(weekday_labels)}'></div>
                    </div>
                </div>
            </div>
            <script>
                (function() {{
                    const hiddenInput = document.getElementById('id_holiday_dates');
                    const monthInput = document.getElementById('id_month');
                    const yearInput = document.getElementById('id_year');
                    const calendarRoot = document.getElementById('holiday-calendar');
                    const panel = document.getElementById('holiday-calendar-panel');
                    const toggleButton = document.getElementById('holiday-calendar-toggle');

                    if (!hiddenInput || !monthInput || !yearInput || !calendarRoot || !panel || !toggleButton) {{
                        return;
                    }}

                    const weekdayLabels = JSON.parse(calendarRoot.dataset.weekdayLabels || '[]');
                    const defaultHolidays = new Set(JSON.parse(calendarRoot.dataset.defaultHolidays || '[]'));

                    function calculateWorkDaysPerMonth(year, month, selectedDates) {{
                        const daysInMonth = new Date(year, month, 0).getDate();
                        return Math.max(daysInMonth - selectedDates.size, 0);
                    }}

                    function updateWorkDaysPerMonth(year, month, selectedDates) {{
                        const workDaysInput = document.getElementById('id_work_days_per_month');
                        if (!workDaysInput) {{
                            return;
                        }}
                        const calculated = calculateWorkDaysPerMonth(year, month, selectedDates);
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

                    function countBusinessHolidays(selectedDates, year, month) {{
                        return Array.from(selectedDates).filter(value => {{
                            const date = new Date(`${{value}}T00:00:00`);
                            return date.getFullYear() === year && (date.getMonth() + 1) === month && date.getDay() !== 0 && date.getDay() !== 6;
                        }}).length;
                    }}

                    function renderCalendar() {{
                        if (panel.classList.contains('hidden')) {{
                            return;
                        }}
                        const year = parseInt(yearInput.value || calendarRoot.dataset.selectedYear || '0', 10);
                        const month = parseInt(monthInput.value || calendarRoot.dataset.selectedMonth || '0', 10);
                        if (!year || !month) {{
                            return;
                        }}

                        calendarRoot.dataset.selectedYear = String(year);
                        calendarRoot.dataset.selectedMonth = String(month);
                        let selectedDates = filterDatesForMonth(parseSelectedDates(), year, month);
                        if (selectedDates.size === 0 && defaultHolidays.size > 0) {{
                            selectedDates = filterDatesForMonth(defaultHolidays, year, month);
                        }}
                        hiddenInput.value = Array.from(selectedDates).sort().join(',');
                        updateWorkDaysPerMonth(year, month, selectedDates);
                        const daysInMonth = new Date(year, month, 0).getDate();
                        const firstWeekday = new Date(year, month - 1, 1).getDay();
                        const weekdayOffset = firstWeekday;
                        const businessHolidayCount = countBusinessHolidays(selectedDates, year, month);
                        void businessHolidayCount;
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
                            button.className = `h-7 w-7 rounded-sm border text-[11px] font-medium transition ${{isWeekend ? 'cursor-not-allowed border-base-300 bg-base-100 text-base-content/30' : isSelected ? 'border-warning bg-warning/20 text-warning-content' : 'border-base-300 bg-base-100 hover:border-warning hover:bg-warning/10'}}`;

                            if (isWeekend) {{
                                button.disabled = true;
                            }} else {{
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
                            }}

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

    def _parse_holiday_dates(self, raw_value: object, *, month: object, year: object) -> list[datetime.date]:
        if not raw_value:
            return []

        if not month or not year:
            raise forms.ValidationError("Informe o mês e o ano antes de selecionar feriados.")

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
                raise forms.ValidationError("Existe um feriado inválido selecionado.") from exc

            if parsed_date.year != selected_year or parsed_date.month != selected_month:
                raise forms.ValidationError("Selecione apenas feriados dentro do mês de referência.")

            if parsed_date.day < 1 or parsed_date.day > last_day:
                raise forms.ValidationError("Selecione apenas dias válidos para o mês de referência.")

            if parsed_date not in parsed_dates:
                parsed_dates.append(parsed_date)

        return sorted(parsed_dates)

    def _sync_holidays(self, *, instance: WorkshopCost, holiday_dates: list[datetime.date]) -> None:
        existing_holidays = {holiday.date: holiday for holiday in instance.holidays.all()}
        selected_dates = set(holiday_dates)

        holidays_to_delete = [holiday.pk for current_date, holiday in existing_holidays.items() if current_date not in selected_dates and holiday.pk is not None]
        if holidays_to_delete:
            WorkshopCostHoliday.objects.filter(pk__in=holidays_to_delete).delete()

        holidays_to_create = [WorkshopCostHoliday(workshop_cost=instance, date=holiday_date) for holiday_date in holiday_dates if holiday_date not in existing_holidays]
        if holidays_to_create:
            WorkshopCostHoliday.objects.bulk_create(holidays_to_create)

    def _get_sp_holiday_dates(self, *, month: int, year: int) -> list[datetime.date]:
        holiday_calendar = holidays.Brazil(state="SP", years=year)
        month_holidays: list[datetime.date] = []
        for holiday_date in holiday_calendar.keys():
            if holiday_date.year == year and holiday_date.month == month and holiday_date.weekday() < 5:
                month_holidays.append(holiday_date)
        return sorted(set(month_holidays))

    @staticmethod
    def _calculate_work_days_per_month(*, month: int, year: int, holiday_dates: list[datetime.date]) -> int:
        total_days = calendar.monthrange(year, month)[1]
        return max(total_days - len(set(holiday_dates)), 0)
