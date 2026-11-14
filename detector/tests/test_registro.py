"""Registro de avistamientos en PostgreSQL (Sesión 3)."""
from unittest import mock

import cv2
import numpy as np
from django.db import DatabaseError
from django.test import TestCase

from detector.models import Avistamiento
from detector.registro import Registrador, recortar

from .utiles import DetectorFalso, frame_negro, frame_ruido


class RecortarTests(TestCase):
    def test_recorta_con_margen_y_reduce(self):
        recorte = recortar(frame_ruido(), (50, 40, 200, 300))
        self.assertLessEqual(max(recorte.shape[:2]), 320)
        self.assertGreater(recorte.shape[0], recorte.shape[1], "La forma de la caja se conserva")

    def test_caja_degenerada(self):
        self.assertIsNone(recortar(frame_negro(), (700, 500, 10, 10)))


class RegistradorTests(TestCase):
    def setUp(self):
        self.registrador = Registrador(intervalo=15)
        self.detecciones = DetectorFalso().detectar(None, 0.5)

    def test_guarda_un_avistamiento_por_clase_con_recorte_jpeg(self):
        eventos = self.registrador.registrar(frame_ruido(), self.detecciones)
        self.assertEqual(len(eventos), 2)
        self.assertEqual(Avistamiento.objects.count(), 2)
        taza = Avistamiento.objects.get(clase=41)
        self.assertEqual(taza.cantidad, 2)
        self.assertAlmostEqual(taza.confianza, 0.72, places=4, msg="Se guarda la caja más confiable")
        self.assertEqual((taza.x, taza.y, taza.ancho, taza.alto), (500, 310, 60, 70))
        recorte = cv2.imdecode(np.frombuffer(bytes(taza.imagen), np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(recorte, "La imagen guardada es un JPEG válido")

    def test_respeta_el_intervalo_por_clase(self):
        self.registrador.registrar(frame_ruido(), self.detecciones)
        self.assertEqual(self.registrador.registrar(frame_ruido(), self.detecciones), [])
        self.assertEqual(Avistamiento.objects.count(), 2)

    def test_otra_clase_no_espera_el_intervalo(self):
        self.registrador.registrar(frame_ruido(), self.detecciones[:1])  # solo persona
        eventos = self.registrador.registrar(frame_ruido(), self.detecciones)
        self.assertEqual([e["nombre"] for e in eventos], ["taza"])

    def test_vuelve_a_registrar_pasado_el_intervalo(self):
        with mock.patch("detector.registro.time.monotonic", side_effect=[100.0, 116.0]):
            self.registrador.registrar(frame_ruido(), self.detecciones[:1])
            self.registrador.registrar(frame_ruido(), self.detecciones[:1])
        self.assertEqual(Avistamiento.objects.filter(clase=0).count(), 2)

    def test_marca_nuevo_hallazgo_solo_la_primera_vez(self):
        Avistamiento.objects.create(clase=0, nombre="persona", confianza=0.8, imagen=b"x")
        eventos = {e["nombre"]: e for e in self.registrador.registrar(frame_ruido(), self.detecciones)}
        self.assertFalse(eventos["persona"]["nuevo"], "La persona ya estaba en el álbum")
        self.assertTrue(eventos["taza"]["nuevo"])
        self.assertEqual(len(self.registrador.descubiertas()), 2)

    def test_recientes_en_orden_inverso(self):
        self.registrador.registrar(frame_ruido(), self.detecciones)
        recientes = self.registrador.recientes()
        self.assertEqual(len(recientes), 2)
        self.assertTrue(recientes[0]["imagen"].endswith("/imagen/"))

    def test_desactivado_no_guarda(self):
        self.registrador.activo = False
        self.assertEqual(self.registrador.registrar(frame_ruido(), self.detecciones), [])
        self.assertEqual(Avistamiento.objects.count(), 0)

    def test_error_de_base_de_datos_no_rompe(self):
        with mock.patch.object(Avistamiento.objects, "create", side_effect=DatabaseError("caída")), \
                self.assertLogs("detector.registro", level="ERROR"):
            self.assertEqual(self.registrador.registrar(frame_ruido(), self.detecciones), [])
        self.assertIn("caída", self.registrador.error)

    def test_reiniciar_olvida_el_estado(self):
        self.registrador.registrar(frame_ruido(), self.detecciones)
        Avistamiento.objects.all().delete()
        self.registrador.reiniciar()
        self.assertEqual(self.registrador.recientes(), [])
        self.assertEqual(self.registrador.descubiertas(), set())
        self.assertEqual(len(self.registrador.registrar(frame_ruido(), self.detecciones)), 2)
