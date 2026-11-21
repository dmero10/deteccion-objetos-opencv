"""UNITARIAS: lógica del registrador (registro.py) con la base de datos simulada.

La versión que guarda de verdad en PostgreSQL está en integracion/test_registro_bd.py.
"""
import itertools
from types import SimpleNamespace
from unittest import mock

from django.db import DatabaseError
from django.test import SimpleTestCase
from django.utils import timezone

from detector.registro import LADO_MAXIMO_RECORTE, Registrador, recortar

from ..utiles import DetectorFalso, frame_negro, frame_ruido


class RecortarTests(SimpleTestCase):
    def test_recorta_con_margen_y_reduce(self):
        recorte = recortar(frame_ruido(), (50, 40, 200, 300))
        self.assertLessEqual(max(recorte.shape[:2]), LADO_MAXIMO_RECORTE)
        self.assertGreater(recorte.shape[0], recorte.shape[1], "La forma de la caja se conserva")

    def test_caja_pequena_no_se_agranda(self):
        recorte = recortar(frame_ruido(), (100, 100, 40, 30))
        # 12 % de margen por lado: 40 -> 40 + 2*4 = 48 ; 30 -> 30 + 2*3 = 36
        self.assertEqual(recorte.shape[:2], (36, 48))

    def test_caja_en_el_borde_se_ajusta_al_frame(self):
        recorte = recortar(frame_ruido(), (-20, -20, 100, 100))
        self.assertIsNotNone(recorte)
        self.assertLessEqual(recorte.shape[0], 480)

    def test_caja_fuera_del_frame(self):
        self.assertIsNone(recortar(frame_negro(), (700, 500, 10, 10)))


class BaseDeDatosFalsa:
    """Reemplaza a Avistamiento.objects: guarda en una lista lo que se "crea"."""

    def __init__(self, clases_existentes=()):
        self.creados = []
        self.existentes = list(clases_existentes)
        self._ids = itertools.count(1)

    def values_list(self, *args, **kwargs):
        return mock.Mock(distinct=mock.Mock(return_value=self.existentes))

    def create(self, **campos):
        obj = SimpleNamespace(pk=next(self._ids), fecha=timezone.now(), **campos)
        self.creados.append(obj)
        return obj


class RegistradorTests(SimpleTestCase):
    def setUp(self):
        self.bd = BaseDeDatosFalsa()
        parche = mock.patch("detector.registro.Avistamiento", objects=self.bd)
        parche.start()
        self.addCleanup(parche.stop)
        self.registrador = Registrador(intervalo=15)
        self.detecciones = DetectorFalso().detectar(None, 0.5)  # 1 persona + 2 tazas

    def registrar(self, detecciones=None, instante=100.0):
        with mock.patch("detector.registro.time.monotonic", return_value=instante):
            return self.registrador.registrar(frame_ruido(), self.detecciones if detecciones is None else detecciones)

    def test_un_registro_por_clase_con_la_caja_mas_confiable(self):
        self.registrar()
        self.assertEqual(len(self.bd.creados), 2)
        taza = next(a for a in self.bd.creados if a.clase == 41)
        self.assertEqual(taza.cantidad, 2)
        self.assertAlmostEqual(taza.confianza, 0.72, places=4)
        self.assertEqual((taza.x, taza.y, taza.ancho, taza.alto), (500, 310, 60, 70))
        self.assertTrue(bytes(taza.imagen).startswith(b"\xff\xd8"), "El recorte se guarda en JPEG")

    def test_no_repite_la_misma_clase_dentro_del_intervalo(self):
        self.registrar(instante=100.0)
        self.assertEqual(self.registrar(instante=114.9), [])
        self.assertEqual(len(self.bd.creados), 2)

    def test_vuelve_a_registrar_cuando_pasa_el_intervalo(self):
        self.registrar(instante=100.0)
        self.assertEqual(len(self.registrar(instante=115.0)), 2)

    def test_cada_clase_tiene_su_propio_intervalo(self):
        self.registrar(self.detecciones[:1], instante=100.0)  # solo persona
        eventos = self.registrar(instante=101.0)
        self.assertEqual([e["nombre"] for e in eventos], ["taza"])

    def test_marca_nuevo_solo_lo_que_no_estaba_descubierto(self):
        self.bd.existentes = [0]  # "persona" ya estaba en la BD
        eventos = {e["nombre"]: e for e in self.registrar()}
        self.assertFalse(eventos["persona"]["nuevo"])
        self.assertTrue(eventos["taza"]["nuevo"])
        self.assertEqual(self.registrador.descubiertas(), {0, 41})

    def test_evento_trae_lo_que_necesita_la_interfaz(self):
        evento = self.registrar()[0]
        for clave in ("id", "clase", "nombre", "confianza", "cantidad", "hora", "imagen", "color", "nuevo"):
            self.assertIn(clave, evento)
        self.assertRegex(evento["hora"], r"^\d{2}:\d{2}:\d{2}$")
        self.assertRegex(evento["color"], r"^#[0-9a-f]{6}$")

    def test_recientes_guarda_los_ultimos_primero(self):
        registrador = Registrador(intervalo=0, recientes=3)
        self.registrador = registrador
        for i in range(5):
            self.registrar(self.detecciones[:1], instante=100.0 + i)
        ids = [e["id"] for e in registrador.recientes()]
        self.assertEqual(ids, [5, 4, 3], "Solo los 3 más recientes, del último al primero")

    def test_sin_detecciones_o_desactivado_no_guarda(self):
        self.assertEqual(self.registrar([]), [])
        self.registrador.activo = False
        self.assertEqual(self.registrar(), [])
        self.assertEqual(self.bd.creados, [])

    def test_error_de_base_de_datos_no_detiene_la_deteccion(self):
        self.bd.create = mock.Mock(side_effect=DatabaseError("sin conexión"))
        with self.assertLogs("detector.registro", level="ERROR"):
            self.assertEqual(self.registrar(), [])
        self.assertIn("sin conexión", self.registrador.error)

    def test_tras_un_error_se_puede_reintentar(self):
        self.bd.create = mock.Mock(side_effect=DatabaseError("sin conexión"))
        with self.assertLogs("detector.registro", level="ERROR"):
            self.registrar(instante=100.0)
        self.bd.create = BaseDeDatosFalsa().create
        self.assertEqual(len(self.registrar(instante=100.5)), 2, "El intervalo no cuenta si no se guardó")
        self.assertEqual(self.registrador.error, "")

    def test_reiniciar_olvida_intervalos_y_recientes(self):
        self.registrar(instante=100.0)
        self.registrador.reiniciar()
        self.assertEqual(self.registrador.recientes(), [])
        self.assertEqual(len(self.registrar(instante=101.0)), 2)
