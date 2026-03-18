from __future__ import annotations

import json
from datetime import date, datetime, time

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views import View
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from apps.budget.models import Budget
from apps.customer.models import Vehicle
from apps.scheduling.forms import AppointmentCalendarFilterForm, AppointmentForm, AppointmentMoveForm, build_budget_create_url
from apps.scheduling.models import Appointment
from apps.workorder.models import WorkOrder
from apps.workshops.mixin import WorkshopScopedMixin


def _parse_request_datetime(raw_value: str | None) -> datetime | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    dt = parse_datetime(value)
    if dt is None:
        return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def _parse_request_date(raw_value: str | None) -> date | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    return parse_date(value)


class AppointmentCalendarView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = Appointment
    template_name = "scheduling/appointment_calendar.html"
    workshop_permission_codename = "view_appointment"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["calendar_events_url"] = reverse("scheduling:appointment_events")
        context["create_url"] = reverse("scheduling:appointment_create")
        context["filters_form"] = AppointmentCalendarFilterForm(workshop=self.workshop)
        return context


class AppointmentEventsView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        range_start = _parse_request_datetime(request.GET.get("start"))
        range_end = _parse_request_datetime(request.GET.get("end"))

        queryset = Appointment.objects.filter(workshop=self.workshop).select_related("customer", "vehicle", "budget", "workorder").order_by("starts_at")

        if range_start and range_end:
            queryset = queryset.filter(starts_at__lt=range_end, ends_at__gt=range_start)

        date_from = _parse_request_date(request.GET.get("date_from"))
        date_to = _parse_request_date(request.GET.get("date_to"))

        if date_from:
            dt_from = timezone.make_aware(datetime.combine(date_from, time.min), timezone.get_current_timezone())
            queryset = queryset.filter(ends_at__gt=dt_from)

        if date_to:
            dt_to = timezone.make_aware(datetime.combine(date_to, time.max), timezone.get_current_timezone())
            queryset = queryset.filter(starts_at__lt=dt_to)

        customer_filter = (request.GET.get("customer") or "").strip()
        if customer_filter:
            if customer_filter.isdigit():
                queryset = queryset.filter(customer_id=customer_filter)
            else:
                queryset = queryset.filter(customer__name__icontains=customer_filter)

        vehicle_filter = (request.GET.get("vehicle") or "").strip()
        if vehicle_filter:
            if vehicle_filter.isdigit():
                queryset = queryset.filter(vehicle_id=vehicle_filter)
            else:
                queryset = queryset.filter(Q(vehicle__plate__icontains=vehicle_filter) | Q(vehicle__model__icontains=vehicle_filter))

        status_filter = (request.GET.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        events = []
        for appointment in queryset:
            title = f"{appointment.title} - {appointment.customer.name}"
            events.append(
                {
                    "id": str(appointment.pk),
                    "title": title,
                    "start": appointment.starts_at.isoformat(),
                    "end": appointment.ends_at.isoformat(),
                    "color": appointment.block_color,
                    "extendedProps": {
                        "customer_name": appointment.customer.name,
                        "vehicle_label": str(appointment.vehicle),
                        "budget_id": appointment.budget.pk if appointment.budget else None,
                        "workorder_id": appointment.workorder.pk if appointment.workorder else None,
                        "status": appointment.status,
                    },
                }
            )

        return JsonResponse(events, safe=False)


class AppointmentBaseFormMixin(LoginRequiredMixin, WorkshopScopedMixin):
    model = Appointment
    form_class = AppointmentForm
    template_name = "scheduling/partials/appointment_form_modal.html"


class AppointmentCreateView(AppointmentBaseFormMixin, CreateView):
    success_url = reverse_lazy("scheduling:appointment_calendar")

    def get_form_kwargs(self):
        kwargs = CreateView.get_form_kwargs(self)
        kwargs["workshop"] = self.workshop
        kwargs["request"] = self.request
        return kwargs

    def _htmx_success_response(self):
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"appointmentsCalendarRefresh": True, "showToast": {"message": "Agendamento salvo com sucesso.", "type": "success"}})
        return response

    def _htmx_redirect_response(self, *, url: str):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response

    def form_valid(self, form):
        object_appointment = form.save()
        self.object = object_appointment
        action = (self.request.POST.get("action") or "").strip()

        if action == "save_and_create_budget":
            customer = object_appointment.customer
            vehicle = object_appointment.vehicle
            redirect_url = build_budget_create_url(customer_id=customer.pk, vehicle_id=vehicle.pk)
            if bool(getattr(self.request, "htmx", False)):
                return self._htmx_redirect_response(url=redirect_url)

            return HttpResponse(status=302, headers={"Location": redirect_url})

        if bool(getattr(self.request, "htmx", False)):
            return self._htmx_success_response()
        return CreateView.form_valid(self, form)

    def form_invalid(self, form):
        if bool(getattr(self.request, "htmx", False)):
            return render(
                self.request,
                "scheduling/partials/appointment_form_modal.html",
                {
                    "form": form,
                    "is_update": False,
                },
                status=400,
            )
        return CreateView.form_invalid(self, form)

    def get_initial(self):
        initial = super().get_initial()

        starts_at = _parse_request_datetime(self.request.GET.get("starts_at"))
        ends_at = _parse_request_datetime(self.request.GET.get("ends_at"))

        if starts_at:
            initial["starts_at"] = starts_at.strftime("%Y-%m-%dT%H:%M")
        if ends_at:
            initial["ends_at"] = ends_at.strftime("%Y-%m-%dT%H:%M")

        customer_id = (self.request.GET.get("customer") or "").strip()
        vehicle_id = (self.request.GET.get("vehicle") or "").strip()
        if customer_id:
            initial["customer"] = customer_id
        if vehicle_id:
            initial["vehicle"] = vehicle_id

        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = False
        return context


class AppointmentUpdateView(AppointmentBaseFormMixin, UpdateView):
    success_url = reverse_lazy("scheduling:appointment_calendar")

    def get_form_kwargs(self):
        kwargs = UpdateView.get_form_kwargs(self)
        kwargs["workshop"] = self.workshop
        kwargs["request"] = self.request
        return kwargs

    def _htmx_success_response(self):
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"appointmentsCalendarRefresh": True, "showToast": {"message": "Agendamento salvo com sucesso.", "type": "success"}})
        return response

    def _htmx_redirect_response(self, *, url: str):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response

    def form_valid(self, form):
        object_appointment = form.save()
        self.object = object_appointment
        action = (self.request.POST.get("action") or "").strip()

        if action == "save_and_create_budget":
            customer = object_appointment.customer
            vehicle = object_appointment.vehicle
            redirect_url = build_budget_create_url(customer_id=customer.pk, vehicle_id=vehicle.pk)
            if bool(getattr(self.request, "htmx", False)):
                return self._htmx_redirect_response(url=redirect_url)

            return HttpResponse(status=302, headers={"Location": redirect_url})

        if bool(getattr(self.request, "htmx", False)):
            return self._htmx_success_response()
        return UpdateView.form_valid(self, form)

    def form_invalid(self, form):
        if bool(getattr(self.request, "htmx", False)):
            return render(
                self.request,
                "scheduling/partials/appointment_form_modal.html",
                {
                    "form": form,
                    "is_update": True,
                    "delete_url": reverse("scheduling:appointment_delete", kwargs={"pk": self.object.pk}),
                },
                status=400,
            )
        return UpdateView.form_invalid(self, form)

    def get_queryset(self):
        return super().get_queryset().filter(workshop=self.workshop)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        context["delete_url"] = reverse("scheduling:appointment_delete", kwargs={"pk": self.object.pk})
        return context


class AppointmentDetailView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = Appointment
    template_name = "scheduling/partials/appointment_detail_modal.html"
    workshop_permission_codename = "view_appointment"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        appointment = get_object_or_404(
            Appointment.objects.select_related("customer", "vehicle", "budget", "workorder"),
            pk=kwargs["pk"],
            workshop=self.workshop,
        )

        context["appointment"] = appointment
        context["edit_url"] = reverse("scheduling:appointment_update", kwargs={"pk": appointment.pk})
        context["delete_url"] = reverse("scheduling:appointment_delete", kwargs={"pk": appointment.pk})
        context["create_budget_url"] = build_budget_create_url(customer_id=appointment.customer.pk, vehicle_id=appointment.vehicle.pk)
        context["budget_url"] = reverse("budget:budget_update", kwargs={"pk": appointment.budget.pk}) if appointment.budget else ""
        context["workorder_url"] = reverse("workorder:workorder_detail", kwargs={"pk": appointment.workorder.pk}) if appointment.workorder else ""
        return context


class AppointmentDeleteView(LoginRequiredMixin, WorkshopScopedMixin, DeleteView):
    model = Appointment
    success_url = reverse_lazy("scheduling:appointment_calendar")
    workshop_permission_codename = "delete_appointment"

    def get_queryset(self):
        return super().get_queryset().filter(workshop=self.workshop)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if bool(getattr(self.request, "htmx", False)):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps({"appointmentsCalendarRefresh": True, "showToast": {"message": "Agendamento removido com sucesso.", "type": "success"}})
            return response

        messages.success(request, "Agendamento removido com sucesso.")
        return HttpResponse(status=302, headers={"Location": reverse("scheduling:appointment_calendar")})


class AppointmentMoveView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "change_appointment"

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment, pk=pk, workshop=self.workshop)
        form = AppointmentMoveForm(request.POST, instance=appointment)

        if not form.is_valid():
            message = "Nao foi possivel atualizar o horario do agendamento."
            non_field_errors = form.non_field_errors()
            if non_field_errors:
                message = " ".join(str(error) for error in non_field_errors)

            return JsonResponse({"ok": False, "message": message}, status=400)

        appointment.starts_at = form.cleaned_data["starts_at"]
        appointment.ends_at = form.cleaned_data["ends_at"]

        try:
            appointment.full_clean()
        except ValidationError as exc:
            joined_errors: list[str] = []
            for messages_list in exc.message_dict.values():
                joined_errors.extend(str(message) for message in messages_list)
            message = " ".join(joined_errors) or "Nao foi possivel mover o agendamento."
            return JsonResponse({"ok": False, "message": message}, status=400)

        appointment.save(update_fields=["starts_at", "ends_at", "atualizado_em"])
        return JsonResponse({"ok": True})


class VehicleByCustomerListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        customer_id = (request.GET.get("customer") or "").strip()

        vehicles = Vehicle.objects.none()
        if customer_id:
            vehicles = Vehicle.objects.filter(workshop=self.workshop, customer_id=customer_id).order_by("plate")

        data = [{"id": vehicle.pk, "label": str(vehicle)} for vehicle in vehicles]
        return JsonResponse(data, safe=False)


class BudgetByVehicleListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        vehicle_id = (request.GET.get("vehicle") or "").strip()

        budgets = Budget.objects.none()
        if vehicle_id:
            budgets = Budget.objects.filter(workshop=self.workshop, vehicle_id=vehicle_id).select_related("customer", "vehicle").order_by("-criado_em")

        data = [{"id": budget.pk, "label": f"#{budget.pk} - {budget.customer or '-'} - {budget.vehicle or '-'}"} for budget in budgets]
        return JsonResponse(data, safe=False)


class WorkOrderByVehicleListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        vehicle_id = (request.GET.get("vehicle") or "").strip()

        workorders = WorkOrder.objects.none()
        if vehicle_id:
            workorders = WorkOrder.objects.filter(workshop=self.workshop, budget__vehicle_id=vehicle_id).select_related("budget", "budget__customer", "budget__vehicle").order_by("-criado_em")

        data = [{"id": workorder.pk, "label": f"#{workorder.pk} - {workorder.budget.customer if workorder.budget else '-'} - {workorder.budget.vehicle if workorder.budget else '-'}"} for workorder in workorders]
        return JsonResponse(data, safe=False)
