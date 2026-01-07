from django.urls import path

from .views import UserLoginView, UserLogoutView, UserSignUpView
from .role_views import WorkshopRoleCreateView, WorkshopRoleDeleteView, WorkshopRoleListView, WorkshopRoleUpdateView

app_name = "accounts"

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("register/", UserSignUpView.as_view(), name="register"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("roles/", WorkshopRoleListView.as_view(), name="role_list"),
    path("roles/create/", WorkshopRoleCreateView.as_view(), name="role_create"),
    path("roles/<int:pk>/edit/", WorkshopRoleUpdateView.as_view(), name="role_update"),
    path("roles/<int:pk>/delete/", WorkshopRoleDeleteView.as_view(), name="role_delete"),
]
