"""UNITARIAS: funciones de apoyo de las vistas y filtros de plantilla, sin base de datos."""
from unittest import mock

import cv2
import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from detector.templatetags.lince import entero_pct, porcentaje
from detector.views import LADO_MAXIMO_ANALISIS, _analizar_archivo
from detector.yolo import ModeloNoEncontrado

from ..utiles import DetectorFalso


def imagen_subida(ancho=640, alto=480, formato=".jpg", nombre="foto.jpg"):
    ok, datos = cv2.imencode(formato, np.full((alto, ancho, 3), 200, dtype=np.uint8))
    assert ok
    return SimpleUploadedFile(nombre, datos.tobytes())


class FiltrosPlantillaTests(SimpleTestCase):
    def test_porcentaje(self):
        self.assertEqual(porcentaje(0.913), "91%")
        self.assertEqual(porcentaje(1), "100%")
        self.assertEqual(porcentaje(0), "0%")

    def test_porcentaje_con_valor_invalido(self):
        self.assertEqual(porcentaje(None), "")
        self.assertEqual(porcentaje("abc"), "")

    def test_entero_pct(self):
        self.assertEqual(entero_pct(0.456), 46)
        self.assertEqual(entero_pct(None), 0)


@mock.patch("detector.views.obtener_detector", return_value=DetectorFalso())
class AnalizarArchivoTests(SimpleTestCase):
    def test_devuelve_imagen_marcada_y_resumen(self, _):
        resultado, error = _analizar_archivo(imagen_subida(), 0.45)
        self.assertIsNone(error)
        self.assertEqual(resultado["total"], 3)
        self.assertEqual(resultado["dimensiones"], "640×480")
        self.assertEqual([o["nombre"] for o in resultado["objetos"]], ["taza", "persona"])
        self.assertTrue(resultado["imagen"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(resultado["detecciones"][0]["porcentaje"], 91)

    def test_acepta_png(self, _):
        resultado, error = _analizar_archivo(imagen_subida(formato=".png", nombre="foto.png"), 0.45)
        self.assertIsNone(error)

    def test_reduce_las_imagenes_grandes_antes_de_detectar(self, detector):
        espia = mock.Mock(wraps=DetectorFalso())
        detector.return_value = espia
        _analizar_archivo(imagen_subida(ancho=4000, alto=3000), 0.45)
        frame = espia.detectar.call_args.args[0]
        self.assertEqual(max(frame.shape[:2]), LADO_MAXIMO_ANALISIS)

    def test_pasa_la_confianza_al_detector(self, detector):
        espia = mock.Mock(wraps=DetectorFalso())
        detector.return_value = espia
        _analizar_archivo(imagen_subida(), 0.8)
        self.assertEqual(espia.detectar.call_args.args[1], 0.8)

    def test_archivo_que_no_es_imagen(self, _):
        resultado, error = _analizar_archivo(SimpleUploadedFile("notas.txt", b"hola"), 0.45)
        self.assertIsNone(resultado)
        self.assertIn("no es una imagen válida", error)

    def test_archivo_vacio(self, _):
        resultado, error = _analizar_archivo(SimpleUploadedFile("vacio.jpg", b""), 0.45)
        self.assertIsNone(resultado)
        self.assertIn("no es una imagen válida", error)

    @override_settings(ANALIZAR_MAX_MB=0.001)
    def test_archivo_demasiado_grande(self, _):
        resultado, error = _analizar_archivo(imagen_subida(ancho=800, alto=800), 0.45)
        self.assertIsNone(resultado)
        self.assertIn("pesa más de", error)

    def test_sin_modelo(self, detector):
        detector.side_effect = ModeloNoEncontrado("Falta el modelo")
        resultado, error = _analizar_archivo(imagen_subida(), 0.45)
        self.assertIsNone(resultado)
        self.assertEqual(error, "Falta el modelo")
