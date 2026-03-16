from django.urls import path

from apps.sources import views

app_name = "sources"

urlpatterns = [
    path("", views.SourceListView.as_view(), name="source_list"),
    path("create/", views.SourceCreateView.as_view(), name="source_create"),
    path("quick-create/", views.SourceQuickCreateView.as_view(), name="source_quick_create"),
    path("<int:pk>/edit/", views.SourceUpdateView.as_view(), name="source_update"),
    path("<int:pk>/delete/", views.SourceDeleteView.as_view(), name="source_delete"),
]
