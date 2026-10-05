from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView

from apps.finance.forms.financial_transfer import FinancialTransferForm
from apps.finance.models.financial_transfer import FinancialTransfer
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.mixin import WorkshopScopedMixin


class FinancialTransferCreateView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    form_class = FinancialTransferForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "add_financialmovement"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get(self, request, *args, **kwargs):
        return redirect(reverse("finance:cash_flow"))

    def form_invalid(self, form):
        messages.error(self.request, "Não foi possível concluir a transferência. Revise os dados informados e tente novamente.")
        return redirect(reverse("finance:cash_flow"))

    def form_valid(self, form):
        form.save(user=self.request.user)
        messages.success(self.request, "Transferência registrada no extrato das contas.")
        return redirect(reverse("finance:cash_flow"))


class FinancialTransferReverseView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    """Creates the inverse transaction while retaining the original record."""

    form_class = FinancialTransferForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "add_financialmovement"

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            transfer = get_object_or_404(
                FinancialTransfer.objects.select_for_update().select_related("source_account", "destination_account"),
                pk=kwargs["pk"],
                workshop=self.workshop,
            )
            if transfer.reversal_of_id or FinancialTransfer.objects.filter(reversal_of=transfer).exists():
                messages.error(request, "Esta transferência já foi estornada.")
                return redirect(reverse("finance:cash_flow"))
            FinancialTransfer.objects.create(
                workshop=self.workshop,
                user=request.user,
                source_account=transfer.destination_account,
                destination_account=transfer.source_account,
                transfer_date=timezone.localdate(),
                amount=transfer.amount,
                description="",
                reversal_of=transfer,
            )
        messages.success(request, "Estorno registrado no extrato das contas.")
        return redirect(reverse("finance:cash_flow"))
