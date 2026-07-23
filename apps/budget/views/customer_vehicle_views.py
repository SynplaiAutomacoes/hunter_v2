from __future__ import annotations

import json

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

        vehicles = Vehicle.objects.none()
        if customer_id:
            vehicles = Vehicle.objects.filter(customer_id=customer_id)

        data = [{"id": v.id, "label": str(v)} for v in vehicles]

        return JsonResponse(data, safe=False)


class VehicleDetailView(View):
    def get(self, request, *args, **kwargs):
        vehicle_id = request.GET.get("vehicle")
        vehicle = None
        if vehicle_id:
            vehicle = get_object_or_404(Vehicle.objects.select_related("oil_type"), id=vehicle_id)
        response = render(request, "budget/partials/components/vehicle_resume.html", {"vehicle": vehicle})
        if vehicle is not None:
            response["HX-Trigger"] = json.dumps(
                {
                    "oilPrefill": {
                        "last_oil_change_date": vehicle.last_oil_change_date.isoformat() if vehicle.last_oil_change_date else "",
                        "last_oil_change_km": vehicle.last_oil_change_km if vehicle.last_oil_change_km is not None else "",
                        "oil_type_id": str(vehicle.oil_type_id) if vehicle.oil_type_id else "",
                    }
                }
            )
        return response
