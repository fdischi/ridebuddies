"""
Dummy-Bestand fuer Ridebuddies - Schritt 5 des Plans (Karte TASK-120.05, 23.09.2026).

Plan-Notiz haus/08-Ideen/Ridebuddies.md, Schritt 5: "Skript erzeugt >= 30
Dummy-Profile mit bekannten Eigenschaften (z. B. 5 Enduro-Schotter-Fahrer im
Umkreis Siegburg, 3 Rennstrecken-Fahrer, 4 Frauen mit Praeferenz 'gleich', 2 mit
No-Go 'Alkohol') plus >= 5 Dummy-Ausfahrten und 2 Dummy-Reisen mit
Verfuegbarkeiten. Fertig: Skript idempotent, Admin zeigt die Dummies, ein
Pruefblatt listet, welche Matches erwartet werden."

Aufgerufen wird das ueber `manage.py dummies_anlegen` (kern/management/commands/);
hier steht der Bestand selbst und die Logik, damit die Tests sie ohne
Kommandozeile greifen koennen.

WARUM KEIN ZUFALL: Das Pruefblatt (docs/pruefblatt-matching.*) nennt fuer acht
Anker-Profile, wer unter die ersten fuenf muss und wer nie vorgeschlagen werden
darf. Das geht nur, wenn jeder Lauf dieselben Menschen mit denselben Werten
erzeugt. Alles steht deshalb woertlich unten; wer einen Wert aendert, prueft
danach das Pruefblatt (kern/tests/test_dummies.py rechnet es nach).

ERKENNBAR ALS DUMMY an zwei Merkmalen zugleich: Nutzername beginnt mit
`dummy-` UND E-Mail endet auf `@example.invalid` (RFC 2606: .invalid ist nie
zustellbar). Das Abraeumen verlangt BEIDES - ein echter Nutzer, der sich
"dummy-irgendwas" nennt, bleibt so unberuehrt.
Crews und Ausfahrten tragen zusaetzlich die Marke `[Dummy]` am Anfang der
Beschreibung. Gesucht wird eine Dummy-Crew ueber Name UND Marke: Legt ein echter
Nutzer spaeter eine Crew "Schotterbande Siegburg" an, setzt ein zweiter Lauf
keine Dummies hinein.

IDEMPOTENT heisst hier: Anlegen ueber natuerliche Schluessel (Nutzername,
Crew-Name + Marke, Titel + Crew, Datum + Tageszeit ...); vorhandene Datensaetze
werden nur angefasst, wenn ein Wert vom Soll abweicht, und dann nur die
abweichenden Felder. Ein zweiter Lauf auf unveraendertem Bestand schreibt
nichts - auch Profil.geaendert (auto_now) bleibt stehen, weil dann gar nicht
gespeichert wird. Beziehungen (Verbindung, Ridebuddies, Ausschluss) laufen ueber
kern/ablaeufe.py, damit sie genau so entstehen wie spaeter in der Oberflaeche,
und werden vorher auf Bestand geprueft.

Ausnahme mit Absicht: Beziehungen werden NICHT zurueckgedreht. Hat jemand im
Admin eine Dummy-Verbindung beendet, legt der naechste Lauf eine neue an; einen
Ausschluss, den es schon gibt, laesst er stehen. Das "Soll" gilt fuer die
Existenz, nicht fuer die Geschichte.
"""
import datetime
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q

from . import ablaeufe
from .models import (
    Anfrage,
    Ausfahrt,
    Ausgang,
    Ausschluss,
    Beitrag,
    Crew,
    CrewVorschlag,
    Dimension,
    Einwilligung,
    Mitgliedschaft,
    Profil,
    RidebuddyAnfrage,
    Stufe,
    Teilnahme,
    Termin,
    Verbindung,
    Verfuegbarkeit,
    Verfuegbarkeitszeitraum,
    Vorschlag,
)
from .sichtbarkeit import aktive_verbindung, ausgeschlossen

PRAEFIX = 'dummy-'
DOMAIN = '@example.invalid'
MARKE = '[Dummy]'
EINWILLIGUNG_VERSION = 'dummy-2026-09'

UTC = datetime.timezone.utc


def ist_dummy_q(prefix=''):
    """Q-Filter "ist ein Dummy" - beide Merkmale zugleich (siehe Modulkopf).
    `prefix` fuer Abfragen ueber eine Beziehung, z. B. 'nutzer__'."""
    return Q(**{f'{prefix}username__startswith': PRAEFIX,
                f'{prefix}email__endswith': DOMAIN})


def dummies():
    return get_user_model().objects.filter(ist_dummy_q())


# ---------------------------------------------------------------------------
# Orte - echte Ortsmitten, auf vier Nachkommastellen (~11 m) gerundet.
# ---------------------------------------------------------------------------
# Quelle: allgemein bekannte Koordinaten der Ortsmitten (Rathaus/Markt), aus dem
# Gedaechtnis der Bausitzung, NICHT einzeln gegen eine Karte geprueft. Fuer den
# Zweck genuegt das: Das Pruefblatt rechnet mit genau diesen Zahlen, nicht mit
# der Wirklichkeit, und seine Entfernungen prueft der Test mit kern/geo.py nach.
# Einen Wohnort bildet kein Wert ab.
ORTE = {
    'Siegburg': ('50.8000', '7.2075'),
    'Sankt Augustin': ('50.7700', '7.1867'),
    'Lohmar': ('50.8390', '7.2150'),
    'Hennef (Sieg)': ('50.7753', '7.2838'),
    'Troisdorf': ('50.8161', '7.1556'),
    'Neunkirchen-Seelscheid': ('50.8600', '7.3300'),
    'Königswinter': ('50.6836', '7.1920'),
    'Bonn': ('50.7339', '7.0998'),
    'Bonn-Beuel': ('50.7389', '7.1267'),
    'Bonn-Bad Godesberg': ('50.6844', '7.1558'),
    'Köln': ('50.9375', '6.9603'),
    'Köln-Porz': ('50.8819', '7.0569'),
    'Bergisch Gladbach': ('50.9856', '7.1325'),
    'Leverkusen': ('51.0303', '6.9843'),
    'Brühl': ('50.8290', '6.9047'),
    'Düsseldorf': ('51.2277', '6.7735'),
    'Nürburg (Eifel)': ('50.3433', '6.9525'),
    'Adenau (Eifel)': ('50.3833', '6.9333'),
    'Mayen (Eifel)': ('50.3276', '7.2250'),
    'Bad Münstereifel (Eifel)': ('50.5569', '6.7631'),
    'Winterberg (Sauerland)': ('51.1941', '8.5328'),
    'Meschede (Sauerland)': ('51.3503', '8.2836'),
    'Hachenburg (Westerwald)': ('50.6600', '7.8200'),
    'Altenkirchen (Westerwald)': ('50.6872', '7.6456'),
    'Montabaur (Westerwald)': ('50.4375', '7.8258'),
    'Bad Marienberg (Westerwald)': ('50.6497', '7.9500'),
    'Siegen': ('50.8756', '8.0167'),
    'München': ('48.1372', '11.5755'),
    'Hamburg': ('53.5503', '10.0007'),
}


# ---------------------------------------------------------------------------
# Die Dummies
# ---------------------------------------------------------------------------
# Kurzschreibweise, damit die Tabelle lesbar bleibt. Reihenfolge der
# Positionsargumente:
#   ort, geschlecht, altersbereich, radius_km, geschlechtspraeferenz,
#   (alterswunsch_von, alterswunsch_bis), fahrarten, tempo, erfahrung_jahre,
#   km_pro_jahr, selbsteinschaetzung, tourenformate, tagesdistanz_km,
#   unterwegs_stil, uebernachtung, gruppengroesse, themen, schutzkleidung,
#   alkohol_auf_tour, motorrad, nogo
# Werte sind die Schluessel aus kern/models.py (Auswahllisten).

def _profil(ort, geschlecht, altersbereich, radius_km, praeferenz, alterswunsch, fahrarten,
            tempo, erfahrung_jahre, km_pro_jahr, selbsteinschaetzung, tourenformate,
            tagesdistanz_km, unterwegs_stil, uebernachtung, gruppengroesse, themen,
            schutzkleidung, alkohol_auf_tour, motorrad, nogo, feldstufen=None):
    breite, laenge = ORTE[ort]
    von, bis = alterswunsch
    return {
        'region': ort,
        'breitengrad': Decimal(breite),
        'laengengrad': Decimal(laenge),
        'geschlecht': geschlecht,
        'altersbereich': altersbereich,
        'radius_km': radius_km,
        'geschlechtspraeferenz': praeferenz,
        'alterswunsch_von': von,
        'alterswunsch_bis': bis,
        'fahrarten': fahrarten,
        'tempo': tempo,
        'erfahrung_jahre': erfahrung_jahre,
        'km_pro_jahr': km_pro_jahr,
        'selbsteinschaetzung': selbsteinschaetzung,
        'tourenformate': tourenformate,
        'tagesdistanz_km': tagesdistanz_km,
        'unterwegs_stil': unterwegs_stil,
        'uebernachtung': uebernachtung,
        'gruppengroesse': gruppengroesse,
        'themen': themen,
        'schutzkleidung': schutzkleidung,
        'alkohol_auf_tour': alkohol_auf_tour,
        'motorrad': motorrad,
        'nogo': nogo,
        'feldstufen': feldstufen or {},
        # hart/weich bleibt bei allen auf der Voreinstellung - das Pruefblatt
        # rechnet mit MERKMAL_VOREINSTELLUNG (siehe dort, "Lesarten").
        'gewichtung': {},
    }


W, M, KA = 'weiblich', 'maennlich', 'keine_angabe'
OHNE = ('', '')

# Gruppen im Namen (schotter/ring/frauen/koeln/...) sind nur Lesehilfe; der
# Test zaehlt die Pflichtgruppen an den Werten, nicht am Namen.
PROFILE = {
    # --- Enduro/Schotter im Umkreis Siegburg (Pflicht: >= 5) --------------
    'dummy-schotter-sven': _profil(
        'Siegburg', M, '35-44', 40, 'egal', OHNE, ['enduro', 'landstrasse'], 'zuegig', 15,
        12000, 'erfahren', ['halbtag', 'tag'], 250, 'geniesser', ['zelt', 'pension'], 'klein',
        ['tagestouren', 'schrauben', 'trainings'], 'voll', 'nach_der_fahrt',
        'KTM 690 Enduro R', 'Autobahnetappen, nur um Strecke zu machen.'),
    'dummy-schotter-jonas': _profil(
        'Sankt Augustin', M, '25-34', 50, 'egal', OHNE, ['enduro'], 'zuegig', 8, 9000,
        'geuebt', ['halbtag', 'tag'], 200, 'beides', ['zelt'], 'klein',
        ['tagestouren', 'trainings', 'schrauben'], 'voll', 'nach_der_fahrt',
        'Yamaha Ténéré 700', ''),
    'dummy-schotter-lea': _profil(
        'Lohmar', W, '25-34', 40, 'egal', OHNE, ['enduro', 'touring'], 'zuegig', 6, 8000,
        'geuebt', ['tag', 'mehrtage'], 300, 'geniesser', ['zelt', 'pension'], 'klein',
        ['tagestouren', 'fernreisen', 'trainings'], 'voll', 'nie',
        'Honda CRF300 Rally', 'Querfeldein durch Naturschutzgebiete.'),
    'dummy-schotter-mehmet': _profil(
        'Hennef (Sieg)', M, '35-44', 50, 'egal', OHNE, ['enduro', 'landstrasse'], 'zuegig', 20,
        15000, 'sehr_erfahren', ['halbtag', 'tag'], 250, 'beides', ['pension'], 'mittel',
        ['tagestouren', 'schrauben', 'feierabendrunden'], 'voll', 'egal',
        'BMW R 1250 GS', ''),
    # Stoerfall Alterswunsch: will nur 18-34 - Sven (35-44) passt fuer ihn nicht.
    'dummy-schotter-tim': _profil(
        'Troisdorf', M, '18-24', 30, 'egal', ('18-24', '25-34'), ['enduro'], 'sportlich', 3,
        6000, 'einsteiger', ['halbtag'], 150, 'streckenfresser', ['zelt'], 'mittel',
        ['trainings', 'feierabendrunden'], 'teilweise', 'nach_der_fahrt',
        'KTM 390 Adventure', ''),
    # No-Go Alkohol, die strenge Fassung: auch "erst nach der Fahrt" reisst es.
    'dummy-schotter-nina': _profil(
        'Neunkirchen-Seelscheid', W, '45-54', 50, 'gemischt', OHNE, ['enduro', 'touring'],
        'zuegig', 12, 10000, 'erfahren', ['tag', 'mehrtage'], 300, 'geniesser',
        ['pension', 'hotel'], 'klein', ['tagestouren', 'fernreisen'], 'voll', 'nie',
        'Triumph Tiger 900 Rally',
        'Alkohol auf Tour – keinen Tropfen, auch nicht abends in der Unterkunft, '
        'solange am nächsten Tag gefahren wird.'),
    'dummy-eifel-rainer': _profil(
        'Adenau (Eifel)', M, '45-54', 60, 'egal', OHNE, ['enduro', 'landstrasse'], 'zuegig', 25,
        12000, 'sehr_erfahren', ['tag'], 300, 'beides', ['pension'], 'klein',
        ['tagestouren', 'schrauben'], 'voll', 'nach_der_fahrt', 'Husqvarna Norden 901', ''),

    # --- Sport/Rennstrecke (Pflicht: >= 3) -------------------------------
    'dummy-ring-marco': _profil(
        'Nürburg (Eifel)', M, '35-44', 80, 'egal', OHNE, ['sport', 'landstrasse'], 'sportlich',
        18, 14000, 'sehr_erfahren', ['tag'], 350, 'streckenfresser', ['hotel'], 'klein',
        ['trainings', 'tagestouren'], 'voll', 'nie', 'BMW S 1000 RR',
        'Heizen auf der Landstraße – dafür gibt es die Rennstrecke.'),
    'dummy-ring-kevin': _profil(
        'Köln', M, '25-34', 100, 'egal', OHNE, ['sport'], 'sportlich', 7, 12000, 'erfahren',
        ['tag'], 300, 'streckenfresser', ['hotel'], 'klein', ['trainings', 'schrauben'],
        'voll', 'nach_der_fahrt', 'Yamaha YZF-R6', ''),
    'dummy-ring-sabine': _profil(
        'Bonn', W, '45-54', 100, 'gemischt', OHNE, ['sport', 'landstrasse'], 'sportlich', 25,
        10000, 'sehr_erfahren', ['halbtag', 'tag'], 250, 'streckenfresser', ['hotel'], 'klein',
        ['trainings', 'messen'], 'voll', 'nach_der_fahrt', 'Ducati Panigale V2', ''),
    # Nachgetragen nach der Gegenpruefung (23.09.2026): Sabine war Muss-Kandidatin
    # fuer Marco, reisst aber plausibel sein Freitext-No-Go "Heizen auf der
    # Landstrasse" (sportlich, Streckenfresser, Landstrasse). Jens faehrt nur
    # Rennstrecke - der saubere Ersatz.
    'dummy-ring-jens': _profil(
        'Mayen (Eifel)', M, '35-44', 80, 'egal', OHNE, ['sport'], 'sportlich', 12, 11000,
        'erfahren', ['tag'], 300, 'streckenfresser', ['hotel'], 'klein',
        ['trainings', 'schrauben'], 'voll', 'nie', 'Honda CBR1000RR-R Fireblade', ''),
    'dummy-sauerland-kai': _profil(
        'Meschede (Sauerland)', M, '25-34', 80, 'egal', OHNE, ['landstrasse', 'sport'],
        'sportlich', 4, 7000, 'geuebt', ['halbtag', 'tag'], 250, 'streckenfresser', ['hotel'],
        'mittel', ['feierabendrunden', 'trainings'], 'teilweise', 'nach_der_fahrt',
        'Kawasaki Z900', ''),
    # Stoerfall Radius: Muenchen, Radius 50 - im Umkreis liegt niemand.
    'dummy-fern-bernd': _profil(
        'München', M, '45-54', 50, 'egal', OHNE, ['sport', 'touring'], 'sportlich', 28, 16000,
        'sehr_erfahren', ['tag', 'mehrtage'], 400, 'streckenfresser', ['hotel'], 'klein',
        ['trainings', 'fernreisen'], 'voll', 'nach_der_fahrt', 'BMW M 1000 XR', ''),

    # --- Frauen mit Praeferenz "gleich" (Pflicht: >= 4) ------------------
    'dummy-frauen-anja': _profil(
        'Bonn', W, '35-44', 50, 'gleich', ('25-34', '45-54'), ['landstrasse', 'touring'],
        'zuegig', 10, 8000, 'erfahren', ['tag', 'mehrtage'], 300, 'geniesser',
        ['pension', 'hotel'], 'klein', ['tagestouren', 'fernreisen', 'messen'], 'voll',
        'nach_der_fahrt', 'BMW F 900 XR', 'Ungefragte Belehrungen über meine Fahrweise.',
        feldstufen={'motorrad': Stufe.RIDEBUDDIES.value}),
    'dummy-frauen-carla': _profil(
        'Köln', W, '25-34', 60, 'gleich', OHNE, ['landstrasse', 'touring'], 'zuegig', 5, 6000,
        'geuebt', ['halbtag', 'tag', 'mehrtage'], 250, 'geniesser', ['pension'], 'klein',
        ['tagestouren', 'feierabendrunden', 'messen'], 'voll', 'nach_der_fahrt',
        'Kawasaki Versys 650', ''),
    # No-Go Alkohol, die mildere Fassung: nur "egal" reisst es.
    'dummy-frauen-petra': _profil(
        'Königswinter', W, '55-64', 60, 'gleich', OHNE, ['landstrasse', 'touring'],
        'gemuetlich', 30, 7000, 'sehr_erfahren', ['tag', 'mehrtage'], 250, 'geniesser',
        ['hotel'], 'klein', ['tagestouren', 'fernreisen'], 'voll', 'nie', 'Honda NT1100',
        'Alkohol vor oder während der Fahrt.'),
    'dummy-frauen-yvonne': _profil(
        'Bad Münstereifel (Eifel)', W, '35-44', 70, 'gleich', OHNE, ['landstrasse', 'cruisen'],
        'gemuetlich', 4, 4000, 'einsteiger', ['halbtag'], 150, 'geniesser', ['pension'],
        'mittel', ['tagestouren', 'trainings'], 'teilweise', 'nach_der_fahrt',
        'Harley-Davidson Sportster S', ''),
    'dummy-frauen-ines': _profil(
        'Montabaur (Westerwald)', W, '45-54', 40, 'gleich', OHNE, ['touring', 'landstrasse'],
        'zuegig', 15, 9000, 'erfahren', ['tag', 'mehrtage'], 350, 'geniesser',
        ['pension', 'hotel'], 'klein', ['fernreisen', 'tagestouren', 'messen'], 'voll',
        'nach_der_fahrt', 'Triumph Tiger 1200 GT', ''),
    'dummy-frauen-ayse': _profil(
        'Köln', W, '25-34', 50, 'gleich', OHNE, ['landstrasse', 'sport'], 'sportlich', 6, 9000,
        'erfahren', ['halbtag', 'tag'], 250, 'streckenfresser', ['hotel'], 'klein',
        ['trainings', 'feierabendrunden', 'messen'], 'voll', 'nach_der_fahrt',
        'Triumph Street Triple', ''),
    'dummy-frauen-melanie': _profil(
        'Troisdorf', W, '45-54', 50, 'gleich', OHNE, ['landstrasse', 'touring'], 'zuegig', 12,
        9000, 'erfahren', ['tag', 'mehrtage'], 300, 'geniesser', ['pension', 'hotel'], 'klein',
        ['tagestouren', 'fernreisen'], 'voll', 'nach_der_fahrt', 'Suzuki V-Strom 800', ''),
    # Stoerfall Radius: Hamburg, Radius 150 - im Umkreis liegt niemand.
    'dummy-fern-hanna': _profil(
        'Hamburg', W, '25-34', 150, 'gleich', OHNE, ['landstrasse', 'touring'], 'zuegig', 8,
        10000, 'erfahren', ['tag', 'mehrtage'], 350, 'geniesser', ['zelt', 'pension'], 'klein',
        ['fernreisen', 'tagestouren'], 'voll', 'nach_der_fahrt', 'Yamaha Tracer 7', ''),

    # --- Stoerfall Geschlecht "keine Angabe" -----------------------------
    # Weich fast deckungsgleich mit Anja - und fuer sie trotzdem nie ein
    # Vorschlag, weil "keine Angabe" in "nur Frauen" nicht auftaucht (Notiz).
    'dummy-ohne-angabe-robin': _profil(
        'Bonn-Beuel', KA, '35-44', 50, 'egal', OHNE, ['landstrasse', 'touring'], 'zuegig', 9,
        9000, 'erfahren', ['tag', 'mehrtage'], 300, 'geniesser', ['pension', 'hotel'], 'klein',
        ['tagestouren', 'fernreisen', 'messen'], 'voll', 'nach_der_fahrt',
        'Triumph Tiger Sport 660', '', feldstufen={'altersbereich': Stufe.VERBUNDEN.value}),

    # --- Koeln: Ausschluss und bestehende Verbindungen -------------------
    'dummy-koeln-frank': _profil(
        'Köln', M, '45-54', 60, 'egal', OHNE, ['landstrasse', 'touring'], 'zuegig', 22, 11000,
        'sehr_erfahren', ['tag', 'mehrtage'], 350, 'beides', ['hotel', 'pension'], 'mittel',
        ['tagestouren', 'fernreisen', 'messen'], 'voll', 'nach_der_fahrt', 'BMW R 1250 RT',
        'Unpünktlichkeit am Treffpunkt.'),
    'dummy-koeln-oliver': _profil(
        'Bergisch Gladbach', M, '45-54', 60, 'egal', OHNE, ['landstrasse', 'touring'],
        'sportlich', 20, 13000, 'sehr_erfahren', ['tag', 'mehrtage'], 400, 'streckenfresser',
        ['hotel'], 'mittel', ['tagestouren', 'fernreisen', 'messen'], 'voll', 'nach_der_fahrt',
        'Kawasaki Ninja 1000SX', ''),
    'dummy-koeln-dirk': _profil(
        'Köln-Porz', M, '45-54', 50, 'egal', OHNE, ['landstrasse', 'touring'], 'zuegig', 18,
        10000, 'erfahren', ['tag', 'mehrtage'], 300, 'beides', ['hotel'], 'mittel',
        ['tagestouren', 'messen'], 'voll', 'nach_der_fahrt',
        'Honda Africa Twin Adventure Sports', ''),
    'dummy-koeln-stefan': _profil(
        'Leverkusen', M, '45-54', 60, 'egal', OHNE, ['landstrasse', 'touring'], 'zuegig', 24,
        12000, 'sehr_erfahren', ['tag', 'mehrtage'], 350, 'beides', ['hotel', 'pension'],
        'mittel', ['tagestouren', 'fernreisen', 'messen'], 'voll', 'nach_der_fahrt',
        'BMW R 1300 GS', ''),
    'dummy-koeln-markus': _profil(
        'Brühl', M, '35-44', 60, 'egal', OHNE, ['landstrasse', 'touring'], 'zuegig', 14, 10000,
        'erfahren', ['tag', 'mehrtage'], 320, 'beides', ['hotel', 'pension'], 'mittel',
        ['tagestouren', 'fernreisen', 'messen'], 'voll', 'nach_der_fahrt',
        'Yamaha Tracer 9 GT', ''),
    'dummy-koeln-thomas': _profil(
        'Düsseldorf', M, '55-64', 40, 'egal', OHNE, ['cruisen', 'landstrasse'], 'gemuetlich',
        35, 6000, 'sehr_erfahren', ['halbtag'], 150, 'geniesser', ['hotel'], 'gross',
        ['feierabendrunden', 'schrauben'], 'egal', 'egal', 'Indian Chief', ''),

    # --- Westerwald, Sauerland, Siegen: Reisende -------------------------
    'dummy-westerwald-uwe': _profil(
        'Hachenburg (Westerwald)', M, '55-64', 120, 'egal', OHNE, ['touring', 'landstrasse'],
        'gemuetlich', 35, 15000, 'sehr_erfahren', ['mehrtage', 'tag'], 450, 'streckenfresser',
        ['zelt', 'pension'], 'klein', ['fernreisen', 'tagestouren'], 'voll', 'nie',
        'BMW R 1250 GS Adventure', 'Jeden Abend Hotel – ich schlafe gern im Zelt.'),
    'dummy-westerwald-gabi': _profil(
        'Altenkirchen (Westerwald)', W, '55-64', 100, 'gemischt', OHNE, ['touring'],
        'gemuetlich', 28, 12000, 'sehr_erfahren', ['mehrtage'], 400, 'geniesser',
        ['zelt', 'pension'], 'klein', ['fernreisen', 'tagestouren'], 'voll', 'nie',
        'Moto Guzzi V85 TT', 'Rauchen in der Pause direkt neben mir.'),
    'dummy-sauerland-heinz': _profil(
        'Winterberg (Sauerland)', M, '65+', 100, 'egal', OHNE, ['touring', 'landstrasse'],
        'gemuetlich', 40, 9000, 'sehr_erfahren', ['tag', 'mehrtage'], 350, 'geniesser',
        ['pension', 'hotel'], 'klein', ['fernreisen', 'tagestouren', 'schrauben'], 'voll',
        'nach_der_fahrt', 'Honda Gold Wing', ''),
    # Nachgetragen nach der Gegenpruefung (23.09.2026): Heinz war Muss-Kandidat
    # fuer Uwe, reisst aber plausibel dessen Freitext-No-Go "Jeden Abend Hotel"
    # (Uebernachtung nur Pension/Hotel). Joerg schlaeft nur im Zelt.
    'dummy-westerwald-joerg': _profil(
        'Bad Marienberg (Westerwald)', M, '55-64', 100, 'egal', OHNE, ['touring', 'landstrasse'],
        'gemuetlich', 25, 12000, 'sehr_erfahren', ['mehrtage', 'tag'], 400, 'streckenfresser',
        ['zelt'], 'klein', ['fernreisen', 'tagestouren'], 'voll', 'nie', 'Honda Africa Twin',
        ''),
    'dummy-siegen-klaus': _profil(
        'Siegen', M, '55-64', 100, 'egal', OHNE, ['touring', 'landstrasse'], 'gemuetlich', 30,
        14000, 'sehr_erfahren', ['mehrtage'], 450, 'streckenfresser', ['zelt'], 'klein',
        ['fernreisen'], 'voll', 'nie', 'Yamaha Ténéré 700 World Raid', ''),

    # --- Einsteiger um Bonn ----------------------------------------------
    # Stoerfall Alterswunsch: Luca will nur 18-34.
    'dummy-einsteiger-luca': _profil(
        'Bonn-Bad Godesberg', M, '18-24', 40, 'egal', ('18-24', '25-34'), ['landstrasse'],
        'gemuetlich', 1, 3000, 'einsteiger', ['halbtag'], 120, 'geniesser', [], 'mittel',
        ['feierabendrunden', 'trainings', 'tagestouren'], 'voll', 'nach_der_fahrt',
        'Yamaha MT-07', 'Wheelies und Rasen in der Gruppe.'),
    'dummy-einsteiger-mia': _profil(
        'Bonn', W, '18-24', 40, 'egal', OHNE, ['landstrasse'], 'gemuetlich', 2, 3500,
        'einsteiger', ['halbtag'], 120, 'geniesser', [], 'mittel',
        ['feierabendrunden', 'trainings'], 'voll', 'nie', 'Honda CB500F', ''),
    'dummy-einsteiger-paul': _profil(
        'Sankt Augustin', M, '25-34', 40, 'egal', OHNE, ['landstrasse'], 'gemuetlich', 2, 4000,
        'einsteiger', ['halbtag', 'tag'], 150, 'geniesser', [], 'mittel',
        ['feierabendrunden', 'tagestouren', 'trainings'], 'voll', 'nach_der_fahrt',
        'Suzuki SV650', ''),
    'dummy-bonn-walter': _profil(
        'Bonn', M, '55-64', 30, 'egal', OHNE, ['landstrasse', 'cruisen'], 'gemuetlich', 30, 5000,
        'sehr_erfahren', ['halbtag'], 120, 'geniesser', ['hotel'], 'mittel',
        ['feierabendrunden', 'tagestouren', 'schrauben'], 'teilweise', 'egal', 'Moto Guzzi V7',
        ''),
}

# Wer keine Einwilligung zur KI-Auswertung gibt: NIEMAND mehr.
# Bis 24.09.2026 stand hier Robin (dummy-ohne-angabe-robin), als Randfall fuer
# Schritt 9 ("seine Beitraege duerfen nicht ins Matching"). ENTSCHIEDEN (Fabian,
# 24.09.2026, TASK-120.13): "Wer keine KI-Einwilligung gibt, darf sich spaeter
# gar nicht anmelden; das System basiert auf der KI-Auswertung. Gib jetzt allen
# Testdaten und meinem Account die Einwilligung zum Testen." Einen Nutzer ohne
# Einwilligung gibt es damit im Betrieb nicht mehr, also auch keinen Dummy
# dafuer. Die Menge bleibt als Stellschraube stehen; anlegen() zieht die
# Einwilligung auf einem vorhandenen Bestand nach (_soll legt fehlende an).
# Die Datensperre in kern/urteile/sperre.py prueft die Einwilligung weiter.
OHNE_KI_EINWILLIGUNG = set()


# ---------------------------------------------------------------------------
# Beitraege - Schluessel (autor, erstellt); Text und Stufe werden nachgefuehrt.
# ---------------------------------------------------------------------------
# Einige tragen ein inhaltliches Signal fuer Schritt 9 ("ein Beitrag verschiebt
# nachweislich ein Ranking"); welches, steht im Pruefblatt unter "Beitragssignale".

def _zeit(tag, stunde):
    return datetime.datetime(2026, 9, tag, stunde, 0, tzinfo=UTC)


BEITRAEGE = [
    ('dummy-schotter-sven', _zeit(1, 9), Stufe.OEFFENTLICH,
     'Suche Leute für Schotter im Bergischen und im Westerwald. Früh los, Pause mit '
     'Thermoskanne statt Biergarten, abends gern ein Bier am Zelt.'),
    # Signal: Alkohol WAEHREND der Tour - verstaerkt den No-Go-Konflikt mit Petra/Nina.
    ('dummy-schotter-mehmet', _zeit(2, 12), Stufe.OEFFENTLICH,
     'Zur Mittagspause gehört für mich ein Radler dazu, manchmal auch ein richtiges Bier – '
     'danach geht es gemütlich weiter.'),
    # Signal: Paul ist im Profil reiner Landstrassenfahrer, will aber ins Gelaende.
    # Nach Schritt 9 soll er fuer Sven und Jonas nach oben ruecken.
    ('dummy-einsteiger-paul', _zeit(3, 18), Stufe.OEFFENTLICH,
     'Seit diesem Frühjahr zieht es mich auf Schotter: Die SV650 ist verkauft, eine '
     'Ténéré 700 bestellt und ein Enduro-Grundkurs gebucht. Wer nimmt einen Anfänger mit '
     'ins Gelände?'),
    ('dummy-einsteiger-luca', _zeit(4, 19), Stufe.OEFFENTLICH,
     'Ich fahre seit einem Jahr und suche ruhige Feierabendrunden um Bonn – niemand muss '
     'mir zeigen, was seine Maschine kann.'),
    ('dummy-frauen-yvonne', _zeit(5, 10), Stufe.VERBUNDEN,
     'Ich fahre erst seit vier Jahren und mag Runden, bei denen niemand drängelt und man '
     'an der Eisdiele auch mal eine Stunde sitzen bleibt.'),
    ('dummy-frauen-anja', _zeit(6, 20), Stufe.RIDEBUDDIES,
     'Nach meinem Sturz 2024 fahre ich defensiver. Das erzähle ich lieber nur Leuten, die '
     'ich schon kenne.'),
    ('dummy-schotter-nina', _zeit(7, 8), Stufe.VERBUNDEN,
     'Ich trinke seit Jahren keinen Alkohol und fahre am liebsten mit Leuten, bei denen das '
     'auch abends kein Thema ist.'),
    ('dummy-koeln-frank', _zeit(8, 9), Stufe.OEFFENTLICH,
     'Treffpunkt heißt bei mir: Um neun läuft der Motor, nicht um Viertel nach.'),
    ('dummy-westerwald-uwe', _zeit(9, 21), Stufe.OEFFENTLICH,
     'Nordkap 2025 mit Zelt, nächstes Jahr das Baltikum. Wer Lust auf lange Etappen und '
     'Isomatte hat, meldet sich.'),
    ('dummy-westerwald-gabi', _zeit(10, 7), Stufe.RIDEBUDDIES,
     'Mein Knie macht lange Etappen nicht mehr jeden Tag mit – bei Reisen plane ich '
     'Ruhetage ein.'),
    ('dummy-sauerland-heinz', _zeit(11, 16), Stufe.VERBUNDEN,
     'Schraube im Winter an einer R 80 G/S von 1983. Ersatzteile tausche ich gern.'),
    ('dummy-ohne-angabe-robin', _zeit(12, 14), Stufe.OEFFENTLICH,
     'Mein Geschlecht gebe ich bewusst nicht an – mir geht es ums Fahren.'),
    ('dummy-ring-kevin', _zeit(13, 17), Stufe.OEFFENTLICH,
     'Auf der Rennstrecke gebe ich alles, auf der Landstraße fahre ich nach Schild.'),
]


# ---------------------------------------------------------------------------
# Crews - Schluessel: Name + Marke in der Beschreibung.
# ---------------------------------------------------------------------------
# Festlegung der Bausitzung: Kein Anker aus dem Pruefblatt sitzt mit einem
# seiner Muss- oder Nie-Kandidaten in derselben Crew. Sonst haenge das
# Pruefblatt an der offenen Frage, ob das Matching Crew-Kollegen ueberhaupt
# vorschlaegt (in der Notiz nicht entschieden).
O, MI, G = (Mitgliedschaft.Rolle.ORGANISATOR, Mitgliedschaft.Rolle.MITGLIED,
            Mitgliedschaft.Rolle.GAST)

CREWS = {
    'Schotterbande Siegburg': (
        'Schotter und Waldwege zwischen Siebengebirge und Bergischem Land.',
        [('dummy-schotter-jonas', O), ('dummy-schotter-mehmet', MI),
         ('dummy-schotter-tim', MI), ('dummy-eifel-rainer', MI), ('dummy-schotter-lea', G)]),
    'Ladies on Tour Rheinland': (
        'Frauenrunde zwischen Köln, Bonn und Eifel.',
        [('dummy-frauen-carla', O), ('dummy-frauen-ayse', MI), ('dummy-frauen-yvonne', MI),
         ('dummy-frauen-petra', G)]),
    'Westerwald-Weitfahrer': (
        'Mehrtägige Reisen, gern mit Zelt.',
        [('dummy-westerwald-gabi', O), ('dummy-sauerland-heinz', MI),
         ('dummy-frauen-ines', MI), ('dummy-koeln-markus', G)]),
}


# ---------------------------------------------------------------------------
# Ausfahrten und Reisen (Saison 2027, April-Juni) mit Terminabstimmung.
# ---------------------------------------------------------------------------
# Fuer Schritt 6 (Prozentwert je Termin) so gewaehlt, dass es klare Faelle gibt.
# Die Faelle stehen mit Zaehlung im Pruefblatt unter "Terminfaelle fuer Schritt 6".
# S = sicher, V = mit Vorbehalt, N = nein. Reihenfolge der Buchstaben = Reihenfolge
# der Teilnehmer in `wer`.
#
# Schluessel einer Ausfahrt: Titel + Crew (+ Marke). Die crewlose Ausfahrt hat
# als Schluessel Titel + vorgeschlagen_von.
D = datetime.date

AUSFAHRTEN = [
    {
        'titel': 'Schotterrunde Bergisches Land', 'art': 'tagestour',
        'crew': 'Schotterbande Siegburg', 'von': 'dummy-schotter-jonas',
        'wer': ['dummy-schotter-jonas', 'dummy-schotter-mehmet', 'dummy-schotter-tim',
                'dummy-eifel-rainer', 'dummy-schotter-lea'],
        'termine': [
            (D(2027, 4, 17), 'vormittags', 'SSSSS'),   # alle sicher -> 100 %
            (D(2027, 4, 18), 'vormittags', 'SVSVS'),   # 3 sicher, 2 mit Vorbehalt
            (D(2027, 4, 24), 'nachmittags', 'SNNSN'),  # 3 fehlen
        ],
    },
    {
        'titel': 'Enduro-Grundlagentraining', 'art': 'training',
        'crew': 'Schotterbande Siegburg', 'von': 'dummy-schotter-mehmet',
        'wer': ['dummy-schotter-jonas', 'dummy-schotter-mehmet', 'dummy-schotter-tim',
                'dummy-eifel-rainer', 'dummy-schotter-lea'],
        'termine': [
            (D(2027, 5, 8), 'vormittags', 'SSVNS'),    # gleichauf mit dem naechsten:
            (D(2027, 5, 15), 'vormittags', 'SNSVS'),   # je 3 S, 1 V, 1 N (andere Leute)
        ],
    },
    {
        'titel': 'Frauenrunde Ahr und Eifel', 'art': 'tagestour',
        'crew': 'Ladies on Tour Rheinland', 'von': 'dummy-frauen-carla',
        'wer': ['dummy-frauen-carla', 'dummy-frauen-ayse', 'dummy-frauen-yvonne',
                'dummy-frauen-petra'],
        'termine': [
            (D(2027, 5, 2), 'mittags', 'SSSS'),        # 100 %
            (D(2027, 5, 9), 'mittags', 'SSVN'),
        ],
    },
    {
        'titel': 'Messebesuch Frühjahrsmesse', 'art': 'messe',
        'crew': 'Ladies on Tour Rheinland', 'von': 'dummy-frauen-ayse',
        'wer': ['dummy-frauen-carla', 'dummy-frauen-ayse', 'dummy-frauen-yvonne',
                'dummy-frauen-petra'],
        'termine': [
            (D(2027, 4, 10), 'vormittags', 'SVVS'),
            (D(2027, 4, 11), 'vormittags', 'SNSN'),
        ],
    },
    {
        # Ohne Crew (erlaubt, siehe Ausfahrt-Docstring). Wer abstimmt, ergibt
        # sich hier aus den Teilnahmen.
        'titel': 'Renntraining Nürburgring', 'art': 'training',
        'crew': None, 'von': 'dummy-ring-kevin',
        'wer': ['dummy-ring-kevin', 'dummy-ring-sabine', 'dummy-ring-marco'],
        'teilnahmen': {'dummy-ring-kevin': 'zugesagt', 'dummy-ring-sabine': 'zugesagt',
                       'dummy-ring-marco': 'offen'},
        'termine': [
            (D(2027, 6, 12), 'vormittags', 'SSV'),
            (D(2027, 6, 26), 'vormittags', 'SNS'),
        ],
    },
    # Reisen: Termin = Zeitraum, Antworten als Verfuegbarkeitszeitraum.
    {
        'titel': 'Vogesen-Reise', 'art': 'reise',
        'crew': 'Westerwald-Weitfahrer', 'von': 'dummy-westerwald-gabi',
        'wer': ['dummy-westerwald-gabi', 'dummy-sauerland-heinz', 'dummy-frauen-ines',
                'dummy-koeln-markus'],
        'zeitraeume': [
            (D(2027, 6, 3), D(2027, 6, 6), 'SSSV'),
            (D(2027, 6, 17), D(2027, 6, 20), 'SNSN'),
        ],
    },
    {
        'titel': 'Pfingsttour Harz', 'art': 'reise',
        'crew': 'Westerwald-Weitfahrer', 'von': 'dummy-sauerland-heinz',
        'wer': ['dummy-westerwald-gabi', 'dummy-sauerland-heinz', 'dummy-frauen-ines',
                'dummy-koeln-markus'],
        'zeitraeume': [
            (D(2027, 5, 14), D(2027, 5, 17), 'SSSS'),  # 100 %
            (D(2027, 5, 21), D(2027, 5, 24), 'VSVS'),
        ],
    },
]

STUFE_BUCHSTABE = {'S': 'sicher', 'V': 'vorbehalt', 'N': 'nein'}


# ---------------------------------------------------------------------------
# Beziehungen - ueber kern/ablaeufe.py.
# ---------------------------------------------------------------------------
VERBINDUNGEN = [  # Stufe verbunden, ueber eine angenommene Anfrage
    ('dummy-koeln-frank', 'dummy-koeln-dirk'),
    ('dummy-frauen-carla', 'dummy-frauen-ayse'),
    ('dummy-ring-kevin', 'dummy-ring-sabine'),
]
RIDEBUDDIES = [  # verbunden + bestaetigte Ridebuddy-Anfrage (erster fragt, zweiter bestaetigt)
    ('dummy-koeln-frank', 'dummy-koeln-stefan'),
    ('dummy-schotter-jonas', 'dummy-schotter-mehmet'),
    ('dummy-westerwald-gabi', 'dummy-sauerland-heinz'),
]
# Ausschluesse auf zwei verschiedenen Wegen der Notiz:
#  - "passt nicht" auf einen Vorschlag (Runde 1), mit angetippter Dimension;
#  - Verbindung beendet mit "passt nicht" (die Verbindung bleibt als Geschichte).
AUSSCHLUESSE = [
    {'urheber': 'dummy-koeln-frank', 'betroffener': 'dummy-koeln-oliver', 'weg': 'vorschlag',
     'dimension': Dimension.TEMPO, 'text': 'klebt am Hinterrad'},
    {'urheber': 'dummy-westerwald-uwe', 'betroffener': 'dummy-siegen-klaus',
     'weg': 'verbindung', 'dimension': Dimension.UNTERWEGS,
     'text': 'wollte jeden Tag 700 km'},
]
VORSCHLAG_RUNDE = 1


# ---------------------------------------------------------------------------
# Anlegen
# ---------------------------------------------------------------------------

class Zaehler:
    """Neu/geaendert je Modell - fuer die Zusammenfassung und die Tests."""

    def __init__(self):
        self.neu = {}
        self.geaendert = {}

    def _plus(self, tabelle, modell, n=1):
        name = modell if isinstance(modell, str) else modell.__name__
        tabelle[name] = tabelle.get(name, 0) + n

    def zaehle_neu(self, modell, n=1):
        self._plus(self.neu, modell, n)

    def zaehle_geaendert(self, modell, n=1):
        self._plus(self.geaendert, modell, n)

    @property
    def nichts_geschrieben(self):
        return not self.neu and not self.geaendert


def _soll(zaehler, modell, schluessel, werte, qs=None):
    """Holt den Datensatz ueber `schluessel` oder legt ihn an; weichen Felder aus
    `werte` ab, werden genau diese gespeichert. Gibt das Objekt zurueck."""
    qs = qs if qs is not None else modell.objects.all()
    obj = qs.filter(**schluessel).first()
    if obj is None:
        obj = modell.objects.create(**schluessel, **werte)
        zaehler.zaehle_neu(modell)
        return obj
    _angleichen(zaehler, obj, werte)
    return obj


def _angleichen(zaehler, obj, werte, als_neu=False):
    geaendert = [feld for feld, wert in werte.items() if getattr(obj, feld) != wert]
    if geaendert:
        for feld in geaendert:
            setattr(obj, feld, werte[feld])
        # auto_now-Felder (Profil.geaendert) nur mitspeichern, wenn wirklich
        # geschrieben wird - sonst waere der zweite Lauf nicht ohne Aenderung.
        extra = [f.name for f in obj._meta.concrete_fields
                 if getattr(f, 'auto_now', False)]
        obj.save(update_fields=geaendert + extra)
        if als_neu:
            zaehler.zaehle_neu(type(obj))
        else:
            zaehler.zaehle_geaendert(type(obj))
    return bool(geaendert)


def _kennwort_setzen(zaehler, nutzer, kennwort, hash_cache):
    """Kennwort nur neu setzen, wenn das gespeicherte nicht passt.

    `hash_cache` haelt je gespeichertem Hash das Pruefergebnis und den einmal
    erzeugten neuen Hash: Jeder PBKDF2-Lauf kostet auf VM 140 ueber eine Sekunde
    (kern/tests/hilfen.py), bei 37 Dummies waeren das je Lauf eine halbe Minute.
    Alle Dummies bekommen deshalb DENSELBEN Hash (gleiches Salz). Fuer
    Wegwerfkonten mit gemeinsamem Kennwort verraet das nichts, was nicht ohnehin
    feststeht; fuer echte Konten waere es falsch.

    Bewusst hashers.check_password statt nutzer.check_password: Letzteres
    speichert bei veraltetem Hasher still einen neuen Hash - dann aenderte ein
    zweiter Lauf doch etwas.
    """
    if kennwort is None:
        # Ohne --kennwort-datei: neue Dummies sind ohnehin ohne Kennwort
        # (create_user mit password=None). Ein vorhandenes Kennwort bleibt -
        # ein Lauf ohne Datei soll niemandem die Anmeldung wegnehmen.
        return
    gespeichert = nutzer.password
    if gespeichert not in hash_cache['geprueft']:
        hash_cache['geprueft'][gespeichert] = (
            nutzer.has_usable_password() and check_password(kennwort, gespeichert))
    if hash_cache['geprueft'][gespeichert]:
        return
    if hash_cache.get('neu') is None:
        hash_cache['neu'] = make_password(kennwort)
        hash_cache['geprueft'][hash_cache['neu']] = True
    nutzer.password = hash_cache['neu']
    nutzer.save(update_fields=['password'])
    zaehler.zaehle_geaendert('Kennwort')


def _nutzer_anlegen(zaehler, name, kennwort, hash_cache):
    Nutzer = get_user_model()
    email = f'{name}{DOMAIN}'
    nutzer = Nutzer.objects.filter(username=name).first()
    neu_angelegt = nutzer is None
    if nutzer is None:
        if Nutzer.objects.filter(email__iexact=email).exists():
            raise DummyFehler(f'{email} gehört schon einem anderen Konto.')
        nutzer = Nutzer.objects.create_user(username=name, email=email, password=None)
        zaehler.zaehle_neu(Nutzer)
    elif nutzer.email.lower() != email:
        # Ein echter Nutzer mit diesem Namen - nicht anfassen.
        raise DummyFehler(f'Nutzer {name} existiert, ist aber kein Dummy '
                          f'(E-Mail endet nicht auf {DOMAIN}) - Abbruch, nichts geändert.')
    _kennwort_setzen(zaehler, nutzer, kennwort, hash_cache)

    # allauth: bestaetigt + primaer, sonst laesst /konto/login/ bei
    # ACCOUNT_EMAIL_VERIFICATION='mandatory' niemanden herein
    # (siehe email_bestaetigen.py fuer den Vorfall dahinter).
    _soll(zaehler, EmailAddress, {'user': nutzer, 'email': email},
          {'verified': True, 'primary': True})

    profil = Profil.objects.get(nutzer=nutzer)
    # Das Signal legt das Profil leer an; beim ersten Lauf ist das Fuellen also
    # kein "Angleichen", sondern Teil des Neuanlegens - so zaehlt es auch.
    _angleichen(zaehler, profil, PROFILE[name], als_neu=neu_angelegt)

    arten = [Einwilligung.Art.VOLLJAEHRIG]
    if name not in OHNE_KI_EINWILLIGUNG:
        arten.append(Einwilligung.Art.KI_AUSWERTUNG)
    for art in arten:
        _soll(zaehler, Einwilligung,
              {'nutzer': nutzer, 'art': art, 'version': EINWILLIGUNG_VERSION},
              {'erteilt_am': _zeit(1, 8), 'widerrufen_am': None})
    return nutzer


class DummyFehler(Exception):
    """Der Bestand laesst sich nicht sauber herstellen - die Transaktion rollt zurueck."""


def _crew(zaehler, name, beschreibung):
    text = f'{MARKE} {beschreibung}'
    qs = Crew.objects.filter(beschreibung__startswith=MARKE)
    return _soll(zaehler, Crew, {'name': name}, {'beschreibung': text}, qs=qs)


def _verbinden(zaehler, a, b):
    verbindung = aktive_verbindung(a, b)
    if verbindung is not None:
        return verbindung
    if ausgeschlossen(a, b):
        raise DummyFehler(f'{a} und {b} sollen verbunden werden, sind aber ausgeschlossen.')
    anfrage = Anfrage.objects.filter(absender=a, empfaenger=b,
                                     status=Anfrage.Status.OFFEN).first()
    if anfrage is None:
        anfrage = ablaeufe.anfrage_stellen(a, b, text='Lust auf eine gemeinsame Runde?')
        zaehler.zaehle_neu(Anfrage)
    verbindung = ablaeufe.anfrage_beantworten(anfrage, b, annehmen=True)
    zaehler.zaehle_neu('Verbindung')
    return verbindung


def _ridebuddies(zaehler, a, b):
    verbindung = _verbinden(zaehler, a, b)
    if verbindung.erreicht == Stufe.RIDEBUDDIES:
        return verbindung
    anfrage = verbindung.ridebuddy_anfragen.filter(
        status=RidebuddyAnfrage.Status.OFFEN).first()
    if anfrage is None:
        anfrage = ablaeufe.ridebuddy_anfrage_stellen(a, b)
        zaehler.zaehle_neu(RidebuddyAnfrage)
    ablaeufe.ridebuddy_anfrage_beantworten(anfrage, anfrage.empfaenger, bestaetigen=True)
    zaehler.zaehle_geaendert('Verbindung')
    return verbindung


def _ausschliessen(zaehler, eintrag, n):
    urheber, betroffener = n[eintrag['urheber']], n[eintrag['betroffener']]
    if Ausschluss.objects.filter(urheber=urheber, betroffener=betroffener).exists():
        return
    if eintrag['weg'] == 'vorschlag':
        vorschlag = Vorschlag.objects.filter(empfaenger=urheber, kandidat=betroffener,
                                             runde=VORSCHLAG_RUNDE).first()
        if vorschlag is None:
            vorschlag = Vorschlag.objects.create(
                empfaenger=urheber, kandidat=betroffener, runde=VORSCHLAG_RUNDE,
                begruendung={Dimension.FAHRART.value: 'beide Landstraße und Touring',
                             Dimension.THEMEN.value: 'beide Messen und Fernreisen'})
            zaehler.zaehle_neu(Vorschlag)
        if vorschlag.reaktion == Vorschlag.Reaktion.OFFEN:
            ablaeufe.vorschlag_reagieren(vorschlag, urheber, Vorschlag.Reaktion.PASST_NICHT,
                                         eintrag['dimension'], eintrag['text'])
            zaehler.zaehle_geaendert(Vorschlag)
    else:
        verbindung = _verbinden(zaehler, urheber, betroffener)
        ablaeufe.verbindung_beenden(verbindung, urheber, Ausgang.PASST_NICHT,
                                    eintrag['dimension'], eintrag['text'])
        zaehler.zaehle_geaendert('Verbindung')
    if not Ausschluss.objects.filter(urheber=urheber, betroffener=betroffener).exists():
        raise DummyFehler(f'Ausschluss {urheber} -> {betroffener} ist nicht entstanden.')
    zaehler.zaehle_neu(Ausschluss)


def _ausfahrt(zaehler, eintrag, n, crews):
    crew = crews[eintrag['crew']] if eintrag['crew'] else None
    von = n[eintrag['von']]
    schluessel = {'titel': eintrag['titel'], 'crew': crew}
    if crew is None:
        schluessel['vorgeschlagen_von'] = von
    werte = {'art': eintrag['art'], 'status': Ausfahrt.Status.ABSTIMMUNG,
             'beschreibung': f'{MARKE} Terminabstimmung für die Saison 2027.'}
    if crew is not None:
        werte['vorgeschlagen_von'] = von
    ausfahrt = _soll(zaehler, Ausfahrt, schluessel, werte,
                     qs=Ausfahrt.objects.filter(beschreibung__startswith=MARKE))
    wer = [n[name] for name in eintrag['wer']]

    for name, zusage in eintrag.get('teilnahmen', {}).items():
        _soll(zaehler, Teilnahme, {'ausfahrt': ausfahrt, 'nutzer': n[name]},
              {'zusage': zusage, 'gefahren': False})

    for datum, tageszeit, antworten in eintrag.get('termine', []):
        _soll(zaehler, Termin, {'ausfahrt': ausfahrt, 'datum': datum, 'tageszeit': tageszeit,
                                'bis_datum': None}, {'gewaehlt': False})
        for person, buchstabe in zip(wer, antworten, strict=True):
            _soll(zaehler, Verfuegbarkeit,
                  {'nutzer': person, 'ausfahrt': ausfahrt, 'datum': datum,
                   'tageszeit': tageszeit},
                  {'stufe': STUFE_BUCHSTABE[buchstabe]})

    for von_datum, bis_datum, antworten in eintrag.get('zeitraeume', []):
        _soll(zaehler, Termin, {'ausfahrt': ausfahrt, 'datum': von_datum,
                                'bis_datum': bis_datum, 'tageszeit': ''}, {'gewaehlt': False})
        for person, buchstabe in zip(wer, antworten, strict=True):
            _soll(zaehler, Verfuegbarkeitszeitraum,
                  {'nutzer': person, 'ausfahrt': ausfahrt, 'von': von_datum, 'bis': bis_datum},
                  {'stufe': STUFE_BUCHSTABE[buchstabe]})
    return ausfahrt


@transaction.atomic
def anlegen(kennwort=None):
    """Stellt den Dummy-Bestand her. Gibt den Zaehler zurueck.

    `kennwort` = Klartext aus der Kennwortdatei oder None. Er wird hier nur an
    make_password/check_password gereicht - nie ausgegeben, nie geloggt.
    """
    zaehler = Zaehler()
    hash_cache = {'geprueft': {}, 'neu': None}
    n = {name: _nutzer_anlegen(zaehler, name, kennwort, hash_cache) for name in PROFILE}

    for autor, erstellt, stufe, text in BEITRAEGE:
        _soll(zaehler, Beitrag, {'autor': n[autor], 'erstellt': erstellt},
              {'stufe': stufe.value, 'text': text})

    crews = {}
    for name, (beschreibung, mitglieder) in CREWS.items():
        crew = _crew(zaehler, name, beschreibung)
        crews[name] = crew
        for mitglied, rolle in mitglieder:
            _soll(zaehler, Mitgliedschaft, {'crew': crew, 'nutzer': n[mitglied]},
                  {'rolle': rolle})

    for eintrag in AUSFAHRTEN:
        _ausfahrt(zaehler, eintrag, n, crews)

    for a, b in VERBINDUNGEN:
        _verbinden(zaehler, n[a], n[b])
    for a, b in RIDEBUDDIES:
        _ridebuddies(zaehler, n[a], n[b])
    for eintrag in AUSSCHLUESSE:
        _ausschliessen(zaehler, eintrag, n)
    return zaehler


# ---------------------------------------------------------------------------
# Abraeumen
# ---------------------------------------------------------------------------

def _nur_dummies(personen_ids, dummy_ids):
    personen_ids = {p for p in personen_ids if p is not None}
    return bool(personen_ids) and personen_ids <= dummy_ids


@transaction.atomic
def abraeumen():
    """Loescht alle Dummies samt abhaengigen Daten und alles, was NUR Dummies gehoert.

    "Gehoert nur Dummies" (Festlegung der Bausitzung):
      - Crew: mindestens ein Mitglied, und alle Mitglieder sind Dummies. Eine
        Crew mit einem echten Mitglied bleibt - die Dummies verschwinden nur
        daraus.
      - Ausfahrt: alle beteiligten Personen (Vorschlagende, Teilnehmer,
        Abstimmende, Feedback, bei Crew-Ausfahrten zusaetzlich alle
        Crew-Mitglieder) sind Dummies.
      - Crew-Vorschlag: alle Beteiligten sind Dummies.
    Der Rest faellt ueber on_delete=CASCADE mit dem Nutzer (Profil, Beitraege,
    Verbindungen, Anfragen, Ausschluesse, Verfuegbarkeiten, EmailAddress ...).
    PROTECT gibt es im Modell nicht (Stand 23.09.2026, geprueft in
    kern/models.py und allauth.account); SET_NULL-Verweise echter Daten auf
    einen Dummy (z. B. Verbindung.beendet_von) werden leer.

    Gibt {Modellname: Anzahl geloescht} zurueck (Djangos delete()-Zaehlung).
    """
    Nutzer = get_user_model()
    dummy_ids = set(dummies().values_list('pk', flat=True))
    geloescht = {}

    def _addiere(ergebnis):
        for label, anzahl in ergebnis[1].items():
            if anzahl:
                name = label.split('.')[-1]
                geloescht[name] = geloescht.get(name, 0) + anzahl

    crew_ids = []
    for crew in Crew.objects.prefetch_related('mitgliedschaften'):
        if _nur_dummies([m.nutzer_id for m in crew.mitgliedschaften.all()], dummy_ids):
            crew_ids.append(crew.pk)

    ausfahrt_ids = []
    for ausfahrt in Ausfahrt.objects.all():
        personen = {ausfahrt.vorgeschlagen_von_id}
        personen |= set(ausfahrt.teilnahmen.values_list('nutzer_id', flat=True))
        personen |= set(ausfahrt.verfuegbarkeiten.values_list('nutzer_id', flat=True))
        personen |= set(ausfahrt.verfuegbarkeitszeitraeume.values_list('nutzer_id', flat=True))
        personen |= set(ausfahrt.feedbacks.values_list('verfasser_id', flat=True))
        if ausfahrt.crew_id is not None:
            personen |= set(Mitgliedschaft.objects.filter(crew_id=ausfahrt.crew_id)
                            .values_list('nutzer_id', flat=True))
        if _nur_dummies(personen, dummy_ids):
            ausfahrt_ids.append(ausfahrt.pk)

    crew_vorschlag_ids = [
        cv.pk for cv in CrewVorschlag.objects.prefetch_related('beteiligte')
        if _nur_dummies([b.pk for b in cv.beteiligte.all()], dummy_ids)
    ]

    # Reihenfolge: erst Ausfahrten (sonst setzte das Loeschen der Crew ihren
    # Verweis nur auf NULL), dann Crews und Crew-Vorschlaege, dann die Nutzer.
    _addiere(Ausfahrt.objects.filter(pk__in=ausfahrt_ids).delete())
    _addiere(CrewVorschlag.objects.filter(pk__in=crew_vorschlag_ids).delete())
    _addiere(Crew.objects.filter(pk__in=crew_ids).delete())
    _addiere(Nutzer.objects.filter(pk__in=dummy_ids).delete())
    return geloescht


# ---------------------------------------------------------------------------
# Bestand zaehlen (fuer die Zusammenfassung)
# ---------------------------------------------------------------------------

def bestand():
    """Anzahl der Dummy-Datensaetze je Modell (was zu einem Dummy gehoert)."""
    d = dummies()
    crews = Crew.objects.filter(mitgliedschaften__nutzer__in=d).distinct()
    ausfahrten = Ausfahrt.objects.filter(
        Q(crew__in=crews) | Q(vorgeschlagen_von__in=d)).distinct()
    return {
        'Nutzer': d.count(),
        'EmailAddress': EmailAddress.objects.filter(user__in=d).count(),
        'Profil': Profil.objects.filter(nutzer__in=d).count(),
        'Einwilligung': Einwilligung.objects.filter(nutzer__in=d).count(),
        'Beitrag': Beitrag.objects.filter(autor__in=d).count(),
        'Crew': crews.count(),
        'Mitgliedschaft': Mitgliedschaft.objects.filter(nutzer__in=d).count(),
        'Ausfahrt': ausfahrten.count(),
        'Termin': Termin.objects.filter(ausfahrt__in=ausfahrten).count(),
        'Teilnahme': Teilnahme.objects.filter(nutzer__in=d).count(),
        'Verfuegbarkeit': Verfuegbarkeit.objects.filter(nutzer__in=d).count(),
        'Verfuegbarkeitszeitraum': Verfuegbarkeitszeitraum.objects.filter(nutzer__in=d).count(),
        'Anfrage': Anfrage.objects.filter(absender__in=d).count(),
        'Verbindung': Verbindung.objects.filter(nutzer_a__in=d, nutzer_b__in=d).count(),
        'RidebuddyAnfrage': RidebuddyAnfrage.objects.filter(absender__in=d).count(),
        'Vorschlag': Vorschlag.objects.filter(empfaenger__in=d).count(),
        'Ausschluss': Ausschluss.objects.filter(urheber__in=d).count(),
    }
