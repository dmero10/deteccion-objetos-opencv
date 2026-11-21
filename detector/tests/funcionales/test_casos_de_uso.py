"""FUNCIONALES: casos de uso clave probados desde el navegador, como lo haría un usuario.

Un navegador Edge automático (Selenium, sin ventana) abre la aplicación servida por Django,
hace clic en los botones y comprueba lo que se ve en pantalla. En cada paso guarda una
captura en docs/evidencias/.

Lo único simulado es el dispositivo de la cámara: en lugar de la webcam entrega siempre
la foto de prueba bus.jpg. La detección es REAL (YOLO11n con OpenCV), igual que el
servidor, las plantillas, el JavaScript y PostgreSQL.

Requiere: pip install -r requirements-dev.txt  (Selenium) y Microsoft Edge o Google Chrome.
Si no están disponibles, estas pruebas se omiten.
"""
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from detector.camera import camara
from detector.models import Avistamiento
from detector.yolo import color_bgr, modelo_disponible

from ..utiles import CapturaFalsa

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select, WebDriverWait
    HAY_SELENIUM = True
except ImportError:  # dependencia solo de desarrollo
    HAY_SELENIUM = False

RAIZ = Path(__file__).resolve().parents[3]
IMAGEN_BUS = RAIZ / "detector" / "datos_prueba" / "bus.jpg"
EVIDENCIAS = RAIZ / "docs" / "evidencias"


def cuadro_de_camara():
    """bus.jpg centrada en un cuadro de 640x480, como si la webcam la estuviera viendo."""
    lienzo = np.full((480, 640, 3), 40, dtype=np.uint8)
    lienzo[:, 140:500] = cv2.resize(cv2.imread(str(IMAGEN_BUS)), (360, 480))
    return lienzo


class CamaraQueVeUnBus(CapturaFalsa):
    CUADRO = None

    def read(self):
        time.sleep(1 / 30)  # ~30 fps, como una webcam
        return True, self.CUADRO.copy()


def abrir_navegador():
    for crear in (webdriver.Edge, webdriver.Chrome):
        opciones = webdriver.EdgeOptions() if crear is webdriver.Edge else webdriver.ChromeOptions()
        for argumento in ("--headless=new", "--window-size=1366,1000", "--disable-gpu", "--lang=es",
                          "--blink-settings=preferredColorScheme=1"):  # tema claro en las capturas
            opciones.add_argument(argumento)
        try:
            return crear(options=opciones)
        except WebDriverException:
            continue
    return None


@unittest.skipUnless(HAY_SELENIUM, "Selenium no está instalado (pip install -r requirements-dev.txt)")
@unittest.skipUnless(modelo_disponible(), "Falta el modelo YOLO")
class CasosDeUsoTests(StaticLiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.navegador = abrir_navegador()
        if cls.navegador is None:
            super().tearDownClass()
            raise unittest.SkipTest("No se encontró Microsoft Edge ni Google Chrome")
        CamaraQueVeUnBus.CUADRO = cuadro_de_camara()
        cls.parche = mock.patch("detector.camera.cv2.VideoCapture", CamaraQueVeUnBus)
        cls.parche.start()
        EVIDENCIAS.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.navegador.quit()
        cls.parche.stop()
        camara.detener()
        super().tearDownClass()

    def setUp(self):
        camara.detener()
        camara.registrador.reiniciar()
        camara.configurar_deteccion(activa=True, confianza=0.45, registrar=True)
        self.addCleanup(camara.detener)  # antes de que se limpie la base de datos

    # ----------------------------------------------------------- ayudas
    def abrir(self, ruta):
        self.navegador.get(self.live_server_url + ruta)

    def el(self, selector):
        return self.navegador.find_element(By.CSS_SELECTOR, selector)

    def todos(self, selector):
        return self.navegador.find_elements(By.CSS_SELECTOR, selector)

    def texto(self, selector):
        return self.el(selector).get_attribute("textContent").strip()

    def esperar(self, condicion, segundos=15, mensaje=""):
        try:
            WebDriverWait(self.navegador, segundos, poll_frequency=0.2).until(lambda _: condicion())
        except TimeoutException:
            self.fail(mensaje or "La condición no se cumplió a tiempo")

    def captura(self, nombre):
        self.navegador.save_screenshot(str(EVIDENCIAS / f"{nombre}.png"))

    def clic_js(self, elemento):
        self.navegador.execute_script("arguments[0].click();", elemento)

    def objetos_en_pantalla(self):
        return {li.get_attribute("textContent").split("×")[0].strip().lower()
                for li in self.todos("#escena li:not(.vacio)")}

    def encender_camara_y_detectar(self):
        self.abrir("/")
        self.el("#btn-camara").click()
        self.esperar(lambda: {"persona", "bus"} <= self.objetos_en_pantalla(), 20,
                     "No aparecieron 'persona' y 'bus' en 'Objetos en pantalla'")

    # ================================================= CU-01 · Inicio
    def test_cu01_1_pagina_inicial(self):
        """Al abrir la aplicación se ve la página En vivo con la cámara apagada y el menú."""
        self.abrir("/")
        self.assertEqual(self.navegador.title, "En vivo · Detector de objetos")
        self.assertEqual(self.texto("h1"), "Detección en vivo")
        menu = [a.text for a in self.todos(".navegacion a")]
        self.assertEqual(menu, ["En vivo", "Objetos", "Historial", "Analizar imagen"])
        self.assertEqual(self.texto("#reposo-titulo"), "La cámara está apagada")
        self.assertEqual(self.el("#btn-camara").text, "Encender cámara")
        self.assertEqual(self.el("#btn-foto").get_attribute("aria-disabled"), "true")
        self.captura("CU01_1_pagina_inicial")

    def test_cu01_2_navegar_por_el_menu(self):
        """Cada opción del menú abre su página."""
        self.abrir("/")
        for opcion, titulo in (("Objetos", "Objetos que reconoce el sistema"),
                               ("Historial", "Historial de detecciones"),
                               ("Analizar imagen", "Analizar una imagen"),
                               ("En vivo", "Detección en vivo")):
            with self.subTest(opcion=opcion):
                self.navegador.find_element(By.LINK_TEXT, opcion).click()
                self.esperar(lambda: self.texto("h1") == titulo, 10, f"No se abrió '{opcion}'")
                activo = self.el('.navegacion a[aria-current="page"]').text
                self.assertEqual(activo, opcion, "El menú marca la página actual")

    def test_cu01_3_encender_la_camara(self):
        """El botón enciende la cámara: aparece el video y cambian los indicadores."""
        self.abrir("/")
        self.el("#btn-camara").click()
        self.esperar(lambda: self.el("#video").is_displayed(), 10, "No apareció el video")
        self.assertIn("/video/", self.el("#video").get_attribute("src"))
        self.esperar(lambda: self.texto("#indicador") == "En vivo")
        self.esperar(lambda: self.texto("#pildora-texto").startswith("En vivo"))
        self.esperar(lambda: int(self.texto("#lec-fps")) > 0, 10, "Los FPS siguen en 0")
        self.assertEqual(self.el("#btn-camara").text, "Apagar cámara")
        self.assertEqual(self.texto("#lec-resolucion"), "640x480")
        self.esperar(lambda: self.navegador.execute_script(
            "const v = document.getElementById('video'); return v.complete && v.naturalWidth > 0;"),
            10, "El video no muestra imagen")
        self.captura("CU01_3_camara_encendida")

    def test_cu01_4_apagar_la_camara(self):
        self.abrir("/")
        self.el("#btn-camara").click()
        self.esperar(lambda: self.texto("#indicador") == "En vivo")
        self.el("#btn-camara").click()
        self.esperar(lambda: self.texto("#indicador") == "Apagada")
        self.assertFalse(self.el("#video").is_displayed())
        self.assertEqual(self.texto("#reposo-titulo"), "La cámara está apagada")
        self.assertFalse(camara.activa, "La cámara se liberó en el servidor")

    # ======================================= CU-02 · Detección en video
    def test_cu02_1_detecta_objetos_en_el_video(self):
        """Con la cámara viendo la escena, el panel lista los objetos detectados."""
        self.encender_camara_y_detectar()
        self.esperar(lambda: int(self.texto("#lec-total")) >= 4)
        filas = {}
        for li in self.todos("#escena li:not(.vacio)"):
            nombre = li.find_element(By.CSS_SELECTOR, ".nombre").get_attribute("textContent").strip()
            cantidad = li.find_elements(By.CSS_SELECTOR, ".num")[0].get_attribute("textContent")  # "×3"
            filas[nombre] = int(cantidad.strip("×"))
        self.assertGreaterEqual(filas.get("persona", 0), 3)
        self.assertEqual(filas.get("bus"), 1)
        self.assertGreater(int(self.texto("#lec-ms")), 0, "Se muestra el tiempo de inferencia")
        self.captura("CU02_1_objetos_detectados")

    def test_cu02_2_las_cajas_se_dibujan_sobre_el_video(self):
        """El cuadro que envía el servidor trae las cajas de colores dibujadas por OpenCV."""
        self.encender_camara_y_detectar()
        with urllib.request.urlopen(self.live_server_url + "/foto/") as r:
            cuadro = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        for clase, nombre in ((0, "persona"), (5, "bus")):
            color = np.array(color_bgr(clase), dtype=int)
            pixeles = int((np.abs(cuadro.astype(int) - color).max(axis=2) < 40).sum())
            with self.subTest(objeto=nombre):
                self.assertGreater(pixeles, 300, f"No se ve la caja de '{nombre}' en el video")
        cv2.imwrite(str(EVIDENCIAS / "CU02_2_cuadro_con_cajas.jpg"), cuadro)

    def test_cu02_3_pausar_y_reanudar_la_deteccion(self):
        self.encender_camara_y_detectar()
        self.clic_js(self.el("#aj-deteccion"))
        self.esperar(lambda: self.texto("#escena") == "La detección está desactivada.")
        self.assertEqual(self.texto("#lec-total"), "0")
        self.assertEqual(self.texto("#indicador"), "Sin detección")
        self.captura("CU02_3_deteccion_en_pausa")
        self.clic_js(self.el("#aj-deteccion"))
        self.esperar(lambda: "persona" in self.objetos_en_pantalla(), 15, "No volvió a detectar")

    def test_cu02_4_subir_la_confianza_minima(self):
        """Con confianza 95 % desaparecen los objetos dudosos; el valor llega al servidor."""
        self.encender_camara_y_detectar()
        self.navegador.execute_script(
            "const r = document.getElementById('aj-confianza'); r.value = 95;"
            "r.dispatchEvent(new Event('input'));")
        self.esperar(lambda: self.texto("#aj-confianza-valor") == "95%")
        self.esperar(lambda: abs(camara.confianza - 0.95) < 1e-9, 5, "El servidor no recibió el cambio")
        self.esperar(lambda: int(self.texto("#lec-total")) == 0, 10, "Siguen apareciendo objetos")
        self.captura("CU02_4_confianza_95")

    def test_cu02_5_capturar_foto(self):
        self.encender_camara_y_detectar()
        enlace = self.el("#btn-foto")
        self.assertEqual(enlace.get_attribute("aria-disabled"), "false")
        with urllib.request.urlopen(enlace.get_attribute("href")) as r:
            self.assertEqual(r.headers["Content-Type"], "image/jpeg")
            self.assertIn("attachment", r.headers["Content-Disposition"])

    # ================================== CU-03 · Visualización en interfaz
    def test_cu03_1_ultimas_detecciones_y_aviso(self):
        """Lo detectado aparece en 'Últimas detecciones guardadas' y avisa del objeto nuevo."""
        self.encender_camara_y_detectar()
        self.esperar(lambda: len(self.todos("#ultimas li:not(.vacio)")) >= 2, 15,
                     "No aparecieron las detecciones guardadas")
        nombres = {n.get_attribute("textContent").split("×")[0].strip().lower()
                   for n in self.todos("#ultimas .nombre")}
        self.assertTrue({"persona", "bus"} <= nombres, nombres)
        self.esperar(lambda: self.el("#notificacion").is_displayed(), 5, "No apareció el aviso")
        self.assertIn("Nuevo objeto descubierto", self.texto("#notificacion"))
        self.assertEqual(self.texto("#alb-descubiertas"), "2")
        self.assertEqual(Avistamiento.objects.count(), 2, "Se guardaron en PostgreSQL")
        self.captura("CU03_1_ultimas_detecciones")

    def test_cu03_2_historial(self):
        """El historial muestra en tabla lo guardado y permite filtrar por objeto."""
        self.encender_camara_y_detectar()
        self.esperar(lambda: Avistamiento.objects.count() == 2)
        self.navegador.find_element(By.LINK_TEXT, "Historial").click()
        self.esperar(lambda: self.texto("h1") == "Historial de detecciones")
        filas = self.todos(".tabla tbody tr")
        self.assertEqual(len(filas), 2)
        self.assertEqual(self.texto(".cifras .cifra strong"), "2")
        self.assertTrue(all(img.get_attribute("naturalWidth") != "0" for img in self.todos(".tabla img")),
                        "Las miniaturas cargan")
        self.captura("CU03_2_historial")

        Select(self.el('select[name="objeto"]')).select_by_visible_text("bus")
        self.navegador.find_element(By.XPATH, "//button[text()='Filtrar']").click()
        self.esperar(lambda: "objeto=5" in self.navegador.current_url)
        filas = self.todos(".tabla tbody tr")
        self.assertEqual(len(filas), 1)
        self.assertIn("bus", filas[0].get_attribute("textContent").lower())

    def test_cu03_3_objetos_descubiertos(self):
        self.encender_camara_y_detectar()
        self.esperar(lambda: Avistamiento.objects.count() == 2)
        self.navegador.find_element(By.LINK_TEXT, "Objetos").click()
        self.esperar(lambda: self.texto("h1") == "Objetos que reconoce el sistema")
        self.assertIn("2 de 80 descubiertos", self.texto(".resumen-objetos"))
        self.assertEqual(len(self.todos(".objeto")), 80)
        descubiertos = {o.get_attribute("textContent").strip().split("\n")[0].strip().lower()
                        for o in self.todos(".objeto:not(.pendiente) .objeto-nombre")}
        self.assertEqual(descubiertos, {"persona", "bus"})
        self.captura("CU03_3_objetos")

    def test_cu03_4_analizar_imagen(self):
        """Subir una foto muestra la imagen con las cajas y la lista de objetos."""
        self.abrir("/analizar/")
        self.el("#archivo").send_keys(str(IMAGEN_BUS))
        self.esperar(lambda: self.el("#vista-previa").is_displayed(), 5, "No se mostró la vista previa")
        self.el("#btn-analizar").click()
        self.esperar(lambda: "encontrado" in self.navegador.page_source, 20, "No apareció el resultado")
        self.assertRegex(self.texto(".resultado h2"), r"^\d+ objetos encontrados$")
        nombres = [n.get_attribute("textContent").strip() for n in self.todos(".resultado .nombre")]
        self.assertGreaterEqual(nombres.count("persona"), 3)
        self.assertIn("bus", nombres)
        self.assertTrue(self.el(".resultado figure img").get_attribute("src").startswith("data:image/jpeg"))
        self.captura("CU03_4_analizar_imagen")

    def test_cu03_5_pantalla_de_celular(self):
        """En un celular (390 px) la página se adapta sin desplazamiento horizontal."""
        self.navegador.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",
                                       {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        self.addCleanup(self.navegador.execute_cdp_cmd, "Emulation.clearDeviceMetricsOverride", {})
        for ruta in ("/", "/album/", "/bitacora/", "/analizar/"):
            with self.subTest(ruta=ruta):
                self.abrir(ruta)
                ancho = self.navegador.execute_script("return document.documentElement.scrollWidth")
                self.assertLessEqual(ancho, 390, f"{ruta} se sale de la pantalla ({ancho} px)")
        self.abrir("/")
        self.captura("CU03_5_celular")
