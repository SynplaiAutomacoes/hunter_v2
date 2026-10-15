from django.urls import path

from apps.yard import views

app_name = "yard"

urlpatterns = [
    path("", views.YardBoardView.as_view(), name="board"),
    path("conteudo/", views.YardBoardContentView.as_view(), name="board_content"),
    path("configurar/", views.YardConfigModalView.as_view(), name="config_modal"),
    path("colunas/nova/", views.YardColumnCreateView.as_view(), name="column_create"),
    path("colunas/<int:pk>/editar/", views.YardColumnUpdateView.as_view(), name="column_update"),
    path("colunas/<int:pk>/excluir/", views.YardColumnDeleteView.as_view(), name="column_delete"),
]
