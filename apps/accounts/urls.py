from django.urls import path

from .views import (
    PasswordResetResendView,
    PasswordResetWizardView,
    UserLoginView,
    UserLogoutView,
    UserSignUpView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("register/", UserSignUpView.as_view(), name="register"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("password-reset/", PasswordResetWizardView.as_view(), name="password_reset"),
    path("password-reset/resend/", PasswordResetResendView.as_view(), name="password_reset_resend"),
]
