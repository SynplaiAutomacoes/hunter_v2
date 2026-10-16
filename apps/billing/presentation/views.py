from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.accounts.mixins import AccountOwnerRequiredMixin
from apps.billing.access import (
    apply_local_subscription_cancel,
    get_account_subscription,
    invalidate_subscription_cache,
)
from apps.billing.domain.contracts import (
    BillingPortalRequest,
    BillingServiceError,
    CancelSubscriptionRequest,
    CheckoutSessionRequest,
    IncompleteSubscriptionRequest,
)
from apps.billing.domain.plans import Plan
from apps.billing.forms import SubscribeSignupForm
from apps.billing.infrastructure.providers import get_billing_service
from apps.billing.infrastructure.services.pending_signup import (
    consume_login_token,
    create_pending_signup,
    materialize_account_from_pending_signup,
)
from apps.billing.models import (
    AccountSubscription,
    PendingSignup,
    PendingSignupStatus,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.core.templatetags.table_tags import TableAction, TableColumn
from apps.workshops.views.system_management import SystemManagementMixin

logger = logging.getLogger(__name__)

STRIPE_USER_ERROR_MESSAGE = "Não foi possível iniciar o pagamento. Tente novamente."
SIGNUP_EMAIL_SESSION_KEY = "signup_email_verified"

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


class SubscribeView(TemplateView):
    template_name = "billing/subscribe.html"

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("billing:plans")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        plan_key = str(self.request.GET.get("plan") or Plan.BASIC).strip()
        if plan_key not in (Plan.BASIC, Plan.FULL):
            plan_key = Plan.BASIC

        plans = get_billing_service().list_public_plans()
        selected = next((plan for plan in plans if plan.key == plan_key), None)
        if selected is None and plans:
            selected = plans[0]
            plan_key = selected.key

        context["selected_plan"] = selected
        context["plan_key"] = plan_key
        context["form"] = SubscribeSignupForm(initial={"plan": plan_key})
        context["stripe_publishable_key"] = str(getattr(settings, "STRIPE_PUBLISHABLE_KEY", "") or "")
        context["start_url"] = reverse("billing:subscribe_start")
        context["send_code_url"] = reverse("billing:subscribe_send_code")
        context["verify_code_url"] = reverse("billing:subscribe_verify_code")
        context["validate_coupon_url"] = reverse("billing:subscribe_validate_coupon")
        context["confirm_setup_url"] = reverse("billing:subscribe_confirm_setup")
        context["status_url_template"] = reverse("billing:subscribe_status", kwargs={"pending_id": 0}).replace("/0/", "/{id}/")
        context["complete_url"] = reverse("billing:subscribe_complete")
        context["login_url"] = reverse("accounts:login")
        context["landing_url"] = reverse("landing")
        return context


class SubscribeSendCodeView(View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        from django.contrib.auth import get_user_model

        from apps.billing.models import SignupEmailVerification
        from apps.core.infrastructure.services.email import mask_email, send_verification_code_email

        if request.user.is_authenticated:
            return JsonResponse({"ok": False, "message": "Você já está autenticado."}, status=400)

        email = str(request.POST.get("email") or "").strip().lower()
        first_name = str(request.POST.get("first_name") or "").strip()
        if not email or "@" not in email:
            return JsonResponse({"ok": False, "message": "Informe um e-mail válido."}, status=400)

        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            return JsonResponse({"ok": False, "message": "Este e-mail já está em uso."}, status=400)

        try:
            token = SignupEmailVerification.create_token(email=email)
        except ValueError as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=429)

        sent = send_verification_code_email(
            to_email=email,
            code=token.code,
            tipo="signup_confirm",
            recipient_name=first_name,
        )
        if not sent:
            return JsonResponse({"ok": False, "message": "Erro ao enviar o código por e-mail. Tente novamente."}, status=500)

        return JsonResponse({"ok": True, "masked_email": mask_email(email)})


class SubscribeVerifyCodeView(View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        from apps.billing.models import SignupEmailVerification

        if request.user.is_authenticated:
            return JsonResponse({"ok": False, "message": "Você já está autenticado."}, status=400)

        email = str(request.POST.get("email") or "").strip().lower()
        code = str(request.POST.get("code") or "").strip()
        if not email or not code:
            return JsonResponse({"ok": False, "message": "Informe o e-mail e o código."}, status=400)

        token = (
            SignupEmailVerification.objects.filter(email__iexact=email, used=False)
            .order_by("-criado_em")
            .first()
        )
        if token is None:
            return JsonResponse({"ok": False, "message": "Código inválido. Solicite um novo."}, status=400)

        if not token.is_valid():
            return JsonResponse({"ok": False, "message": "Código expirado ou bloqueado. Solicite um novo."}, status=400)

        if token.code != code:
            token.attempts += 1
            token.save(update_fields=["attempts", "atualizado_em"])
            return JsonResponse({"ok": False, "message": "Código incorreto."}, status=400)

        token.used = True
        token.save(update_fields=["used", "atualizado_em"])
        request.session[SIGNUP_EMAIL_SESSION_KEY] = email
        return JsonResponse({"ok": True})


class SubscribeStartView(View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated:
            return JsonResponse({"ok": False, "message": "Você já está autenticado."}, status=400)

        form = SubscribeSignupForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)

        verified_email = str(request.session.get(SIGNUP_EMAIL_SESSION_KEY) or "").strip().lower()
        if not verified_email or verified_email != form.cleaned_data["email"]:
            return JsonResponse(
                {"ok": False, "message": "Confirme seu e-mail com o código enviado antes de continuar."},
                status=400,
            )

        plan = str(form.cleaned_data["plan"])
        price_id = ""
        for card in get_billing_service().list_public_plans():
            if card.key == plan:
                price_id = card.stripe_price_id
                break
        if not price_id:
            return JsonResponse({"ok": False, "message": "Price ID do plano não configurado."}, status=400)

        pending = create_pending_signup(
            email=form.cleaned_data["email"],
            username=form.cleaned_data["username"],
            password_hash=form.build_password_hash(),
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data.get("last_name") or "",
            cpf=form.cleaned_data["cpf"],
            plan=plan,
        )

        try:
            result = get_billing_service().create_incomplete_subscription(
                IncompleteSubscriptionRequest(
                    email=pending.email,
                    customer_name=f"{pending.first_name} {pending.last_name}".strip(),
                    plan=plan,
                    price_id=price_id,
                    pending_signup_id=pending.pk,
                    promotion_code=form.cleaned_data.get("promotion_code") or "",
                )
            )
        except BillingServiceError as exc:
            logger.exception("Falha Stripe ao iniciar assinatura pendente %s", pending.pk)
            pending.status = PendingSignupStatus.FAILED
            pending.save(update_fields=["status", "atualizado_em"])
            error_message = str(exc)
            if "cupom" in error_message.lower():
                return JsonResponse({"ok": False, "message": error_message}, status=400)
            return JsonResponse({"ok": False, "message": STRIPE_USER_ERROR_MESSAGE}, status=500)

        pending.stripe_customer_id = result.customer_id
        pending.stripe_subscription_id = result.subscription_id
        pending.stripe_payment_intent_id = result.payment_intent_id
        pending.save(
            update_fields=[
                "stripe_customer_id",
                "stripe_subscription_id",
                "stripe_payment_intent_id",
                "atualizado_em",
            ]
        )

        if not result.client_secret:
            return JsonResponse({"ok": False, "message": STRIPE_USER_ERROR_MESSAGE}, status=500)

        return JsonResponse(
            {
                "ok": True,
                "pending_signup_id": pending.pk,
                "requires_payment": True,
                "confirmation_mode": result.confirmation_mode or "payment",
                "client_secret": result.client_secret,
                "publishable_key": str(getattr(settings, "STRIPE_PUBLISHABLE_KEY", "") or ""),
            }
        )


class SubscribeValidateCouponView(View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        plan = str(request.POST.get("plan") or "").strip()
        code = str(request.POST.get("promotion_code") or "").strip()
        if plan not in (Plan.BASIC, Plan.FULL):
            return JsonResponse({"ok": False, "message": "Plano inválido."}, status=400)
        if not code:
            return JsonResponse({"ok": False, "message": "Informe um cupom válido."}, status=400)

        try:
            preview = get_billing_service().preview_plan_coupon(plan=plan, code=code)
        except BillingServiceError as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=400)
        except Exception:
            logger.exception("Falha ao validar cupom para plano %s", plan)
            return JsonResponse({"ok": False, "message": "Não foi possível validar o cupom. Tente novamente."}, status=500)

        return JsonResponse(
            {
                "ok": True,
                "original_amount": preview.original_amount,
                "final_amount": preview.final_amount,
                "original_label": preview.original_label,
                "final_label": preview.final_label,
                "interval_label": preview.interval_label,
                "discount_label": preview.discount_label,
                "currency": preview.currency,
            }
        )


class SubscribeConfirmSetupView(View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        pending_id = int(request.POST.get("pending_signup_id") or 0)
        setup_intent_id = str(request.POST.get("setup_intent_id") or "").strip()
        pending = get_object_or_404(PendingSignup, pk=pending_id)

        if pending.status == PendingSignupStatus.PAID and pending.login_token:
            return JsonResponse({"ok": True, "login_token": pending.login_token, "pending_signup_id": pending.pk})

        if pending.status != PendingSignupStatus.PENDING:
            return JsonResponse({"ok": False, "message": "Cadastro pendente inválido."}, status=400)
        if not setup_intent_id:
            return JsonResponse({"ok": False, "message": "Confirme o cartão antes de continuar."}, status=400)
        if not pending.stripe_customer_id or not pending.stripe_subscription_id:
            return JsonResponse({"ok": False, "message": STRIPE_USER_ERROR_MESSAGE}, status=400)

        try:
            get_billing_service().finalize_setup_intent(
                setup_intent_id=setup_intent_id,
                customer_id=pending.stripe_customer_id,
                subscription_id=pending.stripe_subscription_id,
            )
            materialize_account_from_pending_signup(
                pending=pending,
                stripe_customer_id=pending.stripe_customer_id,
                stripe_subscription_id=pending.stripe_subscription_id,
            )
            pending.refresh_from_db()
        except BillingServiceError as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=400)
        except Exception:
            logger.exception("Falha ao confirmar SetupIntent do pending %s", pending.pk)
            return JsonResponse({"ok": False, "message": STRIPE_USER_ERROR_MESSAGE}, status=500)

        if not pending.login_token:
            return JsonResponse({"ok": False, "message": STRIPE_USER_ERROR_MESSAGE}, status=500)

        return JsonResponse(
            {
                "ok": True,
                "login_token": pending.login_token,
                "pending_signup_id": pending.pk,
            }
        )


class SubscribeStatusView(View):
    def get(self, request: HttpRequest, pending_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        pending = get_object_or_404(PendingSignup, pk=pending_id)
        payload: dict[str, Any] = {
            "ok": True,
            "status": pending.status,
            "paid": pending.status == PendingSignupStatus.PAID,
            "failed": pending.status in (PendingSignupStatus.FAILED, PendingSignupStatus.EXPIRED),
        }
        if pending.status == PendingSignupStatus.PAID and pending.login_token and pending.login_token_used_at is None:
            payload["login_token"] = pending.login_token
        return JsonResponse(payload)


class SubscribeCompleteView(View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        pending_id = int(request.POST.get("pending_signup_id") or 0)
        token = str(request.POST.get("login_token") or "")
        user = consume_login_token(pending_id=pending_id, token=token)
        if user is None:
            return JsonResponse({"ok": False, "message": "Não foi possível concluir o login."}, status=400)

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        invalidate_subscription_cache(request)
        return JsonResponse({"ok": True, "redirect_url": reverse("billing:checkout_success")})


class PlansView(LoginRequiredMixin, TemplateView):
    template_name = "billing/plans.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        subscription = get_account_subscription(self.request)
        context["subscription"] = subscription
        context["is_account_owner"] = bool(getattr(self.request.user, "is_superuser", False) or (getattr(self.request.user, "account_id", None) and getattr(self.request.user, "account", None) and self.request.user.account.owner_id == self.request.user.id) or getattr(self.request.user, "is_account_owner", False))
        context["plans"] = get_billing_service().list_public_plans()
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
                    "cancel_at_period_end": bool(obj.cancel_at_period_end),
                    "period_end": obj.current_period_end,
                },
                cell_template="billing/partials/subscription_status_cell.html",
                searchable=False,
                sortable=False,
            ),
            TableColumn("Oficinas", attr="workshop_count", searchable=False),
            TableColumn("Renova em", attr="current_period_end", searchable=False),
            TableColumn("Cliente Stripe", attr="stripe_customer_id"),
        ]
        context["actions"] = [
            TableAction(
                url_name="billing:subscriber_cancel",
                label="Cancelar",
                icon="cancel",
                a_class="btn-table-delete",
                aria_label="Cancelar assinatura",
                hx_target="#modal-container",
                hx_swap="innerHTML",
                hx_push_url="false",
                visible=lambda obj: obj.status != SubscriptionStatus.CANCELED,
            ),
        ]
        context["status_choices"] = SubscriptionStatus.choices
        context["plan_choices"] = SubscriptionPlan.choices
        context["system_manage_url"] = reverse_lazy("workshops:system_manage")
        return context


def _parse_cancel_mode(raw: str) -> bool | None:
    """Return True for at_period_end, False for immediate, None if invalid."""
    value = (raw or "").strip().lower()
    if value in {"period_end", "at_period_end", "fim", "period"}:
        return True
    if value in {"immediate", "now", "imediato"}:
        return False
    return None


def _execute_subscription_cancel(
    *,
    subscription: AccountSubscription,
    at_period_end: bool,
) -> AccountSubscription:
    if subscription.status == SubscriptionStatus.CANCELED:
        raise BillingServiceError("Esta assinatura já está cancelada.")

    if subscription.stripe_subscription_id:
        get_billing_service().cancel_subscription(
            CancelSubscriptionRequest(
                stripe_subscription_id=subscription.stripe_subscription_id,
                at_period_end=at_period_end,
            )
        )
        return apply_local_subscription_cancel(subscription, at_period_end=at_period_end)

    # Cortesia / sem Stripe: só cancelamento imediato local.
    if at_period_end:
        raise BillingServiceError(
            "Cancelamento no fim do período só está disponível para assinaturas Stripe."
        )
    return apply_local_subscription_cancel(subscription, at_period_end=False)


class SubscriberCancelView(SystemManagementMixin, View):
    """Sidney / Gerenciar Sistema: cancel with immediate vs period-end choice."""

    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        subscription = get_object_or_404(
            AccountSubscription.objects.select_related("account", "account__owner"),
            pk=pk,
        )
        if subscription.status == SubscriptionStatus.CANCELED:
            messages.info(request, "Esta assinatura já está cancelada.")
            return redirect("billing:subscriber_list")
        return self._render_modal(request, subscription)

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        subscription = get_object_or_404(
            AccountSubscription.objects.select_related("account", "account__owner"),
            pk=pk,
        )
        at_period_end = _parse_cancel_mode(str(request.POST.get("cancel_mode") or ""))
        if at_period_end is None:
            messages.error(request, "Escolha o método de cancelamento.")
            return self._render_modal(request, subscription)

        try:
            _execute_subscription_cancel(subscription=subscription, at_period_end=at_period_end)
        except BillingServiceError as exc:
            messages.error(request, str(exc))
            return self._render_modal(request, subscription)

        if at_period_end:
            messages.success(
                request,
                "Cancelamento agendado para o fim do período. O acesso continua até a data de renovação.",
            )
        else:
            messages.success(request, "Assinatura cancelada imediatamente. O acesso foi revogado.")
        return redirect("billing:subscriber_list")

    def _render_modal(self, request: HttpRequest, subscription: AccountSubscription) -> HttpResponse:
        from django.template.response import TemplateResponse

        return TemplateResponse(
            request,
            "billing/partials/subscriber_cancel_modal.html",
            {
                "subscription": subscription,
                "has_stripe": bool(subscription.stripe_subscription_id),
                "form_url": reverse("billing:subscriber_cancel", kwargs={"pk": subscription.pk}),
            },
        )


class OwnerSubscriptionCancelView(AccountOwnerRequiredMixin, View):
    """Account owner cancels own subscription from plans page."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        subscription = get_account_subscription(request)
        if subscription is None:
            messages.error(request, "Nenhuma assinatura encontrada para esta conta.")
            return redirect("billing:plans")

        at_period_end = _parse_cancel_mode(str(request.POST.get("cancel_mode") or ""))
        if at_period_end is None:
            messages.error(request, "Escolha o método de cancelamento.")
            return redirect("billing:plans")

        try:
            _execute_subscription_cancel(subscription=subscription, at_period_end=at_period_end)
        except BillingServiceError as exc:
            messages.error(request, str(exc))
            return redirect("billing:plans")

        invalidate_subscription_cache(request)
        if at_period_end:
            messages.success(
                request,
                "Cancelamento agendado. Você continua com acesso até o fim do período atual.",
            )
        else:
            messages.success(request, "Assinatura cancelada. Seu acesso foi encerrado.")
        return redirect("billing:plans")
