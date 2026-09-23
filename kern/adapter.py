"""
Registrierung per Umgebungsschalter, Vorgabe: ZU.

Festlegung der Hauptsitzung vom 23.09.2026 (Karte TASK-120.04), nicht von
Fabian entschieden: Solange auf enduro-web nur Dummy-Konten laufen und keine
Mail rausgeht (E-Mail-Versand ist offener Punkt, Backend = Konsole), soll sich
niemand selbst registrieren koennen. Die E-Mail-Bestaetigung ist Pflicht
(ACCOUNT_EMAIL_VERIFICATION = 'mandatory'); ohne Mailversand bliebe ein fremdes
Konto ohnehin unbestaetigt haengen - der Schalter verhindert, dass es ueberhaupt
entsteht. Konten legt bis dahin der Admin an (oder der Dummy-Generator, TASK-120.05).

Auf mit RIDEBUDDIES_REGISTRIERUNG_OFFEN=1. Der Schalter wird bei jeder Anfrage
gelesen, nicht beim Import, damit Tests ihn per override_settings umstellen
koennen (settings.RIDEBUDDIES_REGISTRIERUNG_OFFEN).
"""
from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class KontoAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return bool(getattr(settings, 'RIDEBUDDIES_REGISTRIERUNG_OFFEN', False))
