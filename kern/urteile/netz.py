"""
HTTP fuer die KI-Anbieter - nur Standardbibliothek (urllib), keine neue
Abhaengigkeit in requirements.txt (Karte TASK-120.12).

WIEDERHOLEN: Jev nennt 429 (Ratenlimit) und 529 (ueberlastet) als "mit
exponentiellem Backoff wiederholen" (api.md, Abschnitt Errors). Anthropic
kennt dieselben beiden plus 500er bei eigenen Stoerungen; fuer Claude
wiederholen wir deshalb 429, 529 und jedes 5xx. 401 und 422 wiederholen wir
nie - das wird beim zweiten Mal nicht besser und kostet nur Zeit.

Festlegungen (nicht von Fabian entschieden):
- Hoechstens 3 Wiederholungen (4 Versuche), Wartezeit 1 s, 2 s, 4 s. Schickt
  der Anbieter Retry-After in Sekunden, gilt der, aber hoechstens 30 s. Der
  schlimmste Fall ist damit rund 4 * Zeitlimit + 90 s - fuer einen Lauf im
  Hintergrund (Matching, Schritt 8) vertretbar, fuer eine Webanfrage nicht.
  Urteile gehoeren deshalb nicht in den Request-Zyklus.
- Netz- und Zeitfehler (keine Verbindung, Zeitlimit) werden NICHT wiederholt:
  Ein haengender Anbieter soll den Lauf nicht viermal das Zeitlimit kosten.
- Den Antwortkoerper eines Fehlers lesen wir nicht in die Ausnahme (siehe
  kern/urteile/fehler.py - er kann den Zustand wiederholen).
"""
import json
import socket
import time
import urllib.error
import urllib.request

from .fehler import AnbieterFehler

MAX_WIEDERHOLUNGEN = 3
BACKOFF_SEKUNDEN = (1, 2, 4)
RETRY_AFTER_HOECHSTENS = 30


def _warten_fuer(fehler, versuch):
    kopf = fehler.headers.get('Retry-After') if fehler.headers else None
    if kopf:
        try:
            return max(0.0, min(float(kopf), RETRY_AFTER_HOECHSTENS))
        except ValueError:
            pass  # HTTP-Datum statt Sekunden - dann unser eigener Backoff
    return BACKOFF_SEKUNDEN[min(versuch, len(BACKOFF_SEKUNDEN) - 1)]


def post_json(url, kopf, nutzlast, *, zeitlimit, wiederholen_bei, schlafen=time.sleep):
    """POST mit JSON, gibt (antwort_dict, versuche) zurueck.

    `wiederholen_bei`: Funktion status -> bool. `schlafen` ist fuer die Tests
    austauschbar, damit sie nicht wirklich warten."""
    daten = json.dumps(nutzlast, ensure_ascii=False).encode('utf-8')
    versuch = 0
    while True:
        versuch += 1
        anfrage = urllib.request.Request(url, data=daten, method='POST',
                                         headers={**kopf, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(anfrage, timeout=zeitlimit) as antwort:
                roh = antwort.read()
        except urllib.error.HTTPError as fehler:
            status = fehler.code
            fehler.close()
            if wiederholen_bei(status) and versuch <= MAX_WIEDERHOLUNGEN:
                schlafen(_warten_fuer(fehler, versuch - 1))
                continue
            raise AnbieterFehler(f'http_{status}', versuch) from None
        except (TimeoutError, socket.timeout):
            raise AnbieterFehler('zeitlimit', versuch) from None
        except urllib.error.URLError as fehler:
            if isinstance(fehler.reason, (TimeoutError, socket.timeout)):
                raise AnbieterFehler('zeitlimit', versuch) from None
            raise AnbieterFehler('netz', versuch) from None
        try:
            return json.loads(roh.decode('utf-8')), versuch
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AnbieterFehler('antwortformat', versuch) from None
