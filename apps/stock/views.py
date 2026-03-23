import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, DeleteView, UpdateView
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import transaction
from django.db import models
from django.db.models import F, ExpressionWrapper, IntegerField, Q
from djmoney.money import Money

from .forms import (
    ImportManualItemsForm,
    ImportSefazListForm,
    ImportStep1Form,
    ImportStepItemsForm,
    ImportStepPaymentForm,
    ImportStepSummaryForm,
    ImportStepSupplierForm,
    ImportStepSupplierManualForm,
    QuickProductForm,
    QuickSupplierForm,
    CatalogGroupQuickForm,
    TransferItemsForm,
    TransferStepWorkshopsForm,
    TransferSummaryForm,
)
from .models import StockImport, StockMovement, StockProduct, StockTransfer
from ..catalog.models.groups import CatalogGroup
from ..catalog.models.products import Product
from ..core.forms import MultiStepFormMixin
from ..core.tables import TableActionDefaults
from ..core.templatetags.table_tags import TableColumn
from ..core.utils import clean_id
from ..core.views import HtmxTemplateResponseMixin, HtmxDeleteResponseMixin
from ..finance.models.payment_method import PaymentMethod
from ..suppliers.models import Supplier
from ..workshops.mixin import WorkshopScopedMixin
from ..workshops.models.workshops import Workshop
from ..workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm


@dataclass(frozen=True)
class StockHistoryRow:
    pk: int
    record_type: str
    id: int
    nf_number: str
    supplier_name: str
    user: object
    criado_em: object
    history_status_badge: dict[str, str]

    @property
    def record_edit_url(self) -> str:
        return reverse("stock:history_edit", kwargs={"record_type": self.record_type, "pk": self.pk})


class StockAlertsListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockProduct
    template_name = "stock/alerts.html"
    context_object_name = "alerts"
    workshop_permission_codename = "view_stockproduct"

    def get_queryset(self):
        return StockProduct.objects.filter(workshop=self.workshop, current_quantity__lt=F("minimum_quantity")).select_related("product")


class StockMovementListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = StockMovement
    template_name = "stock/movement.html"
    context_object_name = "movements"
    workshop_permission_codename = "view_stockmovement"
    paginate_by = 20
    htmx_template_name = "stock/partials/movement_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("stock_product__product", "supplier").order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(StockMovement.criado_em.field.verbose_name, attr=StockMovement.criado_em.field.name),
            TableColumn(StockMovement.status.field.verbose_name, attr="stockmovement_status_badge", format="status_badge"),
            TableColumn(StockMovement.type.field.verbose_name, attr="stockmovement_type_badge", format="status_badge"),
            TableColumn(StockMovement.stock_product.field.verbose_name, attr="get_product_reference"),
            TableColumn(StockMovement.quantity.field.verbose_name, attr=StockMovement.quantity.field.name),
            TableColumn("Localização", attr="location"),
            TableColumn(StockMovement.supplier.field.verbose_name, attr=StockMovement.supplier.field.name),
        ]
        return context


class ReplenishmentListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockProduct
    template_name = "stock/replenish.html"
    context_object_name = "items"
    workshop_permission_codename = "view_stockproduct"

    def get_queryset(self):
        suggested_order_calc = ExpressionWrapper(F("restock_quantity") - F("current_quantity"), output_field=IntegerField())
        return StockProduct.objects.filter(workshop=self.workshop).annotate(suggested_order=suggested_order_calc).filter(suggested_order__gt=0)


class MovementApprovalListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockMovement
    template_name = "stock/approvals.html"
    context_object_name = "pending_movements"
    workshop_permission_codename = "view_stockmovement"

    def get_queryset(self):
        return StockMovement.objects.filter(workshop=self.workshop, status=StockMovement.MovementStatus.WAITING)


class MovementApprovalActionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockMovement
    workshop_permission_codename = "change_stockmovement"

    def post(self, request, pk):
        workshop = self.workshop
        movement = get_object_or_404(StockMovement, pk=pk, workshop=workshop)
        action = request.POST.get("action")

        if movement.status != StockMovement.MovementStatus.WAITING:
            messages.error(request, "Esta movimentação já foi processada.")
            return redirect("stock:approvals")

        try:
            with transaction.atomic():
                if action == "approve":
                    product = movement.stock_product
                    if movement.type == StockMovement.MovementType.ENTRY:
                        product.current_quantity += movement.quantity
                    else:
                        product.current_quantity -= movement.quantity
                    product.save()
                    movement.status = StockMovement.MovementStatus.APPROVED
                    messages.success(request, "Movimentação aprovada com sucesso.")
                else:
                    movement.status = StockMovement.MovementStatus.REJECTED
                    messages.warning(request, "Movimentação rejeitada.")
                movement.save()
        except Exception as e:
            messages.error(request, f"Erro: {str(e)}")

        return redirect("stock:approvals")


class StockImportListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = StockImport
    template_name = "stock/stock_list.html"
    context_object_name = "stock"
    htmx_template_name = "stock/partials/stock_table.html"
    workshop_permission_codename = "view_stockimport"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def _build_history_rows(self) -> list[StockHistoryRow]:
        imports = [
            StockHistoryRow(
                pk=stock_import.pk,
                record_type="import",
                id=stock_import.pk,
                nf_number=stock_import.nf_number or stock_import.nf_number_display or "---",
                supplier_name=stock_import.supplier_name or "---",
                user=stock_import.user,
                criado_em=stock_import.criado_em,
                history_status_badge=stock_import.stockimport_status_badge,
            )
            for stock_import in self.get_queryset().select_related("user")
        ]

        transfers_queryset = StockTransfer.objects.filter(Q(source_workshop=self.workshop) | Q(destination_workshop=self.workshop)).select_related("user", "source_workshop", "destination_workshop").order_by("-criado_em")
        transfers = [
            StockHistoryRow(
                pk=transfer.pk,
                record_type="transfer",
                id=transfer.pk,
                nf_number="TRANSFERENCIA",
                supplier_name=f"{transfer.source_workshop.name} -> {transfer.destination_workshop.name}",
                user=transfer.user,
                criado_em=transfer.criado_em,
                history_status_badge=transfer.stocktransfer_status_badge,
            )
            for transfer in transfers_queryset
        ]

        return sorted([*imports, *transfers], key=lambda row: row.criado_em, reverse=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stock"] = self._build_history_rows()
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(StockImport.nf_number.field.verbose_name, attr="nf_number"),
            TableColumn(StockImport.supplier_name.field.verbose_name, attr="supplier_name"),
            TableColumn(StockImport.user.field.verbose_name, attr="user"),
            TableColumn(StockImport.criado_em.field.verbose_name, attr="criado_em"),
            TableColumn(StockImport.status.field.verbose_name, attr="history_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit(url_name="stock:history_edit", args=(), kwargs={"record_type": "record_type", "pk": "pk"}),
        ]
        return context


class StockImportCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = StockImport
    template_name = "stock/import_form.html"
    workshop_permission_codename = "add_stockimport"

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.htmx:
            return ["stock/partials/import_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.request.GET.get("pk") or self.kwargs.get("pk")
        if pk:
            return get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        obj = self.get_object()
        kwargs.update(
            {
                "request": self.request,
                "workshop": self.workshop,
                "instance": obj,
            }
        )
        if obj:
            kwargs.update(
                {
                    "nf_data": {"nf_number": obj.nf_number, "supplier_name": obj.supplier_name},
                    "import_items": obj.items_data,
                    "import_payments": obj.payments_data,
                }
            )
        return kwargs

    def get_steps_definition(self):
        obj = self.get_object()

        base_steps = [
            {"title": "Método de Importação", "form_class": ImportStep1Form},
        ]

        if obj:
            if obj.method == "SEFAZ":
                base_steps.append({"title": "Seleção de NF", "form_class": ImportSefazListForm})

            if obj.method == "MANUAL":
                base_steps.extend(
                    [
                        {"title": "Fornecedor", "form_class": ImportStepSupplierManualForm},
                        {"title": "Importar Itens", "form_class": ImportManualItemsForm},
                    ]
                )
            else:
                # XML/KEY/SEFAZ
                base_steps.extend(
                    [
                        {"title": "Fornecedor", "form_class": ImportStepSupplierForm},
                        {"title": "Importar Itens", "form_class": ImportStepItemsForm},
                    ]
                )

        base_steps.extend(
            [
                {"title": "Método de Pagamento", "form_class": ImportStepPaymentForm},
                {"title": "Revisão e Confirmação", "form_class": ImportStepSummaryForm},
            ]
        )
        return base_steps

    def get_success_url(self):
        return reverse("stock:stock_list")

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        self.object = form.save()

        current_step = self.get_current_step()
        steps_config = self.get_steps_config()
        total_steps = len(steps_config)

        if hasattr(self.object, "current_step"):
            next_step_value = current_step + 1
            if self.object.current_step < next_step_value:
                self.object.current_step = next_step_value
                self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            next_step = current_step + 1
            success_url = f"{self.request.path}?step={next_step}&pk={self.object.pk}"
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class StockImportUpdateView(StockImportCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('stock:stock_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect("stock:stock_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return StockImport.objects.get(pk=pk, workshop=self.workshop)
        return super().get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        self.object = form.save()

        current_step = self.get_current_step()
        steps_config = self.get_steps_config()
        total_steps = len(steps_config)

        if hasattr(self.object, "current_step"):
            next_step_value = current_step + 1
            if self.object.current_step < next_step_value:
                self.object.current_step = next_step_value
                self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            next_step = current_step + 1
            success_url = f"{reverse('stock:stock_update', kwargs={'pk': self.object.pk})}?step={next_step}"
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class RefreshSefazListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "view_stockimport"

    def post(self, request, pk):
        stock_import = get_object_or_404(StockImport, pk=pk, workshop=self.workshop)
        if stock_import.method != StockImport.ImportMethods.SEFAZ:
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {
                        "type": "warning",
                        "message": "A atualização da SEFAZ só está disponível quando o método de importação é SEFAZ.",
                    }
                }
            )
            return response

        form = ImportSefazListForm(instance=stock_import, workshop=self.workshop, request=request)
        success, message = form.update_sefaz_list()

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {
                    "type": "success" if success else "warning",
                    "message": message,
                },
                "sefaz-list-refresh": {},
            }
        )
        return response


class StockImportDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = StockImport
    success_url = reverse_lazy("stock:stock_list")
    workshop_permission_codename = "delete_stockimport"

    htmx_template_name = "stock/partials/stock_delete_modal.html"
    htmx_trigger = "stock-table-refresh"


class StockHistoryEditRedirectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "view_stockimport"

    def get(self, request, record_type, pk):
        if record_type == "import":
            get_object_or_404(StockImport, pk=pk, workshop=self.workshop)
            return redirect("stock:stock_update", pk=pk)

        if record_type == "transfer":
            get_object_or_404(StockTransfer, Q(source_workshop=self.workshop) | Q(destination_workshop=self.workshop), pk=pk)
            return redirect("stock:transfer_update", pk=pk)

        raise PermissionDenied


class AddPaymentSessionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    @staticmethod
    def _htmx_payment_response(message: str, *, level: str = "info", refresh_step: bool = False, status: int = 204) -> HttpResponse:
        trigger: dict[str, object] = {
            "showToast": {
                "type": level,
                "message": message,
            }
        }
        if refresh_step:
            trigger["productCreated"] = {}

        response = HttpResponse(status=status)
        response["HX-Trigger"] = json.dumps(trigger)
        return response

    def post(self, request, *args, **kwargs):
        pk = request.GET.get("pk")
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)

        method_code = (request.POST.get("payment_method") or "").strip()
        payment_date = (request.POST.get("payment_date") or "").strip()
        first_amount_str = (request.POST.get("first_amount_0") or "").strip()
        installments_str = (request.POST.get("installments_count") or "").strip()

        if not all([method_code, payment_date, installments_str, first_amount_str]):
            return self._htmx_payment_response("Preencha todos os campos do pagamento antes de incluir.", level="warning")

        try:
            first_amount = Decimal(first_amount_str.replace(",", "."))
            installments = int(installments_str)
            if first_amount <= 0 or installments <= 0:
                return self._htmx_payment_response("Informe valores válidos para o pagamento.", level="warning")

            method_obj = PaymentMethod.objects.filter(id=method_code, workshop=self.workshop, is_active=True).first()
            if not method_obj:
                return self._htmx_payment_response("A forma de pagamento selecionada é inválida.", level="warning")

            total_paid = first_amount * installments

            valor_total_nf = sum(Decimal(str(item.get("valor", 0))) * Decimal(str(item.get("qtd", 0))) for item in obj.items_data)
            valor_ja_pago = sum(Decimal(str(p.get("total_paid", 0))) for p in obj.payments_data)
            valor_disponivel = valor_total_nf - valor_ja_pago

            if total_paid > valor_disponivel:
                return self._htmx_payment_response(f"O valor informado (R$ {total_paid}) excede o saldo pendente (R$ {valor_disponivel}).", level="warning")

            payments = list(obj.payments_data or [])
            new_payment = {
                "id": len(payments) + 1,
                "method": method_obj.id,
                "method_display": method_obj.description,
                "installments": str(installments),
                "first_amount": str(first_amount),
                "total_paid": str(total_paid),
                "payment_date": payment_date,
            }

            payments.append(new_payment)
            obj.payments_data = payments
            obj.save(update_fields=["payments_data"])

            return self._htmx_payment_response("Pagamento incluído com sucesso.", level="success", refresh_step=True)
        except (InvalidOperation, ValueError):
            return self._htmx_payment_response("Informe valores válidos para o pagamento.", level="warning")
        except Exception:
            return self._htmx_payment_response("Erro ao processar valores do pagamento.", level="error")


class RemovePaymentSessionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def post(self, request, payment_id, *args, **kwargs):
        pk = request.GET.get("pk")
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        payments = [p for p in obj.payments_data if p["id"] != int(payment_id)]

        obj.payments_data = payments
        obj.save(update_fields=["payments_data"])
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"productCreated": {}})
        return response


class LinkProductManualView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def get(self, request):
        item_idx = clean_id(request.GET.get("item_idx"))
        pk = clean_id(request.GET.get("pk"))
        is_manual = request.GET.get("manual") == "true"
        context = {"item_idx": item_idx, "workshop": self.workshop, "pk": pk, "is_manual": is_manual}
        return render(request, "stock/partials/modal/link_manual_modal.html", context)

    @transaction.atomic
    def post(self, request):
        raw_item_idx = clean_id(request.POST.get("item_idx"))
        product_id = clean_id(request.POST.get("product_id"))
        pk = clean_id(request.POST.get("pk"))

        is_manual = request.GET.get("manual") == "true" or request.POST.get("manual") == "true"

        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        product = get_object_or_404(Product, id=product_id, workshop=self.workshop)
        import_items = list(obj.items_data)

        if is_manual:
            new_item = {"ref": product.code, "desc": product.name, "qtd": 1, "valor": str(product.cost_price.amount), "linked_product_id": str(product_id)}
            import_items.append(new_item)
        else:
            try:
                item_idx = int(raw_item_idx)
                if 0 <= item_idx < len(import_items):
                    import_items[item_idx]["linked_product_id"] = product_id
            except (ValueError, TypeError):
                return HttpResponse("Índice de item inválido", status=400)

        obj.items_data = import_items
        obj.save(update_fields=["items_data"])

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class UnlinkItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))

        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        import_items = obj.items_data

        try:
            idx = int(item_idx)
            if 0 <= idx < len(import_items):
                if obj.method == StockImport.ImportMethods.MANUAL:
                    import_items.pop(idx)
                else:
                    # Se for XML/SEFAZ/KEY, apenas limpamos o vínculo
                    import_items[idx]["linked_product_id"] = None

                obj.items_data = import_items
                obj.save(update_fields=["items_data"])
        except (ValueError, TypeError, IndexError):
            return HttpResponse("Erro ao processar índice do item", status=400)

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class StockProductSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Product
    workshop_permission_codename = "view_product"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")

        qs = Product.objects.filter(workshop=self.workshop, is_active=True)
        if query:
            qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query))

        # Otimização com .only() incluindo os campos de moeda do djmoney
        qs = qs.order_by("name").only("id", "code", "name", "brand", "cost_price", "cost_price_currency", "selling_price", "selling_price_currency")

        paginator = Paginator(qs, 10)  # Menor quantidade para caber no modal
        page_obj = paginator.get_page(page)

        return render(
            request,
            "stock/partials/product_search_results.html",
            {
                "products": page_obj.object_list,
                "page_obj": page_obj,
                "query": query,
            },
        )


class ProductQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Product
    form_class = QuickProductForm
    template_name = "stock/partials/modal/product_quick_create_modal.html"
    workshop_permission_codename = "add_product"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_idx"] = self.request.GET.get("item_idx")
        context["pk_import"] = self.request.GET.get("pk")
        return context

    def get_initial(self):
        initial = super().get_initial()
        price_raw = self.request.GET.get("price")

        cost_money = None
        if price_raw:
            try:
                clean_price = Decimal(price_raw.replace(",", "."))
                cost_money = Money(clean_price, "BRL")
            except (InvalidOperation, ValueError):
                pass

        initial.update(
            {
                "code": self.request.GET.get("ref"),
                "name": self.request.GET.get("desc"),
                "cost_price": cost_money,
            }
        )
        return initial

    def form_valid(self, form):
        """Salva o produto e retorna o trigger HTMX."""
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        item_idx = self.request.GET.get("item_idx")
        import_pk = self.request.GET.get("pk")

        if item_idx is not None and import_pk:
            try:
                stock_import = get_object_or_404(StockImport, id=import_pk, workshop=self.workshop)

                items = list(stock_import.items_data)
                idx = int(item_idx)

                if 0 <= idx < len(items):
                    items[idx]["linked_product_id"] = str(self.object.id)
                    stock_import.items_data = items
                    stock_import.save(update_fields=["items_data"])
            except (ValueError, IndexError):
                pass

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class CatalogGroupQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = CatalogGroup
    form_class = CatalogGroupQuickForm
    template_name = "stock/partials/modal/group_quick_create_modal.html"
    workshop_permission_codename = "add_cataloggroup"

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps({"groupAdded": {"id": str(self.object.id), "name": self.object.name}})
        return response


class SupplierDetailsView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Supplier
    workshop_permission_codename = "view_supplier"

    def get(self, request):
        supplier_id = request.GET.get("supplier_select")
        if not supplier_id:
            return HttpResponse('<div class="text-center opacity-50 py-10">Selecione um fornecedor para ver os detalhes.</div>')

        supplier = get_object_or_404(Supplier, id=supplier_id, workshop=self.workshop)

        # Histórico de compras
        history = StockImport.objects.filter(workshop=self.workshop, supplier_cnpj=supplier.cnpj, status=StockImport.ImportStatus.COMPLETED).order_by("-criado_em")[:3]

        history_html = ""
        for imp in history:
            history_html += f"""<tr class="text-sm">
                    <td>#{imp.id or "---"}</td>
                    <td class="py-2">{imp.criado_em.strftime("%d/%m/%Y")}</td>
                    <td>{imp.nf_number or "---"}</td>
                    <td>
                        <a href="{reverse("stock:stock_update", kwargs={"pk": imp.id})}" title="Acessar Importação" class="btn btn-ghost btn-sm btn-circle">
                            <span class="material-icons !text-sm">visibility</span>
                        </a>
                    </td>
            </tr>"""

        if not history:
            history_html = '<tr><td colspan="3" class="text-center py-4 opacity-50 italic">Sem histórico.</td></tr>'

        # Tabelas
        html = f"""
        <div class="animate-in fade-in slide-in-from-right-4 duration-300 space-y-4">
        
            <div class="card bg-base-300 shadow-sm p-4">
                <h4 class="text-base font-bold uppercase mb-3">Contato e Localização</h4>
                <div class="space-y-1 text-base">
                    <p class="flex justify-between">
                        <span>Responsável:</span>
                        <span class="font-medium text-right">{supplier.contact_person or "---"}</span>
                    </p>
                    <p class="flex justify-between">
                        <span>Telefone:</span>
                        <span class="font-medium text-right">{supplier.phone or "---"}</span>
                    </p>
                    <p class="flex justify-between">
                        <span>E-mail:</span>
                        <span class="font-medium text-right lowercase">{supplier.email or "---"}</span>
                    </p>
                    <div class="mt-2 pt-2 border-t border-base-100">
                        <p class="text-[11px] leading-tight opacity-70 italic">Endereço: {supplier.full_address}</p>
                    </div>
                </div>
            </div>

            <div class="card bg-base-300 shadow-sm p-4">
                <h4 class="text-base font-bold uppercase mb-3">Histórico Recente</h4>
                <table class="table table-xs w-full">
                    <thead>
                        <tr class="opacity-50 text-[9px]">
                            <th>ID</th>
                            <th>DATA</th>
                            <th>NF</th>
                            <th>AÇÕES</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history_html}
                    </tbody>
                </table>
            </div>

        </div>
        """

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({"update-supplier-info": {"name": supplier.name, "cnpj": supplier.cnpj}})
        return response


class SupplierQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Supplier
    form_class = QuickSupplierForm
    template_name = "stock/partials/modal/supplier_quick_create_modal.html"
    workshop_permission_codename = "add_supplier"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        if self.request.headers.get("HX-Request"):
            return HttpResponse(headers={"HX-Refresh": "true"})

        return super().form_valid(form)


class SupplierQuickUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Supplier
    form_class = QuickSupplierForm
    template_name = "stock/partials/modal/supplier_quick_update_modal.html"
    workshop_permission_codename = "change_supplier"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        if self.request.headers.get("HX-Request"):
            return HttpResponse(headers={"HX-Refresh": "true"})

        return super().form_valid(form)


class UpdateManualItemDataView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    @transaction.atomic
    def post(self, request, pk):
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        item_idx = request.POST.get("item_idx")

        if item_idx is None:
            return HttpResponse(status=400)

        try:
            idx = int(item_idx)
        except (TypeError, ValueError):
            return HttpResponse(status=400)

        items = list(obj.items_data)

        if 0 <= idx < len(items):
            new_qty = request.POST.get(f"items_qty_{idx}")
            if new_qty is not None:
                try:
                    items[idx]["qtd"] = str(Decimal(new_qty.replace(",", ".")))
                except (InvalidOperation, ValueError):
                    pass

            new_val = request.POST.get(f"items_price_{idx}_0")
            if new_val is not None:
                try:
                    items[idx]["valor"] = str(Decimal(new_val.replace(",", ".")))
                except (InvalidOperation, ValueError):
                    pass

            obj.items_data = items
            obj.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


def _get_user_transfer_workshops(request) -> models.QuerySet[Workshop]:
    return Workshop.objects.filter(account_id=request.user.account_id, is_active=True, members__user=request.user, members__is_active=True).distinct().order_by("name")


class StockTransferAccessMixin(LoginRequiredMixin):
    active_workshop: Workshop

    def dispatch(self, request, *args, **kwargs):
        self.active_workshop = get_active_workshop_or_404(request)
        if not has_workshop_perm(
            user=request.user,
            workshop=self.active_workshop,
            app_label="stock",
            model="stockmovement",
            codename="change_stockmovement",
            request=request,
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_allowed_workshops(self):
        return _get_user_transfer_workshops(self.request)

    def get_allowed_workshop(self, workshop_id):
        if not workshop_id:
            return None
        try:
            workshop_id = int(workshop_id)
        except (TypeError, ValueError):
            return None
        return self.get_allowed_workshops().filter(pk=workshop_id).first()


class StockTransferCreateView(StockTransferAccessMixin, MultiStepFormMixin, CreateView):
    model = StockTransfer
    template_name = "stock/transfer_form.html"
    step_template_name = "stock/partials/transfer_step_content.html"

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return ["stock/partials/transfer_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.request.GET.get("pk") or self.kwargs.get("pk")
        if pk:
            return get_object_or_404(StockTransfer, id=pk)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        obj = self.get_object()
        kwargs.update({"request": self.request, "instance": obj})
        if self.get_form_class() is TransferStepWorkshopsForm:
            kwargs["allowed_workshops"] = self.get_allowed_workshops()
        return kwargs

    def get_steps_definition(self):
        transfer_object = getattr(self, "object", None) or self.get_object()
        base_steps = [{"title": "Origem e Destino", "form_class": TransferStepWorkshopsForm}]
        if transfer_object:
            base_steps.extend(
                [
                    {"title": "Itens da Transferência", "form_class": TransferItemsForm},
                    {"title": "Revisão e Confirmação", "form_class": TransferSummaryForm},
                ]
            )
        return base_steps

    def get_success_url(self):
        return reverse("stock:stock_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()

        current_step = self.get_current_step()
        total_steps = len(self.get_steps_config())

        next_step_value = current_step + 1
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            success_url = f"{reverse('stock:transfer_update', kwargs={'pk': self.object.pk})}?step={current_step + 1}"
        else:
            success_url = self.get_success_url()

        if getattr(self.request, "htmx", False):
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class StockTransferUpdateView(StockTransferCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('stock:transfer_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if pk:
            return get_object_or_404(StockTransfer, pk=pk)
        return None

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()

        current_step = self.get_current_step()
        total_steps = len(self.get_steps_config())

        next_step_value = current_step + 1
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            success_url = f"{reverse('stock:transfer_update', kwargs={'pk': self.object.pk})}?step={current_step + 1}"
        else:
            success_url = self.get_success_url()

        if getattr(self.request, "htmx", False):
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class TransferSourceProductPickerView(StockTransferAccessMixin, View):
    def get(self, request):
        pk = clean_id(request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        context = {"pk": transfer.pk, "source_workshop": transfer.source_workshop}
        return render(request, "stock/partials/modal/transfer_source_picker_modal.html", context)


class TransferSourceProductSearchView(StockTransferAccessMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")
        source_workshop = self.get_allowed_workshop(request.GET.get("source_workshop"))
        if source_workshop is None:
            return HttpResponse("<tr><td colspan='4' class='text-center py-4 opacity-50'>Selecione uma oficina de origem válida.</td></tr>")

        qs = Product.objects.filter(workshop=source_workshop, is_active=True, stock_products__current_quantity__gt=0)
        if query:
            qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query))

        qs = qs.select_related("stock_products").order_by("name").only("id", "code", "name", "brand", "cost_price", "cost_price_currency", "stock_products__current_quantity")
        paginator = Paginator(qs, 10)
        page_obj = paginator.get_page(page)
        return render(request, "stock/partials/transfer_source_search_results.html", {"products": page_obj.object_list, "page_obj": page_obj, "query": query, "source_workshop": source_workshop.pk})


class AddTransferSourceItemView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        product_id = clean_id(request.POST.get("product_id"))
        pk = clean_id(request.POST.get("pk"))
        raw_quantity = request.POST.get("quantity") or "1"
        transfer = get_object_or_404(StockTransfer, pk=pk)
        source_product = get_object_or_404(Product, id=product_id, workshop=transfer.source_workshop)
        items = list(transfer.items_data)

        try:
            quantity = max(1, int(Decimal(str(raw_quantity).replace(",", "."))))
        except (InvalidOperation, ValueError):
            quantity = 1

        for item in items:
            if str(item.get("source_product_id")) == str(source_product.id):
                item["qtd"] = quantity
                response = HttpResponse("")
                response["HX-Trigger"] = "productCreated"
                return response

        items.append(
            {
                "source_product_id": str(source_product.id),
                "destination_product_id": None,
                "qtd": quantity,
                "valor": str(source_product.cost_price.amount),
            }
        )
        transfer.items_data = items
        transfer.save(update_fields=["items_data"])

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class TransferDestinationLinkView(StockTransferAccessMixin, View):
    def get(self, request):
        item_idx = clean_id(request.GET.get("item_idx"))
        pk = clean_id(request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        context = {"item_idx": item_idx, "pk": transfer.pk, "destination_workshop": transfer.destination_workshop}
        return render(request, "stock/partials/modal/transfer_destination_link_modal.html", context)

    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx"))
        product_id = clean_id(request.POST.get("product_id"))
        pk = clean_id(request.POST.get("pk"))

        transfer = get_object_or_404(StockTransfer, pk=pk)
        destination_product = get_object_or_404(Product, id=product_id, workshop=transfer.destination_workshop)
        items = list(transfer.items_data)

        try:
            idx = int(item_idx)
            if 0 <= idx < len(items):
                items[idx]["destination_product_id"] = str(destination_product.id)
        except (TypeError, ValueError):
            return HttpResponse("Índice inválido.", status=400)

        transfer.items_data = items
        transfer.save(update_fields=["items_data"])
        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class TransferDestinationProductSearchView(StockTransferAccessMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")
        destination_workshop = self.get_allowed_workshop(request.GET.get("destination_workshop"))
        if destination_workshop is None:
            return HttpResponse("<tr><td colspan='3' class='text-center py-4 opacity-50'>Selecione uma oficina de destino válida.</td></tr>")

        qs = Product.objects.filter(workshop=destination_workshop, is_active=True)
        if query:
            qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query))

        qs = qs.order_by("name").only("id", "code", "name", "brand", "cost_price", "cost_price_currency", "selling_price", "selling_price_currency")
        paginator = Paginator(qs, 10)
        page_obj = paginator.get_page(page)
        return render(request, "stock/partials/transfer_destination_search_results.html", {"products": page_obj.object_list, "page_obj": page_obj, "query": query, "destination_workshop": destination_workshop.pk})


class CreateTransferDestinationProductView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        items = list(transfer.items_data)

        try:
            idx = int(item_idx)
            item = items[idx]
        except (TypeError, ValueError, IndexError):
            return HttpResponse("Índice inválido.", status=400)

        source_product = get_object_or_404(Product, id=item.get("source_product_id"), workshop=transfer.source_workshop)
        destination_group, _ = CatalogGroup.objects.get_or_create(workshop=transfer.destination_workshop, name=source_product.group.name)
        destination_product = Product.objects.filter(workshop=transfer.destination_workshop, code=source_product.code).first()
        if destination_product is None:
            destination_product = Product.objects.create(
                workshop=transfer.destination_workshop,
                code=source_product.code,
                name=source_product.name,
                description=source_product.description,
                unit=source_product.unit,
                group=destination_group,
                brand=source_product.brand,
                model=source_product.model,
                sku=source_product.sku,
                barcode=source_product.barcode,
                location=source_product.location,
                cost_price=source_product.cost_price,
                selling_price=source_product.selling_price,
                profit_margin=source_product.profit_margin,
                ncm=source_product.ncm,
                cest=source_product.cest,
                origin_cst=source_product.origin_cst,
                purpose=source_product.purpose,
                application=source_product.application,
                is_active=source_product.is_active,
            )

        items[idx]["destination_product_id"] = str(destination_product.id)
        transfer.items_data = items
        transfer.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


class TransferUnlinkDestinationView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        items = list(transfer.items_data)

        try:
            idx = int(item_idx)
            items[idx]["destination_product_id"] = None
        except (TypeError, ValueError, IndexError):
            return HttpResponse("Índice inválido.", status=400)

        transfer.items_data = items
        transfer.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


class RemoveTransferItemView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        source_product_id = clean_id(request.POST.get("source_product_id") or request.GET.get("source_product_id"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        items = list(transfer.items_data)

        if source_product_id is not None:
            items = [item for item in items if str(item.get("source_product_id")) != str(source_product_id)]
        else:
            try:
                idx = int(item_idx)
                items.pop(idx)
            except (TypeError, ValueError, IndexError):
                return HttpResponse("Índice inválido.", status=400)

        transfer.items_data = items
        transfer.save(update_fields=["items_data"])
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


class UpdateTransferItemDataView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        transfer = get_object_or_404(StockTransfer, id=pk)
        item_idx = request.POST.get("item_idx")
        source_product_id = request.POST.get("source_product_id")
        if item_idx is None and source_product_id is None:
            return HttpResponse(status=400)

        items = list(transfer.items_data)
        target_item = None
        field_name = None

        if source_product_id is not None:
            field_name = f"source_qty_{source_product_id}"
            target_item = next((item for item in items if str(item.get("source_product_id")) == str(source_product_id)), None)
        else:
            try:
                idx = int(item_idx)
            except (TypeError, ValueError):
                return HttpResponse(status=400)
            if 0 <= idx < len(items):
                target_item = items[idx]
                field_name = f"items_qty_{idx}"

        if target_item is not None and field_name is not None:
            new_qty = request.POST.get(field_name)
            if new_qty is not None:
                try:
                    target_item["qtd"] = max(1, int(Decimal(new_qty.replace(",", "."))))
                except (InvalidOperation, ValueError):
                    pass

            transfer.items_data = items
            transfer.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response
