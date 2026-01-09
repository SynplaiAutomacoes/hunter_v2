from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.collaborators.forms import WorkshopCollaboratorCreateForm, WorkshopCollaboratorUpdateForm
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.util import User, get_active_workshop_or_404, has_workshop_perm


class WorkshopCollaboratorListView(LoginRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkshopCollaborator
    template_name = "collaborators/collaborator_list.html"
    context_object_name = "collaborators"

    htmx_template_name = "collaborators/partials/collaborator_table.html"

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label="collaborators",
            model=WorkshopCollaborator._meta.model_name,
            codename="view_workshopcollaborator",
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(workshop=self.workshop).order_by("name")

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


class WorkshopCollaboratorCreateView(LoginRequiredMixin, CreateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorCreateForm
    template_name = "collaborators/collaborator_create.html"
    success_url = reverse_lazy("collaborators:collaborator_list")

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label="collaborators",
            model=WorkshopCollaborator._meta.model_name,
            codename="add_workshopcollaborator",
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.request.user.account
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.workshop = self.workshop

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


class WorkshopCollaboratorUpdateView(LoginRequiredMixin, UpdateView):
    model = WorkshopCollaborator
    form_class = WorkshopCollaboratorUpdateForm
    template_name = "collaborators/collaborator_update.html"
    success_url = reverse_lazy("collaborators:collaborator_list")

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label="collaborators",
            model=WorkshopCollaborator._meta.model_name,
            codename="change_workshopcollaborator",
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                workshop=self.workshop,
                workshop__account=self.request.user.account,
            )
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.request.user.account
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            collaborator = self.object

            if collaborator.user_id:
                if collaborator.system_access:
                    user = collaborator.user
                    user.username = form.cleaned_data["system_username"]
                    user.email = collaborator.email or user.email
                    user.is_active = collaborator.is_active
                    user.save(update_fields=["username", "email", "is_active"])

                    role = form.cleaned_data["role"]
                    WorkshopMember.objects.update_or_create(
                        user=user,
                        workshop=self.workshop,
                        defaults={
                            "role": role,
                            "is_active": collaborator.is_active,
                        },
                    )
                else:
                    WorkshopMember.objects.filter(user=collaborator.user, workshop=self.workshop).update(is_active=False)
                    collaborator.user.is_active = False
                    collaborator.user.save(update_fields=["is_active"])

            return response


class WorkshopCollaboratorDeleteView(LoginRequiredMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopCollaborator
    success_url = reverse_lazy("collaborators:collaborator_list")

    htmx_template_name = "collaborators/partials/collaborator_delete_modal.html"
    htmx_trigger = "collaborators-table-refresh"

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label="collaborators",
            model=WorkshopCollaborator._meta.model_name,
            codename="delete_workshopcollaborator",
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                workshop=self.workshop,
                workshop__account=self.request.user.account,
            )
        )

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        with transaction.atomic():
            if self.object.user_id:
                WorkshopMember.objects.filter(user=self.object.user, workshop=self.workshop).update(is_active=False)
                self.object.user.is_active = False
                self.object.user.save(update_fields=["is_active"])
            return super().delete(request, *args, **kwargs)
