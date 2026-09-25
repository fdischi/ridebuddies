"""
manage.py vorschlaege ANKER [--anzahl 5] [--alle] [--holen]

Zeigt die Vorschlaege fuer EINEN Anker (Nutzername) mit Begruendung je
Dimension - Karte TASK-120.13 (Schritt 8). Es gibt bewusst keinen Aufruf ohne
Anker: keine Rangliste ueber alle (Fabian, 24.09.2026).

Ohne --holen liest das Kommando nur gespeicherte Urteile und fragt keinen
Anbieter; fehlt ein noetiges Urteil, faellt der Kandidat mit 'nogo_offen' raus
(dann erst `manage.py matching_urteile`). --holen fragt fehlende beim
eingestellten Anbieter (RIDEBUDDIES_KI_ANBIETER) nach.

--alle zeigt zusaetzlich jeden Ausgeschlossenen mit Grund. Das ist ein
Werkzeug fuer den Betreiber in der Dummy-Phase: Die Gruende (etwa
'geschlechtspraeferenz') verraten Profilwerte, die ein Nutzer nicht sehen
darf - sie gehoeren nie in eine Nutzeransicht. Entfernungen erscheinen auch
hier nur gerundet, Punktzahlen nur relativ zu diesem Anker.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from kern import matching


class Command(BaseCommand):
    help = 'Vorschläge mit Begründung für einen Anker (TASK-120.13).'

    def add_arguments(self, parser):
        parser.add_argument('anker', help='Nutzername')
        parser.add_argument('--anzahl', type=int, default=5)
        parser.add_argument('--alle', action='store_true',
                            help='auch Ausgeschlossene mit Grund (nur Betreiber)')
        parser.add_argument('--holen', action='store_true',
                            help='fehlende KI-Urteile beim Anbieter holen')

    def handle(self, *args, anker, anzahl, alle, holen, **optionen):
        try:
            nutzer = get_user_model().objects.get(username=anker)
        except get_user_model().DoesNotExist:
            raise CommandError('Unbekannter Anker.') from None
        try:
            bewertungen = matching.alle_bewertungen(nutzer, holen=holen)
        except matching.KeineEinwilligung as f:
            raise CommandError(str(f)) from None
        zulaessig = [b for b in bewertungen if b.zulaessig][:anzahl]
        if not zulaessig:
            self.stdout.write(f'{anker}: keine Vorschläge.')
        for platz, b in enumerate(zulaessig, start=1):
            self.stdout.write(f'{platz}. {b.kandidat.username}  ({b.punkte:.3f})')
            for dim, text in b.begruendung.items():
                self.stdout.write(f'     {dim:14} {text}')
        if alle:
            self.stdout.write('Ausgeschlossen:')
            for b in bewertungen:
                if not b.zulaessig:
                    self.stdout.write(f'   {b.kandidat.username:28} '
                                      f'{", ".join(sorted(b.ausgeschlossen))}  '
                                      f'({matching.entfernung_text(b.intern_entfernung_km)})')
