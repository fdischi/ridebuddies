"""
KI-Dimension No-Go-Konflikt - Karte TASK-120.13 (Schritt 8, 24.09.2026).

WARUM KI: Das No-Go ist Freitext ("Was ich definitiv nicht moechte"). Ob ein
Profil es reisst, steht in keinem Feld - "Heizen auf der Landstrasse" gegen
"sportlich, Landstrasse, Streckenfresser" ist ein Urteil, kein Vergleich.
Fabian, 24.09.2026: KI-Einzelurteile nur, wo Freitext im Spiel ist; No-Go
Freitext gegen das Profil des anderen, BEIDSEITIG.

JE RICHTUNG EIN URTEIL: "Reisst B das No-Go von A?" und "Reisst A das No-Go
von B?" sind zwei Anfragen mit zwei gespeicherten Urteilen (PaarUrteil).
Gefragt wird nur eine Richtung, deren Urheber ein No-Go hat. `betrifft` sind
immer BEIDE: Im Zustand stehen Daten beider Personen.

WIRKUNG - HART (Lesart 7, Fabian: "das Matching soll niemanden vorschlagen,
der ein No-Go reisst"): Liegt ein Urteil einer Richtung bei oder ueber der
Schwelle des Anbieters (SCHWELLEN), faellt der Kandidat raus. Das KI-Urteil
schliesst nur ueber das No-Go des Nutzers selbst aus und legt NIE einen
Ausschluss-Datensatz an (Fabian, 24.09.2026) - es ist ein Filter beim Rechnen,
kein Zustand zwischen zwei Menschen. Aendert jemand sein No-Go, wird neu
geurteilt, und der Kandidat kann wieder auftauchen.

FEHLT EIN URTEIL (nie geholt, Datensperre, Anbieterfehler, oder veraltet, weil
sich No-Go, Profil oder Frage geaendert haben): Der Kandidat faellt raus, Grund
'nogo_offen'. ENTSCHIEDEN (Fabian, 25.09.2026, nach der Gegenpruefung):
"Rausfallen, bis nachgeholt." Ein ungeprueftes No-Go ist wie ein moeglicherweise
gerissenes - lieber ein Vorschlag weniger als einer, den Lesart 7 verbietet.
FOLGE, bewusst in Kauf genommen: Faellt der Anbieter aus, bekommt jeder, der
selbst ein No-Go hat, und jeder, dessen Gegenueber eins hat, fuer diese Paare
keine Vorschlaege, bis `manage.py matching_urteile` nachgeholt hat. Paare, in
denen keiner ein No-Go hat, bleiben unberuehrt. Ist der Regel-Baustein fuer den
Anbieter abgeschaltet (REGEL_SCHWELLEN None), fehlt dort nichts - er wird
weder geholt noch als offen gewertet. Ebenso zaehlt ein NEUTRALES Urteil des Test-Anbieters
(Modell 'neutral': er weiss nichts und sagt 0,5) nicht als Urteil und wird nicht
gespeichert - sonst sagte die Voreinstellung RIDEBUDDIES_KI_ANBIETER=test im
Betrieb stillschweigend "kein Konflikt".

WAS IN DEN ZUSTAND GEHT (Festlegungen, nicht von Fabian entschieden):
- KEINE NAMEN: "A" und "B", wie in ki_vergleich.
- Von A: das No-Go und As eigene Profilmerkmale. As Merkmale geben dem No-Go
  seinen Sinn ("ich schlafe gern im Zelt" steht neben As Uebernachtung).
- Von B: die Profilmerkmale, OHNE Geschlecht, Altersbereich, Region,
  Koordinaten, Radius und Bs eigenes No-Go. Geschlecht und Alter nicht, weil
  Fabian sie nur als Nutzerwunsch-Filter zulaesst, nie als Bewertung durch die
  Plattform - ein Modell, das sie sieht, koennte sie ins Urteil ziehen. Wer
  "keine Maenner" will, hat dafuer die Geschlechtspraeferenz.
- KEINE BEITRAEGE. Fabian hat erlaubt, dass das Matching Beitraege aller Stufen
  liest; in Schritt 8 tun wir es trotzdem nicht: (1) Beitraege sind Schritt 9
  mit eigenem Nachweis ("ein Beitrag verschiebt nachweislich ein Ranking") -
  lesen sie schon hier mit, ist dieser Nachweis nicht mehr zu fuehren; (2) das
  Pruefblatt ist so gebaut, dass Schritt 8 ohne Beitraege besteht (Pauls
  Beitrag, Kevins "nach Schild"); (3) jeder neue Beitrag aenderte den
  Zustands-Hash und loeste neue Anfragen aus. Fuer Schritt 9 gilt dann: Die
  Zahl darf Beitraege aller Stufen lesen, die BEGRUENDUNG nie - ein
  ausgeschlossener Kandidat taucht ohnehin nicht auf, und ein gezeigter bekommt
  nur den Satz "kein Konflikt mit einem No-Go" (ranking.py).
- Werte als deutsche Beschriftungen, nicht als Schluessel ('Landstraße/Kurven'
  statt 'landstrasse'); leere Felder fallen weg.

DIE FRAGE ist allgemein formuliert, nicht auf die Pruefungsfaelle zugeschnitten
(kein Wort von Hotel, Zelt, Landstrasse oder Alkohol). Alle Fassungen stehen in
FASSUNGEN, auch die verworfenen - mit ihrem Ergebnis im README (Abschnitt
"Matching") und im Befund zu TASK-120.13. Die gueltige ist FASSUNG. Weil die
Frage im Hash steckt, macht eine neue Fassung alle gespeicherten Urteile
veraltet; sie werden beim naechsten `matching_urteile` neu geholt.
"""
import time

from django.core.exceptions import ImproperlyConfigured

from kern import urteile
from kern.urteile.formen import frage_schluessel
from kern.models import (
    AlkoholAufTour,
    Dimension,
    Fahrart,
    Gruppengroesse,
    PaarUrteil,
    Schutzkleidung,
    Selbsteinschaetzung,
    Tempo,
    Thema,
    Tourenformat,
    Uebernachtung,
    UnterwegsStil,
)

KENNUNG = 'nogo_konflikt'
DIMENSION = Dimension.NOGO.value

# Merkmal -> (Beschriftung im Zustand, Auswahlliste oder None fuer Zahl/Text).
MERKMALE = {
    'fahrarten': ('Fahrarten', Fahrart),
    'tempo': ('Tempo', Tempo),
    'selbsteinschaetzung': ('Selbsteinschätzung', Selbsteinschaetzung),
    'erfahrung_jahre': ('Erfahrung (Jahre)', None),
    'km_pro_jahr': ('km pro Jahr', None),
    'tourenformate': ('Tourenformate', Tourenformat),
    'tagesdistanz_km': ('Tagesdistanz (km)', None),
    'unterwegs_stil': ('Unterwegs', UnterwegsStil),
    'uebernachtung': ('Übernachtung', Uebernachtung),
    'gruppengroesse': ('Gruppengröße', Gruppengroesse),
    'themen': ('Themen', Thema),
    'schutzkleidung': ('Schutzkleidung', Schutzkleidung),
    'alkohol_auf_tour': ('Alkohol auf Tour', AlkoholAufTour),
    'motorrad': ('Motorrad', None),
}


def merkmale(profil):
    """Profilmerkmale als {Beschriftung: Wert(e)} - ohne Personendaten im
    engeren Sinn (siehe Modulkopf), leere Felder weggelassen."""
    daten = {}
    for feld, (name, auswahl) in MERKMALE.items():
        wert = getattr(profil, feld)
        if wert in (None, '', []):
            continue
        if auswahl is not None:
            namen = dict(auswahl.choices)
            wert = [str(namen.get(w, w)) for w in wert] if isinstance(wert, list) \
                else str(namen.get(wert, wert))
        daten[name] = wert
    return daten


# ---------------------------------------------------------------------------
# Fassungen der Frage
# ---------------------------------------------------------------------------

def _zustand_nur_b(a, b):
    return {'a': {'no_go': a.nogo.strip()}, 'b': merkmale(b)}


def _zustand_mit_a(a, b):
    return {'a': {'no_go': a.nogo.strip(), 'merkmale': merkmale(a)},
            'b': {'merkmale': merkmale(b)}}


_SINNGEMAESS = (
    'Lies das No-Go sinngemäß, nicht nur wörtlich: Es gilt auch für Abwandlungen '
    'desselben Verhaltens und für das, was aus Bs Angaben auf einer gemeinsamen Tour '
    'üblicherweise folgt. Ein Konflikt liegt vor, wenn B das Ausgeschlossene selbst '
    'angibt, bevorzugt oder erkennbar in Kauf nimmt – auch wenn B es nicht mit denselben '
    'Worten sagt. Kein Konflikt liegt vor, wenn Bs Angaben das No-Go nicht berühren, ihm '
    'entgegenstehen oder zum Thema nichts sagen.')

FASSUNGEN = {
    # f0 - die Frage aus ki_vergleich (TASK-120.12/120.11), als Vergleichsbasis.
    # Ergebnis 24.09.2026 (TASK-120.11): Uwe gegen Heinz Jev 0,48, Claude 0,15.
    'f0': (_zustand_nur_b, urteile.Noul(
        'Würde eine gemeinsame Tour mit Person B gegen das verstoßen, was Person A '
        'ausdrücklich nicht möchte (`a.no_go`)?',
        wenn_ja='Bs Angaben widersprechen As No-Go direkt oder sehr wahrscheinlich.',
        wenn_nein='Bs Angaben berühren As No-Go nicht oder vereinbaren sich damit.')),
    # f1 - wie f0, aber mit der Anweisung, das No-Go sinngemaess zu lesen.
    'f1': (_zustand_nur_b, urteile.Noul(
        'A und B überlegen, gemeinsam Motorrad zu fahren. Unter `a.no_go` steht, was A '
        'auf keinen Fall möchte. Würde A auf einer gemeinsamen Tour mit B, so wie B laut '
        'seinen Angaben unterwegs ist, genau das erleben? ' + _SINNGEMAESS,
        wenn_ja='Bs Angaben machen es wahrscheinlich, dass A auf einer gemeinsamen Tour '
                'erlebt, was A ausschließt.',
        wenn_nein='Bs Angaben berühren das No-Go nicht, stehen ihm entgegen oder sagen '
                  'dazu nichts.')),
    # f2 - wie f1, dazu As eigene Merkmale im Zustand.
    'f2': (_zustand_mit_a, urteile.Noul(
        'A und B überlegen, gemeinsam Motorrad zu fahren. Unter `a.no_go` steht, was A '
        'auf keinen Fall möchte; `a.merkmale` und `b.merkmale` sagen, wie beide unterwegs '
        'sind. Würde A auf einer gemeinsamen Tour mit B, so wie B laut seinen Angaben '
        'unterwegs ist, genau das erleben, was A ausschließt? ' + _SINNGEMAESS,
        wenn_ja='Bs Angaben machen es wahrscheinlich, dass A auf einer gemeinsamen Tour '
                'erlebt, was A ausschließt.',
        wenn_nein='Bs Angaben berühren das No-Go nicht, stehen ihm entgegen oder sagen '
                  'dazu nichts.')),
}

_VORSTELLUNG = (
    'A und B überlegen, gemeinsam Motorrad zu fahren. Unter `a.no_go` steht, was A auf '
    'keinen Fall möchte; `a.merkmale` und `b.merkmale` sagen, wie beide unterwegs sind. '
    'Stell dir eine gemeinsame Tour vor, auf der B so fährt, übernachtet und sich verhält, '
    'wie B es angibt – bei allem, was B angibt. ')
_LESART = (
    'Lies das No-Go sinngemäß: Es gilt auch für Abwandlungen desselben Verhaltens und für '
    'jede Zeit und jeden Ort, die das No-Go selbst nennt. Ein Verhalten kann sich aus '
    'mehreren Angaben von B zusammen ergeben, auch wenn keine einzelne es wörtlich nennt. '
    'Sagt B zum Thema des No-Gos nichts, ist das kein Hinweis auf einen Konflikt.')

FASSUNGEN['f3'] = (_zustand_mit_a, urteile.Stufenwert(
    _VORSTELLUNG + 'Wie sehr verstößt B damit gegen das, was A ausschließt? ' + _LESART,
    ['Bs Angaben sprechen ausdrücklich gegen einen Verstoß',
     'Bs Angaben berühren das No-Go nicht oder sagen dazu nichts',
     'ein Verstoß ist möglich, aber nicht naheliegend',
     'ein Verstoß ist naheliegend',
     'Bs Angaben verstoßen ausdrücklich gegen das No-Go']))

FASSUNGEN['f4'] = (_zustand_mit_a, urteile.Noul(
    _VORSTELLUNG + 'Erlebt A dabei wahrscheinlich, was A ausschließt? ' + _LESART,
    wenn_ja='Bs Angaben machen es naheliegend oder sicher, dass A auf der gemeinsamen Tour '
            'erlebt, was A ausschließt.',
    wenn_nein='Bs Angaben berühren das No-Go nicht, stehen ihm entgegen oder machen einen '
              'Verstoß höchstens denkbar.'))


_AUSSERHALB = (' Schließt das No-Go etwas auch für die Zeit außerhalb des Fahrens aus, zählt '
               'auch, was B für diese Zeit angibt.')

FASSUNGEN['f5'] = (_zustand_mit_a, urteile.Stufenwert(
    _VORSTELLUNG + 'Wie sehr verstößt B damit gegen das, was A ausschließt? ' + _LESART
    + _AUSSERHALB, FASSUNGEN['f3'][1].stufen))


# f6 (25.09.2026, Fabian: "eine neue Paarfassung, sonst hinnehmen" - genau EIN
# Versuch nach f3): das No-Go WOERTLICH UND ENG lesen. Anlass: Mit f3 fielen
# Paare heraus, bei denen B nur "aehnlich unterwegs" ist (sportlich, zuegig,
# Streckenfresser), ohne dass Bs Angaben den im No-Go beschriebenen Umstand
# belegen - README, "Ausschluesse ueber das Paarurteil".
# VERWORFEN (Entwicklungssatz Jev, 32 Paare, 25.09.2026). Vorher festgelegte
# Regel: f6 ersetzt f3 nur, wenn mit Jev (a) das Pruefblatt voll erfuellt
# bleibt, (b) die nicht gedeckten Paarurteil-Ausschluesse weniger werden und
# (c) die Luecke hoechstes Muss-Paar .. niedrigerer Freitext-Nie-Fall nicht
# kleiner wird als bei f3 (0,058). Ergebnis: Muss max 0,335 (Uwe->Gabi),
# Marco->Sabine 0,328, Uwe->Heinz 0,690 - die Luecke ist NEGATIV (-0,007),
# keine Schwelle haelt zugleich alle Muss-Paare drin und Sabine draussen; (a)
# und (c) verfehlt. (b) waere erreicht worden (Svens fuenf 0,278..0,438 statt
# 0,383..0,690). Kein Volllauf, keine weitere Fassung (Fabian: genau ein Versuch).
_ENG = (
    'Lies das No-Go wörtlich und eng: Ein Verstoß liegt nur vor, wenn Bs Angaben genau das '
    'beschriebene Verhalten oder die beschriebene Situation erwarten lassen – mit den '
    'Umständen, die das No-Go selbst nennt (etwa wo, wann oder in welcher Form). Dass B in '
    'allgemeinen Eigenschaften ähnlich unterwegs ist, etwa beim Tempo oder beim Stil, '
    'genügt nicht, solange Bs Angaben den genannten Umstand nicht belegen. Sagt B zum Thema '
    'des No-Gos nichts, ist das kein Hinweis auf einen Konflikt.')

FASSUNGEN['f6'] = (_zustand_mit_a, urteile.Stufenwert(
    _VORSTELLUNG + 'Wie sehr verstößt B damit gegen das, was A ausschließt? ' + _ENG,
    FASSUNGEN['f3'][1].stufen))


def konfliktwert(u):
    """Urteil -> 0..1 (1 = sicherer Konflikt). Noul: der Wert. Stufenwert:
    Stufenmittel geteilt durch die hoechste Stufe."""
    if isinstance(u, urteile.StufenUrteil):
        return u.wert / (len(u.wahrscheinlichkeiten) - 1)
    return u.wert


FASSUNG = 'f3'   # f6 verworfen, siehe dort


def zustand(a, b, fassung=None):
    """Zustand fuer "reisst b das No-Go von a?" (a, b: Profile)."""
    return FASSUNGEN[fassung or FASSUNG][0](a, b)


def frage(fassung=None):
    return FASSUNGEN[fassung or FASSUNG][1]


def schluessel(a, b, fassung=None):
    return frage_schluessel(zustand(a, b, fassung), frage(fassung))


# ---------------------------------------------------------------------------
# Schwelle
# ---------------------------------------------------------------------------

# Ab diesem Wert (Noul: Wahrscheinlichkeit fuer "ja, Konflikt") faellt ein
# Kandidat raus. JE ANBIETER GETRENNT, weil die Zahlen nicht dasselbe bedeuten:
# Jevs Noul ist eine Modellwahrscheinlichkeit, Claudes eine selbst berichtete
# Zahl (claude.py, Modulkopf). Gewaehlt am Befund vom 24./25.09.2026 - siehe
# README, "Matching". Fuer den Test-Anbieter gilt die Schwelle des Anbieters,
# aus dessen Aufzeichnung er antwortet (Modell "aufzeichnung:<anbieter>/...").
#
# jev 0,37: Im Volllauf (143 Paare, Fassung f3) lag das hoechste Muss-Paar bei
#   0,340 (Sven->Mehmet, Sven->Lea), die beiden Freitext-Nie-Faelle bei 0,398
#   (Marco->Sabine) und 0,820 (Uwe->Heinz). 0,37 liegt mitten in der Luecke
#   0,340..0,398 - die Luecke ist SCHMAL (0,058); eine neue Fassung oder ein
#   neues Jev-Modell muss sie neu vermessen.
# claude 0,73: Mit f3 trennt Claude Haiku nicht - Uwe->Joerg (Muss) und
#   Uwe->Heinz (Nie) liegen beide bei 0,725, Marco->Kevin (Muss) und
#   Marco->Sabine (Nie) beide bei 0,650. 0,73 haelt alle Muss-Paare drin und
#   laesst dafuer beide Freitext-Faelle durch. Bewusst so herum: Ein falscher
#   Ausschluss waere unsichtbar, ein falscher Vorschlag faellt auf.
# test 0,5: NUR fuer den Test-Anbieter mit festen Vorgaben (kern/tests) - er
#   liefert 0 oder 1, die Schwelle muss nur dazwischen liegen. Antwortet er
#   aus einer Aufzeichnung, gilt die Schwelle des aufgezeichneten Anbieters.
# Einen Ersatzwert fuer unbekannte Anbieter gibt es NICHT (Auflage der
# Gegenpruefung, 25.09.2026): Eine nie vermessene Schwelle waere geraten. Wer
# einen Anbieter hinzufuegt (etwa Mistral, Schritt 14a), vermisst ihn zuerst.
SCHWELLEN = {'jev': 0.37, 'claude': 0.73, 'test': 0.5}


class SchwelleFehlt(ImproperlyConfigured):
    """Fuer diesen Anbieter ist keine Schwelle vermessen."""


def _herkunft(anbieter, modell):
    """Test-Anbieter aus einer Aufzeichnung -> der aufgezeichnete Anbieter."""
    if anbieter == 'test' and modell.startswith('aufzeichnung:'):
        return modell.split(':', 1)[1].split('/', 1)[0]
    return anbieter


def schwelle_fuer(anbieter, modell=''):
    herkunft = _herkunft(anbieter, modell)
    if herkunft not in SCHWELLEN:
        raise SchwelleFehlt(f'Keine vermessene No-Go-Schwelle für Anbieter „{herkunft}“ '
                            '(kern/matching/nogo.py, SCHWELLEN).')
    return SCHWELLEN[herkunft]


def ist_konflikt(urteil_satz):
    """urteil_satz: PaarUrteil."""
    return urteil_satz.wert >= schwelle_fuer(urteil_satz.anbieter, urteil_satz.modell)


# ---------------------------------------------------------------------------
# Gespeicherte Urteile lesen und holen
# ---------------------------------------------------------------------------

def gespeichert(a, b):
    """Das gueltige gespeicherte Urteil fuer "reisst b das No-Go von a?" oder
    None (fehlt oder veraltet)."""
    satz = PaarUrteil.objects.filter(urheber_id=a.nutzer_id, gegenueber_id=b.nutzer_id,
                                     dimension=DIMENSION).first()
    if satz is None or satz.schluessel != schluessel(a, b):
        return None
    return satz


class Statistik:
    def __init__(self):
        self.vorhanden = 0
        self.geholt = 0
        self.gesperrt = 0
        self.fehler = 0
        self.neutral = 0
        self.tokens_ein = 0
        self.tokens_aus = 0
        self.dauer_ms = 0

    def __str__(self):
        return (f'{self.geholt} geholt, {self.vorhanden} schon aktuell, '
                f'{self.gesperrt} gesperrt, {self.fehler} Fehler, {self.neutral} neutral '
                f'verworfen; Tokens {self.tokens_ein}/{self.tokens_aus}, '
                f'{self.dauer_ms} ms')


def holen(a, b, *, neu=False, statistik=None):
    """Holt das Urteil "reisst b das No-Go von a?" beim eingestellten Anbieter
    und speichert es. Gibt das PaarUrteil zurueck oder None. Wirft nichts aus
    kern.urteile - Datensperre und Anbieterfehler werden gezaehlt, der Kandidat
    bleibt dann 'nogo_offen'."""
    statistik = statistik if statistik is not None else Statistik()
    if not neu:
        satz = gespeichert(a, b)
        if satz is not None:
            statistik.vorhanden += 1
            return satz
    z, f = zustand(a, b), frage()
    beginn = time.monotonic()
    try:
        u = urteile.beurteilen(z, f, kennung=KENNUNG, betrifft=[a.nutzer, b.nutzer])
    except urteile.DatensperreVerletzt:
        statistik.gesperrt += 1
        return None
    except urteile.UrteilFehler:
        statistik.fehler += 1
        return None
    dauer = int((time.monotonic() - beginn) * 1000)
    if u.anbieter == 'test' and u.modell == 'neutral':
        statistik.neutral += 1
        return None
    statistik.geholt += 1
    statistik.tokens_ein += u.tokens_ein
    statistik.tokens_aus += u.tokens_aus
    statistik.dauer_ms += dauer
    satz, _ = PaarUrteil.objects.update_or_create(
        urheber_id=a.nutzer_id, gegenueber_id=b.nutzer_id, dimension=DIMENSION,
        defaults={'schluessel': frage_schluessel(z, f), 'anbieter': u.anbieter,
                  'modell': u.modell[:80], 'wert': konfliktwert(u), 'vertrauen': u.vertrauen,
                  'tokens_ein': u.tokens_ein, 'tokens_aus': u.tokens_aus,
                  'dauer_ms': dauer})
    return satz


# ---------------------------------------------------------------------------
# Zweiter Baustein: Regeln je Person (25.09.2026)
# ---------------------------------------------------------------------------
# WARUM (Befund der Iteration, README "Matching"): Das Paarurteil sieht das
# ganze Profil von B und verliert darin eine einzelne entscheidende Angabe.
# Ninas "keinen Tropfen, auch nicht abends in der Unterkunft" gegen Svens
# "Alkohol auf Tour: erst nach der Fahrt" erkannte in keiner Fassung ein
# Anbieter verlaesslich (Jev 0,26-0,34, Claude 0,05-0,64), die knappe Frage
# nach genau dieser einen Angabe dagegen schon. Fabian, 24.09.2026, zaehlt
# "strukturiertes No-Go wie Alkohol auf Tour" ausdruecklich zu dem, was der
# CODE rechnet. Ein strukturiertes No-Go-Feld gibt es im Modell nicht; die
# Struktur kommt deshalb EINMAL JE PERSON aus dem Freitext ("was sich nur aus
# Text ergibt"): Fuer jede Auspraegung jedes Merkmals in REGEL_MERKMALE
# (seit r2 nur Verhaltensmerkmale, siehe dort) fragt ein Noul, ob ein
# Gegenueber mit genau dieser Angabe schon fuer sich gegen das No-Go verstoesst.
# Den Abgleich mit jedem Gegenueber macht danach der Code.
#
# Allgemein, nicht auf die Pruefungsfaelle zugeschnitten: Die Fragen entstehen
# aus den Auswahllisten des Modells, fuer alle Merkmale in REGEL_MERKMALE und
# alle Personen gleich. Eine Anfrage je Person (beurteilen_mehrere), nicht je
# Paar - bei 10 No-Go-Inhabern im Dummy-Bestand 10 Anfragen je Anbieter.
#
# NUR EINFACHWAHL (Festlegung, nicht von Fabian entschieden): Bei Mehrfachwahl
# (Fahrarten, Uebernachtung ...) ist offen, ob EIN verbotener Wert reicht oder
# ALLE verboten sein muessen - "Pension, Hotel" gegen ein No-Go, das nur Hotel
# meint, waere mit "einer reicht" ein Konflikt, mit "alle" keiner. Solche Faelle
# bleiben beim Paarurteil oben, das die Angaben im Zusammenhang sieht.
# Erfahrung in Jahren, km und Tagesdistanz sind Zahlen, keine Auswahl.
#
# Wirkung: Beide Bausteine sind HART und wirken zusammen (ODER). Reisst B eine
# Regel von A oder liegt das Paarurteil ueber der Schwelle, faellt B raus.

# NUR VERHALTENSMERKMALE (Fassung r2, 25.09.2026 - Fabian: Regel-Baustein
# "behalten, schaerfer" nach der Gegenpruefung). r1 fragte auch die
# STILMERKMALE Tempo, Unterwegs, Selbsteinschaetzung und Gruppengroesse ab und
# ist verworfen. Grund, allgemein: Ein No-Go gegen einen Fahrstil meint fast
# immer eine KOMBINATION - "Heizen auf der Landstrasse" (Tempo UND Ort),
# "Autobahnetappen, nur um Strecke zu machen" (Stil UND Strassenart). Als
# Einzelregel wird daraus ein Pauschalurteil ueber alle Sportlichen bzw. alle
# Streckenfresser; mit r1 ergab Jev fuer Sven "Streckenfresser" 0,45 und fuer
# Marco "sportlich" 0,30 - beides nah an der Schwelle 0,36, und fuer Sven
# darueber. Den Zusammenhang sieht nur das Paarurteil. Alkohol auf Tour und
# Schutzkleidung dagegen beschreiben eine HANDLUNG, die ein No-Go direkt
# verbieten kann ("keinen Tropfen", "ohne Protektoren") - dort ist die
# einzelne Angabe der Verstoss. Neue Merkmale kommen nur dazu, wenn sie diese
# Art sind.
REGEL_MERKMALE = {
    'schutzkleidung': Schutzkleidung,
    'alkohol_auf_tour': AlkoholAufTour,
}

# Verworfen, nur zur Nachvollziehbarkeit (Ergebnis im README und im Befund):
REGEL_MERKMALE_R1 = ('tempo', 'unterwegs_stil', 'selbsteinschaetzung', 'gruppengroesse',
                     'schutzkleidung', 'alkohol_auf_tour')

REGEL_FASSUNG = 'r2'


def regel_zustand(a):
    return {'no_go': a.nogo.strip(), 'merkmale': merkmale(a)}


def _regel_frage(merkmal, auspraegung):
    name = MERKMALE[merkmal][0]
    wert = str(dict(REGEL_MERKMALE[merkmal].choices)[auspraegung])
    return urteile.Noul(
        f'Unter `no_go` steht, was eine Person A auf einer gemeinsamen Motorradtour auf '
        f'keinen Fall möchte; `merkmale` sind As eigene Angaben. Ein Gegenüber gibt im '
        f'Profil bei „{name}“ die Angabe „{wert}“ an. Verstößt schon diese eine Angabe '
        f'für sich genommen gegen As No-Go – unabhängig von allem anderen, was das '
        f'Gegenüber angibt? Lies das No-Go sinngemäß und genau: Es zählt, was es '
        f'ausschließt, auch zu den Zeiten und an den Orten, die es selbst nennt – nicht '
        f'mehr und nicht weniger.',
        wenn_ja=f'Wer „{wert}“ angibt, tut oder erlaubt auf einer gemeinsamen Tour, was '
                f'A ausschließt.',
        wenn_nein=f'Die Angabe „{wert}“ hat mit dem No-Go nichts zu tun, verträgt sich '
                  f'damit oder verstößt erst zusammen mit weiteren Angaben dagegen.')


def regel_fragen():
    """Kennung '<merkmal>__<auspraegung>' -> Noul, in fester Reihenfolge."""
    return {f'{m}__{w}': _regel_frage(m, w)
            for m, auswahl in REGEL_MERKMALE.items() for w in auswahl.values}


def regeln_gespeichert(a):
    """{(merkmal, auspraegung): MerkmalUrteil} oder None, wenn auch nur eine
    Regel fehlt oder veraltet ist."""
    from kern.models import MerkmalUrteil
    z = regel_zustand(a)
    saetze = {(s.merkmal, s.auspraegung): s for s in MerkmalUrteil.objects.filter(
        nutzer_id=a.nutzer_id, dimension=DIMENSION)}
    ergebnis = {}
    for kennung, f in regel_fragen().items():
        m, w = kennung.split('__', 1)
        s = saetze.get((m, w))
        if s is None or s.schluessel != frage_schluessel(z, f):
            return None
        ergebnis[(m, w)] = s
    return ergebnis


def regeln_holen(a, *, neu=False, statistik=None):
    """Holt fehlende oder veraltete Regeln von a in EINER Anfrage und speichert
    sie. Gibt wie regeln_gespeichert() zurueck (None bei Sperre/Fehler)."""
    from kern.models import MerkmalUrteil
    statistik = statistik if statistik is not None else Statistik()
    if not neu:
        vorhanden = regeln_gespeichert(a)
        if vorhanden is not None:
            statistik.vorhanden += 1
            return vorhanden
    z, fragen = regel_zustand(a), regel_fragen()
    beginn = time.monotonic()
    try:
        antworten = urteile.beurteilen_mehrere(z, fragen, betrifft=[a.nutzer])
    except urteile.DatensperreVerletzt:
        statistik.gesperrt += 1
        return None
    except urteile.UrteilFehler:
        statistik.fehler += 1
        return None
    dauer = int((time.monotonic() - beginn) * 1000)
    if any(u.anbieter == 'test' and u.modell == 'neutral' for u in antworten.values()):
        statistik.neutral += 1
        return None
    erstes = next(iter(antworten.values()))
    statistik.geholt += 1
    statistik.tokens_ein += erstes.tokens_ein    # je Anfrage, nicht je Frage (formen.py)
    statistik.tokens_aus += erstes.tokens_aus
    statistik.dauer_ms += dauer
    for kennung, u in antworten.items():
        m, w = kennung.split('__', 1)
        MerkmalUrteil.objects.update_or_create(
            nutzer_id=a.nutzer_id, dimension=DIMENSION, merkmal=m, auspraegung=w,
            defaults={'schluessel': frage_schluessel(z, fragen[kennung]),
                      'anbieter': u.anbieter, 'modell': u.modell[:80], 'wert': u.wert,
                      'vertrauen': u.vertrauen, 'tokens_ein': u.tokens_ein,
                      'tokens_aus': u.tokens_aus})
    return regeln_gespeichert(a)


# Schwelle der Regeln, je Anbieter - eigene Zahl neben SCHWELLEN (andere Frage,
# andere Verteilung). None = Baustein fuer diesen Anbieter ABGESCHALTET: Seine
# Regeln werden weder geholt noch gewertet, und ihr Fehlen macht niemanden
# 'nogo_offen' (Auflage der Gegenpruefung, 25.09.2026). Kein Ersatzwert fuer
# unbekannte Anbieter (SchwelleFehlt), wie bei SCHWELLEN.
#
# jev 0,31 (Fassung r2, Live-Lauf 25.09.2026): Treffer, die gelten sollen,
#   0,41 (Nina, "erst nach der Fahrt"), 0,70 (Nina, "egal"), 0,53 (Petra,
#   "egal"); hoechster, der nicht gelten soll, 0,21 (Luca, "egal" gegen
#   "Wheelies und Rasen"); alle anderen unter 0,2. 0,31 in der Mitte der
#   Luecke 0,21..0,41.
#   Verworfen - r1 mit 0,36: dort lagen Marco "sportlich" 0,30 und
#   "Streckenfresser" 0,29 knapp darunter und Sven "Streckenfresser" 0,45
#   darueber (siehe REGEL_MERKMALE).
# claude None: Auch mit r2 (6 Fragen je Anfrage, 25.09.2026) unbrauchbar -
#   Gabi, deren No-Go das Rauchen betrifft, bekam Alkohol "nie" 1,0, "nach
#   der Fahrt" 1,0 und "egal" 0,85; Ninas "erst nach der Fahrt" lag unter 0,2. Mit r1
#   (19 Fragen) waren Ninas Werte sogar verkehrt herum (nie 1,0, egal 0,0),
#   einzeln gefragt nie 0,0 / nach der Fahrt 0,0 / egal 0,95.
REGEL_SCHWELLEN = {'jev': 0.31, 'claude': None, 'test': 0.5}


def regel_schwelle_fuer(anbieter, modell=''):
    """Schwelle oder None (Baustein fuer diesen Anbieter abgeschaltet)."""
    herkunft = _herkunft(anbieter, modell)
    if herkunft not in REGEL_SCHWELLEN:
        raise SchwelleFehlt(f'Keine vermessene Regel-Schwelle für Anbieter „{herkunft}“ '
                            '(kern/matching/nogo.py, REGEL_SCHWELLEN).')
    return REGEL_SCHWELLEN[herkunft]


def regeln_aktiv(anbieter):
    """Ob der Regel-Baustein fuer diesen (live gefragten) Anbieter gilt."""
    return regel_schwelle_fuer(anbieter) is not None


def regeln_fuer(a, *, holen=False, statistik=None):
    """Die Regeln von a fuer das Ranking: {} wenn der Baustein fuer den
    eingestellten Anbieter abgeschaltet ist (dann wird nichts geholt und nichts
    fehlt), sonst wie regeln_gespeichert()/regeln_holen() - None = offen."""
    if not regeln_aktiv(urteile.urteiler().name):
        return {}
    return regeln_holen(a, statistik=statistik) if holen else regeln_gespeichert(a)


def regel_verstoesse(regeln, b):
    """Merkmale von b, die eine Regel reissen (Liste, leer = keiner)."""
    treffer = []
    for merkmal in REGEL_MERKMALE:
        wert = getattr(b, merkmal)
        satz = regeln.get((merkmal, wert)) if wert else None
        if satz is None:
            continue
        schwelle = regel_schwelle_fuer(satz.anbieter, satz.modell)
        if schwelle is not None and satz.wert >= schwelle:
            treffer.append(merkmal)
    return treffer
