"""
manage.py dummies_anlegen [--kennwort-datei PFAD] [--abraeumen]

Stellt den festen Dummy-Bestand her (Karte TASK-120.05, 23.09.2026) oder raeumt
ihn ab. Der Bestand selbst - 37 Dummies, drei Crews, fuenf Ausfahrten, zwei
Reisen, Beziehungen - steht in kern/dummies.py; das Pruefblatt dazu in
docs/pruefblatt-matching.md/.json.

Ohne Option: legt an, was fehlt, und gleicht ab, was abweicht. Ein zweiter Lauf
auf unveraendertem Bestand schreibt nichts ("nichts geschrieben" in der Ausgabe).
Neue Dummies haben kein nutzbares Kennwort; ein vorhandenes bleibt stehen.

--kennwort-datei PFAD: liest EIN Kennwort aus der Datei (erste Zeile, Zeilenende
abgeschnitten) und setzt es fuer alle Dummies - nur dort, wo das gespeicherte
nicht passt. Das Kennwort geht nie auf stdout/stderr, in kein Log und nicht ins
Repo; auch Fehlermeldungen nennen es nicht. Warum eine Datei und kein Argument:
Ein Argument stuende in der Shell-History und in `ps` fuer jeden Benutzer der
Maschine lesbar.

--kennwort-datei - liest das Kennwort von der Standardeingabe (dem geerbten
Dateideskriptor 0), fuer den Serveraufruf
`runuser -u ridebuddies -- ... --kennwort-datei - < /root/.config/ridebuddies/dummy-kennwort`.
Warum nicht einfach /dev/stdin als Pfad: Unter runuser oeffnet
Path('/dev/stdin').read_text() ueber /proc/self/fd/0 den Inode NEU, und der
Kernel prueft dabei die Rechte der root-eigenen 0600-Datei gegen den Benutzer
ridebuddies - EACCES (in der Gegenpruefung vom 23.09.2026 nachgestellt). Der
schon offene fd 0 dagegen ist lesbar, weil root ihn geoeffnet hat. Die Datei
bleibt so root 0600 und wird nie fuer ridebuddies lesbar. Bei "-" gibt es
keinen Rechtehinweis - es gibt keine Datei, deren Rechte man pruefen koennte.

--abraeumen: loescht alle Dummies (Nutzername `dummy-` UND E-Mail
`@example.invalid`) samt allem, was an ihnen haengt, und Crews/Ausfahrten, die
nur Dummies gehoeren. Echte Konten bleiben unberuehrt - auch dann, wenn sie mit
einem Dummy verbunden sind (die Verbindung verschwindet, der Nutzer nicht).

Beides laeuft in einer Transaktion: bricht etwas ab, bleibt die Datenbank, wie
sie war.
"""
import sys
from pathlib import Path

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from kern import dummies


class Command(BaseCommand):
    help = ('Festen Dummy-Bestand (TASK-120.05) anlegen oder mit --abraeumen entfernen. '
            'Idempotent.')

    def add_arguments(self, parser):
        parser.add_argument('--kennwort-datei', metavar='PFAD',
                            help='Datei mit einem Kennwort für alle Dummies, "-" = Standardeingabe '
                                 '(wird nie ausgegeben)')
        parser.add_argument('--abraeumen', action='store_true',
                            help='alle Dummies und nur ihnen gehörende Crews/Ausfahrten löschen')

    def handle(self, *args, kennwort_datei=None, abraeumen=False, **optionen):
        if abraeumen:
            if kennwort_datei:
                raise CommandError('--abraeumen und --kennwort-datei schließen sich aus.')
            geloescht = dummies.abraeumen()
            self._tabelle('Gelöscht', geloescht)
            self.stdout.write(self.style.SUCCESS(
                f'Abgeräumt: {geloescht.get("Nutzer", 0)} Dummies. '
                f'Übrig: {dummies.dummies().count()}.'))
            return

        kennwort = self._kennwort_lesen(kennwort_datei) if kennwort_datei else None
        try:
            zaehler = dummies.anlegen(kennwort=kennwort)
        except dummies.DummyFehler as fehler:
            raise CommandError(str(fehler))

        self._tabelle('Bestand (Dummy-Datensätze)', dummies.bestand())
        if zaehler.nichts_geschrieben:
            self.stdout.write(self.style.SUCCESS('Nichts geschrieben – Bestand war vollständig.'))
            return
        if zaehler.neu:
            self._tabelle('Neu angelegt', zaehler.neu)
        if zaehler.geaendert:
            self._tabelle('Angeglichen', zaehler.geaendert)
        self.stdout.write(self.style.SUCCESS('Dummy-Bestand hergestellt.'))

    def _kennwort_lesen(self, pfad):
        von_stdin = pfad == '-'
        if von_stdin:
            # sys.stdin zur Laufzeit nachschlagen (nicht beim Import binden),
            # damit der Test es ersetzen kann.
            inhalt = sys.stdin.read()
        else:
            datei = Path(pfad)
            try:
                inhalt = datei.read_text(encoding='utf-8')
            except OSError as fehler:
                # strerror statt str(fehler): nennt den Grund, nicht mehr.
                raise CommandError(f'Kennwortdatei nicht lesbar: {fehler.strerror}')
        zeilen = inhalt.splitlines()
        kennwort = zeilen[0] if zeilen else ''
        if not kennwort:
            raise CommandError('Kennwortdatei ist leer (erste Zeile).')
        if not von_stdin and datei.stat().st_mode & 0o077:
            self.stderr.write(self.style.WARNING(
                f'Hinweis: {pfad} ist für Gruppe/andere zugänglich - besser chmod 600.'))
        try:
            validate_password(kennwort)
        except ValidationError as fehler:
            # Djangos Meldungen nennen das Kennwort nicht, nur den Mangel.
            raise CommandError('Kennwort abgelehnt: ' + ' '.join(fehler.messages))
        return kennwort

    def _tabelle(self, titel, werte):
        self.stdout.write(f'{titel}:')
        if not werte:
            self.stdout.write('  (nichts)')
        for name in sorted(werte):
            self.stdout.write(f'  {name:<26}{werte[name]:>5}')
