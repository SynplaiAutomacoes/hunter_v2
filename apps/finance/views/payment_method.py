from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.query_filters import apply_is_active_filter
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms.payment_method import PaymentMethodForm
from apps.finance.models.payment_method import PaymentMethod
from apps.workshops.mixin import WorkshopScopedMixin


class PaymentMethodListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = PaymentMethod
    template_name = "finance/payment_methods/payment_methods_list.html"
    context_object_name = "payment_methods"
    htmx_template_name = "finance/partials/payment_methods/payment_methods_table.html"
    workshop_permission_codename = "view_paymentmethod"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("description")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(PaymentMethod.description.field.verbose_name, attr=PaymentMethod.description.field.name),
            TableColumn(PaymentMethod.installments_count.field.verbose_name, attr=PaymentMethod.installments_count.field.name),
            TableColumn(PaymentMethod.is_active.field.verbose_name, attr=PaymentMethod.is_active.field.name),
        ]
        context["actions"] = [TableActionDefaults.edit("finance:payment_methods_update")]
        return context


class PaymentMethodCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "finance/payment_methods/payment_methods_create.html"
    success_url = reverse_lazy("finance:payment_methods_list")
    workshop_permission_codename = "add_paymentmethod"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class PaymentMethodUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "finance/payment_methods/payment_methods_update.html"
    success_url = reverse_lazy("finance:payment_methods_list")
    workshop_permission_codename = "change_paymentmethod"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs
