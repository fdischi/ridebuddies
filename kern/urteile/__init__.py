"""
KI-Urteile fuer das Matching - Schritt 7 des Plans (Karte TASK-120.12, 23.09.2026).

Plan-Notiz haus/08-Ideen/Ridebuddies.md, Sammelkarte TASK-120.07. Das
Matching (Schritt 8) soll den KI-Anbieter tauschen koennen - Jev und Claude
jetzt, womoeglich Mistral fuer echte Nutzer nach Schritt 14a -, ohne dass
sich im Matching-Code etwas aendert. Deshalb gibt es genau EINEN Einstieg:

    from kern import urteile
    u = urteile.beurteilen(zustand, urteile.Noul('Verletzt B das No-Go von A?'),
                           kennung='nogo_konflikt', betrifft=[a, b])
    u.wert, u.vertrauen, u.anbieter, u.modell

Welcher Anbieter antwortet, sagt die Einstellung RIDEBUDDIES_KI_ANBIETER
(jev | claude | test, Voreinstellung test - ohne Netz sicher; siehe
ridebuddies/settings.py). Der Aufrufer kennt ihn nicht und soll ihn nicht
kennen.

DIE REIHENFOLGE IN beurteilen_mehrere() IST DER KERN DIESER KARTE:
 1. Kennungen und Fragen pruefen (Programmierfehler frueh, ohne Anbieter).
 2. DATENSPERRE (sperre.py) - wer nicht darf, loest DatensperreVerletzt aus,
    und es wird KEIN Anbieter auch nur geholt. Entscheidung Fabians vom
    23.09.2026: nur Dummies und das freigegebene Konto, und nur mit aktiver
    KI-Einwilligung.
 3. Anbieter holen und fragen. Dessen beantworten() prueft die Sperre ein
    ZWEITES Mal (anbieter.py) - damit haelt sie auch, wer am Einstieg vorbei
    `urteiler().beantworten(...)` aufruft (Auflage der Gegenpruefung,
    24.09.2026).
 4. Protokoll.

PROTOKOLL OHNE PERSONENDATEN (Logger 'ridebuddies.urteile'): Anbieter, Modell,
Kennung(en), Form(en), Dauer, Tokens, Anzahl der Betroffenen, Ergebnis bzw.
Fehlerart. NIE Zustand, Fragetext, Nutzername, E-Mail oder Nutzer-ID - auch
nicht als Zahl. Die Kennung ist deshalb auf ein enges Muster beschraenkt
(formen.KENNUNG_MUSTER), und von unerwarteten Ausnahmen protokollieren wir
nur den Klassennamen, nie die Meldung. Belegt in kern/tests/test_urteile.py.

TESTS UND WERKZEUGE setzen einen Anbieter mit `mit_anbieter(a)` ein (ein
contextvars-Ersatz, der nur im eigenen Kontext gilt). Die Sperre gilt dann
genauso - sie haengt nicht am Anbieter.
"""
import contextlib
import contextvars
import functools
import logging
import time

from django.conf import settings

from . import sperre
from .anbieter import Anbieter
from .aufzeichnung import Aufzeichner, TestAnbieter
from .claude import ClaudeAnbieter
from .fehler import AnbieterFehler, DatensperreVerletzt, SchluesselFehlt, UrteilFehler
from .formen import (
    FRAGEFORMEN,
    Auswahl,
    AuswahlUrteil,
    Noul,
    NoulUrteil,
    StufenUrteil,
    Stufenwert,
    Urteil,
    kennung_pruefen,
)
from .jev import JevAnbieter

__all__ = [
    'Anbieter', 'AnbieterFehler', 'Auswahl', 'AuswahlUrteil', 'DatensperreVerletzt',
    'Noul', 'NoulUrteil', 'SchluesselFehlt', 'StufenUrteil', 'Stufenwert', 'Urteil',
    'UrteilFehler', 'anbieter_nach_name', 'beurteilen', 'beurteilen_mehrere',
    'mit_anbieter', 'urteiler',
]

log = logging.getLogger('ridebuddies.urteile')

ANBIETER = {'jev': JevAnbieter, 'claude': ClaudeAnbieter, 'test': TestAnbieter}

_ersatz = contextvars.ContextVar('kern_urteile_anbieter', default=None)


def anbieter_nach_name(name, *, mitschnitt=None):
    """Frischer Anbieter nach Name, optional mit Mitschnitt in eine Datei.
    Fuer den Einstieg und fuer manage.py ki_vergleich - nicht fuer das Matching."""
    if name not in ANBIETER:
        raise ValueError('Unbekannter Anbieter.')
    if name == 'test':
        pfad = getattr(settings, 'RIDEBUDDIES_KI_AUFZEICHNUNG', '')
        anbieter = TestAnbieter(aufzeichnung=pfad or None)
    else:
        anbieter = ANBIETER[name]()
    if mitschnitt and name != 'test':
        anbieter = Aufzeichner(anbieter, mitschnitt)
    return anbieter


@functools.lru_cache(maxsize=8)
def _aus_einstellung(name, aufzeichnung, mitschnitt):
    # Die Werte sind Teil des Cache-Schluessels, damit override_settings in
    # Tests einen neuen Anbieter bekommt. Gecacht wird, damit der Test-Anbieter
    # seine Aufrufe ueber mehrere beurteilen() hinweg zaehlt und die
    # Aufzeichnung nicht bei jeder Frage neu gelesen wird.
    return anbieter_nach_name(name, mitschnitt=mitschnitt or None)


def urteiler():
    """Der Anbieter, der jetzt antwortet: ein mit mit_anbieter() gesetzter,
    sonst der aus der Einstellung."""
    ersatz = _ersatz.get()
    if ersatz is not None:
        return ersatz
    return _aus_einstellung(getattr(settings, 'RIDEBUDDIES_KI_ANBIETER', 'test'),
                            getattr(settings, 'RIDEBUDDIES_KI_AUFZEICHNUNG', ''),
                            getattr(settings, 'RIDEBUDDIES_KI_MITSCHNITT', ''))


@contextlib.contextmanager
def mit_anbieter(anbieter):
    """Setzt `anbieter` fuer die Dauer des with-Blocks (Tests, Kommandos)."""
    if not isinstance(anbieter, Anbieter):
        raise TypeError('mit_anbieter erwartet einen Anbieter.')
    marke = _ersatz.set(anbieter)
    try:
        yield anbieter
    finally:
        _ersatz.reset(marke)


def beurteilen(zustand, frage, *, kennung, betrifft, ohne_personen=False):
    """Eine Frage, ein Urteil. `betrifft` ist Pflicht: die Nutzer, deren Daten
    im Zustand oder in der Frage stecken. Leer nur mit ohne_personen=True."""
    return beurteilen_mehrere(zustand, {kennung: frage}, betrifft=betrifft,
                              ohne_personen=ohne_personen)[kennung]


def beurteilen_mehrere(zustand, fragen, *, betrifft, ohne_personen=False):
    """Mehrere Fragen zum selben Zustand in EINER Anfrage (Jev kann das
    nativ und rechnet dann einmal ab). Gibt dict Kennung -> Urteil zurueck."""
    # 1. Programmierfehler - ohne Anbieter, ohne Protokoll von Inhalten.
    if not isinstance(fragen, dict) or not fragen:
        raise ValueError('fragen: nicht-leeres dict Kennung -> Frage erwartet.')
    for kennung, frage in fragen.items():
        kennung_pruefen(kennung)
        if not isinstance(frage, FRAGEFORMEN):
            raise TypeError('Frage muss Noul, Auswahl oder Stufenwert sein.')
    kennungen = ','.join(fragen)
    formen = ','.join(f.form for f in fragen.values())
    # Einmal in eine Liste: Sperre im Einstieg UND in der Grundklasse lesen sie,
    # ein Generator waere beim zweiten Mal leer (und damit gesperrt).
    betrifft = list(betrifft)

    # 2. Datensperre - VOR dem Holen des Anbieters.
    try:
        betroffene = sperre.pruefen(betrifft, ohne_personen=ohne_personen)
    except DatensperreVerletzt as fehler:
        log.warning('urteil gesperrt kennung=%s form=%s betroffene=%d gruende=%s',
                    kennungen, formen, fehler.betroffene,
                    ','.join(f'{g}:{n}' for g, n in sorted(fehler.gruende.items())))
        raise

    # 3. Anbieter fragen.
    anbieter = urteiler()
    beginn = time.monotonic()
    try:
        urteile = anbieter.beantworten(zustand, fragen, betrifft=betrifft,
                                       ohne_personen=ohne_personen)
    except UrteilFehler as fehler:
        log.warning('urteil fehler anbieter=%s kennung=%s form=%s betroffene=%d '
                    'dauer_ms=%d art=%s', anbieter.name, kennungen, formen, betroffene,
                    _ms(beginn), fehler.art)
        raise
    except Exception as fehler:
        # Nur der Klassenname - die Meldung koennte Inhalte tragen.
        log.error('urteil fehler anbieter=%s kennung=%s form=%s betroffene=%d '
                  'dauer_ms=%d art=intern:%s', anbieter.name, kennungen, formen,
                  betroffene, _ms(beginn), type(fehler).__name__)
        raise

    # 4. Protokoll.
    erstes = next(iter(urteile.values()))
    log.info('urteil ok anbieter=%s modell=%s kennung=%s form=%s betroffene=%d '
             'dauer_ms=%d tokens_ein=%d tokens_aus=%d', anbieter.name, erstes.modell,
             kennungen, formen, betroffene, _ms(beginn), erstes.tokens_ein, erstes.tokens_aus)
    return urteile


def _ms(beginn):
    return int((time.monotonic() - beginn) * 1000)
