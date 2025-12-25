from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView

from apps.workshops.forms import WorkshopCreateForm
from apps.workshops.models import Workshop


class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopCreateForm
    template_name = "workshop_create.html"
    success_url = reverse_lazy("workshops:create")
