"""
Eine Anmeldeseite mit Rollen (Karte TASK-120.10, 23.09.2026).

- /admin/login/ leitet auf /konto/login/ um und reicht next weiter
  (kern/views.py), unsichere next-Adressen werden verworfen;
- ein angemeldeter Nicht-Admin geraet auf /admin/ in keine Schleife, sondern
  landet auf der Startseite;
- ein Admin mit bestaetigter Adresse meldet sich EINMAL ueber /konto/login/
  an und steht im Admin, ohne dass je Djangos Admin-Formular erscheint;
- die Startseite zeigt Nutzername, Abmelden und "Verwaltung" nur fuer is_staff;
- manage.py email_bestaetigen macht einen neuen Superuser ueber /konto/login/
  nutzbar.

Kennwoerter mit MD5 statt PBKDF2: Jeder PBKDF2-Hash kostet auf VM 140 unter
Last ueber eine Sekunde (siehe kern/tests/hilfen.py). Hier geht es um den Weg
durch die Views, nicht um den Hash.
"""
from io import StringIO
from urllib.parse import parse_qs, urlsplit

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

LOGIN = '/konto/login/'
KENNWORT = 'geheim-und-lang-42'
SCHNELL = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def _next(location):
    teile = urlsplit(location)
    return teile.path, parse_qs(teile.query).get('next', [None])[0]


def _anlegen(name, **felder):
    return get_user_model().objects.create_user(
        username=name, email=f'{name}@example.org', password=KENNWORT, **felder)


@SCHNELL
class AdminLoginUmleitungTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mitfahrer = _anlegen('mitfahrer')
        cls.admin = _anlegen('chef', is_staff=True, is_superuser=True)

    def test_admin_login_leitet_auf_konto_login_mit_next_admin(self):
        antwort = self.client.get('/admin/login/')
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(_next(antwort['Location']), (LOGIN, '/admin/'))

    def test_next_wird_weitergereicht(self):
        antwort = self.client.get('/admin/login/?next=/admin/kern/nutzer/')
        self.assertEqual(_next(antwort['Location']), (LOGIN, '/admin/kern/nutzer/'))

    def test_unsichere_next_wird_verworfen(self):
        for boese in ('https://boese.example/', '//boese.example/', 'javascript:alert(1)',
                      'http://testserver.boese.example/'):
            antwort = self.client.get('/admin/login/', {'next': boese})
            self.assertEqual(_next(antwort['Location']), (LOGIN, '/admin/'), boese)

    def test_unsichere_next_auch_fuer_angemeldeten_admin_verworfen(self):
        # Hier leitet die View selbst weiter, ohne allauths eigene Pruefung.
        self.client.force_login(self.admin)
        antwort = self.client.get('/admin/login/', {'next': 'https://boese.example/'})
        self.assertEqual(antwort['Location'], '/admin/')

    def test_admin_ohne_anmeldung_endet_auf_konto_login(self):
        antwort = self.client.get('/admin/', follow=True)
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.request['PATH_INFO'], LOGIN)
        self.assertTemplateNotUsed(antwort, 'admin/login.html')
        self.assertLessEqual(len(antwort.redirect_chain), 2, antwort.redirect_chain)
        self.assertEqual(_next(antwort.redirect_chain[-1][0]), (LOGIN, '/admin/'))

    def test_angemeldeter_nicht_admin_ohne_schleife_auf_startseite(self):
        # Die Schleife waere /admin/ -> /admin/login/ -> /konto/login/?next=/admin/
        # -> /admin/ ... Der Testclient bricht eine echte Schleife mit
        # RedirectCycleError ab; die Obergrenze fuer die Kette faengt auch
        # einen Umweg, der erst spaet zurueckfuehrt.
        self.client.force_login(self.mitfahrer)
        for pfad in ('/admin/', '/admin/login/', '/admin/kern/nutzer/'):
            antwort = self.client.get(pfad, follow=True)
            self.assertEqual(antwort.status_code, 200, pfad)
            self.assertEqual(antwort.request['PATH_INFO'], '/', pfad)
            self.assertLessEqual(len(antwort.redirect_chain), 2, antwort.redirect_chain)
            self.assertContains(antwort, 'Die Verwaltung ist nur für Admins.')
            self.assertNotContains(antwort, 'Verwaltung</a>')

    def test_angemeldeter_admin_auf_admin_login_geht_weiter(self):
        self.client.force_login(self.admin)
        antwort = self.client.get('/admin/login/?next=/admin/kern/nutzer/')
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(antwort['Location'], '/admin/kern/nutzer/')
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_admin_mit_bestaetigter_email_kommt_mit_einer_anmeldung_in_den_admin(self):
        EmailAddress.objects.create(user=self.admin, email=self.admin.email,
                                    verified=True, primary=True)
        # Der Weg, den ein Lesezeichen auf /admin/ nimmt: bis zum Formular ...
        antwort = self.client.get('/admin/', follow=True)
        self.assertEqual(antwort.request['PATH_INFO'], LOGIN)
        # ... und von dort mit dem next, das die Umleitung mitgegeben hat.
        antwort = self.client.post(f'{LOGIN}?next=/admin/',
                                   {'login': 'chef', 'password': KENNWORT, 'next': '/admin/'},
                                   follow=True)
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.request['PATH_INFO'], '/admin/')
        self.assertTemplateUsed(antwort, 'admin/index.html')
        self.assertTemplateNotUsed(antwort, 'admin/login.html')

    def test_admin_ohne_bestaetigte_email_kommt_nicht_hinein(self):
        # Der Grund fuer manage.py email_bestaetigen (README).
        self.client.post(LOGIN, {'login': 'chef', 'password': KENNWORT})
        self.assertNotEqual(self.client.get('/admin/').status_code, 200)


@SCHNELL
class StartseiteRollenTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mitfahrer = _anlegen('mitfahrer')
        cls.admin = _anlegen('chef', is_staff=True)

    def test_admin_sieht_verwaltung(self):
        self.client.force_login(self.admin)
        antwort = self.client.get('/')
        self.assertContains(antwort, 'chef')
        self.assertContains(antwort, '<a href="/admin/">Verwaltung</a>', html=True)

    def test_nicht_admin_sieht_keine_verwaltung(self):
        self.client.force_login(self.mitfahrer)
        antwort = self.client.get('/')
        self.assertContains(antwort, 'mitfahrer')
        self.assertNotContains(antwort, 'Verwaltung')
        self.assertNotContains(antwort, '/admin/')

    def test_anonymer_wird_umgeleitet(self):
        antwort = self.client.get('/')
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(_next(antwort['Location']), (LOGIN, '/'))

    def test_abmelden_ist_post_formular_mit_csrf(self):
        self.client.force_login(self.mitfahrer)
        antwort = self.client.get('/')
        self.assertContains(antwort, 'action="/konto/logout/"')
        self.assertContains(antwort, 'method="post"')
        self.assertContains(antwort, 'name="csrfmiddlewaretoken"')
        self.assertContains(antwort, 'Abmelden')

    def test_abmelden_meldet_ab(self):
        self.client.force_login(self.mitfahrer)
        self.client.post('/konto/logout/')
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_abmelden_mit_csrf_pruefung(self):
        # Der echte Browserweg: Token aus der Startseite, Pruefung scharf.
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.mitfahrer)
        client.get('/')
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/konto/logout/', {'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(client.get('/').status_code, 302)


@SCHNELL
class EmailBestaetigenTest(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='fabian', email='Fabian@Example.org', password=KENNWORT)

    def aufrufen(self, *args):
        ausgabe = StringIO()
        call_command('email_bestaetigen', *args, stdout=ausgabe)
        return ausgabe.getvalue()

    def test_setzt_bestaetigt_und_primaer(self):
        self.assertFalse(EmailAddress.objects.filter(user=self.admin).exists())
        ausgabe = self.aufrufen('fabian')
        eintrag = EmailAddress.objects.get(user=self.admin)
        self.assertEqual(eintrag.email, 'fabian@example.org')
        self.assertTrue(eintrag.verified)
        self.assertTrue(eintrag.primary)
        self.assertIn('bestätigt und primär', ausgabe)

    def test_danach_anmeldung_ueber_konto_login(self):
        self.aufrufen('fabian')
        antwort = self.client.post(LOGIN, {'login': 'fabian', 'password': KENNWORT,
                                           'next': '/admin/'}, follow=True)
        self.assertEqual(antwort.request['PATH_INFO'], '/admin/')
        self.assertEqual(antwort.status_code, 200)

    def test_wiederholbar(self):
        self.aufrufen('fabian')
        self.aufrufen('fabian')
        self.assertEqual(EmailAddress.objects.filter(user=self.admin).count(), 1)

    def test_vorhandener_unbestaetigter_eintrag_wird_bestaetigt(self):
        EmailAddress.objects.create(user=self.admin, email='fabian@example.org')
        self.aufrufen('fabian')
        eintrag = EmailAddress.objects.get(user=self.admin)
        self.assertTrue(eintrag.verified and eintrag.primary)

    def test_andere_adresse_loest_alte_primaere_ab(self):
        self.aufrufen('fabian')
        self.aufrufen('fabian', '--email', 'neu@example.org')
        neu = EmailAddress.objects.get(user=self.admin, email='neu@example.org')
        alt = EmailAddress.objects.get(user=self.admin, email='fabian@example.org')
        self.assertTrue(neu.verified and neu.primary)
        self.assertFalse(alt.primary)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.email, 'neu@example.org')

    def test_unbekannter_nutzer(self):
        with self.assertRaisesMessage(CommandError, 'Kein Nutzer'):
            self.aufrufen('niemand')

    def test_ohne_adresse(self):
        get_user_model().objects.create_user(username='stumm', email='', password=None)
        with self.assertRaisesMessage(CommandError, '--email'):
            self.aufrufen('stumm')

    def test_adresse_bei_anderem_nutzer_bestaetigt(self):
        anderer = get_user_model().objects.create_user(
            username='anderer', email='fabian@example.org', password=None)
        EmailAddress.objects.create(user=anderer, email='fabian@example.org',
                                    verified=True, primary=True)
        with self.assertRaisesMessage(CommandError, 'anderen Nutzer'):
            self.aufrufen('fabian')
        self.assertFalse(EmailAddress.objects.filter(user=self.admin).exists())

    def test_adresse_am_konto_eines_anderen_nutzers(self):
        # Ohne bestaetigte EmailAddress, nur als Nutzer.email (unique):
        # vor der Gegenpruefung ein ungefangener IntegrityError.
        get_user_model().objects.create_user(
            username='anderer', email='belegt@example.org', password=None)
        vorher = self.admin.email
        with self.assertRaisesMessage(CommandError, 'Konto eines anderen Nutzers'):
            self.aufrufen('fabian', '--email', 'Belegt@Example.org')
        self.assertFalse(EmailAddress.objects.filter(user=self.admin).exists())
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.email, vorher)


@SCHNELL
class ClientIpHinterProxyTest(TestCase):
    """
    Hotfix 23.09.2026: Hinter nginx ueber den Unix-Socket ist REMOTE_ADDR leer,
    allauth wirft dann PermissionDenied (403) schon vor der Kennwortpruefung.
    ALLAUTH_TRUSTED_PROXY_COUNT = 1 (settings.py) nimmt die Adresse, die nginx
    rechts an X-Forwarded-For haengt. Der Testclient setzt sonst
    REMOTE_ADDR=127.0.0.1 und verdeckt den Fehler -- deshalb hier leer.
    """
    @classmethod
    def setUpTestData(cls):
        cls.nutzer = _anlegen('mitfahrer')
        EmailAddress.objects.create(user=cls.nutzer, email=cls.nutzer.email,
                                    verified=True, primary=True)

    def test_anmeldung_ueber_socket_mit_xff(self):
        # Links ein vom Client vorgetaeuschter Wert, rechts der von nginx.
        antwort = self.client.post(LOGIN, {'login': 'mitfahrer', 'password': KENNWORT},
                                   REMOTE_ADDR='', HTTP_X_FORWARDED_FOR='1.2.3.4, 5.6.7.8')
        self.assertNotEqual(antwort.status_code, 403)
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.nutzer.pk)

    def test_unbekannter_nutzer_ueber_socket_kein_403(self):
        # So wurde es auf dem Server reproduziert: 403 schon ohne Ratenbegrenzung.
        antwort = self.client.post(LOGIN, {'login': 'niemand', 'password': 'falsch'},
                                   REMOTE_ADDR='', HTTP_X_FORWARDED_FOR='5.6.7.8')
        self.assertEqual(antwort.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_ohne_remote_addr_und_ohne_xff_bleibt_403(self):
        # Absicht: Ohne jede Client-IP kann allauth nicht begrenzen und verweigert.
        # Hinter nginx kommt XFF immer an; wer das hier aendert, oeffnet die
        # Ratenbegrenzung.
        antwort = self.client.post(LOGIN, {'login': 'mitfahrer', 'password': KENNWORT},
                                   REMOTE_ADDR='')
        self.assertEqual(antwort.status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_ohne_xff_weiter_ueber_remote_addr(self):
        # runserver und die uebrigen Tests: kein Proxy, REMOTE_ADDR genuegt.
        antwort = self.client.post(LOGIN, {'login': 'mitfahrer', 'password': KENNWORT})
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.nutzer.pk)
