from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views import View
from decimal import Decimal

from apps.finance.models import FinancialMovement, MovementGroup
from apps.finance.forms.movement_group import GroupMovementStep1Form, GroupMovementStep3Form
from apps.suppliers.models import Supplier
from apps.collaborators.models import WorkshopCollaborator
from apps.workshops.mixin import WorkshopScopedMixin


class GroupMovementWizardView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = MovementGroup
    workshop_permission_codename = "add_financialmovement"

    def get(self, request, *args, **kwargs):
        step = request.GET.get("step", "1")

        if step == "1":
            suppliers = Supplier.objects.filter(workshop=self.workshop, is_active=True)
            collaborators = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            form = GroupMovementStep1Form(suppliers=suppliers, collaborators=collaborators)
            return render(request, "finance/reports/partials/group_step1.html", {"form": form})

        return HttpResponse("Invalid Step", status=400)

    def post(self, request, *args, **kwargs):
        step = request.POST.get("step")

        if step == "1":
            suppliers = Supplier.objects.filter(workshop=self.workshop, is_active=True)
            collaborators = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            form = GroupMovementStep1Form(request.POST, suppliers=suppliers, collaborators=collaborators)

            if form.is_valid():
                entity_val = form.cleaned_data["entity"]
                entity_type, entity_id = entity_val.split("_")

                # Fetch pending movements for this entity
                movements = FinancialMovement.objects.filter(workshop=self.workshop, movement_kind=FinancialMovement.MovementKind.DEFAULT, movement_group__isnull=True, is_paid=False)

                if entity_type == "supplier":
                    movements = movements.filter(supplier_id=entity_id)
                    entity_name = Supplier.objects.get(id=entity_id).name
                else:
                    movements = movements.filter(collaborator_id=entity_id)
                    entity_name = str(WorkshopCollaborator.objects.get(id=entity_id))

                # Apply filters
                filter_direction = request.POST.get("filter_direction", "")
                filter_start_date = request.POST.get("filter_start_date", "")
                filter_end_date = request.POST.get("filter_end_date", "")

                if filter_direction:
                    movements = movements.filter(direction=filter_direction)
                if filter_start_date:
                    movements = movements.filter(due_date__gte=filter_start_date)
                if filter_end_date:
                    movements = movements.filter(due_date__lte=filter_end_date)

                # Ensure ordered for consistent display
                movements = movements.order_by("due_date", "id")

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

            all_movements = FinancialMovement.objects.filter(workshop=self.workshop, movement_kind=FinancialMovement.MovementKind.DEFAULT, movement_group__isnull=True, is_paid=False)
            if entity_type == "supplier":
                all_movements = all_movements.filter(supplier_id=entity_id)
                entity_name = Supplier.objects.get(id=entity_id).name
            else:
                all_movements = all_movements.filter(collaborator_id=entity_id)
                entity_name = str(WorkshopCollaborator.objects.get(id=entity_id))

            error = None
            if not movement_ids:
                error = "Selecione ao menos um lançamento."
            else:
                selected_movements = FinancialMovement.objects.filter(id__in=movement_ids, workshop=self.workshop)
                first_mv = selected_movements.first()
                if first_mv:
                    first_month_year = (first_mv.due_date.month, first_mv.due_date.year) if first_mv.due_date else None
                    first_direction = first_mv.direction

                    for mv in selected_movements:
                        mv_month_year = (mv.due_date.month, mv.due_date.year) if mv.due_date else None
                        if mv_month_year != first_month_year:
                            error = "Todos os lançamentos selecionados devem ser do mesmo mês e ano."
                            break
                        if mv.direction != first_direction:
                            error = "Todos os lançamentos selecionados devem ser do mesmo tipo (Crédito ou Débito)."
                            break

            if error:
                return render(request, "finance/reports/partials/group_step2.html", {"movements": all_movements, "entity_type": entity_type, "entity_id": entity_id, "entity_name": entity_name, "error": error})

            # Step 3 form
            total_amount = Decimal("0.00")
            for mv in selected_movements:
                total_amount += Decimal(str(mv.amount.amount))

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
                    else:
                        group.collaborator_id = entity_id

                    group.save()

                    movements = FinancialMovement.objects.filter(id__in=movement_ids, workshop=self.workshop)
                    total_amount = Decimal("0.00")
                    first_mv = movements.first()

                    for mv in movements:
                        mv.movement_group = group
                        total_amount += Decimal(str(mv.amount.amount))
                        mv.save()

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
                        direction=first_mv.direction if first_mv else FinancialMovement.MovementDirection.DEBIT,
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

            # This will delete the MovementGroup and the GROUP_PARENT FinancialMovement (due to CASCADE)
            group.delete()

        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response
