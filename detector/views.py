import json
import time

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .camera import camara


def index(request):
    """Página principal con el video en vivo y los controles."""
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
    """Recibe {"activa": true/false, "confianza": 0.5} y lo aplica al video en vivo."""
    try:
        datos = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    if not isinstance(datos, dict):
        return JsonResponse({"error": "Se esperaba un objeto JSON"}, status=400)

    activa = datos.get("activa")
    if activa is not None and not isinstance(activa, bool):
        return JsonResponse({"error": "'activa' debe ser true o false"}, status=400)
    confianza = datos.get("confianza")
    if confianza is not None and (isinstance(confianza, bool) or not isinstance(confianza, (int, float))):
        return JsonResponse({"error": "'confianza' debe ser un número entre 0 y 1"}, status=400)

    camara.configurar_deteccion(activa=activa, confianza=confianza)
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
