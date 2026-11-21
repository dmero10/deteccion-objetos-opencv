"""INTEGRACIÓN: flujos completos de la aplicación, de punta a punta.

Se usa la cámara real de la aplicación (el objeto `camara` que usan las vistas) con dos
piezas simuladas: el dispositivo de video (CapturaFalsa) y la red neuronal (DetectorFalso,
que "ve" una persona y dos tazas). Todo lo demás es real: hilos, vistas, plantillas,
registrador y PostgreSQL.
"""
import json
import time
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from detector.camera import camara
from detector.models import Avistamiento

from ..utiles import CapturaFalsa, DetectorFalso

IMAGEN_BUS = Path(__file__).resolve().parents[2] / "datos_prueba" / "bus.jpg"


def esperar(condicion, segundos=5.0):
    limite = time.time() + segundos
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.05)
    return False


class FlujoCamaraCompletoTests(TransactionTestCase):
    """Encender → video → detectar → guardar en PostgreSQL → ver en las páginas → apagar.

    TransactionTestCase porque el hilo de detección guarda con su propia conexión a la BD.
    """

    def setUp(self):
        for objetivo, valor in (("detector.camera.cv2.VideoCapture", CapturaFalsa),
                                ("detector.camera.obtener_detector", lambda: DetectorFalso())):
            parche = mock.patch(objetivo, valor)
            parche.start()
            self.addCleanup(parche.stop)
        self.reiniciar_camara()
        self.addCleanup(self.reiniciar_camara)

    def reiniciar_camara(self):
        camara.detener()
        camara._detector, camara._carga_fallida = None, False
        camara.configurar_deteccion(activa=True, confianza=0.45, registrar=True)
        camara.registrador.reiniciar()

    def post(self, nombre, datos=None):
        return self.client.post(reverse(nombre), data=json.dumps(datos or {}), content_type="application/json")

    def estado(self):
        return self.client.get(reverse("detector:api_estado")).json()

    def test_flujo_completo(self):
        # 1. Encender la cámara desde la API
        e = self.post("detector:api_iniciar").json()
        self.assertTrue(e["activa"])
        self.assertEqual(e["resolucion"], "640x480")

        # 2. El navegador recibe el video MJPEG
        r = self.client.get(reverse("detector:video_feed"))
        self.assertEqual(r["Content-Type"], "multipart/x-mixed-replace; boundary=frame")
        primera_parte = next(iter(r.streaming_content))
        self.assertIn(b"Content-Type: image/jpeg", primera_parte)
        r.close()

        # 3. El hilo de detección publica los objetos
        self.assertTrue(esperar(lambda: self.estado()["deteccion"]["total"] == 3), self.estado())
        objetos = {o["nombre"]: o["cantidad"] for o in self.estado()["deteccion"]["objetos"]}
        self.assertEqual(objetos, {"persona": 1, "taza": 2})

        # 4. El registrador guarda en PostgreSQL un avistamiento por clase
        self.assertTrue(esperar(lambda: Avistamiento.objects.count() == 2))
        self.assertEqual(Avistamiento.objects.get(clase=41).cantidad, 2)
        recientes = self.estado()["registro"]["recientes"]
        self.assertEqual({a["nombre"] for a in recientes}, {"persona", "taza"})
        self.assertTrue(all(a["nuevo"] for a in recientes), "Primera vez que se ven: objetos nuevos")

        # 5. Lo guardado aparece en las páginas
        historial = self.client.get(reverse("detector:bitacora"))
        self.assertEqual(historial.context["resumen"]["total"], 2)
        self.assertContains(historial, "taza")
        self.assertEqual(self.client.get(reverse("detector:album")).context["descubiertas"], 2)
        csv = self.client.get(reverse("detector:exportar_csv")).content.decode("utf-8-sig")
        self.assertEqual(len(csv.strip().splitlines()), 3)  # cabecera + 2
        imagen = self.client.get(recientes[0]["imagen"])
        self.assertEqual(imagen.content[:2], b"\xff\xd8")

        # 6. Foto del video actual
        foto = self.client.get(reverse("detector:foto"))
        self.assertEqual((foto.status_code, foto["Content-Type"]), (200, "image/jpeg"))

        # 7. Apagar
        self.assertFalse(self.post("detector:api_detener").json()["activa"])
        self.assertEqual(self.client.get(reverse("detector:foto")).status_code, 409)

    def test_cambiar_ajustes_en_vivo(self):
        # Con el guardado apagado: detecta pero no guarda nada en la BD
        self.post("detector:api_deteccion", {"registrar": False})
        self.post("detector:api_iniciar")
        self.assertTrue(esperar(lambda: self.estado()["deteccion"]["total"] == 3))
        time.sleep(0.3)
        self.assertEqual(Avistamiento.objects.count(), 0)

        # Pausar la detección: el video sigue, sin objetos
        e = self.post("detector:api_deteccion", {"activa": False}).json()
        self.assertTrue(e["activa"])
        self.assertEqual(e["deteccion"]["total"], 0)

        # Reanudar con otra confianza y el guardado encendido: ahora sí guarda
        self.post("detector:api_deteccion", {"activa": True, "registrar": True, "confianza": 0.6})
        self.assertEqual(self.estado()["deteccion"]["confianza"], 0.6)
        self.assertTrue(esperar(lambda: Avistamiento.objects.count() == 2))

    def test_dos_pestanas_comparten_una_sola_camara(self):
        self.post("detector:api_iniciar")
        pestana1 = self.client.get(reverse("detector:video_feed"))
        pestana2 = self.client.get(reverse("detector:video_feed"))
        next(iter(pestana1.streaming_content))
        next(iter(pestana2.streaming_content))
        self.assertEqual(self.estado()["clientes"], 2)
        pestana1.close()
        pestana2.close()
        self.assertEqual(self.estado()["clientes"], 0)

    def test_camara_ocupada_informa_el_error(self):
        with mock.patch("detector.camera.cv2.VideoCapture") as video:
            video.return_value.isOpened.return_value = False
            r = self.post("detector:api_iniciar")
            video_feed = self.client.get(reverse("detector:video_feed"))
        self.assertEqual(r.status_code, 503)
        self.assertIn("No se pudo abrir la cámara", r.json()["error"])
        self.assertEqual(video_feed.status_code, 503)


class FlujoHistorialTests(TestCase):
    """Datos en PostgreSQL → filtros → CSV → borrar."""

    def setUp(self):
        for clase, nombre, conf in ((0, "persona", 0.9), (0, "persona", 0.7), (41, "taza", 0.6)):
            Avistamiento.objects.create(clase=clase, nombre=nombre, confianza=conf, imagen=b"\xff\xd8x")

    def test_filtro_y_csv_coinciden(self):
        historial = self.client.get(reverse("detector:bitacora"), {"objeto": 0})
        csv = self.client.get(reverse("detector:exportar_csv"), {"objeto": 0}).content.decode("utf-8-sig")
        self.assertEqual(historial.context["resumen"]["total"], len(csv.strip().splitlines()) - 1)

    def test_desde_objetos_al_historial_filtrado(self):
        r = self.client.get(reverse("detector:album_clase", args=[41]), follow=True)
        self.assertEqual(r.context["resumen"]["total"], 1)
        self.assertEqual(r.context["filtros"]["objeto"], "41")

    def test_borrar_historial_reinicia_todo(self):
        r = self.client.post(reverse("detector:vaciar_bitacora"), follow=True)
        self.assertContains(r, "Historial borrado: se eliminaron 3 detecciones.")
        self.assertEqual(Avistamiento.objects.count(), 0)
        self.assertEqual(self.client.get(reverse("detector:album")).context["descubiertas"], 0)
        self.assertEqual(self.client.get(reverse("detector:api_estado")).json()["registro"]["descubiertas"], 0)


class FlujoAnalizarImagenTests(TestCase):
    """Subir imagen → YOLO11n real con OpenCV → página de resultado. No guarda nada."""

    def test_analizar_imagen_real(self):
        r = self.client.post(reverse("detector:analizar"),
                             {"imagen": SimpleUploadedFile("bus.jpg", IMAGEN_BUS.read_bytes()), "confianza": 45})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "detector/analizar.html")
        nombres = [d["nombre"] for d in r.context["resultado"]["detecciones"]]
        self.assertGreaterEqual(nombres.count("persona"), 3)
        self.assertIn("bus", nombres)
        self.assertContains(r, "data:image/jpeg;base64,")
        self.assertEqual(Avistamiento.objects.count(), 0)

    def test_confianza_del_formulario_se_respeta(self):
        archivo = lambda: SimpleUploadedFile("bus.jpg", IMAGEN_BUS.read_bytes())  # noqa: E731
        baja = self.client.post(reverse("detector:analizar"), {"imagen": archivo(), "confianza": 25})
        alta = self.client.post(reverse("detector:analizar"), {"imagen": archivo(), "confianza": 90})
        self.assertGreaterEqual(baja.context["resultado"]["total"], alta.context["resultado"]["total"])
        self.assertEqual(alta.context["confianza"], 90)
