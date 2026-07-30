from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.infrastructure.query_filters import apply_is_active_filter
from apps.core.presentation.mixins import BaseModalFormView, HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.workshops.forms.review_plans import QuickReviewPlanForm, ReviewPlanForm
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.review_plans import ReviewPlan


def build_review_plan_saved_trigger(review_plan: ReviewPlan) -> str:
    return json.dumps(
        {
            "reviewPlanSaved": {
                "id": str(review_plan.pk),
                "name": review_plan.name,
            }
        }
    )


class ReviewPlanListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = ReviewPlan
    template_name = "review_plans/review_plan_list.html"
    context_object_name = "review_plans"
    htmx_template_name = "review_plans/partials/review_plan_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(label=ReviewPlan.name.field.verbose_name, attr="name"),
            TableColumn(label=ReviewPlan.validity_days.field.verbose_name, attr="validity_days"),
            TableColumn(label=ReviewPlan.validity_km.field.verbose_name, attr="validity_km"),
            TableColumn(label=ReviewPlan.notification_lead_days.field.verbose_name, attr="notification_lead_days"),
            TableColumn(label=ReviewPlan.is_active.field.verbose_name, attr="is_active"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("workshops:review_plan_update"),
            TableActionDefaults.delete("workshops:review_plan_delete"),
        ]
        return context


class ReviewPlanCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = ReviewPlan
    form_class = ReviewPlanForm
    template_name = "review_plans/review_plan_create.html"
    success_url = reverse_lazy("workshops:review_plan_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class ReviewPlanUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = ReviewPlan
    form_class = ReviewPlanForm
    template_name = "review_plans/review_plan_update.html"
    success_url = reverse_lazy("workshops:review_plan_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        from apps.customer.services.oil_change import recalculate_oil_forecasts_for_review_plan

        recalculate_oil_forecasts_for_review_plan(review_plan=self.object)
        return response


class ReviewPlanDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = ReviewPlan
    success_url = reverse_lazy("workshops:review_plan_list")
    htmx_template_name = "review_plans/partials/review_plan_delete_modal.html"
    htmx_trigger = "review-plans-table-refresh"


class QuickReviewPlanCreateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, CreateView):
    model = ReviewPlan
    form_class = QuickReviewPlanForm
    template_name = "review_plans/partials/quick_review_plan_modal_form.html"
    success_url = reverse_lazy("workshops:review_plan_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            form.instance.workshop = self.workshop
            return super().form_valid(form)

        form.instance.workshop = self.workshop
        review_plan = form.save()
        self.object = review_plan

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_review_plan_saved_trigger(review_plan)
        return response


class QuickReviewPlanUpdateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, UpdateView):
    model = ReviewPlan
    form_class = QuickReviewPlanForm
    template_name = "review_plans/partials/quick_review_plan_modal_form.html"
    success_url = reverse_lazy("workshops:review_plan_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            response = super().form_valid(form)
            from apps.customer.services.oil_change import recalculate_oil_forecasts_for_review_plan

            recalculate_oil_forecasts_for_review_plan(review_plan=self.object)
            return response

        form.instance.workshop = self.workshop
        review_plan = form.save()
        self.object = review_plan

        from apps.customer.services.oil_change import recalculate_oil_forecasts_for_review_plan

        recalculate_oil_forecasts_for_review_plan(review_plan=review_plan)

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_review_plan_saved_trigger(review_plan)
        return response
