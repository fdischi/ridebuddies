"""
Tests fuer kern/urteile (Karte TASK-120.12): Datensperre, Protokoll ohne
Personendaten, die drei Urteilsformen, Jev/Claude gegen nachgebaute HTTP-
Antworten, Test-Anbieter und Aufzeichnung, manage.py ki_vergleich.

KEIN TEST GEHT INS NETZ. Jev und Claude laufen gegen ein ersetztes
urllib.request.urlopen, das die Anfrage mitschneidet und eine Antwort in der
Form der jeweiligen Doku liefert (Jev: api.md vom 23.09.2026; Claude:
Messages API, tool_use-Block). Ob die echten Dienste genau so antworten, ist
damit NICHT belegt - das zeigt erst der Live-Lauf (TASK-120.11).
"""
import contextlib
import datetime
import email.message
import io
import json
import logging
import sys
import os
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from kern import urteile
from kern.models import Einwilligung, Profil
from kern.urteile import formen, netz
from kern.urteile.aufzeichnung import Aufzeichner, TestAnbieter
from kern.urteile.claude import ClaudeAnbieter
from kern.urteile.jev import JevAnbieter
from ridebuddies.settings import _ki_freigabe, _ki_zeitlimit

Nutzer = get_user_model()

NOGO_TEXT = 'Jeden Abend Hotel – ich schlafe gern im Zelt, geheimes Merkmal 7Q'
ECHTE_PK = 987654
DUMMY_PK = 876543
FRAGE = urteile.Noul('Verletzt B das No-Go von A?')

# Fuer Tests des Antwortformats: ein Aufruf ohne Personendaten, ausdruecklich.
OHNE = {'betrifft': [], 'ohne_personen': True}

JEV_SCHLUESSEL = 'jev-geheim-123'
CLAUDE_SCHLUESSEL = 'sk-ant-geheim-456'


def dummy(name='dummy-test-a', einwilligung=True, **extra):
    n = Nutzer.objects.create_user(username=name, email=f'{name}@example.invalid',
                                   password=None, **extra)
    if einwilligung:
        Einwilligung.objects.create(nutzer=n, art=Einwilligung.Art.KI_AUSWERTUNG, version='t')
    return n


def konto(name, mail, einwilligung=True, **extra):
    n = Nutzer.objects.create_user(username=name, email=mail, password=None, **extra)
    if einwilligung:
        Einwilligung.objects.create(nutzer=n, art=Einwilligung.Art.KI_AUSWERTUNG, version='t')
    return n


# ---------------------------------------------------------------------------
# Nachgebautes HTTP
# ---------------------------------------------------------------------------

class _Antwort:
    def __init__(self, daten):
        self._roh = json.dumps(daten).encode()

    def read(self):
        return self._roh

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_fehler(status, koerper=b'', retry_after=None):
    kopf = email.message.Message()
    if retry_after is not None:
        kopf['Retry-After'] = str(retry_after)
    return netz.urllib.error.HTTPError('https://x', status, 'Fehler', kopf, io.BytesIO(koerper))


class FalschesNetz:
    """Ersetzt urlopen: schneidet jede Anfrage mit, antwortet der Reihe nach
    mit den Eintraegen aus `antworten` (dict = JSON-Antwort, Exception = wird
    geworfen)."""

    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.anfragen = []

    def __call__(self, anfrage, timeout=None):
        self.anfragen.append(anfrage)
        naechste = self.antworten.pop(0)
        if isinstance(naechste, BaseException):
            raise naechste
        return _Antwort(naechste)

    def koerper(self, i=-1):
        return json.loads(self.anfragen[i].data.decode())

    def kopf(self, name, i=-1):
        # urllib normalisiert Kopfnamen auf "Xxxx-yyy".
        return self.anfragen[i].get_header(name.capitalize())


@contextlib.contextmanager
def netz_ersetzt(*antworten):
    falsch = FalschesNetz(*antworten)
    with mock.patch.object(netz.urllib.request, 'urlopen', falsch):
        yield falsch


@contextlib.contextmanager
def schluessel(**werte):
    """Setzt/entfernt Schluessel-Variablen fuer die Dauer des Blocks."""
    namen = ['RIDEBUDDIES_JEV_SCHLUESSEL', 'RIDEBUDDIES_ANTHROPIC_SCHLUESSEL',
             'RIDEBUDDIES_JEV_SCHLUESSEL_DATEI', 'RIDEBUDDIES_ANTHROPIC_SCHLUESSEL_DATEI']
    with mock.patch.dict(os.environ):
        for n in namen:
            os.environ.pop(n, None)
        os.environ.update(werte)
        yield


JEV_ANTWORT = {
    'model': 'jev-1.13.0',
    'answers': {
        'nogo_konflikt': {'type': 'noul', 'noul': 0.95},
        'abteilung': {'type': 'choice', 'choice': 'billing',
                      'probabilities': {'billing': 0.88, 'technical': 0.12, 'sales': 0.0},
                      'confidence': 0.81},
        'aerger': {'type': 'score', 'score': 1.05,
                   'legend': {'0': 'Calm', '1': 'Frustrated', '2': 'Very angry'},
                   'probabilities': {'0': 0.0, '1': 0.95, '2': 0.05}, 'confidence': 0.92},
    },
    'usage': {'input_tokens': 296, 'output_tokens': 20},
}

DREI_FRAGEN = {
    'nogo_konflikt': urteile.Noul('Does this convey urgency?', wenn_ja='Explicitly time-sensitive'),
    'abteilung': urteile.Auswahl('Which team?', {'billing': 'Payments', 'technical': None,
                                                 'sales': 'Pricing'}),
    'aerger': urteile.Stufenwert('How frustrated?', ['Calm', 'Frustrated', 'Very angry']),
}


def claude_antwort(eingabe, modell='claude-haiku-4-5-20251001'):
    return {'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'model': modell,
            'content': [{'type': 'tool_use', 'id': 'toolu_1', 'name': 'urteil_abgeben',
                         'input': eingabe}],
            'stop_reason': 'tool_use',
            'usage': {'input_tokens': 512, 'output_tokens': 64}}


# ---------------------------------------------------------------------------
# Datensperre
# ---------------------------------------------------------------------------

class DatensperreTests(TestCase):
    """Entscheidung Fabians 23.09.2026: nur Dummies und das freigegebene
    Konto, beides nur mit aktiver KI-Einwilligung. Jeder Test zaehlt die
    Anbieteraufrufe - bei Sperre muessen es 0 sein."""

    def setUp(self):
        self.anbieter = TestAnbieter()

    def _frag(self, betrifft, **kw):
        # assertLogs faengt die Zeile ab (sonst landet sie per lastResort auf
        # stderr) und belegt nebenbei, dass jeder Aufruf protokolliert.
        with urteile.mit_anbieter(self.anbieter), \
                self.assertLogs('ridebuddies.urteile', 'DEBUG'):
            return urteile.beurteilen('Zustand', FRAGE, kennung='nogo_konflikt',
                                      betrifft=betrifft, **kw)

    def assertGesperrt(self, betrifft, grund=None):
        with self.assertRaises(urteile.DatensperreVerletzt) as cm:
            self._frag(betrifft)
        self.assertEqual(self.anbieter.aufrufe, 0)
        if grund:
            self.assertIn(grund, cm.exception.gruende)
        return cm.exception

    def test_dummy_mit_einwilligung_kommt_durch(self):
        u = self._frag([dummy()])
        self.assertEqual(self.anbieter.aufrufe, 1)
        self.assertIsInstance(u, urteile.NoulUrteil)

    def test_echtes_konto_mit_einwilligung_gesperrt(self):
        self.assertGesperrt([konto('hans', 'hans@web.de')], 'kein_dummy_und_nicht_freigegeben')

    def test_dummy_ohne_einwilligung_gesperrt(self):
        self.assertGesperrt([dummy(einwilligung=False)], 'keine_ki_einwilligung')

    def test_dummy_mit_widerrufener_einwilligung_gesperrt(self):
        n = dummy()
        Einwilligung.objects.filter(nutzer=n).update(widerrufen_am=timezone.now())
        self.assertGesperrt([n], 'keine_ki_einwilligung')

    def test_einwilligung_in_der_zukunft_zaehlt_noch_nicht(self):
        n = dummy(einwilligung=False)
        Einwilligung.objects.create(nutzer=n, art=Einwilligung.Art.KI_AUSWERTUNG, version='t',
                                    erteilt_am=timezone.now() + datetime.timedelta(hours=1))
        self.assertGesperrt([n], 'keine_ki_einwilligung')

    def test_einwilligung_seit_eben_zaehlt(self):
        n = dummy(einwilligung=False)
        Einwilligung.objects.create(nutzer=n, art=Einwilligung.Art.KI_AUSWERTUNG, version='t',
                                    erteilt_am=timezone.now() - datetime.timedelta(seconds=1))
        self._frag([n])
        self.assertEqual(self.anbieter.aufrufe, 1)

    def test_andere_einwilligungsart_zaehlt_nicht(self):
        n = dummy(einwilligung=False)
        Einwilligung.objects.create(nutzer=n, art=Einwilligung.Art.DATENSCHUTZ, version='t')
        self.assertGesperrt([n], 'keine_ki_einwilligung')

    def test_dummy_praefix_mit_echter_mail_gesperrt(self):
        self.assertGesperrt([konto('dummy-hans', 'hans@web.de')],
                            'kein_dummy_und_nicht_freigegeben')

    def test_dummy_mail_ohne_praefix_gesperrt(self):
        self.assertGesperrt([konto('hans', 'hans@example.invalid')],
                            'kein_dummy_und_nicht_freigegeben')

    def test_praefix_in_grossbuchstaben_gesperrt(self):
        # SQLite-LIKE ist ohne Gross/Klein - ist_dummy_q() allein liesse das durch.
        self.assertGesperrt([konto('Dummy-hans', 'dummy-hans@example.invalid')],
                            'kein_dummy_und_nicht_freigegeben')

    def test_gemischte_liste_gesperrt(self):
        fehler = self.assertGesperrt([dummy(), konto('hans', 'hans@web.de')])
        self.assertEqual(fehler.betroffene, 2)
        self.assertEqual(fehler.gruende, {'kein_dummy_und_nicht_freigegeben': 1})

    def test_im_speicher_umbenannt_gesperrt(self):
        n = konto('hans', 'hans@web.de')
        n.username, n.email = 'dummy-hans', 'dummy-hans@example.invalid'   # nicht gespeichert
        self.assertGesperrt([n], 'kein_dummy_und_nicht_freigegeben')

    def test_ungespeichert_gesperrt(self):
        n = Nutzer(username='dummy-neu', email='dummy-neu@example.invalid')
        self.assertGesperrt([n], 'nicht_gespeichert')

    def test_leere_liste_gesperrt(self):
        self.assertGesperrt([], 'keine_betroffenen_benannt')

    def test_ohne_personen_ausdruecklich(self):
        self._frag([], ohne_personen=True)
        self.assertEqual(self.anbieter.aufrufe, 1)

    def test_ohne_personen_mit_liste_ist_widerspruch(self):
        with self.assertRaises(ValueError):
            self._frag([dummy()], ohne_personen=True)
        self.assertEqual(self.anbieter.aufrufe, 0)

    def test_nackte_id_ist_programmierfehler(self):
        with self.assertRaises(TypeError):
            self._frag([dummy().pk])
        self.assertEqual(self.anbieter.aufrufe, 0)

    def test_betrifft_ist_pflicht(self):
        with self.assertRaises(TypeError):
            urteile.beurteilen('Zustand', FRAGE, kennung='nogo_konflikt')

    @override_settings(RIDEBUDDIES_KI_FREIGABE=('fabian', 'fabian@beispiel.de'))
    def test_freigabe_korrekt_mit_einwilligung_kommt_durch(self):
        self._frag([konto('fabian', 'Fabian@Beispiel.DE')])   # E-Mail ohne Gross/Klein
        self.assertEqual(self.anbieter.aufrufe, 1)

    @override_settings(RIDEBUDDIES_KI_FREIGABE=('fabian', 'fabian@beispiel.de'))
    def test_freigabe_zusammen_mit_dummy(self):
        self._frag([konto('fabian', 'fabian@beispiel.de'), dummy()])
        self.assertEqual(self.anbieter.aufrufe, 1)

    @override_settings(RIDEBUDDIES_KI_FREIGABE=('fabian', 'fabian@beispiel.de'))
    def test_freigabe_name_passt_mail_nicht(self):
        self.assertGesperrt([konto('fabian', 'fabian@anders.de')],
                            'kein_dummy_und_nicht_freigegeben')

    @override_settings(RIDEBUDDIES_KI_FREIGABE=('fabian', 'fabian@beispiel.de'))
    def test_freigabe_mail_passt_name_nicht(self):
        self.assertGesperrt([konto('fabian2', 'fabian@beispiel.de')],
                            'kein_dummy_und_nicht_freigegeben')

    @override_settings(RIDEBUDDIES_KI_FREIGABE=('fabian', 'fabian@beispiel.de'))
    def test_freigabe_ohne_einwilligung_gesperrt(self):
        self.assertGesperrt([konto('fabian', 'fabian@beispiel.de', einwilligung=False)],
                            'keine_ki_einwilligung')

    def test_ohne_freigabe_ist_fabian_ein_echtes_konto(self):
        self.assertGesperrt([konto('fabian', 'fabian@beispiel.de')],
                            'kein_dummy_und_nicht_freigegeben')

    def test_sperre_haelt_auch_echten_anbieter_vom_netz_fern(self):
        """Nicht nur der Test-Anbieter: Jev bekommt bei Sperre keine HTTP-Anfrage,
        auch mit Schluessel."""
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                netz_ersetzt(JEV_ANTWORT) as falsch, \
                urteile.mit_anbieter(JevAnbieter()):
            with self.assertRaises(urteile.DatensperreVerletzt), \
                    self.assertLogs('ridebuddies.urteile', 'WARNING'):
                urteile.beurteilen('Zustand', FRAGE, kennung='nogo_konflikt',
                                   betrifft=[konto('hans', 'hans@web.de')])
        self.assertEqual(falsch.anfragen, [])

    @override_settings(RIDEBUDDIES_KI_ANBIETER='jev')
    def test_direkter_aufruf_am_einstieg_vorbei_gesperrt(self):
        """Auflage 24.09.2026: urteiler().beantworten(...) direkt, mit echtem
        Konto und gesetztem Schluessel -> Sperre, keine einzige Netzanfrage."""
        anbieter = urteile.urteiler()
        self.assertIsInstance(anbieter, JevAnbieter)
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                netz_ersetzt(JEV_ANTWORT) as falsch, \
                self.assertLogs('ridebuddies.urteile', 'WARNING') as cm:
            with self.assertRaises(urteile.DatensperreVerletzt):
                anbieter.beantworten('Zustand', {'nogo_konflikt': FRAGE},
                                     betrifft=[konto('hans', 'hans@web.de')])
        self.assertEqual(falsch.anfragen, [])
        self.assertIn('urteil gesperrt anbieter=jev direkt betroffene=1', cm.output[0])

    def test_direkter_aufruf_ohne_betrifft_ist_fehler(self):
        with self.assertRaises(TypeError):
            urteile.urteiler().beantworten('Zustand', {'nogo_konflikt': FRAGE})

    def test_direkter_aufruf_test_anbieter_zaehlt_nicht(self):
        with self.assertRaises(urteile.DatensperreVerletzt), \
                self.assertLogs('ridebuddies.urteile', 'WARNING'):
            self.anbieter.beantworten('Zustand', {'f': FRAGE},
                                      betrifft=[dummy(einwilligung=False)])
        self.assertEqual((self.anbieter.aufrufe, self.anbieter.fragen), (0, 0))

    def test_aufzeichner_direkt_gesperrt(self):
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / 'a.json'
            aufzeichner = Aufzeichner(self.anbieter, pfad)
            with self.assertRaises(urteile.DatensperreVerletzt), \
                    self.assertLogs('ridebuddies.urteile', 'WARNING'):
                aufzeichner.beantworten('Zustand', {'f': FRAGE},
                                        betrifft=[konto('hans', 'hans@web.de')])
            self.assertFalse(pfad.exists())
        self.assertEqual(self.anbieter.aufrufe, 0)

    def test_dummy_direkt_kommt_durch(self):
        self.anbieter.beantworten('Zustand', {'f': FRAGE}, betrifft=[dummy()])
        self.assertEqual(self.anbieter.aufrufe, 1)

    def test_sperre_gilt_auch_ohne_mit_anbieter(self):
        """Der Anbieter aus der Einstellung (Voreinstellung test) steht hinter
        derselben Sperre."""
        with self.assertRaises(urteile.DatensperreVerletzt), \
                self.assertLogs('ridebuddies.urteile', 'WARNING'):
            urteile.beurteilen('Zustand', FRAGE, kennung='nogo_konflikt',
                               betrifft=[konto('hans', 'hans@web.de')])

    def test_meldung_ohne_personendaten(self):
        n = konto('hans-meier', 'hans.meier@web.de', id=ECHTE_PK)
        fehler = self.assertGesperrt([n])
        text = str(fehler) + repr(fehler.gruende)
        for verboten in ('hans', 'meier', str(ECHTE_PK)):
            self.assertNotIn(verboten, text.lower())


class FreigabeEinstellungTests(SimpleTestCase):

    def test_leer_heisst_niemand(self):
        self.assertIsNone(_ki_freigabe(''))
        self.assertIsNone(_ki_freigabe('  '))

    def test_genau_ein_konto_email_klein(self):
        self.assertEqual(_ki_freigabe(' fabian : F@Beispiel.de '), ('fabian', 'f@beispiel.de'))

    def test_liste_bricht_ab(self):
        # Fabian hat genau EIN Konto gewaehlt - eine Liste ist ein Fehler, auch
        # mit nur einem Eintrag und Komma dahinter.
        for roh in ('fabian:f@x.de,zweit:z@x.de', 'fabian:f@x.de,'):
            with self.assertRaises(ImproperlyConfigured) as cm:
                _ki_freigabe(roh)
            self.assertNotIn('fabian', str(cm.exception))
            self.assertNotIn('f@x.de', str(cm.exception))

    def test_kaputter_eintrag_bricht_ab_ohne_wert_zu_nennen(self):
        for roh in ('fabian', 'fabian:', ':f@x.de', 'fabian:keine-mail', 'fabian:f@x.de:mehr'):
            with self.assertRaises(ImproperlyConfigured) as cm:
                _ki_freigabe(roh)
            self.assertNotIn('fabian', str(cm.exception))


class ZeitlimitEinstellungTests(SimpleTestCase):

    def test_gueltig(self):
        self.assertEqual(_ki_zeitlimit('30'), 30.0)
        self.assertEqual(_ki_zeitlimit('2.5'), 2.5)

    def test_ungueltig_bricht_ab(self):
        for roh in ('abc', '', '0', '-5', '601', 'nan', 'inf'):
            with self.assertRaises(ImproperlyConfigured, msg=roh):
                _ki_zeitlimit(roh)


# ---------------------------------------------------------------------------
# Protokoll ohne Personendaten
# ---------------------------------------------------------------------------

class _Mitschnitt(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
        self.output = []

    def emit(self, record):
        # format() haengt einen Traceback (exc_info) mit an - auch der zaehlt.
        self.output.append(self.format(record))

    @property
    def urteile(self):
        return [z for z in self.output if ':ridebuddies.urteile:' in z]


@contextlib.contextmanager
def alles_mitschneiden():
    """Schneidet JEDE Protokollzeile mit, egal von welchem Logger: Wurzel und
    alle bekannten Logger bekommen fuer die Dauer des Blocks nur diesen einen
    Handler, Stufe DEBUG und propagate=False (so zaehlt jede Zeile genau
    einmal). Danach ist alles wie vorher. Anders als assertLogs auf der
    Wurzel sieht das auch Logger mit propagate=False, und es schreibt nichts
    auf stderr (keine INFO-Zeilen in der Testausgabe)."""
    mitschnitt = _Mitschnitt()
    wurzel = logging.getLogger()
    logger = [wurzel] + [lg for lg in logging.Logger.manager.loggerDict.values()
                         if isinstance(lg, logging.Logger)]
    vorher = [(lg, lg.handlers[:], lg.level, lg.propagate, lg.disabled) for lg in logger]
    try:
        for lg in logger:
            lg.handlers = [mitschnitt]
            lg.setLevel(logging.DEBUG)
            lg.disabled = False
            if lg is not wurzel:
                lg.propagate = False
        yield mitschnitt
    finally:
        for lg, handler, stufe, propagate, disabled in vorher:
            lg.handlers = handler
            lg.setLevel(stufe)
            lg.propagate = propagate
            lg.disabled = disabled


class ProtokollEinrichtungTests(SimpleTestCase):
    """Fabian, 24.09.2026: Protokoll ins Journal - ridebuddies.urteile ab INFO
    auf stderr, eigenstaendig (propagate=False)."""

    def test_logger_wie_entschieden(self):
        lg = logging.getLogger('ridebuddies.urteile')
        self.assertFalse(lg.propagate)
        self.assertEqual(lg.level, logging.INFO)
        self.assertEqual(len(lg.handlers), 1)
        self.assertIsInstance(lg.handlers[0], logging.StreamHandler)
        self.assertIs(lg.handlers[0].stream, sys.stderr)

    def test_djangos_protokollierung_unberuehrt(self):
        # disable_existing_loggers=False: Djangos Logger bleiben eingeschaltet.
        self.assertFalse(logging.getLogger('django').disabled)
        self.assertTrue(logging.getLogger('django').handlers)

    def test_mitschnitt_sieht_auch_logger_ohne_propagate(self):
        eigen = logging.getLogger('ridebuddies.test.abgekoppelt')
        eigen.propagate = False
        with alles_mitschneiden() as cm:
            eigen.debug('abgekoppelt')
            logging.getLogger('ridebuddies.urteile').debug('urteile-debug')
            logging.getLogger('irgendwas.neu').info('neu')
        self.assertEqual(len(cm.output), 3)
        self.assertEqual(cm.urteile, ['DEBUG:ridebuddies.urteile:urteile-debug'])
        self.assertFalse(eigen.propagate)                        # wiederhergestellt
        self.assertEqual(logging.getLogger('ridebuddies.urteile').level, logging.INFO)



class ProtokollTests(TestCase):
    """Kriterium #2: Profiltext, Nutzername und Klartext-ID tauchen in keiner
    Protokollzeile auf - bei Erfolg, bei Sperre und bei Anbieterfehler.
    Mitgeschnitten wird mit alles_mitschneiden(): JEDER Logger auf DEBUG,
    auch solche mit propagate=False - seit dem 24.09.2026 ist
    ridebuddies.urteile selbst einer (LOGGING in settings.py), und ein
    assertLogs auf dem Wurzel-Logger saehe seine Zeilen nicht mehr."""

    def setUp(self):
        self.echt = konto('hans-meier', 'hans.meier@web.de', id=ECHTE_PK)
        self.dummy = dummy('dummy-geheim-paul', id=DUMMY_PK)
        for n in (self.echt, self.dummy):
            Profil.objects.filter(nutzer=n).update(nogo=NOGO_TEXT)
        self.zustand = {'a': {'nogo': NOGO_TEXT, 'name': self.dummy.username}}

    def assertSauber(self, zeilen):
        text = '\n'.join(zeilen)
        self.assertTrue(text, 'es wurde gar nichts protokolliert')
        for verboten in (NOGO_TEXT, 'geheimes Merkmal', 'Zelt', 'hans', 'meier', 'geheim-paul',
                         '@web.de', '@example.invalid', 'Verletzt B'):
            self.assertNotIn(verboten, text)
        for pk in (ECHTE_PK, DUMMY_PK):
            self.assertIsNone(re.search(rf'\b{pk}\b', text), f'pk {pk} im Protokoll')
        self.assertNotRegex(text, r'\b(pk|id|nutzer_id|user_id)=')

    def test_erfolg(self):
        with alles_mitschneiden() as cm, urteile.mit_anbieter(TestAnbieter()):
            urteile.beurteilen(self.zustand, FRAGE, kennung='nogo_konflikt',
                               betrifft=[self.dummy])
        self.assertSauber(cm.output)
        self.assertIn('urteil ok anbieter=test modell=neutral kennung=nogo_konflikt form=noul '
                      'betroffene=1', cm.urteile[-1])
        self.assertRegex(cm.urteile[-1], r'dauer_ms=\d+ tokens_ein=0 tokens_aus=0$')

    def test_sperre(self):
        with alles_mitschneiden() as cm, urteile.mit_anbieter(TestAnbieter()):
            with self.assertRaises(urteile.DatensperreVerletzt) as fehler:
                urteile.beurteilen(self.zustand, FRAGE, kennung='nogo_konflikt',
                                   betrifft=[self.dummy, self.echt])
        self.assertSauber(cm.output + [str(fehler.exception)])
        self.assertIn('urteil gesperrt kennung=nogo_konflikt form=noul betroffene=2 '
                      'gruende=kein_dummy_und_nicht_freigegeben:1', cm.urteile[-1])

    def test_anbieterfehler_mit_zustand_im_fehlerkoerper(self):
        """Ein 422 von Jev nennt das beanstandete Feld - und kann dabei den
        Zustand wiederholen. Weder Protokoll noch Ausnahme duerfen ihn tragen."""
        koerper = json.dumps({'detail': f'bad state: {NOGO_TEXT} hans-meier'}).encode()
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                netz_ersetzt(_http_fehler(422, koerper)), \
                alles_mitschneiden() as cm, urteile.mit_anbieter(JevAnbieter()):
            with self.assertRaises(urteile.AnbieterFehler) as fehler:
                urteile.beurteilen(self.zustand, FRAGE, kennung='nogo_konflikt',
                                   betrifft=[self.dummy])
        self.assertSauber(cm.output + [str(fehler.exception)])
        self.assertIn('art=http_422', cm.urteile[-1])
        self.assertNotIn(JEV_SCHLUESSEL, '\n'.join(cm.output))

    def test_fehlender_schluessel(self):
        with schluessel(), alles_mitschneiden() as cm, \
                urteile.mit_anbieter(ClaudeAnbieter()):
            with self.assertRaises(urteile.SchluesselFehlt):
                urteile.beurteilen(self.zustand, FRAGE, kennung='nogo_konflikt',
                                   betrifft=[self.dummy])
        self.assertSauber(cm.output)
        self.assertIn('anbieter=claude', cm.urteile[-1])
        self.assertIn('art=schluessel_fehlt', cm.urteile[-1])

    def test_unerwarteter_fehler_nur_klassenname(self):
        def platzt(zustand, frage):
            raise ValueError(f'kaputt bei {NOGO_TEXT} von hans-meier')
        anbieter = TestAnbieter(vorgaben={'nogo_konflikt': platzt})
        with alles_mitschneiden() as cm, urteile.mit_anbieter(anbieter):
            with self.assertRaises(ValueError):
                urteile.beurteilen(self.zustand, FRAGE, kennung='nogo_konflikt',
                                   betrifft=[self.dummy])
        self.assertSauber(cm.output)
        self.assertIn('art=intern:ValueError', cm.urteile[-1])

    def test_freitext_als_kennung_abgelehnt(self):
        with urteile.mit_anbieter(TestAnbieter()) as anbieter:
            with self.assertRaises(ValueError) as fehler:
                urteile.beurteilen(self.zustand, FRAGE, kennung=NOGO_TEXT,
                                   betrifft=[self.dummy])
        self.assertNotIn('Zelt', str(fehler.exception))
        self.assertEqual(anbieter.aufrufe, 0)


# ---------------------------------------------------------------------------
# Urteilsformen
# ---------------------------------------------------------------------------

class FormenTests(SimpleTestCase):

    def test_vertrauen_wie_jev_doku(self):
        # confidence.md: (n * max - 1) / (n - 1); Doku-Beispiel Stufen 0/0,95/0,05 -> 0,92.
        self.assertAlmostEqual(formen.vertrauen_aus([0.0, 0.95, 0.05]), 0.925)
        self.assertEqual(formen.vertrauen_aus([1 / 3] * 3), 0.0)
        self.assertEqual(formen.vertrauen_aus([1.0, 0.0]), 1.0)

    def test_noul_vertrauen_berechnet(self):
        for p, v in ((0.5, 0.0), (0.95, 0.9), (0.1, 0.8), (1.0, 1.0)):
            u = formen.urteil_aus_verteilung(urteile.Noul('?'), p, anbieter='x', modell='m')
            self.assertAlmostEqual(u.vertrauen, v)
            self.assertEqual(u.vertrauen_quelle, 'berechnet')
            self.assertAlmostEqual(u.wahrscheinlichkeiten['nein'], 1 - p)

    def test_auswahl_normiert_und_gleichstand_erste_option(self):
        frage = urteile.Auswahl('?', {'b': None, 'a': None, 'c': None})
        u = formen.urteil_aus_verteilung(frage, {'b': 2, 'a': 2}, anbieter='x', modell='m')
        self.assertEqual(u.wert, 'b')
        self.assertEqual(u.wahrscheinlichkeiten, {'b': 0.5, 'a': 0.5, 'c': 0.0})
        self.assertAlmostEqual(u.vertrauen, 0.25)

    def test_stufenwert_gewichtet(self):
        frage = urteile.Stufenwert('?', ['a', 'b', 'c'])
        u = formen.urteil_aus_verteilung(frage, [0.0, 0.95, 0.05], anbieter='x', modell='m')
        self.assertAlmostEqual(u.wert, 1.05)
        self.assertEqual(u.legende, {'0': 'a', '1': 'b', '2': 'c'})

    def test_grenzen_der_formen(self):
        with self.assertRaises(ValueError):
            urteile.Stufenwert('?', ['nur eine'])
        with self.assertRaises(ValueError):
            urteile.Stufenwert('?', [str(i) for i in range(11)])
        with self.assertRaises(ValueError):
            urteile.Auswahl('?', {'nur': None})

    def test_unbrauchbare_verteilungen(self):
        for frage, v in ((urteile.Noul('?'), 1.5), (urteile.Noul('?'), 'ja'),
                         (urteile.Noul('?'), True),
                         (urteile.Auswahl('?', {'a': None, 'b': None}), {'z': 1}),
                         (urteile.Auswahl('?', {'a': None, 'b': None}), {'a': 0, 'b': 0}),
                         (urteile.Stufenwert('?', ['a', 'b']), [1.0])):
            with self.assertRaises(urteile.AnbieterFehler):
                formen.urteil_aus_verteilung(frage, v, anbieter='x', modell='m')

    def test_schluessel_haengt_nicht_an_der_kennung(self):
        a = formen.frage_schluessel({'x': 1}, urteile.Noul('?'))
        self.assertEqual(a, formen.frage_schluessel({'x': 1}, urteile.Noul('?')))
        self.assertNotEqual(a, formen.frage_schluessel({'x': 2}, urteile.Noul('?')))


# ---------------------------------------------------------------------------
# Jev
# ---------------------------------------------------------------------------

class JevTests(SimpleTestCase):

    def test_anfrage_und_antwort_wie_doku(self):
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                netz_ersetzt(JEV_ANTWORT) as falsch:
            erg = JevAnbieter().beantworten('Help! My payouts have been failing.', DREI_FRAGEN,
                                            **OHNE)
        anfrage = falsch.anfragen[0]
        self.assertEqual(anfrage.full_url, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(anfrage.get_method(), 'POST')
        self.assertEqual(falsch.kopf('authorization'), f'Bearer {JEV_SCHLUESSEL}')
        self.assertEqual(falsch.koerper(), {
            'state': 'Help! My payouts have been failing.', 'model': 'jev-latest',
            'questions': {
                'nogo_konflikt': {'type': 'noul', 'instructions': 'Does this convey urgency?',
                                  'criteria': {'true': 'Explicitly time-sensitive'}},
                'abteilung': {'type': 'choice', 'instructions': 'Which team?',
                              'criteria': {'billing': 'Payments', 'technical': None,
                                           'sales': 'Pricing'}},
                'aerger': {'type': 'score', 'instructions': 'How frustrated?',
                           'criteria': ['Calm', 'Frustrated', 'Very angry']}}})

        noul, wahl, stufe = erg['nogo_konflikt'], erg['abteilung'], erg['aerger']
        self.assertIsInstance(noul, urteile.NoulUrteil)
        self.assertEqual((noul.wert, noul.vertrauen_quelle), (0.95, 'berechnet'))
        self.assertAlmostEqual(noul.vertrauen, 0.9)
        self.assertEqual((wahl.wert, wahl.vertrauen, wahl.vertrauen_quelle),
                         ('billing', 0.81, 'anbieter'))
        self.assertEqual((stufe.wert, stufe.vertrauen), (1.05, 0.92))
        self.assertEqual(stufe.legende['2'], 'Very angry')
        for u in erg.values():
            self.assertEqual((u.anbieter, u.modell, u.tokens_ein, u.tokens_aus),
                             ('jev', 'jev-1.13.0', 296, 20))

    def test_ohne_schluessel_kein_aufruf(self):
        with schluessel(), netz_ersetzt() as falsch:
            with self.assertRaises(urteile.SchluesselFehlt) as cm:
                JevAnbieter().beantworten('x', {'f': FRAGE}, **OHNE)
        self.assertEqual(falsch.anfragen, [])
        self.assertIn('RIDEBUDDIES_JEV_SCHLUESSEL', str(cm.exception))

    def test_schluessel_aus_datei(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / 'jev'
            datei.write_text(f'{JEV_SCHLUESSEL}\nzweite Zeile\n')
            with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL_DATEI=str(datei)), \
                    netz_ersetzt({'model': 'jev-1', 'answers': {'f': {'type': 'noul',
                                                                      'noul': 0.2}}}) as falsch:
                JevAnbieter().beantworten('x', {'f': FRAGE}, **OHNE)
        self.assertEqual(falsch.kopf('authorization'), f'Bearer {JEV_SCHLUESSEL}')

    def test_429_wird_wiederholt(self):
        schlaf = []
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                netz_ersetzt(_http_fehler(429, retry_after=3), _http_fehler(529),
                             JEV_ANTWORT) as falsch:
            erg = JevAnbieter(schlafen=schlaf.append).beantworten('x', DREI_FRAGEN, **OHNE)
        self.assertEqual(len(falsch.anfragen), 3)
        self.assertEqual(schlaf, [3.0, 2])
        self.assertEqual(erg['abteilung'].wert, 'billing')

    def test_wiederholung_begrenzt(self):
        schlaf = []
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                netz_ersetzt(*[_http_fehler(529) for _ in range(10)]) as falsch:
            with self.assertRaises(urteile.AnbieterFehler) as cm:
                JevAnbieter(schlafen=schlaf.append).beantworten('x', {'f': FRAGE}, **OHNE)
        self.assertEqual(len(falsch.anfragen), 1 + netz.MAX_WIEDERHOLUNGEN)
        self.assertEqual((cm.exception.art, cm.exception.versuche), ('http_529', 4))
        self.assertEqual(schlaf, [1, 2, 4])

    def test_500_und_422_bei_jev_nicht_wiederholt(self):
        for status in (500, 422, 401):
            with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                    netz_ersetzt(_http_fehler(status), JEV_ANTWORT) as falsch:
                with self.assertRaises(urteile.AnbieterFehler) as cm:
                    JevAnbieter(schlafen=lambda s: None).beantworten('x', {'f': FRAGE},
                                                                     **OHNE)
            self.assertEqual(len(falsch.anfragen), 1)
            self.assertEqual(cm.exception.art, f'http_{status}')

    def test_zeitlimit(self):
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                netz_ersetzt(TimeoutError('timed out')):
            with self.assertRaises(urteile.AnbieterFehler) as cm:
                JevAnbieter().beantworten('x', {'f': FRAGE}, **OHNE)
        self.assertEqual(cm.exception.art, 'zeitlimit')

    def test_unerwartete_form(self):
        kaputt = [{'answers': {}},                                          # model fehlt
                  {'model': 'j', 'answers': {}},                            # Antwort fehlt
                  {'model': 'j', 'answers': {'f': {'type': 'choice'}}},     # falscher Typ
                  {'model': 'j', 'answers': {'f': {'type': 'noul', 'noul': 'hoch'}}}]
        for antwort in kaputt:
            with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), netz_ersetzt(antwort):
                with self.assertRaises(urteile.AnbieterFehler) as cm:
                    JevAnbieter().beantworten('x', {'f': FRAGE}, **OHNE)
            self.assertEqual(cm.exception.art, 'antwortformat')


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

class ClaudeTests(SimpleTestCase):

    def test_anfrage_erzwingt_werkzeug(self):
        eingabe = {'f1': 0.9, 'f2': {'billing': 0.6, 'technical': 0.3, 'sales': 0.2},
                   'f3': {'0': 0.1, '1': 0.7, '2': 0.2}}
        with schluessel(RIDEBUDDIES_ANTHROPIC_SCHLUESSEL=CLAUDE_SCHLUESSEL), \
                netz_ersetzt(claude_antwort(eingabe)) as falsch:
            erg = ClaudeAnbieter().beantworten({'a': {'nogo': 'Zelt'}}, DREI_FRAGEN, **OHNE)
        self.assertEqual(falsch.anfragen[0].full_url, 'https://api.anthropic.com/v1/messages')
        self.assertEqual(falsch.kopf('x-api-key'), CLAUDE_SCHLUESSEL)
        self.assertEqual(falsch.kopf('anthropic-version'), '2023-06-01')
        k = falsch.koerper()
        self.assertEqual(k['model'], 'claude-haiku-4-5')
        self.assertEqual(k['tool_choice'], {'type': 'tool', 'name': 'urteil_abgeben'})
        schema = k['tools'][0]['input_schema']
        self.assertEqual(schema['required'], ['f1', 'f2', 'f3'])
        self.assertEqual(schema['properties']['f2']['required'], ['billing', 'technical', 'sales'])
        self.assertEqual(schema['properties']['f3']['required'], ['0', '1', '2'])
        # Die Kennungen des Aufrufers gehen nicht ans Modell.
        self.assertNotIn('nogo_konflikt', json.dumps(k))
        self.assertIn('Zelt', k['messages'][0]['content'])

        self.assertEqual(erg['nogo_konflikt'].wert, 0.9)
        wahl = erg['abteilung']
        self.assertEqual(wahl.wert, 'billing')
        self.assertAlmostEqual(sum(wahl.wahrscheinlichkeiten.values()), 1.0)   # normiert
        self.assertAlmostEqual(wahl.wahrscheinlichkeiten['billing'], 0.6 / 1.1)
        self.assertAlmostEqual(erg['aerger'].wert, 1.1)
        for u in erg.values():
            self.assertEqual((u.anbieter, u.modell, u.vertrauen_quelle, u.tokens_ein),
                             ('claude', 'claude-haiku-4-5-20251001', 'berechnet', 512))

    @override_settings(RIDEBUDDIES_CLAUDE_MODELL='claude-sonnet-4-5')
    def test_modell_aus_einstellung(self):
        with schluessel(RIDEBUDDIES_ANTHROPIC_SCHLUESSEL=CLAUDE_SCHLUESSEL), \
                netz_ersetzt(claude_antwort({'f1': 0.1})) as falsch:
            ClaudeAnbieter().beantworten('x', {'f': FRAGE}, **OHNE)
        self.assertEqual(falsch.koerper()['model'], 'claude-sonnet-4-5')

    def test_5xx_wird_wiederholt(self):
        with schluessel(RIDEBUDDIES_ANTHROPIC_SCHLUESSEL=CLAUDE_SCHLUESSEL), \
                netz_ersetzt(_http_fehler(500), _http_fehler(503),
                             claude_antwort({'f1': 0.3})) as falsch:
            erg = ClaudeAnbieter(schlafen=lambda s: None).beantworten('x', {'f': FRAGE},
                                                                      **OHNE)
        self.assertEqual(len(falsch.anfragen), 3)
        self.assertEqual(erg['f'].wert, 0.3)

    def test_ohne_schluessel_kein_aufruf(self):
        with schluessel(), netz_ersetzt() as falsch:
            with self.assertRaises(urteile.SchluesselFehlt):
                ClaudeAnbieter().beantworten('x', {'f': FRAGE}, **OHNE)
        self.assertEqual(falsch.anfragen, [])

    def test_prosa_statt_werkzeug_ist_formatfehler(self):
        prosa = {'model': 'c', 'content': [{'type': 'text', 'text': 'Ich denke ja.'}],
                 'usage': {}}
        for antwort in (prosa, claude_antwort({}), claude_antwort({'f1': 2})):
            with schluessel(RIDEBUDDIES_ANTHROPIC_SCHLUESSEL=CLAUDE_SCHLUESSEL), \
                    netz_ersetzt(antwort):
                with self.assertRaises(urteile.AnbieterFehler) as cm:
                    ClaudeAnbieter().beantworten('x', {'f': FRAGE}, **OHNE)
            self.assertEqual(cm.exception.art, 'antwortformat')


# ---------------------------------------------------------------------------
# Test-Anbieter, Aufzeichnung, Einstellung
# ---------------------------------------------------------------------------

class TestAnbieterTests(SimpleTestCase):

    def test_zaehlt_und_antwortet_neutral(self):
        a = TestAnbieter()
        erg = a.beantworten('x', DREI_FRAGEN, **OHNE)
        a.beantworten('y', {'f': FRAGE}, **OHNE)
        self.assertEqual((a.aufrufe, a.fragen), (2, 4))
        self.assertEqual(erg['nogo_konflikt'].wert, 0.5)
        self.assertEqual(erg['nogo_konflikt'].vertrauen, 0.0)
        self.assertEqual(erg['abteilung'].vertrauen, 0.0)
        self.assertAlmostEqual(erg['aerger'].wert, 1.0)
        self.assertEqual(erg['aerger'].modell, 'neutral')

    def test_vorgaben(self):
        a = TestAnbieter(vorgaben={'nogo_konflikt': 0.9, 'abteilung': 'sales',
                                   'aerger': lambda zustand, frage: [0, 0, 1]})
        erg = a.beantworten('x', DREI_FRAGEN, **OHNE)
        self.assertEqual(erg['nogo_konflikt'].wert, 0.9)
        self.assertEqual((erg['abteilung'].wert, erg['abteilung'].vertrauen), ('sales', 1.0))
        self.assertEqual(erg['aerger'].wert, 2.0)
        self.assertEqual(erg['aerger'].modell, 'vorgabe')

    def test_streng_ohne_aufzeichnung(self):
        with self.assertRaises(urteile.AnbieterFehler) as cm:
            TestAnbieter(streng=True).beantworten('x', {'f': FRAGE}, **OHNE)
        self.assertEqual(cm.exception.art, 'keine_aufzeichnung')

    def test_mitschnitt_und_wiedergabe(self):
        zustand = {'a': {'nogo': NOGO_TEXT}}
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / 'unter' / 'jev.json'
            with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL), \
                    netz_ersetzt(JEV_ANTWORT):
                live = Aufzeichner(JevAnbieter(), pfad).beantworten(zustand, DREI_FRAGEN, **OHNE)
            roh = pfad.read_text()
            # Kein Zustand, keine Anweisung, keine Options-/Stufenbeschreibung
            # (auch nicht die Legende, Auflage 24.09.2026), kein Schluessel,
            # keine Kopfzeile. Optionsnamen ('billing') duerfen drinstehen.
            for verboten in (NOGO_TEXT, 'Zelt', 'Which team', 'urgency', 'Payments', 'Pricing',
                             'Calm', 'Frustrated', 'Very angry', 'legende', 'time-sensitive',
                             JEV_SCHLUESSEL, 'Bearer', 'Authorization'):
                self.assertNotIn(verboten, roh)
            self.assertIn('billing', roh)
            self.assertEqual(len(json.loads(roh)['eintraege']), 3)

            # Unter anderer Kennung, derselbe Zustand und dieselbe Frage -> derselbe Eintrag.
            fragen = {f'neu_{k}': f for k, f in DREI_FRAGEN.items()}
            wieder = TestAnbieter(aufzeichnung=pfad, streng=True).beantworten(zustand, fragen,
                                                                             **OHNE)
            self.assertEqual(wieder['neu_abteilung'].wert, live['abteilung'].wert)
            self.assertEqual(wieder['neu_aerger'].wahrscheinlichkeiten,
                             live['aerger'].wahrscheinlichkeiten)
            # Legende aus der Frage rekonstruiert - gleich der, die Jev lieferte.
            self.assertEqual(wieder['neu_aerger'].legende, live['aerger'].legende)
            self.assertEqual(wieder['neu_aerger'].legende,
                             {'0': 'Calm', '1': 'Frustrated', '2': 'Very angry'})
            self.assertEqual(wieder['neu_nogo_konflikt'].modell, 'aufzeichnung:jev/jev-1.13.0')
            self.assertEqual(wieder['neu_nogo_konflikt'].tokens_ein, 0)
            # Anderer Zustand -> keine Aufzeichnung.
            with self.assertRaises(urteile.AnbieterFehler):
                TestAnbieter(aufzeichnung=pfad, streng=True).beantworten('anders', fragen, **OHNE)


class EinstellungTests(SimpleTestCase):

    def test_voreinstellung_ist_test(self):
        self.assertIsInstance(urteile.urteiler(), TestAnbieter)

    def test_umschalten(self):
        for name, klasse in (('jev', JevAnbieter), ('claude', ClaudeAnbieter),
                             ('test', TestAnbieter)):
            with override_settings(RIDEBUDDIES_KI_ANBIETER=name):
                self.assertIsInstance(urteile.urteiler(), klasse)

    def test_test_anbieter_bleibt_derselbe_und_zaehlt_weiter(self):
        self.assertIs(urteile.urteiler(), urteile.urteiler())

    def test_mitschnitt_aus_einstellung(self):
        with override_settings(RIDEBUDDIES_KI_ANBIETER='jev',
                               RIDEBUDDIES_KI_MITSCHNITT='/tmp/gibt-es-nicht/x.json'):
            a = urteile.urteiler()
        self.assertIsInstance(a, Aufzeichner)
        self.assertIsInstance(a.innen, JevAnbieter)

    def test_mit_anbieter_gilt_nur_im_block(self):
        eigener = TestAnbieter()
        with urteile.mit_anbieter(eigener):
            self.assertIs(urteile.urteiler(), eigener)
        self.assertIsNot(urteile.urteiler(), eigener)


# ---------------------------------------------------------------------------
# manage.py ki_vergleich
# ---------------------------------------------------------------------------

class KiVergleichTests(TestCase):

    def _paar(self, einwilligung=True):
        for name in ('dummy-westerwald-uwe', 'dummy-sauerland-heinz'):
            n = dummy(name, einwilligung=einwilligung)
            Profil.objects.filter(nutzer=n).update(nogo='Jeden Abend Hotel',
                                                   uebernachtung=['zelt'])

    def _lauf(self, *args):
        aus = io.StringIO()
        call_command('ki_vergleich', *args, stdout=aus)
        return aus.getvalue()

    def test_ohne_schluessel_saubere_meldung_und_kein_aufruf(self):
        self._paar()
        with schluessel(), netz_ersetzt() as falsch:
            aus = self._lauf()
        self.assertIn('jev: kein Schlüssel (RIDEBUDDIES_JEV_SCHLUESSEL', aus)
        self.assertIn('claude: kein Schlüssel (RIDEBUDDIES_ANTHROPIC_SCHLUESSEL', aus)
        self.assertEqual(falsch.anfragen, [])

    def test_mit_test_anbieter_drei_formen(self):
        self._paar()
        with alles_mitschneiden() as cm:
            aus = self._lauf('--anbieter', 'test')
        self.assertEqual(len(cm.urteile), 1)
        self.assertIn('nogo_konflikt [noul] Wert 0.500', aus)
        self.assertIn('unterwegs_typ [choice] Wert geniesser', aus)
        self.assertIn('passung_uebernachtung [score] Wert 1.000', aus)

    def test_beide_live_gegen_nachgebautes_netz(self):
        self._paar()
        jev = {'model': 'jev-1.13.0', 'usage': {'input_tokens': 1, 'output_tokens': 2},
               'answers': {
                   'nogo_konflikt': {'type': 'noul', 'noul': 0.9},
                   'unterwegs_typ': {'type': 'choice', 'choice': 'geniesser',
                                     'probabilities': {'geniesser': 0.7,
                                                       'streckenfresser': 0.1,
                                                       'beides': 0.2},
                                     'confidence': 0.55},
                   'passung_uebernachtung': {'type': 'score', 'score': 0.2,
                                             'probabilities': {'0': 0.8, '1': 0.2, '2': 0.0},
                                             'confidence': 0.7}}}
        claude = claude_antwort({'f1': 0.8, 'f2': {'geniesser': 1, 'streckenfresser': 0,
                                                   'beides': 0},
                                 'f3': {'0': 1, '1': 0, '2': 0}})
        with schluessel(RIDEBUDDIES_JEV_SCHLUESSEL=JEV_SCHLUESSEL,
                        RIDEBUDDIES_ANTHROPIC_SCHLUESSEL=CLAUDE_SCHLUESSEL), \
                netz_ersetzt(jev, claude) as falsch, alles_mitschneiden():
            aus = self._lauf()
        self.assertEqual(len(falsch.anfragen), 2)
        self.assertIn('jev:\n  nogo_konflikt [noul] Wert 0.900', aus)
        self.assertIn('claude:\n  nogo_konflikt [noul] Wert 0.800', aus)
        # Nutzernamen gehen nicht an den Anbieter.
        for i in range(2):
            self.assertNotIn('dummy-', json.dumps(falsch.koerper(i)))

    def test_sperre_greift_auch_im_kommando(self):
        self._paar(einwilligung=False)
        with self.assertRaises(CommandError), \
                self.assertLogs('ridebuddies.urteile', 'WARNING') as cm:
            self._lauf('--anbieter', 'test')
        self.assertIn('gruende=keine_ki_einwilligung:2', cm.output[0])

    def test_ohne_dummies(self):
        with self.assertRaises(CommandError):
            self._lauf('--anbieter', 'test')
