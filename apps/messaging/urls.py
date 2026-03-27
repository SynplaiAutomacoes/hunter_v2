from django.urls import path

from apps.messaging import views

app_name = "messaging"


urlpatterns = [
    path("", views.MessageTemplateListView.as_view(), name="message_template_list"),
    path("create/", views.MessageTemplateCreateView.as_view(), name="message_template_create"),
    path("quick-create/", views.MessageTemplateQuickCreateView.as_view(), name="message_template_quick_create"),
    path("<int:pk>/edit/", views.MessageTemplateUpdateView.as_view(), name="message_template_update"),
    path("<int:pk>/delete/", views.MessageTemplateDeleteView.as_view(), name="message_template_delete"),
    path("groups/", views.CustomerMessageGroupListView.as_view(), name="customer_message_group_list"),
    path("groups/create/", views.CustomerMessageGroupCreateView.as_view(), name="customer_message_group_create"),
    path("groups/customer-picker/", views.CustomerMessageGroupCustomerPickerView.as_view(), name="customer_message_group_customer_picker"),
    path("groups/<int:pk>/edit/", views.CustomerMessageGroupUpdateView.as_view(), name="customer_message_group_update"),
    path("groups/<int:pk>/delete/", views.CustomerMessageGroupDeleteView.as_view(), name="customer_message_group_delete"),
]
