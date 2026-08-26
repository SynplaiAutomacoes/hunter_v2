from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views import View
from decimal import Decimal
import re

from apps.core.workorder_numbers import format_workorder_reference
from apps.finance.models import FinancialMovement, MovementGroup
from apps.finance.forms.movement_group import GroupMovementStep3Form
from apps.suppliers.models import Supplier
from apps.collaborators.models import WorkshopCollaborator
from apps.customer.models import Customer
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workorder.models import WorkOrderPaymentMethod


class GroupMovementWizardView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = MovementGroup
    workshop_permission_codename = "add_financialmovement"
    workshop_permission_model = "financialmovement"

    def get(self, request, *args, **kwargs):
        return HttpResponse("Método não permitido", status=405)

    @staticmethod
    def _normalize_document(value: object) -> str:
        return re.sub(r"\D", "", str(value or ""))

    def _resolve_suppliers_from_sources(self, movements: list[FinancialMovement]) -> dict[int, Supplier]:
        """Resolve suppliers for legacy movements that only have a Source link.

        Sources are matched to suppliers by normalized CNPJ and always within the
        active workshop. A movement with a manually selected supplier is ignored.
        """
        source_documents = {
            movement.source_id: self._normalize_document(movement.source.cnpj)
            for movement in movements
            if movement.supplier_id is None and movement.source_id and self._normalize_document(movement.source.cnpj)
        }
        if not source_documents:
            return {}

        suppliers_by_document = {
            self._normalize_document(supplier.cnpj): supplier
            for supplier in Supplier.objects.filter(workshop=self.workshop)
            if self._normalize_document(supplier.cnpj)
        }
        return {
            movement.pk: suppliers_by_document[document]
            for movement in movements
            if movement.source_id and (document := source_documents.get(movement.source_id)) in suppliers_by_document
        }

    def post(self, request, *args, **kwargs):
        step = request.POST.get("step")

        if step == "3":
            movement_ids = request.POST.getlist("movements")
            entity_type = request.POST.get("entity_type")
            entity_id = request.POST.get("entity_id")

            fm_ids = [int(mid.split("_")[1]) for mid in movement_ids if mid.startswith("fm_")]
            pm_ids = [int(mid.split("_")[1]) for mid in movement_ids if mid.startswith("pm_")]
            fms = FinancialMovement.objects.filter(id__in=fm_ids, workshop=self.workshop)
            pms = WorkOrderPaymentMethod.objects.filter(id__in=pm_ids, workorder__workshop=self.workshop)
            total_amount = sum((Decimal(str(movement.amount.amount)) for movement in fms), Decimal("0.00")) + sum(
                (Decimal(str(payment.total_paid.amount)) for payment in pms), Decimal("0.00")
            )

            direction = FinancialMovement.MovementDirection.DEBIT
            first_movement = fms.first()
            if first_movement is not None:
                direction = first_movement.direction
            elif pms.exists():
                direction = FinancialMovement.MovementDirection.CREDIT

            form = GroupMovementStep3Form(request.POST, workshop=self.workshop, direction=direction, total_amount=total_amount)

            # We need to fetch the entity name to display it on form validation error
            entity_name = ""
            if entity_type == "supplier":
                entity_name = Supplier.objects.get(id=entity_id).name
            elif entity_type == "collaborator":
                entity_name = str(WorkshopCollaborator.objects.get(id=entity_id))
            elif entity_type == "customer":
                entity_name = Customer.objects.get(id=entity_id).name

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

                    first_direction = FinancialMovement.MovementDirection.DEBIT
                    
                    if fm_ids:
                        first_mv = fms.first()
                        if first_mv:
                            first_direction = first_mv.direction
                        for mv in fms:
                            mv.movement_group = group
                            mv.save()
                    
                    if pm_ids:
                        if pms:
                            first_direction = FinancialMovement.MovementDirection.CREDIT
                        for pm in pms:
                            pm.movement_group = group
                            pm.save()

                    payment_method = form.cleaned_data["payment_method"]
                    installments = form.cleaned_data["installment_schedule"]
                    for installment in installments:
                        installment_label = ""
                        if installment.total > 1:
                            installment_label = f" - Parcela {installment.number}/{installment.total}"
                        FinancialMovement.objects.create(
                            workshop=self.workshop,
                            user=request.user,
                            movement_kind=FinancialMovement.MovementKind.GROUP_PARENT,
                            movement_group=group,
                            description=f"Agrupamento - {group.name}{installment_label}",
                            financial_observation=group.description,
                            due_date=installment.due_date,
                            amount=installment.amount,
                            gross_amount=installment.amount,
                            direction=first_direction,
                            payment_method=payment_method,
                            supplier_id=group.supplier_id,
                            collaborator_id=group.collaborator_id,
                            is_paid=False,
                        )

                response = HttpResponse()
                response["HX-Refresh"] = "true"
                return response

            return render(request, "finance/reports/partials/group_step3.html", {
                "form": form,
                "movement_ids": movement_ids,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "total_amount": total_amount,
                "payment_method_installments": form.payment_method_installments,
                "initial_installments": form.installment_schedule_payload(),
            })

        # No step - entry point from reports_home.html checkbox selection
        checkbox_ids = request.POST.getlist("movement_ids")
        if not checkbox_ids:
            return render(request, "finance/reports/partials/group_error.html", {"error": "Selecione ao menos um lançamento."})

        fm_pks = []
        pm_pks = []
        for cid in checkbox_ids:
            if cid.startswith("financial-movement-"):
                fm_pks.append(int(cid.split("-")[-1]))
            elif cid.startswith("workorder-payment-"):
                pm_pks.append(int(cid.split("-")[-1]))
            elif cid.startswith("fm_"):
                fm_pks.append(int(cid.split("_")[1]))
            elif cid.startswith("pm_"):
                pm_pks.append(int(cid.split("_")[1]))

        # Fetch objects
        fms = list(
            FinancialMovement.objects.filter(pk__in=fm_pks, workshop=self.workshop).select_related(
                "source", "supplier", "collaborator", "workorder__budget__customer"
            )
        )
        pms = list(WorkOrderPaymentMethod.objects.filter(pk__in=pm_pks, workorder__workshop=self.workshop).select_related("workorder", "workorder__budget"))

        # Check if all requested items were found
        if len(fms) != len(fm_pks) or len(pms) != len(pm_pks):
            return render(request, "finance/reports/partials/group_error.html", {"error": "Um ou mais lançamentos selecionados não foram encontrados ou não pertencem a esta oficina."})

        # Check if any selected item is already grouped, paid, or is a group parent
        for fm in fms:
            if fm.movement_group_id is not None:
                return render(request, "finance/reports/partials/group_error.html", {"error": f"O lançamento '{fm.description}' já faz parte de um agrupamento."})
            if fm.is_paid:
                return render(request, "finance/reports/partials/group_error.html", {"error": f"O lançamento '{fm.description}' já está pago."})
            if fm.movement_kind == FinancialMovement.MovementKind.GROUP_PARENT:
                return render(request, "finance/reports/partials/group_error.html", {"error": f"Não é possível agrupar o consolidado '{fm.description}'."})

        for pm in pms:
            if pm.movement_group_id is not None:
                return render(request, "finance/reports/partials/group_error.html", {"error": f"O plano de pagamento da {format_workorder_reference(pm.workorder)} já faz parte de um agrupamento."})

        # Validate direction consistency
        directions = set()
        for fm in fms:
            directions.add(fm.direction)
        if pms:
            # WorkOrderPaymentMethod is always CREDIT (inflow)
            directions.add("CREDIT")

        if len(directions) > 1:
            return render(request, "finance/reports/partials/group_error.html", {"error": "Todos os lançamentos selecionados devem ser do mesmo tipo (Crédito ou Débito)."})

        # Legacy imported movements may have only the automatic Source relation.
        # Resolve the already registered supplier by CNPJ so the user does not need
        # to edit each movement before grouping.
        resolved_suppliers = self._resolve_suppliers_from_sources(fms)

        # Validate entity consistency
        candidate_entities = []
        for fm in fms:
            item_candidates = set()
            supplier = fm.supplier if fm.supplier_id else resolved_suppliers.get(fm.pk)
            if supplier is not None:
                item_candidates.add(("supplier", supplier.id, supplier.name))
            if fm.collaborator_id:
                item_candidates.add(("collaborator", fm.collaborator_id, str(fm.collaborator)))
            if fm.workorder_id and fm.workorder.budget_id and fm.workorder.budget.customer_id:
                item_candidates.add(("customer", fm.workorder.budget.customer_id, fm.workorder.budget.customer.name))
            candidate_entities.append(item_candidates)

        for pm in pms:
            item_candidates = set()
            if pm.workorder_id and pm.workorder.budget_id and pm.workorder.budget.customer_id:
                item_candidates.add(("customer", pm.workorder.budget.customer_id, pm.workorder.budget.customer.name))
            candidate_entities.append(item_candidates)

        if not candidate_entities:
            return render(request, "finance/reports/partials/group_error.html", {"error": "Nenhum lançamento selecionado."})

        common_keys = set((c[0], c[1]) for c in candidate_entities[0])
        for item_candidates in candidate_entities[1:]:
            item_keys = set((c[0], c[1]) for c in item_candidates)
            common_keys = common_keys & item_keys

        if not common_keys:
            return render(request, "finance/reports/partials/group_error.html", {"error": "Todos os lançamentos selecionados devem pertencer ao mesmo Fornecedor, Colaborador ou Cliente."})

        # Persist only the safe, CNPJ-based matches that allowed this grouping.
        # Existing manual supplier links are intentionally never changed.
        for fm in fms:
            supplier = resolved_suppliers.get(fm.pk)
            if supplier is not None and fm.supplier_id is None:
                fm.supplier = supplier
                fm.save(update_fields=["supplier"])

        # Pick a common key
        selected_key = list(common_keys)[0]
        entity_type, entity_id = selected_key

        # Find name of this entity from the candidates
        entity_name = ""
        for item_candidates in candidate_entities:
            for c in item_candidates:
                if c[0] == entity_type and c[1] == entity_id:
                    entity_name = c[2]
                    break
            if entity_name:
                break

        # Calculate total amount
        total_amount = Decimal("0.00")
        for fm in fms:
            total_amount += Decimal(str(fm.amount.amount))
        for pm in pms:
            total_amount += Decimal(str(pm.total_paid.amount))

        normalized_movement_ids = [f"fm_{fm.id}" for fm in fms] + [f"pm_{pm.id}" for pm in pms]

        direction = next(iter(directions), FinancialMovement.MovementDirection.DEBIT)
        form = GroupMovementStep3Form(workshop=self.workshop, direction=direction, total_amount=total_amount)
        return render(request, "finance/reports/partials/group_step3.html", {
            "form": form,
            "movement_ids": normalized_movement_ids,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "total_amount": total_amount,
            "entity_name": entity_name,
            "payment_method_installments": form.payment_method_installments,
            "initial_installments": form.installment_schedule_payload(),
        })


class GroupMovementDeleteView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = MovementGroup
    workshop_permission_codename = "delete_financialmovement"
    workshop_permission_model = "financialmovement"

    def post(self, request, pk, *args, **kwargs):
        group = get_object_or_404(MovementGroup, pk=pk, workshop=self.workshop)

        if group.financial_movements.filter(
            movement_kind=FinancialMovement.MovementKind.GROUP_PARENT,
            is_paid=True,
        ).exists():
            response = HttpResponse()
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = '{"showToast":{"message":"Não é possível desagrupar: existe uma parcela já paga.","type":"warning"}}'
            return response

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
