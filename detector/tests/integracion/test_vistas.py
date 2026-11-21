"""Páginas y API web (Sesiones 1-3)."""
import json
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from detector.models import Avistamiento
from detector.yolo import modelo_disponible

from ..utiles import DetectorFalso

IMAGEN_BUS = Path(__file__).resolve().parents[2] / "datos_prueba" / "bus.jpg"


def crear(clase=0, nombre="persona", confianza=0.8, hace_horas=0):
    a = Avistamiento.objects.create(clase=clase, nombre=nombre, confianza=confianza, imagen=b"\xff\xd8jpg")
    if hace_horas:
        Avistamiento.objects.filter(pk=a.pk).update(fecha=timezone.now() - timedelta(hours=hace_horas))
    return a


class ObservatorioTests(TestCase):
    def test_pagina_principal(self):
        r = self.client.get(reverse("detector:index"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Detección en vivo")
        self.assertContains(r, 'id="video"')
        self.assertContains(r, "Guardar en el historial")

    def test_api_estado(self):
        datos = self.client.get(reverse("detector:api_estado")).json()
        for clave in ("activa", "fps", "deteccion", "registro"):
            self.assertIn(clave, datos)
        self.assertEqual(datos["registro"]["total_clases"], 80)

    def test_iniciar_y_detener_solo_por_post(self):
        self.assertEqual(self.client.get(reverse("detector:api_iniciar")).status_code, 405)
        self.assertEqual(self.client.get(reverse("detector:api_detener")).status_code, 405)

    def test_foto_con_camara_apagada(self):
        with mock.patch("detector.views.camara.foto", return_value=None):
            self.assertEqual(self.client.get(reverse("detector:foto")).status_code, 409)

    def test_foto_con_camara_encendida(self):
        with mock.patch("detector.views.camara.foto", return_value=b"\xff\xd8jpg"):
            r = self.client.get(reverse("detector:foto"))
        self.assertEqual(r["Content-Type"], "image/jpeg")
        self.assertIn("attachment", r["Content-Disposition"])

    def test_video_devuelve_503_si_no_hay_camara(self):
        with mock.patch("detector.views.camara.iniciar", return_value=False):
            self.assertEqual(self.client.get(reverse("detector:video_feed")).status_code, 503)


class ApiDeteccionTests(TestCase):
    url = reverse("detector:api_deteccion")

    def post(self, datos):
        return self.client.post(self.url, data=json.dumps(datos), content_type="application/json")

    def test_configurar(self):
        with mock.patch("detector.views.camara.configurar_deteccion") as configurar:
            r = self.post({"activa": False, "confianza": 0.6, "registrar": True})
        self.assertEqual(r.status_code, 200)
        configurar.assert_called_once_with(activa=False, confianza=0.6, registrar=True)

    def test_valida_datos(self):
        self.assertEqual(self.post({"confianza": "alta"}).status_code, 400)
        self.assertEqual(self.post({"activa": "si"}).status_code, 400)
        self.assertEqual(self.post({"registrar": 1}).status_code, 400)
        self.assertEqual(self.post([1, 2]).status_code, 400)
        r = self.client.post(self.url, data="{no es json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_solo_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class AlbumTests(TestCase):
    def test_album_vacio_muestra_80_laminas_ocultas(self):
        r = self.client.get(reverse("detector:album"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["descubiertas"], 0)
        self.assertEqual(sum(len(s["casillas"]) for s in r.context["secciones"]), 80)
        self.assertContains(r, "Aún no detectado", count=80)

    def test_album_usa_la_foto_mas_confiable(self):
        crear(confianza=0.6)
        mejor = crear(confianza=0.95)
        crear(clase=67, nombre="celular", confianza=0.7)
        r = self.client.get(reverse("detector:album"))
        self.assertEqual(r.context["descubiertas"], 2)
        persona = r.context["secciones"][0]["casillas"][0]
        self.assertEqual(persona["datos"]["foto"], mejor.pk)
        self.assertEqual(persona["datos"]["total"], 2)
        self.assertContains(r, reverse("detector:imagen_avistamiento", args=[mejor.pk]))
        self.assertTrue(r.context["marcas"][67])

    def test_lamina_lleva_a_la_bitacora_filtrada(self):
        r = self.client.get(reverse("detector:album_clase", args=[67]))
        self.assertRedirects(r, reverse("detector:bitacora") + "?objeto=67")


class BitacoraTests(TestCase):
    def setUp(self):
        crear(confianza=0.9)
        crear(confianza=0.7, hace_horas=30)
        crear(clase=41, nombre="taza", confianza=0.6)

    def test_lista_y_resume(self):
        r = self.client.get(reverse("detector:bitacora"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["resumen"]["total"], 3)
        self.assertEqual(r.context["resumen"]["distintos"], 2)
        self.assertEqual(r.context["top"][0]["nombre"], "persona")
        self.assertEqual(sum(h["total"] for h in r.context["horas"]), 3)

    def test_filtra_por_objeto(self):
        r = self.client.get(reverse("detector:bitacora"), {"objeto": 41})
        self.assertEqual(r.context["resumen"]["total"], 1)

    def test_filtra_por_fecha(self):
        hoy = timezone.localdate().isoformat()
        r = self.client.get(reverse("detector:bitacora"), {"desde": hoy, "hasta": hoy})
        self.assertEqual(r.context["resumen"]["total"], 2)

    def test_filtros_invalidos_se_ignoran(self):
        r = self.client.get(reverse("detector:bitacora"), {"objeto": "abc", "desde": "ayer"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["resumen"]["total"], 3)

    def test_paginacion(self):
        for _ in range(30):
            crear()
        r = self.client.get(reverse("detector:bitacora"), {"pagina": 2})
        self.assertEqual(r.context["pagina"].number, 2)
        self.assertEqual(len(r.context["pagina"].object_list), 33 - 24)

    def test_exportar_csv(self):
        r = self.client.get(reverse("detector:exportar_csv"), {"objeto": 0})
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        filas = r.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(filas[0].split(",")[:3], ["id", "fecha", "objeto"])
        self.assertEqual(len(filas), 3)  # cabecera + 2 personas

    def test_imagen_del_avistamiento(self):
        a = Avistamiento.objects.first()
        r = self.client.get(reverse("detector:imagen_avistamiento", args=[a.pk]))
        self.assertEqual(r["Content-Type"], "image/jpeg")
        self.assertEqual(r.content, b"\xff\xd8jpg")
        self.assertEqual(self.client.get(reverse("detector:imagen_avistamiento", args=[9999])).status_code, 404)

    def test_vaciar_solo_por_post(self):
        self.assertEqual(self.client.get(reverse("detector:vaciar_bitacora")).status_code, 405)
        r = self.client.post(reverse("detector:vaciar_bitacora"), follow=True)
        self.assertEqual(Avistamiento.objects.count(), 0)
        self.assertContains(r, "Historial borrado")


class AnalizarTests(TestCase):
    url = reverse("detector:analizar")

    def test_formulario(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'type="file"')

    def test_sin_archivo(self):
        r = self.client.post(self.url, {"confianza": 45})
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, "Selecciona una imagen", status_code=400)

    def test_archivo_que_no_es_imagen(self):
        falso = SimpleUploadedFile("notas.txt", b"esto no es una imagen", content_type="text/plain")
        r = self.client.post(self.url, {"imagen": falso})
        self.assertContains(r, "no es una imagen válida", status_code=400)

    @override_settings(ANALIZAR_MAX_MB=0.0001)
    def test_imagen_demasiado_grande(self):
        r = self.client.post(self.url, {"imagen": SimpleUploadedFile("bus.jpg", IMAGEN_BUS.read_bytes())})
        self.assertContains(r, "pesa más de", status_code=400)

    def test_analiza_con_detector_simulado(self):
        with mock.patch("detector.views.obtener_detector", return_value=DetectorFalso()):
            r = self.client.post(self.url, {"imagen": SimpleUploadedFile("bus.jpg", IMAGEN_BUS.read_bytes())})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["resultado"]["total"], 3)
        self.assertTrue(r.context["resultado"]["imagen"].startswith("data:image/jpeg;base64,"))

    def test_analizar_no_guarda_en_la_bitacora(self):
        with mock.patch("detector.views.obtener_detector", return_value=DetectorFalso()):
            self.client.post(self.url, {"imagen": SimpleUploadedFile("bus.jpg", IMAGEN_BUS.read_bytes())})
        self.assertEqual(Avistamiento.objects.count(), 0)

    def test_analiza_con_el_modelo_real(self):
        if not modelo_disponible():
            self.skipTest("Falta el modelo")
        r = self.client.post(self.url, {"imagen": SimpleUploadedFile("bus.jpg", IMAGEN_BUS.read_bytes()),
                                        "confianza": 45})
        nombres = [d["nombre"] for d in r.context["resultado"]["detecciones"]]
        self.assertGreaterEqual(nombres.count("persona"), 3)  # la 4.ª persona está cortada en el borde
        self.assertIn("bus", nombres)
