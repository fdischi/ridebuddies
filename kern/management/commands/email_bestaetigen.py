"""
manage.py email_bestaetigen <nutzername> [--email adresse]

Traegt die E-Mail-Adresse eines Nutzers in allauths EmailAddress als
bestaetigt UND primaer ein. Karte TASK-120.10, 23.09.2026.

Warum es das braucht: ACCOUNT_EMAIL_VERIFICATION = 'mandatory'. allauth laesst
auf /konto/login/ nur herein, wer eine bestaetigte Adresse hat - und
"bestaetigt" steht nicht am Nutzer, sondern in einer eigenen Tabelle
(account_emailaddress). Ein mit createsuperuser angelegtes Konto hat dort gar
keinen Eintrag. Genau daran scheiterte Fabian am 23.09.2026 nach TASK-120.04:
Der Superuser kam in /admin/ hinein, ueber /konto/login/ aber nicht, weil seine
Adresse unbestaetigt war. Seit /admin/login/ auf /konto/login/ umleitet
(kern/views.py), ist /konto/login/ der EINZIGE Weg hinein - ohne diesen
Schritt sperrt sich ein neuer Superuser also ganz aus.

Den Bestaetigungslink per Mail gibt es noch nicht (Mail-Backend = Konsole,
settings.py). Dieses Kommando ist der Weg des Betreibers auf der Maschine;
es prueft nicht, ob die Adresse dem Nutzer wirklich gehoert.

Ohne --email nimmt es nutzer.email. Mit --email wird die Adresse zusaetzlich
am Nutzer gesetzt (set_as_primary tut das). Es ist wiederholbar: Ein zweiter
Lauf aendert nichts. ACCOUNT_UNIQUE_EMAIL = True: Ist dieselbe Adresse schon
bei einem ANDEREN Nutzer bestaetigt, bricht es ab, statt die Datenbank-Sperre
(unique_verified_email) mit einem IntegrityError auszuloesen. Ebenso, wenn sie
nur als Nutzer.email eines anderen Kontos steht (unique am Nutzermodell).
"""
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = ('E-Mail-Adresse eines Nutzers in allauth als bestaetigt und primaer '
            'eintragen, damit /konto/login/ ihn hereinlaesst.')

    def add_arguments(self, parser):
        parser.add_argument('nutzername')
        parser.add_argument('--email', help='Adresse statt der am Nutzer hinterlegten')

    def handle(self, *args, nutzername, email=None, **optionen):
        Nutzer = get_user_model()
        try:
            nutzer = Nutzer.objects.get_by_natural_key(nutzername)
        except Nutzer.DoesNotExist:
            raise CommandError(f'Kein Nutzer {nutzername!r}.')

        # allauth speichert Adressen klein (EmailAddress.clean); gross
        # geschrieben entstuende sonst ein zweiter Eintrag neben dem alten.
        adresse = (email or nutzer.email or '').strip().lower()
        if not adresse:
            raise CommandError(f'{nutzername} hat keine E-Mail-Adresse; --email angeben.')

        if EmailAddress.objects.filter(email__iexact=adresse, verified=True).exclude(
                user=nutzer).exists():
            raise CommandError(f'{adresse} ist schon bei einem anderen Nutzer bestätigt.')

        # Nutzer.email ist unique (kern/models.py). Steht die Adresse schon am
        # Konto eines ANDEREN Nutzers - auch ohne bestaetigte EmailAddress -,
        # scheiterte set_as_primary sonst mitten im Lauf an einem IntegrityError
        # (Gegenpruefung TASK-120.10, 23.09.2026). iexact, weil allauth
        # Adressen ohne Ruecksicht auf Gross-/Kleinschreibung vergleicht.
        if Nutzer.objects.filter(email__iexact=adresse).exclude(pk=nutzer.pk).exists():
            raise CommandError(f'{adresse} steht schon am Konto eines anderen Nutzers.')

        with transaction.atomic():
            eintrag = EmailAddress.objects.filter(user=nutzer, email__iexact=adresse).first()
            if eintrag is None:
                eintrag = EmailAddress.objects.create(user=nutzer, email=adresse)
            if not eintrag.verified:
                eintrag.verified = True
                eintrag.save(update_fields=['verified'])
            if not eintrag.primary or (nutzer.email or '').lower() != eintrag.email.lower():
                # Setzt eine bisherige primaere Adresse zurueck und schreibt
                # die Adresse an den Nutzer (allauth.account.utils.user_email).
                eintrag.set_as_primary()

        self.stdout.write(self.style.SUCCESS(
            f'{nutzer.get_username()}: {eintrag.email} bestätigt und primär.'))
