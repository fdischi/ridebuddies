"""
Datensperre vor jedem KI-Anbieteraufruf (Karte TASK-120.12).

ENTSCHIEDEN (Fabian, 23.09.2026, Einlesen der Sammelkarte TASK-120.07,
Entscheidung 1): Solange kein Anbieter mit AV-Vertrag entschieden ist
(Schritt 14a der Plan-Notiz), gehen NUR Dummy-Konten und Fabians eigenes
Profil an Jev oder Claude - beides US-Dienste ohne AV-Vertrag. Jedes andere
echte Konto wird nie uebermittelt, "im Code erzwungen, nicht nur in der
Abfrage". Zusaetzlich gilt die KI-Einwilligung des Profils.

ENTSCHIEDEN (Fabian, 23.09.2026, Einlesen TASK-120.12): Fabians Konto wird
ueber die Umgebungsvariable RIDEBUDDIES_KI_FREIGABE benannt, Format
`nutzername:email` - GENAU EIN Konto. Nutzername UND E-Mail muessen beide
passen. Nicht gesetzt = nur Dummies. (Ein Komma, also ein Versuch, mehrere
Konten freizugeben, bricht den Start ab - ridebuddies/settings.py.)

Durchgelassen wird ein Nutzer also nur, wenn BEIDES gilt:
 1. Dummy (Nutzername beginnt mit `dummy-` UND E-Mail endet auf
    `@example.invalid`, dieselben Konstanten wie kern/dummies.py) ODER das
    freigegebene Konto (Name exakt, E-Mail ohne Gross/Klein - letzteres
    Festlegung, nicht von Fabian entschieden).
 2. Aktive Einwilligung Art KI_AUSWERTUNG (widerrufen_am leer, erteilt_am
    nicht in der Zukunft - Festlegung, siehe unten) - auch fuer
    Dummies und Fabian. Robin (dummy-ohne-angabe-robin) hat keine und bleibt
    deshalb draussen, obwohl er ein Dummy ist.

WO DIE SPERRE SITZT: zweimal. Im gemeinsamen Einstieg
(kern/urteile/__init__.py, beurteilen()), VOR der Wahl des Anbieters - dort
wird auch protokolliert. Und in der Grundklasse aller Anbieter
(anbieter.py, beantworten()), damit auch ein direkter Aufruf
`urteiler().beantworten(...)` nicht am Einstieg vorbei ins Netz kommt
(Auflage der Gegenpruefung, 24.09.2026). Auch der Test-Anbieter und der
Aufzeichner laufen hindurch, damit die Tests zeigen, was im Betrieb gilt.

Festlegungen (nicht von Fabian entschieden):
- Geprueft wird der Stand in der DATENBANK, nicht das uebergebene Objekt. Ein
  im Speicher umbenanntes Nutzerobjekt ("dummy-..." gesetzt, nicht
  gespeichert) oder ein ungespeichertes (pk None) kommt so nicht durch.
- Nutzernamen-Praefix gross/klein-GENAU. Djangos `startswith` ist auf SQLite
  in Wahrheit ein LIKE und damit ohne Gross/Klein ("Dummy-Hans" passte in
  ist_dummy_q()). Wir nehmen ist_dummy_q() fuer die Abfrage und pruefen das
  Praefix danach noch einmal in Python. Die E-Mail vergleichen wir ohne
  Gross/Klein - Domains sind es ohnehin nicht.
- Leere Betroffenen-Liste ist eine Sperre, kein Freibrief. Wer wirklich ohne
  Personendaten fragt (etwa ein fester Beispieltext), sagt das ausdruecklich
  mit `ohne_personen=True`.
- Ob die Liste VOLLSTAENDIG ist - ob im Zustand also nur Daten der genannten
  Nutzer stecken -, kann die Sperre nicht sehen. Das bleibt Vertrag des
  Aufrufers; die Pflicht, sie zu nennen, macht ihn nur sichtbar.
- Eine Einwilligung zaehlt erst ab `erteilt_am` (Auflage der Gegenpruefung,
  24.09.2026). Ein Datensatz mit Zeitpunkt in der Zukunft - vorausdatiert,
  falsche Zeitzone, Tippfehler im Admin - ist heute noch keine Einwilligung.
- is_active spielt keine Rolle: Ein deaktivierter Dummy ist immer noch ein
  Dummy, ein deaktiviertes Freigabe-Konto immer noch Fabians. Ein anderes
  echtes Konto kommt so oder so nicht durch - die Frage aendert an der
  Sperre nichts.
"""
from collections import Counter

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from kern.dummies import DOMAIN, PRAEFIX, ist_dummy_q
from kern.models import Einwilligung

from .fehler import DatensperreVerletzt

GRUND_NICHT_ZUGELASSEN = 'kein_dummy_und_nicht_freigegeben'
GRUND_KEINE_EINWILLIGUNG = 'keine_ki_einwilligung'
GRUND_UNGESPEICHERT = 'nicht_gespeichert'
GRUND_KEINE_BETROFFENEN = 'keine_betroffenen_benannt'


def _freigabe():
    """(nutzername, email_klein) oder None - in settings.py schon geparst."""
    return getattr(settings, 'RIDEBUDDIES_KI_FREIGABE', None) or None


def _ist_dummy(nutzer):
    """Python-Gegenstueck zu ist_dummy_q(), aber mit gross/klein-genauem Praefix."""
    return nutzer.username.startswith(PRAEFIX) and nutzer.email.lower().endswith(DOMAIN)


def _ist_freigegeben(nutzer, freigabe):
    if freigabe is None:
        return False
    name, mail = freigabe
    return nutzer.username == name and nutzer.email.lower() == mail


def gruende(betrifft):
    """Counter Grund -> Anzahl Nutzer; leer heisst: alle duerfen.
    Jeder Nutzer zaehlt hoechstens einmal, mit dem ersten zutreffenden Grund."""
    Nutzer = get_user_model()
    betrifft = list(betrifft)
    for n in betrifft:
        if not isinstance(n, Nutzer):
            # Kein Nutzerobjekt (etwa eine nackte ID) - Programmierfehler.
            raise TypeError('betrifft erwartet Nutzer-Objekte.')
    zaehler = Counter()
    zaehler[GRUND_UNGESPEICHERT] += sum(1 for n in betrifft if n.pk is None)
    pks = {n.pk for n in betrifft if n.pk is not None}

    abfrage = Nutzer.objects.filter(pk__in=pks)
    frisch = {n.pk: n for n in abfrage}
    dummy_pks = set(abfrage.filter(ist_dummy_q()).values_list('pk', flat=True))
    freigabe = _freigabe()

    zugelassen = set()
    for pk in pks:
        n = frisch.get(pk)
        if n is None:
            # pk gesetzt, aber nicht (mehr) in der Datenbank.
            zaehler[GRUND_UNGESPEICHERT] += 1
        elif (pk in dummy_pks and _ist_dummy(n)) or _ist_freigegeben(n, freigabe):
            zugelassen.add(pk)
        else:
            zaehler[GRUND_NICHT_ZUGELASSEN] += 1

    mit_einwilligung = set(
        Einwilligung.objects.filter(nutzer_id__in=zugelassen,
                                    art=Einwilligung.Art.KI_AUSWERTUNG,
                                    erteilt_am__lte=timezone.now(),
                                    widerrufen_am__isnull=True)
        .values_list('nutzer_id', flat=True))
    zaehler[GRUND_KEINE_EINWILLIGUNG] += len(zugelassen - mit_einwilligung)
    return +zaehler


def pruefen(betrifft, *, ohne_personen=False):
    """Wirft DatensperreVerletzt, wenn auch nur einer nicht darf. Gibt die
    Zahl der Betroffenen zurueck (fuer das Protokoll - Anzahl, keine IDs)."""
    betrifft = list(betrifft)
    if ohne_personen:
        if betrifft:
            raise ValueError('ohne_personen=True, aber betrifft ist nicht leer.')
        return 0
    if not betrifft:
        raise DatensperreVerletzt({GRUND_KEINE_BETROFFENEN: 1}, 0)
    befund = gruende(betrifft)
    anzahl = len({n.pk for n in betrifft if n.pk is not None}) + \
        sum(1 for n in betrifft if n.pk is None)
    if befund:
        raise DatensperreVerletzt(befund, anzahl)
    return anzahl
