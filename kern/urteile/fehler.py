"""
Ausnahmen der Urteils-Schnittstelle (Karte TASK-120.12).

REGEL FUER JEDE MELDUNG HIER: keine Personendaten. Ausnahmetexte landen in
Protokollen, Tracebacks und Django-Fehlerseiten - also nie Nutzername, E-Mail,
Nutzer-ID, Profiltext, Fragetext oder den Antwortkoerper eines Anbieters (ein
HTTP-422 von Jev nennt das beanstandete Feld und kann dabei den Zustand
wiederholen). Was die Meldung traegt, sind Arten und Anzahlen.
"""


class UrteilFehler(Exception):
    """Oberklasse - wer "irgendwas mit der KI ging schief" fangen will."""
    art = 'unbekannt'


class DatensperreVerletzt(UrteilFehler):
    """Ein betroffener Nutzer darf nicht an einen KI-Anbieter (Entscheidung
    Fabians vom 23.09.2026, siehe kern/urteile/sperre.py). Kein Anbieter wurde
    aufgerufen.

    `gruende` zaehlt je Grund, wie viele Nutzer ihn ausgeloest haben
    ({'kein_dummy_und_nicht_freigegeben': 1, 'keine_ki_einwilligung': 2}) -
    bewusst ohne IDs. Wer wissen will, WER, prueft mit
    sperre.pruefen([nutzer]) einzeln nach; das bleibt beim Aufrufer.
    """
    art = 'datensperre'

    def __init__(self, gruende, betroffene):
        self.gruende = dict(gruende)
        self.betroffene = betroffene
        teile = ', '.join(f'{g}: {n}' for g, n in sorted(self.gruende.items()))
        super().__init__(f'Datensperre: {betroffene} betroffene Nutzer, gesperrt wegen {teile}. '
                         'Kein Anbieteraufruf.')


class SchluesselFehlt(UrteilFehler):
    """Kein API-Schluessel konfiguriert - es wurde nichts gesendet. Die
    Meldung nennt die Variablennamen, nie einen Wert."""
    art = 'schluessel_fehlt'


class AnbieterFehler(UrteilFehler):
    """Der Anbieter hat nicht (brauchbar) geantwortet.

    art: 'http_<status>' | 'zeitlimit' | 'netz' | 'antwortformat'
    Der Antwortkoerper wird NICHT mitgefuehrt (siehe Modulkopf)."""

    def __init__(self, art, versuche=1):
        self.art = art
        self.versuche = versuche
        super().__init__(f'KI-Anbieter: {art} (nach {versuche} Versuch(en)).')
