from django.urls import path

from .views import UserLoginView, UserLogoutView, UserSignUpView

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("cadastro/", UserSignUpView.as_view(), name="cadastro"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
]
