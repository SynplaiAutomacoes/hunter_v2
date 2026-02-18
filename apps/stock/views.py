import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, DeleteView
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import transaction
from django.db.models import F, ExpressionWrapper, IntegerField, Q
from djmoney.money import Money

from .forms import ImportStep1Form, ImportStepSupplierForm, ImportStepItemsForm, ImportStepPaymentForm, QuickProductForm, ImportStepSummaryForm, ImportSefazListForm, CatalogGroupQuickForm, ImportStepSupplierManualForm, QuickSupplierForm, ImportManualItemsForm
from .models import StockProduct, StockMovement, StockPaymentMethod, StockImport
from ..catalog.models.groups import CatalogGroup
from ..catalog.models.products import Product
from ..core.forms import MultiStepFormMixin
from ..core.tables import TableActionDefaults
from ..core.templatetags.table_tags import TableColumn
from ..core.views import HtmxTemplateResponseMixin, HtmxDeleteResponseMixin
from ..suppliers.models import Supplier
from ..workshops.mixin import WorkshopScopedMixin
from ..workshops.util.workshops import get_active_workshop_or_404


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(StockImport.nf_number.field.verbose_name, attr=StockImport.nf_number.field.name),
            TableColumn(StockImport.supplier_name.field.verbose_name, attr=StockImport.supplier_name.field.name),
            TableColumn(StockImport.user.field.verbose_name, attr=StockImport.user.field.name),
            TableColumn(StockImport.criado_em.field.verbose_name, attr=StockImport.criado_em.field.name),
            TableColumn(StockImport.status.field.verbose_name, attr="stockimport_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("stock:stock_update"),
            TableActionDefaults.delete("stock:stock_delete"),
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


class AddPaymentSessionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def post(self, request, *args, **kwargs):
        pk = request.GET.get("pk")
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        payments = obj.payments_data

        method_code = request.POST.get("payment_method")
        payment_date = request.POST.get("payment_date")
        first_amount = Decimal(request.POST.get("first_amount_0", "0"))
        installments = Decimal(request.POST.get("installments_count", "1"))
        total_paid = first_amount * installments

        new_payment = {
            "id": len(payments) + 1,
            "method": method_code,
            "method_display": dict(StockPaymentMethod.PAYMENT_METHOD_CHOICES).get(method_code),
            "installments": str(installments),
            "first_amount": str(first_amount),
            "total_paid": str(total_paid),
            "payment_date": payment_date,
        }

        payments.append(new_payment)
        obj.payments_data = payments
        obj.save(update_fields=["payments_data"])

        return HttpResponse(headers={"HX-Refresh": "true"})


class RemovePaymentSessionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def post(self, request, payment_id, *args, **kwargs):
        pk = request.GET.get("pk")
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        payments = [p for p in obj.payments_data if p["id"] != int(payment_id)]

        obj.payments_data = payments
        obj.save(update_fields=["payments_data"])

        return HttpResponse(headers={"HX-Refresh": "true"})


class LinkProductManualView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def get(self, request):
        item_idx = request.GET.get("item_idx")
        pk = request.GET.get("pk")
        is_manual = request.GET.get("manual") == "true"
        context = {"item_idx": item_idx, "workshop": self.workshop, "pk": pk, "is_manual": is_manual}
        return render(request, "stock/partials/modal/link_manual_modal.html", context)

    @transaction.atomic
    def post(self, request):
        raw_item_idx = request.POST.get("item_idx")
        product_id = request.POST.get("product_id")
        pk = request.POST.get("pk")
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
        item_idx = request.POST.get("item_idx") or request.GET.get("item_idx")
        pk = request.POST.get("pk") or request.GET.get("pk")

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
            response = HttpResponse()
            response["HX-Trigger"] = json.dumps({
                    "supplierCreated": {"id": str(self.object.id), "name": self.object.name, "cnpj": self.object.cnpj},
                    "closeModal": True,
            })
            return response

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

        idx = int(item_idx)
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


        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response
