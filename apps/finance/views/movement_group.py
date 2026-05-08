from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views import View
from decimal import Decimal

from apps.finance.models import FinancialMovement, MovementGroup
from apps.finance.forms.movement_group import GroupMovementStep1Form, GroupMovementStep3Form
from apps.suppliers.models import Supplier
from apps.collaborators.models import WorkshopCollaborator
from apps.customer.models import Customer
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workorder.models import WorkOrderPaymentMethod


class GroupMovementWizardView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = MovementGroup
    workshop_permission_codename = "add_financialmovement"

    def _get_unified_movements(self, entity_type, entity_id, filter_direction, filter_start_date, filter_end_date):
        fm_qs = FinancialMovement.objects.filter(
            workshop=self.workshop, 
            movement_kind=FinancialMovement.MovementKind.DEFAULT, 
            movement_group__isnull=True, 
            is_paid=False
        )
        pm_qs = WorkOrderPaymentMethod.objects.none()

        entity_name = ""
        if entity_type == "supplier":
            fm_qs = fm_qs.filter(supplier_id=entity_id)
            entity_name = Supplier.objects.get(id=entity_id).name
        elif entity_type == "collaborator":
            fm_qs = fm_qs.filter(collaborator_id=entity_id)
            entity_name = str(WorkshopCollaborator.objects.get(id=entity_id))
        elif entity_type == "customer":
            fm_qs = fm_qs.filter(workorder__budget__customer_id=entity_id)
            pm_qs = WorkOrderPaymentMethod.objects.filter(
                workorder__workshop=self.workshop,
                workorder__budget__customer_id=entity_id,
                movement_group__isnull=True
            )
            entity_name = Customer.objects.get(id=entity_id).name

        if filter_direction:
            fm_qs = fm_qs.filter(direction=filter_direction)
            if filter_direction == "DEBIT":
                pm_qs = pm_qs.none()
        
        if filter_start_date:
            fm_qs = fm_qs.filter(due_date__gte=filter_start_date)
            pm_qs = pm_qs.filter(due_date__gte=filter_start_date)
            
        if filter_end_date:
            fm_qs = fm_qs.filter(due_date__lte=filter_end_date)
            pm_qs = pm_qs.filter(due_date__lte=filter_end_date)

        unified = []
        for mv in fm_qs:
            unified.append({
                "id": f"fm_{mv.id}",
                "due_date": mv.due_date,
                "direction": mv.direction,
                "description": mv.description,
                "items_observation": mv.items_observation,
                "payment_method": mv.payment_method,
                "is_paid": mv.is_paid,
                "amount": mv.amount,
                "obj": mv
            })

        for pm in pm_qs:
            unified.append({
                "id": f"pm_{pm.id}",
                "due_date": pm.due_date,
                "direction": "CREDIT",
                "description": f"OS Nº {pm.workorder_id}",
                "items_observation": "",
                "payment_method": pm.payment_method,
                "is_paid": False,
                "amount": pm.total_paid,
                "obj": pm
            })

        unified.sort(key=lambda x: (x["due_date"] or timezone.now().date(), x["id"]))
        return unified, entity_name

    def get(self, request, *args, **kwargs):
        step = request.GET.get("step", "1")

        if step == "1":
            customers = Customer.objects.filter(workshop=self.workshop)
            suppliers = Supplier.objects.filter(workshop=self.workshop, is_active=True)
            collaborators = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            form = GroupMovementStep1Form(customers=customers, suppliers=suppliers, collaborators=collaborators)
            return render(request, "finance/reports/partials/group_step1.html", {"form": form})

        return HttpResponse("Invalid Step", status=400)

    def post(self, request, *args, **kwargs):
        step = request.POST.get("step")

        if step == "1":
            customers = Customer.objects.filter(workshop=self.workshop)
            suppliers = Supplier.objects.filter(workshop=self.workshop, is_active=True)
            collaborators = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            form = GroupMovementStep1Form(request.POST, customers=customers, suppliers=suppliers, collaborators=collaborators)

            if form.is_valid():
                entity_val = form.cleaned_data["entity"]
                entity_type, entity_id = entity_val.split("_")

                filter_direction = request.POST.get("filter_direction", "")
                filter_start_date = request.POST.get("filter_start_date", "")
                filter_end_date = request.POST.get("filter_end_date", "")

                movements, entity_name = self._get_unified_movements(
                    entity_type, entity_id, filter_direction, filter_start_date, filter_end_date
                )

                return render(
                    request,
                    "finance/reports/partials/group_step2.html",
                    {
                        "movements": movements,
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "entity_name": entity_name,
                        "filter_direction": filter_direction,
                        "filter_start_date": filter_start_date,
                        "filter_end_date": filter_end_date,
                    },
                )

            return render(request, "finance/reports/partials/group_step1.html", {"form": form})

        elif step == "2":
            movement_ids = request.POST.getlist("movements")
            entity_type = request.POST.get("entity_type")
            entity_id = request.POST.get("entity_id")

            all_movements, entity_name = self._get_unified_movements(entity_type, entity_id, "", "", "")

            error = None
            if not movement_ids:
                error = "Selecione ao menos um lançamento."
            else:
                selected_movements = [mv for mv in all_movements if mv["id"] in movement_ids]
                if selected_movements:
                    first_direction = selected_movements[0]["direction"]

                    for mv in selected_movements:
                        if mv["direction"] != first_direction:
                            error = "Todos os lançamentos selecionados devem ser do mesmo tipo (Crédito ou Débito)."
                            break

            if error:
                return render(request, "finance/reports/partials/group_step2.html", {"movements": all_movements, "entity_type": entity_type, "entity_id": entity_id, "entity_name": entity_name, "error": error})

            # Step 3 form
            total_amount = Decimal("0.00")
            for mv in selected_movements:
                val = mv["amount"]
                total_amount += Decimal(str(val.amount if hasattr(val, "amount") else val))

            form = GroupMovementStep3Form()
            return render(request, "finance/reports/partials/group_step3.html", {"form": form, "movement_ids": movement_ids, "entity_type": entity_type, "entity_id": entity_id, "total_amount": total_amount})

        elif step == "3":
            form = GroupMovementStep3Form(request.POST)
            movement_ids = request.POST.getlist("movements")
            entity_type = request.POST.get("entity_type")
            entity_id = request.POST.get("entity_id")

            if form.is_valid():
                with transaction.atomic():
                    group = form.save(commit=False)
                    group.workshop = self.workshop
                    group.user = request.user

                    if entity_type == "supplier":
                        group.supplier_id = entity_id
                    elif entity_type == "collaborator":
                        group.collaborator_id = entity_id
                    # We don't save customer_id on group directly right now, unless it's added. Let's just leave it None.

                    group.save()

                    fm_ids = [int(mid.split("_")[1]) for mid in movement_ids if mid.startswith("fm_")]
                    pm_ids = [int(mid.split("_")[1]) for mid in movement_ids if mid.startswith("pm_")]

                    total_amount = Decimal("0.00")
                    first_direction = FinancialMovement.MovementDirection.DEBIT
                    
                    if fm_ids:
                        fms = FinancialMovement.objects.filter(id__in=fm_ids, workshop=self.workshop)
                        first_mv = fms.first()
                        if first_mv:
                            first_direction = first_mv.direction
                        for mv in fms:
                            mv.movement_group = group
                            total_amount += Decimal(str(mv.amount.amount))
                            mv.save()
                    
                    if pm_ids:
                        pms = WorkOrderPaymentMethod.objects.filter(id__in=pm_ids, workorder__workshop=self.workshop)
                        if pms:
                            first_direction = FinancialMovement.MovementDirection.CREDIT
                        for pm in pms:
                            pm.movement_group = group
                            total_amount += Decimal(str(pm.total_paid.amount))
                            pm.save()

                    # Create Parent Movement
                    FinancialMovement.objects.create(
                        workshop=self.workshop,
                        user=request.user,
                        movement_kind=FinancialMovement.MovementKind.GROUP_PARENT,
                        movement_group=group,
                        description=f"Agrupamento - {group.name}",
                        financial_observation=group.description,
                        due_date=group.due_date,
                        amount=total_amount,
                        direction=first_direction,
                        supplier_id=group.supplier_id,
                        collaborator_id=group.collaborator_id,
                        is_paid=False,
                    )

                response = HttpResponse()
                response["HX-Refresh"] = "true"
                return response

            return render(request, "finance/reports/partials/group_step3.html", {"form": form, "movement_ids": movement_ids, "entity_type": entity_type, "entity_id": entity_id})

        return HttpResponse("Invalid Step", status=400)


class GroupMovementDeleteView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = MovementGroup
    workshop_permission_codename = "delete_financialmovement"

    def post(self, request, pk, *args, **kwargs):
        group = get_object_or_404(MovementGroup, pk=pk, workshop=self.workshop)

        with transaction.atomic():
            # Detach original children so they are not deleted
            children = group.financial_movements.exclude(movement_kind=FinancialMovement.MovementKind.GROUP_PARENT)
            children.update(movement_group=None)
            
            group.workorder_payments.update(movement_group=None)

            # This will delete the MovementGroup and the GROUP_PARENT FinancialMovement (due to CASCADE)
            group.delete()

        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response
