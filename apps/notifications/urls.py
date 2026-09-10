from django.urls import path
from apps.notifications.presentation.views.notification_views import (
    NotificationDeleteView,
    NotificationDropdownView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationUnreadCountView,
)
from apps.notifications.presentation.views.system_management_views import (
    NotificationBroadcastView,
    NotificationUsersOptionsView,
    SystemManageDashboardView,
)

app_name = "notifications"

urlpatterns = [
    path("", NotificationListView.as_view(), name="list"),
    path("dropdown/", NotificationDropdownView.as_view(), name="dropdown"),
    path("read/", NotificationMarkReadView.as_view(), name="mark_read"),
    path("read/<int:pk>/", NotificationMarkReadView.as_view(), name="mark_read_single"),
    path("read-all/", NotificationMarkAllReadView.as_view(), name="mark_all_read"),
    path("<int:pk>/delete/", NotificationDeleteView.as_view(), name="delete"),
    path("unread-count/", NotificationUnreadCountView.as_view(), name="unread_count"),
    # System Management
    path("system/manage/", SystemManageDashboardView.as_view(), name="system_manage"),
    path("system/manage/notifications/broadcast/", NotificationBroadcastView.as_view(), name="broadcast"),
    path("system/manage/notifications/users-options/", NotificationUsersOptionsView.as_view(), name="users_options"),
]
