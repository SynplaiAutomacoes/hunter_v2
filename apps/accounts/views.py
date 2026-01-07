from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import FormView

from apps.accounts.models import Account
from apps.iam.utils import get_or_create_director_role

from .forms import LoginForm, SignUpForm


class UserLoginView(LoginView):
    template_name = "login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("workshops:create")


class UserSignUpView(FormView):
    template_name = "register.html"
    form_class = SignUpForm
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()

            account = Account.objects.create(
                name=user.get_full_name() or user.username,
                owner=user,
            )
            user.account = account
            user.save(update_fields=["account"])

            get_or_create_director_role(account=account)

        return super().form_valid(form)


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")
