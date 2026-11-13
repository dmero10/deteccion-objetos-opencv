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
