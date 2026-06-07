from apps.core.templatetags.table_tags import TableAction


class TableActionDefaults:
    @staticmethod
    def edit(url_name: str, **overrides) -> TableAction:
        return TableAction(
            url_name=url_name,
            label="Editar",
            icon="edit",
            a_class="btn-table-edit",
            aria_label="Editar registro",
            **overrides,
        )

    @staticmethod
    def delete(url_name: str, **overrides) -> TableAction:
        return TableAction(
            url_name=url_name,
            label="Excluir",
            icon="delete",
            a_class="btn-table-delete",
            aria_label="Excluir registro",
            hx_target="#modal-container",
            hx_swap="innerHTML",
            hx_push_url="false",
            **overrides,
        )

    @staticmethod
    def view(url_name: str, **overrides) -> TableAction:
        return TableAction(
            url_name=url_name,
            label="Visualizar",
            icon="visibility",
            a_class="btn-table-view",
            aria_label="Visualizar registro",
            **overrides,
        )

    @staticmethod
    def copy(url_name: str, **overrides) -> TableAction:
        return TableAction(
            url_name=url_name,
            label="Copiar",
            icon="content_copy",
            a_class="btn-table-copy",
            aria_label="Copiar registro",
            **overrides,
        )
