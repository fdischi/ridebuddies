# Ridebuddies

Eine Web-Plattform, auf der Motorradfahrer Gleichgesinnte für Tagestouren, Reisen, Messen und Trainings finden – nicht per Zufall in Foren, sondern über ein Matching aus Fahrart, Fahrstil, Themen, Verfügbarkeit und räumlicher Nähe.
Kennenlernen zuerst anonym und unverbindlich; jeder bestimmt selbst, wie sichtbar er ist, und gibt Kontaktwege außerhalb der Plattform erst frei, wenn es passt.

**Stand:** in Planung – Datenmodell mit Sichtbarkeitsregeln (App `kern`), Anmeldung über django-allauth, Dummy-Bestand mit Prüfblatt fürs Matching, Terminfindung, KI-Urteils-Schnittstelle mit Datensperre (noch ohne Live-Lauf), noch keine Oberfläche außer Admin und Login.

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

### KI-Urteile

`kern/urteile/` ist die austauschbare Schnittstelle zu den KI-Anbietern
(Karte TASK-120.12). Das Matching ruft nur `kern.urteile.beurteilen(...)` auf
und kennt den Anbieter nicht. Drei Urteilsformen wie bei Jev: `Noul`
(ja/nein-Wahrscheinlichkeit), `Auswahl` (feste Optionen) und `Stufenwert`
(2–10 geordnete Stufen). Das Ergebnis ist ein typisiertes Urteil mit Wert,
Vertrauen, Verteilung, Anbieter, gemeldetem Modell und Tokens.

| Variable | Bedeutung |
|---|---|
| `RIDEBUDDIES_KI_ANBIETER` | `jev`, `claude` oder `test` (Voreinstellung `test`: kein Netz, neutrale Antworten oder Aufzeichnung) |
| `RIDEBUDDIES_KI_FREIGABE` | `nutzername:email` – genau ein echtes Konto (Fabians), das außer Dummies an die KI darf; leer = nur Dummies, eine Liste bricht den Start ab |
| `RIDEBUDDIES_JEV_SCHLUESSEL` / `…_DATEI` | Jev-Schlüssel direkt oder als Pfad (erste Zeile) |
| `RIDEBUDDIES_ANTHROPIC_SCHLUESSEL` / `…_DATEI` | Anthropic-Schlüssel direkt oder als Pfad |
| `RIDEBUDDIES_JEV_MODELL`, `RIDEBUDDIES_CLAUDE_MODELL` | Voreinstellung `jev-latest` bzw. `claude-haiku-4-5` |
| `RIDEBUDDIES_KI_ZEITLIMIT` | Sekunden je HTTP-Versuch (über 0, höchstens 600), Voreinstellung 30 |
| `RIDEBUDDIES_KI_AUFZEICHNUNG` | JSON-Datei, aus der der Test-Anbieter antwortet |
| `RIDEBUDDIES_KI_MITSCHNITT` | JSON-Datei, in die ein echter Anbieter jede Antwort mitschreibt: Hash und Urteil, ohne Zustand, Anweisung, Stufen- oder Optionsbeschreibungen und Schlüssel; die Optionsnamen einer Auswahl stehen als Schlüssel der Verteilung drin |

Schlüssel liegen nie im Repo: auf enduro-web in `/etc/ridebuddies/ridebuddies.env`,
auf VM 140 unter `~/.config/ridebuddies/` (0600) über die `_DATEI`-Variante.
Fehlt der Schlüssel, wird nichts gesendet (`SchluesselFehlt`).

**Datensperre** (Fabian, 23.09.2026): Jeder Aufruf nennt die betroffenen Nutzer
(`betrifft=[…]`, Pflicht). Durch kommt nur, wer Dummy ist (`dummy-` **und**
`@example.invalid`) oder das freigegebene Konto (Name **und** E-Mail) – und in
beiden Fällen eine aktive Einwilligung „KI-Auswertung“ hat. Sonst
`DatensperreVerletzt`, und kein Anbieter wird gefragt, auch nicht der
Test-Anbieter. Die Sperre sitzt im Einstieg und zusätzlich in jedem Anbieter
(`beantworten(…, betrifft=…)`), hält also auch einen direkten Aufruf auf.
Eine Einwilligung zählt erst ab ihrem Erteilungszeitpunkt.

Das Protokoll (Logger `ridebuddies.urteile`, ab INFO auf stderr, auf
enduro-web also im Journal von `ridebuddies.service`; Fabian, 24.09.2026)
enthält nur Anbieter, Modell, Kennung, Form, Dauer, Tokens, Anzahl der
Betroffenen und Fehlerart – keinen Zustand, keinen Namen, keine ID.

`ki_vergleich` stellt dieselbe feste Frage (Uwes Freitext-No-Go gegen Heinz,
alle drei Formen) an Jev und Claude und zeigt die Urteile nebeneinander.
Ohne Schlüssel meldet es den Anbieter als übersprungen. Vorher muss
`dummies_anlegen` gelaufen sein.

    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py ki_vergleich
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py ki_vergleich --anbieter test
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py ki_vergleich --mitschnitt docs/ki-aufzeichnung.json

### Matching

`kern/matching/` rechnet Vorschläge **je Anker** (Karte TASK-120.13, Schritt 8).
Es gibt keinen Aufruf ohne Anker, keine Rangliste über alle und keine
gespeicherte Punktzahl (Fabian, 24.09.2026).

    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py matching_urteile --nur-zaehlen
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py matching_urteile --anbieter test --aufzeichnung docs/ki-aufzeichnung-jev.json
    RIDEBUDDIES_DEBUG=1 .venv/bin/python manage.py vorschlaege dummy-westerwald-uwe [--anzahl 5] [--alle]
    # live, schneidet mit:
    RIDEBUDDIES_DEBUG=1 RIDEBUDDIES_JEV_SCHLUESSEL_DATEI=~/.config/ridebuddies/jev \
      .venv/bin/python manage.py matching_urteile --anbieter jev --mitschnitt docs/ki-aufzeichnung-jev.json

`matching_urteile` holt nur fehlende oder veraltete Urteile und speichert sie
(`PaarUrteil`, `MerkmalUrteil`, Migration `0003_matching_urteile`). `vorschlaege`
liest nur gespeicherte Urteile und fragt keinen Anbieter (`--holen` fragt nach).
`--alle` zeigt Ausgeschlossene mit Grund. Das ist ein Betreiberwerkzeug, die
Gründe verraten Profilwerte.

Die beiden Aufzeichnungen `docs/ki-aufzeichnung-{jev,claude}.json` enthalten
neben den Paarurteilen (f3) und den Regeln der Fassung r2 auch noch die
Regel-Einträge der verworfenen Fassung r1. Sie werden nicht mehr abgefragt und
sind harmlos (nur Hash und Urteil); sie bleiben, damit ältere Messungen
nachvollziehbar sind.

**Ablauf je Kandidat:** Grundmenge (aktives Konto mit aktiver KI-Einwilligung)
→ harte Filter nach den Lesarten des Prüfblatts, beidseitig (`filter.py`) →
weiche Merkmale, die eine Seite auf „hart“ gestellt hat (`dimensionen.py`) →
No-Go (`nogo.py`) → Punktzahl aus den weichen Merkmalen des Ankers.
Gleichstand: Entfernung, dann Nutzername.

**No-Go, zwei Bausteine, beide hart:**
1. *Regeln je Person:* Einmal je No-Go-Inhaber fragt eine Anfrage je
   Ausprägung eines **Verhaltensmerkmals** (Alkohol auf Tour, Schutzkleidung),
   ob schon diese Angabe gegen das No-Go verstößt. Den Abgleich mit dem
   Gegenüber rechnet der Code. Stilmerkmale (Tempo, Unterwegs, Erfahrung,
   Gruppe) haben seit der Fassung r2 (25.09.2026) keine Regeln mehr. Ein No-Go
   gegen einen Fahrstil meint fast immer eine Kombination, und die sieht nur
   das Paarurteil.
2. *Paarurteil:* Je Richtung eine Frage mit As No-Go, As und Bs Merkmalen
   (Fassung `f3`, Stufenwert, 0..1 umgerechnet).

Fehlt ein Urteil oder ist es veraltet, fällt der Kandidat mit `nogo_offen`
heraus. Das hat Fabian am 25.09.2026 entschieden: „Rausfallen, bis nachgeholt.“ Die Folge:
Fällt der Anbieter aus, bekommen Personen mit No-Go und ihre Gegenüber
vorübergehend keine Vorschläge füreinander, bis `matching_urteile` nachgeholt
hat. Ist der Regel-Baustein für einen Anbieter abgeschaltet, wird er weder
geholt noch als offen gewertet. Ein KI-Urteil legt nie einen `Ausschluss` an.
Für einen Anbieter ohne vermessene Schwelle gibt es keinen Ersatzwert, sondern
den Fehler `SchwelleFehlt`.

| Konstante | Wert | wo |
|---|---|---|
| `GEWICHTE` | Fahrart 3 · Tempo 2 · Unterwegs 2 · Tourenformat 1,5 · Themen 1,5 · Erfahrung 1 · Sicherheit 1 · Motorrad 0 · Region 2 (nur wenn weich) | `ranking.py` |
| `SCHWELLEN` (Paarurteil) | jev 0,37 · claude 0,73 · test 0,5 (nur feste Vorgaben in Tests) | `nogo.py` |
| `REGEL_SCHWELLEN` | jev 0,31 · claude abgeschaltet · test 0,5 | `nogo.py` |
| `RUNDUNG_KM` | 5 (unter 5 km: „unter 5 km“) | `ranking.py` |
| `NEUTRAL` | 0,5 für „keine Angabe“ in der Punktzahl | `dimensionen.py` |

**Festlegungen (nicht von Fabian entschieden, umwerfbar):**
- Geschlechtspräferenz und Alterswunsch auf „weich“ gestellt = ohne Wirkung.
  Grund: Fabians Regel „nur als Nutzerwunsch-Filter, nie als weiche Bewertung“.
- Was „hart“ bei einem weichen Merkmal heißt (mindestens ein gemeinsamer Wert,
  gleiches Tempo usw.): `dimensionen.py`, Modulkopf. Fehlende Angabe = besteht.
- Wiedervorlage: „nicht jetzt“ bei Vorschlag oder Verbindung sperrt das Paar bis
  `wiedervorlage_ab`. Die Ausnahme „wesentliche Profiländerung“ ist nicht gebaut.
- Die Begründung nennt Werte des Kandidaten nur, wenn sein Feld auf „öffentlich“
  steht. Sicherheit (voreingestellt „verbunden“) bekommt keinen wertenden Text.
  Geschlecht und Alter kommen in der Begründung nie vor.
- Der No-Go-Zustand enthält keine Namen, kein Geschlecht, kein Alter, keinen Ort
  und **keine Beiträge**. Beiträge kommen in Schritt 9, mit eigenem Nachweis.
  Die Begründung zeigt davon nie etwas (`nogo.py`, Modulkopf).
- Motorrad hat das Gewicht 0: Es ist Freitext, und ohne Katalog lässt es sich nicht vergleichen.
- Regeln gibt es nur für Verhaltensmerkmale mit Einfachwahl. Bei Mehrfachwahl
  wie „Pension, Hotel“ ist offen, ob ein verbotener Wert reicht.
- `Bewertung.intern_entfernung_km` ist ungerundet und nur intern (Sortierung,
  Betreiberkommando). Nutzer bekommen nur `begruendung['region']`.
- Ein Urteil je Richtung und Dimension. Ist es veraltet, wird es überschrieben. Der Anbieter
  gehört nicht zum Schlüssel; nach einem Anbieterwechsel `matching_urteile --neu`.
- Claude antwortet mit Temperatur 0 und ohne `strict`. Die API lehnt `strict` zusammen mit `minimum`/`maximum`
  ab (Probe am 25.09.2026, HTTP 400). Näheres im Modulkopf von `kern/urteile/claude.py`.

**Ergebnis gegen das Prüfblatt** (`kern/tests/test_matching.py`, offline): Mit
`docs/ki-aufzeichnung-jev.json` stimmt das Blatt vollständig: alle Muss-Kandidaten in den ersten fünf,
kein Nie-Kandidat zulässig, fern-bernd und fern-hanna leer, 17 Grenzfälle
wie im Blatt. Mit `docs/ki-aufzeichnung-claude.json` weicht es an acht
erklärten Stellen ab (`ABWEICHUNGEN_CLAUDE` im Test): Claude Haiku 4.5 trennt
die Freitextfälle Heinz und Sabine nicht von Muss-Paaren und erkennt Ninas
strenges Alkohol-No-Go nicht.

**Fragefassungen** (Entwicklungssatz aus 30 gerichteten Paaren, live am
24./25.09.2026; Werte = Konfliktwert 0..1):

| Fassung | Anbieter | Muss max | Marco→Sabine | Uwe→Heinz | Nina→Sven | Nina→Jonas | Nina→Mehmet | Nina→Anja |
|---|---|---|---|---|---|---|---|---|
| f0 (Frage aus `ki_vergleich`) | jev | 0,380 | 0,330 | 0,330 | 0,260 | 0,330 | 0,700 | 0,280 |
| f0 | claude | 0,950 | 0,150 | 0,950 | 0,050 | 0,050 | 0,950 | 0,050 |
| f1 (+ „sinngemäß lesen“) | jev | 0,480 | 0,500 | 0,290 | 0,320 | 0,310 | 0,730 | 0,280 |
| f1 | claude | 0,950 | 0,150 | 0,950 | 0,050 | 0,050 | 0,850 | 0,050 |
| f2 (+ As Merkmale) | jev | 0,320 | 0,340 | 0,680 | 0,270 | 0,260 | 0,540 | 0,330 |
| f2 | claude | 0,150 | 0,150 | 0,850 | 0,150 | 0,150 | 0,750 | 0,750 |
| **f3** (Stufenwert, gültig) | jev | 0,340 | 0,398 | 0,820 | 0,338 | 0,315 | 0,595 | 0,385 |
| **f3** | claude | 0,725 | 0,650 | 0,725 | 0,637 | 0,600 | 0,575 | 0,700 |
| f4 (Noul, Text wie f3) | jev | 0,290 | 0,300 | 0,750 | 0,220 | 0,220 | 0,370 | 0,240 |
| f4 | claude | 0,150 | 0,150 | 0,050 | 0,750 | 0,750 | 0,750 | 0,850 |
| f5 (f3 + „außerhalb des Fahrens“) | jev | 0,412 | 0,403 | 0,865 | 0,318 | 0,370 | 0,603 | 0,407 |
| f6 („wörtlich und eng“, verworfen) | jev | 0,335 | 0,328 | 0,690 | – | – | – | – |

Jev trennt nur mit f3 beide Freitextfälle von allen Muss-Paaren, und das mit schmaler
Lücke (0,340 gegen 0,398). Keine Fassung trennt Ninas „erst nach der Fahrt“.
Daher kommen die Regeln je Person (Baustein 1). Mit ihnen sieht Jev das:
in der geltenden Fassung r2 Nina „nach der Fahrt“ 0,41, „egal“ 0,70 und Petra
„egal“ 0,53; der höchste Nicht-Treffer liegt bei 0,21 (Luca „egal“), Schwelle
0,31. (In der verworfenen r1: Nina 0,42/0,65 gegen Marcos harmlose Treffer
0,30/0,29.)
Alle Fassungen stehen in `nogo.FASSUNGEN`, auch die verworfenen.

**Regelfassungen:** r1 fragte alle sechs Einfachwahl-Merkmale ab und ist verworfen.
Jev gab dort Svens No-Go „Autobahnetappen“ gegen „Streckenfresser“ 0,45 und schloss damit
über die Regel Oliver, Kevin und Sabine aus. r2 fragt nur die Verhaltensmerkmale
ab (Live-Lauf 25.09.2026, 10 Anfragen je Anbieter). Jev: Nina „nach der Fahrt“
0,41, „egal“ 0,70, Petra „egal“ 0,53, der höchste Nicht-Treffer 0,21, Schwelle
0,31. Claude bleibt unbrauchbar (Gabi, No-Go Rauchen, bekommt Alkohol „nie“ 1,0).
`RegelAusschluesseTest` prüft über alle Anker, dass eine Regel nur dort
ausschließt, wo das Prüfblatt eine nennt (`nogo_regeln`). Gegen r1 schlägt der
Test fehl, und zwar an Sven und „Streckenfresser“.

**Ausschlüsse über das Paarurteil, die nicht im Prüfblatt stehen** (Jev, Stand
25.09.2026; das Blatt sagt zu ihnen nichts, sie sind also keine Fehler gegen
das Blatt, aber eine Lesart des Modells):

| Anker | fällt über das Paarurteil heraus | Wert |
|---|---|---|
| Sven („Autobahnetappen, nur um Strecke zu machen“) | Kevin, Sabine, Oliver, Stefan, Dirk | 0,690 · 0,630 · 0,600 · 0,388 · 0,383 |
| Marco | Uwe (Uwes No-Go gegen Marcos „nur Hotel“) | 0,860 |
| Anja („ungefragte Belehrungen“) | Sabine, Ayse | 0,415 · 0,383 |
| Nina | Uwe (Uwes No-Go) | 0,777 |
| Uwe („jeden Abend Hotel“) | Marco, Jens, Robin, Kevin, Sabine, Nina, Mehmet | 0,860 … 0,520 |
| Luca („Wheelies und Rasen“) | Kevin, Tim, Jonas, Lea | 0,603 · 0,585 · 0,480 · 0,430 |
| Frank, fern-bernd, fern-hanna | niemand | – |

Uwes Ausschlüsse sind in sich stimmig: Alle Genannten übernachten nur in Pension oder Hotel. Svens Dirk und Stefan
(0,383/0,388) liegen knapp über der Schwelle 0,37.

**Bekannte Schwäche, hingenommen** (Fabian, 25.09.2026: „eine neue Paarfassung,
sonst hinnehmen“). Der eine Versuch f6 („wörtlich und eng lesen“) ist verworfen.
Vorher festgelegte Regel: f6 ersetzt f3 nur, wenn mit Jev (a) das Prüfblatt voll erfüllt
bleibt, (b) die ungedeckten Ausschlüsse weniger werden und (c) die Lücke
zwischen höchstem Muss-Paar und niedrigerem Freitext-Nie-Fall nicht unter 0,058
fällt. Auf dem Entwicklungssatz (32 Paare, Jev) lag Marco→Sabine bei 0,328,
also unter dem höchsten Muss-Paar Uwe→Gabi (0,335). Die Lücke ist damit
−0,007, und (a) und (c) sind verfehlt. (b) wäre erreicht gewesen (Svens fünf
0,278–0,438, Lucas vier 0,270–0,420, Anjas zwei 0,270/0,273). Der Volllauf
fand deshalb nicht statt. Die Tabelle oben bleibt als bekannte Schwäche von f3 stehen.

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
