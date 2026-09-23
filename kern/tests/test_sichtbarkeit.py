"""
Sichtbarkeitsregeln (Karte TASK-120.04, Abnahmekriterium #3).

Je Regel ein eigener Testfall. Jede Pruefung laeuft ueber
assertSiehtBis(): Sie prueft nicht nur die Zahl aus stufe_fuer(), sondern
auch, welche Profilfelder und welche Beitraege tatsaechlich herauskommen -
eine richtige Stufe mit falscher Filterung wuerde sonst durchrutschen.
"""
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone

from kern import ablaeufe, sichtbarkeit
from kern.models import (
    Anfrage,
    Ausgang,
    Ausschluss,
    Dimension,
    Fremdprofil,
    Mitgliedschaft,
    Profil,
    Stufe,
    Verbindung,
    Vorschlag,
)

from .hilfen import (
    OEFFENTLICHES_FELD,
    RIDEBUDDY_FELD,
    VERBUNDENES_FELD,
    crew_mit,
    fertiger_nutzer,
    ridebuddies_machen,
    verbinden,
    vorschlag,
)


class SichtTestCase(TestCase):
    def setUp(self):
        self.anna = fertiger_nutzer('anna')
        self.ben = fertiger_nutzer('ben')

    def assertSiehtBis(self, betrachter, inhaber, stufe):
        """betrachter sieht inhaber genau bis `stufe` - Zahl, Felder, Beitraege."""
        self.assertEqual(sichtbarkeit.stufe_fuer(betrachter, inhaber), stufe)
        sicht = sichtbarkeit.profil_sicht(betrachter, inhaber)
        beitraege = set(sichtbarkeit.beitraege_sichtbar(betrachter, inhaber)
                        .values_list('stufe', flat=True))
        if stufe == Stufe.KEINE:
            self.assertEqual(sicht, {})
            self.assertEqual(beitraege, set())
            return
        profil = Profil.objects.get(nutzer=inhaber)
        self.assertEqual(sicht['nutzername'], inhaber.username)
        for feld in (OEFFENTLICHES_FELD, VERBUNDENES_FELD, RIDEBUDDY_FELD):
            if profil.feldstufe(feld) <= stufe:
                self.assertEqual(sicht.get(feld), getattr(profil, feld), feld)
            else:
                self.assertNotIn(feld, sicht, feld)
        self.assertEqual(beitraege, set(range(1, int(stufe) + 1)))
        # Feldstufen und hart/weich-Gewichtung verlassen das Profil nie.
        self.assertNotIn('feldstufen', sicht)
        self.assertNotIn('gewichtung', sicht)


class OhneBeziehungTest(SichtTestCase):
    def test_nicht_angemeldet_sieht_nichts(self):
        self.assertSiehtBis(AnonymousUser(), self.anna, Stufe.KEINE)
        self.assertFalse(sichtbarkeit.fremdprofile_sichtbar(AnonymousUser()).exists())
        self.assertFalse(sichtbarkeit.nachrichten_sichtbar(AnonymousUser()).exists())
        self.assertFalse(sichtbarkeit.feedback_sichtbar(AnonymousUser()).exists())

    def test_stufe_0_sieht_nichts(self):
        # Angemeldet, aber ohne Vorschlag, Anfrage, Crew oder Verbindung:
        # kein Durchstoebern.
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)

    def test_sich_selbst_sieht_man_ganz(self):
        self.assertSiehtBis(self.anna, self.anna, Stufe.RIDEBUDDIES)


class VorschlagSichtTest(SichtTestCase):
    def test_vorschlag_empfaenger_sieht_nur_oeffentlich(self):
        vorschlag(empfaenger=self.anna, kandidat=self.ben)
        self.assertSiehtBis(self.anna, self.ben, Stufe.OEFFENTLICH)

    def test_vorschlag_kandidat_sieht_empfaenger_nicht(self):
        # Festlegung der Hauptsitzung: Vorschlagssicht ist einseitig.
        vorschlag(empfaenger=self.anna, kandidat=self.ben)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)

    def test_angenommener_vorschlag_bleibt_oeffentlich_sichtbar(self):
        v = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        ablaeufe.vorschlag_reagieren(v, v.empfaenger, Vorschlag.Reaktion.ANGENOMMEN)
        self.assertSiehtBis(self.anna, self.ben, Stufe.OEFFENTLICH)
        # Einseitig angenommen ist noch keine Verbindung.
        self.assertIsNone(sichtbarkeit.aktive_verbindung(self.anna, self.ben))

    def test_nicht_jetzt_beendet_sicht_und_setzt_wiedervorlage(self):
        # Zeitunabhaengig (Auflage A3 des gegenpruefer): Frueher stand hier
        # reagiert_am.date() - das UTC-Datum -, der Ablauf rechnet aber mit
        # timezone.localdate() (Europe/Berlin). Zwischen 22 und 24 Uhr UTC
        # liegen beide auf verschiedenen Tagen, und der Test war rot. Jetzt wird
        # das lokale Datum vor und nach dem Aufruf genommen; das Ergebnis muss
        # zu einem der beiden passen (auch ueber Mitternacht hinweg).
        v = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        vorher = timezone.localdate()
        ablaeufe.vorschlag_reagieren(v, v.empfaenger, Vorschlag.Reaktion.NICHT_JETZT)
        nachher = timezone.localdate()
        v.refresh_from_db()
        self.assertIn(v.wiedervorlage_ab, {ablaeufe.plus_monate(vorher, 6),
                                           ablaeufe.plus_monate(nachher, 6)})
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        self.assertFalse(Ausschluss.objects.exists())

    def test_angenommen_und_gegenueber_sagt_nicht_jetzt_endet_sicht(self):
        # Auflage A1/A2: Anna nimmt an, Ben sagt "nicht jetzt" -> Anna sieht
        # Ben nicht mehr (vorher hielt ihr angenommener Vorschlag die Sicht
        # unbefristet).
        v1 = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        v2 = vorschlag(empfaenger=self.ben, kandidat=self.anna)
        ablaeufe.vorschlag_reagieren(v1, v1.empfaenger, Vorschlag.Reaktion.ANGENOMMEN)
        ablaeufe.vorschlag_reagieren(v2, v2.empfaenger, Vorschlag.Reaktion.NICHT_JETZT)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)

    def test_verbindung_aus_vorschlaegen_beendet_sieht_nichts(self):
        # Auflage A1/A2 - der Vorfall selbst: beidseitig angenommen ->
        # Verbindung -> beendet. Danach 0/0, nicht mehr 1/1.
        v1 = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        v2 = vorschlag(empfaenger=self.ben, kandidat=self.anna)
        ablaeufe.vorschlag_reagieren(v1, v1.empfaenger, Vorschlag.Reaktion.ANGENOMMEN)
        verbindung = ablaeufe.vorschlag_reagieren(v2, v2.empfaenger, Vorschlag.Reaktion.ANGENOMMEN)
        ablaeufe.verbindung_beenden(verbindung, self.anna, Ausgang.NICHT_JETZT)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)

    def test_neuer_offener_vorschlag_nach_beenden_gibt_wieder_sicht(self):
        # Gegenstueck zu A1: Die Sperre gilt dem alten, angenommenen Vorschlag,
        # nicht jedem kuenftigen. Legt das Matching spaeter eine neue Runde vor,
        # sieht der Empfaenger den Kandidaten wieder oeffentlich.
        verbindung = verbinden(self.anna, self.ben)
        ablaeufe.verbindung_beenden(verbindung, self.anna, Ausgang.NICHT_JETZT)
        vorschlag(empfaenger=self.anna, kandidat=self.ben, runde=7)
        self.assertSiehtBis(self.anna, self.ben, Stufe.OEFFENTLICH)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)

    def test_nur_empfaenger_reagiert_auf_vorschlag(self):
        # Auflage A4, dasselbe Muster: Kandidat und Dritter werden abgewiesen.
        v = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        for fremder in (self.ben, fertiger_nutzer('carla')):
            with self.assertRaises(ablaeufe.NichtErlaubt):
                ablaeufe.vorschlag_reagieren(v, fremder, Vorschlag.Reaktion.ANGENOMMEN)
        v.refresh_from_db()
        self.assertEqual(v.reaktion, Vorschlag.Reaktion.OFFEN)

    def test_angenommen_ohne_reagiert_am_bricht_nicht_ab(self):
        # Nachpruefung 23.09.2026: Im Admin auf "angenommen" gesetzt, ohne
        # reagiert_am - stufe_fuer brach mit ValueError ab. Jetzt gilt der
        # Anlagezeitpunkt, und die Model-Pruefung verlangt den Zeitpunkt.
        from django.core.exceptions import ValidationError
        v = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        Vorschlag.objects.filter(pk=v.pk).update(reaktion=Vorschlag.Reaktion.ANGENOMMEN)
        self.assertSiehtBis(self.anna, self.ben, Stufe.OEFFENTLICH)
        verbindung = verbinden(self.anna, self.ben)
        ablaeufe.verbindung_beenden(verbindung, self.anna, Ausgang.NICHT_JETZT)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        v.refresh_from_db()
        with self.assertRaises(ValidationError):
            v.full_clean()

    def test_beidseitig_angenommen_wird_verbunden(self):
        v1 = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        v2 = vorschlag(empfaenger=self.ben, kandidat=self.anna)
        self.assertIsNone(ablaeufe.vorschlag_reagieren(v1, v1.empfaenger, Vorschlag.Reaktion.ANGENOMMEN))
        verbindung = ablaeufe.vorschlag_reagieren(v2, v2.empfaenger, Vorschlag.Reaktion.ANGENOMMEN)
        self.assertEqual(verbindung.erreicht, Stufe.VERBUNDEN)
        self.assertEqual(verbindung.entstanden_durch, Verbindung.Entstehung.VORSCHLAG)
        self.assertSiehtBis(self.anna, self.ben, Stufe.VERBUNDEN)
        self.assertSiehtBis(self.ben, self.anna, Stufe.VERBUNDEN)


class AnfrageSichtTest(SichtTestCase):
    def test_anfrage_empfaenger_sieht_nur_oeffentlich(self):
        ablaeufe.anfrage_stellen(self.anna, self.ben, 'Lust auf die Eifel?')
        self.assertSiehtBis(self.ben, self.anna, Stufe.OEFFENTLICH)

    def test_anfrage_absender_sieht_empfaenger_nicht(self):
        ablaeufe.anfrage_stellen(self.anna, self.ben)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)

    def test_angenommene_anfrage_verbindet(self):
        anfrage = ablaeufe.anfrage_stellen(self.anna, self.ben)
        verbindung = ablaeufe.anfrage_beantworten(anfrage, anfrage.empfaenger, annehmen=True)
        self.assertEqual(verbindung.entstanden_durch, Verbindung.Entstehung.ANFRAGE)
        self.assertSiehtBis(self.anna, self.ben, Stufe.VERBUNDEN)
        self.assertSiehtBis(self.ben, self.anna, Stufe.VERBUNDEN)

    def test_verbindung_aus_anfrage_beendet_sieht_nichts(self):
        # Auflage A2: derselbe Weg ueber die Anfrage.
        verbindung = ablaeufe.anfrage_beantworten(
            ablaeufe.anfrage_stellen(self.anna, self.ben), self.ben, annehmen=True)
        ablaeufe.verbindung_beenden(verbindung, self.ben, Ausgang.NICHT_JETZT)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)

    def test_nur_empfaenger_beantwortet_anfrage(self):
        # Auflage A4, dasselbe Muster: Absender und Dritter werden abgewiesen.
        anfrage = ablaeufe.anfrage_stellen(self.anna, self.ben)
        for fremder in (self.anna, fertiger_nutzer('carla')):
            with self.assertRaises(ablaeufe.NichtErlaubt):
                ablaeufe.anfrage_beantworten(anfrage, fremder, annehmen=True)
        self.assertIsNone(sichtbarkeit.aktive_verbindung(self.anna, self.ben))

    def test_abgelehnte_anfrage_endet_sicht_ohne_ausschluss(self):
        anfrage = ablaeufe.anfrage_stellen(self.anna, self.ben)
        ablaeufe.anfrage_beantworten(anfrage, anfrage.empfaenger, annehmen=False)
        self.assertEqual(Anfrage.objects.get().status, Anfrage.Status.ABGELEHNT)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)
        self.assertFalse(Ausschluss.objects.exists())


class CrewSichtTest(SichtTestCase):
    def test_crew_mitglieder_sehen_einander_oeffentlich(self):
        crew_mit(self.anna, self.ben)
        self.assertSiehtBis(self.anna, self.ben, Stufe.OEFFENTLICH)
        self.assertSiehtBis(self.ben, self.anna, Stufe.OEFFENTLICH)

    def test_gast_und_mitglied_sehen_einander_oeffentlich(self):
        crew = crew_mit(self.anna, rolle=Mitgliedschaft.Rolle.ORGANISATOR)
        Mitgliedschaft.objects.create(crew=crew, nutzer=self.ben,
                                      rolle=Mitgliedschaft.Rolle.GAST)
        self.assertSiehtBis(self.anna, self.ben, Stufe.OEFFENTLICH)
        self.assertSiehtBis(self.ben, self.anna, Stufe.OEFFENTLICH)

    def test_andere_crew_sieht_nichts(self):
        crew_mit(self.anna, name='Eins')
        crew_mit(self.ben, name='Zwei')
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)

    def test_crew_ausfahrten_fuer_mitglieder_und_gaeste(self):
        from kern.models import Ausfahrt
        crew = crew_mit(self.anna, rolle=Mitgliedschaft.Rolle.ORGANISATOR)
        Mitgliedschaft.objects.create(crew=crew, nutzer=self.ben,
                                      rolle=Mitgliedschaft.Rolle.GAST)
        ausfahrt = Ausfahrt.objects.create(titel='Bergische Runde', crew=crew,
                                           vorgeschlagen_von=self.anna)
        self.assertEqual(list(sichtbarkeit.ausfahrten_sichtbar(self.ben)), [ausfahrt])
        self.assertFalse(sichtbarkeit.ausfahrten_sichtbar(fertiger_nutzer('carla')).exists())
        self.assertFalse(sichtbarkeit.ausfahrten_sichtbar(AnonymousUser()).exists())

    def test_verbindung_schlaegt_crew(self):
        # Eine gemeinsame Crew darf eine bestehende Verbindung nicht auf
        # oeffentlich druecken.
        crew_mit(self.anna, self.ben)
        ablaeufe.verbindung_anlegen(self.anna, self.ben, Verbindung.Entstehung.ANFRAGE)
        self.assertSiehtBis(self.anna, self.ben, Stufe.VERBUNDEN)


class VerbundenUndRidebuddiesTest(SichtTestCase):
    def test_verbunden_sieht_felder_und_beitraege_bis_verbunden(self):
        ablaeufe.verbindung_anlegen(self.anna, self.ben, Verbindung.Entstehung.ANFRAGE)
        self.assertSiehtBis(self.anna, self.ben, Stufe.VERBUNDEN)
        sicht = sichtbarkeit.profil_sicht(self.anna, self.ben)
        self.assertIn(VERBUNDENES_FELD, sicht)
        self.assertNotIn(RIDEBUDDY_FELD, sicht)

    def test_ridebuddies_sehen_alles(self):
        ridebuddies_machen(self.anna, self.ben)
        self.assertSiehtBis(self.anna, self.ben, Stufe.RIDEBUDDIES)
        self.assertIn(RIDEBUDDY_FELD, sichtbarkeit.profil_sicht(self.anna, self.ben))

    def test_vom_nutzer_hochgestellte_feldstufe_wirkt(self):
        # Ben stellt die (voreingestellt oeffentliche) Region auf Ridebuddies:
        # eine blosse Verbindung sieht sie nicht mehr.
        profil = Profil.objects.get(nutzer=self.ben)
        profil.feldstufen[OEFFENTLICHES_FELD] = Stufe.RIDEBUDDIES.value
        profil.full_clean()
        profil.save()
        ablaeufe.verbindung_anlegen(self.anna, self.ben, Verbindung.Entstehung.ANFRAGE)
        self.assertNotIn(OEFFENTLICHES_FELD, sichtbarkeit.profil_sicht(self.anna, self.ben))

    def test_vom_nutzer_heruntergestellte_feldstufe_wirkt(self):
        # Ben stellt sein (voreingestellt verbundenes) No-Go auf oeffentlich:
        # schon ein Vorschlag zeigt es.
        profil = Profil.objects.get(nutzer=self.ben)
        profil.feldstufen[VERBUNDENES_FELD] = Stufe.OEFFENTLICH.value
        profil.save()
        vorschlag(empfaenger=self.anna, kandidat=self.ben)
        self.assertIn(VERBUNDENES_FELD, sichtbarkeit.profil_sicht(self.anna, self.ben))

    def test_feldstufe_0_nicht_waehlbar(self):
        from django.core.exceptions import ValidationError
        profil = Profil.objects.get(nutzer=self.ben)
        profil.feldstufen = {OEFFENTLICHES_FELD: 0}
        with self.assertRaises(ValidationError):
            profil.full_clean()


class SenkenTest(SichtTestCase):
    def setUp(self):
        super().setUp()
        self.verbindung = ridebuddies_machen(self.anna, self.ben)

    def test_einseitiges_senken_wirkt_nur_in_eine_richtung(self):
        # Anna senkt still: Ben sieht von Anna nur noch "verbunden" ...
        ablaeufe.stufe_senken(self.verbindung, self.anna)
        self.assertSiehtBis(self.ben, self.anna, Stufe.VERBUNDEN)

    def test_senkender_sieht_unveraendert(self):
        # ... Anna sieht von Ben weiterhin, was Ben gewaehrt: Ridebuddies.
        ablaeufe.stufe_senken(self.verbindung, self.anna)
        self.assertSiehtBis(self.anna, self.ben, Stufe.RIDEBUDDIES)

    def test_senken_unter_verbunden_geht_nicht(self):
        ablaeufe.stufe_senken(self.verbindung, self.anna)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.stufe_senken(self.verbindung, self.anna)

    def test_beenden_nimmt_beiden_die_sicht(self):
        ablaeufe.verbindung_beenden(self.verbindung, self.anna, Ausgang.NICHT_JETZT)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)
        self.verbindung.refresh_from_db()
        self.assertIsNotNone(self.verbindung.wiedervorlage_ab)
        self.assertFalse(Ausschluss.objects.exists())

    def test_beenden_mit_passt_nicht_schliesst_aus(self):
        ablaeufe.verbindung_beenden(self.verbindung, self.anna, Ausgang.PASST_NICHT,
                                    grund_dimension=Dimension.TEMPO)
        ausschluss = Ausschluss.objects.get()
        self.assertEqual((ausschluss.urheber, ausschluss.betroffener), (self.anna, self.ben))
        self.assertEqual(ausschluss.quelle, Ausschluss.Quelle.VERBINDUNG)


class AusschlussTest(SichtTestCase):
    def _alle_wege_oeffnen(self):
        """Gemeinsame Crew, offene Vorschlaege in beide Richtungen, offene Anfrage."""
        crew_mit(self.anna, self.ben)
        vorschlag(empfaenger=self.anna, kandidat=self.ben)
        vorschlag(empfaenger=self.ben, kandidat=self.anna)
        ablaeufe.anfrage_stellen(self.anna, self.ben)

    def test_ausgeschlossen_sieht_in_beiden_richtungen_nichts(self):
        self._alle_wege_oeffnen()
        ablaeufe.ausschliessen(self.anna, self.ben, Ausschluss.Quelle.VORSCHLAG)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        self.assertSiehtBis(self.ben, self.anna, Stufe.KEINE)

    def test_ausschluss_beendet_verbindung(self):
        ablaeufe.verbindung_anlegen(self.anna, self.ben, Verbindung.Entstehung.ANFRAGE)
        ablaeufe.ausschliessen(self.ben, self.anna, Ausschluss.Quelle.FEEDBACK)
        self.assertIsNone(sichtbarkeit.aktive_verbindung(self.anna, self.ben))
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.verbindung_anlegen(self.anna, self.ben, Verbindung.Entstehung.ANFRAGE)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.anfrage_stellen(self.anna, self.ben)

    def test_passt_nicht_beim_vorschlag_schliesst_mit_dimension_aus(self):
        v = vorschlag(empfaenger=self.anna, kandidat=self.ben)
        ablaeufe.vorschlag_reagieren(v, v.empfaenger, Vorschlag.Reaktion.PASST_NICHT,
                                     grund_dimension=Dimension.FAHRART,
                                     grund_text='nur Rennstrecke')
        ausschluss = Ausschluss.objects.get()
        self.assertEqual(ausschluss.grund_dimension, Dimension.FAHRART)
        self.assertSiehtBis(self.anna, self.ben, Stufe.KEINE)

    def test_grund_nur_beim_urheber(self):
        ablaeufe.ausschliessen(self.anna, self.ben, Ausschluss.Quelle.VORSCHLAG,
                               grund_dimension=Dimension.TEMPO, grund_text='viel zu schnell')
        ausschluss = Ausschluss.objects.get()
        self.assertEqual(sichtbarkeit.ausschluss_grund(self.anna, ausschluss),
                         (Dimension.TEMPO, 'viel zu schnell'))
        self.assertIsNone(sichtbarkeit.ausschluss_grund(self.ben, ausschluss))
        dritter = fertiger_nutzer('carla')
        self.assertIsNone(sichtbarkeit.ausschluss_grund(dritter, ausschluss))
        # Der Betroffene erfaehrt nicht einmal, dass es den Ausschluss gibt.
        self.assertEqual(list(sichtbarkeit.ausschluesse_sichtbar(self.anna)), [ausschluss])
        self.assertFalse(sichtbarkeit.ausschluesse_sichtbar(self.ben).exists())


class FremdprofilTest(SichtTestCase):
    def setUp(self):
        super().setUp()
        self.carla = fertiger_nutzer('carla')
        # Anna ist mit Ben und mit Carla verbunden, teilt aber nur mit Ben.
        ablaeufe.verbindung_anlegen(self.anna, self.ben, Verbindung.Entstehung.ANFRAGE)
        ablaeufe.verbindung_anlegen(self.anna, self.carla, Verbindung.Entstehung.ANFRAGE)
        self.fp = Fremdprofil.objects.create(inhaber=self.anna,
                                             dienst=Fremdprofil.Dienst.STEGRA, wert='anna_s')

    def test_fremdprofil_ohne_teilen_sieht_niemand(self):
        self.assertFalse(sichtbarkeit.fremdprofile_sichtbar(self.ben).exists())
        self.assertFalse(sichtbarkeit.fremdprofile_sichtbar(self.carla).exists())
        self.assertEqual(list(sichtbarkeit.fremdprofile_sichtbar(self.anna)), [self.fp])

    def test_fremdprofil_nur_beim_empfaenger_des_teilens(self):
        ablaeufe.fremdprofil_teilen(self.fp, self.ben)
        self.assertEqual(list(sichtbarkeit.fremdprofile_sichtbar(self.ben)), [self.fp])
        # Carla ist genauso verbunden - Teilen gilt je Empfaenger, nicht je Stufe.
        self.assertFalse(sichtbarkeit.fremdprofile_sichtbar(self.carla).exists())

    def test_teilen_nur_mit_verbundenen(self):
        fremder = fertiger_nutzer('dieter')
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.fremdprofil_teilen(self.fp, fremder)

    def test_geteiltes_fremdprofil_bleibt_nach_beenden(self):
        ablaeufe.fremdprofil_teilen(self.fp, self.ben)
        ablaeufe.verbindung_beenden(sichtbarkeit.aktive_verbindung(self.anna, self.ben),
                                    self.anna, Ausgang.NICHT_JETZT)
        self.assertEqual(list(sichtbarkeit.fremdprofile_sichtbar(self.ben)), [self.fp])

    def test_ausschluss_nimmt_geteiltes_fremdprofil(self):
        ablaeufe.fremdprofil_teilen(self.fp, self.ben)
        ablaeufe.ausschliessen(self.anna, self.ben, Ausschluss.Quelle.VERBINDUNG)
        self.assertFalse(sichtbarkeit.fremdprofile_sichtbar(self.ben).exists())


class NachrichtenTest(SichtTestCase):
    def test_direktnachricht_nur_bei_verbindung(self):
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.nachricht_senden(self.anna, 'Hallo', empfaenger=self.ben)
        verbinden(self.anna, self.ben)
        n = ablaeufe.nachricht_senden(self.anna, 'Hallo', empfaenger=self.ben)
        self.assertIn(n, sichtbarkeit.nachrichten_sichtbar(self.ben))
        self.assertFalse(sichtbarkeit.nachrichten_sichtbar(fertiger_nutzer('carla')).exists())

    def test_nach_beenden_verlauf_lesbar_aber_nicht_schreibbar(self):
        # Fabian, 23.09.2026 (Nacharbeit): Verlauf bleibt fuer beide lesbar,
        # neue Nachrichten verweigert.
        verbindung = verbinden(self.anna, self.ben)
        n = ablaeufe.nachricht_senden(self.anna, 'Hallo', empfaenger=self.ben)
        antwort = ablaeufe.nachricht_senden(self.ben, 'Servus', empfaenger=self.anna)
        ablaeufe.verbindung_beenden(verbindung, self.ben, Ausgang.NICHT_JETZT)
        for wer in (self.anna, self.ben):
            self.assertEqual(list(sichtbarkeit.nachrichten_sichtbar(wer)), [n, antwort])
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.nachricht_senden(self.anna, 'Noch da?', empfaenger=self.ben)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.nachricht_senden(self.ben, 'Noch da?', empfaenger=self.anna)

    def test_ausschluss_nimmt_den_verlauf(self):
        verbinden(self.anna, self.ben)
        ablaeufe.nachricht_senden(self.anna, 'Hallo', empfaenger=self.ben)
        ablaeufe.nachricht_senden(self.ben, 'Servus', empfaenger=self.anna)
        ablaeufe.ausschliessen(self.ben, self.anna, Ausschluss.Quelle.VERBINDUNG)
        self.assertFalse(sichtbarkeit.nachrichten_sichtbar(self.anna).exists())
        self.assertFalse(sichtbarkeit.nachrichten_sichtbar(self.ben).exists())

    def test_crew_chat_ohne_ausgeschlossene(self):
        carla = fertiger_nutzer('carla')
        crew = crew_mit(self.anna, self.ben, carla)
        von_ben = ablaeufe.nachricht_senden(self.ben, 'Sonntag?', crew=crew)
        von_carla = ablaeufe.nachricht_senden(carla, 'Bin dabei', crew=crew)
        ablaeufe.ausschliessen(self.anna, self.ben, Ausschluss.Quelle.FEEDBACK)
        # Anna sieht Carla, aber nichts von Ben; Ben nichts von Anna.
        self.assertEqual(list(sichtbarkeit.nachrichten_sichtbar(self.anna)), [von_carla])
        von_anna = ablaeufe.nachricht_senden(self.anna, 'Ich auch', crew=crew)
        self.assertNotIn(von_anna, sichtbarkeit.nachrichten_sichtbar(self.ben))
        self.assertIn(von_ben, sichtbarkeit.nachrichten_sichtbar(carla))

    def test_crew_chat_nur_fuer_mitglieder(self):
        crew = crew_mit(self.anna)
        with self.assertRaises(ablaeufe.NichtErlaubt):
            ablaeufe.nachricht_senden(self.ben, 'Darf ich?', crew=crew)
        ablaeufe.nachricht_senden(self.anna, 'Intern', crew=crew)
        self.assertFalse(sichtbarkeit.nachrichten_sichtbar(self.ben).exists())
