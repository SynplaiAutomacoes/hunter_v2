from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Account
from apps.billing.access import sync_subscription_from_stripe
from apps.billing.models import PendingSignup, PendingSignupStatus, SubscriptionPlan, SubscriptionStatus

logger = logging.getLogger(__name__)
User = get_user_model()

PENDING_SIGNUP_TTL = timedelta(hours=24)


@transaction.atomic
def create_pending_signup(
    *,
    email: str,
    username: str,
    password_hash: str,
    first_name: str,
    last_name: str,
    cpf: str,
    plan: str,
) -> PendingSignup:
    unfinished = PendingSignup.objects.select_for_update().filter(
        status=PendingSignupStatus.PENDING,
    ).filter(Q(email__iexact=email) | Q(username__iexact=username))
    for previous in unfinished:
        previous.status = PendingSignupStatus.EXPIRED
        previous.save(update_fields=["status", "atualizado_em"])

    return PendingSignup.objects.create(
        email=email,
        username=username,
        password_hash=password_hash,
        first_name=first_name,
        last_name=last_name,
        cpf=cpf,
        plan=plan,
        status=PendingSignupStatus.PENDING,
        expires_at=timezone.now() + PENDING_SIGNUP_TTL,
    )


def mark_pending_signup_failed(pending: PendingSignup) -> PendingSignup:
    if pending.status == PendingSignupStatus.PAID:
        return pending
    pending.status = PendingSignupStatus.FAILED
    pending.save(update_fields=["status", "atualizado_em"])
    return pending


@transaction.atomic
def materialize_account_from_pending_signup(
    *,
    pending: PendingSignup,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    stripe_price_id: str = "",
    current_period_end=None,
) -> PendingSignup:
    pending = PendingSignup.objects.select_for_update().get(pk=pending.pk)
    if pending.status == PendingSignupStatus.PAID and pending.created_account_id:
        return pending
    if pending.status != PendingSignupStatus.PENDING:
        raise ValueError("Cadastro pendente não está mais ativo.")

    if pending.is_expired and pending.status == PendingSignupStatus.PENDING:
        pending.status = PendingSignupStatus.EXPIRED
        pending.save(update_fields=["status", "atualizado_em"])
        raise ValueError("Cadastro pendente expirado.")

    user = User(
        username=pending.username,
        email=pending.email,
        first_name=pending.first_name,
        last_name=pending.last_name,
        cpf=pending.cpf,
        is_account_owner=True,
    )
    user.password = pending.password_hash
    user.save()

    account = Account.objects.create(
        name=user.get_full_name() or user.username,
        owner=user,
    )
    user.account = account
    user.save(update_fields=["account"])

    sync_subscription_from_stripe(
        account_id=account.pk,
        plan=pending.plan if pending.plan in SubscriptionPlan.values else SubscriptionPlan.BASIC,
        status=SubscriptionStatus.ACTIVE,
        stripe_customer_id=stripe_customer_id or pending.stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id or pending.stripe_subscription_id,
        stripe_price_id=stripe_price_id,
        current_period_end=current_period_end,
    )

    pending.status = PendingSignupStatus.PAID
    pending.created_account = account
    pending.login_token = secrets.token_urlsafe(32)
    pending.login_token_used_at = None
    if stripe_customer_id:
        pending.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id:
        pending.stripe_subscription_id = stripe_subscription_id
    pending.save(
        update_fields=[
            "status",
            "created_account",
            "login_token",
            "login_token_used_at",
            "stripe_customer_id",
            "stripe_subscription_id",
            "atualizado_em",
        ]
    )
    logger.info("Conta materializada a partir do PendingSignup %s", pending.pk)
    return pending


def consume_login_token(*, pending_id: int, token: str) -> User | None:
    try:
        pending = PendingSignup.objects.select_related("created_account").get(pk=pending_id)
    except PendingSignup.DoesNotExist:
        return None

    if pending.status != PendingSignupStatus.PAID:
        return None
    if not pending.login_token or pending.login_token != token:
        return None
    if pending.login_token_used_at is not None:
        return None
    if pending.created_account_id is None:
        return None

    user = User.objects.filter(account_id=pending.created_account_id, is_account_owner=True).first()
    if user is None:
        return None

    pending.login_token_used_at = timezone.now()
    pending.save(update_fields=["login_token_used_at", "atualizado_em"])
    return user
