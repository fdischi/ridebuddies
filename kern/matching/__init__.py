"""
Matching - Schritt 8 des Plans (Karte TASK-120.13, 24.09.2026).

Plan-Notiz haus/08-Ideen/Ridebuddies.md, Schritt 8; gepruefte Erwartung:
docs/pruefblatt-matching.md (Lesarten von Fabian bestaetigt am 23.09.2026).

    filter.py       harte Filter nach den Lesarten, beidseitig
    dimensionen.py  weiche Merkmale, im Code gerechnet, mit Begruendung
    nogo.py         No-Go-Freitext als KI-Urteil, gespeichert (PaarUrteil)
    ranking.py      Grundmenge, Punktzahl, Vorschlaege JE ANKER

Einstieg: vorschlaege(anker, anzahl=5). Es gibt bewusst keine Funktion ohne
Anker (keine Rangliste ueber alle - Fabian, 24.09.2026).
"""
from .ranking import (  # noqa: F401
    GEWICHTE,
    Bewertung,
    KeineEinwilligung,
    alle_bewertungen,
    bewerten,
    entfernung_text,
    grundmenge,
    noetige_nogo_paare,
    vorschlaege,
)
