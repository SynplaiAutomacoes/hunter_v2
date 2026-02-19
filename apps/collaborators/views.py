from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.collaborators.forms import WorkshopCollaboratorCreateForm, WorkshopCollaboratorModalForm, WorkshopCollaboratorUpdateForm
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin

AuthUser = get_user_model()
User = get_user_model()


# TODO: Validar melhor o fluxo de edição e criação com relação ao acesso ao sistema.
class WorkshopCollaboratorListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkshopCollaborator
    template_name = "collaborators/collaborator_list.html"
    context_object_name = "collaborators"

    htmx_template_name = "collaborators/partials/collaborator_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label=WorkshopCollaborator.name.field.verbose_name, attr=WorkshopCollaborator.name.field.name),
            TableColumn(label=WorkshopCollaborator.cpf.field.verbose_name, attr=WorkshopCollaborator.cpf.field.name, format="cpf"),
            TableColumn(label=WorkshopCollaborator.position.field.verbose_name, attr=WorkshopCollaborator.position.field.name),
            TableColumn(label=WorkshopCollaborator.is_active.field.verbose_name, attr=WorkshopCollaborator.is_active.field.name),
            TableColumn(label=WorkshopCollaborator.system_access.field.verbose_name, attr=WorkshopCollaborator.system_access.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("collaborators:collaborator_update"),
            TableActionDefaults.delete("collaborators:collaborator_delete"),
        ]

        return context


class WorkshopCollaboratorCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorCreateForm
    template_name = "collaborators/collaborator_create.html"
    success_url = reverse_lazy("collaborators:collaborator_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.request.user.account
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.workshop = self.workshop

            if form.instance.salary is None:
                form.instance.salary = 0

            if form.cleaned_data.get("system_access"):
                username = form.cleaned_data["system_username"]
                password = form.cleaned_data["password1"]
                role = form.cleaned_data["role"]

                user = User(
                    username=username,
                    cpf=form.cleaned_data["cpf"],
                    email=form.cleaned_data.get("email") or "",
                    account=self.workshop.account,
                    is_active=form.cleaned_data.get("is_active", True),
                )
                parts = (form.cleaned_data.get("name") or "").split(" ", 1)
                user.first_name = parts[0] if parts else ""
                user.last_name = parts[1] if len(parts) > 1 else ""
                user.set_password(password)
                user.save()

                form.instance.user = user

                response = super().form_valid(form)

                WorkshopMember.objects.update_or_create(
                    user=user,
                    workshop=self.workshop,
                    defaults={
                        "role": role,
                        "is_active": self.object.is_active,
                    },
                )
            else:
                form.instance.user = None
                response = super().form_valid(form)

        return response


class WorkshopCollaboratorUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorUpdateForm
    template_name = "collaborators/collaborator_update.html"
    success_url = reverse_lazy("collaborators:collaborator_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.request.user.account
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            if form.instance.salary is None:
                form.instance.salary = 0

            response = super().form_valid(form)
            collaborator = self.object

            if collaborator.system_access:
                role = form.cleaned_data["role"]

                if collaborator.user_id:
                    user = collaborator.user
                    user.username = form.cleaned_data["system_username"]
                    user.email = collaborator.email or user.email
                    user.is_active = collaborator.is_active
                    user.save(update_fields=["username", "email", "is_active"])
                else:
                    user = User(
                        username=form.cleaned_data["system_username"],
                        cpf=collaborator.cpf,
                        email=collaborator.email or "",
                        account=self.workshop.account,
                        is_active=collaborator.is_active,
                    )
                    parts = (collaborator.name or "").split(" ", 1)
                    user.first_name = parts[0] if parts else ""
                    user.last_name = parts[1] if len(parts) > 1 else ""
                    user.set_password(form.cleaned_data["password1"])
                    user.save()

                    collaborator.user = user
                    collaborator.save(update_fields=["user"])

                WorkshopMember.objects.update_or_create(
                    user=user,
                    workshop=self.workshop,
                    defaults={
                        "role": role,
                        "is_active": collaborator.is_active,
                    },
                )
            elif collaborator.user_id:
                WorkshopMember.objects.filter(user=collaborator.user, workshop=self.workshop).update(is_active=False)
                collaborator.user.is_active = False
                collaborator.user.save(update_fields=["is_active"])

            return response


class WorkshopCollaboratorDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopCollaborator
    success_url = reverse_lazy("collaborators:collaborator_list")

    htmx_template_name = "collaborators/partials/collaborator_delete_modal.html"
    htmx_trigger = "collaborators-table-refresh"

    def _delete_collaborator_and_related(self, *, using: str):
        user_id = self.object.user_id
        workshop_id = self.object.workshop_id

        with transaction.atomic(using=using):
            if user_id:
                WorkshopMember.objects.using(using).filter(user_id=user_id, workshop_id=workshop_id).delete()
                AuthUser.objects.using(using).filter(pk=user_id).delete()

            self.object.delete(using=using)

    def form_valid(self, form):
        using = self.object._state.db
        self._delete_collaborator_and_related(using=using)

        if bool(getattr(self.request, "htmx", False)):
            response = HttpResponse()
            if self.htmx_trigger:
                response["HX-Trigger"] = self.htmx_trigger
            return response

        return HttpResponseRedirect(self.get_success_url())


class WorkshopCollaboratorModalCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorModalForm
    template_name = "collaborators/partials/collaborator_create_modal.html"

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.workshop = self.workshop

            if self.object.salary is None:
                self.object.salary = 0

            self.object.save()

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"collaboratorSaved": {"id": str(self.object.pk), "name": self.object.name}})
        return response


class WorkshopCollaboratorModalUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorModalForm
    template_name = "collaborators/partials/collaborator_update_modal.html"

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)

            if self.object.salary is None:
                self.object.salary = 0

            self.object.save()

            if self.object.user_id:
                user = self.object.user
                if self.object.email and user.email != self.object.email:
                    user.email = self.object.email
                    user.save(update_fields=["email"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"collaboratorSaved": {"id": str(self.object.pk), "name": self.object.name}})
        return response
