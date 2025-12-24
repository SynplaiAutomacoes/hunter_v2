from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import LoginForm, SignUpForm


class UserLoginView(LoginView):
    template_name = "login.html"
    authentication_form = LoginForm
    success_url = reverse_lazy("home")
    redirect_authenticated_user = True


class UserSignUpView(FormView):
    template_name = "cadastro.html"
    form_class = SignUpForm
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("login")
