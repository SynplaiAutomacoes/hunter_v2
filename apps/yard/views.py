from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.yard.forms import YardColumnForm, YardHiddenStatusForm, YardStatusGroupForm
from apps.yard.models import YardColumn, YardHiddenStatus, YardPreference, YardStatusGroup
from apps.yard.services import ensure_default_columns, get_board_data, get_board_preference
from apps.workshops.mixin import WorkshopScopedMixin


def _board_triggers() -> str:
    return json.dumps({"yard-board-refresh": {}, "closeYardModal": {}})


class YardBoardView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, TemplateView):
    model = YardColumn
    template_name = "yard/board.html"
    htmx_template_name = "yard/partials/board_content.html"
    workshop_permission_codename = "view_yardcolumn"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ensure_default_columns(workshop=self.workshop)
        context["board"] = get_board_data(workshop=self.workshop)
        context["preference"] = get_board_preference(workshop=self.workshop)
        context["can_edit"] = self._can_edit()
        return context

    def _can_edit(self) -> bool:
        from apps.workshops.util.workshops import has_workshop_perm

        return has_workshop_perm(
            user=self.request.user,
            workshop=self.workshop,
            app_label="yard",
            model="yardcolumn",
            codename="change_yardcolumn",
            request=self.request,
        )


class YardBoardContentView(YardBoardView):
    template_name = "yard/partials/board_content.html"


class YardConfigMixin:
    def _config_context(self, *, form=None, hidden_form=None, group_form=None, editing_group=None):
        columns = list(YardColumn.objects.filter(workshop=self.workshop).order_by("position", "id"))
        hidden_statuses = list(YardHiddenStatus.objects.filter(workshop=self.workshop).order_by("target", "status"))
        groups = list(YardStatusGroup.objects.filter(workshop=self.workshop).order_by("target", "title"))
        return {
            "columns": columns,
            "hidden_statuses": hidden_statuses,
            "groups": groups,
            "editing_group": editing_group,
            "form": form or YardColumnForm(),
            "hidden_form": hidden_form or YardHiddenStatusForm(),
            "group_form": group_form or YardStatusGroupForm(),
            "workshop": self.workshop,
        }

    def _columns_list_context(self):
        columns = list(YardColumn.objects.filter(workshop=self.workshop).order_by("position", "id"))
        return {"columns": columns, "workshop": self.workshop}


class YardConfigModalView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardColumn
    workshop_permission_codename = "view_yardcolumn"

    def get(self, request, *args, **kwargs):
        return render(request, "yard/partials/config_modal_content.html", self._config_context())


class YardColumnCreateView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardColumn
    workshop_permission_codename = "add_yardcolumn"

    def post(self, request, *args, **kwargs):
        form = YardColumnForm(request.POST)
        form.instance.workshop = self.workshop
        if form.is_valid():
            column = form.save(commit=False)
            column.workshop = self.workshop
            if not YardColumn.objects.filter(workshop=self.workshop).exists():
                column.position = 0
            else:
                from django.db.models import Max

                column.position = (YardColumn.objects.filter(workshop=self.workshop).aggregate(max_position=Max("position"))["max_position"] or 0) + 1
            column.save()
            response = render(request, "yard/partials/config_modal_content.html", self._config_context())
            response["HX-Trigger"] = _board_triggers()
            return response
        response = render(request, "yard/partials/config_modal_content.html", self._config_context(form=form))
        return response

    def get(self, request, *args, **kwargs):
        return redirect(reverse("yard:board"))


class YardColumnUpdateView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardColumn
    workshop_permission_codename = "change_yardcolumn"

    def _get_column(self):
        return get_object_or_404(YardColumn, pk=self.kwargs.get("pk"), workshop=self.workshop)

    def get(self, request, *args, **kwargs):
        column = self._get_column()
        form = YardColumnForm(instance=column)
        return render(
            request,
            "yard/partials/config_column_form.html",
            {"form": form, "column": column, "workshop": self.workshop},
        )

    def post(self, request, *args, **kwargs):
        column = self._get_column()
        form = YardColumnForm(request.POST, instance=column)
        form.instance.workshop = self.workshop
        if form.is_valid():
            form.save()
            response = render(request, "yard/partials/config_modal_content.html", self._config_context())
            response["HX-Trigger"] = _board_triggers()
            return response
        response = render(request, "yard/partials/config_modal_content.html", self._config_context(form=form))
        return response


class YardColumnDeleteView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardColumn
    workshop_permission_codename = "delete_yardcolumn"

    def post(self, request, *args, **kwargs):
        column = get_object_or_404(YardColumn, pk=self.kwargs.get("pk"), workshop=self.workshop)
        column.delete()
        response = render(request, "yard/partials/config_columns_list.html", self._columns_list_context())
        response["HX-Trigger"] = _board_triggers()
        return response

    def get(self, request, *args, **kwargs):
        return redirect(reverse("yard:board"))


class YardColumnMoveView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardColumn
    workshop_permission_codename = "change_yardcolumn"

    def post(self, request, *args, **kwargs):
        column = get_object_or_404(YardColumn, pk=self.kwargs.get("pk"), workshop=self.workshop)
        direction = str(request.POST.get("direction") or "").strip().lower()
        siblings = list(YardColumn.objects.filter(workshop=self.workshop).order_by("position", "id"))
        index = next((position for position, sibling in enumerate(siblings) if sibling.pk == column.pk), None)
        if index is not None:
            neighbor_index = index - 1 if direction == "up" else index + 1 if direction == "down" else None
            if neighbor_index is not None and 0 <= neighbor_index < len(siblings):
                neighbor = siblings[neighbor_index]
                column.position, neighbor.position = neighbor.position, column.position
                if column.position == neighbor.position:
                    column.position = index
                    neighbor.position = neighbor_index
                column.save(update_fields=["position"])
                neighbor.save(update_fields=["position"])
        response = render(request, "yard/partials/config_columns_list.html", self._columns_list_context())
        response["HX-Trigger"] = _board_triggers()
        return response


class YardColumnsReorderView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = YardColumn
    workshop_permission_codename = "change_yardcolumn"

    def post(self, request, *args, **kwargs):
        ordered_ids = []
        for raw_id in request.POST.getlist("column_ids"):
            try:
                ordered_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        columns = {column.pk: column for column in YardColumn.objects.filter(workshop=self.workshop, pk__in=ordered_ids)}
        for position, column_id in enumerate(ordered_ids):
            column = columns.get(column_id)
            if column is not None and column.position != position:
                column.position = position
                column.save(update_fields=["position"])
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"yard-board-refresh": {}})
        return response


class YardPreferenceToggleView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = YardPreference
    workshop_permission_codename = "view_yardcolumn"

    def post(self, request, *args, **kwargs):
        preference, _created = YardPreference.objects.get_or_create(workshop=self.workshop)
        preference.hide_similar = not preference.hide_similar
        preference.save(update_fields=["hide_similar"])
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response


class YardHiddenStatusCreateView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardHiddenStatus
    workshop_permission_codename = "change_yardcolumn"

    def post(self, request, *args, **kwargs):
        form = YardHiddenStatusForm(request.POST)
        form.instance.workshop = self.workshop
        if form.is_valid():
            form.save()
            response = render(request, "yard/partials/config_modal_content.html", self._config_context())
            response["HX-Trigger"] = _board_triggers()
            return response
        response = render(request, "yard/partials/config_modal_content.html", self._config_context(hidden_form=form))
        return response

    def get(self, request, *args, **kwargs):
        return redirect(reverse("yard:board"))


class YardHiddenStatusDeleteView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardHiddenStatus
    workshop_permission_codename = "change_yardcolumn"

    def post(self, request, *args, **kwargs):
        hidden_status = get_object_or_404(YardHiddenStatus, pk=self.kwargs.get("pk"), workshop=self.workshop)
        hidden_status.delete()
        response = render(request, "yard/partials/config_modal_content.html", self._config_context())
        response["HX-Trigger"] = _board_triggers()
        return response

    def get(self, request, *args, **kwargs):
        return redirect(reverse("yard:board"))


class YardStatusGroupCreateView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardStatusGroup
    workshop_permission_codename = "change_yardcolumn"

    def post(self, request, *args, **kwargs):
        form = YardStatusGroupForm(request.POST)
        form.instance.workshop = self.workshop
        if form.is_valid():
            form.save()
            response = render(request, "yard/partials/config_modal_content.html", self._config_context())
            response["HX-Trigger"] = _board_triggers()
            return response
        response = render(request, "yard/partials/config_modal_content.html", self._config_context(group_form=form))
        return response

    def get(self, request, *args, **kwargs):
        return redirect(reverse("yard:board"))


class YardStatusGroupUpdateView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardStatusGroup
    workshop_permission_codename = "change_yardcolumn"

    def _get_group(self):
        return get_object_or_404(YardStatusGroup, pk=self.kwargs.get("pk"), workshop=self.workshop)

    def get(self, request, *args, **kwargs):
        group = self._get_group()
        form = YardStatusGroupForm(instance=group)
        return render(
            request,
            "yard/partials/config_group_form.html",
            {"form": form, "group": group, "workshop": self.workshop},
        )

    def post(self, request, *args, **kwargs):
        group = self._get_group()
        form = YardStatusGroupForm(request.POST, instance=group)
        form.instance.workshop = self.workshop
        if form.is_valid():
            form.save()
            response = render(request, "yard/partials/config_modal_content.html", self._config_context())
            response["HX-Trigger"] = _board_triggers()
            return response
        response = render(request, "yard/partials/config_modal_content.html", self._config_context(group_form=form))
        return response


class YardStatusGroupDeleteView(LoginRequiredMixin, WorkshopScopedMixin, YardConfigMixin, View):
    model = YardStatusGroup
    workshop_permission_codename = "change_yardcolumn"

    def post(self, request, *args, **kwargs):
        group = get_object_or_404(YardStatusGroup, pk=self.kwargs.get("pk"), workshop=self.workshop)
        group.delete()
        response = render(request, "yard/partials/config_modal_content.html", self._config_context())
        response["HX-Trigger"] = _board_triggers()
        return response

    def get(self, request, *args, **kwargs):
        return redirect(reverse("yard:board"))
