"""
Sichtbarkeitsschicht - wer sieht was von wem.

Karte TASK-120.04, Regeln von Fabian am 23.09.2026 (Notiz
haus/08-Ideen/Ridebuddies.md, "Das Beziehungsmodell"). Alles, was spaeter eine
View, ein Template oder eine API ausgibt, soll HIER durch - nicht an den
Modellen vorbei per `Profil.objects.get(...)`. Deshalb laufen die Tests gegen
diese Funktionen und nicht gegen Views: Eine Regel, die nur in einer View steht,
gilt fuer die naechste View schon nicht mehr.

Die Kette in stufe_fuer() ist die ganze Logik; die Reihenfolge ist Absicht:

  1. nicht angemeldet                         -> 0 (ohne Anmeldung nichts)
  2. sich selbst                              -> 3 (man sieht alles von sich)
  3. Ausschluss in IRGENDEINER Richtung       -> 0 - schlaegt alles Folgende,
     auch gemeinsame Crew und offenen Vorschlag (Fabian: "auch nicht ueber Crew")
  4. aktive Verbindung                        -> die Stufe, die der INHABER
     gewaehrt (einseitiges stilles Senken: was B von A sieht, bestimmt A)
  5. Vorschlag an den Betrachter ueber den Inhaber, der noch Sicht gibt
     (vorschlag_gibt_sicht - offen, oder angenommen und nicht ueberholt),
     offene Anfrage des Inhabers an den Betrachter,
     gemeinsame Crew (jede Rolle, auch Gast)  -> 1 (oeffentlich)
  6. sonst                                    -> 0 (kein Durchstoebern)

Punkt 4 vor Punkt 5: Eine Verbindung liefert immer >= 2, eine gemeinsame Crew
darf sie nicht auf 1 druecken.
"""
from django.db.models import Q

from .models import (
    FELD_VOREINSTELLUNG,
    Anfrage,
    Ausfahrt,
    Ausschluss,
    Beitrag,
    Crew,
    Feedback,
    Fremdprofil,
    Mitgliedschaft,
    Nachricht,
    Profil,
    Stufe,
    Verbindung,
    Vorschlag,
)


def _angemeldet(nutzer):
    return nutzer is not None and getattr(nutzer, 'is_authenticated', False) and nutzer.is_active


def ausgeschlossen(a, b):
    """True, wenn einer der beiden den anderen ausgeschlossen hat."""
    return Ausschluss.objects.filter(
        Q(urheber=a, betroffener=b) | Q(urheber=b, betroffener=a)
    ).exists()


def aktive_verbindung(a, b):
    """Die aktive (nicht beendete) Verbindung zwischen a und b oder None."""
    erster, zweiter = (a, b) if a.pk < b.pk else (b, a)
    return Verbindung.objects.filter(
        nutzer_a=erster, nutzer_b=zweiter, beendet_am__isnull=True
    ).first()


def gemeinsame_crew(a, b):
    """True, wenn a und b in derselben Crew sind (Organisator, Mitglied oder Gast)."""
    return Mitgliedschaft.objects.filter(
        nutzer=b, crew__mitgliedschaften__nutzer=a
    ).exists()


def vorschlag_gibt_sicht(empfaenger, kandidat):
    """True, wenn ein Vorschlag an `empfaenger` ueber `kandidat` noch Sicht gibt.

    Festlegung der Hauptsitzung (23.09.2026, Nacharbeit nach Auflage A1 des
    gegenpruefer): Ein Vorschlag gibt Sicht, solange er OFFEN ist - oder
    ANGENOMMEN, solange
      (a) der Gegenueber auf seinen Vorschlag ueber den Empfaenger seither nicht
          negativ reagiert hat ("nicht jetzt" / "passt nicht"), und
      (b) zwischen beiden seit der Annahme keine Verbindung entstanden ist -
          auch keine inzwischen beendete.

    Der Vorfall dahinter: Bis zur Nacharbeit zaehlte jeder angenommene Vorschlag
    unbefristet. Zwei Nutzer, die sich ueber beidseitig angenommene Vorschlaege
    verbunden und die Verbindung dann beendet hatten, sahen einander danach
    weiter auf Stufe oeffentlich - Profil und Beitraege (Probe des gegenpruefer:
    "nach Beenden (erwartet 0/0): 1 1"). Ebenso hielt ein einseitig angenommener
    Vorschlag die Sicht, wenn der andere "nicht jetzt" gesagt hatte. (b) schliesst
    die erste Luecke, (a) die zweite.
    """
    if Vorschlag.objects.filter(empfaenger=empfaenger, kandidat=kandidat,
                                reaktion=Vorschlag.Reaktion.OFFEN).exists():
        return True
    erster, zweiter = (empfaenger, kandidat) if empfaenger.pk < kandidat.pk else (kandidat, empfaenger)
    for vorschlag in Vorschlag.objects.filter(empfaenger=empfaenger, kandidat=kandidat,
                                              reaktion=Vorschlag.Reaktion.ANGENOMMEN):
        abgewiesen = Vorschlag.objects.filter(
            empfaenger=kandidat, kandidat=empfaenger,
            reaktion__in=[Vorschlag.Reaktion.NICHT_JETZT, Vorschlag.Reaktion.PASST_NICHT],
            reagiert_am__gte=vorschlag.erstellt,
        ).exists()
        # reagiert_am fehlt nur bei Datensaetzen am Ablauf vorbei (Admin; die
        # Model.clean verlangt es inzwischen). Dann gilt der Anlagezeitpunkt -
        # die vorsichtige Wahl: Jede Verbindung seit dem Vorschlag beendet seine
        # Sicht. Vorher brach stufe_fuer hier mit ValueError ab (None im Filter).
        seit = vorschlag.reagiert_am or vorschlag.erstellt
        seither_verbunden = Verbindung.objects.filter(
            nutzer_a=erster, nutzer_b=zweiter, erstellt__gte=seit,
        ).exists()
        if not abgewiesen and not seither_verbunden:
            return True
    return False


def stufe_fuer(betrachter, inhaber):
    """Die Stufe (0-3), auf der `betrachter` den `inhaber` sieht. Siehe Modulkopf."""
    if not _angemeldet(betrachter) or inhaber is None:
        return Stufe.KEINE
    if betrachter.pk == inhaber.pk:
        return Stufe.RIDEBUDDIES
    if ausgeschlossen(betrachter, inhaber):
        return Stufe.KEINE

    verbindung = aktive_verbindung(betrachter, inhaber)
    if verbindung is not None:
        # Was der Betrachter sieht, bestimmt die Stufe, die der Inhaber gewaehrt.
        # Der CheckConstraint haelt sie <= erreicht, min() ist nur Absicherung.
        return Stufe(min(verbindung.gewaehrt_von(inhaber), verbindung.erreicht))

    if vorschlag_gibt_sicht(betrachter, inhaber):
        return Stufe.OEFFENTLICH
    if Anfrage.objects.filter(
        absender=inhaber, empfaenger=betrachter, status=Anfrage.Status.OFFEN
    ).exists():
        return Stufe.OEFFENTLICH
    if gemeinsame_crew(betrachter, inhaber):
        return Stufe.OEFFENTLICH
    return Stufe.KEINE


def profil_sicht(betrachter, inhaber):
    """Was `betrachter` vom Profil des `inhaber` sieht, als dict {feld: wert}.

    Leeres dict = nichts sichtbar (Stufe 0). Ab Stufe oeffentlich ist der
    Nutzername immer dabei, dazu jedes Feld, dessen (vom Inhaber gewaehlte oder
    voreingestellte) Stufe <= der Betrachterstufe ist. Die Feldstufen und die
    hart/weich-Gewichtung selbst gibt diese Funktion nie heraus.
    """
    stufe = stufe_fuer(betrachter, inhaber)
    if stufe == Stufe.KEINE:
        return {}
    profil = Profil.objects.get(nutzer=inhaber)
    sicht = {'nutzername': inhaber.username}
    for feld in FELD_VOREINSTELLUNG:
        if profil.feldstufe(feld) <= stufe:
            sicht[feld] = getattr(profil, feld)
    return sicht


def beitraege_sichtbar(betrachter, inhaber):
    """Beitraege des `inhaber`, die `betrachter` lesen darf (Queryset)."""
    stufe = stufe_fuer(betrachter, inhaber)
    if stufe == Stufe.KEINE:
        return Beitrag.objects.none()
    return Beitrag.objects.filter(autor=inhaber, stufe__lte=stufe)


def fremdprofile_sichtbar(betrachter):
    """Fremdprofile, die `betrachter` sieht: die eigenen und die ihm
    ausdruecklich geteilten - ausser von jemandem, mit dem ein Ausschluss
    besteht (der schlaegt auch eine fruehere Teilung).

    Festlegung der Hauptsitzung (23.09.2026): Nach dem BEENDEN einer
    Verbindung bleibt ein geteiltes Fremdprofil sichtbar - wie der Chatverlauf;
    die Teilung war eine bewusste Handlung. Erst ein Ausschluss nimmt es weg.
    Neu teilen geht nur an aktiv Verbundene (ablaeufe.fremdprofil_teilen)."""
    if not _angemeldet(betrachter):
        return Fremdprofil.objects.none()
    ausgeschlossene = _ausgeschlossene_ids(betrachter)
    return Fremdprofil.objects.filter(
        Q(inhaber=betrachter)
        | (Q(teilungen__empfaenger=betrachter) & ~Q(inhaber__in=ausgeschlossene))
    ).distinct()


def feedback_sichtbar(betrachter):
    """Feedback, das `betrachter` sieht: nur das selbst verfasste.
    Kein anderer Nutzer - auch nicht der Bewertete - sieht es (Fabian, 23.09.2026)."""
    if not _angemeldet(betrachter):
        return Feedback.objects.none()
    return Feedback.objects.filter(verfasser=betrachter)


def ausschluesse_sichtbar(betrachter):
    """Ausschluesse, die `betrachter` sieht: nur die eigenen. Der Betroffene
    erfaehrt weder vom Ausschluss noch vom Grund ("der andere erfaehrt den Grund nie")."""
    if not _angemeldet(betrachter):
        return Ausschluss.objects.none()
    return Ausschluss.objects.filter(urheber=betrachter)


def ausschluss_grund(betrachter, ausschluss):
    """Grund eines Ausschlusses als (dimension, text) - nur fuer den Urheber, sonst None."""
    if not _angemeldet(betrachter) or ausschluss.urheber_id != betrachter.pk:
        return None
    return (ausschluss.grund_dimension, ausschluss.grund_text)


def nachrichten_sichtbar(betrachter):
    """Nachrichten, die `betrachter` lesen darf (Queryset).

    - Direktnachrichten: fuer Absender und Empfaenger, solange zwischen beiden
      kein Ausschluss besteht. Fabian, 23.09.2026 (Nacharbeit): Nach dem
      Beenden einer Verbindung bleibt der Verlauf fuer beide lesbar, aber nicht
      mehr schreibbar (ablaeufe.nachricht_senden verweigert); bei einem
      Ausschluss verschwindet er. Geschrieben werden konnte eine
      Direktnachricht ohnehin nur bei aktiver Verbindung.
    - Crew-Nachrichten: fuer aktuelle Mitglieder (jede Rolle) der Crew,
      aber nichts von Ausgeschlossenen (Festlegung der Hauptsitzung).
    """
    if not _angemeldet(betrachter):
        return Nachricht.objects.none()
    ausgeschlossene = _ausgeschlossene_ids(betrachter)
    direkt = (
        Q(crew__isnull=True)
        & ((Q(absender=betrachter) & ~Q(empfaenger__in=ausgeschlossene))
           | Q(empfaenger=betrachter))
    )
    crews = Crew.objects.filter(mitgliedschaften__nutzer=betrachter)
    in_crew = Q(crew__in=crews) & ~Q(absender__in=ausgeschlossene)
    return Nachricht.objects.filter(direkt | in_crew).exclude(absender__in=ausgeschlossene)


def ausfahrten_sichtbar(betrachter):
    """Ausfahrten, die `betrachter` sieht: die seiner Crews (jede Rolle, auch
    Gast - Fabian: "plus Crew-Chat/Ausfahrten der Crew"), die, an denen er
    teilnimmt, und die er selbst vorgeschlagen hat.

    Festlegung der Hauptsitzung (23.09.2026): Ein Ausschluss blendet eine
    gemeinsame Crew-Ausfahrt NICHT aus - sonst koennte ein einzelner Ausschluss
    einem Mitglied die Ausfahrten der eigenen Crew nehmen.
    AUFLAGE FUER SCHRITT 13: Diese Funktion gibt nur die Ausfahrt frei, nicht
    die Menschen daran. Wer eine Ausfahrt anzeigt, muss Urheber
    (`vorgeschlagen_von`) und Teilnehmer einzeln durch stufe_fuer() schicken und
    Ausgeschlossene (Stufe 0) weglassen - sonst ist der Ausschluss ueber die
    Teilnehmerliste unterlaufen.
    """
    if not _angemeldet(betrachter):
        return Ausfahrt.objects.none()
    return Ausfahrt.objects.filter(
        Q(crew__mitgliedschaften__nutzer=betrachter)
        | Q(teilnahmen__nutzer=betrachter)
        | Q(vorgeschlagen_von=betrachter)
    ).distinct()


def _ausgeschlossene_ids(nutzer):
    """IDs aller Nutzer, zu denen ein Ausschluss in irgendeiner Richtung besteht."""
    von_mir = Ausschluss.objects.filter(urheber=nutzer).values_list('betroffener_id', flat=True)
    von_anderen = Ausschluss.objects.filter(betroffener=nutzer).values_list('urheber_id', flat=True)
    return set(von_mir) | set(von_anderen)
