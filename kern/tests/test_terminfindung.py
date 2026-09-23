"""
Terminfindung (Karte TASK-120.06, 23.09.2026).

Was hier geprueft wird und warum:
- DUMMY-BESTAND GEGEN ZWEI QUELLEN: Die Erwartungswerte der Karte (von Hand
  gerechnet, mit Namenslisten) UND die Tabelle im Pruefblatt
  (docs/pruefblatt-matching.md, "Terminfaelle fuer Schritt 6"), die hier
  gelesen und mit Gewicht 0,5 nachgerechnet wird. Zwei Quellen, weil die Karte
  aus dem Pruefblatt abgeschrieben ist - ein Abschreibfehler faellt nur auf,
  wenn beide gegen den Code laufen. Der Bestand kommt wie in test_dummies.py
  ueber `call_command('dummies_anlegen')`, also denselben Weg wie auf dem Server.
- HANDGERECHNETE FAELLE mit Rechenweg: Vogesen (Gast im Nenner), Enduro
  (gleichauf, andere Leute), Renntraining (ohne Crew).
- RANDREGELN mit eigenen, kleinen Daten ohne Dummies - der Dummy-Bestand hat
  weder fehlende Antworten noch Teilueberdeckungen noch allgemeine
  Verfuegbarkeiten, dort koennten diese Regeln also gar nicht auffallen.
- KOMMANDO: Reihenfolge und eine Zeile woertlich.
"""
import datetime
import re
from fractions import Fraction
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from kern import terminfindung
from kern.models import (
    Ausfahrt,
    Mitgliedschaft,
    Teilnahme,
    Termin,
    Verfuegbarkeit,
    Verfuegbarkeitszeitraum,
)
from kern.terminfindung import (
    VORBEHALT_GEWICHT,
    prozent_runden,
    termin_auswertung,
    termin_text,
    terminuebersicht,
    zeile,
)

from .hilfen import crew_mit, nutzer

DOCS = Path(settings.BASE_DIR) / 'docs'
D = datetime.date


def _namen(liste):
    return [n.username for n in liste]


def _uebersicht(titel):
    return terminuebersicht(Ausfahrt.objects.get(titel=titel))


# ---------------------------------------------------------------------------
# Dummy-Bestand
# ---------------------------------------------------------------------------

JONAS, MEHMET, TIM = 'dummy-schotter-jonas', 'dummy-schotter-mehmet', 'dummy-schotter-tim'
RAINER, LEA = 'dummy-eifel-rainer', 'dummy-schotter-lea'
CARLA, AYSE, YVONNE, PETRA = ('dummy-frauen-carla', 'dummy-frauen-ayse', 'dummy-frauen-yvonne',
                              'dummy-frauen-petra')
KEVIN, SABINE, MARCO = 'dummy-ring-kevin', 'dummy-ring-sabine', 'dummy-ring-marco'
GABI, HEINZ, INES, MARKUS = ('dummy-westerwald-gabi', 'dummy-sauerland-heinz',
                             'dummy-frauen-ines', 'dummy-koeln-markus')

# Erwartungswerte aus der Kartenbeschreibung TASK-120.06, in der erwarteten
# Reihenfolge (Prozent absteigend, Gleichstand nach Datum):
# (Termin, Prozent, fehlt, Vorbehalt). "Noch keine Antwort" ist ueberall leer -
# im Bestand hat jeder zu jedem Termin geantwortet.
KARTE = {
    'Schotterrunde Bergisches Land': [
        ('Sa 17.04.2027 vormittags', 100, [], []),
        ('So 18.04.2027 vormittags', 80, [], [MEHMET, RAINER]),
        ('Sa 24.04.2027 nachmittags', 40, [MEHMET, TIM, LEA], []),
    ],
    'Enduro-Grundlagentraining': [
        ('Sa 08.05.2027 vormittags', 70, [RAINER], [TIM]),
        ('Sa 15.05.2027 vormittags', 70, [MEHMET], [RAINER]),
    ],
    'Frauenrunde Ahr und Eifel': [
        ('So 02.05.2027 mittags', 100, [], []),
        ('So 09.05.2027 mittags', 63, [PETRA], [YVONNE]),
    ],
    'Messebesuch Frühjahrsmesse': [
        ('Sa 10.04.2027 vormittags', 75, [], [AYSE, YVONNE]),
        ('So 11.04.2027 vormittags', 50, [AYSE, PETRA], []),
    ],
    'Renntraining Nürburgring': [
        ('Sa 12.06.2027 vormittags', 83, [], [MARCO]),
        ('Sa 26.06.2027 vormittags', 67, [SABINE], []),
    ],
    'Vogesen-Reise': [
        ('Do 03.06.2027–So 06.06.2027', 88, [], [MARKUS]),
        ('Do 17.06.2027–So 20.06.2027', 50, [HEINZ, MARKUS], []),
    ],
    'Pfingsttour Harz': [
        ('Fr 14.05.2027–Mo 17.05.2027', 100, [], []),
        ('Fr 21.05.2027–Mo 24.05.2027', 75, [], [GABI, INES]),
    ],
}


def _pruefblatt_terminfaelle():
    """Die Tabelle "Terminfaelle fuer Schritt 6" als Liste von
    (Titel, Termin-Zelle, [(Vorname, Buchstabe), ...])."""
    text = (DOCS / 'pruefblatt-matching.md').read_text()
    abschnitt = text.split('## Terminfälle für Schritt 6', 1)[1].split('\n## ', 1)[0]
    zeilen = [z for z in abschnitt.splitlines() if z.startswith('| ')]
    faelle, titel = [], None
    for z in zeilen[1:]:                       # Kopfzeile weg; '|---|' beginnt nicht mit '| '
        zellen = [c.strip() for c in z.strip('|').split('|')]
        if zellen[0]:
            titel = re.sub(r'\s*\([^)]*\)$', '', zellen[0].replace('**Reise** ', ''))
        antworten = [re.fullmatch(r'(\w+)(?:\(G\))? ([SVN])', a.strip()).groups()
                     for a in zellen[2].split(',')]
        faelle.append((titel, zellen[1], antworten))
    return faelle


class DummyBestandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('dummies_anlegen', stdout=StringIO(), stderr=StringIO())

    def test_alle_termine_wie_in_der_karte(self):
        gezaehlt = 0
        for titel, erwartet in KARTE.items():
            ist = _uebersicht(titel)
            self.assertEqual(
                [(termin_text(a.termin), a.prozent, _namen(a.fehlt), _namen(a.vorbehalt))
                 for a in ist],
                [(t, p, sorted(f), sorted(v)) for t, p, f, v in erwartet], titel)
            for a in ist:
                self.assertEqual(a.keine_antwort, [], titel)
                self.assertEqual(len(a.sicher) + len(a.vorbehalt) + len(a.fehlt), a.nenner)
            gezaehlt += len(ist)
        self.assertEqual(gezaehlt, 15)
        self.assertEqual(Termin.objects.count(), 15)

    def test_alle_termine_wie_im_pruefblatt(self):
        """Pruefblatt-Tabelle lesen, mit 0,5 je Vorbehalt nachrechnen, vergleichen.
        Die Spalte "mit Gast" gilt (Entscheidung 1): der Nenner ist die Zahl der
        Antworten in der Zeile, Gast eingeschlossen."""
        faelle = _pruefblatt_terminfaelle()
        self.assertEqual(len(faelle), 15)
        benutzer = list(get_user_model().objects.values_list('username', flat=True))

        def username(vorname):
            passend = [u for u in benutzer if u.endswith('-' + vorname.lower())]
            self.assertEqual(len(passend), 1, vorname)
            return passend[0]

        auswertungen = {}
        for titel in {f[0] for f in faelle}:
            for a in _uebersicht(titel):
                t = a.termin
                zelle = (f'{t.datum:%d}.–{t.bis_datum:%d.%m.%Y}' if t.bis_datum
                         else termin_text(t))
                auswertungen[(titel, zelle)] = a

        for titel, zelle, antworten in faelle:
            a = auswertungen[(titel, zelle)]
            punkte = sum({'S': 1, 'V': VORBEHALT_GEWICHT, 'N': 0}[b] for _, b in antworten)
            self.assertEqual(a.anteil, Fraction(punkte) / len(antworten), (titel, zelle))
            self.assertEqual(a.nenner, len(antworten), (titel, zelle))
            for buchstabe, liste in (('S', a.sicher), ('V', a.vorbehalt), ('N', a.fehlt)):
                self.assertEqual(_namen(liste),
                                 sorted(username(n) for n, b in antworten if b == buchstabe),
                                 (titel, zelle, buchstabe))

    # --- handgerechnete Faelle (AC 3) ---------------------------------------

    def test_vogesen_gast_im_nenner(self):
        # Crew Westerwald-Weitfahrer: Gabi (Organisator), Heinz, Ines (Mitglied),
        # Markus (Gast). Zeitraum 03.-06.06.2027, alle vier Tage abgedeckt:
        #   Gabi S = 1, Heinz S = 1, Ines S = 1, Markus V = 0,5
        #   Summe 3,5; Nenner 4 (Gast zaehlt, Entscheidung 1)
        #   3,5 / 4 = 7/8 = 87,5 % -> kaufmaennisch 88 %
        # Ohne Gast waeren es 3/3 = 100 % - genau das hat Fabian verworfen.
        a = _uebersicht('Vogesen-Reise')[0]
        self.assertEqual((a.termin.datum, a.termin.bis_datum), (D(2027, 6, 3), D(2027, 6, 6)))
        self.assertEqual(a.nenner, 4)
        self.assertEqual(a.anteil, Fraction(7, 8))
        self.assertEqual(a.prozent, 88)
        self.assertEqual(_namen(a.vorbehalt), [MARKUS])
        self.assertEqual(_namen(a.sicher), sorted([GABI, HEINZ, INES]))

    def test_enduro_gleichauf_andere_leute(self):
        # Schotterbande, Nenner 5 (Jonas, Mehmet, Tim, Rainer, Lea als Gast).
        #   08.05.: Jonas S, Mehmet S, Tim V, Rainer N, Lea S
        #           1 + 1 + 0,5 + 0 + 1 = 3,5 -> 3,5 / 5 = 70 %
        #   15.05.: Jonas S, Mehmet N, Tim S, Rainer V, Lea S
        #           1 + 0 + 1 + 0,5 + 1 = 3,5 -> 3,5 / 5 = 70 %
        # Exakt gleich (7/10), also entscheidet das Datum: 08.05. vor 15.05.
        erster, zweiter = _uebersicht('Enduro-Grundlagentraining')
        self.assertEqual(erster.anteil, zweiter.anteil)
        self.assertEqual(erster.anteil, Fraction(7, 10))
        self.assertEqual((erster.termin.datum, zweiter.termin.datum),
                         (D(2027, 5, 8), D(2027, 5, 15)))
        self.assertEqual((_namen(erster.fehlt), _namen(erster.vorbehalt)), ([RAINER], [TIM]))
        self.assertEqual((_namen(zweiter.fehlt), _namen(zweiter.vorbehalt)), ([MEHMET], [RAINER]))

    def test_renntraining_ohne_crew(self):
        # Keine Crew: Nenner = Teilnahmen (Kevin zugesagt, Sabine zugesagt, Marco
        # offen) plus vorgeschlagen_von (Kevin, schon enthalten) = 3.
        #   12.06.: Kevin S = 1, Sabine S = 1, Marco V = 0,5 -> 2,5 / 3 = 5/6
        #           = 83,33 % -> 83 %
        # Marcos "offen" ist keine Absage - er zaehlt mit seiner Antwort.
        a = _uebersicht('Renntraining Nürburgring')[0]
        self.assertEqual(a.termin.datum, D(2027, 6, 12))
        self.assertEqual(a.nenner, 3)
        self.assertEqual(a.anteil, Fraction(5, 6))
        self.assertEqual(a.prozent, 83)
        self.assertEqual(_namen(a.vorbehalt), [MARCO])

    # --- Abfragen -----------------------------------------------------------

    def test_abfragen_fest_je_ausfahrt(self):
        # Termine, Teilnahmen, Mitgliedschaften, Verfuegbarkeiten - vier, egal
        # wie viele Personen und Termine. Bei Reisen Zeitraeume statt
        # Verfuegbarkeiten. Waechst diese Zahl, rechnet jemand je Person.
        schotter = Ausfahrt.objects.get(titel='Schotterrunde Bergisches Land')
        vogesen = Ausfahrt.objects.get(titel='Vogesen-Reise')
        with self.assertNumQueries(4):
            terminuebersicht(schotter)
        with self.assertNumQueries(4):
            terminuebersicht(vogesen)

    # --- Kommando -----------------------------------------------------------

    def _kommando(self, *args):
        ausgabe = StringIO()
        call_command('terminfindung', *args, stdout=ausgabe)
        return ausgabe.getvalue().splitlines()

    def test_kommando_reihenfolge_und_zeile(self):
        zeilen = self._kommando('Schotterrunde Bergisches Land')
        self.assertTrue(zeilen[0].startswith('Schotterrunde Bergisches Land (ID '))
        self.assertEqual(zeilen[1], 'Nenner: 5')
        self.assertEqual(zeilen[2], 'Sa 17.04.2027 vormittags – 100 % – fehlt: – – '
                                    'Vorbehalt: – – keine Antwort: –')
        self.assertEqual(zeilen[4], 'Sa 24.04.2027 nachmittags – 40 % – fehlt: '
                                    f'{LEA}, {MEHMET}, {TIM} – Vorbehalt: – – keine Antwort: –')
        self.assertEqual([z[:13] for z in zeilen[2:]],
                         ['Sa 17.04.2027', 'So 18.04.2027', 'Sa 24.04.2027'])

    def test_kommando_gleichstand_nach_datum(self):
        zeilen = self._kommando('Enduro-Grundlagentraining')
        self.assertEqual(zeilen[2:], [
            f'Sa 08.05.2027 vormittags – 70 % – fehlt: {RAINER} – Vorbehalt: {TIM} – '
            'keine Antwort: –',
            f'Sa 15.05.2027 vormittags – 70 % – fehlt: {MEHMET} – Vorbehalt: {RAINER} – '
            'keine Antwort: –',
        ])

    def test_kommando_id_teiltitel_und_fehler(self):
        vogesen = Ausfahrt.objects.get(titel='Vogesen-Reise')
        self.assertEqual(self._kommando(str(vogesen.pk)), self._kommando('vogesen'))
        with self.assertRaisesMessage(CommandError, 'Mehrere Ausfahrten'):
            self._kommando('runde')             # Schotterrunde und Frauenrunde
        with self.assertRaisesMessage(CommandError, 'Keine Ausfahrt'):
            self._kommando('Gibtsnicht')
        with self.assertRaisesMessage(CommandError, 'Keine Ausfahrt mit ID'):
            self._kommando('999999')


# ---------------------------------------------------------------------------
# Randregeln mit eigenen Daten (AC 4)
# ---------------------------------------------------------------------------

S, V, N = 'sicher', 'vorbehalt', 'nein'


class RandregelnTest(TestCase):
    def setUp(self):
        self.a, self.b, self.c, self.d = (nutzer(n) for n in ('anna', 'bert', 'cora', 'dirk'))

    def _crew_ausfahrt(self, *leute, art=Ausfahrt.Art.TAGESTOUR, titel='Runde'):
        crew = crew_mit(*leute)
        return Ausfahrt.objects.create(titel=titel, art=art, crew=crew)

    def _tag(self, wer, ausfahrt, datum, tageszeit, stufe):
        Verfuegbarkeit.objects.create(nutzer=wer, ausfahrt=ausfahrt, datum=datum,
                                      tageszeit=tageszeit, stufe=stufe)

    def _zeitraum(self, wer, ausfahrt, von, bis, stufe):
        Verfuegbarkeitszeitraum.objects.create(nutzer=wer, ausfahrt=ausfahrt, von=von, bis=bis,
                                               stufe=stufe)

    def test_keine_antwort_zaehlt_null_und_steht_getrennt(self):
        ausfahrt = self._crew_ausfahrt(self.a, self.b, self.c)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                       tageszeit='vormittags')
        self._tag(self.a, ausfahrt, termin.datum, 'vormittags', S)
        self._tag(self.b, ausfahrt, termin.datum, 'vormittags', N)
        # cora antwortet nicht: 1 + 0 + 0 = 1 von 3
        e = termin_auswertung(termin)
        self.assertEqual(e.nenner, 3)
        self.assertEqual(e.anteil, Fraction(1, 3))
        self.assertEqual(e.prozent, 33)
        self.assertEqual(_namen(e.fehlt), ['bert'])
        self.assertEqual(_namen(e.keine_antwort), ['cora'])
        self.assertIn('fehlt: bert – Vorbehalt: – – keine Antwort: cora', zeile(e))

    def test_reise_schlechtester_tag(self):
        ausfahrt = self._crew_ausfahrt(self.a, self.b, self.c, self.d, art=Ausfahrt.Art.REISE)
        von, bis = D(2027, 6, 1), D(2027, 6, 4)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=von, bis_datum=bis)
        # anna: drei Tage sicher, der 03.06. nein -> fehlt
        self._zeitraum(self.a, ausfahrt, D(2027, 6, 1), D(2027, 6, 2), S)
        self._zeitraum(self.a, ausfahrt, D(2027, 6, 3), D(2027, 6, 3), N)
        self._zeitraum(self.a, ausfahrt, D(2027, 6, 4), D(2027, 6, 4), S)
        # bert: sicher, aber der 03.06. ist nicht abgedeckt -> keine Antwort
        self._zeitraum(self.b, ausfahrt, D(2027, 6, 1), D(2027, 6, 2), S)
        self._zeitraum(self.b, ausfahrt, D(2027, 6, 4), D(2027, 6, 4), S)
        # cora: Luecke UND Vorbehalt -> keine Antwort (schlechter als Vorbehalt)
        self._zeitraum(self.c, ausfahrt, D(2027, 6, 1), D(2027, 6, 3), V)
        # dirk: nein am ersten Tag, Rest unabgedeckt -> fehlt (nein schlaegt Luecke)
        self._zeitraum(self.d, ausfahrt, D(2027, 6, 1), D(2027, 6, 1), N)
        e = termin_auswertung(termin)
        self.assertEqual(_namen(e.fehlt), ['anna', 'dirk'])
        self.assertEqual(_namen(e.keine_antwort), ['bert', 'cora'])
        self.assertEqual((e.sicher, e.vorbehalt), ([], []))
        self.assertEqual(e.anteil, 0)
        self.assertEqual(e.prozent, 0)

    def test_reise_vorbehalt_an_einem_tag(self):
        ausfahrt = self._crew_ausfahrt(self.a, self.b, art=Ausfahrt.Art.REISE)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 6, 1),
                                       bis_datum=D(2027, 6, 3))
        # ein Zeitraum ueber den Termin hinaus deckt ihn ab
        self._zeitraum(self.a, ausfahrt, D(2027, 5, 28), D(2027, 6, 10), S)
        self._zeitraum(self.b, ausfahrt, D(2027, 6, 1), D(2027, 6, 2), S)
        self._zeitraum(self.b, ausfahrt, D(2027, 6, 3), D(2027, 6, 3), V)
        e = termin_auswertung(termin)
        self.assertEqual((_namen(e.sicher), _namen(e.vorbehalt)), (['anna'], ['bert']))
        self.assertEqual(e.anteil, Fraction(3, 4))

    def test_ueberlappende_zeitraeume_gleichen_vorrangs(self):
        # Festlegung: decken zwei Zeitraeume GLEICHEN Vorrangs (beide mit Bezug
        # auf diese Ausfahrt) denselben Tag ab, gilt der schlechteste.
        # anna: 01.-03.06. sicher, dazu 02.06. Vorbehalt -> am 02.06. Vorbehalt
        # -> Reise insgesamt Vorbehalt: 0,5 von 1.
        ausfahrt = self._crew_ausfahrt(self.a, art=Ausfahrt.Art.REISE)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 6, 1),
                                       bis_datum=D(2027, 6, 3))
        self._zeitraum(self.a, ausfahrt, D(2027, 6, 1), D(2027, 6, 3), S)
        self._zeitraum(self.a, ausfahrt, D(2027, 6, 2), D(2027, 6, 2), V)
        e = termin_auswertung(termin)
        self.assertEqual((_namen(e.sicher), _namen(e.vorbehalt)), ([], ['anna']))
        self.assertEqual(e.anteil, Fraction(1, 2))

    def test_tagestermin_ignoriert_zeitraum(self):
        # Spiegelbild zu "bei Reisen zaehlen Tag-Eintraege nicht": ein Zeitraum,
        # der den Tag eines Tagestermins abdeckt, zaehlt nicht - auch kein nein.
        ausfahrt = self._crew_ausfahrt(self.a)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 6, 2),
                                       tageszeit='vormittags')
        self._zeitraum(self.a, ausfahrt, D(2027, 6, 1), D(2027, 6, 3), N)
        e = termin_auswertung(termin)
        self.assertEqual((_namen(e.fehlt), _namen(e.keine_antwort)), ([], ['anna']))

    def test_ausfahrt_antwort_vor_allgemeiner(self):
        ausfahrt = self._crew_ausfahrt(self.a, self.b, self.c)
        andere = Ausfahrt.objects.create(titel='Andere', crew=ausfahrt.crew)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                       tageszeit='mittags')
        # anna: allgemein nein, fuer diese Ausfahrt sicher -> sicher
        self._tag(self.a, None, termin.datum, 'mittags', N)
        self._tag(self.a, ausfahrt, termin.datum, 'mittags', S)
        # bert: nur allgemein, mit Vorbehalt -> die allgemeine greift
        self._tag(self.b, None, termin.datum, 'mittags', V)
        # cora: sicher - aber fuer eine ANDERE Ausfahrt, und allgemein nur
        # vormittags -> keine Antwort
        self._tag(self.c, andere, termin.datum, 'mittags', S)
        self._tag(self.c, None, termin.datum, 'vormittags', S)
        e = termin_auswertung(termin)
        self.assertEqual(_namen(e.sicher), ['anna'])
        self.assertEqual(_namen(e.vorbehalt), ['bert'])
        self.assertEqual(_namen(e.keine_antwort), ['cora'])

    def test_ausfahrt_zeitraum_vor_allgemeinem(self):
        ausfahrt = self._crew_ausfahrt(self.a, self.b, self.c, art=Ausfahrt.Art.REISE)
        andere = Ausfahrt.objects.create(titel='Andere', crew=ausfahrt.crew)
        von, bis = D(2027, 6, 1), D(2027, 6, 2)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=von, bis_datum=bis)
        self._zeitraum(self.a, None, von, bis, N)
        self._zeitraum(self.a, ausfahrt, von, bis, S)
        self._zeitraum(self.b, None, von, bis, V)
        self._zeitraum(self.c, andere, von, bis, S)
        # Einzelne Tagesverfuegbarkeiten zaehlen bei Reisen nicht (Festlegung).
        self._tag(self.c, ausfahrt, von, 'vormittags', S)
        e = termin_auswertung(termin)
        self.assertEqual(_namen(e.sicher), ['anna'])
        self.assertEqual(_namen(e.vorbehalt), ['bert'])
        self.assertEqual(_namen(e.keine_antwort), ['cora'])

    def test_teilnahme_abgesagt_fehlt(self):
        # Ohne Crew: anna schlaegt vor (keine Teilnahme), bert sagt zu, cora sagt
        # ab, hat aber sicher angegeben. Nenner 3, cora fehlt.
        ausfahrt = Ausfahrt.objects.create(titel='Zu dritt', vorgeschlagen_von=self.a)
        Teilnahme.objects.create(ausfahrt=ausfahrt, nutzer=self.b,
                                 zusage=Teilnahme.Zusage.ZUGESAGT)
        Teilnahme.objects.create(ausfahrt=ausfahrt, nutzer=self.c,
                                 zusage=Teilnahme.Zusage.ABGESAGT)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                       tageszeit='vormittags')
        for wer in (self.a, self.b, self.c):
            self._tag(wer, ausfahrt, termin.datum, 'vormittags', S)
        e = termin_auswertung(termin)
        self.assertEqual(e.nenner, 3)
        self.assertEqual(_namen(e.fehlt), ['cora'])
        self.assertEqual(_namen(e.sicher), ['anna', 'bert'])
        self.assertEqual(e.prozent, 67)

    def test_teilnahme_abgesagt_auch_in_crew(self):
        # Festlegung dieses Baus: die Absage gilt auch bei einer Crew-Ausfahrt.
        # Eine Teilnahme eines Nicht-Mitglieds erweitert den Nenner aber nicht.
        ausfahrt = self._crew_ausfahrt(self.a, self.b)
        Teilnahme.objects.create(ausfahrt=ausfahrt, nutzer=self.b,
                                 zusage=Teilnahme.Zusage.ABGESAGT)
        Teilnahme.objects.create(ausfahrt=ausfahrt, nutzer=self.d,
                                 zusage=Teilnahme.Zusage.ZUGESAGT)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                       tageszeit='vormittags')
        for wer in (self.a, self.b, self.d):
            self._tag(wer, ausfahrt, termin.datum, 'vormittags', S)
        e = termin_auswertung(termin)
        self.assertEqual(e.nenner, 2)
        self.assertEqual(_namen(e.fehlt), ['bert'])

    def test_ohne_crew_vorschlagender_nicht_doppelt(self):
        ausfahrt = Ausfahrt.objects.create(titel='Zu zweit', vorgeschlagen_von=self.a)
        Teilnahme.objects.create(ausfahrt=ausfahrt, nutzer=self.a)
        Teilnahme.objects.create(ausfahrt=ausfahrt, nutzer=self.b)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                       tageszeit='vormittags')
        self.assertEqual(termin_auswertung(termin).nenner, 2)

    def test_gast_zaehlt_zum_nenner(self):
        ausfahrt = self._crew_ausfahrt(self.a)
        Mitgliedschaft.objects.create(crew=ausfahrt.crew, nutzer=self.b,
                                      rolle=Mitgliedschaft.Rolle.GAST)
        Mitgliedschaft.objects.create(crew=ausfahrt.crew, nutzer=self.c,
                                      rolle=Mitgliedschaft.Rolle.ORGANISATOR)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                       tageszeit='vormittags')
        self.assertEqual(termin_auswertung(termin).nenner, 3)

    def test_ganzer_tag_schlechteste_tageszeit(self):
        ausfahrt = self._crew_ausfahrt(self.a, self.b, self.c, self.d)
        tag = D(2027, 5, 1)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=tag, tageszeit='')
        for wer, stufen in ((self.a, (S, S, V)),       # -> Vorbehalt
                            (self.b, (S, S, None)),    # nachmittags fehlt -> keine Antwort
                            (self.c, (S, N, S)),       # -> fehlt
                            (self.d, (S, S, S))):      # -> sicher
            for tageszeit, stufe in zip(('vormittags', 'mittags', 'nachmittags'), stufen):
                if stufe:
                    self._tag(wer, ausfahrt, tag, tageszeit, stufe)
        e = termin_auswertung(termin)
        self.assertEqual(_namen(e.vorbehalt), ['anna'])
        self.assertEqual(_namen(e.keine_antwort), ['bert'])
        self.assertEqual(_namen(e.fehlt), ['cora'])
        self.assertEqual(_namen(e.sicher), ['dirk'])
        self.assertEqual(termin_text(termin), 'Sa 01.05.2027 ganztags')

    def test_leerer_nenner_ohne_absturz(self):
        ausfahrt = Ausfahrt.objects.create(titel='Niemand')
        leer = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                     tageszeit='vormittags')
        e = termin_auswertung(leer)
        self.assertEqual((e.nenner, e.anteil, e.prozent), (0, None, None))
        self.assertEqual(zeile(e), 'Sa 01.05.2027 vormittags – – % – fehlt: – – '
                                   'Vorbehalt: – – keine Antwort: –')
        Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 6, 1), bis_datum=D(2027, 6, 2))
        self.assertEqual([a.prozent for a in terminuebersicht(ausfahrt)], [None, None])

    def test_ohne_termine(self):
        self.assertEqual(terminuebersicht(Ausfahrt.objects.create(titel='Leer')), [])

    def test_sortierung_gleichstand_tageszeit_und_none_zuletzt(self):
        ausfahrt = self._crew_ausfahrt(self.a)
        tag = D(2027, 5, 1)
        nachm = Termin.objects.create(ausfahrt=ausfahrt, datum=tag, tageszeit='nachmittags')
        vorm = Termin.objects.create(ausfahrt=ausfahrt, datum=tag, tageszeit='vormittags')
        mitt = Termin.objects.create(ausfahrt=ausfahrt, datum=tag, tageszeit='mittags')
        spaeter = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 2),
                                        tageszeit='vormittags')
        for tz in ('vormittags', 'mittags', 'nachmittags'):
            self._tag(self.a, ausfahrt, tag, tz, V)
        self._tag(self.a, ausfahrt, spaeter.datum, 'vormittags', S)
        self.assertEqual([a.termin for a in terminuebersicht(ausfahrt)],
                         [spaeter, vorm, mitt, nachm])

    def test_sortierung_nach_exaktem_wert(self):
        # Zwei Werte, die gerundet GLEICH sind (beide 63 %): 5/8 = 62,5 % und
        # 19/30 = 63,33 %. Sortiert wird exakt, also 19/30 zuerst, obwohl der
        # andere Termin frueher liegt. Ueber den Schluessel direkt geprueft -
        # 19/30 mit echten Antworten braeuchte 30 Personen.
        ausfahrt = self._crew_ausfahrt(self.a)
        frueh = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                      tageszeit='vormittags')
        spaet = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 2),
                                      tageszeit='vormittags')
        a_frueh = terminfindung.Auswertung(frueh, 8, Fraction(5, 8), 63)
        a_spaet = terminfindung.Auswertung(spaet, 3, Fraction(19, 30), 63)   # 63,33 %
        self.assertEqual(sorted([a_frueh, a_spaet], key=terminfindung.sortierschluessel),
                         [a_spaet, a_frueh])

    def test_rundung_kaufmaennisch(self):
        self.assertEqual(round(62.5), 62)          # der Grund, warum nicht round()
        faelle = {Fraction(5, 8): 63, Fraction(7, 8): 88, Fraction(5, 6): 83,
                  Fraction(2, 3): 67, Fraction(1, 8): 13, Fraction(3, 8): 38,
                  Fraction(0): 0, Fraction(1): 100, None: None}
        for anteil, erwartet in faelle.items():
            self.assertEqual(prozent_runden(anteil), erwartet, anteil)

    def test_rundung_mit_daten_62_5(self):
        # 8 Leute: 5 sicher, 3 nein = 5/8 = 62,5 % -> 63
        leute = [nutzer(f'p{i}') for i in range(8)]
        ausfahrt = self._crew_ausfahrt(*leute)
        termin = Termin.objects.create(ausfahrt=ausfahrt, datum=D(2027, 5, 1),
                                       tageszeit='vormittags')
        for i, wer in enumerate(leute):
            self._tag(wer, ausfahrt, termin.datum, 'vormittags', S if i < 5 else N)
        e = termin_auswertung(termin)
        self.assertEqual((e.anteil, e.prozent), (Fraction(5, 8), 63))

    def test_vorbehalt_gewicht(self):
        self.assertEqual(VORBEHALT_GEWICHT, Fraction(1, 2))
