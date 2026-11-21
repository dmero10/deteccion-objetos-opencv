"""INTEGRACIÓN: acceso a las rutas principales de Django (urls.py + views.py + plantillas + BD)."""
from django.test import Client, TestCase
from django.urls import resolve, reverse

from detector import views
from detector.models import Avistamiento

# (nombre de la ruta, argumentos, URL esperada, vista, plantilla o tipo de contenido)
PAGINAS = [
    ("detector:index", [], "/", views.index, "detector/index.html"),
    ("detector:album", [], "/album/", views.album, "detector/album.html"),
    ("detector:bitacora", [], "/bitacora/", views.bitacora, "detector/bitacora.html"),
    ("detector:analizar", [], "/analizar/", views.analizar, "detector/analizar.html"),
]

# Rutas que solo aceptan POST (cambian el estado del sistema)
SOLO_POST = ["detector:api_iniciar", "detector:api_detener", "detector:api_deteccion", "detector:vaciar_bitacora"]


class RutasTests(TestCase):
    def test_cada_url_apunta_a_su_vista(self):
        for nombre, args, url, vista, _ in PAGINAS:
            with self.subTest(ruta=nombre):
                self.assertEqual(reverse(nombre, args=args), url)
                self.assertEqual(resolve(url).func, vista)

    def test_paginas_responden_200_con_su_plantilla(self):
        for nombre, args, _, _, plantilla in PAGINAS:
            with self.subTest(ruta=nombre):
                r = self.client.get(reverse(nombre, args=args))
                self.assertEqual(r.status_code, 200)
                self.assertTemplateUsed(r, plantilla)
                self.assertTemplateUsed(r, "detector/base.html")

    def test_menu_marca_la_pagina_actual(self):
        for nombre, args, url, _, _ in PAGINAS:
            with self.subTest(ruta=nombre):
                r = self.client.get(url)
                self.assertContains(r, f'<a href="{url}" aria-current="page">')

    def test_paginas_enlazan_a_las_demas(self):
        r = self.client.get("/")
        for _, _, url, _, _ in PAGINAS:
            self.assertContains(r, f'href="{url}"')

    def test_api_estado_devuelve_json(self):
        r = self.client.get(reverse("detector:api_estado"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/json")
        self.assertEqual(set(r.json()), {"activa", "fps", "resolucion", "clientes", "indice", "error",
                                         "deteccion", "registro"})

    def test_rutas_de_accion_rechazan_get(self):
        for nombre in SOLO_POST:
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 405)

    def test_rutas_de_accion_exigen_token_csrf(self):
        cliente = Client(enforce_csrf_checks=True)  # como un navegador real
        for nombre in SOLO_POST:
            with self.subTest(ruta=nombre):
                self.assertEqual(cliente.post(reverse(nombre)).status_code, 403)

    def test_ruta_inexistente_da_404(self):
        self.assertEqual(self.client.get("/no-existe/").status_code, 404)

    def test_imagen_de_avistamiento(self):
        a = Avistamiento.objects.create(clase=0, nombre="persona", confianza=0.9, imagen=b"\xff\xd8jpg")
        r = self.client.get(reverse("detector:imagen_avistamiento", args=[a.pk]))
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/jpeg"))
        self.assertIn("max-age", r["Cache-Control"])

    def test_admin_requiere_inicio_de_sesion(self):
        r = self.client.get("/admin/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login/", r["Location"])

    def test_archivos_estaticos(self):
        """Django encuentra el CSS/JS y las páginas los enlazan (el servidor de pruebas no los sirve)."""
        from django.contrib.staticfiles import finders
        pagina = self.client.get("/")
        for archivo in ("detector/estilos.css", "detector/base.js", "detector/observatorio.js"):
            with self.subTest(archivo=archivo):
                self.assertIsNotNone(finders.find(archivo))
                self.assertContains(pagina, f"/static/{archivo}")
