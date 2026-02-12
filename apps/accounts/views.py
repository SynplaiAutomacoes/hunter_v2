from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponse
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import FormView
from typing import cast

from apps.accounts.models import Account

from .forms import LoginForm, SignUpForm


class UserLoginView(LoginView):
    template_name = "login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return str(redirect_url)
        return str(reverse_lazy("workshops:create"))


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
    next_page = cast(str, reverse_lazy("accounts:login"))

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if request.headers.get("HX-Request") == "true":
            htmx_response = HttpResponse(status=204)
            htmx_response["HX-Redirect"] = str(self.get_success_url())
            return htmx_response

        return response
