from django.urls import path

from apps.messaging import views

app_name = "messaging"


urlpatterns = [
    path("", views.MessageTemplateListView.as_view(), name="message_template_list"),
    path("create/", views.MessageTemplateCreateView.as_view(), name="message_template_create"),
    path("<int:pk>/edit/", views.MessageTemplateUpdateView.as_view(), name="message_template_update"),
    path("<int:pk>/delete/", views.MessageTemplateDeleteView.as_view(), name="message_template_delete"),
]
