import base64
import csv
import json
import time

import cv2
import numpy as np
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, OuterRef, Subquery
from django.db.models.functions import ExtractHour
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .camera import camara
from .clases import CATEGORIAS, CLASES
from .models import Avistamiento
from .yolo import ModeloNoEncontrado, color_hex, dibujar_detecciones, obtener_detector, resumir


# ------------------------------------------------------------- Observatorio
def index(request):
    """Página principal: video en vivo, objetos en escena y últimos avistamientos."""
    return render(request, "detector/index.html", {"estado": camara.estado()})


@never_cache
@require_GET
def video_feed(request):
    """Flujo MJPEG que el navegador muestra dentro de un <img>."""
    if not camara.iniciar():
        return HttpResponse(camara.error, status=503, content_type="text/plain; charset=utf-8")
    return StreamingHttpResponse(
        camara.frames_mjpeg(), content_type="multipart/x-mixed-replace; boundary=frame"
    )


@never_cache
@require_GET
def api_estado(request):
    return JsonResponse(camara.estado())


@require_POST
def api_iniciar(request):
    ok = camara.iniciar()
    return JsonResponse(camara.estado(), status=200 if ok else 503)


@require_POST
def api_detener(request):
    camara.detener()
    return JsonResponse(camara.estado())


@require_POST
def api_configurar_deteccion(request):
    """Recibe {"activa": bool, "confianza": 0-1, "registrar": bool} y lo aplica en vivo."""
    try:
        datos = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    if not isinstance(datos, dict):
        return JsonResponse({"error": "Se esperaba un objeto JSON"}, status=400)

    for campo in ("activa", "registrar"):
        if datos.get(campo) is not None and not isinstance(datos[campo], bool):
            return JsonResponse({"error": f"'{campo}' debe ser true o false"}, status=400)
    confianza = datos.get("confianza")
    if confianza is not None and (isinstance(confianza, bool) or not isinstance(confianza, (int, float))):
        return JsonResponse({"error": "'confianza' debe ser un número entre 0 y 1"}, status=400)

    camara.configurar_deteccion(
        activa=datos.get("activa"), confianza=confianza, registrar=datos.get("registrar")
    )
    return JsonResponse(camara.estado())


@never_cache
@require_GET
def foto(request):
    """Descarga el frame actual como imagen JPEG."""
    jpg = camara.foto()
    if jpg is None:
        return HttpResponse("La cámara está apagada.", status=409, content_type="text/plain; charset=utf-8")
    respuesta = HttpResponse(jpg, content_type="image/jpeg")
    respuesta["Content-Disposition"] = f'attachment; filename="captura_{time.strftime("%Y%m%d_%H%M%S")}.jpg"'
    return respuesta


# -------------------------------------------------------------------- Álbum
def _subconsulta_mejor_foto():
    return Subquery(
        Avistamiento.objects.filter(clase=OuterRef("clase"))
        .order_by("-confianza", "-fecha").values("id")[:1]
    )


def album(request):
    """Las 80 clases de COCO como un álbum: cada una se "descubre" al detectarla."""
    estadisticas = {
        fila["clase"]: fila
        for fila in Avistamiento.objects.values("clase").annotate(
            total=Count("id"), mejor=Max("confianza"), primera=Min("fecha"),
            ultima=Max("fecha"), foto=_subconsulta_mejor_foto(),
        )
    }
    secciones = []
    for nombre_categoria, inicio, fin in CATEGORIAS:
        casillas = []
        for clase in range(inicio, fin + 1):
            datos = estadisticas.get(clase)
            casillas.append({
                "clase": clase,
                "numero": f"{clase + 1:02d}",
                "nombre": CLASES[clase][1],
                "ingles": CLASES[clase][0],
                "color": color_hex(clase),
                "descubierta": datos is not None,
                "datos": datos,
            })
        secciones.append({
            "nombre": nombre_categoria,
            "casillas": casillas,
            "descubiertas": sum(c["descubierta"] for c in casillas),
        })
    descubiertas = len(estadisticas)
    return render(request, "detector/album.html", {
        "secciones": secciones,
        "descubiertas": descubiertas,
        "total_clases": len(CLASES),
        "porcentaje": round(descubiertas * 100 / len(CLASES)),
        "marcas": [clase in estadisticas for clase in range(len(CLASES))],
    })


# ----------------------------------------------------------------- Bitácora
def _filtrar(request):
    """Aplica los filtros de la URL (objeto, desde, hasta) a los avistamientos."""
    qs = Avistamiento.objects.defer("imagen")
    filtros = {"objeto": "", "desde": "", "hasta": ""}
    objeto = request.GET.get("objeto", "").strip()
    if objeto.isdigit() and int(objeto) < len(CLASES):
        qs = qs.filter(clase=int(objeto))
        filtros["objeto"] = objeto
    for campo, lookup in (("desde", "fecha__date__gte"), ("hasta", "fecha__date__lte")):
        fecha = parse_date(request.GET.get(campo, "") or "")
        if fecha:
            qs = qs.filter(**{lookup: fecha})
            filtros[campo] = fecha.isoformat()
    return qs, filtros


def bitacora(request):
    qs, filtros = _filtrar(request)

    por_hora = {fila["hora"]: fila["total"] for fila in
                qs.annotate(hora=ExtractHour("fecha")).values("hora").annotate(total=Count("id")).order_by()}
    maximo_hora = max(por_hora.values(), default=0)
    horas = [{
        "hora": h,
        "total": por_hora.get(h, 0),
        "porcentaje": round(por_hora.get(h, 0) * 100 / maximo_hora) if maximo_hora else 0,
    } for h in range(24)]

    top = list(qs.values("clase", "nombre").annotate(total=Count("id")).order_by("-total", "nombre")[:6])
    maximo_top = top[0]["total"] if top else 0
    for fila in top:
        fila["porcentaje"] = round(fila["total"] * 100 / maximo_top) if maximo_top else 0

    resumen = qs.aggregate(total=Count("id"), distintos=Count("clase", distinct=True),
                           primera=Min("fecha"), ultima=Max("fecha"))
    hora_pico = max(horas, key=lambda h: h["total"]) if maximo_hora else None

    pagina = Paginator(qs, 24).get_page(request.GET.get("pagina"))
    params = request.GET.copy()
    params.pop("pagina", None)

    return render(request, "detector/bitacora.html", {
        "pagina": pagina,
        "filtros": filtros,
        "querystring": params.urlencode(),
        "objetos": Avistamiento.objects.values("clase", "nombre").distinct().order_by("nombre"),
        "resumen": resumen,
        "horas": horas,
        "hora_pico": hora_pico,
        "top": top,
    })


def exportar_csv(request):
    qs, _ = _filtrar(request)
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="bitacora_avistamientos.csv"'
    respuesta.write("﻿")  # BOM: Excel respeta las tildes
    escritor = csv.writer(respuesta)
    escritor.writerow(["id", "fecha", "objeto", "clase_coco", "confianza", "cantidad", "x", "y", "ancho", "alto"])
    for a in qs.iterator():
        escritor.writerow([
            a.pk, timezone.localtime(a.fecha).strftime("%Y-%m-%d %H:%M:%S"), a.nombre,
            a.nombre_ingles, f"{a.confianza:.4f}", a.cantidad, a.x, a.y, a.ancho, a.alto,
        ])
    return respuesta


@require_GET
def imagen_avistamiento(request, pk):
    fila = Avistamiento.objects.filter(pk=pk).values_list("imagen", flat=True).first()
    if fila is None:
        raise Http404("Avistamiento no encontrado")
    respuesta = HttpResponse(bytes(fila), content_type="image/jpeg")
    respuesta["Cache-Control"] = "public, max-age=31536000, immutable"  # el recorte nunca cambia
    return respuesta


@require_POST
def vaciar_bitacora(request):
    borrados, _ = Avistamiento.objects.all().delete()
    if camara.registrador is not None:
        camara.registrador.reiniciar()
    messages.success(request, f"Bitácora vaciada: se eliminaron {borrados} avistamientos.")
    return redirect("detector:bitacora")


# ---------------------------------------------------------- Analizar imagen
LADO_MAXIMO_ANALISIS = 1280


def _analizar_archivo(archivo, confianza):
    """Detecta objetos en una imagen subida. Devuelve (resultado, error)."""
    max_bytes = int(settings.ANALIZAR_MAX_MB * 1024 * 1024)
    if archivo.size > max_bytes:
        return None, f"La imagen pesa más de {settings.ANALIZAR_MAX_MB:g} MB."
    datos = np.frombuffer(archivo.read(), dtype=np.uint8)
    imagen = cv2.imdecode(datos, cv2.IMREAD_COLOR) if datos.size else None
    if imagen is None:
        return None, "El archivo no es una imagen válida (usa JPG, PNG, BMP o WEBP)."

    alto, ancho = imagen.shape[:2]
    escala = LADO_MAXIMO_ANALISIS / max(alto, ancho)
    if escala < 1:
        imagen = cv2.resize(imagen, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)

    try:
        detector = obtener_detector()
    except (ModeloNoEncontrado, cv2.error) as exc:
        return None, str(exc)

    inicio = time.perf_counter()
    detecciones = detector.detectar(imagen, confianza)
    ms = (time.perf_counter() - inicio) * 1000
    anotada = dibujar_detecciones(imagen.copy(), detecciones)
    ok, jpg = cv2.imencode(".jpg", anotada, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        return None, "No se pudo generar la imagen de resultado."
    return {
        "imagen": "data:image/jpeg;base64," + base64.b64encode(jpg.tobytes()).decode("ascii"),
        "nombre_archivo": archivo.name,
        "dimensiones": f"{ancho}×{alto}",
        "objetos": resumir(detecciones),
        "detecciones": [
            {**d, "porcentaje": round(d["confianza"] * 100), "color": color_hex(d["clase"])}
            for d in detecciones
        ],
        "total": len(detecciones),
        "ms": round(ms),
    }, None


@require_http_methods(["GET", "POST"])
def analizar(request):
    """Sube una foto y la analiza con el mismo detector que el video."""
    contexto = {"confianza": round(camara.confianza * 100), "max_mb": settings.ANALIZAR_MAX_MB}
    if request.method == "POST":
        try:
            confianza = min(max(int(request.POST.get("confianza", 45)), 5), 95)
        except ValueError:
            confianza = 45
        contexto["confianza"] = confianza
        archivo = request.FILES.get("imagen")
        if archivo is None:
            contexto["error"] = "Selecciona una imagen para analizar."
        else:
            contexto["resultado"], contexto["error"] = _analizar_archivo(archivo, confianza / 100)
        status = 400 if contexto.get("error") else 200
        return render(request, "detector/analizar.html", contexto, status=status)
    return render(request, "detector/analizar.html", contexto)


def ir_a_bitacora_de(request, clase):
    """Atajo del álbum: abre la bitácora filtrada por un objeto."""
    return redirect(f"{reverse('detector:bitacora')}?objeto={clase}")
