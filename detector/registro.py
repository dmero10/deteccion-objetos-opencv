"""Registro de avistamientos en PostgreSQL.

El hilo de detección analiza ~8 frames por segundo; guardar todos llenaría la
base de datos de duplicados. Por eso, por cada clase se guarda como máximo un
avistamiento cada `intervalo` segundos, con:
  * la caja de mayor confianza de esa clase y un recorte JPEG del objeto,
  * cuántos objetos de esa clase había en el frame.

Además se lleva la cuenta de qué clases ya fueron "descubiertas" (álbum) y una
lista en memoria de los últimos avistamientos para la tira de la interfaz.
"""
import logging
import threading
import time
from collections import deque

import cv2
from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone

from .models import Avistamiento
from .yolo import color_hex

log = logging.getLogger(__name__)

LADO_MAXIMO_RECORTE = 320


def recortar(frame, caja, margen=0.12):
    """Recorta el objeto con un pequeño margen y lo reduce a LADO_MAXIMO_RECORTE px."""
    alto, ancho = frame.shape[:2]
    x, y, w, h = caja
    mx, my = int(w * margen), int(h * margen)
    x1, y1 = max(0, x - mx), max(0, y - my)
    x2, y2 = min(ancho, x + w + mx), min(alto, y + h + my)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    recorte = frame[y1:y2, x1:x2]
    escala = LADO_MAXIMO_RECORTE / max(recorte.shape[:2])
    if escala < 1:
        recorte = cv2.resize(recorte, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return recorte


class Registrador:
    def __init__(self, intervalo=15.0, activo=True, recientes=14):
        self.intervalo = intervalo
        self.activo = activo
        self.error = ""
        self._ultimo = {}            # clase -> instante del último guardado
        self._recientes = deque(maxlen=recientes)
        self._descubiertas = None    # set de clases con al menos un avistamiento (carga perezosa)
        self._lock = threading.Lock()

    # ----------------------------------------------------------- consultas
    def descubiertas(self):
        with self._lock:
            if self._descubiertas is None:
                try:
                    self._descubiertas = set(
                        Avistamiento.objects.values_list("clase", flat=True).distinct()
                    )
                except DatabaseError as exc:
                    self.error = f"No se pudo leer la base de datos: {exc}"
                    return set()
            return set(self._descubiertas)

    def recientes(self):
        with self._lock:
            return list(self._recientes)

    def reiniciar(self):
        """Olvida el estado en memoria (por ejemplo, tras vaciar la bitácora)."""
        with self._lock:
            self._ultimo.clear()
            self._recientes.clear()
            self._descubiertas = None

    # ------------------------------------------------------------ registro
    def registrar(self, frame, detecciones):
        """Guarda los avistamientos que correspondan. Devuelve la lista de eventos creados."""
        if not self.activo or not detecciones:
            return []

        # La mejor caja y la cantidad de objetos por clase
        por_clase = {}
        for d in detecciones:
            actual = por_clase.get(d["clase"])
            if actual is None:
                por_clase[d["clase"]] = [d, 1]
            else:
                actual[1] += 1
                if d["confianza"] > actual[0]["confianza"]:
                    actual[0] = d

        ahora = time.monotonic()
        descubiertas = self.descubiertas()
        eventos = []
        for clase, (mejor, cantidad) in por_clase.items():
            if ahora - self._ultimo.get(clase, float("-inf")) < self.intervalo:
                continue
            recorte = recortar(frame, mejor["caja"])
            if recorte is None:
                continue
            ok, jpg = cv2.imencode(".jpg", recorte, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                continue
            x, y, w, h = mejor["caja"]
            try:
                avistamiento = Avistamiento.objects.create(
                    clase=clase, nombre=mejor["nombre"], confianza=round(mejor["confianza"], 4),
                    cantidad=cantidad, x=max(0, x), y=max(0, y), ancho=max(0, w), alto=max(0, h),
                    imagen=jpg.tobytes(),
                )
            except DatabaseError as exc:
                self.error = f"No se pudo guardar en la base de datos: {exc}"
                log.exception("Error al guardar un avistamiento")
                return eventos
            self.error = ""
            self._ultimo[clase] = ahora

            evento = {
                "id": avistamiento.pk,
                "clase": clase,
                "nombre": avistamiento.nombre,
                "confianza": round(avistamiento.confianza, 2),
                "cantidad": cantidad,
                "hora": timezone.localtime(avistamiento.fecha).strftime("%H:%M:%S"),
                "imagen": reverse("detector:imagen_avistamiento", args=[avistamiento.pk]),
                "color": color_hex(clase),
                "nuevo": clase not in descubiertas,
            }
            with self._lock:
                if self._descubiertas is not None:
                    self._descubiertas.add(clase)
                self._recientes.appendleft(evento)
            descubiertas.add(clase)
            eventos.append(evento)
        return eventos
