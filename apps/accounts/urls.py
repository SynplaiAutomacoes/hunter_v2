from django.urls import path

from .views import UserLoginView, UserLogoutView, UserSignUpView

app_name = "accounts"

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("register/", UserSignUpView.as_view(), name="register"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
]
