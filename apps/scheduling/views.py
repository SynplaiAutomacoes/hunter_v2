from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, time

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views import View
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from apps.budget.models import Budget
from apps.core.infrastructure.search import apply_text_search
from apps.customer.models import Customer
from apps.customer.models import Vehicle
from apps.customer.vehicle_engine import normalize_vehicle_engine_choice
from apps.customer.vehicle_fuel import normalize_vehicle_fuel_choice
from apps.scheduling.forms import AppointmentCalendarFilterForm, AppointmentForm, AppointmentMoveForm, build_budget_create_url, default_appointment_ends_at
from apps.scheduling.models import Appointment
from apps.workorder.models import WorkOrder
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


def _format_datetime_local_value(value: datetime) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def _log_request_context(request, scope: str, **extra) -> None:
    logger.debug(
        "[SCHED_DEBUG] %s method=%s path=%s htmx=%s HX-Request=%s HX-Target=%s HX-Current-URL=%s extra=%s",
        scope,
        request.method,
        request.path,
        bool(getattr(request, "htmx", False)),
        request.headers.get("HX-Request", ""),
        request.headers.get("HX-Target", ""),
        request.headers.get("HX-Current-URL", ""),
        extra,
    )


def _parse_request_datetime(raw_value: str | None) -> datetime | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    dt = parse_datetime(value)
    if dt is None:
        parsed_date = parse_date(value)
        if parsed_date:
            naive = datetime.combine(parsed_date, time.min)
            aware = timezone.make_aware(naive, timezone.get_current_timezone())
            logger.debug("[SCHED_DEBUG] parse_date raw=%s -> aware_local=%s", value, aware.isoformat())
            return aware
        return None

    if timezone.is_naive(dt):
        aware = timezone.make_aware(dt, timezone.get_current_timezone())
        logger.debug("[SCHED_DEBUG] parse_datetime naive raw=%s -> aware_local=%s", value, aware.isoformat())
        return aware

    localized = timezone.localtime(dt)
    logger.debug("[SCHED_DEBUG] parse_datetime aware raw=%s -> local=%s", value, localized.isoformat())
    return localized


def _parse_wall_datetime(raw_value: str | None) -> datetime | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    normalized = value.replace(" ", "T")
    if len(normalized) >= 16:
        normalized = normalized[:16]

    try:
        parsed = datetime.strptime(normalized, "%Y-%m-%dT%H:%M")
        logger.debug("[SCHED_DEBUG] parse_wall raw=%s -> parsed=%s", value, parsed.isoformat())
        return parsed
    except ValueError:
        return None


def _parse_request_timestamp(raw_value: str | None) -> datetime | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    try:
        milliseconds = int(value)
    except ValueError:
        return None

    utc_dt = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    localized = timezone.localtime(utc_dt)
    logger.debug("[SCHED_DEBUG] parse_ts raw=%s -> utc=%s local=%s", value, utc_dt.isoformat(), localized.isoformat())
    return localized


def _parse_request_date(raw_value: str | None) -> date | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    return parse_date(value)


def _serialize_calendar_datetime(value: datetime, tz=None) -> str:
    if tz is None:
        tz = timezone.get_current_timezone()
    return timezone.localtime(value, tz).isoformat()


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
                queryset = apply_text_search(queryset, search_value=customer_filter, lookups=("customer__name", "guest_customer_name"))

        vehicle_filter = (request.GET.get("vehicle") or "").strip()
        if vehicle_filter:
            if vehicle_filter.isdigit():
                queryset = queryset.filter(vehicle_id=vehicle_filter)
            else:
                queryset = apply_text_search(queryset, search_value=vehicle_filter, lookups=("vehicle__plate", "vehicle__model", "guest_vehicle_plate", "guest_vehicle_brand", "guest_vehicle_model"))

        status_filter = (request.GET.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        events = []
        current_tz = timezone.get_current_timezone()
        for appointment in queryset:
            customer_name = appointment.display_customer_name
            title = f"{appointment.title} - {customer_name}" if customer_name else appointment.title
            events.append(
                {
                    "id": str(appointment.pk),
                    "title": title,
                    "start": _serialize_calendar_datetime(appointment.starts_at, current_tz),
                    "end": _serialize_calendar_datetime(appointment.ends_at, current_tz),
                    "color": appointment.block_color,
                    "extendedProps": {
                        "customer_name": customer_name,
                        "vehicle_label": appointment.display_vehicle_label,
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

    def get(self, request, *args, **kwargs):
        _log_request_context(request, "create.get")
        if not bool(getattr(request, "htmx", False)):
            return HttpResponse(status=302, headers={"Location": reverse("scheduling:appointment_calendar")})
        return super().get(request, *args, **kwargs)

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
        _log_request_context(
            self.request,
            "create.form_valid",
            action=(self.request.POST.get("action") or ""),
            starts_at=str(form.cleaned_data.get("starts_at")),
            ends_at=str(form.cleaned_data.get("ends_at")),
        )
        object_appointment = form.save()
        self.object = object_appointment
        action = (self.request.POST.get("action") or "").strip()

        if action == "save_and_create_budget":
            redirect_url = build_budget_create_url(
                customer_id=object_appointment.customer.pk if object_appointment.customer else None,
                vehicle_id=object_appointment.vehicle.pk if object_appointment.vehicle else None,
                appointment_id=object_appointment.pk,
            )
            if bool(getattr(self.request, "htmx", False)):
                return self._htmx_redirect_response(url=redirect_url)

            return HttpResponse(status=302, headers={"Location": redirect_url})

        if bool(getattr(self.request, "htmx", False)):
            return self._htmx_success_response()
        return CreateView.form_valid(self, form)

    def form_invalid(self, form):
        _log_request_context(
            self.request,
            "create.form_invalid",
            errors=form.errors.get_json_data(),
            posted_starts_at=(self.request.POST.get("starts_at") or ""),
            posted_ends_at=(self.request.POST.get("ends_at") or ""),
        )
        if bool(getattr(self.request, "htmx", False)):
            return render(
                self.request,
                "scheduling/partials/appointment_form_modal.html",
                {
                    "form": form,
                    "is_update": False,
                },
                status=200,
            )
        messages.error(self.request, "Nao foi possivel salvar o agendamento. Revise os campos informados.")
        return HttpResponse(status=302, headers={"Location": reverse("scheduling:appointment_calendar")})

    def get_initial(self):
        initial = super().get_initial()

        starts_at = _parse_wall_datetime(self.request.GET.get("starts_at")) or _parse_request_timestamp(self.request.GET.get("start_ts")) or _parse_request_datetime(self.request.GET.get("starts_at"))
        ends_at = _parse_wall_datetime(self.request.GET.get("ends_at")) or _parse_request_timestamp(self.request.GET.get("end_ts")) or _parse_request_datetime(self.request.GET.get("ends_at"))

        if starts_at:
            initial["starts_at"] = _format_datetime_local_value(starts_at)
        if ends_at:
            initial["ends_at"] = _format_datetime_local_value(ends_at)
        elif starts_at:
            initial["ends_at"] = _format_datetime_local_value(default_appointment_ends_at(starts_at))

        customer_id = (self.request.GET.get("customer") or "").strip()
        vehicle_id = (self.request.GET.get("vehicle") or "").strip()
        if customer_id:
            initial["customer"] = customer_id
        if vehicle_id:
            initial["vehicle"] = vehicle_id

        _log_request_context(
            self.request,
            "create.get_initial",
            query_starts_at=(self.request.GET.get("starts_at") or ""),
            query_ends_at=(self.request.GET.get("ends_at") or ""),
            query_start_ts=(self.request.GET.get("start_ts") or ""),
            query_end_ts=(self.request.GET.get("end_ts") or ""),
            initial_starts_at=str(initial.get("starts_at") or ""),
            initial_ends_at=str(initial.get("ends_at") or ""),
        )

        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = False
        return context


class AppointmentUpdateView(AppointmentBaseFormMixin, UpdateView):
    success_url = reverse_lazy("scheduling:appointment_calendar")

    def get(self, request, *args, **kwargs):
        _log_request_context(request, "update.get", pk=kwargs.get("pk"))
        if not bool(getattr(request, "htmx", False)):
            return HttpResponse(status=302, headers={"Location": reverse("scheduling:appointment_calendar")})
        return super().get(request, *args, **kwargs)

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
        _log_request_context(
            self.request,
            "update.form_valid",
            pk=self.kwargs.get("pk"),
            action=(self.request.POST.get("action") or ""),
            starts_at=str(form.cleaned_data.get("starts_at")),
            ends_at=str(form.cleaned_data.get("ends_at")),
        )
        object_appointment = form.save()
        self.object = object_appointment
        action = (self.request.POST.get("action") or "").strip()

        if action == "save_and_create_budget":
            redirect_url = build_budget_create_url(
                customer_id=object_appointment.customer.pk if object_appointment.customer else None,
                vehicle_id=object_appointment.vehicle.pk if object_appointment.vehicle else None,
                appointment_id=object_appointment.pk,
            )
            if bool(getattr(self.request, "htmx", False)):
                return self._htmx_redirect_response(url=redirect_url)

            return HttpResponse(status=302, headers={"Location": redirect_url})

        if bool(getattr(self.request, "htmx", False)):
            return self._htmx_success_response()
        return UpdateView.form_valid(self, form)

    def form_invalid(self, form):
        _log_request_context(
            self.request,
            "update.form_invalid",
            pk=self.kwargs.get("pk"),
            errors=form.errors.get_json_data(),
            posted_starts_at=(self.request.POST.get("starts_at") or ""),
            posted_ends_at=(self.request.POST.get("ends_at") or ""),
        )
        if bool(getattr(self.request, "htmx", False)):
            object_appointment = self.get_object()
            return render(
                self.request,
                "scheduling/partials/appointment_form_modal.html",
                {
                    "form": form,
                    "is_update": True,
                    "delete_url": reverse("scheduling:appointment_delete", kwargs={"pk": object_appointment.pk}),
                },
                status=200,
            )
        messages.error(self.request, "Nao foi possivel salvar o agendamento. Revise os campos informados.")
        return HttpResponse(status=302, headers={"Location": reverse("scheduling:appointment_calendar")})

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
        context["create_budget_url"] = build_budget_create_url(
            customer_id=appointment.customer.pk if appointment.customer else None,
            vehicle_id=appointment.vehicle.pk if appointment.vehicle else None,
            appointment_id=appointment.pk,
        )
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
        from apps.messaging.application.services.appointment_alert import sync_appointment_alert_schedule

        sync_appointment_alert_schedule(appointment)
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


class CustomerListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        search = (request.GET.get("q") or "").strip()

        customers = Customer.objects.filter(workshop=self.workshop, is_active=True).order_by("name")
        if search:
            customers = apply_text_search(customers, search_value=search, lookups=("name", "cpf_or_cnpj", "email"))

        data = [{"id": customer.pk, "label": customer.name} for customer in customers[:30]]
        return JsonResponse(data, safe=False)


class VehicleDetailView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        vehicle_id = (request.GET.get("vehicle") or "").strip()
        if not vehicle_id:
            return JsonResponse({}, status=404)

        vehicle = get_object_or_404(Vehicle, pk=vehicle_id, workshop=self.workshop)
        return JsonResponse(
            {
                "id": vehicle.pk,
                "plate": str(vehicle.plate or ""),
                "brand": str(vehicle.brand or ""),
                "model": str(vehicle.model or ""),
                "year_fabrication": str(vehicle.year_fabrication or ""),
                "year_model": str(vehicle.year_model or ""),
                "engine": normalize_vehicle_engine_choice(vehicle.engine),
                "fuel": normalize_vehicle_fuel_choice(vehicle.fuel),
            }
        )


class BudgetByVehicleListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        vehicle_id = (request.GET.get("vehicle") or "").strip()

        budgets = Budget.objects.none()
        if vehicle_id:
            budgets = Budget.objects.filter(workshop=self.workshop, vehicle_id=vehicle_id).select_related("customer", "vehicle").order_by("-criado_em")

        data = [{"id": budget.pk, "label": f"Orçamento #{budget.pk}"} for budget in budgets]
        return JsonResponse(data, safe=False)


class WorkOrderByVehicleListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Appointment
    workshop_permission_codename = "view_appointment"

    def get(self, request):
        vehicle_id = (request.GET.get("vehicle") or "").strip()

        workorders = WorkOrder.objects.none()
        if vehicle_id:
            workorders = WorkOrder.objects.filter(workshop=self.workshop, budget__vehicle_id=vehicle_id).select_related("budget", "budget__customer", "budget__vehicle").order_by("-criado_em")

        data = [{"id": workorder.pk, "label": f"O.S. #{workorder.get_id}"} for workorder in workorders]
        return JsonResponse(data, safe=False)
