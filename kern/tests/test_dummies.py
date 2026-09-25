"""
Dummy-Generator und Pruefblatt (Karte TASK-120.05, 23.09.2026).

Was hier geprueft wird und warum:
- BESTAND: Die Pflichtgruppen der Plan-Notiz (Schritt 5) werden an den WERTEN
  gezaehlt, nicht an den Nutzernamen - ein Name wie "dummy-schotter-x" beweist
  nicht, dass x Enduro faehrt und bei Siegburg wohnt.
- IDEMPOTENZ: Momentaufnahme aller Zeilen aller kern-Modelle plus allauths
  EmailAddress vor und nach einem zweiten Lauf - nicht nur Anzahlen. Ein Lauf,
  der z. B. Profil.geaendert (auto_now) neu stempelt, faellt so auf.
- ABRAEUMEN: danach kein Dummy und nichts, was an ihnen hing; echte Konten -
  auch eins mit Verbindung zu einem Dummy, eins namens "dummy-..." mit echter
  Adresse und eins mit .invalid-Adresse ohne Praefix - bleiben.
- KENNWORT: mit Datei echte Anmeldung ueber /konto/login/, ohne Datei
  unbrauchbar, und das Kennwort erscheint in keiner Ausgabe.
- PRUEFBLATT: Die Erwartungen im Pruefblatt sind nur etwas wert, wenn sie zu
  den Daten passen. Die Konsistenzprobe rechnet jeden "nie"-Grund nach
  (Haversine, Alterswunsch, Geschlecht, No-Go-Regel, Ausschluss, Verbindung)
  und prueft, dass kein "muss"-Kandidat einen harten Filter reisst.
  Das ist KEIN Matching (Schritt 8) - nur die Lesarten aus dem Pruefblatt,
  als Code, um das Blatt selbst zu pruefen.
- KOORDINATEN: nie fuer Dritte sichtbar, auch nicht auf Stufe Ridebuddies und
  auch nicht, wenn jemand am Formular vorbei eine Feldstufe dafuer speichert.
"""
import json
import re
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from allauth.account.models import EmailAddress
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from kern import dummies, sichtbarkeit
from kern.geo import entfernung_km, profil_entfernung_km
from kern.models import (
    FELD_VOREINSTELLUNG,
    Altersbereich,
    Ausfahrt,
    Ausschluss,
    Beitrag,
    Crew,
    Einwilligung,
    Mitgliedschaft,
    Profil,
    RidebuddyAnfrage,
    Stufe,
    Termin,
    Verbindung,
    Verfuegbarkeit,
    Verfuegbarkeitszeitraum,
)

from .hilfen import ridebuddies_machen

DOCS = Path(settings.BASE_DIR) / 'docs'
SIEGBURG = dummies.ORTE['Siegburg']
SCHNELL = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
LOGIN = '/konto/login/'


def _anlegen(*args):
    ausgabe = StringIO()
    call_command('dummies_anlegen', *args, stdout=ausgabe, stderr=ausgabe)
    return ausgabe.getvalue()


def _profil(name):
    return Profil.objects.select_related('nutzer').get(nutzer__username=name)


def _momentaufnahme():
    """Alle Zeilen aller kern-Modelle und der EmailAddress, nach pk sortiert."""
    modelle = list(apps.get_app_config('kern').get_models()) + [EmailAddress]
    return {m.__name__: list(m.objects.order_by('pk').values()) for m in modelle}


# ---------------------------------------------------------------------------
# Lesarten der harten Filter - wie im Pruefblatt, Abschnitt "Lesarten".
# ---------------------------------------------------------------------------
ALTER = list(Altersbereich.values)


def alterswunsch_ok(wer, anderer):
    if not wer.alterswunsch_von and not wer.alterswunsch_bis:
        return True
    if not anderer.altersbereich:
        return False
    von = ALTER.index(wer.alterswunsch_von) if wer.alterswunsch_von else 0
    bis = ALTER.index(wer.alterswunsch_bis) if wer.alterswunsch_bis else len(ALTER) - 1
    return von <= ALTER.index(anderer.altersbereich) <= bis


def geschlecht_ok(wer, anderer):
    if wer.geschlechtspraeferenz != 'gleich':  # 'gemischt' und 'egal' filtern nicht
        return True
    return anderer.geschlecht != 'keine_angabe' and anderer.geschlecht == wer.geschlecht


def nogo_ok(wer, anderer, regeln):
    regel = regeln.get(wer.nutzer.username)
    return regel is None or getattr(anderer, regel['feld']) not in regel['verboten']


def gerissene_filter(a, b, regeln):
    """Menge der harten Gruende, die einen Vorschlag zwischen a und b verbieten
    (beide Richtungen, siehe Lesart 1)."""
    gruende = set()
    entfernung = profil_entfernung_km(a, b)
    if entfernung is None or entfernung > min(a.radius_km, b.radius_km):
        gruende.add('radius')
    if not (geschlecht_ok(a, b) and geschlecht_ok(b, a)):
        gruende.add('geschlechtspraeferenz')
    if not (alterswunsch_ok(a, b) and alterswunsch_ok(b, a)):
        gruende.add('alterswunsch')
    if not (nogo_ok(a, b, regeln) and nogo_ok(b, a, regeln)):
        gruende.add('nogo')
    if sichtbarkeit.ausgeschlossen(a.nutzer, b.nutzer):
        gruende.add('ausschluss')
    if sichtbarkeit.aktive_verbindung(a.nutzer, b.nutzer) is not None:
        gruende.add('verbindung')
    return gruende


# ---------------------------------------------------------------------------
# Bestand
# ---------------------------------------------------------------------------

class BestandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ausgabe = _anlegen()
        cls.profile = list(Profil.objects.select_related('nutzer')
                           .filter(nutzer__in=dummies.dummies()))

    def _entfernung_siegburg(self, p):
        return entfernung_km(*SIEGBURG, p.breitengrad, p.laengengrad)

    def test_mindestens_30_dummies_alle_erkennbar(self):
        self.assertGreaterEqual(len(self.profile), 30)
        self.assertEqual(len(self.profile), len(dummies.PROFILE))
        for p in self.profile:
            self.assertTrue(p.nutzer.username.startswith('dummy-'))
            self.assertEqual(p.nutzer.email, f'{p.nutzer.username}@example.invalid')
            self.assertFalse(p.nutzer.is_staff)

    def test_email_bestaetigt_und_primaer(self):
        for p in self.profile:
            adressen = EmailAddress.objects.filter(user=p.nutzer)
            self.assertEqual(adressen.count(), 1, p.nutzer)
            self.assertTrue(adressen.get().verified and adressen.get().primary, p.nutzer)

    def test_profile_bestehen_die_modellpruefung(self):
        # full_clean prueft Auswahllisten, Mehrfachwahl-Validatoren und feldstufen.
        for p in self.profile:
            p.full_clean()

    def test_pflichtgruppe_enduro_um_siegburg(self):
        treffer = [p for p in self.profile if 'enduro' in p.fahrarten
                   and self._entfernung_siegburg(p) <= 20]
        self.assertGreaterEqual(len(treffer), 5, [p.nutzer.username for p in treffer])

    def test_pflichtgruppe_sport(self):
        self.assertGreaterEqual(sum('sport' in p.fahrarten for p in self.profile), 3)

    def test_pflichtgruppe_frauen_gleich(self):
        self.assertGreaterEqual(sum(p.geschlecht == 'weiblich'
                                    and p.geschlechtspraeferenz == 'gleich'
                                    for p in self.profile), 4)

    def test_pflichtgruppe_nogo_alkohol(self):
        mit = [p for p in self.profile if 'alkohol' in p.nogo.lower()]
        self.assertGreaterEqual(len(mit), 2)
        for p in mit:  # wer Alkohol als No-Go hat, trinkt auch selbst nicht
            self.assertEqual(p.alkohol_auf_tour, 'nie', p.nutzer)

    def test_orte(self):
        regionen = ' '.join(p.region for p in self.profile)
        for ort in ('Bonn', 'Köln', 'Eifel', 'Sauerland', 'Westerwald'):
            self.assertIn(ort, regionen)
        self.assertTrue(any(self._entfernung_siegburg(p) > 300 for p in self.profile))
        self.assertTrue(all(p.breitengrad is not None for p in self.profile))

    def test_stoerfaelle(self):
        # jemand, mit dem niemand im beidseitigen Radius liegt
        einsam = [a for a in self.profile if all(
            profil_entfernung_km(a, b) > min(a.radius_km, b.radius_km)
            for b in self.profile if b is not a)]
        self.assertTrue(einsam)
        self.assertTrue(any(p.geschlecht == 'keine_angabe' for p in self.profile))
        self.assertTrue(any(p.alterswunsch_von for p in self.profile))

    def test_merkmale_vielfaeltig(self):
        for feld in ('tempo', 'selbsteinschaetzung', 'unterwegs_stil', 'gruppengroesse',
                     'altersbereich', 'alkohol_auf_tour', 'schutzkleidung'):
            werte = {getattr(p, feld) for p in self.profile}
            self.assertGreaterEqual(len(werte), 3, feld)
        for feld in ('tourenformate', 'themen', 'uebernachtung', 'fahrarten'):
            werte = {w for p in self.profile for w in getattr(p, feld)}
            self.assertGreaterEqual(len(werte), 3, feld)

    def test_crews_mit_allen_rollen(self):
        crews = Crew.objects.filter(beschreibung__startswith=dummies.MARKE)
        self.assertGreaterEqual(crews.count(), 2)
        rollen = set(Mitgliedschaft.objects.filter(crew__in=crews)
                     .values_list('rolle', flat=True))
        self.assertEqual(rollen, set(Mitgliedschaft.Rolle.values))
        for crew in crews:
            self.assertTrue(crew.mitgliedschaften.filter(rolle='organisator').exists(), crew)

    def test_ausfahrten_und_reisen_saison_2027(self):
        ausfahrten = Ausfahrt.objects.filter(beschreibung__startswith=dummies.MARKE)
        ohne_reise = ausfahrten.exclude(art=Ausfahrt.Art.REISE)
        self.assertGreaterEqual(ohne_reise.count(), 5)
        self.assertEqual(set(ohne_reise.values_list('art', flat=True)),
                         {'tagestour', 'messe', 'training'})
        self.assertEqual(ausfahrten.filter(art=Ausfahrt.Art.REISE).count(), 2)
        for termin in Termin.objects.filter(ausfahrt__in=ausfahrten):
            self.assertEqual(termin.datum.year, 2027)
            self.assertIn(termin.datum.month, (4, 5, 6))
            if termin.ausfahrt.art == Ausfahrt.Art.REISE:
                self.assertTrue(termin.bis_datum)
                self.assertTrue(Verfuegbarkeitszeitraum.objects.filter(
                    ausfahrt=termin.ausfahrt, von=termin.datum, bis=termin.bis_datum).exists())
            else:
                self.assertTrue(termin.tageszeit)
                self.assertTrue(Verfuegbarkeit.objects.filter(
                    ausfahrt=termin.ausfahrt, datum=termin.datum,
                    tageszeit=termin.tageszeit).exists())
        self.assertEqual(set(Verfuegbarkeit.objects.values_list('stufe', flat=True)),
                         {'sicher', 'vorbehalt', 'nein'})
        self.assertEqual(set(Verfuegbarkeit.objects.values_list('tageszeit', flat=True)),
                         {'vormittags', 'mittags', 'nachmittags'})

    def test_terminfaelle_fuer_schritt_6(self):
        """Die im Pruefblatt genannten Faelle stehen so in den Daten."""
        def antworten(titel, datum):
            return sorted(Verfuegbarkeit.objects.filter(ausfahrt__titel=titel, datum=datum)
                          .values_list('stufe', flat=True))
        runde = 'Schotterrunde Bergisches Land'
        self.assertEqual(antworten(runde, '2027-04-17'), ['sicher'] * 5)
        self.assertEqual(antworten(runde, '2027-04-18'), ['sicher'] * 3 + ['vorbehalt'] * 2)
        self.assertEqual(antworten(runde, '2027-04-24'), ['nein'] * 3 + ['sicher'] * 2)
        training = 'Enduro-Grundlagentraining'
        self.assertEqual(antworten(training, '2027-05-08'), antworten(training, '2027-05-15'))

    def test_beziehungen(self):
        aktiv = Verbindung.objects.filter(beendet_am__isnull=True,
                                          nutzer_a__in=dummies.dummies())
        self.assertGreaterEqual(aktiv.filter(erreicht=Stufe.VERBUNDEN).count(), 2)
        buddies = aktiv.filter(erreicht=Stufe.RIDEBUDDIES)
        self.assertGreaterEqual(buddies.count(), 2)
        for v in buddies:
            # Modellregel (Fabian, 23.09.2026): Stufe 3 nur ueber bestaetigte Anfrage.
            self.assertTrue(v.ridebuddy_anfragen.filter(
                status=RidebuddyAnfrage.Status.BESTAETIGT).exists(), v)
            self.assertEqual((v.gewaehrt_a, v.gewaehrt_b), (3, 3))
        self.assertGreaterEqual(Ausschluss.objects.filter(
            urheber__in=dummies.dummies()).count(), 1)

    def test_beitraege_in_allen_stufen(self):
        stufen = set(Beitrag.objects.filter(autor__in=dummies.dummies())
                     .values_list('stufe', flat=True))
        self.assertEqual(stufen, {1, 2, 3})

    def test_alle_dummies_haben_die_ki_einwilligung(self):
        # Fabian, 24.09.2026 (TASK-120.13): ohne KI-Einwilligung keine Anmeldung,
        # also auch kein Dummy ohne sie - Robin eingeschlossen.
        ohne = dummies.dummies().exclude(
            einwilligungen__art=Einwilligung.Art.KI_AUSWERTUNG,
            einwilligungen__widerrufen_am__isnull=True)
        self.assertEqual(list(ohne.values_list('username', flat=True)), [])
        self.assertEqual(dummies.OHNE_KI_EINWILLIGUNG, set())

    def test_zusammenfassung(self):
        self.assertIn('Nutzer', self.ausgabe)
        # Beim Erstlauf ist das Fuellen des Signal-Profils "neu", nicht "angeglichen".
        self.assertNotIn('Angeglichen:\n  Profil', self.ausgabe)
        self.assertIn('Dummy-Bestand hergestellt.', self.ausgabe)


# ---------------------------------------------------------------------------
# Idempotenz
# ---------------------------------------------------------------------------

class IdempotenzTest(TestCase):
    def test_zweiter_lauf_aendert_nichts(self):
        _anlegen()
        vorher = _momentaufnahme()
        ausgabe = _anlegen()
        nachher = _momentaufnahme()
        for modell in vorher:
            self.assertEqual(len(vorher[modell]), len(nachher[modell]), modell)
            self.assertEqual(vorher[modell], nachher[modell], modell)
        self.assertIn('Nichts geschrieben', ausgabe)

    def test_abweichung_wird_angeglichen_und_nur_sie(self):
        _anlegen()
        profil = _profil('dummy-schotter-sven')
        profil.tempo = 'gemuetlich'
        profil.save()
        andere = _profil('dummy-schotter-jonas').geaendert
        ausgabe = _anlegen()
        self.assertEqual(_profil('dummy-schotter-sven').tempo, 'zuegig')
        self.assertEqual(_profil('dummy-schotter-jonas').geaendert, andere)
        self.assertIn('Angeglichen', ausgabe)

    def test_ki_einwilligung_wird_auf_altem_bestand_nachgezogen(self):
        # Ein Bestand von vor dem 24.09.2026: Robin ohne KI-Einwilligung.
        _anlegen()
        robin = Einwilligung.objects.filter(nutzer__username='dummy-ohne-angabe-robin',
                                            art=Einwilligung.Art.KI_AUSWERTUNG)
        robin.delete()
        ausgabe = _anlegen()
        self.assertEqual(robin.count(), 1)
        self.assertRegex(ausgabe, r'Neu angelegt:\n\s+Einwilligung\s+1\n')
        self.assertIn('Nichts geschrieben', _anlegen())

    def test_echter_nutzer_mit_dummy_namen_bricht_ab_ohne_aenderung(self):
        get_user_model().objects.create_user(
            username='dummy-schotter-sven', email='sven@example.org', password=None)
        vorher = _momentaufnahme()
        with self.assertRaises(CommandError):
            _anlegen()
        self.assertEqual(_momentaufnahme(), vorher)


# ---------------------------------------------------------------------------
# Abraeumen
# ---------------------------------------------------------------------------

class AbraeumenTest(TestCase):
    def test_nur_dummies_danach_alles_leer(self):
        _anlegen()
        ausgabe = StringIO()
        call_command('dummies_anlegen', '--abraeumen', stdout=ausgabe)
        for modell, zeilen in _momentaufnahme().items():
            self.assertEqual(zeilen, [], modell)
        self.assertIn('Übrig: 0', ausgabe.getvalue())

    def test_echte_konten_bleiben(self):
        _anlegen()
        Nutzer = get_user_model()
        echt = Nutzer.objects.create_user(username='echt', email='echt@example.org',
                                          password=None)
        # Kein Dummy: Praefix ja, Adresse echt - und umgekehrt.
        namensvetter = Nutzer.objects.create_user(
            username='dummy-namensvetter', email='nv@example.org', password=None)
        invalid = Nutzer.objects.create_user(
            username='fritz', email='fritz@example.invalid', password=None)
        sven = Nutzer.objects.get(username='dummy-schotter-sven')
        ridebuddies_machen(echt, sven)  # Verbindung Stufe 3 zu einem Dummy
        Beitrag.objects.create(autor=echt, text='echt', stufe=1)
        eigene = Crew.objects.create(name='Echte Crew')
        Mitgliedschaft.objects.create(crew=eigene, nutzer=echt, rolle='organisator')
        # echt als Gast in einer Dummy-Crew: die Crew gehoert damit nicht mehr
        # nur Dummies und bleibt, samt ihren Ausfahrten.
        ladies = Crew.objects.get(name='Ladies on Tour Rheinland')
        Mitgliedschaft.objects.create(crew=ladies, nutzer=echt, rolle='gast')

        call_command('dummies_anlegen', '--abraeumen', stdout=StringIO())

        self.assertFalse(dummies.dummies().exists())
        self.assertEqual(set(Nutzer.objects.values_list('username', flat=True)),
                         {'echt', 'dummy-namensvetter', 'fritz'})
        self.assertEqual(Profil.objects.count(), 3)
        self.assertEqual(Beitrag.objects.get().autor, echt)
        self.assertFalse(Verbindung.objects.exists())
        self.assertFalse(RidebuddyAnfrage.objects.exists())
        self.assertEqual(set(Crew.objects.values_list('name', flat=True)),
                         {'Echte Crew', 'Ladies on Tour Rheinland'})
        self.assertEqual(list(ladies.mitgliedschaften.values_list('nutzer__username',
                                                                   flat=True)), ['echt'])
        self.assertEqual(set(Ausfahrt.objects.values_list('crew__name', flat=True)),
                         {'Ladies on Tour Rheinland'})
        self.assertFalse(Verfuegbarkeit.objects.exists())
        self.assertFalse(EmailAddress.objects.filter(email__endswith='.invalid')
                         .exclude(user=invalid).exists())
        self.assertTrue(Nutzer.objects.filter(pk=namensvetter.pk).exists())

    def test_abraeumen_und_neu_anlegen(self):
        _anlegen()
        call_command('dummies_anlegen', '--abraeumen', stdout=StringIO())
        _anlegen()
        self.assertEqual(dummies.dummies().count(), len(dummies.PROFILE))


# ---------------------------------------------------------------------------
# Kennwort
# ---------------------------------------------------------------------------

@SCHNELL
class KennwortTest(TestCase):
    KENNWORT = 'Schotter-auf-dem-Westerwald-2027'

    def setUp(self):
        self.verzeichnis = tempfile.TemporaryDirectory()
        self.datei = Path(self.verzeichnis.name) / 'kennwort'
        self.datei.write_text(self.KENNWORT + '\n', encoding='utf-8')
        self.datei.chmod(0o600)

    def tearDown(self):
        self.verzeichnis.cleanup()

    def test_ohne_datei_kein_nutzbares_kennwort(self):
        _anlegen()
        self.assertFalse(any(n.has_usable_password() for n in dummies.dummies()))

    def test_mit_datei_anmeldung_moeglich_und_nichts_ausgegeben(self):
        ausgabe = _anlegen('--kennwort-datei', str(self.datei))
        self.assertNotIn(self.KENNWORT, ausgabe)
        self.assertTrue(all(n.has_usable_password() for n in dummies.dummies()))
        antwort = self.client.post(LOGIN, {'login': 'dummy-frauen-anja',
                                           'password': self.KENNWORT})
        self.assertEqual(antwort.status_code, 302, antwort.content[:500])
        self.assertEqual(self.client.get('/').context['user'].username, 'dummy-frauen-anja')

    def test_zweiter_lauf_mit_datei_aendert_nichts(self):
        _anlegen('--kennwort-datei', str(self.datei))
        vorher = _momentaufnahme()
        ausgabe = _anlegen('--kennwort-datei', str(self.datei))
        self.assertEqual(_momentaufnahme(), vorher)
        self.assertIn('Nichts geschrieben', ausgabe)

    def test_lauf_ohne_datei_nimmt_kennwort_nicht_weg(self):
        _anlegen('--kennwort-datei', str(self.datei))
        _anlegen()
        self.assertTrue(all(n.has_usable_password() for n in dummies.dummies()))

    def test_kennwort_von_stdin(self):
        # So laeuft es auf dem Server: runuser ... --kennwort-datei - < datei.
        # Der Befehl liest den geerbten fd 0 (sys.stdin), nie /dev/stdin als Pfad.
        with mock.patch('sys.stdin', StringIO(self.KENNWORT + '\n')):
            ausgabe = _anlegen('--kennwort-datei', '-')
        self.assertNotIn(self.KENNWORT, ausgabe)
        self.assertNotIn('Hinweis', ausgabe)  # keine Rechtepruefung bei "-"
        sven = get_user_model().objects.get(username='dummy-schotter-sven')
        self.assertTrue(sven.check_password(self.KENNWORT))
        with mock.patch('sys.stdin', StringIO('')), self.assertRaises(CommandError):
            _anlegen('--kennwort-datei', '-')

    def test_rechtehinweis_bei_offener_datei(self):
        self.datei.chmod(0o644)
        self.assertIn('Hinweis', _anlegen('--kennwort-datei', str(self.datei)))

    def test_neues_kennwort_wird_gesetzt(self):
        _anlegen('--kennwort-datei', str(self.datei))
        self.datei.write_text('Ein-ganz-anderes-Kennwort-99', encoding='utf-8')
        _anlegen('--kennwort-datei', str(self.datei))
        sven = get_user_model().objects.get(username='dummy-schotter-sven')
        self.assertTrue(sven.check_password('Ein-ganz-anderes-Kennwort-99'))

    def test_schlechte_dateien_brechen_ab_ohne_kennwort_zu_nennen(self):
        leer = Path(self.verzeichnis.name) / 'leer'
        leer.write_text('', encoding='utf-8')
        with self.assertRaises(CommandError):
            _anlegen('--kennwort-datei', str(leer))
        with self.assertRaises(CommandError):
            _anlegen('--kennwort-datei', str(Path(self.verzeichnis.name) / 'fehlt'))
        kurz = Path(self.verzeichnis.name) / 'kurz'
        kurz.write_text('abc12', encoding='utf-8')
        with self.assertRaises(CommandError) as fehler:
            _anlegen('--kennwort-datei', str(kurz))
        self.assertNotIn('abc12', str(fehler.exception))
        self.assertFalse(dummies.dummies().exists())  # nichts angelegt


# ---------------------------------------------------------------------------
# Pruefblatt
# ---------------------------------------------------------------------------

class PruefblattTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _anlegen()
        cls.blatt = json.loads((DOCS / 'pruefblatt-matching.json').read_text(encoding='utf-8'))
        cls.markdown = (DOCS / 'pruefblatt-matching.md').read_text(encoding='utf-8')
        cls.regeln = cls.blatt['nogo_regeln']

    def _personen(self, anker):
        return ([anker['nutzer']] + [m['nutzer'] for m in anker['muss_top5']]
                + [n['nutzer'] for n in anker['nie']])

    def test_form(self):
        self.assertGreaterEqual(len(self.blatt['anker']), 8)
        for anker in self.blatt['anker']:
            self.assertLessEqual(len(anker['muss_top5']), 5, anker['nutzer'])
            self.assertTrue(anker['steckbrief'])
            for eintrag in anker['muss_top5'] + anker['nie']:
                self.assertTrue(eintrag['begruendung'], eintrag)
            for eintrag in anker['nie']:
                self.assertIn(eintrag['grund'], self.blatt['gruende'])
            muss = {m['nutzer'] for m in anker['muss_top5']}
            nie = {n['nutzer'] for n in anker['nie']}
            self.assertFalse(muss & nie, anker['nutzer'])
            self.assertNotIn(anker['nutzer'], muss | nie)
        gruende = {n['grund'] for a in self.blatt['anker'] for n in a['nie']}
        self.assertEqual(gruende, set(self.blatt['gruende']))

    def test_jede_person_existiert(self):
        vorhanden = set(dummies.dummies().values_list('username', flat=True))
        for anker in self.blatt['anker']:
            for name in self._personen(anker):
                self.assertIn(name, vorhanden)
        for name in self.regeln:
            self.assertIn(name, vorhanden)
        for name in set(re.findall(r'dummy-[a-z-]+[a-z]', self.markdown)):
            self.assertIn(name, vorhanden, 'im Markdown genannt')

    def test_markdown_und_json_nennen_dieselben_anker_und_personen(self):
        abschnitte = re.split(r'^### \d+\. ', self.markdown, flags=re.M)[1:]
        md_anker = [a.split()[0] for a in abschnitte]
        self.assertEqual(md_anker, [a['nutzer'] for a in self.blatt['anker']])
        for text, anker in zip(abschnitte, self.blatt['anker']):
            text = text.split('\n## ')[0]  # nur bis zum naechsten Hauptabschnitt
            genannt = set(re.findall(r'\| (dummy-[a-z-]+[a-z]) \|', text))
            erwartet = set(self._personen(anker)) - {anker['nutzer']}
            self.assertEqual(genannt, erwartet, anker['nutzer'])

    def test_entfernungen_stimmen(self):
        for anker in self.blatt['anker']:
            a = _profil(anker['nutzer'])
            for eintrag in anker['muss_top5'] + anker['nie']:
                ist = profil_entfernung_km(a, _profil(eintrag['nutzer']))
                self.assertAlmostEqual(ist, eintrag['entfernung_km'], delta=0.06,
                                       msg=f"{anker['nutzer']} - {eintrag['nutzer']}")

    def test_nie_gruende_liegen_in_den_daten_vor(self):
        maschinell = set(self.blatt['maschinell_geprueft'])
        for anker in self.blatt['anker']:
            a = _profil(anker['nutzer'])
            for eintrag in anker['nie']:
                if eintrag['grund'] not in maschinell:
                    continue  # Freitext-No-Go: eigener Test unten
                gerissen = gerissene_filter(a, _profil(eintrag['nutzer']), self.regeln)
                self.assertIn(eintrag['grund'], gerissen,
                              f"{anker['nutzer']} - {eintrag['nutzer']}: {gerissen}")

    def test_muss_kandidaten_reissen_keinen_harten_filter(self):
        for anker in self.blatt['anker']:
            a = _profil(anker['nutzer'])
            for eintrag in anker['muss_top5']:
                gerissen = gerissene_filter(a, _profil(eintrag['nutzer']), self.regeln)
                self.assertEqual(gerissen, set(), f"{anker['nutzer']} - {eintrag['nutzer']}")

    def test_freitext_nogo_eintraege(self):
        # Lesart 7: Freitext-Gruende prueft kein Code nach (das ist Schritt 8),
        # aber die Person muss es geben, und das No-Go, auf das sich der Eintrag
        # stuetzt, darf nicht leer sein.
        freitext = [(a, n) for a in self.blatt['anker'] for n in a['nie']
                    if n['grund'] == 'nogo_freitext']
        self.assertGreaterEqual(len(freitext), 2)
        for anker, eintrag in freitext:
            self.assertTrue(dummies.dummies().filter(username=eintrag['nutzer']).exists())
            self.assertIn(eintrag['nogo_von'], (anker['nutzer'], eintrag['nutzer']))
            self.assertTrue(_profil(eintrag['nogo_von']).nogo.strip(), eintrag)
            self.assertTrue(eintrag['begruendung'].get('nogo'), eintrag)

    def test_jeder_muss_eintrag_begruendet_die_nogo_pruefung(self):
        # Lesart 7: beide Richtungen, auch Freitext. Wo einer von beiden ein
        # No-Go hat, muss die Begruendung sagen, warum es nicht gerissen ist.
        for anker in self.blatt['anker']:
            for eintrag in anker['muss_top5']:
                if _profil(anker['nutzer']).nogo or _profil(eintrag['nutzer']).nogo:
                    self.assertTrue(eintrag['begruendung'].get('nogo'),
                                    f"{anker['nutzer']} - {eintrag['nutzer']}")

    def test_grenzfaelle_vollstaendig_und_richtig(self):
        profile = {p.nutzer.username: p for p in
                   Profil.objects.select_related('nutzer').filter(nutzer__in=dummies.dummies())}
        namen = sorted(profile)
        erwartet = set()
        for i, a in enumerate(namen):
            for b in namen[i + 1:]:
                d = profil_entfernung_km(profile[a], profile[b])
                if abs(d - min(profile[a].radius_km, profile[b].radius_km)) < 1:
                    erwartet.add((a, b))
        genannt = {tuple(g['paar']) for g in self.blatt['grenzfaelle']}
        self.assertEqual(genannt, erwartet)
        im_blatt = {frozenset((a['nutzer'], e['nutzer'])) for a in self.blatt['anker']
                    for e in a['muss_top5'] + a['nie']}
        for g in self.blatt['grenzfaelle']:
            a, b = (profile[n] for n in g['paar'])
            d = profil_entfernung_km(a, b)
            self.assertAlmostEqual(d, g['entfernung_km'], delta=0.006)
            self.assertEqual(g['radius_km'], min(a.radius_km, b.radius_km))
            self.assertEqual(g['ergebnis'], 'drin' if d <= g['radius_km'] else 'draußen')
            self.assertNotIn(frozenset(g['paar']), im_blatt)

    def test_kein_anker_teilt_eine_crew_mit_seinen_kandidaten(self):
        # Lesart 9 im Pruefblatt: sonst haenge es an der offenen Crew-Frage.
        for anker in self.blatt['anker']:
            crews = set(Mitgliedschaft.objects.filter(nutzer__username=anker['nutzer'])
                        .values_list('crew_id', flat=True))
            for name in self._personen(anker)[1:]:
                andere = set(Mitgliedschaft.objects.filter(nutzer__username=name)
                             .values_list('crew_id', flat=True))
                self.assertFalse(crews & andere, f"{anker['nutzer']} - {name}")

    def test_robins_beitragssignal_als_ueberholt_markiert(self):
        # Nicht geloescht, sondern markiert (Auftrag TASK-120.13).
        zeile = next(z for z in self.markdown.splitlines()
                     if z.startswith('| dummy-ohne-angabe-robin | öffentlich'))
        self.assertIn('~~**darf nicht wirken:**', zeile)
        self.assertIn('überholt 24.09.2026', zeile)
        self.assertEqual(self.blatt['ueberholt'][0]['datum'], '2026-09-24')

    def test_nogo_regeln_passen_zum_freitext(self):
        for name in self.regeln:
            self.assertIn('alkohol', _profil(name).nogo.lower())


# ---------------------------------------------------------------------------
# Koordinaten
# ---------------------------------------------------------------------------

class KoordinatenTest(TestCase):
    def setUp(self):
        Nutzer = get_user_model()
        self.inhaber = Nutzer.objects.create_user(username='inhaber', email='i@example.org',
                                                  password=None)
        self.buddy = Nutzer.objects.create_user(username='buddy', email='b@example.org',
                                                password=None)
        ridebuddies_machen(self.inhaber, self.buddy)
        Profil.objects.filter(nutzer=self.inhaber).update(
            breitengrad='50.8000', laengengrad='7.2075', region='Siegburg')

    def test_nicht_in_den_waehlbaren_feldern(self):
        self.assertNotIn('breitengrad', FELD_VOREINSTELLUNG)
        self.assertNotIn('laengengrad', FELD_VOREINSTELLUNG)

    def test_ridebuddy_sieht_keine_koordinaten(self):
        self.assertEqual(sichtbarkeit.stufe_fuer(self.buddy, self.inhaber), Stufe.RIDEBUDDIES)
        sicht = sichtbarkeit.profil_sicht(self.buddy, self.inhaber)
        self.assertEqual(sicht['region'], 'Siegburg')
        self.assertNotIn('breitengrad', sicht)
        self.assertNotIn('laengengrad', sicht)
        self.assertNotIn('50.8', str(sicht))

    def test_auch_eine_untergeschobene_feldstufe_gibt_sie_nicht_frei(self):
        # Am Formular vorbei gespeichert (update umgeht clean):
        Profil.objects.filter(nutzer=self.inhaber).update(
            feldstufen={'breitengrad': 1, 'laengengrad': 1})
        sicht = sichtbarkeit.profil_sicht(self.buddy, self.inhaber)
        self.assertNotIn('breitengrad', sicht)
        self.assertNotIn('laengengrad', sicht)
        # ... und ueber das Formular (clean) geht es gar nicht erst:
        profil = Profil.objects.get(nutzer=self.inhaber)
        with self.assertRaises(ValidationError):
            profil.full_clean()

    def test_nur_der_inhaber_bekommt_sie(self):
        self.assertEqual(sichtbarkeit.eigene_koordinaten(self.inhaber, self.inhaber),
                         (Profil.objects.get(nutzer=self.inhaber).breitengrad,
                          Profil.objects.get(nutzer=self.inhaber).laengengrad))
        self.assertIsNone(sichtbarkeit.eigene_koordinaten(self.buddy, self.inhaber))
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(sichtbarkeit.eigene_koordinaten(AnonymousUser(), self.inhaber))

    def test_halbes_paar_verboten(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Profil.objects.filter(nutzer=self.buddy).update(breitengrad='50.1')

    def test_im_admin_bearbeitbar(self):
        chef = get_user_model().objects.create_superuser(
            username='chef', email='chef@example.org', password=None)
        self.client.force_login(chef)
        profil = Profil.objects.get(nutzer=self.inhaber)
        antwort = self.client.get(f'/admin/kern/profil/{profil.pk}/change/')
        self.assertContains(antwort, 'name="breitengrad"')
        self.assertContains(antwort, 'name="laengengrad"')


class GeoTest(TestCase):
    def test_bekannte_entfernung(self):
        # Koeln Dom - Bonn Markt: Luftlinie rund 24-25 km.
        self.assertAlmostEqual(entfernung_km(50.9413, 6.9583, 50.7353, 7.1022), 25.0, delta=1.0)
        self.assertEqual(entfernung_km(50, 7, 50, 7), 0)
