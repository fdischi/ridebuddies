"""
Anmeldepflicht und Konto-Seiten (Karte TASK-120.04, Abnahmekriterium #2).

Fabian, 23.09.2026: Ohne Anmeldung ist nichts zu sehen; jede Seite ausser
Login/Konto leitet um. Den eigenen Admin-Login gibt es seit TASK-120.10 nicht
mehr: /admin/login/ leitet auf /konto/login/ (kern/tests/test_anmeldung.py). Bis Schritt 3b antwortete die
Startseite jedem mit 200 - dieser Test hiess damals test_startseite_antwortet
und ist jetzt zweigeteilt: ohne Anmeldung Umleitung, mit Anmeldung 200.

Die Tests laufen mit DEBUG=False (Djangos Testrunner erzwingt das), also so,
wie der Server antwortet: ein unbekannter Pfad ist 404 ohne Fehlerseite.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from kern.models import Profil

LOGIN = '/konto/login/'


class AnmeldepflichtTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.nutzer = get_user_model().objects.create_user(
            username='kurvenfan', email='kurvenfan@example.org', password='geheim-und-lang-42')
        # Ein Inhalt, der nirgends ohne Anmeldung auftauchen darf.
        Profil.objects.filter(nutzer=cls.nutzer).update(region='Siegburg-Geheimwert')

    def assertLeitetZumLogin(self, pfad):
        antwort = self.client.get(pfad)
        self.assertEqual(antwort.status_code, 302, pfad)
        self.assertTrue(antwort['Location'].startswith(LOGIN), antwort['Location'])
        self.assertNotIn(b'Siegburg-Geheimwert', antwort.content)
        return antwort

    def test_startseite_ohne_anmeldung_leitet_um(self):
        antwort = self.assertLeitetZumLogin('/')
        self.assertIn('next=/', antwort['Location'])

    def test_startseite_mit_anmeldung_antwortet(self):
        self.client.force_login(self.nutzer)
        antwort = self.client.get('/')
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, 'Ridebuddies')

    def test_admin_startseite_leitet_ueber_admin_login_zu_konto_login(self):
        # Gemessen 23.09.2026: /admin/ faengt die Admin-Site selbst ab und
        # leitet auf IHREN Login /admin/login/. Seit TASK-120.10 steht dort die
        # Umleitung auf /konto/login/ - zwei Schritte, dann allauth.
        antwort = self.client.get('/admin/')
        self.assertEqual(antwort.status_code, 302)
        self.assertTrue(antwort['Location'].startswith('/admin/login/'), antwort['Location'])
        antwort = self.client.get(antwort['Location'])
        self.assertEqual(antwort.status_code, 302)
        self.assertTrue(antwort['Location'].startswith(LOGIN), antwort['Location'])

    def test_admin_inhalte_ohne_anmeldung_leiten_um(self):
        # Modellseiten des Admin laufen durch die LoginRequiredMiddleware und
        # landen deshalb auf /konto/login/ - umgeleitet, kein Inhalt.
        for pfad in ('/admin/kern/profil/',
                     f'/admin/kern/profil/{self.nutzer.profil.pk}/change/',
                     '/admin/kern/nutzer/'):
            antwort = self.assertLeitetZumLogin(pfad)
            self.assertNotIn(b'kurvenfan', antwort.content)

    def test_konto_verwaltung_ohne_anmeldung_leitet_um(self):
        # Auch unter konto/ gilt: was ein Konto voraussetzt, leitet um.
        self.assertLeitetZumLogin('/konto/email/')
        self.assertLeitetZumLogin('/konto/password/change/')

    def test_unbekannter_pfad_zeigt_nichts(self):
        antwort = self.client.get('/profil/kurvenfan/')
        self.assertIn(antwort.status_code, (302, 404))
        self.assertNotIn(b'kurvenfan', antwort.content)
        self.assertNotIn(b'Siegburg-Geheimwert', antwort.content)

    def test_login_seite_erreichbar(self):
        antwort = self.client.get(LOGIN)
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, 'name="login"')

    def test_passwort_vergessen_erreichbar(self):
        self.assertEqual(self.client.get('/konto/password/reset/').status_code, 200)

    def test_admin_login_leitet_auf_konto_login(self):
        # Bis TASK-120.10 antwortete /admin/login/ mit Djangos eigenem
        # Formular (200) - das zweite Kennwort, das es nicht mehr geben soll.
        antwort = self.client.get('/admin/login/')
        self.assertEqual(antwort.status_code, 302)
        self.assertTrue(antwort['Location'].startswith(LOGIN), antwort['Location'])

    def test_anmelden_mit_nutzername_ueber_allauth(self):
        # Belegt, dass allauth mit dem eigenen Nutzermodell und hinter der
        # Middleware tatsaechlich anmeldet (nicht nur die Seite ausliefert).
        # E-Mail-Bestaetigung ist Pflicht - dieser Nutzer bekommt eine
        # bestaetigte Adresse, wie sie spaeter der Bestaetigungslink setzt.
        from allauth.account.models import EmailAddress
        EmailAddress.objects.create(user=self.nutzer, email=self.nutzer.email,
                                    verified=True, primary=True)
        antwort = self.client.post(LOGIN, {'login': 'kurvenfan',
                                           'password': 'geheim-und-lang-42'})
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_unbestaetigte_email_meldet_nicht_an(self):
        # ACCOUNT_EMAIL_VERIFICATION = 'mandatory': ohne bestaetigte Adresse
        # fuehrt die Anmeldung auf die Seite "Bestaetigung gesendet", nicht hinein.
        antwort = self.client.post(LOGIN, {'login': 'kurvenfan',
                                           'password': 'geheim-und-lang-42'})
        self.assertNotEqual(self.client.get('/').status_code, 200)
        self.assertIn(antwort.status_code, (200, 302))


class RegistrierungTest(TestCase):
    """Registrierung per Umgebungsschalter, Vorgabe zu (kern/adapter.py)."""

    def test_registrierung_vorgabe_zu(self):
        antwort = self.client.get('/konto/signup/')
        self.assertEqual(antwort.status_code, 200)
        self.assertTemplateUsed(antwort, 'account/signup_closed.html')

    @override_settings(RIDEBUDDIES_REGISTRIERUNG_OFFEN=True)
    def test_registrierung_mit_schalter_offen(self):
        antwort = self.client.get('/konto/signup/')
        self.assertEqual(antwort.status_code, 200)
        self.assertTemplateUsed(antwort, 'account/signup.html')

    @override_settings(RIDEBUDDIES_REGISTRIERUNG_OFFEN=True)
    def test_registrierung_legt_nutzer_mit_profil_an(self):
        antwort = self.client.post('/konto/signup/', {
            'email': 'neu@example.org', 'username': 'neuling',
            'password1': 'ein-langes-kennwort-99', 'password2': 'ein-langes-kennwort-99'})
        self.assertEqual(antwort.status_code, 302)
        nutzer = get_user_model().objects.get(username='neuling')
        self.assertTrue(Profil.objects.filter(nutzer=nutzer).exists())


class UrlNamenTest(TestCase):
    def test_login_url_zeigt_auf_allauth(self):
        self.assertEqual(reverse('account_login'), LOGIN)
