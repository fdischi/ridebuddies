"""
manage.py matching_urteile [--anbieter jev|claude|test] [--mitschnitt DATEI]
                           [--aufzeichnung DATEI] [--neu] [--nur-zaehlen]

Holt die KI-Urteile, die das Matching braucht, und speichert sie (PaarUrteil,
MerkmalUrteil) - Karte TASK-120.13 (Schritt 8, 24./25.09.2026).

Welche: (1) die No-Go-Regeln jeder Person der Grundmenge mit No-Go - eine
Anfrage je Person; (2) je gerichtetem Paar ein Paarurteil, wenn das Paar alle
harten Code-Filter besteht und der Urheber ein No-Go hat
(matching.noetige_nogo_paare). Aktuelle Urteile werden nicht neu geholt;
`--neu` holt alles neu (etwa nach einem Anbieterwechsel, siehe PaarUrteil).

    --anbieter jev|claude   live; Schluessel ueber RIDEBUDDIES_*_SCHLUESSEL(_DATEI)
    --mitschnitt DATEI      die echten Antworten zusaetzlich aufzeichnen
                            (Hash und Urteil, kein Zustand - aufzeichnung.py)
    --anbieter test --aufzeichnung DATEI
                            offline aus einer Aufzeichnung, STRENG: fehlt eine
                            Antwort, zaehlt das als Fehler statt als neutral
    --nur-zaehlen           nichts fragen, nur sagen, wie viele Anfragen es waeren
    --nur-regeln            nur die Regeln je Person (etwa nach einer neuen
                            Regelfassung), keine Paarurteile

Die Datensperre gilt wie bei jedem Urteil (kern/urteile/sperre.py): Ausser
Dummies und dem freigegebenen Konto geht niemand an einen Anbieter. Gesperrte
Paare zaehlt die Zusammenfassung; sie bleiben im Ranking 'nogo_offen'.
Ausgegeben werden nur Anzahlen, Tokens und Dauer - keine Namen, keine Werte.
"""
from django.core.management.base import BaseCommand, CommandError

from kern import matching, urteile
from kern.matching import nogo
from kern.urteile.aufzeichnung import TestAnbieter


class Command(BaseCommand):
    help = 'Holt und speichert die KI-Urteile fürs Matching (TASK-120.13).'

    def add_arguments(self, parser):
        parser.add_argument('--anbieter', choices=sorted(urteile.ANBIETER), default=None,
                            help='Voreinstellung: RIDEBUDDIES_KI_ANBIETER')
        parser.add_argument('--mitschnitt', metavar='DATEI')
        parser.add_argument('--aufzeichnung', metavar='DATEI',
                            help='nur mit --anbieter test: antwortet streng aus DATEI')
        parser.add_argument('--neu', action='store_true', help='auch aktuelle Urteile neu holen')
        parser.add_argument('--nur-zaehlen', action='store_true')
        parser.add_argument('--nur-regeln', action='store_true',
                            help='nur die Regeln je Person, keine Paarurteile')

    def handle(self, *args, anbieter, mitschnitt, aufzeichnung, neu, nur_zaehlen, nur_regeln,
               **optionen):
        personen = [p for p in matching.grundmenge() if p.nogo.strip()]
        paare = matching.noetige_nogo_paare()
        self.stdout.write(f'Regeln: {len(personen)} Personen mit No-Go (je eine Anfrage); '
                          f'Paarurteile: {len(paare)} gerichtete Paare.')
        if nur_zaehlen:
            return
        if aufzeichnung and anbieter != 'test':
            raise CommandError('--aufzeichnung nur mit --anbieter test.')
        if anbieter == 'test':
            a_obj = TestAnbieter(aufzeichnung=aufzeichnung, streng=bool(aufzeichnung))
        elif anbieter:
            a_obj = urteile.anbieter_nach_name(anbieter, mitschnitt=mitschnitt)
            if not a_obj.schluessel_vorhanden():
                raise CommandError(f'{anbieter}: kein Schlüssel ({a_obj.schluessel_variable} '
                                   f'oder {a_obj.schluessel_variable}_DATEI) – nichts gesendet.')
        else:
            a_obj = urteile.urteiler()
        regeln, paar = nogo.Statistik(), nogo.Statistik()
        with urteile.mit_anbieter(a_obj):
            # Regel-Baustein fuer diesen Anbieter abgeschaltet: nicht fragen.
            for p in (personen if nogo.regeln_aktiv(a_obj.name) else []):
                nogo.regeln_holen(p, neu=neu, statistik=regeln)
            for x, y in ([] if nur_regeln else paare):
                nogo.holen(x, y, neu=neu, statistik=paar)
        self.stdout.write(f'Anbieter {a_obj.name}, Fassung {nogo.FASSUNG}/{nogo.REGEL_FASSUNG}')
        self.stdout.write(f'  Regeln:      {regeln}')
        self.stdout.write(f'  Paarurteile: {paar}')
        if regeln.fehler or paar.fehler:
            raise CommandError(f'{regeln.fehler + paar.fehler} Anfragen mit Fehler.')
