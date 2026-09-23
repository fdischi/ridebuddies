# Ridebuddies

Eine Web-Plattform, auf der Motorradfahrer Gleichgesinnte für Tagestouren, Reisen, Messen und Trainings finden – nicht per Zufall in Foren, sondern über ein Matching aus Fahrart, Fahrstil, Themen, Verfügbarkeit und räumlicher Nähe.
Kennenlernen zuerst anonym und unverbindlich; jeder bestimmt selbst, wie sichtbar er ist, und gibt Kontaktwege außerhalb der Plattform erst frei, wenn es passt.

**Stand:** in Planung – Datenmodell mit Sichtbarkeitsregeln (App `kern`), Anmeldung über django-allauth, noch keine Oberfläche außer Admin und Login.

## Lizenz

GNU Affero General Public License v3.0 (AGPL-3.0), siehe [LICENSE](LICENSE).

---

Planung: haus/08-Ideen/Ridebuddies.md (internes Notizbuch, nicht öffentlich)

## Lokal starten

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py migrate
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py createsuperuser
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py runserver

Ohne Anmeldung leitet jede Seite auf `/konto/login/` um. Das ist die
einzige Anmeldeseite, auch für die Verwaltung: `/admin/login/` leitet dorthin
weiter und reicht `next` mit (Vorgabe `/admin/`). Admins (`is_staff`) sehen auf
der Startseite den Link „Verwaltung“; wer angemeldet, aber kein Admin ist, landet
von `/admin/` aus auf der Startseite. Die Registrierung ist zu, solange
`RIDEBUDDIES_REGISTRIERUNG_OFFEN=1` nicht gesetzt ist; Mails (E-Mail-Bestätigung)
gehen auf die Konsole.

### Einen neuen Superuser nutzbar machen

`createsuperuser` allein reicht nicht. Die E-Mail-Bestätigung ist Pflicht
(`ACCOUNT_EMAIL_VERIFICATION = 'mandatory'`), und ob eine Adresse bestätigt ist,
steht nicht am Nutzer, sondern in allauths Tabelle `EmailAddress`. Ein frisch
angelegter Superuser hat dort keinen Eintrag – `/konto/login/` lässt ihn nicht
herein, und einen anderen Weg in den Admin gibt es nicht mehr. Deshalb direkt
danach:

    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py createsuperuser
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py email_bestaetigen <nutzername>

`email_bestaetigen` trägt die Adresse des Nutzers als bestätigt und primär ein
(mit `--email adresse` eine andere, die dann auch am Nutzer steht). Es ist
wiederholbar und bricht ab, wenn die Adresse schon bei einem anderen Nutzer
bestätigt ist, oder wenn sie schon am Konto eines anderen Nutzers steht.

**Auf dem Server** (als root, Umgebung wie der Dienst, analog zum
Ausspiel-Rezept aus Schritt 3b):

    cd /srv/ridebuddies && set -a; . /etc/ridebuddies/ridebuddies.env; set +a
    runuser -u ridebuddies -- env RIDEBUDDIES_SECRET_KEY="$RIDEBUDDIES_SECRET_KEY" RIDEBUDDIES_ALLOWED_HOSTS="$RIDEBUDDIES_ALLOWED_HOSTS" RIDEBUDDIES_DATA_DIR="$RIDEBUDDIES_DATA_DIR" RIDEBUDDIES_STATIC_ROOT="$RIDEBUDDIES_STATIC_ROOT" .venv/bin/python manage.py createsuperuser
    runuser -u ridebuddies -- env RIDEBUDDIES_SECRET_KEY="$RIDEBUDDIES_SECRET_KEY" RIDEBUDDIES_ALLOWED_HOSTS="$RIDEBUDDIES_ALLOWED_HOSTS" RIDEBUDDIES_DATA_DIR="$RIDEBUDDIES_DATA_DIR" RIDEBUDDIES_STATIC_ROOT="$RIDEBUDDIES_STATIC_ROOT" .venv/bin/python manage.py email_bestaetigen <nutzername> [--email adresse]

Ohne die Umgebung trifft das Kommando die falsche oder gar keine Datenbank
(ohne `RIDEBUDDIES_SECRET_KEY` startet Django im Betriebsmodus gar nicht).
**Als Benutzer `ridebuddies`, nicht als root:** Was SQLite beim Schreiben
anlegt (`db.sqlite3-journal`, bei leerem Verzeichnis die Datenbank selbst),
gehört sonst root. Der Dienst läuft als `ridebuddies` mit
`ProtectSystem=strict` und darf nur unter `/var/lib/ridebuddies` schreiben; eine
root-eigene Datei dort kann er weder beschreiben noch wegräumen, und die
Anwendung scheitert dann an „attempt to write a readonly database“.

Tests:

    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py test

Wer was von wem sieht, steht in `kern/sichtbarkeit.py`; Zustandswechsel
(Vorschlag, Anfrage, Senken, Beenden, Ausschluss, Feedback) in `kern/ablaeufe.py`.

Im Betrieb kommen `RIDEBUDDIES_SECRET_KEY`, `RIDEBUDDIES_ALLOWED_HOSTS` und
`RIDEBUDDIES_DATA_DIR` (optional `RIDEBUDDIES_STATIC_ROOT`) aus der Umgebung, nie aus dem Repo.

gunicorn lauscht auf einem Unix-Socket, dort ist `REMOTE_ADDR` leer. Die
Client-IP (für allauths Ratenbegrenzung) kommt deshalb aus `X-Forwarded-For`,
das nginx mit `$proxy_add_x_forwarded_for` setzen **muss**
(`ALLAUTH_TRUSTED_PROXY_COUNT = 1` in `settings.py`); fehlt der Header, endet
jede Anmeldung mit 403.
