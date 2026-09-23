# Ridebuddies

Eine Web-Plattform, auf der Motorradfahrer Gleichgesinnte für Tagestouren, Reisen, Messen und Trainings finden – nicht per Zufall in Foren, sondern über ein Matching aus Fahrart, Fahrstil, Themen, Verfügbarkeit und räumlicher Nähe.
Kennenlernen zuerst anonym und unverbindlich; jeder bestimmt selbst, wie sichtbar er ist, und gibt Kontaktwege außerhalb der Plattform erst frei, wenn es passt.

**Stand:** in Planung – Django-Grundgerüst mit Platzhalter-Startseite.

## Lizenz

GNU Affero General Public License v3.0 (AGPL-3.0), siehe [LICENSE](LICENSE).

---

Planung: haus/08-Ideen/Ridebuddies.md (internes Notizbuch, nicht öffentlich)

## Lokal starten

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py migrate
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py runserver

Im Betrieb kommen `RIDEBUDDIES_SECRET_KEY`, `RIDEBUDDIES_ALLOWED_HOSTS` und
`RIDEBUDDIES_DATA_DIR` (optional `RIDEBUDDIES_STATIC_ROOT`) aus der Umgebung, nie aus dem Repo.
