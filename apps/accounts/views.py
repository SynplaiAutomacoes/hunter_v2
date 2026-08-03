import logging
import re

from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView
from django_htmx.http import HttpResponseClientRedirect

from apps.accounts.models import Account, PasswordResetToken

from .forms import (
    PasswordResetForm,
    SignUpForm,
    UserIdentificationForm,
)
from .forms import LoginForm
from ..core.infrastructure.services import get_whatsapp_service

logger = logging.getLogger(__name__)


def _mensagem(tipo: str, user, code: str) -> str:
    nome = user.first_name or user.username

    mensagens = {
        "password_reset": {
            "titulo": "Código de recuperação de senha",
            "texto": "Seu código de verificação é",
            "expira": "15 minutos",
        },
        "login_code": {
            "titulo": "Código de login",
            "texto": "Seu código de acesso é",
            "expira": "5 minutos",
        },
    }

    data = mensagens[tipo]

    return f"""*{data["titulo"]}*

Olá {nome}!

🔒 {data["texto"]}: *{code}*

Este código expira em {data["expira"]}.

Se você não solicitou esta ação, ignore esta mensagem.

Equipe Hunter"""


def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 4:
        return phone
    return phone[:2] + "*" * (len(phone) - 4) + phone[-2:]


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if not digits.startswith("55") and len(digits) >= 10:
        return "55" + digits
    return digits


def _get_user_phone(user) -> str | None:
    if user.phone:
        return user.phone
    try:
        collaborator = getattr(user, "workshop_collaborator", None)
        if collaborator and collaborator.phone:
            return str(collaborator.phone)
    except Exception:
        pass
    return None


def _send_whatsapp(user, code: str, tipo: str, phone: str | None = None) -> bool:
    if not phone:
        phone = _get_user_phone(user)

    if not phone:
        logger.warning("user_phone_missing", extra={"user_id": user.id, "tipo": tipo})
        return False

    normalized_phone = _normalize_phone(phone)

    try:
        message = _mensagem(tipo=tipo, user=user, code=code)

        whatsapp_service = get_whatsapp_service()
        whatsapp_service.send_text(normalized_phone, message)

        logger.info("whatsapp_message_sent", extra={"phone": _mask_phone(normalized_phone), "tipo": tipo, "user_id": user.id})
        return True

    except Exception as e:
        logger.error("whatsapp_send_failed", extra={"user_id": user.id, "tipo": tipo, "error": str(e)})
        return False


class UserLoginView(LoginView):
    template_name = "login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("core:dashboard")


class UserSignUpView(FormView):
    template_name = "register.html"
    form_class = SignUpForm
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()
            user.is_account_owner = True

            account = Account.objects.create(
                name=user.get_full_name() or user.username,
                owner=user,
            )
            user.account = account
            user.save(update_fields=["account", "is_account_owner"])

        return super().form_valid(form)


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.headers.get("HX-Request"):
            return HttpResponseClientRedirect(str(self.next_page))
        return response


class PasswordResetWizardView(View):
    def post(self, request):
        if request.POST:
            post_data = request.POST
        else:
            from urllib.parse import parse_qs

            parsed = parse_qs(request.body.decode("utf-8"))
            post_data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

        step = post_data.get("step", "1")
        identifier = post_data.get("identifier", "")
        code = post_data.get("code", "")

        logger.info("password_reset_request", extra={"step": step, "identifier": identifier})

        if step == "1":
            logger.info("password_reset_step1_started")
            form = UserIdentificationForm(data=post_data)
            if form.is_valid():
                user = form.user
                logger.info("password_reset_user_validated", extra={"user_id": user.id})

                phone = _get_user_phone(user)
                if not phone:
                    logger.warning("password_reset_user_no_phone", extra={"user_id": user.id})
                    return JsonResponse(
                        {
                            "success": False,
                            "step": 1,
                            "error": "Conta sem número de WhatsApp cadastrado. Procure a oficina para recuperar sua senha.",
                        },
                        status=400,
                    )

                token = PasswordResetToken.create_token(user)
                logger.info("password_reset_token_created", extra={"user_id": user.id, "token_id": token.pk})

                sent = _send_whatsapp(tipo="password_reset", user=user, code=token.code, phone=phone)
                if not sent:
                    logger.error("password_reset_whatsapp_failed", extra={"user_id": user.id})
                    return JsonResponse(
                        {
                            "success": False,
                            "step": 1,
                            "error": "Erro ao enviar código via WhatsApp. Tente novamente.",
                        },
                        status=500,
                    )

                request.session["password_reset_user_id"] = user.id
                request.session["password_reset_token_id"] = token.pk
                return JsonResponse(
                    {
                        "success": True,
                        "step": 2,
                        "phone": _mask_phone(phone),
                        "message": "Código enviado via WhatsApp!",
                    }
                )
            logger.warning("password_reset_step1_validation_failed", extra={"errors": str(form.errors)})
            return JsonResponse({"success": False, "step": 1, "errors": form.errors}, status=400)

        elif step == "2":
            logger.info("password_reset_step2_started")
            token_id = request.session.get("password_reset_token_id")
            if not token_id:
                logger.warning("password_reset_step2_no_token_in_session")
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Sessão expirada."},
                    status=400,
                )
            try:
                token = PasswordResetToken.objects.get(id=token_id, used=False)
            except PasswordResetToken.DoesNotExist:
                logger.warning("password_reset_step2_token_not_found", extra={"token_id": token_id})
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Token inválido ou expirado."},
                    status=400,
                )

            if not token.is_valid():
                logger.warning("password_reset_step2_token_expired", extra={"user_id": token.user.pk, "token_id": token_id})
                token.used = True
                token.save()
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Código expirado. Tente novamente."},
                    status=400,
                )

            if code.upper() != token.code.upper():
                logger.warning("password_reset_step2_invalid_code", extra={"user_id": token.user.pk})
                return JsonResponse(
                    {
                        "success": False,
                        "step": 2,
                        "error": "Código incorreto. Tente novamente.",
                    },
                    status=400,
                )

            logger.info("password_reset_step2_code_verified", extra={"user_id": token.user.pk})
            return JsonResponse({"success": True, "step": 3, "message": "Código validado!"})

        elif step == "3":
            logger.info("password_reset_step3_started")
            user_id = request.session.get("password_reset_user_id")
            token_id = request.session.get("password_reset_token_id")
            if not user_id or not token_id:
                logger.warning("password_reset_step3_missing_session_data")
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Sessão expirada."},
                    status=400,
                )

            from django.contrib.auth import get_user_model

            User = get_user_model()
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.warning("password_reset_step3_user_not_found", extra={"user_id": user_id})
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Usuário não encontrado."},
                    status=400,
                )

            form = PasswordResetForm(user, data=post_data)
            if form.is_valid():
                logger.info("password_reset_step3_password_saved", extra={"user_id": user_id})
                form.save()
                try:
                    token = PasswordResetToken.objects.get(id=token_id)
                    token.used = True
                    token.save()
                except PasswordResetToken.DoesNotExist:
                    pass

                request.session.pop("password_reset_user_id", None)
                request.session.pop("password_reset_token_id", None)

                logger.info("password_reset_completed", extra={"user_id": user_id})
                return JsonResponse({"success": True, "step": 4, "message": "Senha redefinida com sucesso!"})
            logger.warning("password_reset_step3_validation_failed", extra={"user_id": user_id, "errors": str(form.errors)})
            return JsonResponse({"success": False, "step": 3, "errors": form.errors}, status=400)

        logger.warning("password_reset_invalid_step", extra={"step": step})
        return JsonResponse({"error": "Etapa inválida"}, status=400)


class PasswordResetResendView(View):
    def post(self, request):
        logger.info("password_reset_resend_requested")
        user_id = request.session.get("password_reset_user_id")
        if not user_id:
            logger.warning("password_reset_resend_no_user_in_session")
            return JsonResponse({"success": False, "error": "Sessão expirada."}, status=400)

        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.warning("password_reset_resend_user_not_found", extra={"user_id": user_id})
            return JsonResponse({"success": False, "error": "Usuário não encontrado."}, status=400)

        logger.info("password_reset_resend_creating_token", extra={"user_id": user_id})
        token = PasswordResetToken.create_token(user)
        request.session["password_reset_token_id"] = token.pk

        phone = _get_user_phone(user)
        _send_whatsapp(tipo="password_reset", user=user, code=token.code, phone=phone)

        return JsonResponse(
            {
                "success": True,
                "phone": _mask_phone(phone) if phone else "",
                "message": "Novo código enviado!",
            }
        )


class LoginCodeWizardView(View):
    def post(self, request):
        if request.POST:
            post_data = request.POST
        else:
            import json

            try:
                post_data = json.loads(request.body)
            except Exception:
                from urllib.parse import parse_qs

                parsed = parse_qs(request.body.decode("utf-8"))
                post_data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

        step = post_data.get("step", "1")
        identifier = post_data.get("identifier", "")
        code = post_data.get("code", "")

        logger.info("login_code_request", extra={"step": step, "identifier": identifier})

        if step == "1":
            logger.info("login_code_step1_started")
            form = UserIdentificationForm(data=post_data)
            if form.is_valid():
                user = form.user
                logger.info("login_code_user_validated", extra={"user_id": user.id})

                phone = _get_user_phone(user)
                if not phone:
                    logger.warning("login_code_user_no_phone", extra={"user_id": user.id})
                    return JsonResponse(
                        {"success": False, "step": 1, "error": "Conta sem número de WhatsApp cadastrado."},
                        status=400,
                    )

                from apps.accounts.models import LoginCodeToken

                try:
                    token = LoginCodeToken.create_token(user)
                except ValueError as e:
                    logger.warning("login_code_token_creation_failed", extra={"user_id": user.id, "error": str(e)})
                    return JsonResponse({"success": False, "step": 1, "error": str(e)}, status=400)

                sent = _send_whatsapp(tipo="login_code", user=user, code=token.code, phone=phone)
                if not sent:
                    logger.error("login_code_whatsapp_failed", extra={"user_id": user.id})
                    return JsonResponse(
                        {"success": False, "step": 1, "error": "Erro ao enviar código via WhatsApp. Tente novamente."},
                        status=500,
                    )

                request.session["login_code_user_id"] = user.id
                request.session["login_code_token_id"] = token.pk
                return JsonResponse(
                    {
                        "success": True,
                        "step": 2,
                        "phone": _mask_phone(phone),
                        "message": "Código enviado via WhatsApp!",
                    }
                )
            logger.warning("login_code_step1_validation_failed", extra={"errors": str(form.errors)})
            return JsonResponse({"success": False, "step": 1, "errors": form.errors}, status=400)

        elif step == "2":
            logger.info("login_code_step2_started")
            token_id = request.session.get("login_code_token_id")
            if not token_id:
                logger.warning("login_code_step2_no_token_in_session")
                return JsonResponse({"success": False, "step": 1, "error": "Sessão expirada."}, status=400)

            from apps.accounts.models import LoginCodeToken

            try:
                token = LoginCodeToken.objects.get(id=token_id)
            except LoginCodeToken.DoesNotExist:
                logger.warning("login_code_step2_token_not_found", extra={"token_id": token_id})
                return JsonResponse({"success": False, "step": 1, "error": "Token inválido."}, status=400)

            if token.used:
                logger.warning("login_code_step2_token_already_used", extra={"user_id": token.user_id, "token_id": token_id})
                return JsonResponse({"success": False, "step": 1, "error": "Token já utilizado ou invalidado."}, status=400)

            if not token.is_valid():
                logger.warning("login_code_step2_token_expired", extra={"user_id": token.user_id, "token_id": token_id})
                return JsonResponse({"success": False, "step": 1, "error": "Código expirado ou bloqueado por tentativas. Solicite um novo."}, status=400)

            if code.upper() != token.code.upper():
                token.attempts += 1
                token.save(update_fields=["attempts"])
                if token.attempts >= 3:
                    token.used = True
                    token.save(update_fields=["used"])
                    logger.warning("login_code_step2_max_attempts_reached", extra={"user_id": token.user_id})
                    return JsonResponse({"success": False, "step": 1, "error": "Limite de tentativas excedido. Solicite novo código."}, status=400)

                logger.warning("login_code_step2_wrong_code", extra={"user_id": token.user_id, "attempts": token.attempts})
                return JsonResponse({"success": False, "step": 2, "error": f"Código incorreto. Tentativas restantes: {3 - token.attempts}"}, status=400)

            token.used = True
            token.save(update_fields=["used"])

            from django.contrib.auth import login

            user = token.user
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")

            logger.info("login_code_success", extra={"user_id": user.id})

            request.session.pop("login_code_user_id", None)
            request.session.pop("login_code_token_id", None)

            return JsonResponse({"success": True, "step": 3, "redirect_url": str(reverse_lazy("core:dashboard"))})

        logger.warning("login_code_invalid_step", extra={"step": step})
        return JsonResponse({"error": "Etapa inválida"}, status=400)


class LoginCodeResendView(View):
    def post(self, request):
        user_id = request.session.get("login_code_user_id")
        if not user_id:
            return JsonResponse({"success": False, "error": "Sessão expirada."}, status=400)

        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"success": False, "error": "Usuário não encontrado."}, status=400)

        from apps.accounts.models import LoginCodeToken

        try:
            token = LoginCodeToken.create_token(user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

        request.session["login_code_token_id"] = token.pk

        phone = _get_user_phone(user)
        _send_whatsapp(tipo="login_code", user=user, code=token.code, phone=phone)

        return JsonResponse(
            {
                "success": True,
                "phone": _mask_phone(phone) if phone else "",
                "message": "Novo código enviado!",
            }
        )
