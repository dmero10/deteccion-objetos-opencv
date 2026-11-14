from django.urls import path

from . import views

app_name = "detector"

urlpatterns = [
    # Observatorio (video en vivo)
    path("", views.index, name="index"),
    path("video/", views.video_feed, name="video_feed"),
    path("foto/", views.foto, name="foto"),
    path("api/estado/", views.api_estado, name="api_estado"),
    path("api/camara/iniciar/", views.api_iniciar, name="api_iniciar"),
    path("api/camara/detener/", views.api_detener, name="api_detener"),
    path("api/deteccion/", views.api_configurar_deteccion, name="api_deteccion"),
    # Álbum y bitácora (PostgreSQL)
    path("album/", views.album, name="album"),
    path("album/<int:clase>/", views.ir_a_bitacora_de, name="album_clase"),
    path("bitacora/", views.bitacora, name="bitacora"),
    path("bitacora/exportar/", views.exportar_csv, name="exportar_csv"),
    path("bitacora/vaciar/", views.vaciar_bitacora, name="vaciar_bitacora"),
    path("avistamientos/<int:pk>/imagen/", views.imagen_avistamiento, name="imagen_avistamiento"),
    # Analizar una imagen subida
    path("analizar/", views.analizar, name="analizar"),
]
