# Detector de objetos en tiempo real (Django + OpenCV)

Práctica – Construcción de Software · UNEMI

Aplicativo web que captura video de la cámara con **OpenCV (cv2)**, detecta en tiempo real
80 tipos de objetos con **YOLO11n ejecutado por `cv2.dnn`**, dibuja los resultados sobre el
video y guarda cada avistamiento en **PostgreSQL**. La interfaz web está hecha con **Django**.

**Integrantes:** _(escribir nombres del grupo)_

## Inicio rápido (Windows)

1. Descarga el proyecto: botón verde **Code → Download ZIP** (y descomprímelo) o
   `git clone https://github.com/dmero10/deteccion-objetos-opencv.git`
2. Entra a la carpeta y haz **doble clic en `iniciar.bat`**.
3. La primera vez te pedirá la **contraseña de PostgreSQL**. Si no tienes PostgreSQL,
   ofrece instalarlo y te pide elegir una. Si no tienes Python, también ofrece instalarlo.
4. Espera a que se abra el navegador (la primera vez tarda 2-3 minutos) y presiona
   **Encender cámara**.

Las siguientes veces, el mismo doble clic arranca todo en segundos. Para detenerlo,
presiona `Ctrl + C` en la ventana negra o ciérrala.

`iniciar.bat` hace solo lo que harías a mano: crea el entorno virtual `venv`, instala
`requirements.txt`, crea el `.env`, crea la base de datos `deteccion_objetos`, aplica las
migraciones y arranca el servidor (si el puerto 8000 está ocupado, usa el siguiente libre).
En Linux o macOS: `./iniciar.sh` (con Python 3.10+ y PostgreSQL ya instalados).

| Si pasa esto | Haz esto |
|---|---|
| Escribiste mal la contraseña de PostgreSQL | Te la vuelve a pedir; o ejecuta `iniciar.bat --reconfigurar` |
| "No se pudo abrir la cámara" | Cierra Zoom, Teams, Meet o la app Cámara y vuelve a encenderla |
| Windows SmartScreen bloquea el `.bat` | **Más información → Ejecutar de todas formas** |

## Qué hace

| Página | Para qué sirve |
|---|---|
| **En vivo** | Video de la cámara con cajas, nombre y confianza de cada objeto. Estado (FPS, inferencia), objetos en pantalla, ajustes y últimas detecciones guardadas. |
| **Objetos** | Las 80 clases de COCO agrupadas por categoría. Cada una se marca como descubierta (con su mejor foto) la primera vez que la cámara la detecta. |
| **Historial** | Detecciones guardadas en PostgreSQL: filtros por objeto y fecha, detecciones por hora, los más detectados, tabla con recortes y exportación a CSV. |
| **Analizar imagen** | Sube una foto y el mismo detector la analiza (no se guarda). |

## Avance por sesión

### Sesión 1 – Configuración inicial y video en tiempo real ✅
- Proyecto Django (`config`) y aplicación base (`detector`).
- Conexión a PostgreSQL configurada mediante `.env`.
- Captura de video con `cv2.VideoCapture` en un hilo propio (la cámara se abre una sola vez
  aunque haya varias pestañas abiertas) y apagado automático si nadie mira.
- Transmisión en vivo al navegador como flujo **MJPEG** (`multipart/x-mixed-replace`).

### Sesión 2 – Procesamiento y detección ✅
- Módulo de detección con el **módulo DNN de OpenCV** (`cv2.dnn`), ejecutando **YOLO11n**
  (Ultralytics) exportado a ONNX y entrenado con COCO: **80 clases** (persona, celular,
  laptop, botella, silla, taza...). No usa PyTorch ni TensorFlow: OpenCV carga la red
  (`readNetFromONNX`), prepara la imagen (letterbox + `blobFromImage`), hace la inferencia
  y aplica NMS por clase (`NMSBoxesBatched`).
- La detección corre en **un hilo aparte** sobre el frame más reciente: el video va a la
  velocidad de la cámara y las cajas se actualizan unas 8 veces por segundo en CPU.
- Resultados dibujados **directamente en el video** con `cv2.rectangle` y `cv2.putText`.

#### Elección del modelo

Se compararon tres modelos con OpenCV DNN en CPU, sobre las imágenes de prueba de
Ultralytics (`bus.jpg`: 4 personas —una cortada en el borde— y un bus; `zidane.jpg`:
2 personas y una corbata), con confianza mínima 0,45:

| Modelo | mAP COCO | Tiempo por imagen | `bus.jpg` | `zidane.jpg` |
|---|---|---|---|---|
| YOLOv4-tiny | ~22 | ~45 ms | 3 personas + bus | **1 de 2 personas** + corbata (50 %) |
| YOLOv8n | 37.3 | ~115 ms | 3 personas + bus | 2 personas, **sin corbata** |
| **YOLO11n** | **39.5** | ~113 ms | 3 personas + bus (94 %) | **2 personas + corbata** |

Se eligió **YOLO11n**: misma velocidad que YOLOv8n y más precisión. Con la webcam, la
confianza al detectar una persona subió de 57–77 % (YOLOv4-tiny) a 84–94 %.

### Sesión 3 – Interfaz y pruebas ✅
- **Interfaz mejorada** con un diseño simple y claro: cuatro secciones (En vivo, Objetos,
  Historial, Analizar imagen), tema claro y oscuro automático según el sistema, diseño
  adaptable a celular, atajos de teclado (`Espacio` cámara, `D` detección, `F` foto) y
  accesibilidad (foco visible, textos alternativos, tabla para lectores de pantalla).
- **Historial en PostgreSQL** (modelo `Avistamiento`): por cada clase se guarda como máximo
  un avistamiento cada 15 s, con la caja más confiable, la cantidad de objetos y un recorte
  JPEG. Gráfico de actividad por hora, ranking, filtros, paginación, CSV y panel de admin.
- **Objetos descubiertos**: las 80 clases con su mejor foto y un aviso cuando aparece un
  objeto por primera vez.
- **Analizar imagen**: subida con arrastrar y soltar, validación de tipo y tamaño.
- **Pruebas en tres niveles** (detalle en [docs/CASOS_DE_PRUEBA.md](docs/CASOS_DE_PRUEBA.md)):
  - Pruebas automatizadas (`python manage.py test`), ver la sección Pruebas.
  - 15 pruebas funcionales del sistema en funcionamiento con cámara real y PostgreSQL
    (`python scripts/prueba_funcional.py`): **15 / 15 pasan**
    ([informe](docs/resultado_pruebas.md)).
  - Revisión visual en tema claro, oscuro y celular.

## Estructura

```
config/                     Configuración del proyecto (settings, urls)
detector/
  camera.py                 Captura (hilo de video + hilo de detección) y flujo MJPEG
  yolo.py                   Detección (cv2.dnn + YOLO11n) y dibujo de resultados
  registro.py               Guarda avistamientos en PostgreSQL con su recorte
  models.py                 Modelo Avistamiento
  clases.py                 80 clases de COCO (inglés / español) y sus categorías
  views.py / urls.py        Páginas y API
  templates/detector/       Plantillas (base, en vivo, objetos, historial, analizar)
  static/detector/          CSS y JavaScript
  modelos/yolo11n.onnx      Modelo ya exportado (~11 MB, incluido en el repositorio)
  datos_prueba/bus.jpg      Imagen de referencia para las pruebas
  tests/                    Pruebas automatizadas (un archivo por módulo)
scripts/
  prueba_funcional.py       Pruebas del sistema en funcionamiento (servidor + cámara)
  exportar_modelo.py        Cómo se generó el .onnx (opcional, requiere Ultralytics)
docs/
  CASOS_DE_PRUEBA.md        Casos de prueba y resultados
  resultado_pruebas.md      Informe generado por prueba_funcional.py
```

## Instalación manual (alternativa a `iniciar.bat`)

Requisitos: Python 3.10+, PostgreSQL 14+ y una cámara web.

```bash
git clone https://github.com/dmero10/deteccion-objetos-opencv.git
cd deteccion-objetos-opencv

python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux / macOS

pip install -r requirements.txt
```

### Base de datos

Copia `.env.example` como `.env` y escribe tu usuario y contraseña de PostgreSQL. Luego crea
la base con `python manage.py preparar_bd` (o a mano en pgAdmin:
`CREATE DATABASE deteccion_objetos;`).

### Ejecutar

```bash
python manage.py migrate
python manage.py runserver
```

Abre <http://127.0.0.1:8000/> y presiona **Encender cámara** (o la tecla `Espacio`).

Opcional, para ver el historial desde el panel de administración de Django:
`python manage.py createsuperuser` y entra a <http://127.0.0.1:8000/admin/>.

## Pruebas

La forma más fácil: **doble clic en `probar.bat`**. Ejecuta los tres niveles de pruebas,
muestra la cobertura y abre el reporte en el navegador (`docs/cobertura/index.html`).

| Nivel | Carpeta | Qué prueba | Cantidad |
|---|---|---|---|
| Unitarias | `detector/tests/unitarias/` | Funciones críticas aisladas (detección con OpenCV, cámara, registrador, análisis de imágenes), sin base de datos ni cámara | 78 |
| Integración | `detector/tests/integracion/` | Rutas de Django y flujos completos con PostgreSQL | 56 |
| Funcionales | `detector/tests/funcionales/` | Casos de uso desde un navegador Edge automático (Selenium), con capturas en `docs/evidencias/` | 14 |

A mano (necesita `pip install -r requirements-dev.txt`):

```bash
python manage.py test                                 # todas
python manage.py test detector.tests.unitarias        # solo un nivel
coverage run manage.py test && coverage report        # con cobertura
python scripts/prueba_funcional.py                    # sistema real: servidor corriendo + cámara
```

Los registros de la última ejecución están en `docs/logs/`.

## Rutas

| Ruta | Método | Descripción |
|---|---|---|
| `/` | GET | En vivo (video de la cámara) |
| `/album/` | GET | Objetos (las 80 clases) |
| `/album/<clase>/` | GET | Redirige al historial filtrado por ese objeto |
| `/bitacora/` | GET | Historial con filtros `?objeto=&desde=&hasta=&pagina=` |
| `/bitacora/exportar/` | GET | CSV con los mismos filtros |
| `/bitacora/vaciar/` | POST | Borra todo el historial |
| `/avistamientos/<id>/imagen/` | GET | Recorte JPEG de un avistamiento |
| `/analizar/` | GET / POST | Formulario y resultado del análisis de una imagen |
| `/video/` | GET | Flujo MJPEG de la cámara |
| `/foto/` | GET | Descarga el frame actual en JPEG |
| `/api/estado/` | GET | Estado de cámara, detección y registro en JSON |
| `/api/camara/iniciar/` · `/api/camara/detener/` | POST | Enciende / apaga la cámara |
| `/api/deteccion/` | POST | `{"activa": true, "confianza": 0.45, "registrar": true}` |

## Configuración (`.env`)

| Variable | Descripción | Por defecto |
|---|---|---|
| `CAMERA_INDEX` | Índice de la cámara (prueba 1 si la 0 no abre) | 0 |
| `CAMERA_ANCHO` / `CAMERA_ALTO` | Resolución solicitada | 640 / 480 |
| `CAMERA_ESPEJO` | Voltear la imagen horizontalmente (1/0) | 1 |
| `CAMERA_CALIDAD_JPEG` | Calidad del JPEG enviado (1-100) | 80 |
| `CAMERA_APAGADO_INACTIVO` | Segundos sin espectadores antes de apagar la cámara | 15 |
| `DETECTOR_ACTIVO` | Detección encendida al arrancar (1/0) | 1 |
| `DETECTOR_MODELO` | Archivo en `detector/modelos/<nombre>.onnx` | yolo11n |
| `DETECTOR_CONFIANZA` | Confianza mínima inicial (0-1) | 0.45 |
| `DETECTOR_NMS` | Umbral para eliminar cajas repetidas | 0.45 |
| `DETECTOR_REGISTRAR` | Guardar las detecciones en el historial (1/0) | 1 |
| `DETECTOR_INTERVALO_REGISTRO` | Segundos mínimos entre registros del mismo objeto | 15 |
| `ANALIZAR_MAX_MB` | Tamaño máximo de una imagen subida | 8 |

## ¿Dónde quedan los datos?

El historial se guarda en la base PostgreSQL **de cada computadora**, no en el repositorio.
Quien clone el proyecto empieza con el historial vacío; tus datos se quedan en tu PC
hasta que pulses **Borrar historial** o elimines la base de datos.

## Solución de problemas

- **"No se pudo abrir la cámara"**: ciérrala en otras apps (Zoom, Teams, la app Cámara) o
  cambia `CAMERA_INDEX`.
- **Error 500 "'lince' is not a registered tag library"**: reinicia `runserver` (Django
  registra las librerías de plantillas solo al arrancar).
- **"Falta el modelo"**: el archivo `detector/modelos/yolo11n.onnx` viene en el
  repositorio; recupéralo con `git checkout -- detector/modelos`.
- **Las cajas van un poco detrás del movimiento**: es normal en CPU (la red tarda ~0,1 s
  por imagen); el video en sí no se frena.
- **Error de conexión a PostgreSQL**: revisa que el servicio esté iniciado y que los datos
  del `.env` sean correctos.

## Créditos

- Modelo YOLO11n de [Ultralytics](https://github.com/ultralytics/ultralytics), licencia
  AGPL-3.0, entrenado con el dataset [COCO](https://cocodataset.org/). La imagen de prueba
  `bus.jpg` también es de Ultralytics.
