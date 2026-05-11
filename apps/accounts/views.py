import logging
import re

from django.conf import settings
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import FormView
from django_htmx.http import HttpResponseClientRedirect

from apps.accounts.models import Account, PasswordResetToken
from apps.core.services import get_whatsapp_service

from .forms import (
    CodeVerificationForm,
    PasswordResetForm,
    SignUpForm,
    UserIdentificationForm,
)
from .forms import LoginForm

logger = logging.getLogger(__name__)


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
            parsed = parse_qs(request.body.decode('utf-8'))
            post_data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

        step = post_data.get("step", "1")
        identifier = post_data.get("identifier", "")
        code = post_data.get("code", "")

        logger.info(f"Password reset request | Step: {step}, Identifier: {identifier}, Code: {code}")

        if step == "1":
            logger.info("Processing step 1 - User identification")
            form = UserIdentificationForm(data=post_data)
            if form.is_valid():
                user = form.user
                logger.info(f"User validated: {user.username}")

                phone = self._get_user_phone(user)
                if not phone:
                    logger.warning(f"User {user.id} has no phone number in User or WorkshopCollaborator")
                    return JsonResponse(
                        {
                            "success": False,
                            "step": 1,
                            "error": "Conta sem número de WhatsApp cadastrado. Procure a oficina para recuperar sua senha.",
                        },
                        status=400,
                    )

                token = PasswordResetToken.create_token(user)
                logger.info(f"Token created for user {user.id}, token id: {token.id}")

                sent = self._send_reset_via_whatsapp(user, token.code, phone)
                if not sent:
                    logger.error(f"Failed to send WhatsApp to user {user.id}")
                    return JsonResponse(
                        {
                            "success": False,
                            "step": 1,
                            "error": "Erro ao enviar código via WhatsApp. Tente novamente.",
                        },
                        status=500,
                    )

                request.session["password_reset_user_id"] = user.id
                request.session["password_reset_token_id"] = token.id
                return JsonResponse(
                    {
                        "success": True,
                        "step": 2,
                        "phone": self._mask_phone(phone),
                        "message": "Código enviado via WhatsApp!",
                    }
                )
            logger.warning(f"Step 1 validation failed: {form.errors}")
            return JsonResponse(
                {"success": False, "step": 1, "errors": form.errors}, status=400
            )

        elif step == "2":
            logger.info("Processing step 2 - Code verification")
            token_id = request.session.get("password_reset_token_id")
            if not token_id:
                logger.warning("Step 2 - No token_id in session")
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Sessão expirada."},
                    status=400,
                )
            try:
                token = PasswordResetToken.objects.get(id=token_id, used=False)
            except PasswordResetToken.DoesNotExist:
                logger.warning(f"Step 2 - Token {token_id} not found or already used")
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Token inválido ou expirado."},
                    status=400,
                )

            if not token.is_valid():
                logger.warning(f"Step 2 - Token expired for user {token.user_id}")
                token.used = True
                token.save()
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Código expirado. Tente novamente."},
                    status=400,
                )

            if code.upper() != token.code.upper():
                logger.warning(f"Step 2 - Invalid code submitted")
                return JsonResponse(
                    {
                        "success": False,
                        "step": 2,
                        "error": "Código incorreto. Tente novamente.",
                    },
                    status=400,
                )

            logger.info(f"Step 2 - Code verified successfully for user {token.user_id}")
            return JsonResponse({"success": True, "step": 3, "message": "Código validado!"})

        elif step == "3":
            logger.info("Processing step 3 - Password reset")
            user_id = request.session.get("password_reset_user_id")
            token_id = request.session.get("password_reset_token_id")
            if not user_id or not token_id:
                logger.warning("Step 3 - Missing user_id or token_id in session")
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Sessão expirada."},
                    status=400,
                )

            from django.contrib.auth import get_user_model

            User = get_user_model()
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.warning(f"Step 3 - User {user_id} not found")
                return JsonResponse(
                    {"success": False, "step": 1, "error": "Usuário não encontrado."},
                    status=400,
                )

            form = PasswordResetForm(user, data=post_data)
            if form.is_valid():
                logger.info(f"Step 3 - Password form valid, saving for user {user_id}")
                form.save()
                try:
                    token = PasswordResetToken.objects.get(id=token_id)
                    token.used = True
                    token.save()
                except PasswordResetToken.DoesNotExist:
                    pass

                request.session.pop("password_reset_user_id", None)
                request.session.pop("password_reset_token_id", None)

                logger.info(f"Password reset completed for user {user_id}")
                return JsonResponse(
                    {"success": True, "step": 4, "message": "Senha redefinida com sucesso!"}
                )
            logger.warning(f"Step 3 - Password validation failed: {form.errors}")
            return JsonResponse(
                {"success": False, "step": 3, "errors": form.errors}, status=400
            )

        logger.warning(f"Invalid step received: {step}")
        return JsonResponse({"error": "Step inválido"}, status=400)

    def _mask_phone(self, phone: str) -> str:
        if not phone or len(phone) < 4:
            return phone
        return phone[:2] + "*" * (len(phone) - 4) + phone[-2:]

    def _normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if not digits.startswith('55') and len(digits) >= 10:
            return '55' + digits
        return digits

    def _get_user_phone(self, user) -> str | None:
        if user.phone:
            return user.phone
        try:
            collaborator = user.workshop_collaborator
            if collaborator and collaborator.phone:
                return str(collaborator.phone)
        except Exception:
            pass
        return None

    def _send_reset_via_whatsapp(self, user, code: str, phone: str | None = None) -> bool:
        if not phone:
            phone = self._get_user_phone(user)
        if not phone:
            logger.warning(f"User {user.id} has no phone number configured")
            return False

        normalized_phone = self._normalize_phone(phone)
        message = f"""*Código de Recuperação de Senha - Hunter*

Olá {user.first_name or user.username}!

Seu código de verificação é: *{code}*

Este código expira em 15 minutos.

Se você não solicitou esta recuperação, ignore esta mensagem.

Equipe Hunter"""

        try:
            whatsapp_service = get_whatsapp_service()
            whatsapp_service.send_text(normalized_phone, message)
            logger.info(f"WhatsApp code sent to {normalized_phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return False


class PasswordResetResendView(View):
    def post(self, request):
        logger.info("Password reset resend requested")
        user_id = request.session.get("password_reset_user_id")
        if not user_id:
            logger.warning("Resend - No user_id in session")
            return JsonResponse(
                {"success": False, "error": "Sessão expirada."}, status=400
            )

        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.warning(f"Resend - User {user_id} not found")
            return JsonResponse(
                {"success": False, "error": "Usuário não encontrado."}, status=400
            )

        logger.info(f"Resend - Creating new token for user {user_id}")
        token = PasswordResetToken.create_token(user)
        request.session["password_reset_token_id"] = token.id

        phone = self._get_user_phone(user)
        self._send_reset_via_whatsapp(user, token.code, phone)

        return JsonResponse(
            {
                "success": True,
                "phone": self._mask_phone(phone) if phone else "",
                "message": "Novo código enviado!",
            }
        )

    def _get_user_phone(self, user) -> str | None:
        if user.phone:
            return user.phone
        try:
            collaborator = user.workshop_collaborator
            if collaborator and collaborator.phone:
                return str(collaborator.phone)
        except Exception:
            pass
        return None

    def _mask_phone(self, phone: str) -> str:
        if not phone or len(phone) < 4:
            return phone
        return phone[:2] + "*" * (len(phone) - 4) + phone[-2:]

    def _normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if not digits.startswith('55') and len(digits) >= 10:
            return '55' + digits
        return digits

    def _send_reset_via_whatsapp(self, user, code: str, phone: str | None = None) -> bool:
        if not phone:
            phone = self._get_user_phone(user)
        if not phone:
            logger.warning(f"User {user.id} has no phone number configured")
            return False

        normalized_phone = self._normalize_phone(phone)
        message = f"""*Codigo de Recuperação de Senha - Hunter*

Olá {user.first_name or user.username}!

Seu código de verificação e: *{code}*

Este código expira em 15 minutos.

Se você não solicitou esta recuperação, ignore esta mensagem.

Equipe Hunter"""

        try:
            whatsapp_service = get_whatsapp_service()
            whatsapp_service.send_text(normalized_phone, message)
            logger.info(f"WhatsApp code sent to {normalized_phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return False
