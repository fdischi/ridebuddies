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

Ohne Anmeldung leitet jede Seite auf `/konto/login/` um – außer `/admin/`
selbst, das auf den eigenen Admin-Login `/admin/login/` leitet (die
Admin-Modellseiten landen wieder auf `/konto/login/`). Die Registrierung ist
zu, solange `RIDEBUDDIES_REGISTRIERUNG_OFFEN=1` nicht gesetzt ist; Mails
(E-Mail-Bestätigung) gehen auf die Konsole.

Tests:

    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py test

Wer was von wem sieht, steht in `kern/sichtbarkeit.py`; Zustandswechsel
(Vorschlag, Anfrage, Senken, Beenden, Ausschluss, Feedback) in `kern/ablaeufe.py`.

Im Betrieb kommen `RIDEBUDDIES_SECRET_KEY`, `RIDEBUDDIES_ALLOWED_HOSTS` und
`RIDEBUDDIES_DATA_DIR` (optional `RIDEBUDDIES_STATIC_ROOT`) aus der Umgebung, nie aus dem Repo.
