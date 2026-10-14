from django.apps import AppConfig


class FinanceConfig(AppConfig):
    name = 'apps.finance'
    verbose_name = "Financeiro"

    def ready(self) -> None:
        from apps.finance.importing import register_payable_import_adapter

        register_payable_import_adapter()

