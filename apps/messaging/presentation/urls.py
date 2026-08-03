from django.urls import path

from apps.messaging.presentation.views import (
    dispatch_status_views,
    message_group_views,
    message_template_views,
    satisfaction_review_views,
    segment_preview_view,
)

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
    path("groups/<int:pk>/dispatch/", message_group_views.CustomerMessageGroupDispatchView.as_view(), name="customer_message_group_dispatch"),
    path("groups/<int:pk>/history/", message_group_views.CustomerMessageGroupHistoryView.as_view(), name="customer_message_group_history"),
    # Satisfaction reviews (management)
    path("reviews/", satisfaction_review_views.SatisfactionReviewListView.as_view(), name="satisfaction_review_list"),
    path(
        "reviews/<int:pk>/detail/",
        satisfaction_review_views.SatisfactionReviewDetailModalView.as_view(),
        name="satisfaction_review_detail_modal",
    ),
    # Worker status ingest (also served by dedicated ASGI process)
    path("dispatch/status/", dispatch_status_views.MessageDispatchStatusIngestView.as_view(), name="dispatch_status_ingest"),
]
