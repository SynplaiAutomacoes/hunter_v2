from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from apps.customer.models import Customer, Vehicle


class CustomerDetailView(View):
    def get(self, request, *args, **kwargs):
        customer_id = request.GET.get("customer")
        customer = None
        if customer_id:
            customer = get_object_or_404(Customer, id=customer_id)
        return render(request, "budget/partials/components/customer_resume.html", {"customer": customer})


class VehicleListView(View):
    def get(self, request, *args, **kwargs):
        customer_id = request.GET.get("customer")
        selected_vehicle_raw = request.GET.get("selected_vehicle")

        extra_ids = set()
        if selected_vehicle_raw:
            for part in selected_vehicle_raw.split(","):
                part = part.strip()
                if part:
                    extra_ids.add(part)

        vehicle_pks = set()

        if customer_id:
            vehicle_pks.update(
                Vehicle.objects.filter(customer_id=customer_id).values_list("pk", flat=True)
            )

        for vid in extra_ids:
            try:
                vehicle_pks.add(int(vid))
            except (ValueError, TypeError):
                pass

        vehicles = Vehicle.objects.filter(pk__in=vehicle_pks)

        data = [{"id": v.id, "label": str(v), "km": v.km} for v in vehicles]

        return JsonResponse(data, safe=False)


class VehicleDetailView(View):
    def get(self, request, *args, **kwargs):
        vehicle_id = request.GET.get("vehicle")
        vehicle = None
        if vehicle_id:
            vehicle = get_object_or_404(Vehicle, id=vehicle_id)
        return render(request, "budget/partials/components/vehicle_resume.html", {"vehicle": vehicle})
