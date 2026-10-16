from django.apps import AppConfig


class SuppliersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = "apps.suppliers"
    verbose_name = "Fornecedores"

    def ready(self) -> None:
        from apps.suppliers.importing import register_supplier_import_adapter

        register_supplier_import_adapter()

