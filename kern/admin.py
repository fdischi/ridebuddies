"""
Django-Admin fuer alle Modelle (Karte TASK-120.04, Abnahmekriterium #1:
"Django-Admin zeigt alle genannten Modelle").

In der Dummy-Phase ist der Admin das Werkzeug, um Zustaende anzulegen und
nachzusehen. Er umgeht dabei kern/ablaeufe.py - wer hier eine Verbindung von
Hand anlegt, prueft keine Regel. Das ist fuer Dummies gewollt.

VOR DEM ERSTEN ECHTEN NUTZER (Schritt 13b/15): Feedback darf der Admin dann nur
noch aggregiert zeigen, und Nachrichten, Fremdprofile und Ausschlussgruende
gehoeren nicht in eine Betreiber-Liste. Siehe den Kommentar am Feedback-Modell.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Anfrage,
    Ausfahrt,
    Ausschluss,
    Beitrag,
    Crew,
    CrewVorschlag,
    Einwilligung,
    Feedback,
    Fremdprofil,
    Mitgliedschaft,
    Nachricht,
    Nutzer,
    Profil,
    RidebuddyAnfrage,
    Teilnahme,
    Teilung,
    Termin,
    Verbindung,
    Verfuegbarkeit,
    Verfuegbarkeitszeitraum,
    Vorschlag,
)


@admin.register(Nutzer)
class NutzerAdmin(UserAdmin):
    # UserAdmin nennt first_name/last_name, die es hier nicht gibt
    # (Nutzername statt Klarname) - deshalb eigene Feldgruppen.
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Kontakt', {'fields': ('email',)}),
        ('Rechte', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups',
                               'user_permissions')}),
        ('Zeitpunkte', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',),
                'fields': ('username', 'email', 'password1', 'password2')}),
    )
    list_display = ('username', 'email', 'is_active', 'is_staff', 'date_joined')
    search_fields = ('username', 'email')


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    # Die Koordinaten (TASK-120.05) erscheinen im Bearbeitungsformular wie jedes
    # andere Feld - der Admin ist Betreiber-Sicht, keine Nutzer-Sicht. In der
    # Liste stehen sie bewusst nicht: Dort reicht der Anzeigetext `region`.
    list_display = ('nutzer', 'altersbereich', 'region', 'radius_km', 'tempo')
    search_fields = ('nutzer__username', 'region')


@admin.register(Beitrag)
class BeitragAdmin(admin.ModelAdmin):
    list_display = ('autor', 'stufe', 'erstellt')
    list_filter = ('stufe',)


@admin.register(Verbindung)
class VerbindungAdmin(admin.ModelAdmin):
    list_display = ('nutzer_a', 'nutzer_b', 'erreicht', 'gewaehrt_a', 'gewaehrt_b',
                    'entstanden_durch', 'beendet_am')
    list_filter = ('erreicht', 'entstanden_durch')


@admin.register(Vorschlag)
class VorschlagAdmin(admin.ModelAdmin):
    list_display = ('empfaenger', 'kandidat', 'runde', 'reaktion', 'wiedervorlage_ab')
    list_filter = ('reaktion', 'runde')


@admin.register(Anfrage)
class AnfrageAdmin(admin.ModelAdmin):
    list_display = ('absender', 'empfaenger', 'status', 'erstellt')
    list_filter = ('status',)


@admin.register(RidebuddyAnfrage)
class RidebuddyAnfrageAdmin(admin.ModelAdmin):
    list_display = ('absender', 'empfaenger', 'status', 'erstellt', 'beantwortet_am')
    list_filter = ('status',)


@admin.register(Ausschluss)
class AusschlussAdmin(admin.ModelAdmin):
    list_display = ('urheber', 'betroffener', 'quelle', 'erstellt')
    list_filter = ('quelle',)


class MitgliedschaftInline(admin.TabularInline):
    model = Mitgliedschaft
    extra = 0


@admin.register(Crew)
class CrewAdmin(admin.ModelAdmin):
    list_display = ('name', 'erstellt')
    inlines = [MitgliedschaftInline]


@admin.register(Mitgliedschaft)
class MitgliedschaftAdmin(admin.ModelAdmin):
    list_display = ('crew', 'nutzer', 'rolle', 'seit')
    list_filter = ('rolle',)


@admin.register(CrewVorschlag)
class CrewVorschlagAdmin(admin.ModelAdmin):
    list_display = ('pk', 'status', 'angenommen_von', 'crew', 'erstellt')


class TerminInline(admin.TabularInline):
    model = Termin
    extra = 0


class TeilnahmeInline(admin.TabularInline):
    model = Teilnahme
    extra = 0


@admin.register(Ausfahrt)
class AusfahrtAdmin(admin.ModelAdmin):
    list_display = ('titel', 'art', 'crew', 'status', 'erstellt')
    list_filter = ('art', 'status')
    inlines = [TerminInline, TeilnahmeInline]


@admin.register(Termin)
class TerminAdmin(admin.ModelAdmin):
    list_display = ('ausfahrt', 'datum', 'bis_datum', 'tageszeit', 'gewaehlt')


@admin.register(Teilnahme)
class TeilnahmeAdmin(admin.ModelAdmin):
    list_display = ('ausfahrt', 'nutzer', 'zusage', 'gefahren')
    list_filter = ('zusage', 'gefahren')


@admin.register(Verfuegbarkeit)
class VerfuegbarkeitAdmin(admin.ModelAdmin):
    list_display = ('nutzer', 'datum', 'tageszeit', 'stufe', 'ausfahrt')
    list_filter = ('stufe', 'tageszeit')


@admin.register(Verfuegbarkeitszeitraum)
class VerfuegbarkeitszeitraumAdmin(admin.ModelAdmin):
    list_display = ('nutzer', 'von', 'bis', 'stufe', 'ausfahrt')


@admin.register(Nachricht)
class NachrichtAdmin(admin.ModelAdmin):
    list_display = ('absender', 'empfaenger', 'crew', 'gesendet')


@admin.register(Fremdprofil)
class FremdprofilAdmin(admin.ModelAdmin):
    list_display = ('inhaber', 'dienst', 'erstellt')


@admin.register(Teilung)
class TeilungAdmin(admin.ModelAdmin):
    list_display = ('fremdprofil', 'empfaenger', 'geteilt_am')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    # Dummy-Phase: Einzelwerte sichtbar. Vor echten Nutzern auf Aggregation
    # reduzieren (Schritt 13b) - siehe Kommentar am Modell.
    list_display = ('ausfahrt', 'verfasser', 'bewerteter', 'urteil', 'erstellt')
    list_filter = ('urteil',)


@admin.register(Einwilligung)
class EinwilligungAdmin(admin.ModelAdmin):
    list_display = ('nutzer', 'art', 'version', 'erteilt_am', 'widerrufen_am')
    list_filter = ('art',)
