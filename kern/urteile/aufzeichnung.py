"""
Test-Anbieter und Aufzeichnung (Karte TASK-120.12).

Zwei Dinge, die zusammengehoeren:

TestAnbieter - antwortet ohne Netz. Reihenfolge je Frage:
  1. `vorgaben[kennung]` - feste Verteilung oder Funktion (zustand, frage) ->
     Verteilung (Form wie in formen.urteil_aus_verteilung). Fuer Tests, die
     ein bestimmtes Urteil brauchen.
  2. Aufzeichnung - Schluessel ist formen.frage_schluessel(zustand, frage),
     also ein Hash ueber Zustand und Frage. Fuer den Pruefblatt-Test
     (Schritt 8), der mit einmal live geholten Urteilen offline laufen soll.
  3. sonst: `streng=True` -> AnbieterFehler('keine_aufzeichnung');
     `streng=False` (Voreinstellung) -> NEUTRAL: Noul 0,5, Auswahl und
     Stufenwert gleichverteilt, Vertrauen 0. Neutral statt Zufall, weil ein
     Test-Anbieter, der etwas zu wissen vorgibt, im Betrieb (Voreinstellung
     'test') Matching-Ergebnisse vortaeuschen wuerde. Festlegung (nicht von
     Fabian entschieden).
  Er ZAEHLT: `aufrufe` (Anfragen) und `fragen` (einzelne Fragen). Schritt 8
  braucht das fuer "Gewichtsaenderung ohne neuen Anbieteraufruf"
  (TASK-120.07 #5). Auch der Test-Anbieter sitzt hinter der Datensperre
  (Grundklasse, anbieter.py) - gezaehlt wird erst NACH der Sperre, ein
  gesperrter Aufruf zaehlt also 0.

Aufzeichner - legt sich um einen echten Anbieter und schreibt jede Antwort in
  eine JSON-Datei, die der TestAnbieter wieder lesen kann.
  Festlegung (nicht von Fabian entschieden): In der Datei steht NUR der Hash
  und das Urteil (Wert, Verteilung, Vertrauen, Anbieter, Modell, Tokens) -
  kein Zustand, keine Anweisung, keine Stufen- oder Optionsbeschreibung, kein
  Schluessel, keine HTTP-Kopfzeile. Was von der Frage doch drinsteht: die
  OPTIONSNAMEN einer Auswahl (Schluessel der Verteilung, z. B. 'geniesser')
  - das sind Konstanten des Aufrufers, keine Texte. Die Legende eines
  Stufenwerts (Stufentexte) schreiben wir bewusst NICHT mit (Auflage der
  Gegenpruefung, 24.09.2026: vorher stand sie drin, und der Kopf behauptete
  trotzdem "kein Fragetext"); beim Abspielen kommt sie aus der Frage, die ja
  ueber den Hash ohnehin genau passen muss. Die
  Aufzeichnung soll ins Repo (Festlegung des Einlesens, TASK-120.07), das
  Repo hat einen oeffentlichen GitHub-Spiegel, und unter den Zustaenden kann
  Fabians eigenes Profil sein. Wer sehen will, welche Frage zu einem Eintrag
  gehoert, rechnet den Hash aus seiner Frage nach.
  Geschrieben wird atomar (Hilfsdatei + os.replace). Zwei Aufzeichner auf
  dieselbe Datei gleichzeitig verlieren Eintraege - gedacht ist ein Lauf von
  Hand (manage.py), kein Dauerbetrieb.
"""
import json
import os
import tempfile
from pathlib import Path

from .anbieter import Anbieter
from .fehler import AnbieterFehler
from .formen import (
    Auswahl,
    Noul,
    Stufenwert,
    frage_schluessel,
    urteil_als_dict,
    urteil_aus_dict,
    urteil_aus_verteilung,
)

FORMAT_VERSION = 1
HINWEIS = ('Aufzeichnung von KI-Urteilen fuer kern.urteile (TASK-120.12). Schluessel = '
           'SHA-256 ueber Zustand und Frage (formen.frage_schluessel). Kein Zustand, '
           'keine Anweisung, keine Stufen- oder Optionsbeschreibung, kein API-Schluessel; '
           'Optionsnamen einer Auswahl stehen als Schluessel der Verteilung drin.')


def aufzeichnung_laden(pfad):
    pfad = Path(pfad)
    if not pfad.exists():
        return {}
    daten = json.loads(pfad.read_text(encoding='utf-8'))
    if daten.get('version') != FORMAT_VERSION:
        raise ValueError('Aufzeichnung hat ein unbekanntes Format.')
    return dict(daten.get('eintraege') or {})


def _neutral(frage):
    if isinstance(frage, Noul):
        return 0.5
    if isinstance(frage, Auswahl):
        return {o: 1.0 for o in frage.optionen}
    if isinstance(frage, Stufenwert):
        return [1.0] * len(frage.stufen)
    raise TypeError('Unbekannte Frageform.')


class TestAnbieter(Anbieter):
    name = 'test'
    # pytest/unittest sollen die Klasse nicht fuer einen Testfall halten.
    __test__ = False

    def __init__(self, aufzeichnung=None, vorgaben=None, streng=False):
        if isinstance(aufzeichnung, (str, Path)):
            aufzeichnung = aufzeichnung_laden(aufzeichnung)
        self.aufzeichnung = dict(aufzeichnung or {})
        self.vorgaben = dict(vorgaben or {})
        self.streng = streng
        self.aufrufe = 0
        self.fragen = 0

    def _beantworten(self, zustand, fragen):
        self.aufrufe += 1
        self.fragen += len(fragen)
        return {k: self._eins(zustand, k, f) for k, f in fragen.items()}

    def _eins(self, zustand, kennung, frage):
        if kennung in self.vorgaben:
            vorgabe = self.vorgaben[kennung]
            verteilung = vorgabe(zustand, frage) if callable(vorgabe) else vorgabe
            return urteil_aus_verteilung(frage, verteilung, anbieter=self.name, modell='vorgabe')
        eintrag = self.aufzeichnung.get(frage_schluessel(zustand, frage))
        if eintrag is not None:
            urteil = eintrag['urteil']
            if urteil.get('form') != frage.form:
                raise AnbieterFehler('antwortformat')
            # Anbieter 'test', Herkunft im Modell; Tokens 0, weil jetzt nichts
            # verbraucht wurde (die echten stehen in der Datei). Die Legende
            # steht nicht in der Datei - sie kommt aus der Frage.
            extra = {}
            if isinstance(frage, Stufenwert):
                extra['legende'] = {str(i): s for i, s in enumerate(frage.stufen)}
            return urteil_aus_dict(urteil, anbieter=self.name,
                                   modell=f"aufzeichnung:{urteil['anbieter']}/{urteil['modell']}",
                                   tokens_ein=0, tokens_aus=0, **extra)
        if self.streng:
            raise AnbieterFehler('keine_aufzeichnung')
        return urteil_aus_verteilung(frage, _neutral(frage), anbieter=self.name, modell='neutral')


class Aufzeichner(Anbieter):
    """Echter Anbieter plus Mitschnitt in `pfad` (siehe Modulkopf)."""

    def __init__(self, anbieter, pfad):
        self.innen = anbieter
        self.pfad = Path(pfad)
        self.name = anbieter.name
        self.schluessel_variable = anbieter.schluessel_variable

    def _beantworten(self, zustand, fragen):
        # Die Sperre hat beantworten() der Grundklasse schon geprueft - fuer
        # DIESEN Aufzeichner. Deshalb das innere _beantworten(), nicht das
        # oeffentliche (das braeuchte betrifft ein zweites Mal).
        urteile = self.innen._beantworten(zustand, fragen)
        eintraege = aufzeichnung_laden(self.pfad)
        for kennung, frage in fragen.items():
            d = urteil_als_dict(urteile[kennung])
            d.pop('legende', None)   # Stufentexte nicht mitschreiben (Modulkopf)
            eintraege[frage_schluessel(zustand, frage)] = {'urteil': d}
        self._schreiben(eintraege)
        return urteile

    def _schreiben(self, eintraege):
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        inhalt = json.dumps({'version': FORMAT_VERSION, 'hinweis': HINWEIS,
                             'eintraege': dict(sorted(eintraege.items()))},
                            ensure_ascii=False, indent=1, sort_keys=False) + '\n'
        fd, hilf = tempfile.mkstemp(dir=self.pfad.parent, prefix='.aufzeichnung-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(inhalt)
            os.replace(hilf, self.pfad)
        except BaseException:
            if os.path.exists(hilf):
                os.unlink(hilf)
            raise
