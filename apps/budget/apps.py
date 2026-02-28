from django.apps import AppConfig


class BudgetConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.budget"
    verbose_name = "Orçamentos"

    def ready(self):
        from . import signals  # noqa: F401

