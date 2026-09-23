"""
URL configuration for ridebuddies project.

https://docs.djangoproject.com/en/6.1/topics/http/urls/

Seit TASK-120.04 (23.09.2026) gilt die Anmeldepflicht global
(LoginRequiredMiddleware in settings.py): Die Startseite braucht eine
Anmeldung; ohne sind nur die allauth-Seiten unter konto/ und der Admin-Login
erreichbar.
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path('', TemplateView.as_view(template_name='startseite.html'), name='startseite'),
    path('konto/', include('allauth.urls')),
    path('admin/', admin.site.urls),
]
