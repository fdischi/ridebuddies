"""
Matching (Karte TASK-120.13, Schritt 8, 24./25.09.2026).

Was hier geprueft wird und warum:
- PRUEFBLATT OFFLINE: Alle 8 Anker gegen docs/pruefblatt-matching.json, mit den
  KI-Urteilen aus der Aufzeichnung im Repo und einem STRENGEN Test-Anbieter -
  fehlt eine Antwort, bricht das Holen mit 'keine_aufzeichnung' ab und der
  Kandidat steht auf 'nogo_offen'; der Test prueft, dass das nirgends passiert.
  Kein Netz. Mit der Jev-Aufzeichnung muss das Blatt VOLLSTAENDIG stimmen; mit
  der Claude-Aufzeichnung weicht es ab, und der Test verlangt genau die
  erklaerten Abweichungen (ABWEICHUNGEN_CLAUDE) - nicht mehr und nicht weniger.
- GRENZFAELLE: die 17 Paare am Radius, wie im Blatt.
- KOSTEN: Gewichte aendern und hart/weich umschalten aendern das Ranking, der
  zaehlende Test-Anbieter bekommt dabei KEINE neue Anfrage (Fabian, 24.09.2026).
- LEITPLANKEN: kein Ausschluss-Datensatz durch ein KI-Urteil, keine Koordinaten
  und keine ungerundete Entfernung in der Begruendung, Geschlecht und Alter nie
  als Punktzahl oder Begruendung, verborgene Felder nicht woertlich, keine
  Vorschlaege ohne Einwilligung, Datensperre haelt.
"""
import json
import logging
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from kern import matching, urteile
from kern.geo import profil_entfernung_km
from kern.matching import filter as harte
from kern.matching import nogo
from kern.models import (
    Ausschluss,
    Einwilligung,
    MerkmalUrteil,
    PaarUrteil,
    Profil,
    Vorschlag,
)
from kern.urteile.aufzeichnung import TestAnbieter

from .hilfen import nutzer

DOCS = Path(settings.BASE_DIR) / 'docs'
BLATT = json.loads((DOCS / 'pruefblatt-matching.json').read_text(encoding='utf-8'))

# Pruefblatt-Gruende -> Gruende des Matchings.
GRUND = {'radius': 'region', 'nogo_freitext': 'nogo'}

# Erklaerte Abweichungen mit der Claude-Aufzeichnung (Paar f3, Regeln r2,
# claude-haiku-4-5; Schwellen claude: Paar 0,73, Regeln abgeschaltet -
# kern/matching/nogo.py):
#  - Claude trennt die Freitext-Faelle nicht: Uwe->Heinz liegt mit 0,725 genau
#    auf Uwe->Joerg (Muss), Marco->Sabine mit 0,650 genau auf Marco->Kevin (Muss).
#    Die Schwelle haelt die Muss-Paare drin, also bleiben Heinz und Sabine.
#  - Ninas strenges Alkohol-No-Go erkennt Claude weder im Paarurteil noch als
#    Regel (Regeln abgeschaltet, siehe nogo.py). Nina bleibt fuer Sven und Anja
#    zulaessig, Sven/Jonas/Mehmet fuer Nina, und weil Nina so viele
#    "erst nach der Fahrt"-Kandidaten behaelt, rutscht Gabi aus ihren Top 5.
# (anker, kandidat, art): 'muss_fehlt' | 'nie_gezeigt' (in den Top 5) |
# 'nie_zulaessig' (nicht ausgeschlossen, aber nicht unter den ersten fuenf).
ABWEICHUNGEN_CLAUDE = {
    ('dummy-schotter-sven', 'dummy-schotter-nina', 'nie_gezeigt'),
    ('dummy-ring-marco', 'dummy-ring-sabine', 'nie_gezeigt'),
    ('dummy-frauen-anja', 'dummy-schotter-nina', 'nie_gezeigt'),
    ('dummy-schotter-nina', 'dummy-westerwald-gabi', 'muss_fehlt'),
    ('dummy-schotter-nina', 'dummy-schotter-mehmet', 'nie_zulaessig'),
    ('dummy-schotter-nina', 'dummy-schotter-sven', 'nie_zulaessig'),
    ('dummy-schotter-nina', 'dummy-schotter-jonas', 'nie_zulaessig'),
    ('dummy-westerwald-uwe', 'dummy-sauerland-heinz', 'nie_gezeigt'),
}


_LOGGER_STUFE = []


def setUpModule():
    # Jedes Urteil schreibt eine INFO-Zeile (kern/urteile, Protokoll) - hier
    # Hunderte. Inhalt und Form prueft test_urteile.py; hier nur Rauschen.
    # Die alte Stufe zurueckstellen, nicht NOTSET: test_urteile prueft sie
    # (erster Lauf 25.09.2026 liess dort zwei Tests scheitern).
    lg = logging.getLogger('ridebuddies.urteile')
    _LOGGER_STUFE.append(lg.level)
    lg.setLevel(logging.WARNING)


def tearDownModule():
    logging.getLogger('ridebuddies.urteile').setLevel(_LOGGER_STUFE.pop())


def _anlegen():
    call_command('dummies_anlegen', stdout=StringIO(), stderr=StringIO())


def _profil(name):
    return Profil.objects.select_related('nutzer').get(nutzer__username=name)


def _namen(bewertungen):
    return [b.kandidat.username for b in bewertungen]


def _abweichungen(testfall):
    """Alle Abweichungen vom Pruefblatt; prueft nebenbei, dass kein Urteil fehlt."""
    gefunden = set()
    for anker in BLATT['anker']:
        alle = matching.alle_bewertungen(_profil(anker['nutzer']), holen=True)
        for b in alle:
            testfall.assertNotIn('nogo_offen', b.ausgeschlossen,
                                 f"{anker['nutzer']} - {b.kandidat}: Urteil fehlt")
        top5 = _namen([b for b in alle if b.zulaessig][:5])
        je_name = {b.kandidat.username: b for b in alle}
        for m in anker['muss_top5']:
            if m['nutzer'] not in top5:
                gefunden.add((anker['nutzer'], m['nutzer'], 'muss_fehlt'))
        for n in anker['nie']:
            b = je_name[n['nutzer']]
            if n['nutzer'] in top5:
                gefunden.add((anker['nutzer'], n['nutzer'], 'nie_gezeigt'))
            elif b.zulaessig:
                gefunden.add((anker['nutzer'], n['nutzer'], 'nie_zulaessig'))
            else:
                testfall.assertIn(GRUND.get(n['grund'], n['grund']), b.ausgeschlossen,
                                  f"{anker['nutzer']} - {n['nutzer']}")
    return gefunden


class PruefblattJevTest(TestCase):
    """Das Pruefblatt mit der Jev-Aufzeichnung: vollstaendig."""

    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def setUp(self):
        self.anbieter = TestAnbieter(aufzeichnung=DOCS / 'ki-aufzeichnung-jev.json', streng=True)

    def test_pruefblatt_vollstaendig(self):
        with urteile.mit_anbieter(self.anbieter):
            self.assertEqual(_abweichungen(self), set())

    def test_leere_listen(self):
        with urteile.mit_anbieter(self.anbieter):
            for name in ('dummy-fern-bernd', 'dummy-fern-hanna'):
                self.assertEqual(matching.vorschlaege(_profil(name), holen=True), [], name)

    def test_freitextfaelle_kommen_aus_dem_urteil(self):
        # Heinz und Sabine bestehen alle Code-Filter - nur das KI-Urteil nimmt sie raus.
        with urteile.mit_anbieter(self.anbieter):
            for anker, kandidat in (('dummy-westerwald-uwe', 'dummy-sauerland-heinz'),
                                    ('dummy-ring-marco', 'dummy-ring-sabine')):
                a, b = _profil(anker), _profil(kandidat)
                self.assertEqual(matching.ranking.code_gruende(
                    a, b, profil_entfernung_km(a, b), harte.Beziehungen.fuer(a.nutzer)), set())
                bewertung = matching.bewerten(a, b, holen=True)
                self.assertEqual(bewertung.ausgeschlossen, {'nogo'})

    def test_kein_ausschluss_datensatz_durch_ki(self):
        vorher = list(Ausschluss.objects.values_list('pk', flat=True))
        with urteile.mit_anbieter(self.anbieter):
            _abweichungen(self)
        self.assertEqual(list(Ausschluss.objects.values_list('pk', flat=True)), vorher)
        self.assertGreater(PaarUrteil.objects.count(), 0)


class RegelAusschluesseTest(TestCase):
    """Unerwartete Regel-Ausschluesse, ueber ALLE Anker der Grundmenge - nicht
    nur die acht des Pruefblatts (Auflage nach der Gegenpruefung, 25.09.2026).

    Eine Regel darf ein Paar nur dort ausschliessen, wo das Pruefblatt eine
    entsprechende Regel nennt (`nogo_regeln`: Nina und Petra, Alkohol auf Tour).
    Anlass: Mit der Regelfassung r1 schloss Jevs Regel "Streckenfresser" gegen
    Svens No-Go "Autobahnetappen" Oliver, Kevin und Sabine aus - im Blatt steht
    davon nichts. Faellt ein Paar zusaetzlich ueber das Paarurteil heraus, ist
    es hier trotzdem gezaehlt: Gemessen wird, was die REGEL tut."""

    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def test_nur_regeln_aus_dem_pruefblatt(self):
        erlaubt = {(name, r['feld'], wert) for name, r in BLATT['nogo_regeln'].items()
                   for wert in r['verboten']}
        treffer = set()
        anbieter = TestAnbieter(aufzeichnung=DOCS / 'ki-aufzeichnung-jev.json', streng=True)
        with urteile.mit_anbieter(anbieter):
            profile = list(matching.grundmenge())
            for x, y in matching.noetige_nogo_paare(profile):
                regeln = nogo.regeln_holen(x)
                self.assertIsNotNone(regeln, x.nutzer.username)
                for feld in nogo.regel_verstoesse(regeln, y):
                    treffer.add((x.nutzer.username, feld, getattr(y, feld)))
        self.assertEqual(treffer - erlaubt, set())
        # Und die Regeln des Blatts greifen tatsaechlich (Nina gegen "erst nach
        # der Fahrt", Petra gegen "egal", sofern ein solches Gegenueber da ist).
        self.assertIn(('dummy-schotter-nina', 'alkohol_auf_tour', 'nach_der_fahrt'), treffer)
        self.assertIn(('dummy-schotter-nina', 'alkohol_auf_tour', 'egal'), treffer)

    def test_stilmerkmale_haben_keine_regeln(self):
        # r2: nur Verhaltensmerkmale (nogo.REGEL_MERKMALE, Begruendung dort).
        self.assertEqual(set(nogo.REGEL_MERKMALE), {'alkohol_auf_tour', 'schutzkleidung'})
        self.assertFalse({k.split('__')[0] for k in nogo.regel_fragen()}
                         & {'tempo', 'unterwegs_stil', 'selbsteinschaetzung', 'gruppengroesse'})


class PruefblattClaudeTest(TestCase):
    """Die Claude-Aufzeichnung: genau die erklaerten Abweichungen."""

    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def test_nur_die_erklaerten_abweichungen(self):
        anbieter = TestAnbieter(aufzeichnung=DOCS / 'ki-aufzeichnung-claude.json', streng=True)
        with urteile.mit_anbieter(anbieter):
            self.assertEqual(_abweichungen(self), ABWEICHUNGEN_CLAUDE)


class GrenzfaelleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def test_radius_wie_im_blatt(self):
        self.assertEqual(len(BLATT['grenzfaelle']), 17)
        for g in BLATT['grenzfaelle']:
            a, b = (_profil(n) for n in g['paar'])
            gruende = harte.harte_gruende(a, b, profil_entfernung_km(a, b),
                                          harte.Beziehungen.fuer(a.nutzer))
            self.assertEqual('region' in gruende, g['ergebnis'] == 'draußen', g['paar'])


def _vorgaben(konflikt=False):
    """Test-Anbieter mit festen Antworten fuer beide Bausteine."""
    stufen = [0, 0, 0, 0, 1] if konflikt else [0, 1, 0, 0, 0]
    vorgaben = {k: 0.0 for k in nogo.regel_fragen()}
    vorgaben[nogo.KENNUNG] = stufen
    return TestAnbieter(vorgaben=vorgaben)


class KostenTest(TestCase):
    """Gewichte und hart/weich aendern das Ranking ohne neue Anfrage."""

    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def test_gewichte_und_hart_weich_ohne_neue_anfrage(self):
        anbieter = _vorgaben()
        sven = _profil('dummy-schotter-sven')
        with urteile.mit_anbieter(anbieter):
            vorher = _namen(matching.vorschlaege(sven, holen=True))
            anfragen = anbieter.aufrufe
            self.assertGreater(anfragen, 0)

            # Gewichte: nur Themen zaehlen.
            nur_themen = {d: 0.0 for d in matching.GEWICHTE}
            nur_themen['themen'] = 1.0
            anders = _namen(matching.vorschlaege(sven, holen=True, gewichte=nur_themen))
            self.assertNotEqual(anders, vorher)
            self.assertEqual(anbieter.aufrufe, anfragen)

            # hart/weich: Tempo hart - nur noch "zuegig" bleibt.
            sven.gewichtung = {'tempo': 'hart'}
            sven.save()
            hart = matching.vorschlaege(sven, anzahl=20, holen=True)
            self.assertNotEqual(_namen(hart), vorher)
            self.assertTrue(all(_profil(n).tempo == 'zuegig' for n in _namen(hart)))
            self.assertEqual(anbieter.aufrufe, anfragen)

        # Und ganz ohne Anbieter (holen=False) dasselbe Ergebnis aus der Tabelle.
        with urteile.mit_anbieter(TestAnbieter(streng=True)) as leer:
            self.assertEqual(_namen(matching.vorschlaege(sven, anzahl=20)), _namen(hart))
        self.assertEqual(leer.aufrufe, 0)

    def test_geaendertes_nogo_wird_neu_beurteilt(self):
        anbieter = _vorgaben()
        uwe = _profil('dummy-westerwald-uwe')
        with urteile.mit_anbieter(anbieter):
            matching.vorschlaege(uwe, holen=True)
            anfragen = anbieter.aufrufe
            matching.vorschlaege(uwe, holen=True)
            self.assertEqual(anbieter.aufrufe, anfragen)
            uwe.nogo = 'Lange Autobahnetappen.'
            uwe.save()
            # Ohne holen: veraltet -> offen, nicht still das alte Urteil.
            self.assertTrue(any('nogo_offen' in b.ausgeschlossen
                                for b in matching.alle_bewertungen(uwe)))
            matching.vorschlaege(uwe, holen=True)
            self.assertGreater(anbieter.aufrufe, anfragen)

    def test_konflikturteil_schliesst_aus(self):
        with urteile.mit_anbieter(_vorgaben(konflikt=True)):
            # Uwe hat ein No-Go: jeder Kandidat faellt ueber das Paarurteil raus.
            self.assertEqual(matching.vorschlaege(_profil('dummy-westerwald-uwe'),
                                                  holen=True), [])


class SicherheitTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def test_neutraler_test_anbieter_zaehlt_nicht(self):
        # Voreinstellung 'test' ohne Aufzeichnung antwortet neutral - das darf
        # kein "kein Konflikt" werden.
        with urteile.mit_anbieter(TestAnbieter()):
            alle = matching.alle_bewertungen(_profil('dummy-westerwald-uwe'), holen=True)
        self.assertFalse(any(b.zulaessig for b in alle))
        self.assertEqual(PaarUrteil.objects.count() + MerkmalUrteil.objects.count(), 0)

    def test_begruendung_ohne_koordinaten_geschlecht_alter(self):
        with urteile.mit_anbieter(_vorgaben()):
            for anker in ('dummy-koeln-frank', 'dummy-frauen-anja', 'dummy-einsteiger-luca'):
                for b in matching.vorschlaege(_profil(anker), holen=True):
                    self.assertNotIn('geschlechtspraeferenz', b.begruendung)
                    self.assertNotIn('alterswunsch', b.begruendung)
                    self.assertNotIn('geschlechtspraeferenz', b.teilwerte)
                    self.assertNotIn('alterswunsch', b.teilwerte)
                    text = json.dumps(b.begruendung, ensure_ascii=False)
                    p = _profil(b.kandidat.username)
                    self.assertNotIn(str(p.breitengrad), text)
                    self.assertNotIn(str(p.laengengrad), text)
                    self.assertRegex(b.begruendung['region'],
                                     r'^(unter 5 km|etwa \d*[05] km) entfernt$')
                    # Alkohol und Schutzkleidung sind "verbunden" - nicht woertlich.
                    self.assertIn('berücksichtigt', b.begruendung['sicherheit'])
                    self.assertEqual(b.begruendung['nogo'], 'kein Konflikt mit einem No-Go')

    def test_entfernung_gerundet(self):
        self.assertEqual(matching.entfernung_text(3.6), 'unter 5 km entfernt')
        self.assertEqual(matching.entfernung_text(12.7), 'etwa 15 km entfernt')
        self.assertEqual(matching.entfernung_text(66.1), 'etwa 65 km entfernt')

    def test_verborgenes_feld_nicht_woertlich(self):
        frank, markus = _profil('dummy-koeln-frank'), _profil('dummy-koeln-markus')
        markus.feldstufen = {'fahrarten': 2}
        markus.save()
        with urteile.mit_anbieter(_vorgaben()):
            b = matching.bewerten(frank, markus, holen=True)
        self.assertNotIn('Touring', b.begruendung['fahrart'])
        self.assertIn(b.begruendung['fahrart'], ('passt gut', 'passt teilweise', 'passt kaum'))

    def test_ohne_einwilligung_kein_matching(self):
        luca = _profil('dummy-einsteiger-luca')
        mia = _profil('dummy-einsteiger-mia')
        Einwilligung.objects.filter(nutzer=mia.nutzer, art=Einwilligung.Art.KI_AUSWERTUNG) \
            .update(widerrufen_am=timezone.now())
        with urteile.mit_anbieter(_vorgaben()):
            self.assertNotIn('dummy-einsteiger-mia',
                             _namen(matching.vorschlaege(luca, holen=True)))
            with self.assertRaises(matching.KeineEinwilligung):
                matching.vorschlaege(mia, holen=True)

    def test_datensperre_echtes_konto(self):
        # Ein echtes Konto mit Einwilligung und No-Go neben Uwe: Das Urteil darf
        # nicht an den Anbieter, der Kandidat bleibt offen - nie "zulaessig".
        echt = nutzer('echt')
        Einwilligung.objects.create(nutzer=echt, art=Einwilligung.Art.KI_AUSWERTUNG, version='t')
        p = Profil.objects.get(nutzer=echt)
        uwe = _profil('dummy-westerwald-uwe')
        p.breitengrad, p.laengengrad = uwe.breitengrad, uwe.laengengrad
        p.nogo = 'Unpünktlichkeit.'
        p.save()
        anbieter = _vorgaben()
        with urteile.mit_anbieter(anbieter):
            b = matching.bewerten(uwe, p, holen=True)
        self.assertEqual(b.ausgeschlossen, {'nogo_offen'})
        # Gefragt wurde nur Uwes Regel (nur Dummy-Daten); nichts, was das echte
        # Konto betrifft, ist beim Anbieter angekommen oder gespeichert.
        self.assertEqual(anbieter.aufrufe, 1)
        self.assertFalse(PaarUrteil.objects.filter(urheber=echt).exists())
        self.assertFalse(PaarUrteil.objects.filter(gegenueber=echt).exists())
        self.assertFalse(MerkmalUrteil.objects.filter(nutzer=echt).exists())

    def test_wiedervorlage_nicht_jetzt(self):
        frank, markus = _profil('dummy-koeln-frank'), _profil('dummy-koeln-markus')
        Vorschlag.objects.create(empfaenger=markus.nutzer, kandidat=frank.nutzer, runde=7,
                                 reaktion=Vorschlag.Reaktion.NICHT_JETZT,
                                 reagiert_am=timezone.now(),
                                 wiedervorlage_ab=timezone.localdate().replace(year=2099))
        with urteile.mit_anbieter(_vorgaben()):
            b = matching.bewerten(frank, markus, holen=True)
        self.assertIn('wiedervorlage', b.ausgeschlossen)


class ClaudeLive(TestAnbieter):
    """Test-Anbieter, der sich als Claude ausgibt - fuer "Regeln abgeschaltet"."""
    name = 'claude'


class Auflagen25Test(TestCase):
    """Auflagen der Gegenpruefung vom 25.09.2026."""

    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def test_unbekannter_anbieter_hat_keine_schwelle(self):
        with self.assertRaises(nogo.SchwelleFehlt):
            nogo.schwelle_fuer('mistral')
        with self.assertRaises(nogo.SchwelleFehlt):
            nogo.regel_schwelle_fuer('mistral')
        with self.assertRaises(nogo.SchwelleFehlt):
            nogo.schwelle_fuer('test', 'aufzeichnung:mistral/x')

    def test_abgeschaltete_regeln_werden_weder_geholt_noch_offen(self):
        anbieter = ClaudeLive(vorgaben={nogo.KENNUNG: [0, 1, 0, 0, 0]})
        uwe = _profil('dummy-westerwald-uwe')
        with urteile.mit_anbieter(anbieter):
            alle = matching.alle_bewertungen(uwe, holen=True)
        self.assertFalse(any('nogo_offen' in b.ausgeschlossen for b in alle))
        self.assertTrue(any(b.zulaessig for b in alle))
        self.assertEqual(MerkmalUrteil.objects.count(), 0)
        # Jede Anfrage war ein Paarurteil (1 Frage), keine Regelanfrage.
        self.assertEqual(anbieter.fragen, anbieter.aufrufe)

    def test_bewerten_prueft_auch_den_anker(self):
        luca, mia = _profil('dummy-einsteiger-luca'), _profil('dummy-einsteiger-mia')
        Einwilligung.objects.filter(nutzer=luca.nutzer, art=Einwilligung.Art.KI_AUSWERTUNG) \
            .update(widerrufen_am=timezone.now())
        with self.assertRaises(matching.KeineEinwilligung):
            matching.bewerten(luca, mia)


class KommandoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _anlegen()

    def _lauf(self, *args):
        aus = StringIO()
        call_command(*args, stdout=aus, stderr=StringIO())
        return aus.getvalue()

    def test_offline_aus_aufzeichnung_und_vorschlaege(self):
        aus = self._lauf('matching_urteile', '--anbieter', 'test', '--aufzeichnung',
                         str(DOCS / 'ki-aufzeichnung-jev.json'))
        self.assertIn('0 Fehler', aus)
        aus = self._lauf('vorschlaege', 'dummy-westerwald-uwe')
        self.assertIn('1. dummy-westerwald-joerg', aus)
        self.assertNotIn('sauerland-heinz', aus)
        self.assertIn('keine Vorschläge', self._lauf('vorschlaege', 'dummy-fern-bernd'))

    def test_nur_zaehlen_fragt_niemanden(self):
        with urteile.mit_anbieter(TestAnbieter(streng=True)) as a:
            aus = self._lauf('matching_urteile', '--nur-zaehlen')
        self.assertIn('Personen mit No-Go', aus)
        self.assertEqual(a.aufrufe, 0)

    def test_aufzeichnung_ohne_zustand(self):
        # Die Aufzeichnungen im Repo tragen nur Hash und Urteil (aufzeichnung.py).
        for anbieter in ('jev', 'claude'):
            text = (DOCS / f'ki-aufzeichnung-{anbieter}.json').read_text(encoding='utf-8')
            for wort in ('dummy-', 'Hotel', 'Zelt', 'Alkohol', 'no_go', 'Landstraße'):
                self.assertNotIn(wort, text, anbieter)
