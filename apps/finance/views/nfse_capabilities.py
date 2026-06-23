from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.finance.forms.nfse_capabilities import NfseMunicipalCapabilityForm
from apps.finance.models.finance import NfseMunicipalCapability, WebmaniaCompany
from apps.workshops.mixin import WorkshopScopedMixin


class NfseMunicipalCapabilityListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = NfseMunicipalCapability
    template_name = "finance/nfse_capabilities/list.html"
    context_object_name = "capabilities"
    workshop_permission_codename = "manage_nfse_capabilities"

    def get_queryset(self):
        return super().get_queryset().select_related("company").order_by("state", "city_name", "provider")

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("Municipio", attr="city_name"),
            TableColumn("UF", attr="state"),
            TableColumn("Codigo IBGE", attr="city_code"),
            TableColumn("Provedor", attr="provider"),
            TableColumn("Emissao", attr="emission_enabled"),
            TableColumn("Ativa", attr="is_active"),
        ]
        context["actions"] = [TableActionDefaults.edit("finance:nfse_capability_update")]
        return context


class NfseMunicipalCapabilityCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = NfseMunicipalCapability
    form_class = NfseMunicipalCapabilityForm
    template_name = "finance/nfse_capabilities/form.html"
    success_url = reverse_lazy("finance:nfse_capability_list")
    workshop_permission_codename = "manage_nfse_capabilities"

    def get_initial(self) -> dict[str, object]:
        initial = super().get_initial()
        company = self._company()
        initial.update({"city_name": company.cidade, "state": company.uf})
        return initial

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.company = self._company()
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"workshop": self.workshop, "company": self._company()})
        return kwargs

    def _company(self) -> WebmaniaCompany:
        company = WebmaniaCompany.objects.filter(workshop=self.workshop).first()
        if company is None:
            raise ImproperlyConfigured("Configure a empresa Webmania da oficina antes das capacidades NFS-e.")
        return company


class NfseMunicipalCapabilityUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = NfseMunicipalCapability
    form_class = NfseMunicipalCapabilityForm
    template_name = "finance/nfse_capabilities/form.html"
    success_url = reverse_lazy("finance:nfse_capability_list")
    workshop_permission_codename = "manage_nfse_capabilities"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        company = WebmaniaCompany.objects.filter(workshop=self.workshop).first()
        if company is None:
            raise ImproperlyConfigured("Configure a empresa Webmania da oficina antes das capacidades NFS-e.")
        kwargs.update({"workshop": self.workshop, "company": company})
        return kwargs
