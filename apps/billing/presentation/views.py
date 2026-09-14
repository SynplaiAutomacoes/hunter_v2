from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.accounts.mixins import AccountOwnerRequiredMixin
from apps.billing.access import get_account_subscription, invalidate_subscription_cache
from apps.billing.domain.contracts import BillingPortalRequest, BillingServiceError, CheckoutSessionRequest
from apps.billing.domain.plans import Plan
from apps.billing.infrastructure.providers import get_billing_service
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.core.templatetags.table_tags import TableColumn
from apps.workshops.views.system_management import SystemManagementMixin

SUBSCRIBER_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(
        param_name="status",
        lookup="status",
        kind="choice",
        allowed_values=frozenset(SubscriptionStatus.values),
    ),
    QueryParamFilter(
        param_name="plan",
        lookup="plan",
        kind="choice",
        allowed_values=frozenset(SubscriptionPlan.values),
    ),
)

STATUS_BADGE_CLASS = {
    SubscriptionStatus.ACTIVE: "badge-success",
    SubscriptionStatus.PAST_DUE: "badge-warning",
    SubscriptionStatus.CANCELED: "badge-error",
    SubscriptionStatus.INCOMPLETE: "badge-ghost",
    SubscriptionStatus.GRANDFATHERED: "badge-info",
}


class PlansView(LoginRequiredMixin, TemplateView):
    template_name = "billing/plans.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        subscription = get_account_subscription(self.request)
        context["subscription"] = subscription
        context["is_account_owner"] = bool(getattr(self.request.user, "is_superuser", False) or (getattr(self.request.user, "account_id", None) and getattr(self.request.user, "account", None) and self.request.user.account.owner_id == self.request.user.id) or getattr(self.request.user, "is_account_owner", False))
        context["plans"] = [
            {
                "key": Plan.BASIC,
                "name": "Orçamento",
                "description": "Tudo o que você precisa para cadastrar produtos, serviços, kits, termos e emitir orçamentos.",
                "features": [
                    "Clientes e veículos",
                    "Produtos, serviços e kits",
                    "Termos de assinatura",
                    "Fluxo completo de orçamento",
                    "Checklist e perguntas investigativas",
                ],
            },
            {
                "key": Plan.FULL,
                "name": "Completo",
                "description": "Libera o sistema inteiro: ordens de serviço, estoque, financeiro, fiscal, agendamentos e mais.",
                "features": [
                    "Tudo do plano Orçamento",
                    "Ordens de serviço",
                    "Estoque e fornecedores",
                    "Financeiro, DRE e emissão fiscal",
                    "Agendamentos e mensagens WhatsApp",
                ],
            },
        ]
        return context


class CheckoutSessionView(AccountOwnerRequiredMixin, View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        plan = str(request.POST.get("plan") or "").strip()
        if plan not in (Plan.BASIC, Plan.FULL):
            messages.error(request, "Selecione um plano válido.")
            return redirect("billing:plans")

        account = request.user.account
        subscription = get_account_subscription(request)
        success_url = request.build_absolute_uri(reverse("billing:checkout_success")) + "?session_id={CHECKOUT_SESSION_ID}"
        cancel_url = request.build_absolute_uri(reverse("billing:plans"))

        try:
            result = get_billing_service().create_checkout_session(
                CheckoutSessionRequest(
                    account_id=account.pk,
                    plan=plan,
                    customer_email=request.user.email or "",
                    success_url=success_url,
                    cancel_url=cancel_url,
                    stripe_customer_id=(subscription.stripe_customer_id if subscription else ""),
                    customer_name=request.user.get_full_name() or request.user.username,
                )
            )
        except BillingServiceError as exc:
            messages.error(request, f"Não foi possível iniciar o pagamento: {exc}")
            return redirect("billing:plans")

        if not result.url:
            messages.error(request, "A Stripe não retornou uma URL de checkout.")
            return redirect("billing:plans")

        return HttpResponseRedirect(result.url)


class CheckoutSuccessView(AccountOwnerRequiredMixin, TemplateView):
    template_name = "billing/checkout_success.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        invalidate_subscription_cache(request)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["subscription"] = get_account_subscription(self.request)
        context["home_url"] = reverse("budget:budget_list")
        return context


class BillingPortalView(AccountOwnerRequiredMixin, View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        subscription = get_account_subscription(request)
        if subscription is None or not subscription.stripe_customer_id:
            messages.error(request, "Nenhuma assinatura Stripe encontrada para esta conta.")
            return redirect("billing:plans")

        try:
            result = get_billing_service().create_billing_portal_session(
                BillingPortalRequest(
                    stripe_customer_id=subscription.stripe_customer_id,
                    return_url=request.build_absolute_uri(reverse("billing:plans")),
                )
            )
        except BillingServiceError as exc:
            messages.error(request, f"Não foi possível abrir o portal de cobrança: {exc}")
            return redirect("billing:plans")

        return HttpResponseRedirect(result.url)


class UpgradeRequiredView(LoginRequiredMixin, TemplateView):
    template_name = "billing/upgrade_required.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["is_account_owner"] = bool(getattr(self.request.user, "is_account_owner", False))
        return context


class SubscriberListView(SystemManagementMixin, HtmxTemplateResponseMixin, ListView):
    model = AccountSubscription
    template_name = "billing/subscriber_list.html"
    context_object_name = "subscriptions"
    htmx_template_name = "billing/partials/subscriber_table.html"

    def get_queryset(self):
        queryset = AccountSubscription.objects.select_related("account", "account__owner").annotate(workshop_count=Count("account__workshops", distinct=True)).order_by("-criado_em")

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            queryset = apply_text_search(
                queryset,
                search_value=search_query,
                lookups=(
                    "account__name",
                    "account__owner__first_name",
                    "account__owner__last_name",
                    "account__owner__email",
                    "stripe_customer_id",
                ),
            )

        return apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=SUBSCRIBER_LIST_FILTERS,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        status_counts = {row["status"]: row["total"] for row in AccountSubscription.objects.values("status").annotate(total=Count("id"))}
        context["status_stats"] = [
            {"label": "Ativas", "total": status_counts.get(SubscriptionStatus.ACTIVE, 0), "class": "badge-success"},
            {"label": "Cortesia", "total": status_counts.get(SubscriptionStatus.GRANDFATHERED, 0), "class": "badge-info"},
            {"label": "Pagamento atrasado", "total": status_counts.get(SubscriptionStatus.PAST_DUE, 0), "class": "badge-warning"},
            {"label": "Canceladas", "total": status_counts.get(SubscriptionStatus.CANCELED, 0), "class": "badge-error"},
        ]

        context["fields"] = [
            TableColumn("Conta", attr="account.name"),
            TableColumn("Responsável", attr=lambda obj: obj.account.owner.get_full_name() if obj.account.owner else "—", searchable=False, sortable=False),
            TableColumn("E-mail", attr=lambda obj: obj.account.owner.email if obj.account.owner else "—", searchable=False, sortable=False),
            TableColumn("Plano", attr="get_plan_display", searchable=False, sortable=False),
            TableColumn(
                "Status",
                attr=lambda obj: {
                    "label": obj.get_status_display(),
                    "badge_class": STATUS_BADGE_CLASS.get(obj.status, "badge-ghost"),
                },
                cell_template="billing/partials/subscription_status_cell.html",
                searchable=False,
                sortable=False,
            ),
            TableColumn("Oficinas", attr="workshop_count", searchable=False),
            TableColumn("Renova em", attr="current_period_end", searchable=False),
            TableColumn("Cliente Stripe", attr="stripe_customer_id"),
        ]
        context["actions"] = []
        context["status_choices"] = SubscriptionStatus.choices
        context["plan_choices"] = SubscriptionPlan.choices
        context["system_manage_url"] = reverse_lazy("workshops:system_manage")
        return context
