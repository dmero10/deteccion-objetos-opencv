"""Pruebas funcionales del sistema EN FUNCIONAMIENTO (servidor + cámara real + PostgreSQL).

A diferencia de `python manage.py test` (pruebas automatizadas con cámara simulada),
este script habla con el servidor que está corriendo, igual que lo haría el navegador.

Uso (con el servidor encendido en otra terminal):
    python scripts/prueba_funcional.py
    python scripts/prueba_funcional.py --url http://127.0.0.1:8000 --informe docs/resultado_pruebas.md
    python scripts/prueba_funcional.py --sin-camara      # omite los casos que usan la cámara

Para los casos de detección en vivo, ponte frente a la cámara (o pon un objeto a la vista).
Solo usa la librería estándar de Python.
"""
import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
IMAGEN_BUS = RAIZ / "detector" / "datos_prueba" / "bus.jpg"


class Cliente:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.cookies = http.cookiejar.CookieJar()
        self.abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def csrf(self):
        for c in self.cookies:
            if c.name == "csrftoken":
                return c.value
        self.get("/")
        return next((c.value for c in self.cookies if c.name == "csrftoken"), "")

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None, timeout=15):
        cabeceras = dict(cabeceras or {})
        if metodo == "POST":
            cabeceras["X-CSRFToken"] = self.csrf()
            cabeceras["Referer"] = self.base + "/"
        req = urllib.request.Request(self.base + ruta, data=cuerpo, headers=cabeceras, method=metodo)
        try:
            with self.abridor.open(req, timeout=timeout) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def get(self, ruta, **kw):
        return self.pedir("GET", ruta, **kw)

    def post_json(self, ruta, datos=None):
        return self.pedir("POST", ruta, json.dumps(datos or {}).encode(), {"Content-Type": "application/json"})

    def post_archivo(self, ruta, nombre, contenido, campos=None):
        limite = uuid.uuid4().hex
        partes = []
        for clave, valor in (campos or {}).items():
            partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{clave}"\r\n\r\n{valor}\r\n'.encode())
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="imagen"; filename="{nombre}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode() + contenido + b"\r\n"
        )
        cuerpo = b"".join(partes) + f"--{limite}--\r\n".encode()
        campos_csrf = {"Content-Type": f"multipart/form-data; boundary={limite}"}
        return self.pedir("POST", ruta, cuerpo, campos_csrf, timeout=60)

    def estado(self):
        return json.loads(self.get("/api/estado/")[2])

    def esperar(self, condicion, segundos):
        limite = time.time() + segundos
        while time.time() < limite:
            e = self.estado()
            if condicion(e):
                return e
            time.sleep(0.4)
        return self.estado()

    def contar_frames_mjpeg(self, segundos=3.0):
        req = urllib.request.Request(self.base + "/video/")
        frames, inicio = 0, time.time()
        with self.abridor.open(req, timeout=10) as r:
            tipo = r.headers.get("Content-Type", "")
            while time.time() - inicio < segundos:
                bloque = r.read(65536)
                if not bloque:
                    break
                frames += bloque.count(b"--frame")
        return tipo, frames


class Resultado(Exception):
    pass


class Omitido(Exception):
    pass


def verificar(condicion, detalle):
    if not condicion:
        raise Resultado(detalle)


def casos(c, con_camara):
    """Generador de (id, descripción, función). Cada función devuelve un detalle o lanza error."""

    def cf01():
        s, _, html = c.get("/")
        verificar(s == 200 and "Detección en vivo".encode() in html, f"HTTP {s}")
        return "HTTP 200 · página En vivo"
    yield "CF-01", "La página principal carga", cf01

    def cf02():
        estados = {r: c.get(r)[0] for r in ("/album/", "/bitacora/", "/analizar/", "/admin/login/")}
        verificar(all(v == 200 for v in estados.values()), str(estados))
        return "Objetos, Historial, Analizar y Admin: HTTP 200"
    yield "CF-02", "Las demás páginas cargan", cf02

    def cf03():
        e = c.estado()
        for clave in ("activa", "fps", "deteccion", "registro"):
            verificar(clave in e, f"falta '{clave}'")
        return f"modelo {e['deteccion']['modelo']} · objetos descubiertos {e['registro']['descubiertas']}/80"
    yield "CF-03", "La API de estado responde JSON válido", cf03

    if con_camara:
        def cf04():
            s, _, cuerpo = c.post_json("/api/camara/iniciar/")
            e = json.loads(cuerpo)
            verificar(s == 200 and e["activa"], e.get("error") or f"HTTP {s}")
            return f"cámara {e['indice']} abierta a {e['resolucion']}"
        yield "CF-04", "Encender la cámara", cf04

        def cf05():
            tipo, frames = c.contar_frames_mjpeg(3.0)
            verificar("multipart/x-mixed-replace" in tipo, tipo)
            verificar(frames >= 10, f"solo {frames} frames en 3 s")
            return f"{frames} frames JPEG en 3 s (~{frames / 3:.0f} fps)"
        yield "CF-05", "El video en vivo llega al navegador (MJPEG)", cf05

        def cf06():
            c.post_json("/api/deteccion/", {"activa": True, "confianza": 0.45})
            e = c.esperar(lambda e: e["deteccion"]["fps"] > 0 and e["deteccion"]["inferencia_ms"] > 0, 10)
            d = e["deteccion"]
            verificar(d["inferencia_ms"] > 0, d["error"] or "el detector no publicó resultados")
            e = c.esperar(lambda e: e["deteccion"]["total"] > 0, 6)
            objetos = ", ".join(f"{o['nombre']} {o['confianza']:.0%}" for o in e["deteccion"]["objetos"]) or "ninguno a la vista"
            return f"{d['inferencia_ms']:.0f} ms por inferencia · {d['fps']:.1f} detecciones/s · objetos: {objetos}"
        yield "CF-06", "YOLO11n detecta en vivo sobre el video", cf06

        def cf07():
            e = json.loads(c.post_json("/api/deteccion/", {"confianza": 0.8})[2])
            verificar(abs(e["deteccion"]["confianza"] - 0.8) < 1e-6, str(e["deteccion"]["confianza"]))
            e = json.loads(c.post_json("/api/deteccion/", {"confianza": 0.45})[2])
            return "0.45 → 0.80 → 0.45 aplicado sin reiniciar el video"
        yield "CF-07", "Cambiar la confianza mínima en vivo", cf07

        def cf08():
            c.post_json("/api/deteccion/", {"activa": False})
            time.sleep(0.5)
            e = c.estado()
            verificar(e["activa"] and e["deteccion"]["total"] == 0, "seguía mostrando objetos")
            c.post_json("/api/deteccion/", {"activa": True})
            return "con la detección apagada el video sigue y no hay objetos"
        yield "CF-08", "Pausar y reanudar la detección", cf08

        def cf09():
            s, h, cuerpo = c.get("/foto/")
            verificar(s == 200 and h.get("Content-Type") == "image/jpeg" and cuerpo[:2] == b"\xff\xd8", f"HTTP {s}")
            return f"JPEG de {len(cuerpo) / 1024:.0f} KB"
        yield "CF-09", "Capturar una foto del video", cf09

        def cf10():
            e = c.estado()
            if not e["registro"]["activo"]:
                raise Omitido("el guardado en el historial está desactivado")
            e = c.esperar(lambda e: e["registro"]["recientes"], 8)
            recientes = e["registro"]["recientes"]
            if not recientes:
                raise Omitido("no hubo objetos a la vista para registrar")
            a = recientes[0]
            s, h, img = c.get(a["imagen"])
            verificar(s == 200 and img[:2] == b"\xff\xd8", "el recorte no es un JPEG")
            return f"#{a['id']} {a['nombre']} {a['confianza']:.0%} guardado con recorte en PostgreSQL"
        yield "CF-10", "Las detecciones se guardan en el historial", cf10

    def cf11():
        s, _, html = c.post_archivo("/analizar/", "bus.jpg", IMAGEN_BUS.read_bytes(), {"confianza": "45"})
        nombres = re.findall(r'class="nombre">([^<]+)<', html.decode("utf-8", "replace"))
        personas, bus = nombres.count("persona"), nombres.count("bus")
        verificar(s == 200, f"HTTP {s}")
        verificar(personas >= 3 and bus >= 1, f"{personas} personas y {bus} bus")
        return f"{personas} personas y {bus} bus en la imagen de referencia"
    yield "CF-11", "Analizar una imagen subida (bus.jpg)", cf11

    def cf12():
        s, _, html = c.post_archivo("/analizar/", "notas.txt", b"esto no es una imagen")
        verificar(s == 400 and "no es una imagen".encode() in html, f"HTTP {s}")
        return "rechazado con HTTP 400 y mensaje claro"
    yield "CF-12", "Rechazar un archivo que no es imagen", cf12

    def cf13():
        s, h, cuerpo = c.get("/bitacora/exportar/")
        verificar(s == 200 and "text/csv" in h.get("Content-Type", ""), f"HTTP {s}")
        filas = cuerpo.decode("utf-8-sig").strip().splitlines()
        return f"CSV con {len(filas) - 1} detección(es)"
    yield "CF-13", "Exportar el historial a CSV", cf13

    def cf14():
        s, _, _ = c.get("/api/camara/iniciar/")
        verificar(s == 405, f"GET devolvió HTTP {s}")
        # POST sin token CSRF (como lo haría otra página web): debe rechazarse
        req = urllib.request.Request(c.base + "/api/camara/detener/", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            codigo = 200
        except urllib.error.HTTPError as e:
            codigo = e.code
        verificar(codigo == 403, f"POST sin CSRF devolvió HTTP {codigo}")
        return "GET → 405 y POST sin token CSRF → 403"
    yield "CF-14", "Las acciones exigen POST con token CSRF", cf14

    if con_camara:
        def cf15():
            e = json.loads(c.post_json("/api/camara/detener/")[2])
            verificar(not e["activa"], "la cámara sigue activa")
            return "cámara liberada"
        yield "CF-15", "Apagar la cámara", cf15


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--sin-camara", action="store_true", help="omitir los casos que usan la cámara")
    parser.add_argument("--informe", help="guardar los resultados en un archivo Markdown")
    args = parser.parse_args()

    c = Cliente(args.url)
    try:
        c.get("/api/estado/", timeout=5)
    except OSError as exc:
        sys.exit(f"No se pudo conectar con {args.url}: {exc}\n¿Está corriendo 'python manage.py runserver'?")

    filas = []
    print(f"\nPruebas funcionales contra {args.url}\n")
    for id_, descripcion, funcion in casos(c, not args.sin_camara):
        inicio = time.time()
        try:
            detalle, resultado = funcion(), "PASA"
        except Omitido as exc:
            detalle, resultado = str(exc), "OMITIDO"
        except Resultado as exc:
            detalle, resultado = str(exc), "FALLA"
        except Exception as exc:  # noqa: BLE001 - cualquier error es un fallo del caso
            detalle, resultado = f"{type(exc).__name__}: {exc}", "FALLA"
        segundos = time.time() - inicio
        filas.append((id_, descripcion, resultado, detalle, segundos))
        marca = {"PASA": "✔", "FALLA": "✘", "OMITIDO": "–"}[resultado]
        print(f" {marca} {id_}  {descripcion:<55} {resultado:<8} {detalle}")

    pasan = sum(f[2] == "PASA" for f in filas)
    fallan = sum(f[2] == "FALLA" for f in filas)
    print(f"\n{pasan} pasan · {fallan} fallan · {len(filas) - pasan - fallan} omitidos\n")

    if args.informe:
        ruta = Path(args.informe)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        lineas = [
            "# Resultado de las pruebas funcionales",
            "",
            f"Ejecutado el {datetime.now():%Y-%m-%d %H:%M} contra `{args.url}` "
            f"({'con' if not args.sin_camara else 'sin'} cámara).",
            "",
            "| ID | Caso | Resultado | Detalle | Tiempo |",
            "|---|---|---|---|---|",
        ]
        lineas += [f"| {i} | {d} | **{r}** | {det} | {s:.1f} s |" for i, d, r, det, s in filas]
        lineas += ["", f"**{pasan} pasan · {fallan} fallan · {len(filas) - pasan - fallan} omitidos**", ""]
        ruta.write_text("\n".join(lineas), encoding="utf-8")
        print(f"Informe guardado en {ruta}")

    sys.exit(1 if fallan else 0)


if __name__ == "__main__":
    main()
