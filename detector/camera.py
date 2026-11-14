"""Captura de video en tiempo real con OpenCV y transmisión MJPEG al navegador.

Funcionamiento (dos hilos):
  * Hilo de captura: lee la cámara con cv2.VideoCapture, dibuja las últimas
    detecciones sobre cada frame y lo guarda codificado en JPEG. La cámara se
    abre una sola vez aunque haya varias pestañas mirando el video.
  * Hilo de detección: toma el frame más reciente, ejecuta YOLO (yolo.py) y
    publica los resultados. Como la red tarda ~100 ms por imagen, separarla
    evita que el video se vuelva lento: el video va a la velocidad de la
    cámara y las cajas se actualizan tan rápido como lo permita el modelo.
  * Cada cliente recibe un flujo "multipart/x-mixed-replace" (MJPEG): una
    secuencia de imágenes JPEG que el navegador muestra en una etiqueta <img>.
  * Si nadie mira el video durante CAMERA_APAGADO_INACTIVO segundos, la
    cámara se libera sola.
"""
import platform
import threading
import time

import cv2
from django.conf import settings

from .yolo import ModeloNoEncontrado, dibujar_detecciones, obtener_detector, resumir


def _media_movil(anterior, nuevo):
    return nuevo if anterior == 0 else 0.9 * anterior + 0.1 * nuevo


class Camara:
    """Fuente de video compartida (patrón singleton, ver `camara` al final)."""

    def __init__(self, indice, ancho, alto, espejo=True, calidad=80, apagado_inactivo=15.0,
                 deteccion_activa=True, confianza=0.45):
        self.indice = indice
        self.ancho = ancho
        self.alto = alto
        self.espejo = espejo
        self.calidad = calidad
        self.apagado_inactivo = apagado_inactivo

        self._control = threading.Lock()           # protege iniciar/detener
        self._nuevo_frame = threading.Condition()  # avisa a los clientes
        self._hilo = None
        self._hilo_deteccion = None
        self._activa = False
        self._jpeg = None
        self._numero_frame = 0
        self._clientes = 0
        self._sin_clientes_desde = None

        self.fps = 0.0
        self.resolucion = (0, 0)
        self.error = ""

        # Detección de objetos
        self.deteccion_activa = deteccion_activa
        self.confianza = confianza
        self.inferencia_ms = 0.0
        self.fps_deteccion = 0.0
        self.detector_error = ""
        self._detector = None
        self._carga_fallida = False
        self._pendiente = None                    # último frame a la espera de ser analizado
        self._hay_pendiente = threading.Event()
        self._detecciones = []
        self._resumen = []

    # ------------------------------------------------------------------ control
    @property
    def activa(self):
        return self._activa

    def iniciar(self):
        """Abre la cámara y lanza los hilos de captura y detección. True si quedó activa."""
        with self._control:
            if self._activa:
                return True
            # En Windows, DirectShow abre la webcam mucho más rápido que MSMF.
            backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.indice, backend)
            if not cap.isOpened():
                cap.release()
                self.error = (
                    f"No se pudo abrir la cámara {self.indice}. Ciérrala en otras "
                    "aplicaciones o cambia CAMERA_INDEX en el archivo .env."
                )
                return False

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto)
            self.resolucion = (
                int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
            self.error = ""
            self.fps = 0.0
            self._sin_clientes_desde = time.monotonic()
            self._activa = True
            self._hilo = threading.Thread(target=self._bucle_captura, args=(cap,), daemon=True)
            self._hilo_deteccion = threading.Thread(target=self._bucle_deteccion, daemon=True)
            self._hilo.start()
            self._hilo_deteccion.start()
            return True

    def detener(self):
        """Pide a los hilos que terminen y espera a que liberen la cámara."""
        with self._control:
            self._activa = False
            hilos = (self._hilo, self._hilo_deteccion)
        self._hay_pendiente.set()  # despierta al hilo de detección para que salga
        for hilo in hilos:
            if hilo and hilo is not threading.current_thread():
                hilo.join(timeout=3)

    # ---------------------------------------------------------------- captura
    def _bucle_captura(self, cap):
        anterior = time.perf_counter()
        fallos = 0
        try:
            while self._activa:
                ok, frame = cap.read()
                if not ok:
                    fallos += 1
                    if fallos >= 30:
                        self.error = "La cámara dejó de enviar imágenes."
                        break
                    time.sleep(0.05)
                    continue
                fallos = 0

                ahora = time.perf_counter()
                self.fps = _media_movil(self.fps, 1.0 / max(ahora - anterior, 1e-6))
                anterior = ahora

                frame = self.procesar(frame)
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.calidad])
                if ok:
                    with self._nuevo_frame:
                        self._jpeg = jpg.tobytes()
                        self._numero_frame += 1
                        self._nuevo_frame.notify_all()

                if self._sin_espectadores():
                    break
        finally:
            cap.release()
            self._activa = False
            self._hay_pendiente.set()
            self._limpiar_resultados()
            with self._nuevo_frame:
                self._jpeg = None
                self._nuevo_frame.notify_all()

    def _sin_espectadores(self):
        """True si lleva demasiado tiempo sin nadie mirando el video."""
        if self._clientes > 0:
            self._sin_clientes_desde = None
            return False
        if self._sin_clientes_desde is None:
            self._sin_clientes_desde = time.monotonic()
        return time.monotonic() - self._sin_clientes_desde > self.apagado_inactivo

    # ------------------------------------------------------------ detección
    def configurar_deteccion(self, activa=None, confianza=None):
        """Cambia la detección en vivo, sin reiniciar el video."""
        if confianza is not None:
            self.confianza = min(max(float(confianza), 0.05), 0.95)
        if activa is not None:
            self.deteccion_activa = bool(activa)
            if self.deteccion_activa and self._carga_fallida:
                # Permite reintentar si el modelo se agregó después
                self._carga_fallida, self.detector_error = False, ""
            if not self.deteccion_activa:
                self._limpiar_resultados()

    def _limpiar_resultados(self):
        self._detecciones, self._resumen = [], []
        self.inferencia_ms = self.fps_deteccion = 0.0

    def _obtener_detector(self):
        if self._detector is None and not self._carga_fallida:
            try:
                self._detector = obtener_detector()
                self.detector_error = ""
            except (ModeloNoEncontrado, cv2.error) as exc:
                self._carga_fallida = True
                self.detector_error = str(exc)
        return self._detector

    def _bucle_deteccion(self):
        """Analiza siempre el frame más reciente; los intermedios se descartan."""
        anterior = None
        while self._activa:
            if not self._hay_pendiente.wait(timeout=0.5):
                continue
            self._hay_pendiente.clear()
            frame, self._pendiente = self._pendiente, None
            if frame is None or not self._activa:
                continue
            if self._detectar(frame):
                ahora = time.perf_counter()
                if anterior is not None:
                    self.fps_deteccion = _media_movil(self.fps_deteccion, 1.0 / max(ahora - anterior, 1e-6))
                anterior = ahora

    def _detectar(self, frame):
        """Ejecuta YOLO sobre un frame y publica los resultados. Devuelve True si se ejecutó."""
        detector = self._obtener_detector() if self.deteccion_activa else None
        if detector is None:
            return False
        inicio = time.perf_counter()
        detecciones = detector.detectar(frame, self.confianza)
        if not self.deteccion_activa:
            return False  # se desactivó mientras se procesaba este frame
        self.inferencia_ms = _media_movil(self.inferencia_ms, (time.perf_counter() - inicio) * 1000)
        self._detecciones = detecciones
        self._resumen = resumir(detecciones)
        return True

    # -------------------------------------------------------- procesamiento
    def procesar(self, frame):
        """Procesamiento de cada frame con OpenCV antes de enviarlo:
        espejo -> enviar al detector -> dibujar las últimas detecciones -> barra de información.
        """
        if self.espejo:
            frame = cv2.flip(frame, 1)

        detecciones = []
        if self.deteccion_activa:
            self._pendiente = frame.copy()  # el detector toma el más reciente
            self._hay_pendiente.set()
            detecciones = self._detecciones
            dibujar_detecciones(frame, detecciones)

        texto = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  |  {self.fps:4.1f} FPS"
        if self.deteccion_activa and self._detector is not None:
            texto += f"  |  {len(detecciones)} objeto(s)"
        fuente, escala, grosor = cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
        (tw, th), base = cv2.getTextSize(texto, fuente, escala, grosor)
        cv2.rectangle(frame, (8, 8), (8 + tw + 12, 8 + th + base + 10), (0, 0, 0), -1)
        cv2.putText(frame, texto, (14, 8 + th + 5), fuente, escala, (255, 255, 255), grosor, cv2.LINE_AA)
        return frame

    # ---------------------------------------------------------------- salida
    def frames_mjpeg(self):
        """Generador para StreamingHttpResponse: entrega cada frame nuevo como parte MJPEG."""
        if not self.iniciar():
            return
        with self._nuevo_frame:
            self._clientes += 1
        ultimo = -1
        try:
            while True:
                with self._nuevo_frame:
                    self._nuevo_frame.wait_for(
                        lambda: self._numero_frame != ultimo or not self._activa, timeout=2
                    )
                    if not self._activa:
                        break
                    if self._numero_frame == ultimo or self._jpeg is None:
                        continue
                    jpg, ultimo = self._jpeg, self._numero_frame
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
                )
        finally:
            with self._nuevo_frame:
                self._clientes -= 1

    def foto(self):
        """Devuelve el último frame en JPEG (bytes) o None si la cámara está apagada."""
        with self._nuevo_frame:
            return self._jpeg if self._activa else None

    def estado(self):
        detectando = self._activa and self.deteccion_activa
        return {
            "activa": self._activa,
            "fps": round(self.fps, 1) if self._activa else 0,
            "resolucion": f"{self.resolucion[0]}x{self.resolucion[1]}" if self._activa else "-",
            "clientes": self._clientes,
            "indice": self.indice,
            "error": self.error,
            "deteccion": {
                "activa": self.deteccion_activa,
                "modelo": settings.DETECTOR_MODELO,
                "confianza": round(self.confianza, 2),
                "inferencia_ms": round(self.inferencia_ms, 1) if detectando else 0,
                "fps": round(self.fps_deteccion, 1) if detectando else 0,
                "total": len(self._detecciones) if detectando else 0,
                "objetos": self._resumen if detectando else [],
                "error": self.detector_error,
            },
        }


camara = Camara(
    indice=settings.CAMERA_INDEX,
    ancho=settings.CAMERA_ANCHO,
    alto=settings.CAMERA_ALTO,
    espejo=settings.CAMERA_ESPEJO,
    calidad=settings.CAMERA_CALIDAD_JPEG,
    apagado_inactivo=settings.CAMERA_APAGADO_INACTIVO,
    deteccion_activa=settings.DETECTOR_ACTIVO,
    confianza=settings.DETECTOR_CONFIANZA,
)
