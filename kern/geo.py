"""
Entfernung zweier Punkte auf der Erde - Haversine, ohne Zusatzpaket.

Karte TASK-120.05 (23.09.2026): Die Dummy-Profile tragen seitdem Koordinaten
(Profil.breitengrad/laengengrad), und das Pruefblatt fuer das Matching begruendet
"nie vorschlagen, Radius" mit einer Entfernung. Diese Entfernung muss jemand
nachrechnen koennen - der Test kern/tests/test_dummies.py tut es mit genau
dieser Funktion.

Das ist KEIN Matching (das ist Schritt 8, TASK-120.08). Hier steht nur die
Geometrie, die das Matching spaeter ebenfalls braucht.

Warum Haversine und nicht geopy/GeoDjango: Luftlinie auf einer Kugel reicht fuer
"liegt im Umkreis von 50 km" voellig; der Fehler gegenueber dem Ellipsoid liegt
unter 0,5 %, weit unter der Unschaerfe "Ortsmitte statt Wohnort". Eine
Abhaengigkeit mit GDAL fuer eine Zeile Trigonometrie waere auf enduro-web
(4 GB, Ubuntu 24.04) ein Paket mehr, das bei jedem Update mitmuss.
Festlegung (nicht von Fabian entschieden): Luftlinie, nicht Fahrstrecke.
"""
import math

ERDRADIUS_KM = 6371.0088  # mittlerer Erdradius (IUGG)


def entfernung_km(breite1, laenge1, breite2, laenge2):
    """Luftlinie in km zwischen zwei Punkten (Grad, Dezimal oder float)."""
    b1, l1, b2, l2 = (math.radians(float(w)) for w in (breite1, laenge1, breite2, laenge2))
    a = (math.sin((b2 - b1) / 2) ** 2
         + math.cos(b1) * math.cos(b2) * math.sin((l2 - l1) / 2) ** 2)
    return 2 * ERDRADIUS_KM * math.asin(math.sqrt(a))


def profil_entfernung_km(profil_a, profil_b):
    """Luftlinie zwischen zwei Profilen, oder None, wenn einem die Koordinaten fehlen."""
    if None in (profil_a.breitengrad, profil_a.laengengrad,
                profil_b.breitengrad, profil_b.laengengrad):
        return None
    return entfernung_km(profil_a.breitengrad, profil_a.laengengrad,
                         profil_b.breitengrad, profil_b.laengengrad)
