"""Captura de video en tiempo real con OpenCV y transmisión MJPEG al navegador.

Funcionamiento:
  * Un único hilo lee la cámara con cv2.VideoCapture y guarda el último frame
    ya codificado en JPEG. Así la cámara se abre una sola vez aunque haya
    varias pestañas mirando el video.
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


class Camara:
    """Fuente de video compartida (patrón singleton, ver `camara` al final)."""

    def __init__(self, indice, ancho, alto, espejo=True, calidad=80, apagado_inactivo=15.0):
        self.indice = indice
        self.ancho = ancho
        self.alto = alto
        self.espejo = espejo
        self.calidad = calidad
        self.apagado_inactivo = apagado_inactivo

        self._control = threading.Lock()      # protege iniciar/detener
        self._nuevo_frame = threading.Condition()  # avisa a los clientes
        self._hilo = None
        self._activa = False
        self._jpeg = None
        self._numero_frame = 0
        self._clientes = 0
        self._sin_clientes_desde = None

        self.fps = 0.0
        self.resolucion = (0, 0)
        self.error = ""

    # ------------------------------------------------------------------ control
    @property
    def activa(self):
        return self._activa

    def iniciar(self):
        """Abre la cámara y lanza el hilo de captura. Devuelve True si quedó activa."""
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
            self._hilo = threading.Thread(target=self._bucle, args=(cap,), daemon=True)
            self._hilo.start()
            return True

    def detener(self):
        """Pide al hilo de captura que termine y espera a que libere la cámara."""
        with self._control:
            self._activa = False
            hilo = self._hilo
        if hilo and hilo is not threading.current_thread():
            hilo.join(timeout=3)

    # ---------------------------------------------------------------- captura
    def _bucle(self, cap):
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
                instantaneo = 1.0 / max(ahora - anterior, 1e-6)
                anterior = ahora
                # Media móvil para que el FPS mostrado no salte tanto
                self.fps = instantaneo if self.fps == 0 else 0.9 * self.fps + 0.1 * instantaneo

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

    def procesar(self, frame):
        """Procesamiento de cada frame con OpenCV antes de enviarlo.

        Por ahora: efecto espejo y una marca con fecha/hora y FPS.
        Aquí se conectará la detección de objetos en la siguiente sesión.
        """
        if self.espejo:
            frame = cv2.flip(frame, 1)

        texto = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  |  {self.fps:4.1f} FPS"
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
        return {
            "activa": self._activa,
            "fps": round(self.fps, 1) if self._activa else 0,
            "resolucion": f"{self.resolucion[0]}x{self.resolucion[1]}" if self._activa else "-",
            "clientes": self._clientes,
            "indice": self.indice,
            "error": self.error,
        }


camara = Camara(
    indice=settings.CAMERA_INDEX,
    ancho=settings.CAMERA_ANCHO,
    alto=settings.CAMERA_ALTO,
    espejo=settings.CAMERA_ESPEJO,
    calidad=settings.CAMERA_CALIDAD_JPEG,
    apagado_inactivo=settings.CAMERA_APAGADO_INACTIVO,
)
