from __future__ import annotations

from django.db import models

from apps.core.infrastructure.models.abstract import TimeStampedModel


class DashboardMonthlySnapshot(TimeStampedModel):
    """Frozen dashboard KPIs for a workshop calendar month after month-end close."""

    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="dashboard_monthly_snapshots",
        verbose_name="Oficina",
    )
    year = models.PositiveIntegerField(verbose_name="Ano")
    month = models.PositiveSmallIntegerField(verbose_name="Mês")
    closed_at = models.DateTimeField(verbose_name="Fechamento oficial")
    captured_at = models.DateTimeField(verbose_name="Capturado em")

    cars_this_month = models.PositiveIntegerField(default=0)
    warranty_courtesy_cars = models.PositiveIntegerField(default=0)
    average_ticket = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_sold_to_date = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    projection = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    projection_warning = models.TextField(blank=True, default="")
    elapsed_days = models.PositiveIntegerField(default=0)
    remaining_days = models.PositiveIntegerField(default=0)
    configured_working_days = models.PositiveIntegerField(null=True, blank=True)
    business_holidays = models.PositiveIntegerField(default=0)
    accumulated_profitability = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    accumulated_markup = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    accumulated_markup_progress = models.PositiveSmallIntegerField(default=0)
    warranty_return_rate = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    approval_rate = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    total_pending_receivable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monthly_pending_receivable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    previous_months_pending_receivable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_general_pending_receivable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_pending_budgets = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monthly_pending_budgets = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    previous_months_pending_budgets = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_general_pending_budgets = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_rejected_budgets = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gross_revenue_target = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    daily_revenue_target = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    actual_daily_revenue = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    today_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    projection_vs_target = models.JSONField(default=dict, blank=True)
    actual_daily_revenue_vs_target = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Snapshot mensal do dashboard"
        verbose_name_plural = "Snapshots mensais do dashboard"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "year", "month"),
                name="unique_dashboard_monthly_snapshot_per_workshop_month",
            ),
        ]
        indexes = [
            models.Index(fields=("workshop", "year", "month"), name="dash_snap_ws_ym_idx"),
        ]
        ordering = ("-year", "-month", "workshop_id")

    def __str__(self) -> str:
        return f"Dashboard {self.workshop_id} {self.month:02d}/{self.year}"
