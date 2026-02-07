from .shared import *


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
            vehicle = get_object_or_404(Vehicle, id=vehicle_id)
        return render(request, "budget/partials/components/vehicle_resume.html", {"vehicle": vehicle})
