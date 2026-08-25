from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.infrastructure.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.core.presentation.tables import TableActionDefaults
from apps.core.workorder_numbers import resolve_workorder_number
from apps.core.templatetags.table_tags import TableColumn
from apps.messaging.models import SatisfactionReview
from apps.workshops.mixin import WorkshopScopedMixin


class PublicSatisfactionReviewForm(forms.Form):
    rating = forms.TypedChoiceField(
        label="Sua avaliação",
        choices=[(i, str(i)) for i in range(1, 6)],
        coerce=int,
        required=True,
        error_messages={"required": "Selecione uma nota de 1 a 5."},
    )
    comment = forms.CharField(
        label="Comentário (opcional)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "textarea textarea-bordered w-full",
                "placeholder": "Conte como foi sua experiência...",
            }
        ),
    )


class PublicSatisfactionReviewView(View):
    template_name = "messaging/public/satisfaction_review.html"
    thanks_template_name = "messaging/public/satisfaction_review_thanks.html"

    def get_review(self, token: str) -> SatisfactionReview:
        return get_object_or_404(
            SatisfactionReview.objects.select_related("workshop", "customer", "workorder"),
            public_token=token,
        )

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        review = self.get_review(token)
        if review.status == SatisfactionReview.Status.SUBMITTED:
            return self._render_thanks(request, review=review, already_submitted=True)
        if review.status in {SatisfactionReview.Status.CANCELLED, SatisfactionReview.Status.EXPIRED}:
            raise Http404("Avaliação indisponível.")

        form = PublicSatisfactionReviewForm()
        return render(request, self.template_name, self._form_context(review=review, form=form))

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        review = self.get_review(token)
        if review.status == SatisfactionReview.Status.SUBMITTED:
            return self._render_thanks(request, review=review, already_submitted=True)
        if review.status in {SatisfactionReview.Status.CANCELLED, SatisfactionReview.Status.EXPIRED}:
            raise Http404("Avaliação indisponível.")

        form = PublicSatisfactionReviewForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._form_context(review=review, form=form),
                status=400,
            )

        rating = int(form.cleaned_data["rating"])
        comment = str(form.cleaned_data.get("comment") or "").strip()
        workshop = review.workshop
        min_rating = int(getattr(workshop, "google_review_min_rating", 4) or 4)
        google_url = str(getattr(workshop, "google_review_url", "") or "").strip()
        show_google = bool(google_url and rating >= min_rating)

        review.rating = rating
        review.comment = comment
        review.status = SatisfactionReview.Status.SUBMITTED
        review.submitted_at = timezone.now()
        review.google_cta_shown = show_google
        review.save(
            update_fields=[
                "rating",
                "comment",
                "status",
                "submitted_at",
                "google_cta_shown",
                "atualizado_em",
            ]
        )
        return self._render_thanks(request, review=review, already_submitted=False)

    def _form_context(self, *, review: SatisfactionReview, form: PublicSatisfactionReviewForm) -> dict[str, Any]:
        return {
            "review": review,
            "form": form,
            "workshop": review.workshop,
            "customer": review.customer,
        }

    def _render_thanks(self, request: HttpRequest, *, review: SatisfactionReview, already_submitted: bool) -> HttpResponse:
        workshop = review.workshop
        google_url = str(getattr(workshop, "google_review_url", "") or "").strip()
        show_google = bool(review.google_cta_shown or (review.rating is not None and google_url and int(review.rating) >= int(getattr(workshop, "google_review_min_rating", 4) or 4)))
        return render(
            request,
            self.thanks_template_name,
            {
                "review": review,
                "workshop": workshop,
                "customer": review.customer,
                "google_review_url": google_url if show_google else "",
                "show_google_cta": show_google and bool(google_url),
                "already_submitted": already_submitted,
            },
        )


class SatisfactionReviewListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = SatisfactionReview
    template_name = "messaging/satisfaction_review_list.html"
    context_object_name = "satisfaction_reviews"
    htmx_template_name = "messaging/partials/satisfaction_review_table.html"
    # Reuse message-template view permission so existing workshop roles keep access.
    workshop_permission_codename = "view_messagetemplate"
    workshop_permission_app_label = "messaging"
    workshop_permission_model = "messagetemplate"

    def get_queryset(self) -> QuerySet[SatisfactionReview]:
        queryset = super().get_queryset().select_related("customer", "workorder", "workorder__budget", "workshop")

        search_query = str(self.request.GET.get("q") or "").strip()
        if search_query:
            queryset = apply_text_search(
                queryset,
                search_value=search_query,
                lookups=("customer__name", "comment"),
            )

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=(
                QueryParamFilter(
                    param_name="status",
                    lookup="status",
                    kind="choice",
                    allowed_values=frozenset(value for value, _ in SatisfactionReview.Status.choices),
                ),
                QueryParamFilter(
                    param_name="rating",
                    lookup="rating",
                    kind="choice",
                    allowed_values=frozenset(str(i) for i in range(1, 6)),
                ),
            ),
        )
        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("Cliente", attr=lambda review: review.customer.name),
            TableColumn("O.S.", attr=lambda review: str(resolve_workorder_number(review.workorder))),
            TableColumn("Nota", attr="rating_display", searchable=False),
            TableColumn("Status", attr=lambda review: review.get_status_display(), searchable=False),
            TableColumn("Respondida em", attr="submitted_at_display", searchable=False),
            TableColumn("Criada em", attr="created_at_display", searchable=False),
        ]
        context["actions"] = [
            TableActionDefaults.view(
                "messaging:satisfaction_review_detail_modal",
                hx_target="#modal-container",
                hx_swap="innerHTML",
                hx_push_url="false",
            ),
        ]
        context["status_choices"] = SatisfactionReview.Status.choices
        context["rating_choices"] = [(str(i), str(i)) for i in range(1, 6)]
        return context


class SatisfactionReviewDetailModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = SatisfactionReview
    workshop_permission_codename = "view_messagetemplate"
    workshop_permission_app_label = "messaging"
    workshop_permission_model = "messagetemplate"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        review = get_object_or_404(
            SatisfactionReview.objects.select_related("customer", "workorder", "workorder__budget", "workshop"),
            pk=pk,
            workshop=self.workshop,
        )
        return render(
            request,
            "messaging/partials/satisfaction_review_detail_modal.html",
            {"review": review},
        )
