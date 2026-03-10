from decimal import Decimal

from django.utils import timezone
from djmoney.money import Money
from apps.workshops.models.workshop_costs import WorkshopCost


def get_current_workshop_cost(workshop):
    now = timezone.now()
    try:
        cost = WorkshopCost.objects.get(workshop=workshop, month=now.month, year=now.year)
        return cost, False
    except WorkshopCost.DoesNotExist:
        return None, True


def calculate_catalog_service_prices(duration, workshop_cost):
    """Calcula custo e venda baseados na duração (timedelta) e WorkshopCost."""
    if not duration:
        return Money(0, "BRL"), Money(0, "BRL")

    duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

    if workshop_cost:
        min_hourly = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
        hourly_val = workshop_cost.hourly_cost_value or Money(0, "BRL")

        cost = min_hourly * duration_hours
        sale = hourly_val * duration_hours
        return cost, sale

    return Money(0, "BRL"), Money(0, "BRL")
