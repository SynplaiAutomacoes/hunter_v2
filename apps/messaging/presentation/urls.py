from django.urls import path

from apps.messaging.presentation.views import message_group_views, message_template_views, segment_preview_view

urlpatterns = [
    # Message Templates
    path("", message_template_views.MessageTemplateListView.as_view(), name="message_template_list"),
    path("create/", message_template_views.MessageTemplateCreateView.as_view(), name="message_template_create"),
    path("quick-create/", message_template_views.MessageTemplateQuickCreateView.as_view(), name="message_template_quick_create"),
    path("<int:pk>/edit/", message_template_views.MessageTemplateUpdateView.as_view(), name="message_template_update"),
    path("<int:pk>/delete/", message_template_views.MessageTemplateDeleteView.as_view(), name="message_template_delete"),
    # Customer Message Groups
    path("groups/", message_group_views.CustomerMessageGroupListView.as_view(), name="customer_message_group_list"),
    path("groups/create/", message_group_views.CustomerMessageGroupCreateView.as_view(), name="customer_message_group_create"),
    path("groups/customer-picker/", message_group_views.CustomerMessageGroupCustomerPickerView.as_view(), name="customer_message_group_customer_picker"),
    path("groups/preview-segment/", segment_preview_view.CustomerMessageGroupSegmentPreviewView.as_view(), name="customer_message_group_segment_preview"),
    path("groups/<int:pk>/edit/", message_group_views.CustomerMessageGroupUpdateView.as_view(), name="customer_message_group_update"),
    path("groups/<int:pk>/delete/", message_group_views.CustomerMessageGroupDeleteView.as_view(), name="customer_message_group_delete"),
]
