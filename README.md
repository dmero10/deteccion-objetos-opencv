# Detector de objetos en tiempo real (Django + OpenCV)

Práctica – Construcción de Software · UNEMI

Aplicativo web que captura video de la cámara con **OpenCV (cv2)**, detecta en tiempo real
80 tipos de objetos con **YOLO11n ejecutado por `cv2.dnn`**, dibuja los resultados sobre el
video y guarda cada avistamiento en **PostgreSQL**. La interfaz web está hecha con **Django**.

**Integrantes:** _(escribir nombres del grupo)_

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
  - 68 pruebas automatizadas (`python manage.py test`): **68 / 68 pasan**.
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

## Instalación

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

Crea la base en PostgreSQL (desde pgAdmin o `psql`):

```sql
CREATE DATABASE deteccion_objetos;
```

Copia `.env.example` como `.env` y escribe tu usuario y contraseña de PostgreSQL.

### Ejecutar

```bash
python manage.py migrate
python manage.py runserver
```

Abre <http://127.0.0.1:8000/> y presiona **Encender cámara** (o la tecla `Espacio`).

Opcional, para ver el historial desde el panel de administración de Django:
`python manage.py createsuperuser` y entra a <http://127.0.0.1:8000/admin/>.

## Pruebas

```bash
python manage.py test                     # 68 pruebas automatizadas (no necesitan cámara)
python scripts/prueba_funcional.py        # con el servidor corriendo y la cámara libre
python scripts/prueba_funcional.py --informe docs/resultado_pruebas.md
```

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
