"""Captura de video, hilos y transmisión MJPEG (Sesión 1) + integración con la detección (Sesión 2)."""
import time
from unittest import mock

from django.test import SimpleTestCase

from detector.yolo import ModeloNoEncontrado

from .utiles import (CapturaFalsa, DetectorFalso, camara_de_prueba, camara_encendida,
                     frame_negro)


class CapturaTests(SimpleTestCase):
    def setUp(self):
        self.camara = camara_de_prueba(deteccion_activa=False)

    def tearDown(self):
        self.camara.detener()

    def test_procesar_mantiene_tamano_y_dibuja_barra(self):
        salida = self.camara.procesar(frame_negro())
        self.assertEqual(salida.shape, (480, 640, 3))
        self.assertTrue(salida.any(), "Debe dibujar la barra de fecha/FPS sobre el frame")

    @mock.patch("detector.camera.cv2.VideoCapture", CapturaFalsa)
    def test_stream_entrega_partes_jpeg(self):
        self.assertTrue(self.camara.iniciar())
        parte = next(self.camara.frames_mjpeg())
        self.assertTrue(parte.startswith(b"--frame\r\nContent-Type: image/jpeg"))
        self.assertIn(b"\xff\xd8", parte)  # marca de inicio de un JPEG
        self.assertEqual(self.camara.estado()["resolucion"], "640x480")

    @mock.patch("detector.camera.cv2.VideoCapture", CapturaFalsa)
    def test_iniciar_dos_veces_no_abre_otra_camara(self):
        self.assertTrue(self.camara.iniciar())
        hilo = self.camara._hilo
        self.assertTrue(self.camara.iniciar())
        self.assertIs(self.camara._hilo, hilo)

    @mock.patch("detector.camera.cv2.VideoCapture")
    def test_error_si_la_camara_no_abre(self, video_capture):
        video_capture.return_value.isOpened.return_value = False
        self.assertFalse(self.camara.iniciar())
        self.assertIn("No se pudo abrir la cámara", self.camara.estado()["error"])

    @mock.patch("detector.camera.cv2.VideoCapture", CapturaFalsa)
    def test_se_apaga_sola_sin_espectadores(self):
        camara = camara_de_prueba(deteccion_activa=False, apagado_inactivo=0.2)
        self.assertTrue(camara.iniciar())
        for _ in range(60):
            if not camara.activa:
                break
            time.sleep(0.05)
        self.assertFalse(camara.activa, "La cámara debe liberarse si nadie mira el video")


class DeteccionEnCamaraTests(SimpleTestCase):
    """El hilo de detección llama a _detectar(); aquí se llama directamente."""

    def test_detectar_publica_resultados(self):
        camara = camara_encendida()
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            self.assertTrue(camara._detectar(frame_negro()))
        d = camara.estado()["deteccion"]
        self.assertEqual(d["total"], 3)
        self.assertEqual(d["objetos"][0]["nombre"], "taza")

    def test_procesar_dibuja_ultimas_detecciones_y_encola_frame_limpio(self):
        camara = camara_encendida(espejo=False)
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            camara._detectar(frame_negro())
        salida = camara.procesar(frame_negro())
        self.assertTrue(salida[200, 50].any(), "Debe dibujar el borde izquierdo de la caja de la persona")
        self.assertIsNotNone(camara._pendiente, "El frame queda listo para el hilo de detección")
        self.assertFalse(camara._pendiente.any(), "Al detector se le envía el frame sin cajas")

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

    def test_desactivar_durante_la_inferencia(self):
        """Si se apaga la detección mientras un frame se procesa, ese frame no reescribe resultados."""
        camara = camara_encendida()

        class DetectorQueSeApaga(DetectorFalso):
            def detectar(self, frame, confianza):
                camara.configurar_deteccion(activa=False)  # el usuario lo apaga "a mitad"
                return super().detectar(frame, confianza)

        with mock.patch("detector.camera.obtener_detector", return_value=DetectorQueSeApaga()):
            self.assertFalse(camara._detectar(frame_negro()))
        self.assertEqual(camara.estado()["deteccion"]["objetos"], [])

    def test_confianza_se_limita_entre_5_y_95(self):
        camara = camara_de_prueba()
        camara.configurar_deteccion(confianza=5)
        self.assertEqual(camara.confianza, 0.95)
        camara.configurar_deteccion(confianza=-1)
        self.assertEqual(camara.confianza, 0.05)

    def test_detectar_pasa_resultados_al_registrador(self):
        registrador = mock.Mock()
        camara = camara_encendida(registrador=registrador)
        frame = frame_negro()
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            camara._detectar(frame)
        registrador.registrar.assert_called_once()
        self.assertIs(registrador.registrar.call_args.args[0], frame)
        self.assertEqual(len(registrador.registrar.call_args.args[1]), 3)

    def test_configurar_registro(self):
        registrador = mock.Mock(activo=True)
        camara = camara_de_prueba(registrador=registrador)
        camara.configurar_deteccion(registrar=False)
        self.assertFalse(registrador.activo)

    @mock.patch("detector.camera.cv2.VideoCapture", CapturaFalsa)
    def test_hilos_de_captura_y_deteccion(self):
        camara = camara_de_prueba()
        with mock.patch("detector.camera.obtener_detector", return_value=DetectorFalso()):
            self.assertTrue(camara.iniciar())
            try:
                for _ in range(50):  # hasta 2.5 s para que el hilo de detección publique
                    if camara.estado()["deteccion"]["total"]:
                        break
                    time.sleep(0.05)
                self.assertEqual(camara.estado()["deteccion"]["total"], 3)
            finally:
                camara.detener()
        self.assertFalse(camara.activa)
        self.assertFalse(camara._hilo_deteccion.is_alive())
