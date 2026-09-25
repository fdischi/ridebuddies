"""
Weiche Matching-Dimensionen, im CODE gerechnet - Karte TASK-120.13 (Schritt 8).

ENTSCHIEDEN (Fabian, 24.09.2026): Hybrid. Was strukturiert im Profil steht
(Fahrart, Tempo, Erfahrung, Tourenformat, Unterwegs, Themen, Sicherheit,
Motorrad), rechnet der Code; ein KI-Urteil gibt es nur, wo Freitext im Spiel
ist (nogo.py). Die Jev-Notiz sagt dasselbe von der anderen Seite: "Rechnen im
Code, Urteilen im Modell" (haus/08-Ideen/Jev-Entscheidermodell.md).

Jede Dimension liefert ein Teilurteil:
  wert        0..1 (1 = passt genau) oder None, wenn eine Seite nichts angibt
  hart_ok     ob das Paar die Dimension als HARTEN Filter besteht - gebraucht,
              wenn ein Nutzer das Merkmal auf "hart" stellt
  text        Begruendung aus Sicht des Ankers ("du ...")

WAS "HART" BEI EINEM WEICHEN MERKMAL HEISST (Festlegung, nicht von Fabian
entschieden - die Notiz sagt nur "jeder stellt hart/weich selbst um"):
  Fahrart, Tourenformat, Themen   mindestens ein gemeinsamer Wert
  Tempo                           gleiches Tempo
  Erfahrung                       Selbsteinschaetzung hoechstens eine Stufe auseinander
  Unterwegs                       Stil nicht gegensaetzlich (Streckenfresser gegen
                                  Geniesser); geben beide Uebernachtungen an,
                                  mindestens eine gemeinsame
  Sicherheit                      Schutzkleidung und Alkohol je hoechstens eine
                                  Stufe auseinander
  Motorrad                        filtert nie (siehe unten)
Fehlt einer Seite die Angabe, ist der harte Filter BESTANDEN - dieselbe
Haltung wie Lesart 6 (Verfuegbarkeit): wo nichts steht, filtert nichts.

MOTORRAD ist Freitext ("BMW R 1250 GS"), und die Notiz nennt es "informativ".
Der Code kann Modelle nicht sinnvoll vergleichen (ein Katalog fehlt), und ein
KI-Urteil dafuer waere eine eigene Dimension. Deshalb: Gewicht 0, nur
Begruendungstext. Festlegung.

SICHTBARKEIT DER BEGRUENDUNG (Fabian, 24.09.2026: Begruendungen duerfen nie
etwas an jemanden geben, der es nicht sehen darf): Ein Vorschlag gibt dem Anker
Sicht auf Stufe OEFFENTLICH (kern/sichtbarkeit.py). Ein Wert des Kandidaten
steht deshalb nur dann woertlich in der Begruendung, wenn SEIN Feld auf
oeffentlich steht (Profil.feldstufe). Sonst steht dort nur "passt gut /
teilweise / kaum" - oder, bei Sicherheit (Schutzkleidung und Alkohol sind
voreingestellt "verbunden"), gar kein Urteil: "passt gut" zu "Alkohol" wuerde
den verborgenen Wert fast verraten. Der Wert fliesst trotzdem in die Punktzahl
- das Matching darf lesen, was der Nutzer nicht sieht (Fabian, 24.09.2026).
Die Werte des Ankers selbst darf die Begruendung immer nennen.
"""
from dataclasses import dataclass

from kern.models import (
    AlkoholAufTour,
    Dimension,
    Fahrart,
    Gruppengroesse,
    Schutzkleidung,
    Selbsteinschaetzung,
    Stufe,
    Tempo,
    Thema,
    Tourenformat,
    Uebernachtung,
    UnterwegsStil,
)

# Unbekannt (eine Seite ohne Angabe) zaehlt in der Punktzahl als Mitte.
NEUTRAL = 0.5


@dataclass(frozen=True)
class Teilurteil:
    wert: float | None
    hart_ok: bool
    text: str


def sichtbar(profil, feld):
    """Darf ein Vorschlagsempfaenger (Stufe oeffentlich) dieses Feld sehen?"""
    return profil.feldstufe(feld) <= Stufe.OEFFENTLICH


def _labels(choices, werte):
    namen = dict(choices.choices)
    return ', '.join(str(namen.get(w, w)) for w in werte)


def _label(choices, wert):
    return str(dict(choices.choices).get(wert, wert))


def dice(a, b):
    """Ueberlappung zweier Mengen, 0..1 (Dice-Koeffizient). None, wenn eine leer ist."""
    a, b = set(a or ()), set(b or ())
    if not a or not b:
        return None
    return 2 * len(a & b) / (len(a) + len(b))


def ordinal(werte, x, y):
    """1 - Abstand/(Stufen-1); None, wenn eine Seite fehlt."""
    if not x or not y or x not in werte or y not in werte:
        return None
    return 1 - abs(werte.index(x) - werte.index(y)) / (len(werte) - 1)


def abstand(werte, x, y):
    return abs(werte.index(x) - werte.index(y))


def grob(wert):
    if wert is None:
        return 'keine Angabe'
    if wert >= 0.75:
        return 'passt gut'
    if wert >= 0.4:
        return 'passt teilweise'
    return 'passt kaum'


def _mittel(werte):
    werte = [w for w in werte if w is not None]
    return sum(werte) / len(werte) if werte else None


# ---------------------------------------------------------------------------
# Die Dimensionen. a = Anker, b = Kandidat.
# ---------------------------------------------------------------------------

def fahrart(a, b):
    wert = dice(a.fahrarten, b.fahrarten)
    if wert is None:
        return Teilurteil(None, True, 'keine Angabe')
    gemeinsam = [f for f in Fahrart.values if f in set(a.fahrarten) & set(b.fahrarten)]
    ok = bool(gemeinsam)
    if not sichtbar(b, 'fahrarten'):
        return Teilurteil(wert, ok, grob(wert))
    if set(a.fahrarten) == set(b.fahrarten):
        return Teilurteil(wert, ok, f'beide {_labels(Fahrart, gemeinsam)}')
    if gemeinsam:
        return Teilurteil(wert, ok, f'gemeinsam: {_labels(Fahrart, gemeinsam)}')
    return Teilurteil(wert, ok, f'keine gemeinsame Fahrart (Gegenüber: '
                                f'{_labels(Fahrart, b.fahrarten)})')


def tempo(a, b):
    stufen = list(Tempo.values)
    wert = ordinal(stufen, a.tempo, b.tempo)
    if wert is None:
        return Teilurteil(None, True, 'keine Angabe')
    ok = a.tempo == b.tempo
    if not sichtbar(b, 'tempo'):
        return Teilurteil(wert, ok, grob(wert))
    if ok:
        return Teilurteil(wert, ok, f'beide {_label(Tempo, a.tempo)}')
    return Teilurteil(wert, ok, f'du {_label(Tempo, a.tempo)}, Gegenüber '
                                f'{_label(Tempo, b.tempo)}')


def erfahrung(a, b):
    stufen = list(Selbsteinschaetzung.values)
    wert = ordinal(stufen, a.selbsteinschaetzung, b.selbsteinschaetzung)
    if wert is None:
        return Teilurteil(None, True, 'keine Angabe')
    ok = abstand(stufen, a.selbsteinschaetzung, b.selbsteinschaetzung) <= 1
    if not sichtbar(b, 'selbsteinschaetzung'):
        return Teilurteil(wert, ok, grob(wert))
    if a.selbsteinschaetzung == b.selbsteinschaetzung:
        return Teilurteil(wert, ok, f'beide {_label(Selbsteinschaetzung, a.selbsteinschaetzung)}')
    return Teilurteil(wert, ok, f'du {_label(Selbsteinschaetzung, a.selbsteinschaetzung)}, '
                                f'Gegenüber {_label(Selbsteinschaetzung, b.selbsteinschaetzung)}')


def tourenformat(a, b):
    formate = dice(a.tourenformate, b.tourenformate)
    distanz = None
    if a.tagesdistanz_km and b.tagesdistanz_km:
        distanz = min(a.tagesdistanz_km, b.tagesdistanz_km) / max(a.tagesdistanz_km,
                                                                   b.tagesdistanz_km)
    if formate is None and distanz is None:
        return Teilurteil(None, True, 'keine Angabe')
    # Formate zaehlen mehr als die Tagesdistanz (Festlegung): ob man
    # ueberhaupt mehrtaegig faehrt, trennt staerker als 250 gegen 300 km.
    if formate is not None and distanz is not None:
        wert = 0.7 * formate + 0.3 * distanz
    else:
        wert = formate if formate is not None else distanz
    gemeinsam = [f for f in Tourenformat.values
                 if f in set(a.tourenformate) & set(b.tourenformate)]
    ok = formate is None or bool(gemeinsam)
    if not sichtbar(b, 'tourenformate'):
        return Teilurteil(wert, ok, grob(wert))
    teile = []
    if gemeinsam:
        teile.append(f'gemeinsam: {_labels(Tourenformat, gemeinsam)}')
    elif formate is not None:
        teile.append('kein gemeinsames Format')
    if distanz is not None and sichtbar(b, 'tagesdistanz_km'):
        teile.append(f'Tagesdistanz du {a.tagesdistanz_km} km, Gegenüber {b.tagesdistanz_km} km')
    return Teilurteil(wert, ok, '; '.join(teile) or grob(wert))


def unterwegs(a, b):
    # Stil: gleich 1; einer "mal so, mal so" 0,75; gegensaetzlich 0,25 (Festlegung).
    stil = None
    if a.unterwegs_stil and b.unterwegs_stil:
        if a.unterwegs_stil == b.unterwegs_stil:
            stil = 1.0
        elif UnterwegsStil.BEIDES in (a.unterwegs_stil, b.unterwegs_stil):
            stil = 0.75
        else:
            stil = 0.25
    nacht = dice(a.uebernachtung, b.uebernachtung)
    gruppe = ordinal(list(Gruppengroesse.values), a.gruppengroesse, b.gruppengroesse)
    wert = _mittel([stil, nacht, gruppe])
    if wert is None:
        return Teilurteil(None, True, 'keine Angabe')
    ok = (stil is None or stil > 0.25) and (nacht is None or nacht > 0)
    teile = []
    if stil is not None and sichtbar(b, 'unterwegs_stil'):
        teile.append(f'beide {_label(UnterwegsStil, a.unterwegs_stil)}' if stil == 1.0 else
                     f'du {_label(UnterwegsStil, a.unterwegs_stil)}, Gegenüber '
                     f'{_label(UnterwegsStil, b.unterwegs_stil)}')
    if nacht is not None and sichtbar(b, 'uebernachtung'):
        gemeinsam = [u for u in Uebernachtung.values
                     if u in set(a.uebernachtung) & set(b.uebernachtung)]
        teile.append(f'Übernachtung gemeinsam: {_labels(Uebernachtung, gemeinsam)}'
                     if gemeinsam else 'keine gemeinsame Übernachtungsart')
    if gruppe is not None and sichtbar(b, 'gruppengroesse'):
        teile.append(f'Gruppe beide {_label(Gruppengroesse, a.gruppengroesse)}'
                     if a.gruppengroesse == b.gruppengroesse else
                     f'Gruppe du {_label(Gruppengroesse, a.gruppengroesse)}, Gegenüber '
                     f'{_label(Gruppengroesse, b.gruppengroesse)}')
    return Teilurteil(wert, ok, '; '.join(teile) or grob(wert))


def themen(a, b):
    wert = dice(a.themen, b.themen)
    if wert is None:
        return Teilurteil(None, True, 'keine Angabe')
    gemeinsam = [t for t in Thema.values if t in set(a.themen) & set(b.themen)]
    ok = bool(gemeinsam)
    if not sichtbar(b, 'themen'):
        return Teilurteil(wert, ok, grob(wert))
    if gemeinsam:
        return Teilurteil(wert, ok, f'gemeinsam: {_labels(Thema, gemeinsam)}')
    return Teilurteil(wert, ok, 'kein gemeinsames Thema')


def sicherheit(a, b):
    schutz_stufen = list(Schutzkleidung.values)
    alk_stufen = list(AlkoholAufTour.values)
    schutz = ordinal(schutz_stufen, a.schutzkleidung, b.schutzkleidung)
    alkohol = ordinal(alk_stufen, a.alkohol_auf_tour, b.alkohol_auf_tour)
    wert = _mittel([schutz, alkohol])
    if wert is None:
        return Teilurteil(None, True, 'keine Angabe')
    ok = ((schutz is None or abstand(schutz_stufen, a.schutzkleidung, b.schutzkleidung) <= 1)
          and (alkohol is None
               or abstand(alk_stufen, a.alkohol_auf_tour, b.alkohol_auf_tour) <= 1))
    if sichtbar(b, 'schutzkleidung') and sichtbar(b, 'alkohol_auf_tour'):
        return Teilurteil(wert, ok, grob(wert))
    # Siehe Modulkopf: bei verborgenen Werten kein Urteil im Text.
    return Teilurteil(wert, ok, 'berücksichtigt (Angaben des Gegenübers erst ab „verbunden“ '
                                'sichtbar)')


def motorrad(a, b):
    if b.motorrad and sichtbar(b, 'motorrad'):
        return Teilurteil(None, True, f'informativ: {b.motorrad}')
    return Teilurteil(None, True, 'informativ')


DIMENSIONEN = {
    Dimension.FAHRART.value: fahrart,
    Dimension.TEMPO.value: tempo,
    Dimension.ERFAHRUNG.value: erfahrung,
    Dimension.TOURENFORMAT.value: tourenformat,
    Dimension.UNTERWEGS.value: unterwegs,
    Dimension.THEMEN.value: themen,
    Dimension.SICHERHEIT.value: sicherheit,
    Dimension.MOTORRAD.value: motorrad,
}
