"""
Eine Anmeldeseite fuer alle: /admin/login/ leitet auf /konto/login/ um.

Karte TASK-120.10, Fabian 23.09.2026: Hinter der Basic-Auth-Sperre gibt es nur
noch EINE Anmeldeseite (allauth unter /konto/login/), die Rollen entscheiden
danach. Bis dahin brauchte die Verwaltung zwei Kennwoerter hintereinander -
erst /konto/login/, dann Djangos eigenen Admin-Login unter /admin/login/.

Warum eine eigene View VOR admin.site.urls und nicht einfach ein
RedirectView: Djangos Admin schickt jeden, der nicht is_active und is_staff ist,
auf admin:login (AdminSite.admin_view -> redirect_to_login). allauth wiederum
schickt einen bereits Angemeldeten von /konto/login/ sofort auf ?next= weiter
(ACCOUNT_AUTHENTICATED_LOGIN_REDIRECTS, Vorgabe True). Ein stumpfes
"/admin/login/ -> /konto/login/?next=/admin/" ergibt fuer einen angemeldeten
Nicht-Admin deshalb die Schleife

    /admin/ -> /admin/login/ -> /konto/login/?next=/admin/ -> /admin/ -> ...

Diese View unterscheidet darum drei Faelle:

- nicht angemeldet: auf account_login, next weitergereicht (Vorgabe /admin/);
- angemeldet mit Admin-Recht: direkt auf next (Vorgabe /admin/), damit ein
  Lesezeichen auf /admin/login/ nicht erst durch allauth laeuft;
- angemeldet OHNE Admin-Recht: auf die Startseite, mit einer Meldung.

Festlegung des Bauenden (23.09.2026), nicht von Fabian entschieden: Startseite
statt 403. Die Karte laesst beides zu. Die Startseite ist fuer einen Mitfahrer,
der /admin/ von Hand eintippt, der naechste sinnvolle Ort; ein 403 waere
ehrlicher, fuehrt aber ins Leere, solange es keine eigene Fehlerseite gibt
(DEBUG=False zeigt dann nur Djangos nackte "403 Forbidden"). Eine Schleife ist
in beiden Varianten ausgeschlossen, weil die Startseite fuer jeden
Angemeldeten mit 200 antwortet. Belegt in kern/tests/test_anmeldung.py.

next wird nur uebernommen, wenn url_has_allowed_host_and_scheme es als Adresse
auf DIESEM Host akzeptiert - sonst waere /admin/login/?next=https://boese.example
eine offene Umleitung. allauth prueft next zwar selbst noch einmal, aber im Fall
"angemeldeter Admin" leitet diese View direkt um, ohne allauth.

login_not_required ist Pflicht: Die LoginRequiredMiddleware wuerde die View
sonst selbst abfangen und auf /konto/login/?next=/admin/login/ schicken - dann
landete der Nutzer nach der Anmeldung wieder hier und wuerde erst im zweiten
Schritt auf /admin/ weitergereicht.
"""
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache


def _sicheres_ziel(request, vorgabe):
    ziel = request.GET.get(REDIRECT_FIELD_NAME, '')
    if ziel and url_has_allowed_host_and_scheme(
            ziel, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return ziel
    return vorgabe


@never_cache
@login_not_required
def admin_login_umleitung(request):
    ziel = _sicheres_ziel(request, reverse('admin:index'))
    if not request.user.is_authenticated:
        return redirect(f"{reverse('account_login')}?{urlencode({REDIRECT_FIELD_NAME: ziel})}")
    # Dieselbe Pruefung wie Djangos Admin selbst (is_active und is_staff),
    # damit beide Seiten nie verschieden urteilen - sonst waere die Schleife
    # zurueck.
    if admin.site.has_permission(request):
        return redirect(ziel)
    messages.info(request, 'Die Verwaltung ist nur für Admins.')
    return redirect('startseite')
