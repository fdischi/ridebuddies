"""
URL configuration for ridebuddies project.

https://docs.djangoproject.com/en/6.1/topics/http/urls/

Seit TASK-120.04 (23.09.2026) gilt die Anmeldepflicht global
(LoginRequiredMiddleware in settings.py): Die Startseite braucht eine
Anmeldung; ohne sind nur die allauth-Seiten unter konto/ erreichbar.

Seit TASK-120.10 (23.09.2026) gibt es nur noch EINE Anmeldeseite:
admin/login/ steht VOR admin.site.urls und leitet auf konto/login/ um
(kern/views.py, dort auch, warum das ohne Schleife gehen muss). Die Reihenfolge
traegt: Django nimmt das erste passende Muster, reverse('admin:login') liefert
weiter /admin/login/ und landet damit ebenfalls hier.
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from kern.views import admin_login_umleitung

urlpatterns = [
    path('', TemplateView.as_view(template_name='startseite.html'), name='startseite'),
    path('konto/', include('allauth.urls')),
    path('admin/login/', admin_login_umleitung, name='admin_login_umleitung'),
    path('admin/', admin.site.urls),
]
