"""
Modelle, Admin und Migrationen (Karte TASK-120.04, Abnahmekriterium #1 lokal).
"""
import datetime
from io import StringIO

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from kern.ablaeufe import plus_monate
from kern.models import Profil, Stufe, Verbindung

from .hilfen import nutzer

# Die Modelle, die die Karte nennt - ausdruecklich aufgezaehlt, damit ein
# vergessenes Modell auffaellt und nicht nur "alle, die es gibt" geprueft werden.
KARTENMODELLE = {
    'Nutzer', 'Profil', 'Beitrag', 'Verbindung', 'Vorschlag', 'Anfrage', 'Ausschluss',
    'Crew', 'Mitgliedschaft', 'CrewVorschlag', 'Ausfahrt', 'Termin', 'Teilnahme',
    'Verfuegbarkeit', 'Verfuegbarkeitszeitraum', 'Nachricht', 'Fremdprofil', 'Teilung',
    'Feedback', 'Einwilligung',
}


class AdminTest(TestCase):
    def test_alle_kartenmodelle_existieren(self):
        vorhanden = {m.__name__ for m in apps.get_app_config('kern').get_models()}
        self.assertEqual(KARTENMODELLE - vorhanden, set())

    def test_alle_modelle_im_admin_registriert(self):
        registriert = set(admin.site._registry)
        fehlend = [m.__name__ for m in apps.get_app_config('kern').get_models()
                   if m not in registriert]
        self.assertEqual(fehlend, [])

    def test_admin_seiten_antworten_fuer_superuser(self):
        chef = get_user_model().objects.create_superuser(
            username='chef', email='chef@example.org', password=None)
        self.client.force_login(chef)
        for modell in apps.get_app_config('kern').get_models():
            pfad = f'/admin/kern/{modell._meta.model_name}/'
            self.assertEqual(self.client.get(pfad).status_code, 200, pfad)
            pfad_neu = pfad + 'add/'
            self.assertEqual(self.client.get(pfad_neu).status_code, 200, pfad_neu)


class MigrationenTest(TestCase):
    def test_keine_fehlende_migration(self):
        ausgabe = StringIO()
        # --check beendet mit SystemExit(1), wenn eine Migration fehlt.
        call_command('makemigrations', '--check', '--dry-run', stdout=ausgabe)
        self.assertIn('No changes detected', ausgabe.getvalue())


class NutzerUndProfilTest(TestCase):
    def test_profil_entsteht_automatisch(self):
        n = nutzer('neu')
        self.assertTrue(Profil.objects.filter(nutzer=n).exists())

    def test_kein_klarname(self):
        felder = {f.name for f in get_user_model()._meta.get_fields()}
        self.assertNotIn('first_name', felder)
        self.assertNotIn('last_name', felder)

    def test_voreinstellungen_greifen(self):
        profil = nutzer('neu').profil
        self.assertEqual(profil.feldstufe('region'), Stufe.OEFFENTLICH)
        self.assertEqual(profil.feldstufe('nogo'), Stufe.VERBUNDEN)
        self.assertEqual(profil.gewichtung_von('region'), 'hart')
        self.assertEqual(profil.gewichtung_von('tempo'), 'weich')
        self.assertEqual(profil.geschlecht, 'keine_angabe')
        profil.gewichtung = {'tempo': 'hart'}
        self.assertEqual(profil.gewichtung_von('tempo'), 'hart')


class VerbindungIntegritaetTest(TestCase):
    def test_gewaehrt_nicht_ueber_erreicht(self):
        a, b = nutzer('a'), nutzer('b')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Verbindung.objects.create(nutzer_a=a, nutzer_b=b, erreicht=Stufe.VERBUNDEN,
                                      gewaehrt_a=Stufe.RIDEBUDDIES,
                                      entstanden_durch=Verbindung.Entstehung.ANFRAGE)

    def test_nur_eine_aktive_verbindung_je_paar(self):
        a, b = nutzer('a'), nutzer('b')
        Verbindung.objects.create(nutzer_a=a, nutzer_b=b,
                                  entstanden_durch=Verbindung.Entstehung.ANFRAGE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Verbindung.objects.create(nutzer_a=a, nutzer_b=b,
                                      entstanden_durch=Verbindung.Entstehung.ANFRAGE)


class PlusMonateTest(TestCase):
    def test_monatsende_gekappt(self):
        self.assertEqual(plus_monate(datetime.date(2026, 8, 31), 6), datetime.date(2027, 2, 28))
        self.assertEqual(plus_monate(datetime.date(2026, 9, 23), 6), datetime.date(2027, 3, 23))
