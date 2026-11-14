from django.urls import path

from . import views

app_name = "detector"

urlpatterns = [
    path("", views.index, name="index"),
    path("video/", views.video_feed, name="video_feed"),
    path("foto/", views.foto, name="foto"),
    path("api/estado/", views.api_estado, name="api_estado"),
    path("api/camara/iniciar/", views.api_iniciar, name="api_iniciar"),
    path("api/camara/detener/", views.api_detener, name="api_detener"),
    path("api/deteccion/", views.api_configurar_deteccion, name="api_deteccion"),
]
