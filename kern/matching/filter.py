"""
Harte Filter des Matchings - Karte TASK-120.13 (Schritt 8, 24.09.2026).

Massgeblich sind die Lesarten im Pruefblatt (docs/pruefblatt-matching.md,
Abschnitt "Lesarten", von Fabian am 23.09.2026 bestaetigt). Hier stehen sie als
Code, jede Regel mit ihrer Nummer:

  1. BEIDE SEITEN ZAEHLEN. Jede Regel wird fuer (a, b) und (b, a) geprueft,
     jeweils mit der hart/weich-Wahl DESSEN, dem die Regel gehoert. Wer ein
     Merkmal auf weich stellt, lockert nur seinen eigenen Filter, nie den des
     anderen.
  2. RADIUS: Entfernung <= eigener Radius, fuer jede Seite mit Region "hart".
     Genau auf der Grenze = drin. Luftlinie (kern/geo.py), UNGERUNDET verglichen
     - gerundet wird nur fuer die Begruendung (ranking.py). Fehlen einer Seite
     die Koordinaten, reisst das den Filter jeder Seite mit Region "hart".
  3. GESCHLECHT "gleich": der andere muss dasselbe Geschlecht angegeben haben;
     "keine Angabe" ist nie "gleich".
  4. "gemischt" filtert beim Einzelvorschlag nichts (wirkt wie "egal").
  5. ALTERSWUNSCH: Altersbereich des anderen zwischen von und bis (inklusive).
     Leerer Wunsch = kein Filter; fehlt dem anderen der Altersbereich, reisst er
     einen gesetzten Wunsch. Nur "von" oder nur "bis" = offen zur anderen Seite
     (Festlegung, im Pruefblatt nicht behandelt - kein Dummy hat das).
  6. VERFUEGBARKEIT: ohne Wirkung, solange nicht entschieden ist, wie sie mit
     Angaben filtern soll.
  7. NO-GO: steht NICHT hier, sondern in nogo.py - es ist Freitext und braucht
     ein KI-Urteil. Siehe dort.
  8. AUSSCHLUSS in irgendeiner Richtung und AKTIVE VERBINDUNG schliessen immer
     aus.
  9. Crew-Mitgliedschaft ist kein Filter.

ZUSAETZLICH (Festlegungen, nicht von Fabian entschieden):
- Geschlechtspraeferenz und Alterswunsch auf "weich" gestellt heisst: OHNE
  WIRKUNG. Fabian, 24.09.2026: "Geschlecht/Alter nur als Nutzerwunsch-Filter,
  nie als weiche Bewertung durch die Plattform." Ein weich gestellter Wunsch
  kann also nicht als Punktzahl weiterleben.
- WIEDERVORLAGE: Ein Vorschlag mit Reaktion "nicht jetzt" oder eine mit "nicht
  jetzt" beendete Verbindung sperrt das Paar bis `wiedervorlage_ab`, in beide
  Richtungen (wie Lesart 1). Die Modelle sagen seit Schritt 4 "das Matching
  liest diese Sperre" (kern/models.py, Verbindung und Vorschlag). Die Ausnahme
  "ausser bei wesentlicher Profilaenderung" ist NICHT gebaut - was
  "wesentlich" ist, ist nicht entschieden. Der Dummy-Bestand hat keinen
  solchen Fall; das Pruefblatt beruehrt es nicht.
- Die Grundmenge (wer ueberhaupt Kandidat sein kann) steht in ranking.py:
  aktives Konto mit aktiver KI-Einwilligung.
"""
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from kern.models import (
    Altersbereich,
    Ausgang,
    Ausschluss,
    Dimension,
    Geschlecht,
    Geschlechtspraeferenz,
    Gewichtung,
    Verbindung,
    Vorschlag,
)

ALTER = list(Altersbereich.values)

# Gruende, die dieses Modul vergibt. Die Dimensionsschluessel sind dieselben wie
# in Vorschlag.begruendung und Ausschluss.grund_dimension.
REGION = Dimension.REGION.value
GESCHLECHT = Dimension.GESCHLECHTSPRAEFERENZ.value
ALTER_GRUND = Dimension.ALTERSWUNSCH.value
AUSSCHLUSS = 'ausschluss'
VERBINDUNG = 'verbindung'
WIEDERVORLAGE = 'wiedervorlage'


def hart(profil, dimension):
    return profil.gewichtung_von(dimension) == Gewichtung.HART.value


def geschlecht_passt(wer, anderer):
    """Lesart 3/4: nur "gleich" filtert, und "keine Angabe" ist nie gleich."""
    if wer.geschlechtspraeferenz != Geschlechtspraeferenz.GLEICH:
        return True
    return (anderer.geschlecht != Geschlecht.KEINE_ANGABE
            and anderer.geschlecht == wer.geschlecht)


def alterswunsch_passt(wer, anderer):
    """Lesart 5."""
    if not wer.alterswunsch_von and not wer.alterswunsch_bis:
        return True
    if not anderer.altersbereich:
        return False
    von = ALTER.index(wer.alterswunsch_von) if wer.alterswunsch_von else 0
    bis = ALTER.index(wer.alterswunsch_bis) if wer.alterswunsch_bis else len(ALTER) - 1
    return von <= ALTER.index(anderer.altersbereich) <= bis


def radius_passt(wer, entfernung_km):
    """Lesart 2 fuer EINE Seite: ungerundet, Gleichstand zaehlt als drin."""
    return entfernung_km is not None and entfernung_km <= wer.radius_km


@dataclass(frozen=True)
class Beziehungen:
    """Was der Anker mit anderen schon zu tun hat - einmal je Anker geladen,
    statt je Kandidat drei Abfragen."""
    ausgeschlossen: frozenset
    verbunden: frozenset
    wiedervorlage: frozenset

    @classmethod
    def fuer(cls, nutzer, heute=None):
        heute = heute or timezone.localdate()
        pk = nutzer.pk
        ausgeschlossen = set()
        for u, b in Ausschluss.objects.filter(Q(urheber=nutzer) | Q(betroffener=nutzer)) \
                .values_list('urheber_id', 'betroffener_id'):
            ausgeschlossen.add(b if u == pk else u)
        verbunden, wiedervorlage = set(), set()
        for v in Verbindung.objects.filter(Q(nutzer_a=nutzer) | Q(nutzer_b=nutzer)):
            anderer = v.nutzer_b_id if v.nutzer_a_id == pk else v.nutzer_a_id
            if v.beendet_am is None:
                verbunden.add(anderer)
            elif (v.beendet_ausgang == Ausgang.NICHT_JETZT and v.wiedervorlage_ab
                  and v.wiedervorlage_ab > heute):
                wiedervorlage.add(anderer)
        for e, k in Vorschlag.objects.filter(
                Q(empfaenger=nutzer) | Q(kandidat=nutzer),
                reaktion=Vorschlag.Reaktion.NICHT_JETZT, wiedervorlage_ab__gt=heute) \
                .values_list('empfaenger_id', 'kandidat_id'):
            wiedervorlage.add(k if e == pk else e)
        return cls(frozenset(ausgeschlossen), frozenset(verbunden), frozenset(wiedervorlage))


def harte_gruende(a, b, entfernung_km, beziehungen):
    """Menge der Gruende, aus denen b dem a (und a dem b) nicht vorgeschlagen
    werden darf - ohne No-Go (nogo.py) und ohne die auf hart gestellten weichen
    Merkmale (dimensionen.py). `beziehungen` gehoert zu a.nutzer."""
    gruende = set()
    for wer in (a, b):
        if hart(wer, REGION) and not radius_passt(wer, entfernung_km):
            gruende.add(REGION)
    for wer, anderer in ((a, b), (b, a)):
        if hart(wer, GESCHLECHT) and not geschlecht_passt(wer, anderer):
            gruende.add(GESCHLECHT)
        if hart(wer, ALTER_GRUND) and not alterswunsch_passt(wer, anderer):
            gruende.add(ALTER_GRUND)
    # Lesart 6: Verfuegbarkeit ohne Wirkung - bewusst keine Zeile.
    kandidat = b.nutzer_id
    if kandidat in beziehungen.ausgeschlossen:
        gruende.add(AUSSCHLUSS)
    if kandidat in beziehungen.verbunden:
        gruende.add(VERBINDUNG)
    if kandidat in beziehungen.wiedervorlage:
        gruende.add(WIEDERVORLAGE)
    return gruende
