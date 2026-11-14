"""Módulo de detección (Sesión 2): decodificación de YOLO, NMS, dibujo y utilidades."""
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from django.test import SimpleTestCase

from detector.clases import CATEGORIAS, CLASES, categoria_de
from detector.yolo import (DetectorYOLO, ModeloNoEncontrado, color_hex, decodificar_salida,
                           dibujar_detecciones, letterbox, modelo_disponible, resumir, sin_tildes)

from .utiles import DetectorFalso

IMAGEN_BUS = Path(__file__).resolve().parent.parent / "datos_prueba" / "bus.jpg"


class ClasesTests(SimpleTestCase):
    def test_80_clases_coco(self):
        self.assertEqual(len(CLASES), 80)
        self.assertEqual(CLASES[0][1], "persona")
        self.assertEqual(CLASES[67][1], "celular")

    def test_categorias_cubren_las_80_clases_sin_huecos(self):
        cubiertas = [c for _, inicio, fin in CATEGORIAS for c in range(inicio, fin + 1)]
        self.assertEqual(cubiertas, list(range(80)))
        self.assertEqual(categoria_de(67), "Electrónica")
        self.assertEqual(categoria_de(41), "Cocina")


class UtilidadesTests(SimpleTestCase):
    def test_sin_tildes_para_putText(self):
        self.assertEqual(sin_tildes("avión señal"), "avion senal")

    def test_color_hex(self):
        self.assertRegex(color_hex(5), r"^#[0-9a-f]{6}$")
        self.assertEqual(color_hex(0), color_hex(12), "La paleta se repite de forma estable")

    def test_resumir_agrupa_y_ordena(self):
        resumen = resumir(DetectorFalso().detectar(None, 0.5))
        self.assertEqual([g["nombre"] for g in resumen], ["taza", "persona"])
        self.assertEqual(resumen[0]["cantidad"], 2)
        self.assertEqual(resumen[0]["confianza"], 0.72)

    def test_dibujar_pinta_cajas_sin_rellenarlas(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        dibujar_detecciones(frame, DetectorFalso().detectar(frame, 0.5))
        self.assertTrue(frame[40, 100].any(), "Debe dibujar el borde superior de la caja")
        self.assertFalse(frame[200, 150].any(), "El interior de la caja no se rellena")

    def test_dibujar_caja_que_se_sale_del_frame(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        caja = {"clase": 0, "nombre": "persona", "confianza": 0.5, "caja": (-10, -5, 500, 500)}
        dibujar_detecciones(frame, [caja])  # no debe lanzar excepción

    def test_letterbox_mantiene_proporcion(self):
        imagen, escala, (dx, dy) = letterbox(np.zeros((480, 640, 3), dtype=np.uint8))
        self.assertEqual(imagen.shape, (640, 640, 3))
        self.assertEqual(escala, 1.0)
        self.assertEqual((dx, dy), (0, 80))  # 80 px de relleno arriba y abajo

    def test_error_si_falta_el_modelo(self):
        with mock.patch("detector.yolo.modelo_disponible", return_value=False):
            with self.assertRaises(ModeloNoEncontrado):
                DetectorYOLO()


class DecodificarSalidaTests(SimpleTestCase):
    """Simula la salida cruda de YOLO11/YOLOv8: (1, 84, 8400)."""

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


@unittest.skipUnless(modelo_disponible(), "Falta detector/modelos/yolo11n.onnx")
class ModeloRealTests(SimpleTestCase):
    """Ejecutan YOLO11n de verdad con cv2.dnn."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.detector = DetectorYOLO()

    def test_imagen_negra_no_tiene_objetos(self):
        self.assertEqual(self.detector.detectar(np.zeros((480, 640, 3), dtype=np.uint8), 0.45), [])

    def test_detecta_personas_y_bus_en_imagen_de_referencia(self):
        imagen = cv2.imread(str(IMAGEN_BUS))
        self.assertIsNotNone(imagen, "Falta detector/datos_prueba/bus.jpg")
        nombres = [d["nombre"] for d in self.detector.detectar(imagen, 0.45)]
        self.assertGreaterEqual(nombres.count("persona"), 3)  # la 4.ª persona está cortada en el borde
        self.assertIn("bus", nombres)

    def test_cajas_dentro_de_la_imagen(self):
        imagen = cv2.imread(str(IMAGEN_BUS))
        alto, ancho = imagen.shape[:2]
        for d in self.detector.detectar(imagen, 0.45):
            x, y, w, h = d["caja"]
            self.assertTrue(0 <= x < ancho and 0 <= y < alto and x + w <= ancho + 1 and y + h <= alto + 1, d)
