"""
Claude (Anthropic Messages API) als Urteils-Anbieter (Karte TASK-120.12).

Claude kennt Jevs drei Fragetypen nicht. Wir bilden sie mit einem
ERZWUNGENEN WERKZEUGAUFRUF nach: ein Werkzeug `urteil_abgeben`, dessen
JSON-Schema je Frage die Verteilung verlangt (Noul: eine Zahl p fuer "ja";
Auswahl: je Option eine Wahrscheinlichkeit; Stufenwert: je Stufenindex eine),
und `tool_choice = {"type": "tool", "name": "urteil_abgeben"}`, damit Claude
nicht in Prosa ausweicht. Aus der Verteilung rechnet formen.py Wert und
Vertrauen nach derselben Formel wie Jev (confidence.md).

WICHTIG FUER JEDEN, DER DIE ZAHLEN VERGLEICHT: Claudes Wahrscheinlichkeiten
sind SELBST BERICHTET - das Modell schreibt Zahlen in ein Formular. Sie sind
nicht aus Token-Wahrscheinlichkeiten abgeleitet und nicht kalibriert; eine
0,8 von Claude und eine 0,8 von Jev bedeuten nicht dasselbe. Wir normieren
Claudes Verteilung auf Summe 1, weil selbst berichtete Zahlen nicht immer
genau aufgehen. Das `vertrauen` ist deshalb immer 'berechnet'.

Vertrag (Anthropic-Doku, Stand Wissensstand des Baus, NICHT live geprueft):
    POST https://api.anthropic.com/v1/messages
    x-api-key: <key>, anthropic-version: 2023-06-01
    {"model": ..., "max_tokens": ..., "system": ..., "messages": [...],
     "tools": [{"name", "description", "input_schema"}],
     "tool_choice": {"type": "tool", "name": ...}}
    -> {"model": "claude-haiku-4-5-...", "content": [{"type": "tool_use",
        "name": ..., "input": {...}}], "usage": {"input_tokens", "output_tokens"}}
Weicht die echte Antwort ab, wirft auswerten() AnbieterFehler('antwortformat').

Die Kennungen des Aufrufers gehen NICHT ins Schema; die Fragen heissen dort
f1, f2, ... - wie bei Jev, wo die Frage-ID nicht ins Modell geht. Sonst
koennte ein sprechender Name ('nogo_konflikt') das Urteil faerben.

Festlegungen (nicht von Fabian entschieden): Modell per
RIDEBUDDIES_CLAUDE_MODELL, Voreinstellung claude-haiku-4-5 (billig, schnell,
fuer Einzelurteile genug - ob es fuer deutschen Freitext taugt, klaert der
Jev-Befund in Schritt 8). max_tokens 1024.

TEMPERATUR 0 (geaendert 24./25.09.2026, TASK-120.13; vorher Standard mit der
Begruendung "wir wollen Claudes Einschaetzung, keine kuenstlich geschaerfte").
Festlegung (nicht von Fabian entschieden), Anlass: Das Matching speichert
Urteile und spielt sie aus einer Aufzeichnung ab. Ein zweiter Lauf mit
derselben Frage soll dieselbe Zahl liefern, sonst ist ein Unterschied zwischen
zwei Fragefassungen nicht vom Wuerfeln zu trennen. Die Zahl ist ohnehin eine
SELBST BERICHTETE Wahrscheinlichkeit, keine Stichprobe - die Temperatur macht
sie nicht "ehrlicher", nur schwankender. Voll deterministisch ist auch 0 bei
Anthropic nicht zugesichert.

NICHT UEBERNOMMEN aus der Anthropic-Doku (gelesen 24.09.2026, TASK-120.13):
- `strict: true` am Werkzeug: siehe STRICT unten.
- Prompt Caching: Der Mindestpraefix fuer Haiku 4.5 sind 4096 Tokens; eine
  ganze Anfrage hier hat rund 1000-2000. Ein cache_control wuerde nur
  scheinbar wirken (messbar waere es an usage.cache_read_input_tokens = 0).
- Batch-API (50 % billiger, asynchron): bei wenigen Dutzend bis gut hundert
  Anfragen je Lauf lohnt der zweite Weg nicht.
- Offizielles SDK statt urllib: bewusst nicht (Schritt 7, netz.py: keine neue
  Abhaengigkeit). Offener Punkt, kein Umbau.

STRICT: Nicht gesetzt. Live geprueft am 25.09.2026 mit einem festen
Beispieltext (keine Personendaten): `strict: true` zusammen mit unserem Schema
-> HTTP 400 "For 'number' type, properties maximum, minimum are not supported";
ohne minimum/maximum nimmt die API strict an. Wir behalten minimum/maximum
(sie sagen dem Modell den Wertebereich) und verzichten auf strict: Der Zwang
zum Werkzeug (tool_choice) haelt schon heute, und was trotzdem aus dem Bereich
faellt, faengt formen.py ab (AnbieterFehler 'antwortformat' bzw. Normieren).
In TASK-120.11 und im Mitschnitt fuer Schritt 8 gab es keinen Formatfehler.
"""
import json

from django.conf import settings

from . import netz
from .anbieter import Anbieter, schluessel_lesen
from .fehler import AnbieterFehler
from .formen import Auswahl, Noul, Stufenwert, urteil_aus_verteilung

URL = 'https://api.anthropic.com/v1/messages'
API_VERSION = '2023-06-01'
WERKZEUG = 'urteil_abgeben'
MAX_TOKENS = 1024
TEMPERATUR = 0


def _wiederholen(status):
    return status in (429, 529) or 500 <= status <= 599


SYSTEM = (
    'Du bist ein sorgfältiger Gutachter. Du bekommst einen Zustand (Text oder '
    'strukturierte Daten) und nummerierte Fragen. Beurteile jede Frage NUR anhand '
    'des Zustands und gib dein Urteil ausschließlich über das Werkzeug '
    f'`{WERKZEUG}` ab.\n'
    'Fragetypen:\n'
    '- noul: ja/nein. Gib die Wahrscheinlichkeit an, dass die Antwort ja ist '
    '(0 = sicher nein, 1 = sicher ja). `kriterien.true`/`kriterien.false` sagen, '
    'was ja und nein bedeuten.\n'
    '- choice: genau eine der Optionen trifft zu. Verteile Wahrscheinlichkeiten '
    'über alle Optionen (Summe 1).\n'
    '- score: geordnete Stufen, Index 0 zuerst. Verteile Wahrscheinlichkeiten '
    'über die Stufenindizes (Summe 1).\n'
    'Drücke Unsicherheit ehrlich aus: Gibt der Zustand für eine Frage wenig her, '
    'verteile die Wahrscheinlichkeit breit, statt zu raten.'
)


def _schema_fuer(frage):
    zahl = {'type': 'number', 'minimum': 0, 'maximum': 1}
    if isinstance(frage, Noul):
        return {**zahl, 'description': 'Wahrscheinlichkeit für ja'}
    if isinstance(frage, Auswahl):
        schluessel = list(frage.optionen)
    elif isinstance(frage, Stufenwert):
        schluessel = [str(i) for i in range(len(frage.stufen))]
    else:
        raise TypeError('Unbekannte Frageform.')
    return {'type': 'object', 'properties': {k: dict(zahl) for k in schluessel},
            'required': schluessel, 'additionalProperties': False,
            'description': 'Wahrscheinlichkeit je Option/Stufe, Summe 1'}


class ClaudeAnbieter(Anbieter):
    name = 'claude'
    schluessel_variable = 'RIDEBUDDIES_ANTHROPIC_SCHLUESSEL'

    def __init__(self, modell=None, zeitlimit=None, url=URL, schlafen=None):
        self.modell = modell or getattr(settings, 'RIDEBUDDIES_CLAUDE_MODELL', 'claude-haiku-4-5')
        self.zeitlimit = zeitlimit or getattr(settings, 'RIDEBUDDIES_KI_ZEITLIMIT', 30)
        self.url = url
        self._schlafen = schlafen

    @staticmethod
    def _namen(fragen):
        """Kennung -> neutraler Name f1, f2, ... in fester Reihenfolge."""
        return {k: f'f{i}' for i, k in enumerate(fragen, start=1)}

    def nutzlast(self, zustand, fragen):
        namen = self._namen(fragen)
        beschreibung = []
        for kennung, frage in fragen.items():
            d = frage.als_dict()
            eintrag = {'id': namen[kennung], 'typ': d['type'], 'anweisung': d['instructions']}
            if 'criteria' in d:
                eintrag['kriterien'] = d['criteria']
            if isinstance(frage, Stufenwert):
                eintrag['kriterien'] = {str(i): s for i, s in enumerate(frage.stufen)}
            beschreibung.append(eintrag)
        zustand_text = zustand if isinstance(zustand, str) else \
            json.dumps(zustand, ensure_ascii=False, indent=1)
        text = (f'<zustand>\n{zustand_text}\n</zustand>\n\n'
                f'<fragen>\n{json.dumps(beschreibung, ensure_ascii=False, indent=1)}\n</fragen>')
        schema = {'type': 'object',
                  'properties': {namen[k]: _schema_fuer(f) for k, f in fragen.items()},
                  'required': list(namen.values()), 'additionalProperties': False}
        return {
            'model': self.modell,
            'max_tokens': MAX_TOKENS,
            'temperature': TEMPERATUR,
            'system': SYSTEM,
            'messages': [{'role': 'user', 'content': text}],
            'tools': [{'name': WERKZEUG,
                       'description': 'Gibt je Frage die Wahrscheinlichkeitsverteilung ab.',
                       'input_schema': schema}],
            'tool_choice': {'type': 'tool', 'name': WERKZEUG},
        }

    def _beantworten(self, zustand, fragen):
        schluessel = schluessel_lesen(self.schluessel_variable)
        extra = {'schlafen': self._schlafen} if self._schlafen else {}
        antwort, _ = netz.post_json(
            self.url, {'x-api-key': schluessel, 'anthropic-version': API_VERSION},
            self.nutzlast(zustand, fragen), zeitlimit=self.zeitlimit,
            wiederholen_bei=_wiederholen, **extra)
        return self.auswerten(antwort, fragen)

    def auswerten(self, antwort, fragen):
        namen = self._namen(fragen)
        try:
            modell = antwort['model']
            nutzung = antwort.get('usage') or {}
            tokens_ein = int(nutzung.get('input_tokens') or 0)
            tokens_aus = int(nutzung.get('output_tokens') or 0)
            bloecke = [b for b in antwort['content']
                       if b.get('type') == 'tool_use' and b.get('name') == WERKZEUG]
            if len(bloecke) != 1 or not isinstance(modell, str):
                raise AnbieterFehler('antwortformat')
            eingabe = bloecke[0]['input']
            return {k: urteil_aus_verteilung(f, eingabe[namen[k]], anbieter=self.name,
                                             modell=modell, tokens_ein=tokens_ein,
                                             tokens_aus=tokens_aus)
                    for k, f in fragen.items()}
        except (KeyError, TypeError, ValueError, AttributeError):
            raise AnbieterFehler('antwortformat') from None
