import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView

from apps.budget.forms import BudgetItemEditForm, BudgetStep1Form, BudgetStep2Form, BudgetStep3Form, BudgetStep4Form, BudgetStep5Form, BudgetStep6Form, LocalServiceForm, LocalProductForm
from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.budget.utils import HtmxResponseHelper
from apps.budget.fields import DurationField
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.customer.models import Customer, Vehicle
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.util.workshops import get_active_workshop_or_404


class BudgetListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Budget
    template_name = "budget/budget_list.html"
    context_object_name = "budget"
    htmx_template_name = "budget/partials/budget_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(Budget.customer.field.verbose_name, attr=Budget.customer.field.name),
            TableColumn(Budget.vehicle.field.verbose_name, attr=Budget.vehicle.field.name),
            TableColumn(Budget.collaborator.field.verbose_name, attr="collaborator_name"),
            TableColumn(Budget.criado_em.field.verbose_name, attr=Budget.criado_em.field.name),
            TableColumn("Valor Total", attr="total_budget_value"),
            TableColumn(Budget.status.field.verbose_name, attr="budget_status"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("budget:budget_update"),
            TableActionDefaults.delete("budget:budget_delete"),
        ]
        return context


class BudgetCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = Budget
    template_name = "budget/budget_form.html"

    steps_definition = [
        {"title": "Dados do Cliente", "form_class": BudgetStep1Form},
        {"title": "Relato do Cliente", "form_class": BudgetStep2Form},
        {"title": "Diagnóstico", "form_class": BudgetStep3Form},
        {"title": "Peças e Serviços", "form_class": BudgetStep4Form},
        {"title": "Método de Precificação", "form_class": BudgetStep5Form},
        {"title": "Revisão e Confirmação", "form_class": BudgetStep6Form},
    ]

    def get(self, request, *args, **kwargs):
        today = timezone.now()
        if not WorkshopCost.objects.filter(workshop=self.workshop, month=today.month, year=today.year).exists():
            messages.warning(request, "Cadastre um custo mensal da oficina para este mês antes de prosseguir.")
            return redirect("budget:budget_list")

        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.htmx:
            return ["budget/partials/budget_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if pk:
            return Budget.objects.get(pk=pk, workshop=self.workshop)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["workshop"] = self.workshop
        kwargs["instance"] = self.get_object()
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user

        self.object = form.save()  # Salva o progresso atual

        current_step = self.get_current_step()
        if self.object.current_step < current_step + 1:
            self.object.current_step = current_step + 1
            self.object.save(update_fields=["current_step"])

        if current_step < len(self.steps_definition):
            next_step = current_step + 1
            success_url = f"{reverse('budget:budget_create')}?step={next_step}&pk={self.object.pk}"

            if self.request.htmx:
                response = redirect(success_url)
                response["HX-Push-Url"] = success_url
                return response

            return redirect(success_url)

        return super().form_valid(form)


class BudgetUpdateView(BudgetCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if not self.budget_object:
            return redirect("budget:budget_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return Budget.objects.get(pk=pk)
        return super().get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        # Mantemos a lógica de salvar o workshop e colaborador
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user
        self.object = form.save()

        current_step = self.get_current_step()

        # Lógica de progressão de etapa (opcional em Update, mas útil se ele puder avançar)
        if self.object.current_step < current_step + 1:
            self.object.current_step = current_step + 1
            self.object.save(update_fields=["current_step"])

        if current_step < len(self.steps_definition):
            next_step = current_step + 1
            # Importante: Apontamos para budget_update para manter o contexto de edição
            success_url = f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={next_step}"

            if self.request.htmx:
                response = redirect(success_url)
                response["HX-Push-Url"] = success_url
                return response

            return redirect(success_url)

        # Se for o último passo, volta para a lista
        return redirect(reverse("budget:budget_list"))


class BudgetDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Budget
    success_url = reverse_lazy("budget:budget_list")

    htmx_template_name = "budget/partials/budget_delete_modal.html"
    htmx_trigger = "budget-table-refresh"


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


class ItemSelectionModalView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = Budget
    template_name = "budget/partials/modals/modal_item_list.html"
    workshop_permission_codename = "add_budget"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        budget_id = self.kwargs.get("budget_id")
        item_type = self.kwargs.get("item_type")

        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        map_config = {
            "product": (Product, "Selecionar Produto"),
            "service": (Service, "Selecionar Serviço"),
            "kit": (Kit, "Selecionar Kit"),
        }

        model_class, title = map_config.get(item_type, (Product, "Selecionar Item"))
        queryset = model_class.objects.filter(workshop=self.workshop, is_active=True)

        # Get already added items to mark them as selected
        existing_items = set()
        if item_type == "product":
            existing_items = set(budget.items.filter(product__isnull=False).values_list('product_id', flat=True))
        elif item_type == "service":
            existing_items = set(budget.items.filter(service__isnull=False).values_list('service_id', flat=True))
        elif item_type == "kit":
            existing_items = set(budget.items.filter(kit__isnull=False).values_list('kit_id', flat=True))

        context.update({
            "items": queryset,
            "budget": budget,
            "item_type": item_type,
            "modal_title": title,
            "existing_items": existing_items
        })
        return context


class AddItemToBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, *args, **kwargs):
        budget = get_object_or_404(Budget, id=kwargs["budget_id"], workshop=self.workshop)

        item_filter = {f"{kwargs['item_type']}_id": kwargs["item_id"]}

        item, created = BudgetItem.objects.get_or_create(
            workshop=self.workshop,
            budget=budget,
            **item_filter,
            defaults={"quantity": 1},
        )

        if not created:
            item.quantity += 1
            item.save()

        success_url = f"{reverse('budget:budget_update', kwargs={'pk': budget.id})}?step={budget.current_step}"

        response = HttpResponse()
        response["HX-Redirect"] = success_url
        return response


class RemoveItemFromBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, *args, **kwargs):
        budget = get_object_or_404(Budget, id=kwargs["budget_id"], workshop=self.workshop)

        item_filter = {f"{kwargs['item_type']}_id": kwargs["item_id"]}

        item = get_object_or_404(BudgetItem, workshop=self.workshop, budget=budget, **item_filter)

        item.delete()

        from urllib.parse import urlparse, parse_qs
        referer = request.META.get('HTTP_REFERER', '')
        current_step = budget.current_step

        if referer:
            parsed = urlparse(referer)
            query_params = parse_qs(parsed.query)
            if 'step' in query_params:
                try:
                    current_step = int(query_params['step'][0])
                except (ValueError, IndexError):
                    pass

        success_url = f"{reverse('budget:budget_update', kwargs={'pk': budget.id})}?step={current_step}"

        response = HttpResponse()
        response["HX-Redirect"] = success_url
        return response


class RemoveBudgetItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Remove item do orçamento pelo item_id (funciona para itens locais e normais)"""
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, item_id):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        item = get_object_or_404(BudgetItem, id=item_id, budget=budget, workshop=self.workshop)

        item.delete()

        # Extract step from referer URL to stay on current step
        from urllib.parse import urlparse, parse_qs
        referer = request.META.get('HTTP_REFERER', '')
        current_step = budget.current_step

        if referer:
            parsed = urlparse(referer)
            query_params = parse_qs(parsed.query)
            if 'step' in query_params:
                try:
                    current_step = int(query_params['step'][0])
                except (ValueError, IndexError):
                    pass

        success_url = f"{reverse('budget:budget_update', kwargs={'pk': budget.id})}?step={current_step}"

        response = HttpResponse()
        response["HX-Redirect"] = success_url
        return response


class UpdateBudgetDiscountView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = get_object_or_404(Budget, pk=budget_id, workshop=self.workshop)
        try:
            val = request.POST.get("discount_value_0", "0").replace(",", ".")
            budget.discount_value = Decimal(val)
            budget.save()
        except (ValueError, TypeError):
            pass

        return HttpResponse(headers={"HX-Refresh": "true"})


class UpdateBudgetStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, status):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        # Validar se há itens locais ao tentar aprovar
        if status == "approve":
            local_items = budget.items.filter(is_local=True)
            if local_items.exists():
                return JsonResponse({
                    "success": False,
                    "error": "Não é possível aprovar. Existem itens sem cadastro que devem ser registrados antes de gerar a ordem de serviço."
                }, status=400)

        status_map = {
            "cancel": BudgetStatus.CANCELLED,
            "approve": BudgetStatus.APPROVED,
            "reject": BudgetStatus.REJECTED,
        }

        if status in status_map:
            budget.status = status_map[status]
            budget.save()

        return JsonResponse({"success": True})


class UpdateSliderView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        slider_value = request.POST.get("slider")
        if slider_value is not None:
            budget.slider = int(slider_value)
            budget.save()
        return HttpResponse(status=204)


class SaveObservationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request):
        try:
            data = json.loads(request.body)
            observation = data.get("observation", "").strip()
            self.workshop.pdf_observation = observation
            self.workshop.save()
            return JsonResponse({"success": True})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"success": False}, status=400)


class BudgetItemUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def get(self, request, budget_id, item_id):
        item = get_object_or_404(BudgetItem, pk=item_id, budget_id=budget_id)
        form = BudgetItemEditForm(instance=item, budget_id=budget_id)
        in_queue = request.GET.get('in_queue', 'false').lower() == 'true'

        context = {
            "form": form,
            "item": item,
            "budget_id": budget_id,
            "in_queue": in_queue
        }
        return render(request, "budget/partials/modals/modal_edit_item.html", context)

    def post(self, request, budget_id, item_id):
        item = get_object_or_404(BudgetItem, pk=item_id, budget_id=budget_id)
        form = BudgetItemEditForm(request.POST, instance=item, budget_id=budget_id)
        if form.is_valid():
            action = request.POST.get("action")
            item = form.save()

            if action == "update_master":
                self.update_master_record(item)
                return HtmxResponseHelper.success(
                    "Cadastro atualizado com sucesso.",
                    update_summary=True
                )

            # Para action "save_only" - retorna HTML da linha atualizada
            # Identificar tipo de item (incluindo locais)
            is_local_product = item.is_local and (item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0 or item.shipping.amount > 0)
            is_local_service = item.is_local and (item.service_cost_price.amount > 0 or item.service_selling_price.amount > 0 or item.duration)

            if item.product or is_local_product:
                template = "budget/partials/items/item_product_row.html"
            elif item.service or is_local_service:
                template = "budget/partials/items/item_service_row.html"
            else:
                template = "budget/partials/items/item_kit_row.html"

            context = {"item": item, "budget": item.budget, "is_full_render": False}
            row_html = render_to_string(template, context)

            return HtmxResponseHelper.success(
                "Item atualizado com sucesso!",
                close_modal=True,
                update_summary=True,
                content=row_html
            )

        return render(request, "budget/partials/modals/modal_edit_item.html", {"form": form, "item": item, "budget_id": budget_id})

    def update_master_record(self, item):
        if item.product:
            product = item.product
            product.name = item.description
            product.cost_price = item.product_cost_price
            product.selling_price = item.product_selling_price
            product.save()
        elif item.service:
            service = item.service
            service.name = item.description
            service.suggested_cost = item.service_cost_price
            service.selling_price = item.service_selling_price
            service.duration = item.duration
            service.save()
        elif item.kit:
            kit = item.kit
            kit.name = item.description


class BudgetItemCalculateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def post(self, request, budget_id, item_id):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        item = get_object_or_404(BudgetItem, pk=item_id, budget_id=budget_id)

        # Usamos o form para processar o valor da duração vindo do POST
        form = BudgetItemEditForm(request.POST, instance=item, budget_id=budget_id)

        # Chamamos full_clean() para popular cleaned_data
        try:
            form.full_clean()
        except Exception:
            pass

        cleaned_data = getattr(form, "cleaned_data", {})

        # Tentamos obter a duração, mesmo que o form tenha outros erros
        duration = cleaned_data.get("duration")

        # Se não estiver no cleaned_data (erro de validação), tentamos pegar o valor bruto
        if duration is None:
            raw_duration = request.POST.get("duration")
            if raw_duration:
                try:
                    duration = DurationField.parse_duration(raw_duration)
                except Exception:
                    duration = timedelta()
                except (ValueError, TypeError):
                    duration = timedelta()
            else:
                duration = timedelta()

        # Lógica de busca do WorkshopCost (similar ao calculate_pricing_methods do modelo)
        workshop_cost = None
        workshop_cost_missing = False
        try:
            reference_date = budget.criado_em if budget.criado_em else timezone.now()
            workshop_cost = WorkshopCost.objects.get(workshop=self.workshop, month=reference_date.month, year=reference_date.year)
        except WorkshopCost.DoesNotExist:
            try:
                workshop_cost = WorkshopCost.objects.get(workshop=self.workshop, month=timezone.now().month, year=timezone.now().year)
            except WorkshopCost.DoesNotExist:
                workshop_cost_missing = True

        duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

        if workshop_cost:
            min_hourly = workshop_cost.minimum_hourly_cost if workshop_cost.minimum_hourly_cost else Money(0, "BRL")
            hourly_val = workshop_cost.hourly_cost_value if workshop_cost.hourly_cost_value else Money(0, "BRL")
            service_cost_price = min_hourly * duration_hours
            service_selling_price = hourly_val * duration_hours
        else:
            service_cost_price = Money(0, "BRL")
            service_selling_price = Money(0, "BRL")

        # Arredondamento
        service_cost_price_amount = service_cost_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
        service_selling_price_amount = service_selling_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP)

        # Atualiza a instância com os novos valores calculados
        item.service_cost_price = Money(service_cost_price_amount, "BRL")
        item.service_selling_price = Money(service_selling_price_amount, "BRL")
        if duration:
            item.duration = duration

        # Atualiza os dados do POST para refletir os novos preços no formulário bound
        data = request.POST.copy()

        # No Django, campos MoneyField costumam usar o sufixo _0 para o valor numérico no POST
        data["service_cost_price_0"] = str(service_cost_price_amount)
        data["service_cost_price_1"] = "BRL"
        data["service_selling_price_0"] = str(service_selling_price_amount)
        data["service_selling_price_1"] = "BRL"

        # Garante que o valor da duração formatado também vá para o POST do novo form
        if duration:
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            data["duration"] = f"{hours:02d}:{minutes:02d}"

        # Re-inicializa o formulário com os dados atualizados e a instância
        form = BudgetItemEditForm(data, instance=item, budget_id=budget_id)

        # Apenas o campo de venda vai por OOB, o de custo é o target principal
        oob_fields = ["service_selling_price"]

        # Se houver erros no form (especialmente na duração), incluímos nos campos OOB
        # para que as mensagens de erro sejam exibidas no modal.
        if form.errors:
            for field_with_error in form.errors:
                if field_with_error not in oob_fields:
                    oob_fields.append(field_with_error)

        context = {
            "form": form,
            "item": item,
            "budget_id": budget_id,
            "oob_fields": oob_fields,
        }

        response = render(request, "budget/partials/modals/modal_edit_item_fields.html", context)

        # Add toast error if WorkshopCost is missing
        if workshop_cost_missing:
            response["HX-Trigger"] = json.dumps({
                "showToast": {
                    "message": "Custo da oficina não cadastrado para o mês atual. Os valores não puderam ser calculados automaticamente.",
                    "type": "error"
                }
            })

        return response


class BudgetImageView(LoginRequiredMixin, View):
    def get(self, request, pk):
        from django.http import HttpResponse

        from apps.budget.models import BudgetImage

        image = get_object_or_404(BudgetImage, pk=pk)

        return HttpResponse(image.content, content_type=image.content_type)


class BudgetKitEditView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View para editar itens de um kit no contexto deste orçamento"""
    model = BudgetItem
    workshop_permission_codename = "change_budgetitem"

    def get(self, request, budget_id, item_id):
        from apps.budget.models import BudgetKitItemOverride

        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        item = get_object_or_404(BudgetItem, id=item_id, budget=budget, kit__isnull=False)

        # Buscar produtos do kit com overrides
        kit_products = []
        for product in item.kit.products.all():
            override = BudgetKitItemOverride.objects.filter(
                budget_item=item,
                product=product
            ).first()

            kit_products.append({
                'id': product.id,
                'name': product.name,
                'quantity': override.quantity if override else 1,
                'cost': override.product_cost_price if override else product.cost_price,
                'price': override.product_selling_price if override else product.selling_price,
                'shipping': override.shipping if override else Money(0, 'BRL'),
            })

        # Buscar serviços do kit com overrides
        kit_services = []
        for service in item.kit.services.all():
            override = BudgetKitItemOverride.objects.filter(
                budget_item=item,
                service=service
            ).first()

            # Format duration as HH:MM:SS
            duration_str = ""
            if override and override.duration:
                duration = override.duration
            elif service.duration:
                duration = service.duration
            else:
                duration = timedelta(0)

            if duration:
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            kit_services.append({
                'id': service.id,
                'name': service.name,
                'quantity': override.quantity if override else 1,
                'cost': override.service_cost_price if override else service.suggested_cost,
                'price': override.service_selling_price if override else service.selling_price,
                'duration': duration_str,
            })

        context = {
            'item': item,
            'kit_products': kit_products,
            'kit_services': kit_services,
        }

        return render(request, 'budget/partials/modals/modal_edit_kit.html', context)

    def post(self, request, budget_id, item_id):
        from apps.budget.models import BudgetKitItemOverride
        from datetime import timedelta

        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        item = get_object_or_404(BudgetItem, id=item_id, budget=budget, kit__isnull=False)

        # Parse products data
        products_json = request.POST.get('products', '[]')
        products_data = json.loads(products_json)

        for product_data in products_data:
            product_id = product_data.get('id')
            product = get_object_or_404(Product, id=product_id)

            # Create or update override
            override, created = BudgetKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                budget_item=item,
                product=product,
                defaults={
                    'quantity': int(product_data.get('quantity', 1)),
                    'product_cost_price': Money(Decimal(str(product_data.get('cost', 0))), 'BRL'),
                    'product_selling_price': Money(Decimal(str(product_data.get('price', 0))), 'BRL'),
                    'shipping': Money(Decimal(str(product_data.get('shipping', 0))), 'BRL'),
                }
            )

        # Parse services data
        services_json = request.POST.get('services', '[]')
        services_data = json.loads(services_json)

        print(f"DEBUG Kit Edit: Saving {len(products_data)} products and {len(services_data)} services for budget_item #{item.id}")

        for service_data in services_data:
            service_id = service_data.get('id')
            service = get_object_or_404(Service, id=service_id)

            # Parse duration string (HH:MM:SS)
            duration_str = service_data.get('duration', '00:00:00')
            duration = None
            if duration_str:
                try:
                    parts = duration_str.split(':')
                    if len(parts) == 3:
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        seconds = int(parts[2])
                        duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
                except (ValueError, IndexError):
                    duration = timedelta(0)

            # Create or update override
            override, created = BudgetKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                budget_item=item,
                service=service,
                defaults={
                    'quantity': int(service_data.get('quantity', 1)),
                    'service_cost_price': Money(Decimal(str(service_data.get('cost', 0))), 'BRL'),
                    'service_selling_price': Money(Decimal(str(service_data.get('price', 0))), 'BRL'),
                    'duration': duration,
                }
            )

            print(f"DEBUG: Saved service override - {service.name}: qtd={override.quantity}, price={override.service_selling_price}, duration={override.duration}")

        # Force recalculation by accessing total_price
        total = item.total_price
        print(f"DEBUG: Kit total calculated: {total}")

        # Redirect with full page reload (not HTMX)
        import time
        timestamp = int(time.time())
        response = HttpResponse()
        response["HX-Redirect"] = f"/budget/{budget_id}/edit/?step=4&_t={timestamp}"
        response["HX-Refresh"] = "true"  # Force full page refresh
        return response


class CalculateKitServiceView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Calcula custo e preço de um serviço baseado na duração (para edição de kit)"""
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        from datetime import timedelta
        from decimal import Decimal

        service_id = request.POST.get('service_id')
        duration_str = request.POST.get('duration', '00:00:00')

        # Parse duration
        duration = None
        try:
            parts = duration_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        except (ValueError, IndexError):
            return JsonResponse({'error': 'Invalid duration format'}, status=400)

        if not duration or duration.total_seconds() == 0:
            return JsonResponse({'error': 'Duration is required'}, status=400)

        # Get service
        try:
            service = get_object_or_404(Service, id=service_id)
        except:
            return JsonResponse({'error': 'Service not found'}, status=404)

        # Calculate pricing using existing logic
        try:
            budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

            # Try to get WorkshopCost for calculation
            workshop_cost = WorkshopCost.objects.filter(
                workshop=self.workshop,
                month=timezone.now().month,
                year=timezone.now().year
            ).first()

            if workshop_cost and workshop_cost.minimum_hourly_cost:
                # Calculate based on duration and hourly cost
                hours_decimal = Decimal(str(duration.total_seconds())) / Decimal('3600')
                cost = float(workshop_cost.minimum_hourly_cost.amount) * float(hours_decimal)

                # Apply markup from slider (if exists)
                slider_value = budget.slider if hasattr(budget, 'slider') else 50
                markup_percentage = Decimal(str(slider_value)) / Decimal('100')
                price = cost * float(Decimal('1') + markup_percentage)

                return JsonResponse({
                    'cost': round(cost, 2),
                    'price': round(price, 2)
                })
            else:
                # Fallback to service defaults
                cost_val = float(service.suggested_cost.amount) if service.suggested_cost else 0
                price_val = float(service.selling_price.amount) if service.selling_price else 0

                return JsonResponse({
                    'cost': cost_val,
                    'price': price_val
                })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)


from django.views.decorators.clickjacking import xframe_options_exempt
from djmoney.money import Money
@xframe_options_exempt
def visualizar_pdf(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)
    workshop = get_active_workshop_or_404(request)

    context = {
        'budget': budget,
        'produtos': produtos,
        'servicos': servicos,
        'total_produtos': budget.total_products_value,
        'total_servicos': budget.total_services_value,
        'desconto': budget.discount_value,
        'total_geral': budget.total_budget_value,
        'observacao': workshop.pdf_observation
    }

    return render(request, 'budget/partials/pdf/visualizarPDF.html', context)


@xframe_options_exempt
def visualizar_pdf_gestor(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)
    workshop = get_active_workshop_or_404(request)

    total_profit_product_value = Money(0, 'BRL')
    for p in produtos:
        total_profit_product_value += p.profit_value

    total_profit_service_value = Money(0, 'BRL')
    for s in servicos:
        total_profit_service_value += s.profit_value

    context = {
        'budget': budget,
        'produtos': produtos,
        'servicos': servicos,
        'observacao': workshop.pdf_observation,
        'total_profit_product_value': total_profit_product_value,
        'total_profit_service_value': total_profit_service_value
    }

    return render(request, 'budget/partials/pdf/visualizarPDFGestor.html', context)


@xframe_options_exempt
def visualizar_pdf_mecanico(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    itens_all = BudgetItem.objects.filter(budget=budget)
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)
    workshop = get_active_workshop_or_404(request)

    context = {
        'budget': budget,
        'produtos': produtos,
        'servicos': servicos,
        'observacao': workshop.pdf_observation
    }

    return render(request, 'budget/partials/pdf/visualizarPDFMecanico.html', context)


class AddItemsBatchToBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, item_type):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        # Recebe IDs dos checkboxes marcados
        selected_ids = request.POST.getlist("selected_items")
        if not selected_ids:
            # Return error message in the modal container
            error_html = """
            <div class="modal-box w-11/12 max-w-md bg-base-100">
                <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2" onclick="form_modal.close()">✕</button>
                <div class="flex flex-col items-center justify-center py-8">
                    <span class="material-icons text-warning text-6xl mb-4">warning</span>
                    <h3 class="font-bold text-xl mb-2">Nenhum item selecionado</h3>
                    <p class="text-base-content/70 mb-6">Por favor, selecione pelo menos um item para adicionar ao orçamento.</p>
                    <button class="btn btn-primary" onclick="form_modal.close()">Entendi</button>
                </div>
            </div>
            """
            return HttpResponse(error_html)

        if item_type == 'kit':
            for item_id in selected_ids:
                BudgetItem.objects.get_or_create(
                    workshop=self.workshop,
                    budget=budget,
                    kit_id=item_id,
                    defaults={"quantity": 1}
                )

            # Extract step from referer URL to stay on current step
            from urllib.parse import urlparse, parse_qs
            referer = request.META.get('HTTP_REFERER', '')
            current_step = budget.current_step

            if referer:
                parsed = urlparse(referer)
                query_params = parse_qs(parsed.query)
                if 'step' in query_params:
                    try:
                        current_step = int(query_params['step'][0])
                    except (ValueError, IndexError):
                        pass

            success_url = f"{reverse('budget:budget_update', kwargs={'pk': budget.id})}?step={current_step}"
            response = HttpResponse()
            response["HX-Redirect"] = success_url
            return response

        created_items = []
        for item_id in selected_ids:
            item_filter = {f"{item_type}_id": item_id}

            budget_item, created = BudgetItem.objects.get_or_create(workshop=self.workshop, budget=budget, **item_filter, defaults={"quantity": 1})

            created_items.append(budget_item.id)

        context = {
            "budget": budget,
            "item_type": item_type,
            "item_ids": created_items,
            "total_items": len(created_items),
            "current_index": 0,
        }

        return render(request, "budget/partials/modals/modal_edit_queue.html", context)


class BudgetSummaryView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Retorna apenas o partial do resumo do orçamento para atualização via HTMX."""
    model = Budget
    workshop_permission_codename = "view_budget"

    def get(self, request, budget_id):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        return render(request, 'budget/partials/components/budget_summary.html', {'budget': budget})


class BudgetStep3CollaboratorFieldView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Retorna apenas o campo de colaborador para refresh via HTMX após criar/editar colaborador."""
    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, budget_id):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)
        form = BudgetStep3Form(instance=budget, workshop=self.workshop, request=request)

        # Get the selected collaborator ID from query params (for restoration)
        selected_id = request.GET.get('selected', '')
        if selected_id:
            form.fields['collaborator'].initial = selected_id

        # Determine initial collaborator ID for Alpine.js x-data
        initial_collab_id = selected_id or (budget.collaborator.id if budget.collaborator else '')

        # Render the field using the template
        context = {
            'form': form,
            'field': form['collaborator'],
            'initial_collab_id': initial_collab_id,
        }

        return render(request, 'budget/partials/components/collaborator_field.html', context)


class CreateLocalItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Modal para criar item local (produto ou serviço apenas neste orçamento)"""
    model = Budget
    workshop_permission_codename = "add_budget"

    def get(self, request, budget_id, item_type):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        if item_type == "product":
            form = LocalProductForm()
            title = "Incluir Novo Produto Local"
        elif item_type == "service":
            form = LocalServiceForm(budget_id=budget_id)
            title = "Incluir Novo Serviço Local"
        else:
            return HttpResponse("Tipo inválido", status=400)

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": title,
        }
        return render(request, "budget/partials/modals/modal_create_local_item.html", context)

    def post(self, request, budget_id, item_type):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        if item_type == "product":
            form = LocalProductForm(request.POST)
        elif item_type == "service":
            form = LocalServiceForm(request.POST, budget_id=budget_id)
        else:
            return HttpResponse("Tipo inválido", status=400)

        if form.is_valid():
            item = form.save(commit=False)
            item.workshop = self.workshop
            item.budget = budget
            item.is_local = True
            item.save()

            # Retornar HTML da linha do item criado
            if item_type == "product":
                template = "budget/partials/items/item_product_row.html"
            else:
                template = "budget/partials/items/item_service_row.html"

            context = {
                "item": item,
                "budget": budget,
                "is_full_render": True
            }

            row_html = render_to_string(template, context)

            # Fechar modal e adicionar linha na tabela
            return HtmxResponseHelper.success(
                f"{'Produto' if item_type == 'product' else 'Serviço'} local criado com sucesso!",
                close_modal=True,
                update_summary=True,
                content=row_html
            )

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": f"Incluir Novo {'Produto' if item_type == 'product' else 'Serviço'} Local",
        }
        return render(request, "budget/partials/modals/modal_create_local_item.html", context)



class RegisterLocalItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Abre modal para cadastrar item local no banco de dados"""
    model = Budget
    workshop_permission_codename = "add_budget"

    def get(self, request, budget_id, item_id):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        item = get_object_or_404(BudgetItem, id=item_id, budget_id=budget_id, workshop=self.workshop, is_local=True)

        if item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0:
            # É um produto - usar formulário simplificado
            initial = {
                "name": item.description,
                "cost_price": item.product_cost_price,
                "selling_price": item.product_selling_price,
                "code": f"TEMP-{item.id}",  # Código temporário
                "unit": "UND",  # Unidade padrão
            }
            form = QuickProductForm(initial=initial, workshop=self.workshop)
            title = "Cadastrar Produto no Banco de Dados"
            item_type = "product"
        else:
            # É um serviço - usar formulário simplificado
            initial = {
                "name": item.description,
                "selling_price": item.service_selling_price,
                "duration": item.duration,
            }
            form = QuickServiceForm(initial=initial)
            title = "Cadastrar Serviço no Banco de Dados"
            item_type = "service"

        context = {
            "form": form,
            "item": item,
            "budget_id": budget_id,
            "item_id": item_id,
            "item_type": item_type,
            "title": title,
            "is_register_mode": True,  # Flag para identificar que é registro de item local
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)

    def post(self, request, budget_id, item_id):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        item = get_object_or_404(BudgetItem, id=item_id, budget_id=budget_id, workshop=self.workshop, is_local=True)

        if item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0:
            # Cadastrar produto
            form = QuickProductForm(request.POST, workshop=self.workshop)

            if form.is_valid():
                product = form.save(commit=False)
                product.workshop = self.workshop
                product.save()

                # Vincular ao budget item
                item.product = product
                item.is_local = False
                item.save()

                # Retornar a linha atualizada com OOB swap
                context = {"item": item, "budget": item.budget, "is_full_render": False}
                row_html = render_to_string("budget/partials/items/item_product_row.html", context)

                return HtmxResponseHelper.success(
                    "Produto cadastrado com sucesso!",
                    close_modal=True,
                    update_summary=True,
                    content=row_html
                )
        else:
            # Cadastrar serviço
            form = QuickServiceForm(request.POST)

            if form.is_valid():
                service = form.save(commit=False)
                service.workshop = self.workshop
                service.save()

                # Vincular ao budget item
                item.service = service
                item.is_local = False
                item.save()

                # Retornar a linha atualizada
                context = {"item": item, "budget": item.budget, "is_full_render": False}
                row_html = render_to_string("budget/partials/items/item_service_row.html", context)

                return HtmxResponseHelper.success(
                    "Serviço cadastrado com sucesso!",
                    close_modal=True,
                    update_summary=True,
                    content=row_html
                )

        # Se form inválido, retorna com erros
        item_type = "product" if item.product_cost_price.amount > 0 else "service"
        context = {
            "form": form,
            "item": item,
            "budget_id": budget_id,
            "item_id": item_id,
            "item_type": item_type,
            "title": f"Cadastrar {'Produto' if item_type == 'product' else 'Serviço'} no Banco de Dados",
            "is_register_mode": True,
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)


class CalculateLocalServiceView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Calcular custos de serviço local baseado na duração"""
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        # Parse duration
        raw_duration = request.POST.get("duration", "")
        duration = timedelta()

        if raw_duration:
            try:
                duration = DurationField.parse_duration(raw_duration) or timedelta()
            except Exception:
                pass

        # Buscar WorkshopCost
        workshop_cost = None
        workshop_cost_missing = False

        try:
            reference_date = budget.criado_em if budget.criado_em else timezone.now()
            workshop_cost = WorkshopCost.objects.get(workshop=self.workshop, month=reference_date.month, year=reference_date.year)
        except WorkshopCost.DoesNotExist:
            try:
                workshop_cost = WorkshopCost.objects.get(workshop=self.workshop, month=timezone.now().month, year=timezone.now().year)
            except WorkshopCost.DoesNotExist:
                workshop_cost_missing = True

        # Calcular valores
        duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

        if workshop_cost:
            min_hourly = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
            hourly_val = workshop_cost.hourly_cost_value or Money(0, "BRL")
            service_cost_price = min_hourly * duration_hours
            service_selling_price = hourly_val * duration_hours
        else:
            service_cost_price = Money(0, "BRL")
            service_selling_price = Money(0, "BRL")

        # Preparar form
        data = request.POST.copy()
        data["service_cost_price_0"] = str(service_cost_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
        data["service_cost_price_1"] = "BRL"
        data["service_selling_price_0"] = str(service_selling_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
        data["service_selling_price_1"] = "BRL"

        form = LocalServiceForm(data, budget_id=budget_id)

        context = {
            "form": form,
            "budget_id": budget_id,
            "oob_fields": ["service_selling_price"],
        }

        response = render(request, "budget/partials/modals/modal_local_service_fields.html", context)

        if workshop_cost_missing:
            response["HX-Trigger"] = json.dumps({
                "showToast": {
                    "message": "Custo da oficina não cadastrado para o mês atual.",
                    "type": "error"
                }
            })

        return response


class QuickCreateProductView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Cadastro rápido de produto com atualização automática da lista"""
    model = Budget
    workshop_permission_codename = "add_budget"

    def get(self, request, budget_id, item_type):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        if item_type == "product":
            form = QuickProductForm(workshop=self.workshop)
            title = "Cadastrar Novo Produto"
        elif item_type == "service":
            form = QuickServiceForm()
            title = "Cadastrar Novo Serviço"
        else:
            return HttpResponse("Tipo inválido", status=400)

        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": title,
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)

    def post(self, request, budget_id, item_type):
        from apps.budget.forms import QuickProductForm, QuickServiceForm

        budget = get_object_or_404(Budget, id=budget_id, workshop=self.workshop)

        if item_type == "product":
            form = QuickProductForm(request.POST, workshop=self.workshop)
        elif item_type == "service":
            form = QuickServiceForm(request.POST)
        else:
            return HttpResponse("Tipo inválido", status=400)

        if form.is_valid():
            item = form.save(commit=False)
            item.workshop = self.workshop
            item.save()

            # Retornar a lista atualizada de itens
            from apps.catalog.models.products import Product
            from apps.catalog.models.services import Service

            if item_type == "product":
                model_class = Product
            else:
                model_class = Service

            queryset = model_class.objects.filter(workshop=self.workshop, is_active=True)

            # Get already added items
            existing_items = set()
            if item_type == "product":
                existing_items = set(budget.items.filter(product__isnull=False).values_list('product_id', flat=True))
            elif item_type == "service":
                existing_items = set(budget.items.filter(service__isnull=False).values_list('service_id', flat=True))

            context = {
                "items": queryset,
                "budget": budget,
                "item_type": item_type,
                "modal_title": f"Selecionar {'Produto' if item_type == 'product' else 'Serviço'}",
                "existing_items": existing_items,
                "newly_created_id": item.id,  # ID do item recém-criado
            }

            return HtmxResponseHelper.render_and_trigger(
                "budget/partials/modals/modal_item_list.html",
                context,
                {
                    "showToast": {
                        "message": f"{'Produto' if item_type == 'product' else 'Serviço'} cadastrado com sucesso!",
                        "type": "success"
                    }
                }
            )

        # Se form inválido
        context = {
            "form": form,
            "budget_id": budget_id,
            "item_type": item_type,
            "title": f"Cadastrar Novo {'Produto' if item_type == 'product' else 'Serviço'}",
        }
        return render(request, "budget/partials/modals/modal_quick_create.html", context)

