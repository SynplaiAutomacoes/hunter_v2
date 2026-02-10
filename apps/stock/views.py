import re
from decimal import Decimal

from crispy_forms.utils import render_crispy_form
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.context_processors import csrf
from django.views import View
from django.views.generic import ListView, FormView, CreateView
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import transaction
from django.db.models import F, ExpressionWrapper, IntegerField
from pynfe.processamento import ComunicacaoSefaz

from .forms import ImportStep1Form, ImportStepSupplierForm, ImportStepItemsForm, ImportStepPaymentForm
from .models import StockProduct, StockMovement, StockPaymentMethod
from .utils import NFParser
from ..catalog.models.products import Product
from ..core.forms import MultiStepFormMixin
from ..core.templatetags.table_tags import TableColumn
from ..core.views import HtmxTemplateResponseMixin
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
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(StockMovement.criado_em.field.verbose_name, attr=StockMovement.criado_em.field.name),
            TableColumn(StockMovement.status.field.verbose_name, attr="get_status_display"),
            TableColumn(StockMovement.type.field.verbose_name, attr="get_type_display"),
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
    workshop_permission_codename = "update_stockmovement"

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

        return redirect('stock:approvals')


class StockImportView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, FormView):
    model = StockProduct
    template_name = "stock/import_form.html"
    workshop_permission_codename = "add_stockproduct"

    def get_object(self, queryset=None):
        return None

    def render_next_step(self, form):
        current_step = self.get_current_step()
        total_steps = len(self.get_steps_config())

        # Se for a última etapa, executamos a persistência
        if current_step == total_steps:
            return self.finalize_import()

        # Caso contrário, usa o comportamento padrão do Mixin
        return super().render_next_step(form)

    def finalize_import(self):
        """ Lógica de persistência final no banco de dados """
        nf_data = self.request.session.get("nf_data")
        messages.success(self.request, "Importação concluída com sucesso!")
        return redirect("stock:movement")

    def get(self, request, *args, **kwargs):
        # Se for HTMX, renderizamos apenas o fragmento da etapa
        if request.htmx:
            form = self.get_form()
            context = self.get_context_data(form=form)
            return render(request, 'stock/partials/import_step_content.html', context)

        # Se não for HTMX (carregamento inicial da página), segue o fluxo normal
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['nf_data'] = self.request.session.get("nf_data", {})
        kwargs['import_items'] = self.request.session.get("import_items", [])
        kwargs['import_payments'] = self.request.session.get("import_payments", [])

        kwargs.pop('instance', None)
        return kwargs

    # Definição dinâmica baseada na escolha do Step 1
    def get_steps_definition(self):
        method = self.request.session.get("import_method", "XML")

        base_steps = [
            {"title": "Método de Importação", "form_class": ImportStep1Form},
        ]

        # if method == "SEFAZ":
        #     base_steps.append({"title": "Seleção de NF", "form_class": ImportSefazListForm})

        base_steps.extend(
            [
                {"title": "Fornecedor", "form_class": ImportStepSupplierForm},
                {"title": "Importar Itens", "form_class": ImportStepItemsForm},
                {"title": "Método de Pagamento", "form_class": ImportStepPaymentForm},
        #         {"title": "Revisão e Confirmação", "form_class": ImportStepSummaryForm},
            ]
        )
        return base_steps

    def form_invalid(self, form):
        if self.request.htmx:
            return render(self.request, 'stock/partials/import_step_content.html', self.get_context_data(form=form))
        return super().form_invalid(form)

    def form_valid(self, form):
        current_step = self.get_current_step()
        nf_data = self.request.session.get("nf_data", {})
        import_items = self.request.session.get("import_items", [])

        # Lógica de persistência em Sessão (Exemplo Step 1)
        if current_step == 1:
            method = form.cleaned_data["method"]
            self.request.session["import_method"] = method

            if method == "XML":
                xml_file = self.request.FILES.get("xml_file")
                nf_data = NFParser.parse_nfe_xml_to_dict(xml_file)

            elif method == "KEY":
                chave = re.sub(r"\D", "", form.cleaned_data.get("access_key"))
                workshop = self.workshop or get_active_workshop_or_404(self.request)

                if not workshop.pfx_certificate or not workshop.certificate_password:
                    error_message = "Oficina sem certificado configurado."
                    messages.error(self.request, error_message)
                    form.add_error("access_key", error_message)
                    return self.form_invalid(form)

                try:
                    comunicacao = ComunicacaoSefaz(workshop.uf, workshop.pfx_certificate.path, workshop.certificate_password)
                    cnpj_clean = re.sub(r"\D", "", workshop.cnpj)
                    xml_response = comunicacao.consulta_distribuicao(cnpj=cnpj_clean, chave=chave)
                    nf_data = NFParser.parse_nfe_xml_to_dict(xml_response.content)
                except Exception as e:
                    form.add_error("access_key", f"Erro na SEFAZ: {str(e)}")
                    return self.form_invalid(form)

            if method in ["XML", "KEY"]:
                if not nf_data:
                    form.add_error(None, "Não foi possível extrair dados desta Nota Fiscal.")
                    return self.form_invalid(form)

                # Persistência em Sessão para as próximas etapas
                self.request.session["nf_data"] = nf_data
                self.request.session["import_items"] = nf_data['items']
                self.request.session["import_payments"] = nf_data['payments']
                self.request.session.modified = True

        elif current_step == 2:
            cnpj = nf_data.get('supplier_cnpj')

            with transaction.atomic():
                supplier, created = Supplier.objects.get_or_create(
                    workshop=self.workshop,
                    cnpj=cnpj,
                    defaults={'name': nf_data.get('supplier_name')}
                )

                nf_data["supplier_id"] = supplier.id
                self.request.session["nf_data"] = nf_data
                self.request.session.modified = True

        elif current_step == 3:
            # Validação
            missing_products = [item.get("desc") for item in import_items
                if not Product.objects.filter(workshop=self.workshop, code=item.get("ref")).exists()]
            if missing_products:
                return self.form_invalid(form)

            # Cadastro
            supplier_id = nf_data.get('supplier_id')
            supplier = Supplier.objects.get(id=supplier_id)

            try:
                with transaction.atomic():
                    for item in import_items:
                        product = Product.objects.get(workshop=self.workshop, code=item.get("ref"))

                        stock_product, created = StockProduct.objects.get_or_create(
                            workshop=self.workshop,
                            product=product,
                            defaults={
                                'supplier': supplier,
                                'last_nf': nf_data.get('nf_number')
                            }
                        )

                        quantity = int(Decimal(str(item.get("qtd", 0))))

                        StockMovement.objects.create(
                            workshop=self.workshop,
                            stock_product=stock_product,
                            type=StockMovement.MovementType.ENTRY,
                            supplier=supplier,
                            transcation_by=self.request.user,
                            quantity=quantity,
                        )

            except Exception as e:
                form.add_error(None, f"Erro ao processar estoque: {str(e)}")
                return self.form_invalid(form)

        return self.render_next_step(form)


def add_payment_session(request):
    workshop = get_active_workshop_or_404(request)
    payments = request.session.get("import_payments", [])

    method_code = request.POST.get("payment_method")
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
    }

    payments.append(new_payment)
    request.session["import_payments"] = payments
    request.session.modified = True

    nf_data = request.session.get("nf_data", {})
    import_items = request.session.get("import_items", {})
    form = ImportStepPaymentForm(nf_data=nf_data, import_payments=payments, import_items=import_items, workshop=workshop)

    ctx = {}
    ctx.update(csrf(request))
    return HttpResponse(render_crispy_form(form, context=ctx))


def remove_payment_session(request, payment_id):
    workshop = get_active_workshop_or_404(request)
    payments = request.session.get("import_payments", [])
    payments = [p for p in payments if p["id"] != int(payment_id)]

    request.session["import_payments"] = payments
    request.session.modified = True

    nf_data = request.session.get("nf_data", {})
    import_items = request.session.get("import_items", {})
    form = ImportStepPaymentForm(nf_data=nf_data, import_payments=payments, import_items=import_items, workshop=workshop)

    ctx = {}
    ctx.update(csrf(request))
    return HttpResponse(render_crispy_form(form, context=ctx))
