"""
URL configuration for ridebuddies project.

https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path('', TemplateView.as_view(template_name='startseite.html'), name='startseite'),
    path('admin/', admin.site.urls),
]
