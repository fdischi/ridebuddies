"""
Die drei Urteilsformen und ihre typisierten Ergebnisse (Karte TASK-120.12).

Vorbild ist Jev (TypeSafe, System One). Deren HTTP-Vertrag kennt genau drei
Fragetypen, und die uebernehmen wir mit derselben Bedeutung, damit Jev ohne
Uebersetzung dranhaengt und Claude sie nachbildet:

- Noul      - ja/nein, Antwort ist die Wahrscheinlichkeit fuer "ja" (0..1).
- Auswahl   - Jevs "choice": eine Option aus einer festen Menge, dazu die
              Verteilung ueber alle Optionen. Jev: hoechstens 255 Optionen.
- Stufenwert - Jevs "score": geordnete Stufen (2..10), Antwort ist der
              wahrscheinlichkeitsgewichtete Mittelwert der Stufenindizes -
              kann also zwischen zwei Stufen liegen (1,43 heisst "zwischen
              Stufe 1 und 2, naeher an 1").

Quelle: Jev-Doku api.md und confidence.md, heruntergeladen am 23.09.2026
(docs.typesafe.ai). Die Grenzen 255/2..10 stehen dort; wir pruefen sie schon
beim Bauen der Frage, damit ein Fehler nicht erst als HTTP 422 zurueckkommt.

VERTRAUEN (confidence)
Jev liefert fuer Auswahl und Stufenwert ein `confidence` 0..1, "abgeleitet aus
der Verteilung". Die Formel nennt die Doku nur fuer ihre Demo, als
Naeherung: (n * groesste Wahrscheinlichkeit - 1) / (n - 1). Nachgerechnet an
den Doku-Beispielen: Stufen 0/0,95/0,05 -> 0,925, Jev meldet 0,92 (passt);
Auswahl 0,88/0,12/0 -> 0,82, Jev meldet 0,81 (knapp daneben). Jev rechnet also
etwas Aehnliches, aber nicht nachweislich genau das.

Festlegung (nicht von Fabian entschieden):
- Liefert der Anbieter selbst ein Vertrauen (Jev bei Auswahl/Stufenwert),
  nehmen wir SEINE Zahl, `vertrauen_quelle = 'anbieter'`.
- Sonst rechnen wir die Doku-Formel oben, `vertrauen_quelle = 'berechnet'`.
  Das gilt fuer alles, was Claude und der Test-Anbieter liefern.
- Noul: Jev liefert bewusst KEIN Vertrauen ("die eine Zahl beschreibt die
  Verteilung vollstaendig", primitives_noul.md). Wir rechnen trotzdem eins,
  und zwar mit derselben Formel fuer n = 2 Ausgaenge (ja, nein):
  (2 * max(p, 1-p) - 1) / 1 = |2p - 1|. p = 0,5 -> 0 (weiss nicht),
  p = 0 oder 1 -> 1. Warum nicht None: Das Matching (Schritt 8) soll alle
  drei Formen gleich behandeln koennen ("unter Schwelle X nicht handeln"),
  ohne Sonderfall. Weil die Zahl keine neue Information traegt, ist sie als
  'berechnet' markiert - wer Jevs Sicht will, nimmt `wert`.

TOKENS
Anbieter zaehlen je ANFRAGE, nicht je Frage. Stellt man mehrere Fragen in
einer Anfrage (beurteilen_mehrere), traegt jedes Urteil die Zahlen der ganzen
Anfrage - beim Summieren je Anfrage nur ein Urteil zaehlen.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from dataclasses import dataclass, field

# Grenzen aus Jevs api.md (Stand 23.09.2026).
AUSWAHL_MAX_OPTIONEN = 255
STUFEN_MIN = 2
STUFEN_MAX = 10

# Kennungen (Dimension/Frage) landen im Protokoll. Deshalb nur ein enges
# Muster: Kleinbuchstaben, Ziffern, Unterstrich - so kann niemand versehentlich
# einen Freitext (und damit Personendaten) als Kennung durchreichen.
# Festlegung (nicht von Fabian entschieden).
KENNUNG_MUSTER = re.compile(r'^[a-z][a-z0-9_]{0,63}$')


def kennung_pruefen(kennung):
    if not isinstance(kennung, str) or not KENNUNG_MUSTER.match(kennung):
        # Den Wert NICHT in die Meldung: er koennte ja gerade der Freitext sein.
        raise ValueError('Kennung muss eine Konstante sein: Kleinbuchstaben, Ziffern, '
                         'Unterstrich, beginnend mit Buchstabe, hoechstens 64 Zeichen.')
    return kennung


# ---------------------------------------------------------------------------
# Fragen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Noul:
    """Ja/nein. `wenn_ja`/`wenn_nein` sind Jevs optionale criteria.true/.false."""
    anweisung: str | dict | list
    wenn_ja: str | dict | list | None = None
    wenn_nein: str | dict | list | None = None

    form = 'noul'

    def als_dict(self):
        d = {'type': 'noul', 'instructions': self.anweisung}
        kriterien = {}
        if self.wenn_ja is not None:
            kriterien['true'] = self.wenn_ja
        if self.wenn_nein is not None:
            kriterien['false'] = self.wenn_nein
        if kriterien:
            d['criteria'] = kriterien
        return d


@dataclass(frozen=True)
class Auswahl:
    """Eine Option aus einer festen Menge. `optionen`: Option -> Beschreibung
    (oder None, wenn der Name genuegt). Die Reihenfolge zaehlt nur fuer den
    Gleichstand: Bei gleicher Wahrscheinlichkeit gewinnt die zuerst genannte
    (Festlegung - Jev sagt dazu nichts)."""
    anweisung: str | dict | list
    optionen: dict

    form = 'choice'

    def __post_init__(self):
        if not isinstance(self.optionen, dict) or len(self.optionen) < 2:
            raise ValueError('Auswahl braucht mindestens zwei Optionen.')
        if len(self.optionen) > AUSWAHL_MAX_OPTIONEN:
            raise ValueError(f'Auswahl: hoechstens {AUSWAHL_MAX_OPTIONEN} Optionen (Jev).')
        if not all(isinstance(k, str) and k for k in self.optionen):
            raise ValueError('Auswahl: Optionen muessen nicht-leere Zeichenketten sein.')

    def als_dict(self):
        return {'type': 'choice', 'instructions': self.anweisung,
                'criteria': dict(self.optionen)}

    # dict ist nicht hashbar; frozen dataclass will aber __hash__ - wir brauchen
    # keinen, der Schluessel fuer Aufzeichnungen ist frage_schluessel().
    __hash__ = None


@dataclass(frozen=True)
class Stufenwert:
    """Geordnete Stufen, schlecht/wenig zuerst. Ergebnis ist ein Index-Mittel
    0..len(stufen)-1."""
    anweisung: str | dict | list
    stufen: tuple

    form = 'score'

    def __post_init__(self):
        object.__setattr__(self, 'stufen', tuple(self.stufen))
        if not STUFEN_MIN <= len(self.stufen) <= STUFEN_MAX:
            raise ValueError(f'Stufenwert: {STUFEN_MIN} bis {STUFEN_MAX} Stufen (Jev).')

    def als_dict(self):
        return {'type': 'score', 'instructions': self.anweisung,
                'criteria': list(self.stufen)}

    __hash__ = None


FRAGEFORMEN = (Noul, Auswahl, Stufenwert)


def frage_schluessel(zustand, frage):
    """Stabiler Schluessel fuer Aufzeichnungen: SHA-256 ueber Zustand und
    Frage in kanonischem JSON. Die Kennung gehoert NICHT dazu - wie bei Jev,
    wo die Frage-ID nicht ins Modell geht: Dieselbe Frage zum selben Zustand
    ist dieselbe Frage, egal unter welchem Namen sie laeuft."""
    roh = json.dumps({'zustand': zustand, 'frage': frage.als_dict()},
                     sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(roh.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Urteile (Rueckgabe)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Urteil:
    """Gemeinsamer Teil aller Urteile.

    anbieter            'jev' | 'claude' | 'test'
    modell              wie der Anbieter es MELDET (Jev z. B. 'jev-1.13.0',
                        nicht das angefragte 'jev-latest')
    vertrauen           0..1, siehe Modulkopf
    vertrauen_quelle    'anbieter' oder 'berechnet'
    wahrscheinlichkeiten  Option/Stufenindex (als str) -> Wahrscheinlichkeit;
                        bei Noul {'ja': p, 'nein': 1-p}
    tokens_ein/aus      der ganzen Anfrage (siehe Modulkopf)
    """
    wert: float | str
    vertrauen: float
    vertrauen_quelle: str
    wahrscheinlichkeiten: dict
    anbieter: str
    modell: str
    tokens_ein: int
    tokens_aus: int
    form = ''


@dataclass(frozen=True)
class NoulUrteil(Urteil):
    wert: float
    form = 'noul'


@dataclass(frozen=True)
class AuswahlUrteil(Urteil):
    wert: str
    form = 'choice'


@dataclass(frozen=True)
class StufenUrteil(Urteil):
    wert: float
    legende: dict = field(default_factory=dict)
    form = 'score'


def vertrauen_aus(wahrscheinlichkeiten):
    """Doku-Formel (confidence.md): (n * max - 1) / (n - 1), auf 0..1 begrenzt."""
    werte = list(wahrscheinlichkeiten)
    n = len(werte)
    if n < 2:
        return 1.0
    return max(0.0, min(1.0, (n * max(werte) - 1) / (n - 1)))


def _zahl(wert):
    """Endliche Zahl oder AnbieterFehler - bool zaehlt nicht als Zahl."""
    from .fehler import AnbieterFehler
    if isinstance(wert, bool) or not isinstance(wert, (int, float)) or not math.isfinite(wert):
        raise AnbieterFehler('antwortformat')
    return float(wert)


def _normieren(roh):
    """Wahrscheinlichkeiten auf Summe 1; Negatives wird 0. Selbst berichtete
    Verteilungen (Claude) summieren nicht immer genau auf 1."""
    from .fehler import AnbieterFehler
    werte = {k: max(0.0, _zahl(v)) for k, v in roh.items()}
    summe = sum(werte.values())
    if summe <= 0:
        raise AnbieterFehler('antwortformat')
    return {k: v / summe for k, v in werte.items()}


def urteil_aus_verteilung(frage, verteilung, *, anbieter, modell, tokens_ein=0, tokens_aus=0):
    """Baut aus einer rohen Verteilung ein Urteil - fuer Anbieter, die (anders
    als Jev) kein fertiges Urteil liefern: Claude und der Test-Anbieter.

    verteilung:
      Noul        Zahl p (Wahrscheinlichkeit fuer ja)
      Auswahl     dict Option -> Wahrscheinlichkeit, oder ein Optionsname (= 1)
      Stufenwert  dict Stufenindex (int oder str) -> Wahrscheinlichkeit, oder
                  Liste in Stufenreihenfolge
    Fehlende Optionen/Stufen zaehlen 0; unbekannte sind ein Formatfehler.
    """
    from .fehler import AnbieterFehler
    gemeinsam = dict(anbieter=anbieter, modell=modell,
                     tokens_ein=int(tokens_ein or 0), tokens_aus=int(tokens_aus or 0),
                     vertrauen_quelle='berechnet')
    if isinstance(frage, Noul):
        p = _zahl(verteilung)
        if not 0.0 <= p <= 1.0:
            raise AnbieterFehler('antwortformat')
        return NoulUrteil(wert=p, vertrauen=abs(2 * p - 1),
                          wahrscheinlichkeiten={'ja': p, 'nein': 1 - p}, **gemeinsam)

    if isinstance(frage, Auswahl):
        if isinstance(verteilung, str):
            verteilung = {verteilung: 1.0}
        if not isinstance(verteilung, dict) or set(verteilung) - set(frage.optionen):
            raise AnbieterFehler('antwortformat')
        voll = {o: verteilung.get(o, 0.0) for o in frage.optionen}
        probs = _normieren(voll)
        # max() nimmt bei Gleichstand das erste - also die zuerst genannte Option.
        wahl = max(frage.optionen, key=lambda o: probs[o])
        return AuswahlUrteil(wert=wahl, vertrauen=vertrauen_aus(probs.values()),
                             wahrscheinlichkeiten=probs, **gemeinsam)

    if isinstance(frage, Stufenwert):
        n = len(frage.stufen)
        if isinstance(verteilung, (list, tuple)):
            if len(verteilung) != n:
                raise AnbieterFehler('antwortformat')
            verteilung = {str(i): v for i, v in enumerate(verteilung)}
        if not isinstance(verteilung, dict):
            raise AnbieterFehler('antwortformat')
        verteilung = {str(k): v for k, v in verteilung.items()}
        gueltig = {str(i) for i in range(n)}
        if set(verteilung) - gueltig:
            raise AnbieterFehler('antwortformat')
        probs = _normieren({str(i): verteilung.get(str(i), 0.0) for i in range(n)})
        wert = sum(i * probs[str(i)] for i in range(n))
        return StufenUrteil(wert=wert, vertrauen=vertrauen_aus(probs.values()),
                            wahrscheinlichkeiten=probs,
                            legende={str(i): s for i, s in enumerate(frage.stufen)},
                            **gemeinsam)

    raise TypeError('Unbekannte Frageform.')


def urteil_als_dict(urteil):
    """Fuer Aufzeichnungen: alle Felder plus Form."""
    d = dataclasses.asdict(urteil)
    d['form'] = urteil.form
    return d


def urteil_aus_dict(d, **ersetzen):
    d = {**d, **ersetzen}
    form = d.pop('form')
    klasse = {'noul': NoulUrteil, 'choice': AuswahlUrteil, 'score': StufenUrteil}[form]
    return klasse(**d)
