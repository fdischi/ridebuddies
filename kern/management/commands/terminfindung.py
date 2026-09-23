"""
manage.py terminfindung <ausfahrt>

Gibt die Terminuebersicht einer Ausfahrt als Text aus (Karte TASK-120.06,
23.09.2026) - je Termin eine Zeile, sortiert nach Prozent absteigend, bei
Gleichstand nach Datum:

    Sa 17.04.2027 vormittags – 100 % – fehlt: – – Vorbehalt: – – keine Antwort: –

Gedacht zum Pruefen auf enduro-web, solange es keine Oberflaeche gibt
(Schritt 13). Es liest nur. Die Regeln (Nenner, Gewichtung, Reisen, Vorrang
der Antworten) stehen im Kopf von kern/terminfindung.py, nicht hier.

<ausfahrt> ist die ID oder ein Teil des Titels. Beim Titel gilt ein exakter
Treffer (ohne Gross-/Kleinschreibung) vor einem Teiltreffer; passen mehrere,
bricht das Kommando ab und nennt sie mit ID, statt eine zu raten - Dummy-Titel
koennen neben echten Ausfahrten gleichen Namens stehen.
"""
from django.core.management.base import BaseCommand, CommandError

from kern import terminfindung
from kern.models import Ausfahrt


class Command(BaseCommand):
    help = ('Terminübersicht einer Ausfahrt: Prozent je Termin, wer fehlt, wer mit Vorbehalt, '
            'wer noch nicht geantwortet hat (TASK-120.06).')

    def add_arguments(self, parser):
        parser.add_argument('ausfahrt', help='ID oder Teil des Titels')

    def handle(self, *args, ausfahrt, **optionen):
        gefunden = self._finden(ausfahrt)
        uebersicht = terminfindung.terminuebersicht(gefunden)
        crew = f'Crew {gefunden.crew}' if gefunden.crew_id else 'ohne Crew'
        self.stdout.write(f'{gefunden.titel} (ID {gefunden.pk}, {crew})')
        if not uebersicht:
            self.stdout.write('Keine Termine.')
            return
        self.stdout.write(f'Nenner: {uebersicht[0].nenner}')
        for auswertung in uebersicht:
            self.stdout.write(terminfindung.zeile(auswertung))

    @staticmethod
    def _finden(suche):
        if suche.isdigit():
            try:
                return Ausfahrt.objects.select_related('crew').get(pk=int(suche))
            except Ausfahrt.DoesNotExist:
                raise CommandError(f'Keine Ausfahrt mit ID {suche}.')
        treffer = list(Ausfahrt.objects.select_related('crew').filter(titel__iexact=suche))
        if not treffer:
            treffer = list(Ausfahrt.objects.select_related('crew')
                           .filter(titel__icontains=suche))
        if not treffer:
            raise CommandError(f'Keine Ausfahrt passt zu „{suche}“.')
        if len(treffer) > 1:
            liste = '; '.join(f'{a.pk}: {a.titel}' for a in sorted(treffer, key=lambda a: a.pk))
            raise CommandError(f'Mehrere Ausfahrten passen zu „{suche}“ – bitte die ID '
                               f'angeben: {liste}')
        return treffer[0]
