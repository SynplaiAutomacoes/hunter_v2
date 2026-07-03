from django.urls import include, path

app_name = "messaging"

urlpatterns = [
    path("", include("apps.messaging.presentation.urls")),
]
