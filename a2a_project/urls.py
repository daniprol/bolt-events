"""URL configuration for a2a_project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # A2A routes will be included from a2a_app
    path("", include("a2a_app.urls")),
]
