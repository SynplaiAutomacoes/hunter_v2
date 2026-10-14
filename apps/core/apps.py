from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = "Core"

    def ready(self) -> None:
        # Ensure infrastructure models (locks, import batches, snapshots) are registered.
        import apps.core.infrastructure.models  # noqa: F401

