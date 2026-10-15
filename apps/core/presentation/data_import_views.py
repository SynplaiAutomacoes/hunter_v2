from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View


from apps.core.infrastructure.importing.mapper import suggest_mapping
from apps.core.infrastructure.importing.persistence import persist_import_batch
from apps.core.infrastructure.importing.registry import get_adapter
from apps.core.infrastructure.importing.rollback import (
    build_rollback_plan,
    execute_rollback,
    get_entity_label,
)
from apps.core.infrastructure.importing.runner import run_import
from apps.core.infrastructure.importing.session_store import (
    create_import_session,
    delete_import_session,
    get_import_session,
    spreadsheet_from_session,
    update_import_session,
)
from apps.core.infrastructure.importing.kit_report import expand_kit_report
from apps.core.infrastructure.importing.spreadsheet import SpreadsheetParseError, parse_uploaded_file
from apps.core.infrastructure.models.data_import import DataImportBatch
from apps.workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm

_ENTITY_LIST_URL_NAMES: dict[str, str] = {
    "customers": "customer:customer_list",
    "suppliers": "suppliers:supplier_list",
    "products": "catalog:product_list",
    "services": "catalog:services_list",
    "kits": "catalog:kits_list",
    "payables": "finance:financial_movement_list",
}


def _list_url_for_entity(entity_key: str) -> str:
    url_name = _ENTITY_LIST_URL_NAMES.get(entity_key)
    if not url_name:
        raise Http404
    return reverse(url_name)


def _delete_codename_for_adapter(adapter: Any) -> str:
    # add_customer -> delete_customer
    codename = str(adapter.permission_codename or "")
    if codename.startswith("add_"):
        return f"delete_{codename[4:]}"
    return f"delete_{adapter.permission_model}"


def _user_can_view_import_history(*, request: Any, workshop: Any, adapter: Any) -> bool:
    return has_workshop_perm(
        user=request.user,
        workshop=workshop,
        app_label=adapter.permission_app_label,
        model=adapter.permission_model,
        codename=adapter.permission_codename,
        request=request,
    ) or has_workshop_perm(
        user=request.user,
        workshop=workshop,
        app_label=adapter.permission_app_label,
        model=adapter.permission_model,
        codename=_delete_codename_for_adapter(adapter),
        request=request,
    )


def _user_can_rollback(*, request: Any, workshop: Any, adapter: Any) -> bool:
    return has_workshop_perm(
        user=request.user,
        workshop=workshop,
        app_label=adapter.permission_app_label,
        model=adapter.permission_model,
        codename=_delete_codename_for_adapter(adapter),
        request=request,
    )


def _mapped_fields(schema: Any, mapping: dict[str, str]) -> list[dict[str, Any]]:
    return [{"field": field, "selected": mapping.get(field.key, "")} for field in schema.fields]


def _preview_table(schema: Any, mapping: dict[str, str], rows: list[dict[str, Any]], *, limit: int = 5) -> dict[str, Any]:
    active_fields = [field for field in schema.fields if mapping.get(field.key)]
    headers = [field.label for field in active_fields]
    preview_rows: list[list[str]] = []
    for row in rows[:limit]:
        cells: list[str] = []
        for field in active_fields:
            source = mapping.get(field.key, "")
            cells.append(str(row.get(source, "") or ""))
        preview_rows.append(cells)
    return {"headers": headers, "rows": preview_rows}


class DataImportBaseView(LoginRequiredMixin, View):
    entity_key: str = ""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        self.entity_key = kwargs.get("entity") or ""
        self.adapter = get_adapter(self.entity_key)
        if self.adapter is None:
            raise Http404("Tipo de importação não encontrado.")

        self.workshop = get_active_workshop_or_404(request)
        if not has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label=self.adapter.permission_app_label,
            model=self.adapter.permission_model,
            codename=self.adapter.permission_codename,
            request=request,
        ):
            raise PermissionDenied

        return View.dispatch(self, request, *args, **kwargs)

    def _session_or_error(self, request: HttpRequest, token: str) -> tuple[dict[str, Any] | None, HttpResponse | None]:
        payload = get_import_session(token)
        if payload is None:
            return None, render(
                request,
                "core/import/modal_step_upload.html",
                {
                    "adapter": self.adapter,
                    "entity_key": self.entity_key,
                    "error": "A sessão de importação expirou. Envie o arquivo novamente.",
                    "show_stock_toggle": self.entity_key == "products",
                },
            )
        if int(payload.get("workshop_id") or 0) != int(self.workshop.pk):
            raise PermissionDenied
        if int(payload.get("user_id") or 0) != int(request.user.pk):
            raise PermissionDenied
        if payload.get("entity_key") != self.entity_key:
            raise Http404
        return payload, None

    def _options_from_request(self, request: HttpRequest) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self.entity_key == "products":
            raw = request.POST.get("include_stock") or request.GET.get("include_stock")
            options["include_stock"] = raw in {"1", "true", "on", "yes"}
        return options


class DataImportModalView(DataImportBaseView):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return render(
            request,
            "core/import/modal_step_upload.html",
            {
                "adapter": self.adapter,
                "entity_key": self.entity_key,
                "show_stock_toggle": self.entity_key == "products",
            },
        )


class DataImportExampleModalView(DataImportBaseView):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        options = self._options_from_request(request)
        schema = self.adapter.get_schema(self.workshop, options=options)
        return render(
            request,
            "core/import/modal_example.html",
            {
                "adapter": self.adapter,
                "entity_key": self.entity_key,
                "schema": schema,
                "example_headers": schema.example_headers,
                "example_rows": schema.example_rows,
                "example_notes": schema.example_notes,
            },
        )


class DataImportUploadView(DataImportBaseView):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        uploaded = request.FILES.get("file")
        options = self._options_from_request(request)
        context = {
            "adapter": self.adapter,
            "entity_key": self.entity_key,
            "show_stock_toggle": self.entity_key == "products",
            "include_stock": options.get("include_stock", False),
        }
        if uploaded is None:
            context["error"] = "Selecione um arquivo .xlsx, .xls ou .csv."
            return render(request, "core/import/modal_step_upload.html", context)

        try:
            spreadsheet = parse_uploaded_file(uploaded, filename=uploaded.name)
        except SpreadsheetParseError as exc:
            context["error"] = str(exc)
            return render(request, "core/import/modal_step_upload.html", context)

        if self.entity_key == "kits":
            spreadsheet = expand_kit_report(spreadsheet)

        schema = self.adapter.get_schema(self.workshop, options=options)
        token = create_import_session(
            entity_key=self.entity_key,
            workshop_id=int(self.workshop.pk),
            user_id=int(request.user.pk),
            spreadsheet=spreadsheet,
            options=options,
        )
        mapping = suggest_mapping(spreadsheet.headers, schema)
        update_import_session(token, mapping=mapping)

        return render(
            request,
            "core/import/modal_step_mapping.html",
            {
                "adapter": self.adapter,
                "entity_key": self.entity_key,
                "token": token,
                "schema": schema,
                "headers": spreadsheet.headers,
                "mapped_fields": _mapped_fields(schema, mapping),
                "filename": spreadsheet.filename,
                "row_count": len(spreadsheet.rows),
                "include_stock": options.get("include_stock", False),
            },
        )


class DataImportConfirmView(DataImportBaseView):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        token = request.POST.get("token") or ""
        payload, error_response = self._session_or_error(request, token)
        if error_response is not None or payload is None:
            return error_response or HttpResponse(status=400)

        options = payload.get("options") or {}
        schema = self.adapter.get_schema(self.workshop, options=options)
        mapping: dict[str, str] = {}
        for import_field in schema.fields:
            selected = (request.POST.get(f"map_{import_field.key}") or "").strip()
            if selected:
                mapping[import_field.key] = selected

        update_import_session(token, mapping=mapping)
        spreadsheet = spreadsheet_from_session(payload)

        return render(
            request,
            "core/import/modal_step_confirm.html",
            {
                "adapter": self.adapter,
                "entity_key": self.entity_key,
                "token": token,
                "mapped_fields": _mapped_fields(schema, mapping),
                "filename": spreadsheet.filename,
                "row_count": len(spreadsheet.rows),
                "preview_table": _preview_table(schema, mapping, spreadsheet.rows),
                "include_stock": bool(options.get("include_stock")),
            },
        )


class DataImportExecuteView(DataImportBaseView):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        token = request.POST.get("token") or ""
        payload, error_response = self._session_or_error(request, token)
        if error_response is not None or payload is None:
            return error_response or HttpResponse(status=400)

        options = payload.get("options") or {}
        mapping = payload.get("mapping") or {}
        spreadsheet = spreadsheet_from_session(payload)
        batch_result = run_import(
            adapter=self.adapter,
            workshop=self.workshop,
            spreadsheet=spreadsheet,
            mapping=mapping,
            user=request.user,
            options=options,
        )
        import_batch = persist_import_batch(
            workshop=self.workshop,
            entity_key=self.entity_key,
            filename=spreadsheet.filename,
            mapping=mapping,
            options=options,
            user=request.user,
            batch_result=batch_result,
        )
        delete_import_session(token)

        error_results = [r for r in batch_result.results if not r.success]
        return render(
            request,
            "core/import/modal_step_result.html",
            {
                "adapter": self.adapter,
                "entity_key": self.entity_key,
                "success_count": batch_result.success_count,
                "error_count": batch_result.error_count,
                "error_results": error_results[:100],
                "error_results_truncated": len(error_results) > 100,
                "import_batch": import_batch,
                "can_rollback": import_batch.can_rollback and _user_can_rollback(request=request, workshop=self.workshop, adapter=self.adapter),
                "history_url": reverse("core:data_import_history") + f"?entity={self.entity_key}",
            },
        )


class DataImportHistoryView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        workshop = get_active_workshop_or_404(request)
        entity_filter = (request.GET.get("entity") or "").strip()
        if not entity_filter or get_adapter(entity_filter) is None:
            raise Http404
        back_url = _list_url_for_entity(entity_filter)
        adapter = get_adapter(entity_filter)
        assert adapter is not None
        if not _user_can_view_import_history(request=request, workshop=workshop, adapter=adapter):
            raise PermissionDenied

        qs = DataImportBatch.objects.filter(workshop=workshop, entity_key=entity_filter).select_related("user")

        visible_batches = []
        for batch in qs[:100]:
            visible_batches.append(
                {
                    "batch": batch,
                    "entity_label": get_entity_label(batch.entity_key),
                    "can_rollback": batch.can_rollback and _user_can_rollback(request=request, workshop=workshop, adapter=adapter),
                }
            )

        return render(
            request,
            "core/import/history_list.html",
            {
                "rows": visible_batches,
                "entity_filter": entity_filter,
                "entity_label": get_entity_label(entity_filter),
                "back_url": back_url,
            },
        )


class DataImportHistoryDetailView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        workshop = get_active_workshop_or_404(request)
        batch = get_object_or_404(DataImportBatch, pk=kwargs["batch_id"], workshop=workshop)
        adapter = get_adapter(batch.entity_key)
        if adapter is None or not _user_can_view_import_history(request=request, workshop=workshop, adapter=adapter):
            raise PermissionDenied

        items = batch.items.all().order_by("row_number", "id")[:200]
        return render(
            request,
            "core/import/history_detail.html",
            {
                "batch": batch,
                "entity_label": get_entity_label(batch.entity_key),
                "items": items,
                "can_rollback": batch.can_rollback and _user_can_rollback(request=request, workshop=workshop, adapter=adapter),
            },
        )


class DataImportRollbackModalView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        workshop = get_active_workshop_or_404(request)
        batch = get_object_or_404(DataImportBatch, pk=kwargs["batch_id"], workshop=workshop)
        adapter = get_adapter(batch.entity_key)
        if adapter is None or not _user_can_rollback(request=request, workshop=workshop, adapter=adapter):
            raise PermissionDenied
        if not batch.can_rollback:
            return render(
                request,
                "core/import/modal_rollback_result.html",
                {
                    "batch": batch,
                    "entity_label": get_entity_label(batch.entity_key),
                    "error": "Esta importação não possui registros ativos para desfazer.",
                },
            )

        plan = build_rollback_plan(batch)
        warning = ""
        if plan.blocked_count:
            warning = (
                f"{plan.blocked_count} registro(s) estão em uso e não serão removidos. "
                "Você pode continuar e desfazer apenas o que for possível."
            )
        return render(
            request,
            "core/import/modal_rollback_confirm.html",
            {
                "batch": batch,
                "entity_label": get_entity_label(batch.entity_key),
                "plan": plan,
                "blocked_preview": plan.blocked[:20],
                "needs_force": bool(plan.blocked_count),
                "warning": warning,
            },
        )


class DataImportRollbackExecuteView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        workshop = get_active_workshop_or_404(request)
        batch = get_object_or_404(DataImportBatch, pk=kwargs["batch_id"], workshop=workshop)
        adapter = get_adapter(batch.entity_key)
        if adapter is None or not _user_can_rollback(request=request, workshop=workshop, adapter=adapter):
            raise PermissionDenied

        force_partial = request.POST.get("force_partial") in {"1", "true", "on", "yes"}
        plan = build_rollback_plan(batch)

        if plan.blocked and not force_partial:
            return render(
                request,
                "core/import/modal_rollback_confirm.html",
                {
                    "batch": batch,
                    "entity_label": get_entity_label(batch.entity_key),
                    "plan": plan,
                    "blocked_preview": plan.blocked[:20],
                    "needs_force": True,
                    "warning": (
                        f"{plan.blocked_count} registro(s) estão em uso e não serão removidos. "
                        "Deseja continuar e desfazer apenas o que for possível?"
                    ),
                },
            )

        try:
            result = execute_rollback(batch, force_partial=force_partial or not plan.blocked)
        except ValueError as exc:
            return render(
                request,
                "core/import/modal_rollback_confirm.html",
                {
                    "batch": batch,
                    "entity_label": get_entity_label(batch.entity_key),
                    "plan": plan,
                    "blocked_preview": plan.blocked[:20],
                    "needs_force": True,
                    "warning": str(exc),
                },
            )

        batch.refresh_from_db()
        return render(
            request,
            "core/import/modal_rollback_result.html",
            {
                "batch": batch,
                "entity_label": get_entity_label(batch.entity_key),
                "result": result,
            },
        )
