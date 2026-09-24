"""
Gemeinsame Grundlage der KI-Anbieter (Karte TASK-120.12).

Ein Anbieter beantwortet eine ANFRAGE: einen Zustand und ein dict
Kennung -> Frage. Der Matching-Code ruft trotzdem nicht `beantworten()`,
sondern `kern.urteile.beurteilen()` - dort wird protokolliert.

DIE SPERRE SITZT ZWEIMAL (Auflage der Gegenpruefung, 24.09.2026): im
Einstieg UND hier in der Grundklasse. `beantworten()` ist oeffentlich und
verlangt `betrifft` genauso wie der Einstieg; es prueft die Datensperre
(sperre.py) und ruft erst danach `_beantworten()` der Unterklasse. Grund:
`urteiler()` und die Anbieterklassen sind oeffentlich erreichbar - wer
`urteiler().beantworten(...)` direkt aufruft, soll an derselben Sperre
haengen bleiben, statt an ihr vorbei ins Netz zu gehen. Der Einstieg prueft
dadurch doppelt; das kostet zwei kleine Abfragen und ist gewollt.
Unterklassen ueberschreiben NUR `_beantworten()`, nie `beantworten()`.

SCHLUESSEL
Festlegung (nicht von Fabian entschieden): Die Schluessel stehen NICHT in
django.conf.settings, sondern werden erst beim Aufruf aus der Umgebung
gelesen. Grund: Djangos Fehlerseite (DEBUG) und das Fehlerprotokoll blenden
nur Einstellungen aus, deren Name API, KEY, TOKEN, SECRET, PASS ... enthaelt
- "SCHLUESSEL" gehoert nicht dazu, ein Settings-Eintrag
RIDEBUDDIES_JEV_SCHLUESSEL stuende dort im Klartext.

Je Anbieter zwei Wege, der erste gewinnt:
  RIDEBUDDIES_<X>_SCHLUESSEL        der Schluessel selbst (enduro-web: aus
                                    /etc/ridebuddies/ridebuddies.env ueber
                                    die EnvironmentFile der Unit)
  RIDEBUDDIES_<X>_SCHLUESSEL_DATEI  Pfad einer Datei, erste Zeile (VM 140:
                                    ~/.config/ridebuddies/, 0600)
Beides nie im Repo, nie in Karte oder Vault (Festlegung des Einlesens,
TASK-120.07). Fehlt beides, wirft der Anbieter SchluesselFehlt, BEVOR
irgendetwas gesendet wird.
"""
import logging
import os

from .fehler import DatensperreVerletzt, SchluesselFehlt

log = logging.getLogger('ridebuddies.urteile')


def schluessel_lesen(variable):
    wert = os.environ.get(variable, '').strip()
    if wert:
        return wert
    datei = os.environ.get(f'{variable}_DATEI', '').strip()
    if datei:
        try:
            with open(datei, encoding='utf-8') as f:
                wert = f.readline().strip()
        except OSError:
            raise SchluesselFehlt(f'{variable}_DATEI ist gesetzt, die Datei ist aber nicht '
                                  'lesbar.') from None
        if wert:
            return wert
        raise SchluesselFehlt(f'{variable}_DATEI zeigt auf eine leere Datei.')
    raise SchluesselFehlt(f'Kein Schlüssel: {variable} oder {variable}_DATEI setzen.')


class Anbieter:
    """Grundklasse. Unterklassen setzen `name` und `_beantworten()`."""
    name = ''
    # Variable fuer den Schluessel; None = braucht keinen (Test-Anbieter).
    schluessel_variable = None

    def schluessel_vorhanden(self):
        if self.schluessel_variable is None:
            return True
        try:
            schluessel_lesen(self.schluessel_variable)
        except SchluesselFehlt:
            return False
        return True

    def beantworten(self, zustand, fragen, *, betrifft, ohne_personen=False):
        """zustand: str | dict | list (JSON-faehig). fragen: dict Kennung -> Frage.
        betrifft/ohne_personen wie bei kern.urteile.beurteilen(). Gibt dict
        Kennung -> Urteil zurueck, fuer JEDE Kennung. Datensperre zuerst."""
        # Spaeter Import: sperre.py zieht kern.models, und dieses Modul soll
        # ohne geladene Apps importierbar bleiben.
        from . import sperre
        try:
            sperre.pruefen(betrifft, ohne_personen=ohne_personen)
        except DatensperreVerletzt as fehler:
            # Direkter Aufruf am Einstieg vorbei - trotzdem protokollieren,
            # mit denselben Regeln: Anzahl und Gruende, keine IDs, keine Kennung
            # (die ist hier nicht gegen das Muster geprueft).
            log.warning('urteil gesperrt anbieter=%s direkt betroffene=%d gruende=%s',
                        self.name, fehler.betroffene,
                        ','.join(f'{g}:{n}' for g, n in sorted(fehler.gruende.items())))
            raise
        return self._beantworten(zustand, fragen)

    def _beantworten(self, zustand, fragen):
        """Nur nach bestandener Sperre, nur aus beantworten() heraus."""
        raise NotImplementedError
