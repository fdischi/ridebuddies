"""Kleine Fabriken fuer die Tests - bewusst ohne factory_boy, um keine
Abhaengigkeit nur fuer Tests mitzuziehen."""
from django.contrib.auth import get_user_model

from kern.models import (
    Ausfahrt,
    Beitrag,
    Crew,
    Mitgliedschaft,
    Profil,
    Stufe,
    Teilnahme,
    Vorschlag,
)

# Je Stufe ein Feld mit erkennbarem Wert: region ist voreingestellt
# oeffentlich, nogo verbunden; motorrad stellen wir in profil_fuellen auf
# Ridebuddies um - so zeigt jeder Test, bis zu welcher Stufe er reicht.
OEFFENTLICHES_FELD = 'region'
VERBUNDENES_FELD = 'nogo'
RIDEBUDDY_FELD = 'motorrad'


def nutzer(name):
    # Ohne Kennwort (unbrauchbar gesetzt): Jeder PBKDF2-Hash kostet auf VM 140
    # unter Last deutlich ueber eine Sekunde, und die Tests legen weit ueber
    # hundert Nutzer an (23.09.2026: der erste Lauf war nach 300 s nicht fertig).
    # Anmelden muss sich hier niemand - die Tests rufen die Schicht direkt auf.
    return get_user_model().objects.create_user(
        username=name, email=f'{name}@example.org', password=None)


def profil_fuellen(n):
    """Profil mit je einem Wert pro Stufe und je einem Beitrag pro Stufe."""
    profil = Profil.objects.get(nutzer=n)
    profil.region = f'Region von {n.username}'
    profil.nogo = f'No-Go von {n.username}'
    profil.motorrad = f'Motorrad von {n.username}'
    profil.feldstufen = {RIDEBUDDY_FELD: Stufe.RIDEBUDDIES.value}
    profil.save()
    for stufe in (Stufe.OEFFENTLICH, Stufe.VERBUNDEN, Stufe.RIDEBUDDIES):
        Beitrag.objects.create(autor=n, text=f'{n.username} {stufe.label}', stufe=stufe)
    return profil


def fertiger_nutzer(name):
    n = nutzer(name)
    profil_fuellen(n)
    return n


def crew_mit(*mitglieder, rolle=Mitgliedschaft.Rolle.MITGLIED, name='Crew'):
    crew = Crew.objects.create(name=name)
    for m in mitglieder:
        Mitgliedschaft.objects.create(crew=crew, nutzer=m, rolle=rolle)
    return crew


def vorschlag(empfaenger, kandidat, runde=1):
    return Vorschlag.objects.create(empfaenger=empfaenger, kandidat=kandidat, runde=runde,
                                    begruendung={'tempo': 'beide zügig'})


def gefahrene_ausfahrt(*teilnehmer, titel='Eifelrunde', status=Ausfahrt.Status.GEFAHREN):
    ausfahrt = Ausfahrt.objects.create(titel=titel, status=status)
    for t in teilnehmer:
        Teilnahme.objects.create(ausfahrt=ausfahrt, nutzer=t,
                                 zusage=Teilnahme.Zusage.ZUGESAGT, gefahren=True)
    return ausfahrt


def verbinden(a, b):
    """Aktive Verbindung auf Stufe verbunden, auf dem normalen Weg (Anfrage)."""
    from kern import ablaeufe
    return ablaeufe.anfrage_beantworten(ablaeufe.anfrage_stellen(a, b), b, annehmen=True)


def ridebuddies_machen(a, b):
    """Stufe Ridebuddies auf dem einzigen erlaubten Weg (Fabian, 23.09.2026):
    verbinden, dann Ridebuddy-Anfrage von a, von b bestaetigt."""
    from kern import ablaeufe
    verbinden(a, b)
    return ablaeufe.ridebuddy_anfrage_beantworten(
        ablaeufe.ridebuddy_anfrage_stellen(a, b), b, bestaetigen=True)
