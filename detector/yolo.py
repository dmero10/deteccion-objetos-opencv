"""Módulo de detección de objetos con OpenCV.

Se usa el módulo DNN de OpenCV (cv2.dnn) para ejecutar YOLO11n (Ultralytics),
una red neuronal ya entrenada con el dataset COCO (80 clases: personas,
celulares, botellas, sillas, laptops...). El modelo está exportado a ONNX
(detector/modelos/yolo11n.onnx), así que OpenCV lo ejecuta directamente:
no se necesita PyTorch ni TensorFlow. El mismo código sirve para YOLOv8,
que tiene el mismo formato de salida.

Pasos por cada frame (todos con OpenCV):
  1. "Letterbox": redimensionar sin deformar y rellenar hasta 640x640.
  2. cv2.dnn.blobFromImage: normalizar a [0, 1] y pasar de BGR a RGB.
  3. red.forward(): inferencia -> 8400 cajas candidatas con 80 puntajes cada una.
  4. Filtrar por confianza y aplicar NMS por clase (cv2.dnn.NMSBoxesBatched)
     para quedarse con una sola caja por objeto.
"""
import threading
import unicodedata
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings

from .clases import CLASES

TAMANO_ENTRADA = 640  # resolución con la que se entrenó y exportó el modelo

# Colores en BGR (formato de OpenCV), uno por clase de forma estable
PALETA_BGR = [
    (237, 111, 47), (85, 157, 31), (36, 167, 245), (69, 69, 214),
    (188, 71, 171), (193, 172, 0), (67, 112, 255), (66, 179, 124),
    (140, 90, 30), (0, 200, 220), (160, 60, 230), (90, 90, 90),
]


class ModeloNoEncontrado(RuntimeError):
    """Falta el archivo del modelo en detector/modelos/."""


def ruta_modelo(nombre=None):
    nombre = nombre or settings.DETECTOR_MODELO
    return Path(settings.MODELOS_DIR) / f"{nombre}.onnx"


def modelo_disponible(nombre=None):
    ruta = ruta_modelo(nombre)
    return ruta.exists() and ruta.stat().st_size > 0


def color_bgr(clase_id):
    return PALETA_BGR[clase_id % len(PALETA_BGR)]


def color_hex(clase_id):
    """Mismo color que la caja, en formato CSS (#rrggbb) para la interfaz."""
    b, g, r = color_bgr(clase_id)
    return f"#{r:02x}{g:02x}{b:02x}"


def sin_tildes(texto):
    """cv2.putText solo dibuja ASCII: 'avión' -> 'avion', 'señal' -> 'senal'."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def letterbox(frame, tamano=TAMANO_ENTRADA):
    """Escala la imagen para que quepa en tamano x tamano sin deformarla y rellena con gris.

    Devuelve (imagen, escala, (desplazamiento_x, desplazamiento_y)) para poder
    devolver luego las cajas a las coordenadas del frame original.
    """
    alto, ancho = frame.shape[:2]
    escala = min(tamano / alto, tamano / ancho)
    nuevo_ancho, nuevo_alto = round(ancho * escala), round(alto * escala)
    redimensionada = cv2.resize(frame, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_LINEAR)
    dx, dy = (tamano - nuevo_ancho) // 2, (tamano - nuevo_alto) // 2
    lienzo = cv2.copyMakeBorder(
        redimensionada, dy, tamano - nuevo_alto - dy, dx, tamano - nuevo_ancho - dx,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )
    return lienzo, escala, (dx, dy)


def decodificar_salida(salida, confianza, nms, escala, desplazamiento, forma_frame):
    """Convierte la salida cruda de YOLO11/YOLOv8 en detecciones.

    `salida` tiene forma (1, 84, 8400): por cada una de las 8400 cajas candidatas,
    4 valores de caja (centro x, centro y, ancho, alto) + 80 puntajes de clase.
    """
    predicciones = np.squeeze(salida, axis=0)
    if predicciones.shape[0] < predicciones.shape[1]:
        predicciones = predicciones.T  # -> (8400, 84)

    puntajes = predicciones[:, 4:]
    clases = puntajes.argmax(axis=1)
    confianzas = puntajes[np.arange(len(clases)), clases]

    mascara = confianzas >= confianza
    if not mascara.any():
        return []
    cajas_cxcywh = predicciones[mascara, :4]
    clases, confianzas = clases[mascara], confianzas[mascara]

    # Centro/tamaño en la imagen de 640x640 -> esquina/tamaño en el frame original
    dx, dy = desplazamiento
    alto, ancho = forma_frame[:2]
    x = (cajas_cxcywh[:, 0] - cajas_cxcywh[:, 2] / 2 - dx) / escala
    y = (cajas_cxcywh[:, 1] - cajas_cxcywh[:, 3] / 2 - dy) / escala
    w = cajas_cxcywh[:, 2] / escala
    h = cajas_cxcywh[:, 3] / escala
    x, y = np.clip(x, 0, ancho - 1), np.clip(y, 0, alto - 1)
    w, h = np.minimum(w, ancho - x), np.minimum(h, alto - y)
    cajas = np.stack([x, y, w, h], axis=1)

    # NMS separado por clase: una persona no "tapa" al celular que sostiene
    indices = cv2.dnn.NMSBoxesBatched(
        cajas.tolist(), confianzas.tolist(), clases.tolist(), confianza, nms
    )
    resultados = []
    for i in np.array(indices).flatten():
        cid = int(clases[i])
        if not 0 <= cid < len(CLASES):
            continue
        resultados.append({
            "clase": cid,
            "nombre": CLASES[cid][1],
            "confianza": float(confianzas[i]),
            "caja": tuple(int(round(v)) for v in cajas[i]),
        })
    resultados.sort(key=lambda d: -d["confianza"])
    return resultados


class DetectorYOLO:
    """Ejecuta YOLO (ONNX) con cv2.dnn y devuelve los objetos encontrados."""

    def __init__(self, nombre_modelo=None, nms=0.45):
        ruta = ruta_modelo(nombre_modelo)
        if not modelo_disponible(nombre_modelo):
            raise ModeloNoEncontrado(
                f"Falta el modelo {ruta}. Viene en el repositorio; si lo borraste, "
                "recupéralo con 'git checkout -- detector/modelos' o genéralo con "
                "scripts/exportar_modelo.py"
            )
        self.red = cv2.dnn.readNetFromONNX(str(ruta))
        self.red.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.red.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.nombre = ruta.stem
        self.nms = nms
        self._lock = threading.Lock()  # la red de OpenCV no es segura entre hilos

    def detectar(self, frame, confianza=0.45):
        """Devuelve una lista de dicts: {clase, nombre, confianza, caja=(x, y, w, h)}."""
        imagen, escala, desplazamiento = letterbox(frame)
        blob = cv2.dnn.blobFromImage(
            imagen, scalefactor=1 / 255.0, size=(TAMANO_ENTRADA, TAMANO_ENTRADA), swapRB=True
        )
        with self._lock:
            self.red.setInput(blob)
            salida = self.red.forward()
        return decodificar_salida(salida, confianza, self.nms, escala, desplazamiento, frame.shape)


def dibujar_detecciones(frame, detecciones):
    """Dibuja sobre el frame la caja, el nombre y el porcentaje de confianza de cada objeto."""
    alto, ancho = frame.shape[:2]
    fuente, escala, grosor = cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
    for d in detecciones:
        x, y, w, h = d["caja"]
        x, y = max(0, x), max(0, y)
        x2, y2 = min(ancho - 1, x + w), min(alto - 1, y + h)
        color = color_bgr(d["clase"])
        cv2.rectangle(frame, (x, y), (x2, y2), color, 2)

        etiqueta = f'{sin_tildes(d["nombre"])} {d["confianza"]:.0%}'
        (tw, th), base = cv2.getTextSize(etiqueta, fuente, escala, grosor)
        # Si la caja toca el borde superior, la etiqueta va por dentro
        y_fondo = y if y - th - base - 6 >= 0 else y + th + base + 6
        cv2.rectangle(frame, (x, y_fondo - th - base - 6), (x + tw + 8, y_fondo), color, -1)
        cv2.putText(frame, etiqueta, (x + 4, y_fondo - base - 3), fuente, escala,
                    (255, 255, 255), grosor, cv2.LINE_AA)
    return frame


def resumir(detecciones):
    """Agrupa por objeto: [{nombre, cantidad, confianza (máxima), color}], de más a menos."""
    grupos = {}
    for d in detecciones:
        g = grupos.setdefault(d["clase"], {
            "nombre": d["nombre"], "cantidad": 0, "confianza": 0.0, "color": color_hex(d["clase"]),
        })
        g["cantidad"] += 1
        g["confianza"] = max(g["confianza"], round(d["confianza"], 2))
    return sorted(grupos.values(), key=lambda g: (-g["cantidad"], g["nombre"]))


_detector = None
_lock_carga = threading.Lock()


def obtener_detector():
    """Carga el modelo una sola vez y lo reutiliza (singleton)."""
    global _detector
    with _lock_carga:
        if _detector is None:
            _detector = DetectorYOLO(nms=settings.DETECTOR_NMS)
        return _detector
