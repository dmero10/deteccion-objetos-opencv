"""Pruebas de la Sesión 1. No necesitan una cámara real: se usa una cámara simulada."""
from unittest import mock

import numpy as np
from django.test import TestCase
from django.urls import reverse

from .camera import Camara


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


class CamaraTests(TestCase):
    def setUp(self):
        self.camara = Camara(indice=0, ancho=640, alto=480, apagado_inactivo=60)

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

    def test_api_estado(self):
        r = self.client.get(reverse("detector:api_estado"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("activa", r.json())

    def test_iniciar_solo_post(self):
        self.assertEqual(self.client.get(reverse("detector:api_iniciar")).status_code, 405)

    def test_foto_con_camara_apagada(self):
        with mock.patch("detector.views.camara.foto", return_value=None):
            self.assertEqual(self.client.get(reverse("detector:foto")).status_code, 409)
