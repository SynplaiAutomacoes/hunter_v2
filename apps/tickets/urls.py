from django.urls import path

from apps.tickets.presentation.views.ticket_views import (
    AllTicketListView,
    MyTicketListView,
    TicketApproveView,
    TicketAttachmentUploadView,
    TicketCaptureView,
    TicketCreateView,
    TicketDetailView,
    TicketMessageCreateView,
    TicketReassignView,
    TicketRejectView,
    TicketStatusUpdateView,
)

app_name = "tickets"

urlpatterns = [
    path("meus/", MyTicketListView.as_view(), name="my_list"),
    path("geral/", AllTicketListView.as_view(), name="all_list"),
    path("novo/", TicketCreateView.as_view(), name="create"),
    path("<int:pk>/", TicketDetailView.as_view(), name="ticket_detail"),
    path("<int:pk>/capturar/", TicketCaptureView.as_view(), name="capture"),
    path("<int:pk>/reatribuir/", TicketReassignView.as_view(), name="reassign"),
    path("<int:pk>/status/", TicketStatusUpdateView.as_view(), name="status_update"),
    path("<int:pk>/aprovar/", TicketApproveView.as_view(), name="approve"),
    path("<int:pk>/rejeitar/", TicketRejectView.as_view(), name="reject"),
    path("<int:pk>/anexos/", TicketAttachmentUploadView.as_view(), name="attachments_upload"),
    path("<int:pk>/mensagens/", TicketMessageCreateView.as_view(), name="message_create"),
]
