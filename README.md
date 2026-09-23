# Ridebuddies

Eine Web-Plattform, auf der Motorradfahrer Gleichgesinnte für Tagestouren, Reisen, Messen und Trainings finden – nicht per Zufall in Foren, sondern über ein Matching aus Fahrart, Fahrstil, Themen, Verfügbarkeit und räumlicher Nähe.
Kennenlernen zuerst anonym und unverbindlich; jeder bestimmt selbst, wie sichtbar er ist, und gibt Kontaktwege außerhalb der Plattform erst frei, wenn es passt.

**Stand:** in Planung – Datenmodell mit Sichtbarkeitsregeln (App `kern`), Anmeldung über django-allauth, Dummy-Bestand mit Prüfblatt fürs Matching, noch keine Oberfläche außer Admin und Login.

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

### Dummy-Bestand

`dummies_anlegen` legt einen festen Bestand zum Prüfen an (Karte TASK-120.05):
37 Dummies mit Profil, drei Crews, fünf Ausfahrten und zwei Reisen in der Saison
2027 mit Terminabstimmung, Beiträge, Verbindungen, Ridebuddies und zwei
Ausschlüsse. Kein Zufall – die Werte stehen wörtlich in `kern/dummies.py`, und
`docs/pruefblatt-matching.md` sagt, welche Vorschläge das Matching für acht
Anker-Profile machen muss und welche nie.

Dummies erkennt man an zwei Merkmalen zugleich: Nutzername beginnt mit `dummy-`
**und** E-Mail endet auf `@example.invalid`. Ihre Adresse ist bestätigt und
primär, sonst ließe `/konto/login/` sie nicht herein.

    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py dummies_anlegen
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py dummies_anlegen --kennwort-datei /pfad/zur/datei
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py dummies_anlegen --abraeumen

- **Ohne Option** legt es an, was fehlt, und gleicht an, was vom Bestand im Code
  abweicht. Ein zweiter Lauf ändert nichts („Nichts geschrieben“). Neue Dummies
  haben kein nutzbares Kennwort; ein schon gesetztes bleibt stehen.
- **`--kennwort-datei PFAD`** setzt das Kennwort aus der ersten Zeile der Datei
  für alle Dummies – nur dort, wo das gespeicherte nicht passt. `PFAD` = `-`
  liest es von der Standardeingabe (so auf dem Server, siehe unten). Es wird nie
  ausgegeben und muss Djangos Kennwortregeln genügen. Eine Datei statt eines
  Arguments, weil ein Argument in der Shell-History und in `ps` stünde. Die
  Datei gehört nicht ins Repo; eine für Gruppe oder andere zugängliche Datei
  gibt einen Hinweis (`chmod 600`). Alle Dummies teilen sich einen Hash – bei
  Wegwerfkonten mit gemeinsamem Kennwort gewollt, weil jeder PBKDF2-Lauf auf
  VM 140 über eine Sekunde kostet.
- **`--abraeumen`** löscht alle Dummies samt allem, was an ihnen hängt, und die
  Crews und Ausfahrten, an denen **nur** Dummies beteiligt sind. Echte Konten
  bleiben, auch wenn sie mit einem Dummy verbunden waren (die Verbindung
  verschwindet). Sitzt ein echter Nutzer in einer Dummy-Crew, bleibt die Crew
  mit ihren Ausfahrten stehen, nur ohne die Dummies.

Alles läuft in einer Transaktion. Bricht es ab – etwa weil ein echter Nutzer
schon `dummy-schotter-sven` heißt –, bleibt die Datenbank, wie sie war.

**Auf dem Server** mit derselben Umgebung wie bei `email_bestaetigen` (siehe oben)
und aus demselben Grund als Benutzer `ridebuddies`. Vorher `migrate` – der
Bestand braucht die Koordinatenfelder aus
`kern/migrations/0002_profil_koordinaten.py`.

Das Kennwort wird **auf dem Server erzeugt und bleibt dort** – root-eigen, 0600,
nicht in Git, Vault oder Karte. Fabian liest es selbst aus; die Dummies bleiben
damit für die Browser-Prüfungen in Schritt 12/13 anmeldbar. Übergeben wird es
über die Standardeingabe: root öffnet die Datei, `ridebuddies` liest nur den
geerbten Dateideskriptor. Die Datei muss dafür nie für `ridebuddies` lesbar
werden. (`--kennwort-datei /dev/stdin` geht unter `runuser` **nicht** – das
öffnet die Datei über `/proc/self/fd/0` neu, mit den Rechten von `ridebuddies`,
und scheitert mit „Permission denied“.)

    cd /srv/ridebuddies && set -a; . /etc/ridebuddies/ridebuddies.env; set +a
    install -d -m 700 /root/.config/ridebuddies
    test -s /root/.config/ridebuddies/dummy-kennwort || (umask 077; openssl rand -base64 18 > /root/.config/ridebuddies/dummy-kennwort)
    runuser -u ridebuddies -- env RIDEBUDDIES_SECRET_KEY="$RIDEBUDDIES_SECRET_KEY" RIDEBUDDIES_ALLOWED_HOSTS="$RIDEBUDDIES_ALLOWED_HOSTS" RIDEBUDDIES_DATA_DIR="$RIDEBUDDIES_DATA_DIR" RIDEBUDDIES_STATIC_ROOT="$RIDEBUDDIES_STATIC_ROOT" .venv/bin/python manage.py dummies_anlegen --kennwort-datei - < /root/.config/ridebuddies/dummy-kennwort
    stat -c '%a %U' /var/lib/ridebuddies/db.sqlite3    # erwartet: 640 ridebuddies

Das `test -s` davor verhindert, dass ein zweiter Aufruf ein neues Kennwort
würfelt, das Fabian dann nicht kennt. Zeigt `stat` etwas anderes als
`640 ridebuddies`: `chmod 640 /var/lib/ridebuddies/db.sqlite3` – `migrate` hat
die Datenbank beim Neuanlegen schon einmal mit 0644 angelegt (Vault-Nachtrag
zu Schritt 4, Server `enduro-web`).

Abräumen dort genauso, mit `dummies_anlegen --abraeumen` statt
`--kennwort-datei - < …`. Die Kennwortdatei bleibt dabei liegen.

### Terminfindung

`terminfindung` zeigt für eine Ausfahrt oder Reise je Kandidaten-Termin einen
Prozentwert, wer fehlt, wer mit Vorbehalt kommt und wer noch nicht geantwortet
hat (Karte TASK-120.06). Das ist Rechnen, keine KI; es liest nur. Die Logik
steht in `kern/terminfindung.py`, samt Begründung jeder Regel im Modulkopf.

    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py terminfindung <ID oder Teil des Titels>

    Enduro-Grundlagentraining (ID 2, Crew Schotterbande Siegburg)
    Nenner: 5
    Sa 08.05.2027 vormittags – 70 % – fehlt: dummy-eifel-rainer – Vorbehalt: dummy-schotter-tim – keine Antwort: –
    Sa 15.05.2027 vormittags – 70 % – fehlt: dummy-schotter-mehmet – Vorbehalt: dummy-eifel-rainer – keine Antwort: –

Passen mehrere Titel, bricht es ab und nennt sie mit ID. Die Regeln – die
ersten vier von Fabian entschieden (23.09.2026), der Rest Festlegung:

- **Nenner** einer Crew-Ausfahrt sind alle Mitgliedschaften der Crew, **Gäste
  eingeschlossen**. Ohne Crew: alle Teilnahmen plus wer vorgeschlagen hat
  (Festlegung).
- **Gewicht:** sicher 1, mit Vorbehalt 0,5 (`VORBEHALT_GEWICHT`), nein 0.
- **Keine Antwort** zählt 0 und bleibt im Nenner, steht aber getrennt unter
  „keine Antwort“, nicht unter „fehlt“.
- **Reisen** (Termin mit `bis_datum`): der schlechteste Tag zählt – nein vor
  keine Antwort (ein nicht abgedeckter Tag) vor Vorbehalt vor sicher.
- Die Antwort zu **dieser** Ausfahrt geht vor der allgemeinen Verfügbarkeit
  desselben Tages und derselben Tageszeit; Antworten zu anderen Ausfahrten
  zählen nicht. Tagestermine lesen nur die Einträge je Tag und Tageszeit,
  Reisen nur Zeiträume – ein Zeitraum zählt bei einem Tagestermin also nicht,
  auch ein „nein“ nicht (Festlegung). Ein Termin ohne Tageszeit gilt für den ganzen Tag: die
  schlechteste der drei Tageszeiten. Eine abgesagte Teilnahme heißt „fehlt“.
- Gerechnet wird exakt (Bruch), angezeigt auf ganze Prozent **kaufmännisch**
  gerundet (62,5 → 63; Pythons `round()` gäbe 62). Sortiert wird nach dem
  exakten Wert, bei Gleichstand nach Datum und Tageszeit. Ist niemand
  beteiligt, steht „– %“.

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
