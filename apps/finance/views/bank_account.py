from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.query_filters import apply_is_active_filter
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms.bank_account import BankAccountForm
from apps.finance.models.bank_account import BankAccount
from apps.workshops.mixin import WorkshopScopedMixin


class BankAccountListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = BankAccount
    template_name = "finance/bank_account/bank_account_list.html"
    context_object_name = "bank_account"
    htmx_template_name = "finance/partials/bank_account/bank_account_table.html"
    workshop_permission_codename = "view_bankaccount"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("bank_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(BankAccount.bank_name.field.verbose_name, attr=BankAccount.bank_name.field.name),
            TableColumn(BankAccount.agency.field.verbose_name, attr=BankAccount.agency.field.name),
            TableColumn(BankAccount.account_number.field.verbose_name, attr=BankAccount.account_number.field.name),
            TableColumn(BankAccount.account_type.field.verbose_name, attr="get_account_type_display"),
            TableColumn(BankAccount.is_active.field.verbose_name, attr=BankAccount.is_active.field.name),
        ]
        context["actions"] = [TableActionDefaults.edit("finance:bank_account_update")]
        return context


class BankAccountCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = "finance/bank_account/bank_account_create.html"
    success_url = reverse_lazy("finance:bank_account_list")
    workshop_permission_codename = "add_bankaccount"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class BankAccountUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = "finance/bank_account/bank_account_update.html"
    success_url = reverse_lazy("finance:bank_account_list")
    workshop_permission_codename = "change_bankaccount"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs
