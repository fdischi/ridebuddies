"""
Rueckkopplung und Stufe Ridebuddies (Karte TASK-120.04, Abnahmekriterium #4).

Fabian, 23.09.2026: Feedback (Sorte 1 und 2) sieht kein anderer Nutzer, auch
nicht der Bewertete.

Stufe Ridebuddies - Fabians Entscheidung vom 23.09.2026 (Nacharbeit), die die
erste Fassung ersetzt: nur ueber eine sichtbare Ridebuddy-Anfrage zwischen
aktiv Verbundenen, die der andere bestaetigt. Keine gemeinsame
Plattform-Ausfahrt als Voraussetzung. Das Feedback "Ridebuddy" ist nur noch ein
stilles Signal und aendert keine Stufe. Die Tests der ersten Fassung
("beidseitig Ridebuddy nach gemeinsamer Ausfahrt -> Stufe 3") sind deshalb
durch ihr Gegenteil ersetzt.
"""
from django.test import TestCase

from kern import ablaeufe, sichtbarkeit
from kern.models import (
    Ausgang,
    Ausschluss,
    Dimension,
    Feedback,
    RidebuddyAnfrage,
    Stufe,
    Teilnahme,
    Verbindung,
)

from .hilfen import fertiger_nutzer, gefahrene_ausfahrt, ridebuddies_machen, verbinden

RIDEBUDDY = Feedback.Urteil.RIDEBUDDY


class FeedbackSichtTest(TestCase):
    def setUp(self):
        self.anna = fertiger_nutzer('anna')
        self.ben = fertiger_nutzer('ben')
        self.carla = fertiger_nutzer('carla')
        self.ausfahrt = gefahrene_ausfahrt(self.anna, self.ben, self.carla)
        self.feedback = ablaeufe.feedback_abgeben(
            self.ausfahrt, self.anna, self.ben,
            daumen={Dimension.TEMPO: True, Dimension.STIMMUNG: False},
            urteil=Feedback.Urteil.GERNE_WIEDER)

    def test_bewerteter_sieht_feedback_nicht(self):
        self.assertFalse(sichtbarkeit.feedback_sichtbar(self.ben).exists())

    def test_dritter_sieht_feedback_nicht(self):
        self.assertFalse(sichtbarkeit.feedback_sichtbar(self.carla).exists())

    def test_verfasser_sieht_sein_eigenes(self):
        self.assertEqual(list(sichtbarkeit.feedback_sichtbar(self.anna)), [self.feedback])

    def test_auch_verbindung_oder_ridebuddies_zeigen_kein_feedback(self):
        # Selbst auf der hoechsten Stufe gibt es keinen Weg zum Feedback anderer.
        ridebuddies_machen(self.anna, self.ben)
        self.assertFalse(sichtbarkeit.feedback_sichtbar(self.ben).exists())
        self.assertNotIn('feedback', sichtbarkeit.profil_sicht(self.ben, self.anna))

    def test_gerne_wieder_aendert_nichts(self):
        self.assertIsNone(sichtbarkeit.aktive_verbindung(self.anna, self.ben))
        self.assertFalse(Ausschluss.objects.exists())

    def test_war_nix_schliesst_still_aus(self):
        ablaeufe.feedback_abgeben(self.ausfahrt, self.carla, self.ben,
                                  urteil=Feedback.Urteil.WAR_NIX)
        ausschluss = Ausschluss.objects.get()
        self.assertEqual((ausschluss.urheber, ausschluss.betroffener), (self.carla, self.ben))
        self.assertEqual(ausschluss.quelle, Ausschluss.Quelle.FEEDBACK)
        self.assertFalse(sichtbarkeit.ausschluesse_sichtbar(self.ben).exists())

    def test_feedback_nur_von_mitgefahrenen(self):
        dieter = fertiger_nutzer('dieter')
        Teilnahme.objects.create(ausfahrt=self.ausfahrt, nutzer=dieter,
                                 zusage=Teilnahme.Zusage.ZUGESAGT, gefahren=False)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.feedback_abgeben(self.ausfahrt, dieter, self.anna, urteil=RIDEBUDDY)

    def test_feedback_je_ausfahrt_und_paar_eindeutig(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            Feedback.objects.create(ausfahrt=self.ausfahrt, verfasser=self.anna,
                                    bewerteter=self.ben)
        # Die Gegenrichtung ist ein eigenes Paar und erlaubt.
        ablaeufe.feedback_abgeben(self.ausfahrt, self.ben, self.anna)


class RidebuddyFeedbackIstNurSignalTest(TestCase):
    """Sorte 2 "Ridebuddy" aendert keine Stufe - auch nicht beidseitig."""

    def setUp(self):
        self.anna = fertiger_nutzer('anna')
        self.ben = fertiger_nutzer('ben')
        self.ausfahrt = gefahrene_ausfahrt(self.anna, self.ben)

    def test_beidseitig_ridebuddy_mit_gemeinsamer_ausfahrt_hebt_nicht_an(self):
        verbindung = verbinden(self.anna, self.ben)
        ablaeufe.feedback_abgeben(self.ausfahrt, self.anna, self.ben, urteil=RIDEBUDDY)
        ablaeufe.feedback_abgeben(self.ausfahrt, self.ben, self.anna, urteil=RIDEBUDDY)
        verbindung.refresh_from_db()
        self.assertEqual(verbindung.erreicht, Stufe.VERBUNDEN)
        self.assertEqual(sichtbarkeit.stufe_fuer(self.anna, self.ben), Stufe.VERBUNDEN)

    def test_beidseitig_ridebuddy_ohne_verbindung_verbindet_nicht(self):
        # Die erste Fassung legte hier direkt eine Verbindung auf Stufe 3 an.
        ablaeufe.feedback_abgeben(self.ausfahrt, self.anna, self.ben, urteil=RIDEBUDDY)
        ablaeufe.feedback_abgeben(self.ausfahrt, self.ben, self.anna, urteil=RIDEBUDDY)
        self.assertFalse(Verbindung.objects.exists())
        self.assertEqual(sichtbarkeit.stufe_fuer(self.anna, self.ben), Stufe.KEINE)

    def test_verbindung_anlegen_kann_keine_stufe_3_mehr(self):
        # Hinweis des gegenpruefer: verbindung_anlegen nahm frueher erreicht=...
        with self.assertRaises(TypeError):
            ablaeufe.verbindung_anlegen(self.anna, self.ben, Verbindung.Entstehung.ANFRAGE,
                                        erreicht=Stufe.RIDEBUDDIES)
        self.assertFalse(hasattr(ablaeufe, 'ridebuddies_pruefen'))


class RidebuddyAnfrageTest(TestCase):
    """Fabian, 23.09.2026: Stufe 3 nur ueber eine bestaetigte Ridebuddy-Anfrage."""

    def setUp(self):
        self.anna = fertiger_nutzer('anna')
        self.ben = fertiger_nutzer('ben')

    def test_bestaetigt_wird_ridebuddies_ohne_gemeinsame_ausfahrt(self):
        # Keine einzige Ausfahrt existiert - Leute, die schon vorher zusammen
        # gefahren sind, sollen sich manuell als Buddy hinzufuegen koennen.
        verbindung = verbinden(self.anna, self.ben)
        anfrage = ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        ablaeufe.ridebuddy_anfrage_beantworten(anfrage, anfrage.empfaenger, bestaetigen=True)
        verbindung.refresh_from_db()
        self.assertEqual((verbindung.erreicht, verbindung.gewaehrt_a, verbindung.gewaehrt_b),
                         (Stufe.RIDEBUDDIES, Stufe.RIDEBUDDIES, Stufe.RIDEBUDDIES))
        self.assertIsNotNone(verbindung.ridebuddies_seit)
        self.assertEqual(sichtbarkeit.stufe_fuer(self.anna, self.ben), Stufe.RIDEBUDDIES)
        self.assertEqual(sichtbarkeit.stufe_fuer(self.ben, self.anna), Stufe.RIDEBUDDIES)

    def test_offene_anfrage_hebt_noch_nichts(self):
        verbinden(self.anna, self.ben)
        ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        self.assertEqual(sichtbarkeit.stufe_fuer(self.anna, self.ben), Stufe.VERBUNDEN)
        self.assertEqual(sichtbarkeit.stufe_fuer(self.ben, self.anna), Stufe.VERBUNDEN)

    def test_abgelehnt_bleibt_verbunden_ohne_ausschluss(self):
        verbindung = verbinden(self.anna, self.ben)
        anfrage = ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        self.assertIsNone(ablaeufe.ridebuddy_anfrage_beantworten(anfrage, anfrage.empfaenger, bestaetigen=False))
        verbindung.refresh_from_db()
        self.assertEqual(verbindung.erreicht, Stufe.VERBUNDEN)
        self.assertTrue(verbindung.aktiv)
        self.assertFalse(Ausschluss.objects.exists())
        # Danach ist eine neue Anfrage wieder moeglich.
        ablaeufe.ridebuddy_anfrage_stellen(self.ben, self.anna)

    def test_nur_zwischen_verbundenen(self):
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)

    def test_nicht_bei_ausschluss(self):
        verbinden(self.anna, self.ben)
        ablaeufe.ausschliessen(self.ben, self.anna, Ausschluss.Quelle.VORSCHLAG)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)

    def test_nicht_wenn_schon_ridebuddies(self):
        ridebuddies_machen(self.anna, self.ben)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.ridebuddy_anfrage_stellen(self.ben, self.anna)

    def test_hoechstens_eine_offene_je_paar(self):
        verbinden(self.anna, self.ben)
        ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.ridebuddy_anfrage_stellen(self.ben, self.anna)
        self.assertEqual(RidebuddyAnfrage.objects.count(), 1)

    def test_nach_beenden_nicht_mehr_bestaetigbar(self):
        verbindung = verbinden(self.anna, self.ben)
        anfrage = ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        ablaeufe.verbindung_beenden(verbindung, self.ben, Ausgang.NICHT_JETZT)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.ridebuddy_anfrage_beantworten(anfrage, anfrage.empfaenger, bestaetigen=True)
        verbindung.refresh_from_db()
        self.assertEqual(verbindung.erreicht, Stufe.VERBUNDEN)

    def test_nur_empfaenger_bestaetigt(self):
        # Auflage A4: Der Absender bestaetigte frueher seine eigene Anfrage
        # und war ohne Zustimmung des anderen auf Stufe 3.
        verbindung = verbinden(self.anna, self.ben)
        carla = fertiger_nutzer('carla')
        anfrage = ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        for fremder in (self.anna, carla):
            with self.assertRaises(ablaeufe.NichtErlaubt):
                ablaeufe.ridebuddy_anfrage_beantworten(anfrage, fremder, bestaetigen=True)
            with self.assertRaises(ablaeufe.NichtErlaubt):
                ablaeufe.ridebuddy_anfrage_beantworten(anfrage, fremder, bestaetigen=False)
        verbindung.refresh_from_db()
        anfrage.refresh_from_db()
        self.assertEqual(verbindung.erreicht, Stufe.VERBUNDEN)
        self.assertEqual(anfrage.status, RidebuddyAnfrage.Status.OFFEN)

    def test_offene_anfrage_wird_beim_beenden_hinfaellig(self):
        verbindung = verbinden(self.anna, self.ben)
        anfrage = ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        ablaeufe.verbindung_beenden(verbindung, self.ben, Ausgang.NICHT_JETZT)
        anfrage.refresh_from_db()
        self.assertEqual(anfrage.status, RidebuddyAnfrage.Status.HINFAELLIG)
        self.assertIsNotNone(anfrage.beantwortet_am)

    def test_offene_anfrage_wird_beim_ausschluss_hinfaellig(self):
        verbinden(self.anna, self.ben)
        anfrage = ablaeufe.ridebuddy_anfrage_stellen(self.anna, self.ben)
        ablaeufe.ausschliessen(self.ben, self.anna, Ausschluss.Quelle.VERBINDUNG)
        anfrage.refresh_from_db()
        self.assertEqual(anfrage.status, RidebuddyAnfrage.Status.HINFAELLIG)

    def test_feedback_trotz_ausschluss_zulaessig_aber_folgenlos(self):
        # Festlegung der Hauptsitzung: bewusst zulaessig, bewirkt nichts Sichtbares.
        ausfahrt = gefahrene_ausfahrt(self.anna, self.ben)
        ablaeufe.ausschliessen(self.anna, self.ben, Ausschluss.Quelle.VORSCHLAG)
        ablaeufe.feedback_abgeben(ausfahrt, self.ben, self.anna, urteil=RIDEBUDDY)
        self.assertEqual(sichtbarkeit.stufe_fuer(self.ben, self.anna), Stufe.KEINE)
        self.assertFalse(sichtbarkeit.feedback_sichtbar(self.anna).exists())
