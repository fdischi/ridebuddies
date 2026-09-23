"""
Terminfindung - Prozentwert je Kandidaten-Termin aus dem Verfuegbarkeitsraster.

Schritt 6 des Plans (Karte TASK-120.06, 23.09.2026). Entscheidung beim
Einlesen: Terminfindung ist CODE, keine KI - Jevs Doku sagt ueber das Modell
ausdruecklich "not a calculator", und hier wird nur gezaehlt und geteilt. Das
Modul liest nur; es schreibt nichts und braucht keine Migration.

Ausgabe je Termin: Prozentwert, wer fehlt, wer mit Vorbehalt kommt, wer noch
nicht geantwortet hat. `terminuebersicht()` sortiert nach Prozent absteigend,
bei Gleichstand nach Datum. Die Textzeile fuer die Kommandozeile baut
`zeile()` (manage.py terminfindung).

ENTSCHIEDEN (Fabian, 23.09.2026, TASK-120.06):
1. Gaeste zaehlen zum Nenner. Nenner einer Crew-Ausfahrt = alle
   Mitgliedschaften der Crew (Organisator, Mitglied, Gast). Die Vogesen-Reise
   03.-06.06.2027 ist damit 87,5 %, nicht 100 % (Markus ist Gast mit Vorbehalt).
2. Gewichtung sicher = 1, mit Vorbehalt = 0,5, nein = 0 (VORBEHALT_GEWICHT).
3. Keine Antwort zaehlt 0 und bleibt im Nenner, steht aber getrennt unter
   "noch keine Antwort", nicht unter "fehlt" - wer nicht geantwortet hat, kann
   man noch fragen; wer nein gesagt hat, nicht.
4. Reisen (Termin mit bis_datum): Es zaehlt der schlechteste Tag im Zeitraum.
   Rangfolge schlecht -> gut: nein, keine Antwort, Vorbehalt, sicher (RANG).
   Ein Tag nein -> fehlt; sonst ein nicht abgedeckter Tag -> keine Antwort;
   sonst ein Tag Vorbehalt -> Vorbehalt; sonst sicher.

FESTLEGUNGEN (Festlegung, nicht von Fabian entschieden - umwerfbar):
- Tagestermin: Verfuegbarkeit mit gleichem Datum UND gleicher Tageszeit. Die
  Antwort mit ausfahrt = DIESER Ausfahrt geht vor; fehlt sie, gilt die
  allgemeine Verfuegbarkeit (ausfahrt leer) desselben Tages und derselben
  Tageszeit. Antworten auf ANDERE Ausfahrten zaehlen nicht - wer fuer die
  Schotterrunde am 17.04. nein sagt, hat damit nicht fuer die Frauenrunde am
  selben Tag abgesagt.
- Reise: je Tag dasselbe Vorrangprinzip mit Verfuegbarkeitszeitraum (einer zu
  dieser Ausfahrt vor einem allgemeinen). Verfuegbarkeitszeitraeume anderer
  Ausfahrten zaehlen nicht. Einzelne Verfuegbarkeit-Eintraege (Tag x
  Tageszeit) zaehlen bei Reisen NICHT - das Modell sieht fuer Reisen
  Zeitraeume vor (Verfuegbarkeitszeitraum-Docstring).
  Spiegelbildlich zaehlt bei einem TAGESTERMIN ein Verfuegbarkeitszeitraum
  nicht, auch wenn er den Tag abdeckt - selbst ein "nein". Tagestermine lesen
  nur Tag x Tageszeit, Reisen nur Zeitraeume; wer das umwirft, wirft beide
  Richtungen zusammen um.
- Ein Termin mit bis_datum gilt als Reise, auch wenn eine Tageszeit gesetzt
  ist (das Modell verbietet die Kombination nicht); die Tageszeit wird dann
  ignoriert.
- Decken mehrere Zeitraeume GLEICHEN Vorrangs denselben Tag ab (erlaubt, das
  Modell verbietet Ueberlappung nicht), gilt der schlechteste von ihnen.
  Festlegung dieses Baus, nicht in der Karte.
- Termin ohne Tageszeit und ohne bis_datum = ganzer Tag: schlechteste der drei
  Tageszeiten, gleiche Rangfolge wie bei Reisen (eine unbeantwortete Tageszeit
  macht also "keine Antwort", auch wenn die anderen sicher sind).
- Ausfahrt ohne Crew: Nenner = alle Teilnahme-Nutzer plus vorgeschlagen_von,
  falls gesetzt und nicht schon enthalten.
- Teilnahme mit zusage "abgesagt" -> fehlt, unabhaengig von der
  Verfuegbarkeit. Die Karte nennt das bei der crewlosen Ausfahrt; hier gilt es
  fuer JEDE Ausfahrt, weil eine Absage an die Ausfahrt jeden Termin betrifft
  (Festlegung dieses Baus). Eine Teilnahme macht aber bei einer Crew-Ausfahrt
  niemanden zum Teil des Nenners - der ist nach Entscheidung 1 die Crew.
- Anteil intern exakt als fractions.Fraction; angezeigt als ganze Prozent,
  kaufmaennisch gerundet (62,5 -> 63, 87,5 -> 88, 83,3 -> 83, 66,7 -> 67).
  NICHT Pythons round(): das rundet zur geraden Zahl (round(62.5) == 62), und
  mit float kaeme 0,625 * 100 ohnehin nicht exakt heraus. Sortiert wird nach
  dem exakten Wert, nicht nach der gerundeten Anzeige.
- Leerer Nenner (niemand beteiligt): anteil und prozent sind None, keine
  Division durch null; solche Termine sortieren ans Ende.
- Gleichstand im Wert: nach Datum, dann Tageszeit (ganztaegig/Reise vor
  vormittags < mittags < nachmittags), dann bis_datum, dann pk - damit die
  Reihenfolge bei jedem Aufruf dieselbe ist.

ABFRAGEN: Je Ausfahrt ein fester Satz (Termine, Beteiligte, Teilnahmen,
Verfuegbarkeiten, Zeitraeume), unabhaengig von der Zahl der Personen und Tage -
nicht je Person je Tag eine Query. Gerechnet wird danach in Python.

NICHT HIER (Karte, Umfang): keine Oberflaeche (Schritt 13), keine Filterung
nach Ausschluss (Schritt 13), keine allgemeine Verfuegbarkeit als
Matching-Filter (Lesart 6 aus Schritt 5 bleibt offen), keine KI.
"""
import datetime
import math
from dataclasses import dataclass, field
from fractions import Fraction

from django.db.models import Q

from .models import (
    Mitgliedschaft,
    Tageszeit,
    Teilnahme,
    Termin,
    Verfuegbarkeit,
    VerfuegbarkeitsStufe,
    Verfuegbarkeitszeitraum,
)

# Ein Vorbehalt zaehlt halb (Fabian, 23.09.2026, TASK-120.06). Begruendung:
# "Mit Vorbehalt" heisst "kommt wahrscheinlich, aber nicht sicher" - zwischen
# sicher (1) und nein (0) liegt die Mitte. Wer die Gewichtung aendern will,
# aendert NUR diese Zahl; die Tests (kern/tests/test_terminfindung.py) rechnen
# die Erwartungswerte mit 0,5 und zeigen dann, welche Termine sich verschieben.
VORBEHALT_GEWICHT = Fraction(1, 2)

SICHER = VerfuegbarkeitsStufe.SICHER.value
VORBEHALT = VerfuegbarkeitsStufe.VORBEHALT.value
NEIN = VerfuegbarkeitsStufe.NEIN.value
# Kein eigener Wert im Modell - "keine Antwort" ist das Fehlen eines Eintrags.
KEINE_ANTWORT = 'keine_antwort'

GEWICHT = {SICHER: Fraction(1), VORBEHALT: VORBEHALT_GEWICHT, NEIN: Fraction(0),
           KEINE_ANTWORT: Fraction(0)}

# Rangfolge schlecht -> gut (Entscheidung 4). min() ueber RANG ist "der
# schlechteste" - fuer Reisetage und fuer die drei Tageszeiten eines ganzen Tages.
RANG = {NEIN: 0, KEINE_ANTWORT: 1, VORBEHALT: 2, SICHER: 3}

# Gleichstand-Reihenfolge der Tageszeit; '' = ganzer Tag bzw. Reise.
TAGESZEIT_FOLGE = {'': 0, Tageszeit.VORMITTAGS.value: 1, Tageszeit.MITTAGS.value: 2,
                   Tageszeit.NACHMITTAGS.value: 3}

# Deutsche Kuerzel fest im Code statt strftime('%a'): das haengt an der Locale
# des Prozesses, und der Dienst auf dem Server laeuft mit C/POSIX.
WOCHENTAGE = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')


def _schlechteste(stufen):
    return min(stufen, key=RANG.__getitem__)


def prozent_runden(anteil):
    """Ganze Prozent, kaufmaennisch (x,5 -> auf). None bleibt None.

    Nur fuer 0 <= anteil <= 1 gedacht; floor(x + 1/2) rundet dort halbe Werte
    immer auf, anders als round() (Banker's rounding: round(62.5) == 62).
    """
    if anteil is None:
        return None
    return math.floor(Fraction(anteil) * 100 + Fraction(1, 2))


@dataclass
class Auswertung:
    """Ergebnis fuer einen Termin. Personenlisten nach username sortiert."""
    termin: Termin
    nenner: int
    anteil: Fraction | None          # exakt; None bei leerem Nenner
    prozent: int | None              # Anzeige, kaufmaennisch gerundet
    sicher: list = field(default_factory=list)
    vorbehalt: list = field(default_factory=list)
    fehlt: list = field(default_factory=list)
    keine_antwort: list = field(default_factory=list)


class _Raster:
    """Alles, was fuer die Termine EINER Ausfahrt gebraucht wird, einmal geladen."""

    def __init__(self, ausfahrt, termine):
        self.ausfahrt = ausfahrt
        self.beteiligte, self.abgesagt = self._beteiligte(ausfahrt)
        ids = [n.pk for n in self.beteiligte]

        tagestermine = [t for t in termine if not t.bis_datum]
        reisen = [t for t in termine if t.bis_datum]
        bezug = Q(ausfahrt=ausfahrt) | Q(ausfahrt__isnull=True)

        # (nutzer_id, datum, tageszeit) -> {True: Stufe mit Ausfahrtbezug,
        #                                   False: allgemeine Stufe}
        self.tage = {}
        if tagestermine and ids:
            daten = {t.datum for t in tagestermine}
            for nutzer_id, datum, tageszeit, ausfahrt_id, stufe in (
                    Verfuegbarkeit.objects.filter(bezug, nutzer_id__in=ids, datum__in=daten)
                    .values_list('nutzer_id', 'datum', 'tageszeit', 'ausfahrt_id', 'stufe')):
                self.tage.setdefault((nutzer_id, datum, tageszeit), {})[
                    ausfahrt_id is not None] = stufe

        # nutzer_id -> [(von, bis, mit_ausfahrtbezug, stufe), ...]
        self.zeitraeume = {}
        if reisen and ids:
            anfang = min(t.datum for t in reisen)
            ende = max(t.bis_datum for t in reisen)
            for nutzer_id, von, bis, ausfahrt_id, stufe in (
                    Verfuegbarkeitszeitraum.objects
                    .filter(bezug, nutzer_id__in=ids, von__lte=ende, bis__gte=anfang)
                    .values_list('nutzer_id', 'von', 'bis', 'ausfahrt_id', 'stufe')):
                self.zeitraeume.setdefault(nutzer_id, []).append(
                    (von, bis, ausfahrt_id is not None, stufe))

    @staticmethod
    def _beteiligte(ausfahrt):
        """(Nenner als Nutzerliste, Menge der nutzer_ids mit abgesagter Teilnahme)."""
        teilnahmen = list(Teilnahme.objects.filter(ausfahrt=ausfahrt).select_related('nutzer'))
        abgesagt = {t.nutzer_id for t in teilnahmen if t.zusage == Teilnahme.Zusage.ABGESAGT}
        if ausfahrt.crew_id is not None:
            # Entscheidung 1: jede Rolle, auch Gast.
            leute = [m.nutzer for m in Mitgliedschaft.objects.filter(crew_id=ausfahrt.crew_id)
                     .select_related('nutzer')]
        else:
            leute = [t.nutzer for t in teilnahmen]
            if ausfahrt.vorgeschlagen_von_id is not None and \
                    ausfahrt.vorgeschlagen_von_id not in {n.pk for n in leute}:
                leute.append(ausfahrt.vorgeschlagen_von)
        return sorted(leute, key=lambda n: n.username), abgesagt

    def _tagesstufe(self, nutzer_id, datum, tageszeit):
        antworten = self.tage.get((nutzer_id, datum, tageszeit), {})
        if True in antworten:       # Antwort auf diese Ausfahrt geht vor
            return antworten[True]
        return antworten.get(False, KEINE_ANTWORT)

    def _reisetagstufe(self, nutzer_id, tag):
        abgedeckt = [(bezug, stufe) for von, bis, bezug, stufe in self.zeitraeume.get(nutzer_id, [])
                     if von <= tag <= bis]
        for mit_bezug in (True, False):
            stufen = [stufe for bezug, stufe in abgedeckt if bezug is mit_bezug]
            if stufen:
                return _schlechteste(stufen)
        return KEINE_ANTWORT

    def stufe(self, nutzer_id, termin):
        if nutzer_id in self.abgesagt:
            return NEIN
        if termin.bis_datum:
            tage = (termin.bis_datum - termin.datum).days + 1
            return _schlechteste(
                self._reisetagstufe(nutzer_id, termin.datum + datetime.timedelta(days=i))
                for i in range(tage))
        if termin.tageszeit:
            return self._tagesstufe(nutzer_id, termin.datum, termin.tageszeit)
        return _schlechteste(self._tagesstufe(nutzer_id, termin.datum, tz)
                             for tz in Tageszeit.values)

    def auswerten(self, termin):
        listen = {SICHER: [], VORBEHALT: [], NEIN: [], KEINE_ANTWORT: []}
        punkte = Fraction(0)
        for nutzer in self.beteiligte:
            stufe = self.stufe(nutzer.pk, termin)
            listen[stufe].append(nutzer)
            punkte += GEWICHT[stufe]
        nenner = len(self.beteiligte)
        anteil = punkte / nenner if nenner else None
        return Auswertung(termin=termin, nenner=nenner, anteil=anteil,
                          prozent=prozent_runden(anteil), sicher=listen[SICHER],
                          vorbehalt=listen[VORBEHALT], fehlt=listen[NEIN],
                          keine_antwort=listen[KEINE_ANTWORT])


def termin_auswertung(termin):
    """Auswertung eines einzelnen Termins."""
    return _Raster(termin.ausfahrt, [termin]).auswerten(termin)


def sortierschluessel(auswertung):
    t = auswertung.termin
    return (auswertung.anteil is None, -(auswertung.anteil or 0), t.datum,
            TAGESZEIT_FOLGE.get(t.tageszeit, 9), t.bis_datum or t.datum, t.pk)


def terminuebersicht(ausfahrt):
    """Alle Termine einer Ausfahrt, ausgewertet und sortiert (siehe Modulkopf)."""
    termine = list(Termin.objects.filter(ausfahrt=ausfahrt))
    if not termine:
        return []
    raster = _Raster(ausfahrt, termine)
    return sorted((raster.auswerten(t) for t in termine), key=sortierschluessel)


# ---------------------------------------------------------------------------
# Textform fuer die Kommandozeile
# ---------------------------------------------------------------------------

def _tag(datum):
    return f'{WOCHENTAGE[datum.weekday()]} {datum:%d.%m.%Y}'


def termin_text(termin):
    """'Sa 17.04.2027 vormittags', 'So 02.05.2027 ganztags',
    'Do 03.06.2027–So 06.06.2027'."""
    if termin.bis_datum:
        return f'{_tag(termin.datum)}–{_tag(termin.bis_datum)}'
    return f'{_tag(termin.datum)} {termin.tageszeit or "ganztags"}'


def _namen(nutzer):
    return ', '.join(n.username for n in nutzer) or '–'


def zeile(auswertung):
    """Eine Zeile je Termin, Stil der Karte TASK-120.06."""
    prozent = '–' if auswertung.prozent is None else auswertung.prozent
    return (f'{termin_text(auswertung.termin)} – {prozent} % – '
            f'fehlt: {_namen(auswertung.fehlt)} – '
            f'Vorbehalt: {_namen(auswertung.vorbehalt)} – '
            f'keine Antwort: {_namen(auswertung.keine_antwort)}')
