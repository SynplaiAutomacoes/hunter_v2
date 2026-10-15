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
    path("colunas/<int:pk>/mover/", views.YardColumnMoveView.as_view(), name="column_move"),
    path("colunas/reordenar/", views.YardColumnsReorderView.as_view(), name="columns_reorder"),
    path("preferencia/similares/", views.YardPreferenceToggleView.as_view(), name="preference_toggle_similar"),
    path("ocultos/novo/", views.YardHiddenStatusCreateView.as_view(), name="hidden_create"),
    path("ocultos/<int:pk>/excluir/", views.YardHiddenStatusDeleteView.as_view(), name="hidden_delete"),
    path("grupos/novo/", views.YardStatusGroupCreateView.as_view(), name="group_create"),
    path("grupos/<int:pk>/editar/", views.YardStatusGroupUpdateView.as_view(), name="group_update"),
    path("grupos/<int:pk>/excluir/", views.YardStatusGroupDeleteView.as_view(), name="group_delete"),
]
