"""
Datenmodell von Ridebuddies - Schritt 4 des Plans (Karte TASK-120.04, 23.09.2026).

Massgeblich ist die Plan-Notiz haus/08-Ideen/Ridebuddies.md, Abschnitte
"Der Kern (V1)", "Matching-Merkmale" und "Das Beziehungsmodell". Was dort steht,
steht hier als Struktur; was dort offen war und hier festgelegt werden musste,
ist am Ort mit "Festlegung (nicht von Fabian entschieden)" markiert.

Wer was sieht, entscheidet NICHT dieses Modul, sondern kern/sichtbarkeit.py.
Zustandswechsel (Vorschlag annehmen, senken, ausschliessen, Feedback ...) stehen
in kern/ablaeufe.py. Die Modelle tragen nur Daten und Integritaetsregeln, die
die Datenbank selbst durchsetzen kann (Eindeutigkeit, Check-Constraints).

Python-Stand: lokal 3.14, auf enduro-web 3.12.3 - nichts Juengeres als 3.12.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


# ---------------------------------------------------------------------------
# Stufen und Auswahllisten
# ---------------------------------------------------------------------------

class Stufe(models.IntegerChoices):
    """Die Vertrauensleiter aus "Das Beziehungsmodell".

    Festlegung der Hauptsitzung (23.09.2026): 1 oeffentlich, 2 verbunden,
    3 Ridebuddies; 0 = keine Sicht. Als Zahl, damit "sieht Feld mit Stufe s"
    schlicht `s <= stufe` ist. KEINE wird nie als Feld- oder Beitragsstufe
    gespeichert, sie ist nur Ergebnis von sichtbarkeit.stufe_fuer().
    """
    KEINE = 0, 'keine Sicht'
    OEFFENTLICH = 1, 'öffentlich'
    VERBUNDEN = 2, 'verbunden'
    RIDEBUDDIES = 3, 'Ridebuddies'


# Was ein Nutzer als Stufe fuer ein Feld oder einen Beitrag waehlen darf.
WAEHLBARE_STUFEN = [
    (Stufe.OEFFENTLICH.value, Stufe.OEFFENTLICH.label),
    (Stufe.VERBUNDEN.value, Stufe.VERBUNDEN.label),
    (Stufe.RIDEBUDDIES.value, Stufe.RIDEBUDDIES.label),
]


class Dimension(models.TextChoices):
    """Matching-Dimensionen - gemeinsamer Schluessel fuer Merkmal-Gewichtung
    (hart/weich), Vorschlag-Begruendung, Ausschluss-Grund ("angetippte
    Dimension") und Feedback Sorte 1 (Daumen je Dimension).

    Die ersten zwoelf sind die Merkmale aus "Matching-Merkmale" der Notiz.
    'nogo' und 'stimmung' kommen nur als Grund bzw. Feedback-Daumen vor
    ("Stimmung?" steht in der Notiz unter Rueckkopplung Sorte 1).
    Festlegung (nicht von Fabian entschieden): Zuschnitt und Schluessel.
    Die Liste der Urteils-Dimensionen fuer das KI-Matching (Schritt 8) darf sie
    erweitern; gespeichert wird der Schluessel, nicht die Beschriftung.
    """
    REGION = 'region', 'Region und Radius'
    GESCHLECHTSPRAEFERENZ = 'geschlechtspraeferenz', 'Geschlechtspräferenz'
    ALTERSWUNSCH = 'alterswunsch', 'Altersbereich-Wunsch'
    VERFUEGBARKEIT = 'verfuegbarkeit', 'Verfügbarkeit'
    FAHRART = 'fahrart', 'Fahrart'
    TEMPO = 'tempo', 'Tempo'
    ERFAHRUNG = 'erfahrung', 'Erfahrung'
    TOURENFORMAT = 'tourenformat', 'Tourenformat'
    UNTERWEGS = 'unterwegs', 'Unterwegs (Streckenfresser/Genießer, Übernachtung, Gruppe)'
    THEMEN = 'themen', 'Themen'
    SICHERHEIT = 'sicherheit', 'Sicherheit'
    MOTORRAD = 'motorrad', 'Motorrad'
    NOGO = 'nogo', 'No-Go'
    STIMMUNG = 'stimmung', 'Stimmung'


class Gewichtung(models.TextChoices):
    HART = 'hart', 'hart (Filter)'
    WEICH = 'weich', 'weich (gewichtet)'


# Voreinstellung hart/weich laut Notiz, Abschnitt "Matching-Merkmale":
# "Voreingestellt hart: Region + Radius, Geschlechtspraeferenz,
# Altersbereich-Wunsch, Verfuegbarkeit. Voreingestellt weich: alles andere."
# Jeder Nutzer stellt je Merkmal selbst um (Profil.gewichtung).
MERKMAL_VOREINSTELLUNG = {
    Dimension.REGION: Gewichtung.HART,
    Dimension.GESCHLECHTSPRAEFERENZ: Gewichtung.HART,
    Dimension.ALTERSWUNSCH: Gewichtung.HART,
    Dimension.VERFUEGBARKEIT: Gewichtung.HART,
    Dimension.FAHRART: Gewichtung.WEICH,
    Dimension.TEMPO: Gewichtung.WEICH,
    Dimension.ERFAHRUNG: Gewichtung.WEICH,
    Dimension.TOURENFORMAT: Gewichtung.WEICH,
    Dimension.UNTERWEGS: Gewichtung.WEICH,
    Dimension.THEMEN: Gewichtung.WEICH,
    Dimension.SICHERHEIT: Gewichtung.WEICH,
    Dimension.MOTORRAD: Gewichtung.WEICH,
}


class Altersbereich(models.TextChoices):
    # "Altersbereich statt Geburtsdatum" (Notiz, Randbedingung 18+). Grenzen:
    # Festlegung (nicht von Fabian entschieden).
    A18 = '18-24', '18–24'
    A25 = '25-34', '25–34'
    A35 = '35-44', '35–44'
    A45 = '45-54', '45–54'
    A55 = '55-64', '55–64'
    A65 = '65+', '65 und älter'


class Geschlecht(models.TextChoices):
    # "Geschlecht freiwillig mit 'keine Angabe' (wer nichts angibt, taucht in
    # 'nur Frauen'-Suchen nicht auf)" - Vorgabe ist deshalb KEINE_ANGABE.
    KEINE_ANGABE = 'keine_angabe', 'keine Angabe'
    WEIBLICH = 'weiblich', 'weiblich'
    MAENNLICH = 'maennlich', 'männlich'
    DIVERS = 'divers', 'divers'


class Geschlechtspraeferenz(models.TextChoices):
    GLEICH = 'gleich', 'gleich'
    GEMISCHT = 'gemischt', 'gemischt'
    EGAL = 'egal', 'egal'


class Fahrart(models.TextChoices):
    LANDSTRASSE = 'landstrasse', 'Landstraße/Kurven'
    TOURING = 'touring', 'Touring/Reise'
    ENDURO = 'enduro', 'Enduro/Schotter'
    SPORT = 'sport', 'Sport/Rennstrecke'
    CRUISEN = 'cruisen', 'Cruisen'


class Tempo(models.TextChoices):
    GEMUETLICH = 'gemuetlich', 'gemütlich'
    ZUEGIG = 'zuegig', 'zügig'
    SPORTLICH = 'sportlich', 'sportlich'


class Selbsteinschaetzung(models.TextChoices):
    # Stufen: Festlegung (nicht von Fabian entschieden).
    EINSTEIGER = 'einsteiger', 'Einsteiger'
    GEUEBT = 'geuebt', 'geübt'
    ERFAHREN = 'erfahren', 'erfahren'
    SEHR_ERFAHREN = 'sehr_erfahren', 'sehr erfahren'


class Tourenformat(models.TextChoices):
    HALBTAG = 'halbtag', 'Halbtag'
    TAG = 'tag', 'Tag'
    MEHRTAGE = 'mehrtage', 'Mehrtage'


class UnterwegsStil(models.TextChoices):
    STRECKENFRESSER = 'streckenfresser', 'Streckenfresser'
    GENIESSER = 'geniesser', 'Genießer'
    BEIDES = 'beides', 'mal so, mal so'


class Uebernachtung(models.TextChoices):
    ZELT = 'zelt', 'Zelt'
    PENSION = 'pension', 'Pension'
    HOTEL = 'hotel', 'Hotel'


class Gruppengroesse(models.TextChoices):
    # Grenzen: Festlegung (nicht von Fabian entschieden).
    KLEIN = 'klein', 'klein (2–3)'
    MITTEL = 'mittel', 'mittel (4–6)'
    GROSS = 'gross', 'groß (7+)'


class Thema(models.TextChoices):
    TAGESTOUREN = 'tagestouren', 'Tagestouren'
    MESSEN = 'messen', 'Messen'
    TRAININGS = 'trainings', 'Trainings'
    SCHRAUBEN = 'schrauben', 'Schrauben/Technik'
    FERNREISEN = 'fernreisen', 'Fernreisen'
    FEIERABENDRUNDEN = 'feierabendrunden', 'Feierabendrunden'


class Schutzkleidung(models.TextChoices):
    # Auspraegungen: Festlegung (nicht von Fabian entschieden).
    VOLL = 'voll', 'volle Schutzkleidung'
    TEILWEISE = 'teilweise', 'teilweise'
    EGAL = 'egal', 'egal'


class AlkoholAufTour(models.TextChoices):
    # Auspraegungen: Festlegung (nicht von Fabian entschieden).
    NIE = 'nie', 'nie'
    NACH_DER_FAHRT = 'nach_der_fahrt', 'erst nach der Fahrt'
    EGAL = 'egal', 'egal'


class Tageszeit(models.TextChoices):
    VORMITTAGS = 'vormittags', 'vormittags'
    MITTAGS = 'mittags', 'mittags'
    NACHMITTAGS = 'nachmittags', 'nachmittags'


class VerfuegbarkeitsStufe(models.TextChoices):
    SICHER = 'sicher', 'sicher'
    VORBEHALT = 'vorbehalt', 'mit Vorbehalt'
    NEIN = 'nein', 'nein'


def _mehrfachwahl_pruefen(choices):
    """Validator fuer JSON-Listen aus einer festen Auswahl (Mehrfachwahl).

    JSONField statt ManyToMany mit Katalogtabelle: Die Auswahllisten sind fest im
    Code (sie gehoeren zum Matching, das in Schritt 8 im Code gewichtet), und eine
    Katalogtabelle braeuchte Stammdaten in jeder frischen DB.
    """
    erlaubt = {wert for wert, _ in choices}

    def pruefen(wert):
        if not isinstance(wert, list):
            raise ValidationError('Erwartet wird eine Liste.')
        fremd = [w for w in wert if w not in erlaubt]
        if fremd:
            raise ValidationError(f'Unbekannte Werte: {fremd}')
        if len(set(wert)) != len(wert):
            raise ValidationError('Werte doppelt.')

    # Djangos Migrationssystem muss Validatoren serialisieren koennen; ein
    # Closure geht nicht. Deshalb unten die benannten Validatoren.
    return pruefen


def fahrarten_pruefen(wert):
    _mehrfachwahl_pruefen(Fahrart.choices)(wert)


def tourenformate_pruefen(wert):
    _mehrfachwahl_pruefen(Tourenformat.choices)(wert)


def uebernachtung_pruefen(wert):
    _mehrfachwahl_pruefen(Uebernachtung.choices)(wert)


def themen_pruefen(wert):
    _mehrfachwahl_pruefen(Thema.choices)(wert)


# ---------------------------------------------------------------------------
# Nutzer und Profil
# ---------------------------------------------------------------------------

class Nutzer(AbstractUser):
    """Eigenes Nutzermodell von Anfang an (Fabian, 23.09.2026).

    Nutzername statt Klarname (Notiz, "Der Kern (V1)"). Deshalb sind die
    Klarnamenfelder von AbstractUser entfernt - ein Feld, das es nicht gibt,
    kann auch nicht versehentlich sichtbar werden. Festlegung (nicht von Fabian
    entschieden): first_name/last_name = None.

    Warum AbstractUser und nicht AbstractBaseUser: Django-Admin, allauth und
    createsuperuser funktionieren damit ohne eigene Manager/Formulare; spaeter
    umzusteigen waere eine Datenmigration, frueher war es nur eine Zeile.
    """
    first_name = None
    last_name = None
    email = models.EmailField('E-Mail-Adresse', unique=True)

    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = 'Nutzer'
        verbose_name_plural = 'Nutzer'

    def __str__(self):
        return self.username

    def get_full_name(self):
        return self.username

    def get_short_name(self):
        return self.username


# Welche Profilfelder die Sichtbarkeitsschicht kennt, und ihre Voreinstellung.
# Fabian, 23.09.2026: "Sichtbarkeit je Profilfeld waehlt der Nutzer
# (oeffentlich/verbunden/Ridebuddies), mit fester Voreinstellung je Feld im Code."
#
# Die Werte selbst sind eine Festlegung (nicht von Fabian entschieden). Leitlinie:
# oeffentlich ist, was ein Vorschlag zur Meinungsbildung braucht (Fahrart, Tempo,
# Region ...); verbunden ist, was Rueckschluesse auf die Person oder ihre Haltung
# erlaubt (Geschlecht, Praeferenzen, No-Gos, Sicherheitshaltung). Nichts steht
# voreingestellt auf Ridebuddies - das waehlt der Nutzer selbst.
#
# Der Nutzername ist kein waehlbares Feld: Er ist die Identitaet, die ab Stufe
# oeffentlich immer mitgeht (ohne ihn waere ein Vorschlag nicht adressierbar).
# Die hart/weich-Gewichtung und die Feldstufen selbst sind nie fuer andere sichtbar.
FELD_VOREINSTELLUNG = {
    'altersbereich': Stufe.OEFFENTLICH,
    'region': Stufe.OEFFENTLICH,
    'radius_km': Stufe.OEFFENTLICH,
    'geschlecht': Stufe.VERBUNDEN,
    'geschlechtspraeferenz': Stufe.VERBUNDEN,
    'alterswunsch_von': Stufe.VERBUNDEN,
    'alterswunsch_bis': Stufe.VERBUNDEN,
    'fahrarten': Stufe.OEFFENTLICH,
    'tempo': Stufe.OEFFENTLICH,
    'erfahrung_jahre': Stufe.OEFFENTLICH,
    'km_pro_jahr': Stufe.OEFFENTLICH,
    'selbsteinschaetzung': Stufe.OEFFENTLICH,
    'tourenformate': Stufe.OEFFENTLICH,
    'tagesdistanz_km': Stufe.OEFFENTLICH,
    'unterwegs_stil': Stufe.OEFFENTLICH,
    'uebernachtung': Stufe.OEFFENTLICH,
    'gruppengroesse': Stufe.OEFFENTLICH,
    'themen': Stufe.OEFFENTLICH,
    'schutzkleidung': Stufe.VERBUNDEN,
    'alkohol_auf_tour': Stufe.VERBUNDEN,
    'motorrad': Stufe.OEFFENTLICH,
    # No-Go steht auf verbunden (Fabian, 23.09.2026: Voreinstellung bleibt so):
    # Wer "oeffentlich" sieht, ist ein Vorschlag, eine Anfrage oder ein
    # Crew-Mitglied - und das Matching (Etappe 2) soll gar niemanden vorschlagen,
    # der ein No-Go reisst. Die No-Gos wirken also schon vor der Sicht, ueber
    # das Matching; lesen muss sie erst, wer verbunden ist.
    'nogo': Stufe.VERBUNDEN,
}


class Profil(models.Model):
    """Das Profil - entsteht automatisch mit dem Nutzer (kern/signale.py)."""
    nutzer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='profil')

    # Person - alles optional, weil das Profil leer entsteht (Onboarding: Schritt 11).
    altersbereich = models.CharField(max_length=8, choices=Altersbereich.choices, blank=True)
    geschlecht = models.CharField(max_length=16, choices=Geschlecht.choices,
                                  default=Geschlecht.KEINE_ANGABE)
    region = models.CharField('Region', max_length=100, blank=True,
                              help_text='Ort oder PLZ-Bereich, keine Anschrift.')
    radius_km = models.PositiveSmallIntegerField('Radius (km)', default=50)

    # Wuensche an andere (voreingestellt harte Merkmale).
    geschlechtspraeferenz = models.CharField(max_length=10, choices=Geschlechtspraeferenz.choices,
                                             default=Geschlechtspraeferenz.EGAL)
    alterswunsch_von = models.CharField('Altersbereich-Wunsch von', max_length=8,
                                        choices=Altersbereich.choices, blank=True)
    alterswunsch_bis = models.CharField('Altersbereich-Wunsch bis', max_length=8,
                                        choices=Altersbereich.choices, blank=True)

    # Merkmale (voreingestellt weich) - Notiz "Matching-Merkmale".
    fahrarten = models.JSONField(default=list, blank=True, validators=[fahrarten_pruefen],
                                 help_text='Mehrfachwahl')
    tempo = models.CharField(max_length=12, choices=Tempo.choices, blank=True)
    erfahrung_jahre = models.PositiveSmallIntegerField('Erfahrung (Jahre)', null=True, blank=True)
    km_pro_jahr = models.PositiveIntegerField('km pro Jahr', null=True, blank=True)
    selbsteinschaetzung = models.CharField(max_length=16, choices=Selbsteinschaetzung.choices,
                                           blank=True)
    tourenformate = models.JSONField(default=list, blank=True, validators=[tourenformate_pruefen],
                                     help_text='Mehrfachwahl')
    tagesdistanz_km = models.PositiveSmallIntegerField('Tagesdistanz (km)', null=True, blank=True)
    unterwegs_stil = models.CharField(max_length=16, choices=UnterwegsStil.choices, blank=True)
    uebernachtung = models.JSONField(default=list, blank=True, validators=[uebernachtung_pruefen],
                                     help_text='Mehrfachwahl')
    gruppengroesse = models.CharField(max_length=8, choices=Gruppengroesse.choices, blank=True)
    themen = models.JSONField(default=list, blank=True, validators=[themen_pruefen],
                              help_text='Mehrfachwahl')
    schutzkleidung = models.CharField(max_length=10, choices=Schutzkleidung.choices, blank=True)
    alkohol_auf_tour = models.CharField(max_length=16, choices=AlkoholAufTour.choices, blank=True)
    motorrad = models.CharField('Motorrad (Typ/Modell)', max_length=100, blank=True)
    nogo = models.TextField('Was ich definitiv nicht möchte', blank=True)

    # Nur Abweichungen von der Voreinstellung werden gespeichert; wirksam ist
    # immer Voreinstellung + Abweichung (feldstufe(), gewichtung_von()). So
    # wirkt eine spaeter geaenderte Voreinstellung fuer alle, die nichts
    # umgestellt haben.
    feldstufen = models.JSONField(default=dict, blank=True,
                                  help_text='Abweichungen von FELD_VOREINSTELLUNG: {feld: 1|2|3}')
    gewichtung = models.JSONField(default=dict, blank=True,
                                  help_text='Abweichungen von MERKMAL_VOREINSTELLUNG: '
                                            '{dimension: "hart"|"weich"}')

    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Profil'
        verbose_name_plural = 'Profile'

    def __str__(self):
        return f'Profil {self.nutzer}'

    def clean(self):
        super().clean()
        erlaubte_stufen = {wert for wert, _ in WAEHLBARE_STUFEN}
        for feld, stufe in (self.feldstufen or {}).items():
            if feld not in FELD_VOREINSTELLUNG:
                raise ValidationError({'feldstufen': f'Unbekanntes Feld: {feld}'})
            if stufe not in erlaubte_stufen:
                raise ValidationError({'feldstufen': f'Stufe {stufe!r} für {feld} nicht wählbar'})
        for merkmal, wert in (self.gewichtung or {}).items():
            if merkmal not in MERKMAL_VOREINSTELLUNG:
                raise ValidationError({'gewichtung': f'Unbekanntes Merkmal: {merkmal}'})
            if wert not in Gewichtung.values:
                raise ValidationError({'gewichtung': f'{wert!r} ist weder hart noch weich'})

    def feldstufe(self, feld):
        """Wirksame Stufe eines Profilfelds (Nutzerwahl, sonst Voreinstellung)."""
        if feld not in FELD_VOREINSTELLUNG:
            raise KeyError(feld)
        return int((self.feldstufen or {}).get(feld, FELD_VOREINSTELLUNG[feld]))

    def gewichtung_von(self, merkmal):
        """'hart' oder 'weich' fuer ein Merkmal (Nutzerwahl, sonst Voreinstellung)."""
        if merkmal not in MERKMAL_VOREINSTELLUNG:
            raise KeyError(merkmal)
        return (self.gewichtung or {}).get(merkmal, MERKMAL_VOREINSTELLUNG[merkmal].value)


class Beitrag(models.Model):
    """Beitrag - lesbar nach Stufe und (mit Einwilligung) Rohmaterial fuers Matching.

    Voreinstellung VERBUNDEN: Festlegung (nicht von Fabian entschieden) - ein
    Beitrag ist persoenlicher als ein Profilfeld; wer ihn Vorgeschlagenen zeigen
    will, stellt ihn auf oeffentlich.
    """
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='beitraege')
    text = models.TextField()
    stufe = models.PositiveSmallIntegerField(choices=WAEHLBARE_STUFEN, default=Stufe.VERBUNDEN)
    erstellt = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Beitrag'
        verbose_name_plural = 'Beiträge'
        ordering = ['-erstellt']
        constraints = [
            models.CheckConstraint(condition=Q(stufe__gte=1, stufe__lte=3),
                                   name='beitrag_stufe_waehlbar'),
        ]

    def __str__(self):
        return f'Beitrag von {self.autor} ({self.get_stufe_display()})'


# ---------------------------------------------------------------------------
# Beziehungen: Verbindung, Vorschlag, Anfrage, Ausschluss
# ---------------------------------------------------------------------------

class Ausgang(models.TextChoices):
    """Die zwei Ausgaenge beim Ablehnen eines Vorschlags und beim Beenden
    einer Verbindung (Notiz: "Verbindungen kann jeder still beenden, mit
    denselben zwei Ausgaengen")."""
    NICHT_JETZT = 'nicht_jetzt', 'nicht jetzt'
    PASST_NICHT = 'passt_nicht', 'passt nicht'


class Verbindung(models.Model):
    """Verbindung zwischen zwei Nutzern (Stufe verbunden oder Ridebuddies).

    Das Paar steht geordnet (nutzer_a.pk < nutzer_b.pk), damit es je Paar genau
    eine aktive Verbindung geben kann (Constraint unten) - "zwischen zwei
    Nutzern gibt es genau einen Zustand".

    Fabian, 23.09.2026 - einseitiges, stilles Senken: Die Verbindung traegt JE
    RICHTUNG eine gewaehrte Stufe. `gewaehrt_a` ist die Stufe, die A dem B
    gewaehrt; sie bestimmt, was B von A sieht. `erreicht` ist die gemeinsam
    erreichte Stufe und die Obergrenze fuer beide gewaehrten Stufen.

    Festlegung der Hauptsitzung: still gesenkt wird nur von Ridebuddies auf
    verbunden; darunter heisst es "beenden" (beendet_am gesetzt). Eine beendete
    Verbindung bleibt als Geschichte stehen und zaehlt fuer die Sicht nicht mehr.
    Festlegung (nicht von Fabian entschieden): Beenden mit "nicht jetzt" setzt
    `wiedervorlage_ab` (+6 Monate) auf der Verbindung selbst - das Matching
    (Schritt 8) liest diese Sperre dort.

    Fabian, 23.09.2026 (Nacharbeit): Stufe Ridebuddies entsteht NUR ueber eine
    bestaetigte RidebuddyAnfrage zwischen aktiv Verbundenen - nicht mehr
    automatisch aus dem Feedback und ohne gemeinsame Plattform-Ausfahrt als
    Voraussetzung. Eine Verbindung entsteht deshalb immer auf Stufe verbunden;
    es gibt keinen Entstehungsweg "Ridebuddy".
    """

    class Entstehung(models.TextChoices):
        VORSCHLAG = 'vorschlag', 'beidseitig angenommener Vorschlag'
        ANFRAGE = 'anfrage', 'angenommene Anfrage'

    nutzer_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='+')
    nutzer_b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='+')
    erreicht = models.PositiveSmallIntegerField(
        choices=[(Stufe.VERBUNDEN.value, Stufe.VERBUNDEN.label),
                 (Stufe.RIDEBUDDIES.value, Stufe.RIDEBUDDIES.label)],
        default=Stufe.VERBUNDEN)
    gewaehrt_a = models.PositiveSmallIntegerField(
        'von A gewährt', choices=[(Stufe.VERBUNDEN.value, Stufe.VERBUNDEN.label),
                                  (Stufe.RIDEBUDDIES.value, Stufe.RIDEBUDDIES.label)],
        default=Stufe.VERBUNDEN, help_text='bestimmt, was B von A sieht')
    gewaehrt_b = models.PositiveSmallIntegerField(
        'von B gewährt', choices=[(Stufe.VERBUNDEN.value, Stufe.VERBUNDEN.label),
                                  (Stufe.RIDEBUDDIES.value, Stufe.RIDEBUDDIES.label)],
        default=Stufe.VERBUNDEN, help_text='bestimmt, was A von B sieht')
    entstanden_durch = models.CharField(max_length=12, choices=Entstehung.choices)
    erstellt = models.DateTimeField(default=timezone.now)
    ridebuddies_seit = models.DateTimeField(null=True, blank=True)
    beendet_am = models.DateTimeField(null=True, blank=True)
    beendet_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='+')
    beendet_ausgang = models.CharField(max_length=12, choices=Ausgang.choices, blank=True)
    wiedervorlage_ab = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Verbindung'
        verbose_name_plural = 'Verbindungen'
        constraints = [
            models.CheckConstraint(condition=Q(nutzer_a__lt=F('nutzer_b')),
                                   name='verbindung_paar_geordnet'),
            models.CheckConstraint(condition=Q(erreicht__gte=2, erreicht__lte=3),
                                   name='verbindung_erreicht_2_oder_3'),
            models.CheckConstraint(condition=Q(gewaehrt_a__gte=2, gewaehrt_a__lte=F('erreicht')),
                                   name='verbindung_gewaehrt_a_bis_erreicht'),
            models.CheckConstraint(condition=Q(gewaehrt_b__gte=2, gewaehrt_b__lte=F('erreicht')),
                                   name='verbindung_gewaehrt_b_bis_erreicht'),
            models.UniqueConstraint(fields=['nutzer_a', 'nutzer_b'],
                                    condition=Q(beendet_am__isnull=True),
                                    name='verbindung_ein_aktives_paar'),
        ]

    def __str__(self):
        zustand = 'beendet' if self.beendet_am else self.get_erreicht_display()
        return f'{self.nutzer_a} – {self.nutzer_b} ({zustand})'

    @property
    def aktiv(self):
        return self.beendet_am is None

    def ist_beteiligt(self, nutzer):
        return nutzer.pk in (self.nutzer_a_id, self.nutzer_b_id)

    def anderer(self, nutzer):
        return self.nutzer_b if nutzer.pk == self.nutzer_a_id else self.nutzer_a

    def gewaehrt_von(self, nutzer):
        """Die Stufe, die `nutzer` dem jeweils anderen gewaehrt."""
        if nutzer.pk == self.nutzer_a_id:
            return self.gewaehrt_a
        if nutzer.pk == self.nutzer_b_id:
            return self.gewaehrt_b
        raise ValueError(f'{nutzer} ist an {self} nicht beteiligt')


class Vorschlag(models.Model):
    """Ein Matching-Vorschlag: `empfaenger` bekommt `kandidat` vorgelegt.

    Festlegung der Hauptsitzung: Die Vorschlagssicht ist einseitig. Nur der
    Empfaenger sieht den Kandidaten (Stufe oeffentlich), solange der Vorschlag
    offen oder angenommen ist. Der Kandidat sieht den Empfaenger nur, wenn er
    selbst einen Vorschlag fuer ihn hat. Nehmen beide ihren Vorschlag an,
    entsteht eine Verbindung (ablaeufe.vorschlag_reagieren).

    Reaktionen laut Notiz: annehmen / "nicht jetzt" (Wiedervorlage +6 Monate) /
    "passt nicht" (Ausschluss, optional mit angetippter Dimension).
    Die Ausnahme "ausser bei wesentlicher Profilaenderung" wertet das Matching
    aus (Schritt 8), nicht dieses Modell.
    """

    class Reaktion(models.TextChoices):
        OFFEN = 'offen', 'offen'
        ANGENOMMEN = 'angenommen', 'angenommen'
        NICHT_JETZT = 'nicht_jetzt', 'nicht jetzt'
        PASST_NICHT = 'passt_nicht', 'passt nicht'

    empfaenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='vorschlaege')
    kandidat = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='+')
    runde = models.PositiveIntegerField(help_text='Matching-Runde; mehrere Kandidaten je Runde')
    begruendung = models.JSONField(default=dict, blank=True,
                                   help_text='{dimension: Begründungstext}')
    reaktion = models.CharField(max_length=12, choices=Reaktion.choices, default=Reaktion.OFFEN)
    reagiert_am = models.DateTimeField(null=True, blank=True)
    wiedervorlage_ab = models.DateField(null=True, blank=True)
    erstellt = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Vorschlag'
        verbose_name_plural = 'Vorschläge'
        constraints = [
            models.UniqueConstraint(fields=['empfaenger', 'kandidat', 'runde'],
                                    name='vorschlag_einmal_je_runde'),
            models.CheckConstraint(condition=~Q(empfaenger=F('kandidat')),
                                   name='vorschlag_nicht_an_sich_selbst'),
        ]

    def __str__(self):
        return f'Runde {self.runde}: {self.kandidat} für {self.empfaenger} ({self.reaktion})'

    def clean(self):
        super().clean()
        # Wer im Admin eine Reaktion setzt, muss den Zeitpunkt mitsetzen: Die
        # Sicht (sichtbarkeit.vorschlag_gibt_sicht) rechnet damit. Nachpruefung
        # 23.09.2026: ein im Admin auf "angenommen" gesetzter Vorschlag ohne
        # reagiert_am liess stufe_fuer mit ValueError abbrechen.
        if self.reaktion != self.Reaktion.OFFEN and self.reagiert_am is None:
            raise ValidationError({'reagiert_am': 'Pflicht, sobald eine Reaktion gesetzt ist.'})
        unbekannt = [d for d in (self.begruendung or {}) if d not in Dimension.values]
        if unbekannt:
            raise ValidationError({'begruendung': f'Unbekannte Dimensionen: {unbekannt}'})


# Wochenkontingent fuer direkte Anfragen (Notiz: "etwa drei"). Nur als Konstante;
# durchgesetzt wird es erst in Schritt 12 (Festlegung der Hauptsitzung).
ANFRAGEN_JE_WOCHE = 3


class Anfrage(models.Model):
    """Direkte, sichtbare Anfrage - Empfaenger nimmt an oder lehnt ab.

    Festlegung der Hauptsitzung: Der Empfaenger sieht den Absender auf Stufe
    oeffentlich, solange die Anfrage offen ist; angenommen -> Verbindung;
    abgelehnt -> KEIN Ausschluss (in der Notiz nicht entschieden, darum nicht
    erfunden). Der Absender sieht den Empfaenger durch die Anfrage nicht.
    """

    class Status(models.TextChoices):
        OFFEN = 'offen', 'offen'
        ANGENOMMEN = 'angenommen', 'angenommen'
        ABGELEHNT = 'abgelehnt', 'abgelehnt'

    absender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='anfragen_gesendet')
    empfaenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='anfragen_erhalten')
    text = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OFFEN)
    erstellt = models.DateTimeField(default=timezone.now)
    beantwortet_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Anfrage'
        verbose_name_plural = 'Anfragen'
        constraints = [
            models.CheckConstraint(condition=~Q(absender=F('empfaenger')),
                                   name='anfrage_nicht_an_sich_selbst'),
            models.UniqueConstraint(fields=['absender', 'empfaenger'],
                                    condition=Q(status='offen'),
                                    name='anfrage_eine_offene_je_paar'),
        ]

    def __str__(self):
        return f'Anfrage {self.absender} → {self.empfaenger} ({self.status})'


class RidebuddyAnfrage(models.Model):
    """Sichtbare Bitte, Ridebuddies zu werden - B bestaetigt oder lehnt ab.

    Fabian, 23.09.2026 (Nacharbeit TASK-120.04): Stufe 3 gibt es nur ueber diese
    Anfrage, nur zwischen aktiv Verbundenen (Crew-Fremde verbinden sich zuerst
    ueber die normale Anfrage) und OHNE gemeinsame Plattform-Ausfahrt als
    Voraussetzung - wer schon vorher zusammen gefahren ist, soll sich manuell
    als Buddy hinzufuegen koennen. Bestaetigung -> erreicht=3, beide gewaehrt=3.
    Ablehnen -> nichts weiter, kein Ausschluss.

    Eigenes Modell statt eines Art-Felds an Anfrage: Eine offene normale
    Anfrage gibt dem Empfaenger Sicht auf Stufe oeffentlich (stufe_fuer); eine
    Ridebuddy-Anfrage darf das nie tun, weil sie nur zwischen Verbundenen
    existiert. Mit einem Art-Feld muesste jede Abfrage an Anfrage daran denken,
    danach zu filtern - vergisst es eine, ist das ein Sichtbarkeitsfehler.

    Die Anfrage haengt an der aktiven Verbindung. Damit sichert die Datenbank
    "je Paar hoechstens eine offene" fuer das ungeordnete Paar selbst ab (eine
    offene je Verbindung, gleich in welche Richtung), und eine Anfrage aus einer
    beendeten Verbindung laesst sich nicht mehr bestaetigen.
    """

    class Status(models.TextChoices):
        OFFEN = 'offen', 'offen'
        BESTAETIGT = 'bestaetigt', 'bestätigt'
        ABGELEHNT = 'abgelehnt', 'abgelehnt'
        # Verbindung endete (beendet oder Ausschluss), bevor geantwortet wurde.
        HINFAELLIG = 'hinfaellig', 'hinfällig (Verbindung beendet)'

    verbindung = models.ForeignKey('Verbindung', on_delete=models.CASCADE,
                                   related_name='ridebuddy_anfragen')
    absender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='ridebuddy_anfragen_gesendet')
    empfaenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='ridebuddy_anfragen_erhalten')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OFFEN)
    erstellt = models.DateTimeField(default=timezone.now)
    beantwortet_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Ridebuddy-Anfrage'
        verbose_name_plural = 'Ridebuddy-Anfragen'
        constraints = [
            models.CheckConstraint(condition=~Q(absender=F('empfaenger')),
                                   name='ridebuddy_anfrage_nicht_an_sich_selbst'),
            models.UniqueConstraint(fields=['verbindung'], condition=Q(status='offen'),
                                    name='ridebuddy_anfrage_eine_offene_je_verbindung'),
        ]

    def __str__(self):
        return f'Ridebuddy-Anfrage {self.absender} → {self.empfaenger} ({self.status})'


class Ausschluss(models.Model):
    """Ausgeschlossen - dauerhaft, beidseitig wirksam.

    Fabian, 23.09.2026: nichts sichtbar, in beide Richtungen, auch nicht ueber
    Crew oder Vorschlag; der Grund ist nur fuer den Urheber lesbar; dauerhaft
    aus dem Matching. Ein Datensatz genuegt fuer beide Richtungen - die Sicht
    fragt in beide Richtungen ab (sichtbarkeit.ausgeschlossen).

    Es gibt bewusst keinen Ablauf, der einen Ausschluss aufhebt ("dauerhaft").
    Loeschen kann ihn nur der Admin.
    """

    class Quelle(models.TextChoices):
        VORSCHLAG = 'vorschlag', 'Vorschlag: „passt nicht"'
        VERBINDUNG = 'verbindung', 'Verbindung beendet: „passt nicht"'
        FEEDBACK = 'feedback', 'Feedback: „war nix"'

    urheber = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='ausschluesse')
    betroffener = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='+')
    quelle = models.CharField(max_length=12, choices=Quelle.choices)
    grund_dimension = models.CharField(max_length=24, choices=Dimension.choices, blank=True,
                                       help_text='angetippte Dimension - nur der Urheber sieht sie')
    grund_text = models.TextField(blank=True, help_text='nur der Urheber sieht ihn')
    erstellt = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Ausschluss'
        verbose_name_plural = 'Ausschlüsse'
        constraints = [
            models.UniqueConstraint(fields=['urheber', 'betroffener'],
                                    name='ausschluss_einmal_je_richtung'),
            models.CheckConstraint(condition=~Q(urheber=F('betroffener')),
                                   name='ausschluss_nicht_sich_selbst'),
        ]

    def __str__(self):
        return f'Ausschluss {self.urheber} ⟂ {self.betroffener}'


# ---------------------------------------------------------------------------
# Crews
# ---------------------------------------------------------------------------

class Crew(models.Model):
    name = models.CharField(max_length=100)
    beschreibung = models.TextField(blank=True)
    erstellt = models.DateTimeField(default=timezone.now)
    mitglieder = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Mitgliedschaft',
                                        related_name='crews')

    class Meta:
        verbose_name = 'Crew'
        verbose_name_plural = 'Crews'

    def __str__(self):
        return self.name


class Mitgliedschaft(models.Model):
    """Rolle in einer Crew. Notiz: mindestens ein Organisator, Mitglieder mit
    Routenvorschlaegen, Gaeste fahren mit, bis die Crew ueber die Aufnahme
    entscheidet. "Mindestens ein Organisator" setzt die Oberflaeche durch
    (Schritt 13), nicht die Datenbank - beim Anlegen gibt es kurz keinen."""

    class Rolle(models.TextChoices):
        ORGANISATOR = 'organisator', 'Organisator'
        MITGLIED = 'mitglied', 'Mitglied'
        GAST = 'gast', 'Gast'

    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, related_name='mitgliedschaften')
    nutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='mitgliedschaften')
    rolle = models.CharField(max_length=12, choices=Rolle.choices, default=Rolle.MITGLIED)
    seit = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Mitgliedschaft'
        verbose_name_plural = 'Mitgliedschaften'
        constraints = [
            models.UniqueConstraint(fields=['crew', 'nutzer'], name='mitgliedschaft_einmal'),
        ]

    def __str__(self):
        return f'{self.nutzer} in {self.crew} ({self.get_rolle_display()})'


class CrewVorschlag(models.Model):
    """"Bei >= 3 Ridebuddies, die untereinander verbunden sind, schlaegt das
    System eine Crew vor; wer annimmt, wird Organisator und laedt ein."
    Erzeugt wird er ab Schritt 13; hier steht nur die Struktur."""

    class Status(models.TextChoices):
        OFFEN = 'offen', 'offen'
        ANGENOMMEN = 'angenommen', 'angenommen'
        VERWORFEN = 'verworfen', 'verworfen'

    beteiligte = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='crew_vorschlaege')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OFFEN)
    angenommen_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='+')
    crew = models.ForeignKey(Crew, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='+', help_text='die daraus entstandene Crew')
    erstellt = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Crew-Vorschlag'
        verbose_name_plural = 'Crew-Vorschläge'

    def __str__(self):
        return f'Crew-Vorschlag {self.pk} ({self.status})'


# ---------------------------------------------------------------------------
# Ausfahrten, Termine, Teilnahme, Verfuegbarkeit
# ---------------------------------------------------------------------------

class Ausfahrt(models.Model):
    """Ausfahrt oder Reise: Vorschlag -> Abstimmung ueber Termin und Route -> Zusage.

    `crew` darf leer sein. Festlegung (nicht von Fabian entschieden): Die Notiz
    laesst Ausfahrten "in der Crew" entstehen, aber zwei Verbundene sollen auch
    ohne Crew fahren und danach Feedback geben koennen - sonst waere der Weg zu
    Ridebuddies an eine Crew gebunden.

    "Tatsaechlich gefahren" (Voraussetzung fuer Feedback und Stufe Ridebuddies)
    heisst: status GEFAHREN und Teilnahme.gefahren fuer beide.
    """

    class Art(models.TextChoices):
        TAGESTOUR = 'tagestour', 'Tagestour'
        REISE = 'reise', 'Reise (mehrtägig)'
        MESSE = 'messe', 'Messe'
        TRAINING = 'training', 'Training'

    class Status(models.TextChoices):
        VORGESCHLAGEN = 'vorgeschlagen', 'vorgeschlagen'
        ABSTIMMUNG = 'abstimmung', 'Abstimmung läuft'
        FEST = 'fest', 'Termin steht'
        GEFAHREN = 'gefahren', 'gefahren'
        ABGESAGT = 'abgesagt', 'abgesagt'

    titel = models.CharField(max_length=150)
    art = models.CharField(max_length=12, choices=Art.choices, default=Art.TAGESTOUR)
    beschreibung = models.TextField(blank=True)
    routenlink = models.URLField(blank=True, help_text='Link auf Stegra/calimoto - keine eigene '
                                                       'Routenberechnung')
    crew = models.ForeignKey(Crew, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='ausfahrten')
    vorgeschlagen_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='+')
    status = models.CharField(max_length=14, choices=Status.choices,
                              default=Status.VORGESCHLAGEN)
    erstellt = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Ausfahrt/Reise'
        verbose_name_plural = 'Ausfahrten und Reisen'

    def __str__(self):
        return self.titel


class Termin(models.Model):
    """Kandidaten-Termin einer Ausfahrt. Fuer Tagestouren Tag + Tageszeit,
    fuer Reisen ein Zeitraum (datum bis bis_datum, Tageszeit leer).
    `gewaehlt` markiert den festgelegten Termin."""
    ausfahrt = models.ForeignKey(Ausfahrt, on_delete=models.CASCADE, related_name='termine')
    datum = models.DateField()
    bis_datum = models.DateField(null=True, blank=True)
    tageszeit = models.CharField(max_length=12, choices=Tageszeit.choices, blank=True)
    gewaehlt = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Termin'
        verbose_name_plural = 'Termine'
        ordering = ['datum', 'tageszeit']
        constraints = [
            models.CheckConstraint(condition=Q(bis_datum__isnull=True) |
                                   Q(bis_datum__gte=F('datum')),
                                   name='termin_bis_nach_von'),
        ]

    def __str__(self):
        if self.bis_datum:
            return f'{self.datum}–{self.bis_datum}'
        return f'{self.datum} {self.tageszeit}'.strip()


class Teilnahme(models.Model):
    """Zusage zu einer Ausfahrt und, danach, ob tatsaechlich gefahren wurde."""

    class Zusage(models.TextChoices):
        OFFEN = 'offen', 'offen'
        ZUGESAGT = 'zugesagt', 'zugesagt'
        ABGESAGT = 'abgesagt', 'abgesagt'

    ausfahrt = models.ForeignKey(Ausfahrt, on_delete=models.CASCADE, related_name='teilnahmen')
    nutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='teilnahmen')
    zusage = models.CharField(max_length=10, choices=Zusage.choices, default=Zusage.OFFEN)
    gefahren = models.BooleanField(default=False,
                                   help_text='tatsächlich mitgefahren (nach der Ausfahrt)')

    class Meta:
        verbose_name = 'Teilnahme'
        verbose_name_plural = 'Teilnahmen'
        constraints = [
            models.UniqueConstraint(fields=['ausfahrt', 'nutzer'], name='teilnahme_einmal'),
        ]

    def __str__(self):
        return f'{self.nutzer} bei {self.ausfahrt} ({self.zusage})'


class Verfuegbarkeit(models.Model):
    """Tag x Tageszeit x Stufe (sicher / mit Vorbehalt / nein).

    `ausfahrt` leer = allgemeine Verfuegbarkeit fuers Matching; gesetzt =
    Antwort auf die Terminabstimmung dieser Ausfahrt (Festlegung der
    Hauptsitzung). Die Prozentrechnung je Termin ist Schritt 6 (TASK-120.06).
    """
    nutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='verfuegbarkeiten')
    ausfahrt = models.ForeignKey(Ausfahrt, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name='verfuegbarkeiten')
    datum = models.DateField()
    tageszeit = models.CharField(max_length=12, choices=Tageszeit.choices)
    stufe = models.CharField(max_length=10, choices=VerfuegbarkeitsStufe.choices)

    class Meta:
        verbose_name = 'Verfügbarkeit'
        verbose_name_plural = 'Verfügbarkeiten'
        ordering = ['datum', 'tageszeit']
        # SQLite behandelt NULL in Unique-Indizes als verschieden - deshalb
        # zwei bedingte Constraints statt eines ueber (nutzer, ausfahrt, ...).
        constraints = [
            models.UniqueConstraint(fields=['nutzer', 'ausfahrt', 'datum', 'tageszeit'],
                                    condition=Q(ausfahrt__isnull=False),
                                    name='verfuegbarkeit_einmal_je_ausfahrt'),
            models.UniqueConstraint(fields=['nutzer', 'datum', 'tageszeit'],
                                    condition=Q(ausfahrt__isnull=True),
                                    name='verfuegbarkeit_einmal_allgemein'),
        ]

    def __str__(self):
        return f'{self.nutzer} {self.datum} {self.tageszeit}: {self.stufe}'


class Verfuegbarkeitszeitraum(models.Model):
    """Fuer Reisen: Zeitraum von-bis mit Stufe (Notiz: "fuer Reisen Zeitraeume")."""
    nutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='verfuegbarkeitszeitraeume')
    ausfahrt = models.ForeignKey(Ausfahrt, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name='verfuegbarkeitszeitraeume')
    von = models.DateField()
    bis = models.DateField()
    stufe = models.CharField(max_length=10, choices=VerfuegbarkeitsStufe.choices)

    class Meta:
        verbose_name = 'Verfügbarkeit (Zeitraum)'
        verbose_name_plural = 'Verfügbarkeiten (Zeiträume)'
        ordering = ['von']
        constraints = [
            models.CheckConstraint(condition=Q(bis__gte=F('von')),
                                   name='zeitraum_bis_nach_von'),
        ]

    def __str__(self):
        return f'{self.nutzer} {self.von}–{self.bis}: {self.stufe}'


# ---------------------------------------------------------------------------
# Nachricht, Fremdprofil, Feedback, Einwilligung
# ---------------------------------------------------------------------------

class Nachricht(models.Model):
    """Chat: entweder Direktnachricht (`empfaenger`) oder Crew-Nachricht (`crew`),
    nie beides. Wer sie lesen darf, regelt sichtbarkeit.nachrichten_sichtbar;
    wer sie schreiben darf, ablaeufe.nachricht_senden."""
    absender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='nachrichten_gesendet')
    empfaenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   null=True, blank=True, related_name='nachrichten_erhalten')
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, null=True, blank=True,
                             related_name='nachrichten')
    text = models.TextField()
    gesendet = models.DateTimeField(default=timezone.now)
    gelesen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Nachricht'
        verbose_name_plural = 'Nachrichten'
        ordering = ['gesendet']
        constraints = [
            models.CheckConstraint(
                condition=(Q(empfaenger__isnull=False, crew__isnull=True) |
                           Q(empfaenger__isnull=True, crew__isnull=False)),
                name='nachricht_direkt_oder_crew'),
        ]

    def __str__(self):
        ziel = self.empfaenger or self.crew
        return f'{self.absender} → {ziel}'


class Fremdprofil(models.Model):
    """Profil bei einem anderen Dienst (Stegra, Instagram, WhatsApp-Nummer, Mail ...).
    Niemand sieht es - ausser, wem es ausdruecklich geteilt wurde (Teilung)."""

    class Dienst(models.TextChoices):
        STEGRA = 'stegra', 'Stegra'
        CALIMOTO = 'calimoto', 'calimoto'
        INSTAGRAM = 'instagram', 'Instagram'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        SIGNAL = 'signal', 'Signal'
        TELEFON = 'telefon', 'Telefon'
        MAIL = 'mail', 'E-Mail'
        SONSTIGES = 'sonstiges', 'Sonstiges'

    inhaber = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='fremdprofile')
    dienst = models.CharField(max_length=12, choices=Dienst.choices)
    wert = models.CharField(max_length=200, help_text='Nutzername, Nummer, Adresse oder Link')
    erstellt = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Fremdprofil'
        verbose_name_plural = 'Fremdprofile'

    def __str__(self):
        # Bewusst ohne `wert` - __str__ landet in Logs und Admin-Listen.
        return f'{self.get_dienst_display()} von {self.inhaber}'


class Teilung(models.Model):
    """Teilen = eigener Datensatz je Empfaenger (Fabian, 23.09.2026):
    immer eine bewusste Handlung pro Empfaenger, keine Freigabe je Stufe."""
    fremdprofil = models.ForeignKey(Fremdprofil, on_delete=models.CASCADE,
                                    related_name='teilungen')
    empfaenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='erhaltene_teilungen')
    geteilt_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Teilung'
        verbose_name_plural = 'Teilungen'
        constraints = [
            models.UniqueConstraint(fields=['fremdprofil', 'empfaenger'],
                                    name='teilung_einmal_je_empfaenger'),
        ]

    def __str__(self):
        return f'{self.fremdprofil} → {self.empfaenger}'


class Feedback(models.Model):
    """Rueckkopplung nach einer Ausfahrt - je Ausfahrt x (Verfasser, Bewerteter), eindeutig.

    Sorte 1 (`daumen`, fuers System): {dimension: true|false} - nur aggregiert und
    anonym auszuwerten, NIE als sichtbare Bewertung einer Person.
    Sorte 2 (`urteil`, fuer die Beziehung): Ridebuddy / gerne wieder / war nix.
    "Ridebuddy" ist seit Fabians Entscheidung vom 23.09.2026 (Nacharbeit) nur
    noch ein stilles Signal und aendert KEINE Stufe - Ridebuddies wird man ueber
    eine bestaetigte RidebuddyAnfrage. "war nix" schliesst weiterhin aus.

    Fabian, 23.09.2026: Feedback sieht kein anderer Nutzer, auch nicht der
    Bewertete; der Verfasser sieht sein eigenes (sichtbarkeit.feedback_sichtbar).

    ACHTUNG ADMIN: Das Feedback ist im Admin registriert, weil die Karte
    "Admin zeigt alle Modelle" verlangt und in der Dummy-Phase der Blick auf
    Einzelwerte beim Pruefen hilft. Vor dem ersten echten Nutzer muss die
    Admin-Sicht auf eine Aggregation reduziert werden (Schritt 13b) - sonst liest
    der Betreiber Personenbewertungen, die laut Notiz niemand sehen soll.
    """

    class Urteil(models.TextChoices):
        RIDEBUDDY = 'ridebuddy', 'Ridebuddy'
        GERNE_WIEDER = 'gerne_wieder', 'gerne wieder'
        WAR_NIX = 'war_nix', 'war nix'

    ausfahrt = models.ForeignKey(Ausfahrt, on_delete=models.CASCADE, related_name='feedbacks')
    verfasser = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='feedback_verfasst')
    bewerteter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='+')
    daumen = models.JSONField(default=dict, blank=True,
                              help_text='Sorte 1: {dimension: true|false}')
    urteil = models.CharField(max_length=14, choices=Urteil.choices, blank=True,
                              help_text='Sorte 2')
    erstellt = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback'
        constraints = [
            models.UniqueConstraint(fields=['ausfahrt', 'verfasser', 'bewerteter'],
                                    name='feedback_einmal_je_paar_und_ausfahrt'),
            models.CheckConstraint(condition=~Q(verfasser=F('bewerteter')),
                                   name='feedback_nicht_ueber_sich_selbst'),
        ]

    def __str__(self):
        return f'Feedback #{self.pk} zu {self.ausfahrt}'

    def clean(self):
        super().clean()
        for dimension, wert in (self.daumen or {}).items():
            if dimension not in Dimension.values:
                raise ValidationError({'daumen': f'Unbekannte Dimension: {dimension}'})
            if not isinstance(wert, bool):
                raise ValidationError({'daumen': f'{dimension}: Daumen ist true oder false'})


class Einwilligung(models.Model):
    """Einwilligung mit Art, Version und Zeitpunkt. Jede Erteilung ist ein
    eigener Datensatz; ein Widerruf setzt `widerrufen_am` - so bleibt
    nachweisbar, wann welche Fassung galt (Art. 7 Abs. 1 DSGVO: Nachweispflicht).
    Arten: Festlegung (nicht von Fabian entschieden), aus Schritt 11/15 der Notiz."""

    class Art(models.TextChoices):
        VOLLJAEHRIG = 'volljaehrig', '18+ bestätigt'
        NUTZUNGSBEDINGUNGEN = 'nutzungsbedingungen', 'Nutzungsbedingungen'
        DATENSCHUTZ = 'datenschutz', 'Datenschutzerklärung'
        KI_AUSWERTUNG = 'ki_auswertung', 'KI-Auswertung von Profil und Beiträgen fürs Matching'

    nutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='einwilligungen')
    art = models.CharField(max_length=24, choices=Art.choices)
    version = models.CharField(max_length=20, help_text='Fassung des Textes, dem zugestimmt wurde')
    erteilt_am = models.DateTimeField(default=timezone.now)
    widerrufen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Einwilligung'
        verbose_name_plural = 'Einwilligungen'
        ordering = ['-erteilt_am']
        constraints = [
            models.CheckConstraint(condition=Q(widerrufen_am__isnull=True) |
                                   Q(widerrufen_am__gte=F('erteilt_am')),
                                   name='einwilligung_widerruf_nach_erteilung'),
        ]

    def __str__(self):
        zustand = 'widerrufen' if self.widerrufen_am else 'erteilt'
        return f'{self.nutzer}: {self.get_art_display()} v{self.version} ({zustand})'

    @property
    def aktiv(self):
        return self.widerrufen_am is None
