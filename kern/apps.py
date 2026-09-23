from django.apps import AppConfig


class KernConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'kern'
    verbose_name = 'Ridebuddies-Kern'

    def ready(self):
        # Legt zu jedem neuen Nutzer sein Profil an (siehe signale.py).
        from . import signale  # noqa: F401
