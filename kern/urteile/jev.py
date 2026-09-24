"""
Jev (TypeSafe System One) als Urteils-Anbieter (Karte TASK-120.12).

Vertrag aus der Doku api.md (heruntergeladen 23.09.2026, docs.typesafe.ai):

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer <API_KEY>
    {"state": ..., "model": "jev-latest",
     "questions": {"<id>": {"type": "noul"|"choice"|"score",
                            "instructions": ..., "criteria": ...}}}
    -> {"model": "jev-1.13.0",
        "answers": {"<id>": {"type": "noul", "noul": 0.95}
                          | {"type": "choice", "choice": "...",
                             "probabilities": {...}, "confidence": 0.81}
                          | {"type": "score", "score": 1.05, "legend": {...},
                             "probabilities": {"0": ...}, "confidence": 0.92}},
        "usage": {"input_tokens": 296, "output_tokens": 20}}

UNGEPRUEFT: Das ist die Form laut Doku. Einen echten Aufruf gab es beim Bau
noch nicht (Schluessel fehlt, TASK-120.11). Die Tests pruefen gegen die
Doku-Beispiele. Weicht die echte Antwort ab, wirft _urteil() AnbieterFehler
('antwortformat') statt still Unsinn zu liefern - beim ersten Live-Lauf
(manage.py ki_vergleich) also die rohe Antwort ansehen, bevor man hier etwas
"repariert".

Die Frage-ID geht laut Doku nicht ins Modell; wir schicken die Kennung des
Aufrufers (eine Konstante wie 'nogo_konflikt') unveraendert als ID.
"""
from django.conf import settings

from . import netz
from .anbieter import Anbieter, schluessel_lesen
from .fehler import AnbieterFehler
from .formen import (
    Auswahl,
    AuswahlUrteil,
    Noul,
    NoulUrteil,
    StufenUrteil,
    Stufenwert,
    _zahl,
)

URL = 'https://api.typesafe.ai/v1/systemone'
WIEDERHOLEN = {429, 529}


class JevAnbieter(Anbieter):
    name = 'jev'
    schluessel_variable = 'RIDEBUDDIES_JEV_SCHLUESSEL'

    def __init__(self, modell=None, zeitlimit=None, url=URL, schlafen=None):
        self.modell = modell or getattr(settings, 'RIDEBUDDIES_JEV_MODELL', 'jev-latest')
        self.zeitlimit = zeitlimit or getattr(settings, 'RIDEBUDDIES_KI_ZEITLIMIT', 30)
        self.url = url
        self._schlafen = schlafen

    def nutzlast(self, zustand, fragen):
        return {'state': zustand, 'model': self.modell,
                'questions': {k: f.als_dict() for k, f in fragen.items()}}

    def _beantworten(self, zustand, fragen):
        schluessel = schluessel_lesen(self.schluessel_variable)
        extra = {'schlafen': self._schlafen} if self._schlafen else {}
        antwort, _ = netz.post_json(
            self.url, {'Authorization': f'Bearer {schluessel}'},
            self.nutzlast(zustand, fragen), zeitlimit=self.zeitlimit,
            wiederholen_bei=lambda s: s in WIEDERHOLEN, **extra)
        return self.auswerten(antwort, fragen)

    def auswerten(self, antwort, fragen):
        # Jev liefert laut Doku Verteilungen mit Summe 1. Wir normieren sie NICHT
        # nach - was Jev sagt, steht unveraendert im Urteil (anders als bei
        # Claude, siehe claude.py).
        try:
            modell = antwort['model']
            antworten = antwort['answers']
            nutzung = antwort.get('usage') or {}
            tokens_ein = int(nutzung.get('input_tokens') or 0)
            tokens_aus = int(nutzung.get('output_tokens') or 0)
            if not isinstance(modell, str) or not isinstance(antworten, dict):
                raise AnbieterFehler('antwortformat')
            return {k: self._urteil(f, antworten[k], modell, tokens_ein, tokens_aus)
                    for k, f in fragen.items()}
        except (KeyError, TypeError, ValueError, AttributeError):
            raise AnbieterFehler('antwortformat') from None

    def _urteil(self, frage, a, modell, tokens_ein, tokens_aus):
        gemeinsam = dict(anbieter=self.name, modell=modell,
                         tokens_ein=tokens_ein, tokens_aus=tokens_aus)
        if a.get('type') != frage.form:
            raise AnbieterFehler('antwortformat')
        if isinstance(frage, Noul):
            p = _zahl(a['noul'])
            if not 0.0 <= p <= 1.0:
                raise AnbieterFehler('antwortformat')
            # Jev liefert fuer Noul kein Vertrauen - berechnet, siehe formen.py.
            return NoulUrteil(wert=p, vertrauen=abs(2 * p - 1), vertrauen_quelle='berechnet',
                              wahrscheinlichkeiten={'ja': p, 'nein': 1 - p}, **gemeinsam)
        vertrauen = _zahl(a['confidence'])
        if isinstance(frage, Auswahl):
            probs = {k: _zahl(v) for k, v in a['probabilities'].items()}
            if a['choice'] not in frage.optionen or set(probs) - set(frage.optionen):
                raise AnbieterFehler('antwortformat')
            return AuswahlUrteil(wert=a['choice'], vertrauen=vertrauen,
                                 vertrauen_quelle='anbieter', wahrscheinlichkeiten=probs,
                                 **gemeinsam)
        if isinstance(frage, Stufenwert):
            probs = {str(k): _zahl(v) for k, v in a['probabilities'].items()}
            if set(probs) - {str(i) for i in range(len(frage.stufen))}:
                raise AnbieterFehler('antwortformat')
            # Legende wie geliefert; fehlt sie, aus der Frage.
            legende = {str(k): v for k, v in (a.get('legend') or {}).items()} or \
                {str(i): s for i, s in enumerate(frage.stufen)}
            return StufenUrteil(wert=_zahl(a['score']), vertrauen=vertrauen,
                                vertrauen_quelle='anbieter', wahrscheinlichkeiten=probs,
                                legende=legende, **gemeinsam)
        raise TypeError('Unbekannte Frageform.')

