"""Dobles de prueba compartidos: cámara y detector simulados (no hace falta hardware)."""
import numpy as np

from detector.camera import Camara


class CapturaFalsa:
    """Imita a cv2.VideoCapture devolviendo frames negros de 640x480."""

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


def frame_negro():
    return np.zeros((480, 640, 3), dtype=np.uint8)


def frame_ruido(semilla=0):
    """Frame con contenido (para que los recortes JPEG no sean triviales)."""
    return np.random.default_rng(semilla).integers(0, 255, (480, 640, 3), dtype=np.uint8)


def camara_de_prueba(**kwargs):
    kwargs.setdefault("apagado_inactivo", 60)
    return Camara(indice=0, ancho=640, alto=480, **kwargs)


def camara_encendida(**kwargs):
    """Cámara marcada como activa sin abrir hardware: se le pasan frames a mano."""
    camara = camara_de_prueba(**kwargs)
    camara._activa = True
    return camara
