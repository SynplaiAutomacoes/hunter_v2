from django.apps import AppConfig


class CustomerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = "apps.customer"
    verbose_name = "Clientes"

    def ready(self) -> None:
        from apps.customer.importing import register_customer_import_adapter

        register_customer_import_adapter()

