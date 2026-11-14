"""Pruebas. No necesitan una cámara real: se usa una cámara simulada.

ModeloRealTests ejecuta el modelo YOLO11n real (detector/modelos/yolo11n.onnx).
"""
import json
import time
import unittest
from unittest import mock

import numpy as np
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .camera import Camara
from .clases import CLASES
from .yolo import (DetectorYOLO, ModeloNoEncontrado, color_hex, decodificar_salida,
                   dibujar_detecciones, letterbox, modelo_disponible, resumir, sin_tildes)


class CapturaFalsa:
    """Imita a cv2.VideoCapture devolviendo frames negros."""

    def __init__(self, *args, **kwargs):
        self.abierta = True

    def isOpened(self):
        return self.abierta

    def read(self):
        return True, np.zeros((480, 640, 3), dtype=np.uint8)

    def set(self, *args):
        return True

    def get(self, prop):
        return {3: 640, 4: 480}.get(prop, 0)

    def release(self):
        self.abierta = False


class DetectorFalso:
    """Siempre "ve" una persona y dos tazas."""

    def detectar(self, frame, confianza):
        return [
            {"clase": 0, "nombre": "persona", "confianza": 0.91, "caja": (50, 40, 200, 300)},
            {"clase": 41, "nombre": "taza", "confianza": 0.66, "caja": (400, 300, 60, 70)},
            {"clase": 41, "nombre": "taza", "confianza": 0.72, "caja": (500, 310, 60, 70)},
        ]


def camara_de_prueba(**kwargs):
    kwargs.setdefault("apagado_inactivo", 60)
    return Camara(indice=0, ancho=640, alto=480, **kwargs)


# ----------------------------------------------------------------- Sesión 1
class CamaraTests(TestCase):
    def setUp(self):
        self.camara = camara_de_prueba(deteccion_activa=False)

    def tearDown(self):
        self.camara.detener()

    def test_procesar_mantiene_tamano(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        salida = self.camara.procesar(frame)
        self.assertEqual(salida.shape, (480, 640, 3))
        self.assertTrue(salida.any(), "Debe dibujar la marca de fecha/FPS sobre el frame")

    @mock.patch("detector.camera.cv2.VideoCapture", CapturaFalsa)
    def test_stream_entrega_jpeg(self):
        self.assertTrue(self.camara.iniciar())
        parte = next(self.camara.frames_mjpeg())
        self.assertTrue(parte.startswith(b"--frame\r\nContent-Type: image/jpeg"))
        self.assertIn(b"\xff\xd8", parte)  # inicio de un archivo JPEG
        self.assertEqual(self.camara.estado()["resolucion"], "640x480")

    @mock.patch("detector.camera.cv2.VideoCapture")
    def test_error_si_no_abre(self, video_capture):
        video_capture.return_value.isOpened.return_value = False
        self.assertFalse(self.camara.iniciar())
        self.assertIn("No se pudo abrir la cámara", self.camara.estado()["error"])


class VistasTests(TestCase):
    def test_index(self):
        r = self.client.get(reverse("detector:index"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Cámara en vivo")
        self.assertContains(r, "Detección de objetos")

    def test_api_estado(self):
        r = self.client.get(reverse("detector:api_estado"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("activa", r.json())
        self.assertIn("deteccion", r.json())

    def test_iniciar_solo_post(self):
        self.assertEqual(self.client.get(reverse("detector:api_iniciar")).status_code, 405)

    def test_foto_con_camara_apagada(self):
        with mock.patch("detector.views.camara.foto", return_value=None):
            self.assertEqual(self.client.get(reverse("detector:foto")).status_code, 409)


# ----------------------------------------------------------------- Sesión 2
class UtilidadesDeteccionTests(SimpleTestCase):
    def test_80_clases_coco(self):
        self.assertEqual(len(CLASES), 80)
        self.assertEqual(CLASES[0][1], "persona")
        self.assertEqual(CLASES[67][1], "celular")

    def test_sin_tildes_para_putText(self):
        self.assertEqual(sin_tildes("avión señal"), "avion senal")

    def test_color_hex(self):
        self.assertRegex(color_hex(5), r"^#[0-9a-f]{6}$")

    def test_resumir_agrupa_y_ordena(self):
        resumen = resumir(DetectorFalso().detectar(None, 0.5))
        self.assertEqual([g["nombre"] for g in resumen], ["taza", "persona"])
        self.assertEqual(resumen[0]["cantidad"], 2)
        self.assertEqual(resumen[0]["confianza"], 0.72)

    def test_dibujar_pinta_cajas(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        dibujar_detecciones(frame, DetectorFalso().detectar(frame, 0.5))
        self.assertTrue(frame[40, 100].any(), "Debe dibujar el borde superior de la caja")
        self.assertFalse(frame[200, 150].any(), "El interior de la caja no se rellena")

    def test_dibujar_caja_en_el_borde(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        caja = {"clase": 0, "nombre": "persona", "confianza": 0.5, "caja": (-10, -5, 500, 500)}
        dibujar_detecciones(frame, [caja])  # no debe lanzar excepción

    def test_error_si_falta_modelo(self):
        with mock.patch("detector.yolo.modelo_disponible", return_value=False):
            with self.assertRaises(ModeloNoEncontrado):
                DetectorYOLO()

    def test_letterbox_mantiene_proporcion(self):
        imagen, escala, (dx, dy) = letterbox(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(imagen.shape, (640, 640, 3))
        self.assertEqual(escala, 1.0)
        self.assertEqual((dx, dy), (0, 80))  # 80 px de relleno arriba y abajo


class DecodificarSalidaTests(SimpleTestCase):
    """Simula la salida cruda de YOLOv8: (1, 84, 8400)."""

    def salida(self, cajas):
        crudo = np.zeros((84, 8400), dtype=np.float32)
        for i, (cx, cy, w, h, clase, puntaje) in enumerate(cajas):
            crudo[:4, i] = (cx, cy, w, h)
            crudo[4 + clase, i] = puntaje
        return crudo[np.newaxis]

    def decodificar(self, cajas, confianza=0.45):
        # frame 640x480 -> letterbox con escala 1 y 80 px de relleno vertical
        return decodificar_salida(self.salida(cajas), confianza, 0.45, 1.0, (0, 80), (480, 640, 3))

    def test_convierte_coordenadas_al_frame(self):
        (d,) = self.decodificar([(320, 320, 100, 200, 67, 0.9)])
        self.assertEqual(d["nombre"], "celular")
        self.assertEqual(d["caja"], (270, 140, 100, 200))  # y = 320 - 100 - 80
        self.assertAlmostEqual(d["confianza"], 0.9, places=5)

    def test_filtra_por_confianza(self):
        self.assertEqual(self.decodificar([(320, 320, 100, 100, 0, 0.3)]), [])

    def test_nms_quita_cajas_repetidas_de_la_misma_clase(self):
        resultado = self.decodificar([
            (320, 320, 100, 200, 0, 0.9),
            (322, 318, 100, 200, 0, 0.8),  # casi la misma caja: se descarta
        ])
        self.assertEqual(len(resultado), 1)
        self.assertAlmostEqual(resultado[0]["confianza"], 0.9, places=5)

    def test_nms_por_clase_conserva_objetos_superpuestos(self):
        resultado = self.decodificar([
            (320, 320, 100, 200, 0, 0.9),   # persona
            (320, 320, 100, 200, 67, 0.7),  # celular en la misma zona
        ])
        self.assertEqual({d["nombre"] for d in resultado}, {"persona", "celular"})


def camara_encendida(**kwargs):
    """Cámara marcada como activa sin abrir hardware: se le pasan frames a mano."""
    camara = camara_de_prueba(**kwargs)
    camara._activa = True
    return camara


def frame_negro():
    return np.zeros((480, 640, 3), dtype=np.uint8)


class CamaraDeteccionTests(SimpleTestCase):
    """El hilo de detección llama a _detectar(); aquí se llama directamente."""

    def test_detectar_publica_resultados(self):
        camara = camara_encendida()
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            self.assertTrue(camara._detectar(frame_negro()))
        d = camara.estado()["deteccion"]
        self.assertEqual(d["total"], 3)
        self.assertEqual(d["objetos"][0]["nombre"], "taza")

    def test_procesar_dibuja_ultimas_detecciones_y_encola_frame(self):
        camara = camara_encendida(espejo=False)
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            camara._detectar(frame_negro())
        salida = camara.procesar(frame_negro())
        self.assertTrue(salida[200, 50].any(), "Debe dibujar el borde izquierdo de la caja de la persona")
        self.assertIsNotNone(camara._pendiente, "El frame queda listo para el hilo de detección")
        self.assertFalse(camara._pendiente.any(), "Se envía el frame sin las cajas dibujadas")

    def test_sin_modelo_el_video_sigue(self):
        camara = camara_encendida()
        with mock.patch("detector.camera.obtener_detector", side_effect=ModeloNoEncontrado("falta")):
            self.assertFalse(camara._detectar(frame_negro()))
        self.assertEqual(camara.procesar(frame_negro()).shape, (480, 640, 3))
        self.assertEqual(camara.estado()["deteccion"]["error"], "falta")

    def test_desactivar_limpia_resultados(self):
        camara = camara_encendida()
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            camara._detectar(frame_negro())
            camara.configurar_deteccion(activa=False)
            self.assertFalse(camara._detectar(frame_negro()))
        self.assertEqual(camara.estado()["deteccion"]["total"], 0)
        self.assertIsNone(camara._pendiente, "Sin detección no se encolan frames")

    @mock.patch("detector.camera.cv2.VideoCapture", CapturaFalsa)
    def test_hilos_de_captura_y_deteccion(self):
        camara = camara_de_prueba()
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            self.assertTrue(camara.iniciar())
            try:
                for _ in range(50):  # espera hasta 2.5 s a que el hilo de detección publique
                    if camara.estado()["deteccion"]["total"]:
                        break
                    time.sleep(0.05)
                self.assertEqual(camara.estado()["deteccion"]["total"], 3)
            finally:
                camara.detener()
        self.assertFalse(camara.activa)
        self.assertFalse(camara._hilo_deteccion.is_alive())

    def test_desactivar_durante_inferencia(self):
        """Si se apaga la detección mientras un frame se procesa, ese frame no reescribe resultados."""
        camara = camara_encendida()

        class DetectorQueSeApaga(DetectorFalso):
            def detectar(self, frame, confianza):
                camara.configurar_deteccion(activa=False)  # el usuario lo apaga "a mitad"
                return super().detectar(frame, confianza)

        with mock.patch("detector.camera.obtener_detector", return_value=DetectorQueSeApaga()):
            self.assertFalse(camara._detectar(frame_negro()))
        self.assertEqual(camara._resumen, [])
        self.assertEqual(camara.estado()["deteccion"]["objetos"], [])

    def test_confianza_se_limita(self):
        camara = camara_de_prueba()
        camara.configurar_deteccion(confianza=5)
        self.assertEqual(camara.confianza, 0.95)
        camara.configurar_deteccion(confianza=-1)
        self.assertEqual(camara.confianza, 0.05)


class ApiDeteccionTests(TestCase):
    url = reverse("detector:api_deteccion")

    def post(self, datos):
        return self.client.post(self.url, data=json.dumps(datos), content_type="application/json")

    def test_configurar(self):
        with mock.patch("detector.views.camara.configurar_deteccion") as configurar:
            r = self.post({"activa": False, "confianza": 0.6})
        self.assertEqual(r.status_code, 200)
        configurar.assert_called_once_with(activa=False, confianza=0.6)

    def test_valida_datos(self):
        self.assertEqual(self.post({"confianza": "alta"}).status_code, 400)
        self.assertEqual(self.post({"activa": "si"}).status_code, 400)
        self.assertEqual(self.post([1, 2]).status_code, 400)
        r = self.client.post(self.url, data="{no es json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_solo_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


@unittest.skipUnless(modelo_disponible(), "Falta detector/modelos/yolo11n.onnx")
class ModeloRealTests(SimpleTestCase):
    def test_carga_y_detecta_en_imagen_vacia(self):
        detector = DetectorYOLO()
        resultado = detector.detectar(np.zeros((480, 640, 3), dtype=np.uint8), 0.45)
        self.assertIsInstance(resultado, list)
        self.assertEqual(resultado, [], "Una imagen negra no debe tener objetos")
