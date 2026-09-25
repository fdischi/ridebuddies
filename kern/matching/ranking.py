"""
Ranking je Anker - Karte TASK-120.13 (Schritt 8, 24.09.2026).

    from kern import matching
    for v in matching.vorschlaege(anker, anzahl=5):
        v.kandidat, v.punkte, v.begruendung

ABLAUF je Kandidat (bewerten()):
  1. Grundmenge: aktives Konto, Profil, aktive KI-Einwilligung (siehe unten).
  2. Harte Filter nach den Lesarten (filter.py), beidseitig.
  3. Weiche Merkmale, die EINE der beiden Seiten auf "hart" gestellt hat,
     als Filter (dimensionen.py, "Was hart heisst").
  4. No-Go-Konflikt aus gespeicherten KI-Urteilen, beide Richtungen (nogo.py).
  5. Punktzahl aus den weichen Dimensionen des ANKERS (seine hart/weich-Wahl,
     GEWICHTE), Begruendung je Dimension.

RECHTLICHE LEITPLANKEN (Fabian, 24.09.2026) und wie sie hier gelten:
- KEIN GLOBALER SCORE, KEINE RANGLISTE UEBER ALLE. Jede Funktion nimmt einen
  Anker; die Punktzahl ist die Passung ZU DIESEM Anker und wird nirgends
  gespeichert. Es gibt keine Funktion, die Nutzer ohne Anker ordnet.
- Ein KI-Urteil schliesst nur ueber das No-Go eines der beiden aus und legt nie
  einen Ausschluss an (nogo.py).
- ENTFERNUNG in der Begruendung auf 5 km gerundet, unter 5 km nur "unter 5 km"
  (RUNDUNG_KM). Koordinaten nie. Festlegung (nicht von Fabian entschieden):
  5 statt 1 km, weil ein Anker mehrere Runden Vorschlaege sieht und genaue
  Entfernungen von mehreren Punkten aus einen Wohnort wieder eingrenzen
  (Hinweis im Docstring von sichtbarkeit.eigene_koordinaten).
- GESCHLECHT UND ALTER nur als Filter des Nutzerwunschs (filter.py), nie als
  Punktzahl und nie in der Begruendung.

GRUNDMENGE (Fabian, 24.09.2026: "Wer keine KI-Einwilligung gibt, darf sich
spaeter gar nicht anmelden; das System basiert auf der KI-Auswertung."): Ohne
aktive Einwilligung KI_AUSWERTUNG ist niemand Kandidat, und ein Anker ohne sie
bekommt KeineEinwilligung. Dieselbe Regel wie in kern/urteile/sperre.py
(erteilt_am nicht in der Zukunft, nicht widerrufen); die Sperre selbst bleibt
dort unveraendert und prueft zusaetzlich "Dummy oder freigegebenes Konto".

SORTIERUNG: Punktzahl absteigend, bei Gleichstand Entfernung aufsteigend,
dann Nutzername - deterministisch.

GEWICHTE: siehe GEWICHTE unten; `gewichte=` ueberschreibt sie fuer einen
Aufruf (Tests, Experimente). Weder Gewichte noch hart/weich loesen einen
Anbieteraufruf aus: Das Ranking liest nur gespeicherte Urteile, ausser man
verlangt `holen=True`.
"""
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.utils import timezone

from kern.geo import profil_entfernung_km
from kern.models import Dimension, Einwilligung, Profil

from . import filter as harte
from . import nogo
from .dimensionen import DIMENSIONEN, NEUTRAL

# Gewicht je weicher Dimension. Festlegung (nicht von Fabian entschieden),
# Leitlinie: Was bestimmt, ob man ueberhaupt auf derselben Strasse faehrt
# (Fahrart), wiegt am meisten; wie man faehrt und unterwegs ist (Tempo,
# Unterwegs) danach; worueber man sich trifft (Tourenformat, Themen) danach;
# Erfahrung und Sicherheit am wenigsten, weil sie in Grenzen verhandelbar sind.
# Motorrad 0: nur informativ (dimensionen.py). Region zaehlt nur, wenn der
# Anker sie auf weich stellt - dann wird aus dem Radius-Filter eine Punktzahl.
# Nachjustieren soll spaeter die Rueckkopplung Sorte 1 (Notiz, Schritt 13b).
GEWICHTE = {
    Dimension.FAHRART.value: 3.0,
    Dimension.TEMPO.value: 2.0,
    Dimension.UNTERWEGS.value: 2.0,
    Dimension.TOURENFORMAT.value: 1.5,
    Dimension.THEMEN.value: 1.5,
    Dimension.ERFAHRUNG.value: 1.0,
    Dimension.SICHERHEIT.value: 1.0,
    Dimension.MOTORRAD.value: 0.0,
    Dimension.REGION.value: 2.0,
}

RUNDUNG_KM = 5

# Gruende, die nicht aus filter.py kommen.
NOGO = Dimension.NOGO.value
NOGO_OFFEN = 'nogo_offen'
KEINE_EINWILLIGUNG = 'keine_einwilligung'

NOGO_TEXT = 'kein Konflikt mit einem No-Go'


class KeineEinwilligung(ValueError):
    """Der Anker hat keine aktive KI-Einwilligung - ohne sie kein Matching."""


@dataclass(frozen=True)
class Bewertung:
    kandidat: object                       # Nutzer
    ausgeschlossen: frozenset              # leer = Vorschlag moeglich
    punkte: float | None = None            # 0..1, nur relativ zu diesem Anker
    teilwerte: dict = field(default_factory=dict)
    begruendung: dict = field(default_factory=dict)
    # UNGERUNDET und NUR INTERN (Sortierung bei Gleichstand, Betreiberkommando).
    # Nie nach aussen geben - fuer Nutzer gilt allein begruendung['region'],
    # auf RUNDUNG_KM gerundet. Der Name sagt es, damit es keiner uebersieht
    # (Auflage der Gegenpruefung, 25.09.2026).
    intern_entfernung_km: float | None = None

    @property
    def zulaessig(self):
        return not self.ausgeschlossen


def entfernung_text(km):
    if km is None:
        return 'Entfernung unbekannt'
    if km < RUNDUNG_KM:
        return f'unter {RUNDUNG_KM} km entfernt'
    return f'etwa {int(round(km / RUNDUNG_KM) * RUNDUNG_KM)} km entfernt'


def mit_einwilligung(qs):
    """Nutzer-Queryset -> nur solche mit aktiver KI-Einwilligung."""
    aktiv = Einwilligung.objects.filter(art=Einwilligung.Art.KI_AUSWERTUNG,
                                        erteilt_am__lte=timezone.now(),
                                        widerrufen_am__isnull=True)
    return qs.filter(pk__in=aktiv.values('nutzer_id'))


def grundmenge():
    """Profile aller, die Kandidat sein koennen."""
    nutzer = mit_einwilligung(get_user_model().objects.filter(is_active=True))
    return Profil.objects.select_related('nutzer').filter(nutzer__in=nutzer) \
        .order_by('nutzer__username')


def _profil(nutzer_oder_profil):
    if isinstance(nutzer_oder_profil, Profil):
        return nutzer_oder_profil
    return Profil.objects.select_related('nutzer').get(nutzer=nutzer_oder_profil)


def code_gruende(a, b, entfernung, beziehungen):
    """Alle Ausschlussgruende, die der Code ohne KI feststellt."""
    gruende = harte.harte_gruende(a, b, entfernung, beziehungen)
    for dim, funktion in DIMENSIONEN.items():
        if harte.hart(a, dim) or harte.hart(b, dim):
            if not funktion(a, b).hart_ok:
                gruende.add(dim)
    return gruende


def nogo_richtungen(a, b):
    """Die Richtungen (urheber, gegenueber), fuer die ein Urteil noetig ist."""
    return [(x, y) for x, y in ((a, b), (b, a)) if x.nogo.strip()]


def bewerten(anker, kandidat, *, gewichte=None, holen=False, beziehungen=None,
             statistik=None):
    """Bewertung eines Kandidaten fuer einen Anker (Nutzer oder Profil)."""
    a, b = _profil(anker), _profil(kandidat)
    if a.nutzer_id == b.nutzer_id:
        raise ValueError('Anker und Kandidat sind dieselbe Person.')
    if not mit_einwilligung(get_user_model().objects.filter(pk=a.nutzer_id)).exists():
        # Wie alle_bewertungen() (Auflage der Gegenpruefung, 25.09.2026): ohne
        # Einwilligung des Ankers kein Matching, auch nicht fuer ein Paar.
        raise KeineEinwilligung('Der Anker hat keine aktive KI-Einwilligung.')
    beziehungen = beziehungen or harte.Beziehungen.fuer(a.nutzer)
    entfernung = profil_entfernung_km(a, b)

    gruende = code_gruende(a, b, entfernung, beziehungen)
    if not mit_einwilligung(get_user_model().objects.filter(pk=b.nutzer_id)).exists():
        gruende.add(KEINE_EINWILLIGUNG)
    if gruende:
        # Kein KI-Urteil fuer ein Paar, das ohnehin nicht in Frage kommt.
        return Bewertung(b.nutzer, frozenset(gruende), intern_entfernung_km=entfernung)

    for x, y in nogo_richtungen(a, b):
        # Baustein 1: Regeln je Person (einmal je x, gespeichert).
        regeln = nogo.regeln_fuer(x, holen=holen, statistik=statistik)
        if regeln is None:
            gruende.add(NOGO_OFFEN)
        elif nogo.regel_verstoesse(regeln, y):
            gruende.add(NOGO)
            continue   # schon draussen - kein Paarurteil mehr noetig
        # Baustein 2: Paarurteil im Zusammenhang.
        satz = nogo.holen(x, y, statistik=statistik) if holen else nogo.gespeichert(x, y)
        if satz is None:
            gruende.add(NOGO_OFFEN)
        elif nogo.ist_konflikt(satz):
            gruende.add(NOGO)
    if gruende:
        return Bewertung(b.nutzer, frozenset(gruende), intern_entfernung_km=entfernung)

    gewichte = {**GEWICHTE, **(gewichte or {})}
    teilwerte, begruendung = {}, {}
    summe = gewicht_summe = 0.0
    begruendung[Dimension.REGION.value] = entfernung_text(entfernung)
    if not harte.hart(a, Dimension.REGION.value):
        # Region weich: innerhalb des eigenen Radius 1, darueber linear bis 0 beim
        # doppelten Radius (Festlegung).
        if entfernung is None:
            wert = NEUTRAL
        else:
            wert = max(0.0, min(1.0, 1 - (entfernung - a.radius_km) / max(a.radius_km, 1)))
        teilwerte[Dimension.REGION.value] = wert
        w = gewichte[Dimension.REGION.value]
        summe += w * wert
        gewicht_summe += w
    for dim, funktion in DIMENSIONEN.items():
        teil = funktion(a, b)
        begruendung[dim] = teil.text
        if harte.hart(a, dim):
            continue   # beim Anker ein Filter, keine Punktzahl
        wert = NEUTRAL if teil.wert is None else teil.wert
        teilwerte[dim] = wert
        w = gewichte.get(dim, 0.0)
        summe += w * wert
        gewicht_summe += w
    begruendung[NOGO] = NOGO_TEXT
    punkte = summe / gewicht_summe if gewicht_summe else 0.0
    return Bewertung(b.nutzer, frozenset(), punkte=punkte, teilwerte=teilwerte,
                     begruendung=begruendung, intern_entfernung_km=entfernung)


def _sortierschluessel(bewertung):
    e = bewertung.intern_entfernung_km
    return (-bewertung.punkte, e if e is not None else float('inf'),
            bewertung.kandidat.username)


def alle_bewertungen(anker, *, gewichte=None, holen=False, statistik=None):
    """Jede Person der Grundmenge (ausser dem Anker) mit Bewertung - zulaessige
    zuerst in Rangfolge, dann die ausgeschlossenen nach Name. Fuer Kommando
    und Tests; Nutzern wird nur vorschlaege() gezeigt."""
    a = _profil(anker)
    if not mit_einwilligung(get_user_model().objects.filter(pk=a.nutzer_id)).exists():
        raise KeineEinwilligung('Der Anker hat keine aktive KI-Einwilligung.')
    beziehungen = harte.Beziehungen.fuer(a.nutzer)
    bewertungen = [bewerten(a, b, gewichte=gewichte, holen=holen, beziehungen=beziehungen,
                            statistik=statistik)
                   for b in grundmenge().exclude(nutzer_id=a.nutzer_id)]
    zulaessig = sorted((x for x in bewertungen if x.zulaessig), key=_sortierschluessel)
    raus = sorted((x for x in bewertungen if not x.zulaessig),
                  key=lambda x: x.kandidat.username)
    return zulaessig + raus


def vorschlaege(anker, anzahl=5, *, gewichte=None, holen=False, statistik=None):
    """Die besten `anzahl` zulaessigen Kandidaten fuer `anker`. Leer, wenn
    niemand zulaessig ist - aufgefuellt wird nie (Pruefblatt: fern-bernd)."""
    return [x for x in alle_bewertungen(anker, gewichte=gewichte, holen=holen,
                                        statistik=statistik)
            if x.zulaessig][:anzahl]


def noetige_nogo_paare(profile=None):
    """Alle gerichteten Paare (urheber, gegenueber) in der Grundmenge (oder in
    `profile`), die ein No-Go-Urteil brauchen: Das ungeordnete Paar besteht alle
    harten Code-Filter (inkl. der auf hart gestellten weichen Merkmale, beide
    Seiten), und der Urheber hat ein No-Go. Genau die Urteile, die das Ranking
    liest - nicht mehr (Kosten), nicht weniger (sonst 'nogo_offen')."""
    profile = list(profile if profile is not None else grundmenge())
    beziehungen = {p.nutzer_id: harte.Beziehungen.fuer(p.nutzer) for p in profile}
    paare = []
    for i, a in enumerate(profile):
        for b in profile[i + 1:]:
            if code_gruende(a, b, profil_entfernung_km(a, b), beziehungen[a.nutzer_id]):
                continue
            paare.extend(nogo_richtungen(a, b))
    return paare


__all__ = ['GEWICHTE', 'Bewertung', 'KeineEinwilligung', 'alle_bewertungen', 'bewerten',
           'entfernung_text', 'grundmenge', 'noetige_nogo_paare', 'vorschlaege']
