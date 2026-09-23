"""
Profil automatisch beim Anlegen eines Nutzers.

Warum ein Signal und nicht eine Zeile in einer Registrierungs-View: Nutzer
entstehen hier auf drei Wegen - allauth-Registrierung, Django-Admin und
`createsuperuser`, ab Schritt 5 (TASK-120.05) zusaetzlich ueber den
Dummy-Generator. Die Sichtbarkeitsschicht setzt voraus, dass jeder Nutzer ein
Profil hat (Feldstufen stehen dort); ein Nutzer ohne Profil waere ein Sonderfall,
den jede Abfrage abfangen muesste. Das Signal deckt alle Wege ab.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def profil_anlegen(sender, instance, created, raw=False, **kwargs):
    # raw=True heisst: loaddata spielt Fixtures ein, das Profil kommt dann
    # aus der Fixture selbst.
    if created and not raw:
        from .models import Profil

        Profil.objects.get_or_create(nutzer=instance)
