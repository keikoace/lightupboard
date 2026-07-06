from django.apps import AppConfig


class RatesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.rates'

    def ready(self):
        import apps.rates.signals  # noqa: F401
