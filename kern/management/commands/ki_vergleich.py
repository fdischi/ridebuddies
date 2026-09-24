"""
manage.py ki_vergleich [--anbieter jev claude test] [--mitschnitt DATEI]

Stellt dieselbe feste Beispielanfrage an mehrere KI-Anbieter und gibt die
typisierten Urteile nebeneinander aus (Karte TASK-120.12, Kriterium #4:
"dieselbe Frage laeuft gegen Jev und Claude, Antworten liegen typisiert vor").
Gedacht fuer den ersten Live-Lauf, sobald die Schluessel liegen (TASK-120.11)
- beim Bau NICHT live ausgefuehrt, es gab keine Schluessel.

Die Anfrage ist der Freitext-No-Go-Fall aus dem Pruefblatt: Uwe
(dummy-westerwald-uwe, No-Go "Jeden Abend Hotel – ich schlafe gern im Zelt")
gegen Heinz (dummy-sauerland-heinz, uebernachtet nur in Pension/Hotel).
Laut docs/pruefblatt-matching.md muss das Matching hier einen Konflikt sehen.
Eine Anfrage, alle drei Formen: Noul (Konflikt ja/nein), Auswahl (Heinz'
Unterwegs-Typ) und Stufenwert (Passung beim Uebernachten).

Die Profile gehen OHNE Nutzernamen raus, nur als "A" und "B" - der Anbieter
braucht die Namen nicht. Beide sind Dummies mit KI-Einwilligung; die
Datensperre prueft das trotzdem, wie bei jedem Aufruf. Vorher muss
`manage.py dummies_anlegen` gelaufen sein.

Ohne Schluessel meldet das Kommando den Anbieter als uebersprungen und ruft
ihn nicht auf. Mit --mitschnitt DATEI schneidet es die echten Antworten fuer
den Test-Anbieter mit (ohne Zustand, Fragetext und Schluessel, siehe
kern/urteile/aufzeichnung.py).
"""
from django.core.management.base import BaseCommand, CommandError

from kern import urteile
from kern.models import Profil

ANKER = 'dummy-westerwald-uwe'
KANDIDAT = 'dummy-sauerland-heinz'

# Profilfelder, die fuer die Frage zaehlen. Keine Koordinaten, kein Ort.
FELDER = ('nogo', 'fahrarten', 'tempo', 'tourenformate', 'unterwegs_stil', 'uebernachtung',
          'gruppengroesse', 'themen', 'alkohol_auf_tour')

FRAGEN = {
    'nogo_konflikt': urteile.Noul(
        'Würde eine gemeinsame Tour mit Person B gegen das verstoßen, was Person A '
        'ausdrücklich nicht möchte (`a.nogo`)?',
        wenn_ja='Bs Angaben widersprechen As No-Go direkt oder sehr wahrscheinlich.',
        wenn_nein='Bs Angaben berühren As No-Go nicht oder vereinbaren sich damit.'),
    'unterwegs_typ': urteile.Auswahl(
        'Wie ist Person B unterwegs?',
        {'geniesser': 'lässt sich Zeit, Pausen und Landschaft zählen',
         'streckenfresser': 'will Kilometer machen, Ziel und Strecke zählen',
         'beides': 'mal so, mal so'}),
    'passung_uebernachtung': urteile.Stufenwert(
        'Wie gut passen die Übernachtungswünsche von A und B auf einer Mehrtagestour zusammen?',
        ['schließen sich aus', 'nur mit Kompromiss', 'passen gut']),
}


def _profil_daten(profil):
    return {f: getattr(profil, f) for f in FELDER}


class Command(BaseCommand):
    help = ('Stellt eine feste Beispielfrage über zwei Dummy-Profile an mehrere KI-Anbieter '
            'und zeigt die typisierten Urteile (TASK-120.12).')

    def add_arguments(self, parser):
        parser.add_argument('--anbieter', nargs='+', choices=sorted(urteile.ANBIETER),
                            default=['jev', 'claude'])
        parser.add_argument('--mitschnitt', metavar='DATEI',
                            help='echte Antworten zusätzlich in DATEI aufzeichnen')

    def handle(self, *args, anbieter, mitschnitt, **optionen):
        profile = {p.nutzer.username: p for p in
                   Profil.objects.select_related('nutzer')
                   .filter(nutzer__username__in=[ANKER, KANDIDAT])}
        if set(profile) != {ANKER, KANDIDAT}:
            raise CommandError(f'{ANKER} und {KANDIDAT} fehlen - erst '
                               '`manage.py dummies_anlegen` laufen lassen.')
        a, b = profile[ANKER], profile[KANDIDAT]
        zustand = {'a': _profil_daten(a), 'b': _profil_daten(b)}

        fehler = 0
        for name in anbieter:
            a_obj = urteile.anbieter_nach_name(name, mitschnitt=mitschnitt)
            if not a_obj.schluessel_vorhanden():
                self.stdout.write(f'{name}: kein Schlüssel ({a_obj.schluessel_variable} oder '
                                  f'{a_obj.schluessel_variable}_DATEI) – übersprungen, '
                                  'nichts gesendet.')
                continue
            try:
                with urteile.mit_anbieter(a_obj):
                    ergebnis = urteile.beurteilen_mehrere(zustand, FRAGEN,
                                                          betrifft=[a.nutzer, b.nutzer])
            except urteile.UrteilFehler as f:
                fehler += 1
                self.stdout.write(f'{name}: Fehler – {f}')
                continue
            self.stdout.write(f'{name}:')
            for kennung, u in ergebnis.items():
                self.stdout.write('  ' + zeile(kennung, u))
        if fehler:
            raise CommandError(f'{fehler} Anbieter mit Fehler.')


def zeile(kennung, u):
    wert = f'{u.wert:.3f}' if isinstance(u.wert, float) else u.wert
    verteilung = ', '.join(f'{k}={v:.2f}' for k, v in u.wahrscheinlichkeiten.items())
    return (f'{kennung} [{u.form}] Wert {wert} · Vertrauen {u.vertrauen:.2f} '
            f'({u.vertrauen_quelle}) · {verteilung} · Modell {u.modell} · '
            f'Tokens {u.tokens_ein}/{u.tokens_aus}')
