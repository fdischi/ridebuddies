"""
Zustandswechsel - die einzigen Wege, auf denen sich Beziehungen aendern.

Karte TASK-120.04 (23.09.2026). Views gibt es noch keine (Oberflaeche: Etappe 3);
diese Funktionen sind das, was die spaeteren Views aufrufen, und das, wogegen die
Tests heute laufen. Wer eine Verbindung, einen Ausschluss oder eine Stufe an
diesen Funktionen vorbei per `.save()` aendert, umgeht die Regeln - der Admin
kann das (in der Dummy-Phase gewollt), eine View soll es nicht.

Verstoesse gegen eine Regel heben `NichtErlaubt`; das ist ein fachlicher
Fehler fuer die Oberflaeche, kein Programmfehler.

Wer handelt, steht als Pflichtparameter `akteur` (bzw. `nutzer`/`urheber`/
`absender`) in der Signatur und wird geprueft - nie aus dem Objekt abgeleitet.
Anlass (Nachpruefung des gegenpruefer, 23.09.2026, Auflage A4):
ridebuddy_anfrage_beantworten(anfrage, True) nahm keinen Akteur entgegen; der
Absender konnte seine eigene Anfrage bestaetigen und war damit ohne Zustimmung
des anderen auf Stufe Ridebuddies. Die spaetere View haette den angemeldeten
Nutzer uebergeben muessen und keine Stelle gehabt, an der das geprueft wird.

Grundlage: Notiz haus/08-Ideen/Ridebuddies.md, "Das Beziehungsmodell"
(Reaktionen, Anfragen, Rueckkopplung Sorte 1/2), plus die Festlegungen der
Hauptsitzung, die am Ort markiert sind.
"""
import calendar
import datetime

from django.db import transaction
from django.utils import timezone

from .models import (
    Anfrage,
    Ausfahrt,
    Ausgang,
    Ausschluss,
    Feedback,
    Mitgliedschaft,
    Nachricht,
    RidebuddyAnfrage,
    Stufe,
    Teilnahme,
    Teilung,
    Verbindung,
    Vorschlag,
)
from .sichtbarkeit import aktive_verbindung, ausgeschlossen

# "nicht jetzt" = sechs Monate Wiedervorlage-Sperre (Notiz, Reaktionen).
WIEDERVORLAGE_MONATE = 6


class NichtErlaubt(Exception):
    """Ein Zustandswechsel verstoesst gegen eine Regel des Beziehungsmodells."""


def plus_monate(datum, monate):
    """Datum + n Monate, am Monatsende gekappt (31.08. + 6 = 28./29.02.).
    Ohne python-dateutil, um keine Abhaengigkeit nur dafuer mitzuziehen."""
    monat_index = datum.month - 1 + monate
    jahr = datum.year + monat_index // 12
    monat = monat_index % 12 + 1
    tag = min(datum.day, calendar.monthrange(jahr, monat)[1])
    return datetime.date(jahr, monat, tag)


def _heute():
    return timezone.localdate()


# ---------------------------------------------------------------------------
# Verbindung
# ---------------------------------------------------------------------------

def verbindung_anlegen(a, b, entstanden_durch):
    """Legt die aktive Verbindung zwischen a und b an (oder gibt die bestehende
    zurueck) - immer auf Stufe verbunden, in beide Richtungen.

    Bis zur Nacharbeit vom 23.09.2026 nahm diese Funktion ein `erreicht`
    entgegen und konnte damit direkt Stufe 3 anlegen. Das ist weg (Hinweis des
    gegenpruefer): Stufe Ridebuddies entsteht nur ueber die Bestaetigung einer
    RidebuddyAnfrage (ridebuddy_anfrage_beantworten), sonst waere die Regel
    "nur mit Bestaetigung" mit einem Argument zu umgehen."""
    if a.pk == b.pk:
        raise NichtErlaubt('Verbindung mit sich selbst')
    if ausgeschlossen(a, b):
        raise NichtErlaubt('Zwischen diesen Nutzern besteht ein Ausschluss')
    bestehend = aktive_verbindung(a, b)
    if bestehend is not None:
        return bestehend
    erster, zweiter = (a, b) if a.pk < b.pk else (b, a)
    return Verbindung.objects.create(
        nutzer_a=erster, nutzer_b=zweiter, entstanden_durch=entstanden_durch,
        erreicht=Stufe.VERBUNDEN, gewaehrt_a=Stufe.VERBUNDEN, gewaehrt_b=Stufe.VERBUNDEN,
    )


def stufe_senken(verbindung, nutzer):
    """Einseitiges, stilles Senken (Fabian, 23.09.2026): `nutzer` gewaehrt dem
    anderen nur noch 'verbunden'. Der andere sieht von `nutzer` danach weniger;
    `nutzer` sieht vom anderen unveraendert, was der andere gewaehrt.

    Festlegung der Hauptsitzung: nur von Ridebuddies auf verbunden. Wer weiter
    runter will, beendet die Verbindung (verbindung_beenden).
    Nicht gebaut: das Wieder-Anheben der eigenen Stufe (Schritt 12).
    """
    if not verbindung.aktiv:
        raise NichtErlaubt('Verbindung ist beendet')
    if not verbindung.ist_beteiligt(nutzer):
        raise NichtErlaubt('Nicht an dieser Verbindung beteiligt')
    if verbindung.gewaehrt_von(nutzer) != Stufe.RIDEBUDDIES:
        raise NichtErlaubt('Senken geht nur von Ridebuddies auf verbunden; '
                           'darunter heißt es beenden')
    if nutzer.pk == verbindung.nutzer_a_id:
        verbindung.gewaehrt_a = Stufe.VERBUNDEN
    else:
        verbindung.gewaehrt_b = Stufe.VERBUNDEN
    verbindung.save(update_fields=['gewaehrt_a', 'gewaehrt_b'])
    return verbindung


@transaction.atomic
def verbindung_beenden(verbindung, nutzer, ausgang, grund_dimension='', grund_text=''):
    """Still beenden mit den zwei Ausgaengen der Notiz:
    'nicht jetzt' -> Wiedervorlage-Sperre +6 Monate auf der Verbindung;
    'passt nicht' -> Ausschluss (dauerhaft, Grund nur beim Urheber)."""
    if not verbindung.aktiv:
        raise NichtErlaubt('Verbindung ist bereits beendet')
    if not verbindung.ist_beteiligt(nutzer):
        raise NichtErlaubt('Nicht an dieser Verbindung beteiligt')
    if ausgang not in Ausgang.values:
        raise NichtErlaubt(f'Unbekannter Ausgang: {ausgang!r}')
    verbindung.beendet_am = timezone.now()
    verbindung.beendet_von = nutzer
    verbindung.beendet_ausgang = ausgang
    if ausgang == Ausgang.NICHT_JETZT:
        verbindung.wiedervorlage_ab = plus_monate(_heute(), WIEDERVORLAGE_MONATE)
    verbindung.save()
    _ridebuddy_anfragen_hinfaellig(verbindung)
    if ausgang == Ausgang.PASST_NICHT:
        ausschliessen(nutzer, verbindung.anderer(nutzer), Ausschluss.Quelle.VERBINDUNG,
                      grund_dimension, grund_text)
    return verbindung


@transaction.atomic
def ausschliessen(urheber, betroffener, quelle, grund_dimension='', grund_text=''):
    """Ausschluss anlegen - dauerhaft, beidseitig wirksam. Eine aktive
    Verbindung zwischen beiden endet dabei (Ausgang 'passt nicht').
    Ein zweiter Ausschluss in dieselbe Richtung aendert den ersten nicht."""
    if urheber.pk == betroffener.pk:
        raise NichtErlaubt('Ausschluss seiner selbst')
    ausschluss, _ = Ausschluss.objects.get_or_create(
        urheber=urheber, betroffener=betroffener,
        defaults={'quelle': quelle, 'grund_dimension': grund_dimension,
                  'grund_text': grund_text},
    )
    verbindung = aktive_verbindung(urheber, betroffener)
    if verbindung is not None:
        verbindung.beendet_am = timezone.now()
        verbindung.beendet_von = urheber
        verbindung.beendet_ausgang = Ausgang.PASST_NICHT
        verbindung.save()
        _ridebuddy_anfragen_hinfaellig(verbindung)
    return ausschluss


def _ridebuddy_anfragen_hinfaellig(verbindung):
    """Offene Ridebuddy-Anfragen einer endenden Verbindung abschliessen.

    Festlegung der Hauptsitzung (23.09.2026): Sie stehen danach auf
    'hinfaellig' statt ewig auf 'offen' - eine offene Anfrage, die niemand mehr
    beantworten kann, wuerde in jeder kuenftigen Liste "offene Anfragen"
    auftauchen. Gerufen beim Beenden und beim Ausschluss (der beendet mit)."""
    verbindung.ridebuddy_anfragen.filter(status=RidebuddyAnfrage.Status.OFFEN).update(
        status=RidebuddyAnfrage.Status.HINFAELLIG, beantwortet_am=verbindung.beendet_am)


# ---------------------------------------------------------------------------
# Vorschlag und Anfrage
# ---------------------------------------------------------------------------

@transaction.atomic
def vorschlag_reagieren(vorschlag, akteur, reaktion, grund_dimension='', grund_text=''):
    """Reaktion des Empfaengers auf einen Vorschlag. Nur der Empfaenger
    (`akteur` == vorschlag.empfaenger) darf reagieren.

    annehmen    -> wartet auf den anderen; hat der Kandidat seinen Vorschlag
                   ueber den Empfaenger ebenfalls angenommen, entsteht die
                   Verbindung (Stufe verbunden).
    nicht jetzt -> Wiedervorlage-Datum +6 Monate.
    passt nicht -> Ausschluss, optional mit angetippter Dimension als Grund.
    """
    if akteur.pk != vorschlag.empfaenger_id:
        raise NichtErlaubt('Nur der Empfänger reagiert auf einen Vorschlag')
    if vorschlag.reaktion != Vorschlag.Reaktion.OFFEN:
        raise NichtErlaubt('Auf diesen Vorschlag wurde schon reagiert')
    if ausgeschlossen(vorschlag.empfaenger, vorschlag.kandidat):
        raise NichtErlaubt('Zwischen diesen Nutzern besteht ein Ausschluss')
    if reaktion not in (Vorschlag.Reaktion.ANGENOMMEN, Vorschlag.Reaktion.NICHT_JETZT,
                        Vorschlag.Reaktion.PASST_NICHT):
        raise NichtErlaubt(f'Unbekannte Reaktion: {reaktion!r}')

    vorschlag.reaktion = reaktion
    vorschlag.reagiert_am = timezone.now()
    if reaktion == Vorschlag.Reaktion.NICHT_JETZT:
        vorschlag.wiedervorlage_ab = plus_monate(_heute(), WIEDERVORLAGE_MONATE)
    vorschlag.save()

    if reaktion == Vorschlag.Reaktion.PASST_NICHT:
        ausschliessen(vorschlag.empfaenger, vorschlag.kandidat, Ausschluss.Quelle.VORSCHLAG,
                      grund_dimension, grund_text)
        return None
    if reaktion == Vorschlag.Reaktion.ANGENOMMEN:
        gegenseite_angenommen = Vorschlag.objects.filter(
            empfaenger=vorschlag.kandidat, kandidat=vorschlag.empfaenger,
            reaktion=Vorschlag.Reaktion.ANGENOMMEN,
        ).exists()
        if gegenseite_angenommen:
            return verbindung_anlegen(vorschlag.empfaenger, vorschlag.kandidat,
                                      Verbindung.Entstehung.VORSCHLAG)
    return None


def anfrage_stellen(absender, empfaenger, text=''):
    """Direkte, sichtbare Anfrage. Das Wochenkontingent (ANFRAGEN_JE_WOCHE)
    wird hier NICHT durchgesetzt - das ist Schritt 12 (Festlegung der Hauptsitzung)."""
    if absender.pk == empfaenger.pk:
        raise NichtErlaubt('Anfrage an sich selbst')
    if ausgeschlossen(absender, empfaenger):
        raise NichtErlaubt('Zwischen diesen Nutzern besteht ein Ausschluss')
    if aktive_verbindung(absender, empfaenger) is not None:
        raise NichtErlaubt('Bereits verbunden')
    return Anfrage.objects.create(absender=absender, empfaenger=empfaenger, text=text)


@transaction.atomic
def anfrage_beantworten(anfrage, akteur, annehmen):
    """Empfaenger nimmt an (-> Verbindung) oder lehnt ab (-> nichts weiter;
    ausdruecklich KEIN Ausschluss, das ist nicht entschieden). Nur der
    Empfaenger (`akteur`) darf beantworten."""
    if akteur.pk != anfrage.empfaenger_id:
        raise NichtErlaubt('Nur der Empfänger beantwortet eine Anfrage')
    if anfrage.status != Anfrage.Status.OFFEN:
        raise NichtErlaubt('Anfrage ist schon beantwortet')
    anfrage.beantwortet_am = timezone.now()
    if not annehmen:
        anfrage.status = Anfrage.Status.ABGELEHNT
        anfrage.save()
        return None
    if ausgeschlossen(anfrage.absender, anfrage.empfaenger):
        raise NichtErlaubt('Zwischen diesen Nutzern besteht ein Ausschluss')
    anfrage.status = Anfrage.Status.ANGENOMMEN
    anfrage.save()
    return verbindung_anlegen(anfrage.absender, anfrage.empfaenger,
                              Verbindung.Entstehung.ANFRAGE)


# ---------------------------------------------------------------------------
# Stufe Ridebuddies
# ---------------------------------------------------------------------------

def ridebuddy_anfrage_stellen(absender, empfaenger):
    """A bittet B sichtbar, Ridebuddies zu werden (Fabian, 23.09.2026, Nacharbeit).

    Nur zwischen aktiv Verbundenen; nicht bei Ausschluss; nicht, wenn die
    Verbindung schon Stufe 3 erreicht hat; je Paar hoechstens eine offene (in
    welche Richtung auch immer - die Datenbank sichert das je Verbindung ab,
    hier kommt die verstaendliche Meldung). Eine gemeinsame Plattform-Ausfahrt
    ist ausdruecklich KEINE Voraussetzung.
    """
    if absender.pk == empfaenger.pk:
        raise NichtErlaubt('Ridebuddy-Anfrage an sich selbst')
    if ausgeschlossen(absender, empfaenger):
        raise NichtErlaubt('Zwischen diesen Nutzern besteht ein Ausschluss')
    verbindung = aktive_verbindung(absender, empfaenger)
    if verbindung is None:
        raise NichtErlaubt('Ridebuddy-Anfragen nur an Verbundene - zuerst verbinden')
    if verbindung.erreicht == Stufe.RIDEBUDDIES:
        raise NichtErlaubt('Bereits Ridebuddies')
    if verbindung.ridebuddy_anfragen.filter(status=RidebuddyAnfrage.Status.OFFEN).exists():
        raise NichtErlaubt('Es gibt schon eine offene Ridebuddy-Anfrage zwischen beiden')
    return RidebuddyAnfrage.objects.create(verbindung=verbindung, absender=absender,
                                           empfaenger=empfaenger)


@transaction.atomic
def ridebuddy_anfrage_beantworten(anfrage, akteur, bestaetigen):
    """B bestaetigt (-> erreicht=3, beide gewaehrt=3) oder lehnt ab (-> nichts
    weiter, ausdruecklich kein Ausschluss). Der EINZIGE Weg zu Stufe 3.

    Nur der Empfaenger (`akteur`) darf beantworten - der Absender bestaetigt
    sich nicht selbst (Auflage A4, siehe Modulkopf).

    Ist die Verbindung inzwischen beendet oder ein Ausschluss dazugekommen,
    ist die Anfrage ohnehin 'hinfaellig' (_ridebuddy_anfragen_hinfaellig);
    die Pruefungen unten fangen zusaetzlich Datensaetze ab, die am Ablauf
    vorbei (Admin) entstanden sind."""
    if akteur.pk != anfrage.empfaenger_id:
        raise NichtErlaubt('Nur der Empfänger beantwortet eine Ridebuddy-Anfrage')
    if anfrage.status != RidebuddyAnfrage.Status.OFFEN:
        raise NichtErlaubt('Ridebuddy-Anfrage ist schon beantwortet')
    anfrage.beantwortet_am = timezone.now()
    if not bestaetigen:
        anfrage.status = RidebuddyAnfrage.Status.ABGELEHNT
        anfrage.save()
        return None
    verbindung = Verbindung.objects.select_for_update().get(pk=anfrage.verbindung_id)
    if not verbindung.aktiv:
        raise NichtErlaubt('Verbindung ist beendet')
    if ausgeschlossen(anfrage.absender, anfrage.empfaenger):
        raise NichtErlaubt('Zwischen diesen Nutzern besteht ein Ausschluss')
    anfrage.status = RidebuddyAnfrage.Status.BESTAETIGT
    anfrage.save()
    verbindung.erreicht = Stufe.RIDEBUDDIES
    verbindung.gewaehrt_a = Stufe.RIDEBUDDIES
    verbindung.gewaehrt_b = Stufe.RIDEBUDDIES
    verbindung.ridebuddies_seit = anfrage.beantwortet_am
    verbindung.save()
    return verbindung


# ---------------------------------------------------------------------------
# Rueckkopplung
# ---------------------------------------------------------------------------

@transaction.atomic
def feedback_abgeben(ausfahrt, verfasser, bewerteter, daumen=None, urteil=''):
    """Feedback nach einer Ausfahrt: Sorte 1 (`daumen`) und/oder Sorte 2 (`urteil`).

    Nur, wenn beide tatsaechlich mitgefahren sind. Folgen von Sorte 2:
    'war nix'      -> Ausschluss, still (Quelle Feedback);
    'Ridebuddy'    -> nichts Sichtbares. Seit Fabians Entscheidung vom
                      23.09.2026 (Nacharbeit) ist es nur ein stilles Signal
                      fuers System; Stufe 3 gibt es nur ueber
                      ridebuddy_anfrage_beantworten. Die fruehere Automatik
                      (beidseitig "Ridebuddy" + gemeinsame Ausfahrt -> Stufe 3)
                      ist entfernt.
    'gerne wieder' -> nichts (bleibt, wie es ist).

    Bewusst ZULAESSIG trotz Ausschluss (Festlegung der Hauptsitzung): Wer mit
    einem Ausgeschlossenen in derselben Crew-Ausfahrt sass, darf trotzdem
    Sorte 1 fuers System abgeben. Sichtbar wird dadurch nichts - Feedback sieht
    nur sein Verfasser, und keine Folge von Sorte 2 hebt eine Sicht an.
    Nicht durchgesetzt: "ausser bestehende Ridebuddies" (Notiz) - das filtert
    die Oberflaeche in Schritt 13b beim Anbieten der Fragen.
    """
    if verfasser.pk == bewerteter.pk:
        raise NichtErlaubt('Feedback über sich selbst')
    if ausfahrt.status != Ausfahrt.Status.GEFAHREN:
        raise NichtErlaubt('Feedback erst nach einer gefahrenen Ausfahrt')
    gefahren = set(Teilnahme.objects.filter(ausfahrt=ausfahrt, gefahren=True)
                   .values_list('nutzer_id', flat=True))
    if verfasser.pk not in gefahren or bewerteter.pk not in gefahren:
        raise NichtErlaubt('Beide müssen die Ausfahrt tatsächlich gefahren sein')

    feedback = Feedback(ausfahrt=ausfahrt, verfasser=verfasser, bewerteter=bewerteter,
                        daumen=daumen or {}, urteil=urteil)
    feedback.full_clean()
    feedback.save()

    if urteil == Feedback.Urteil.WAR_NIX:
        ausschliessen(verfasser, bewerteter, Ausschluss.Quelle.FEEDBACK)
    return feedback


# ---------------------------------------------------------------------------
# Chat und Teilen
# ---------------------------------------------------------------------------

def nachricht_senden(absender, text, empfaenger=None, crew=None):
    """Direktnachricht nur bei bestehender, nicht beendeter Verbindung;
    Crew-Nachricht nur als Mitglied der Crew (jede Rolle, auch Gast).
    (Festlegung der Hauptsitzung.) Nach dem Beenden bleibt der Verlauf lesbar,
    aber hier wird nichts mehr angenommen (Fabian, 23.09.2026). Dass
    Ausgeschlossene einander nicht lesen, regelt sichtbarkeit.nachrichten_sichtbar."""
    if (empfaenger is None) == (crew is None):
        raise NichtErlaubt('Entweder an einen Empfänger oder an eine Crew')
    if empfaenger is not None:
        if aktive_verbindung(absender, empfaenger) is None:
            raise NichtErlaubt('Direktnachrichten nur an Verbundene')
        if ausgeschlossen(absender, empfaenger):
            raise NichtErlaubt('Zwischen diesen Nutzern besteht ein Ausschluss')
    else:
        if not Mitgliedschaft.objects.filter(crew=crew, nutzer=absender).exists():
            raise NichtErlaubt('Nur Mitglieder schreiben in den Crew-Chat')
    return Nachricht.objects.create(absender=absender, empfaenger=empfaenger, crew=crew, text=text)


def fremdprofil_teilen(fremdprofil, empfaenger):
    """Teilen-Knopf: ein Fremdprofil gezielt einer Person zeigen.
    Nur an verbundene Nutzer (Festlegung der Hauptsitzung; die Notiz nennt den
    Teilen-Knopf bei den Stufen verbunden und Ridebuddies)."""
    inhaber = fremdprofil.inhaber
    if empfaenger.pk == inhaber.pk:
        raise NichtErlaubt('Teilen mit sich selbst')
    if aktive_verbindung(inhaber, empfaenger) is None:
        raise NichtErlaubt('Teilen nur mit Verbundenen')
    teilung, _ = Teilung.objects.get_or_create(fremdprofil=fremdprofil, empfaenger=empfaenger)
    return teilung
