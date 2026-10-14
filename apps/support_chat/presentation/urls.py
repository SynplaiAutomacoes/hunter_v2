from django.urls import path

from apps.support_chat.presentation.views.chat_views import (
    SupportChatAskView,
    SupportChatBootstrapView,
    SupportChatHistoryView,
    SupportChatNewSessionView,
    SupportChatSessionsView,
    SupportChatTitlesView,
)

app_name = "support_chat"

urlpatterns = [
    path("bootstrap/", SupportChatBootstrapView.as_view(), name="bootstrap"),
    path("ask/", SupportChatAskView.as_view(), name="ask"),
    path("sessions/", SupportChatSessionsView.as_view(), name="sessions"),
    path("sessions/new/", SupportChatNewSessionView.as_view(), name="new_session"),
    path("history/", SupportChatHistoryView.as_view(), name="history"),
    path("titles/", SupportChatTitlesView.as_view(), name="titles"),
]
