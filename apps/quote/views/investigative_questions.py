from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.quote.forms.investigative_questions import InvestigativeQuestionForm
from apps.quote.models.investigative_questions import InvestigativeQuestion
from apps.workshops.mixin import WorkshopScopedMixin


class InvestigativeQuestionListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = InvestigativeQuestion
    template_name = "investigative_questions/investigative_questions_list.html"
    context_object_name = "questions"
    htmx_template_name = "investigative_questions/partials/investigative_questions_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label="Ordem", attr="order"),
            TableColumn(label="Pergunta", attr="text"),
            TableColumn(label="Tipo", attr="get_response_type_display"),
            TableColumn(label="Ativa", attr="is_active"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("quote:investigative_question_update"),
            TableActionDefaults.delete("quote:investigative_question_delete"),
        ]

        return context


class InvestigativeQuestionCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = InvestigativeQuestion
    form_class = InvestigativeQuestionForm
    template_name = "investigative_questions/investigative_questions_create.html"
    success_url = reverse_lazy("quote:investigative_question_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class InvestigativeQuestionUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = InvestigativeQuestion
    form_class = InvestigativeQuestionForm
    template_name = "investigative_questions/investigative_questions_update.html"
    success_url = reverse_lazy("quote:investigative_question_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class InvestigativeQuestionDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = InvestigativeQuestion
    success_url = reverse_lazy("quote:investigative_question_list")

    htmx_template_name = "investigative_questions/partials/investigative_questions_delete_modal.html"
    htmx_trigger = "investigative-questions-table-refresh"
