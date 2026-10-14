from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from apps.customer.models import Customer, Vehicle
from apps.workshops.util.workshops import get_active_workshop_or_404


class CustomerDetailView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        workshop = get_active_workshop_or_404(request)
        customer_id = request.GET.get("customer")
        customer = None
        if customer_id:
            customer = get_object_or_404(Customer, id=customer_id, workshop=workshop)
        return render(request, "budget/partials/components/customer_resume.html", {"customer": customer})


class VehicleListView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        workshop = get_active_workshop_or_404(request)
        customer_id = request.GET.get("customer")
        selected_vehicle_raw = request.GET.get("selected_vehicle")

        extra_ids = set()
        if selected_vehicle_raw:
            for part in selected_vehicle_raw.split(","):
                part = part.strip()
                if part:
                    extra_ids.add(part)

        vehicle_pks: set[int] = set()

        if customer_id:
            vehicle_pks.update(
                Vehicle.objects.filter(customer_id=customer_id, workshop=workshop).values_list("pk", flat=True)
            )

        for vid in extra_ids:
            try:
                vehicle_pks.add(int(vid))
            except (ValueError, TypeError):
                pass

        vehicles = Vehicle.objects.filter(pk__in=vehicle_pks, workshop=workshop)

        data = [{"id": v.id, "label": str(v), "km": v.km} for v in vehicles]

        return JsonResponse(data, safe=False)


class VehicleDetailView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        workshop = get_active_workshop_or_404(request)
        vehicle_id = request.GET.get("vehicle")
        vehicle = None
        if vehicle_id:
            vehicle = get_object_or_404(Vehicle, id=vehicle_id, workshop=workshop)
        return render(request, "budget/partials/components/vehicle_resume.html", {"vehicle": vehicle})
