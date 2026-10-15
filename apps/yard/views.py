from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.yard.forms import YardColumnForm
from apps.yard.models import YardColumn
from apps.yard.services import ensure_default_columns, get_board_data
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
    def _config_context(self, *, form=None):
        columns = list(YardColumn.objects.filter(workshop=self.workshop).order_by("position", "id"))
        return {"columns": columns, "form": form or YardColumnForm(), "workshop": self.workshop}

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
        return render(
            request,
            "yard/partials/config_column_form.html",
            {"form": form, "column": column, "workshop": self.workshop},
        )


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
