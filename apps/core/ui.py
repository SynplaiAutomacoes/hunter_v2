class TableActionStyles:
    """
    Padronização visual para ações de tabela.
    As chaves devem corresponder aos campos da dataclass TableAction.
    Icones são do Material Icons.
    """

    EDIT = {
        "label": "Editar",
        "icon": "edit",
        "a_class": "btn btn-primary btn-sm",
        "aria_label": "Editar registro",
    }

    DELETE = {
        "label": "Excluir",
        "icon": "delete",
        "a_class": "btn btn-error btn-sm text-white",
        "aria_label": "Excluir registro",
    }
