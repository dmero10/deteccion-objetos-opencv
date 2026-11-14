# Detector de objetos en tiempo real (Django + OpenCV)

Práctica – Construcción de Software · UNEMI

Aplicativo web que captura video de la cámara con **OpenCV (cv2)**, lo procesa en tiempo
real y lo muestra en una interfaz web hecha con **Django**. Base de datos: **PostgreSQL**.

**Integrantes:** _(escribir nombres del grupo)_

## Avance por sesión

### Sesión 1 – Configuración inicial y video en tiempo real ✅
- Proyecto Django (`config`) y aplicación base (`detector`).
- Conexión a PostgreSQL configurada mediante `.env`.
- Captura de video con `cv2.VideoCapture` en un hilo propio (la cámara se abre una sola vez
  aunque haya varias pestañas abiertas).
- Procesamiento con OpenCV en cada frame (efecto espejo, marca de fecha/hora y FPS).
- Transmisión en vivo al navegador como flujo **MJPEG** (`multipart/x-mixed-replace`).
- Interfaz con botones Iniciar / Detener / Capturar foto y panel de estado (FPS, resolución,
  espectadores) actualizado cada segundo.
- Pruebas automatizadas con una cámara simulada.

### Sesión 2 – Procesamiento y detección ✅
- Módulo de detección de objetos con el **módulo DNN de OpenCV** (`cv2.dnn`), ejecutando
  la red **YOLO11n** (Ultralytics) exportada a ONNX y entrenada con COCO: **80 clases**
  (persona, celular, laptop, botella, silla, taza...). No usa PyTorch ni TensorFlow:
  OpenCV carga la red (`readNetFromONNX`), prepara la imagen (`blobFromImage`), hace la
  inferencia y aplica NMS por clase (`NMSBoxesBatched`) para eliminar cajas repetidas.
- La detección corre en **un hilo aparte** sobre el frame más reciente: el video va a la
  velocidad de la cámara y las cajas se actualizan unas 8 veces por segundo en CPU.
- Resultados dibujados **directamente en el video** con `cv2.rectangle` y `cv2.putText`:
  caja de color por clase, nombre en español y porcentaje de confianza.
- Panel en vivo con los objetos en pantalla (cantidad y confianza), tiempo de inferencia y
  detecciones por segundo.
- Controles sin reiniciar el video: activar/desactivar la detección y ajustar la
  confianza mínima.

#### Elección del modelo

Se compararon tres modelos con OpenCV DNN en CPU, con imágenes de prueba de Ultralytics
(`bus.jpg`: 4 personas y un bus; `zidane.jpg`: 2 personas y una corbata):

| Modelo | mAP COCO | Tiempo por imagen | Resultado |
|---|---|---|---|
| YOLOv4-tiny | ~22 | ~45 ms | Omite una persona; confianza baja con la webcam |
| YOLOv8n | 37.3 | ~115 ms | Todas las personas, sin la corbata |
| **YOLO11n** | **39.5** | ~113 ms | **Todas las personas, el bus y la corbata** |

Se eligió **YOLO11n**: misma velocidad que YOLOv8n y más precisión. Con la webcam, la
confianza al detectar una persona subió de 57–77 % (YOLOv4-tiny) a 84–94 %.

## Estructura

```
config/                 Configuración del proyecto (settings, urls)
detector/
  camera.py             Captura con OpenCV (hilo de video + hilo de detección) y MJPEG
  yolo.py               Detección de objetos (cv2.dnn + YOLO11n) y dibujo de resultados
  clases.py             Las 80 clases de COCO (inglés / español)
  modelos/yolo11n.onnx  Modelo ya exportado (~11 MB, incluido en el repositorio)
  views.py / urls.py    Página, flujo de video, foto y API de estado/control
  templates/detector/   Plantillas HTML
  static/detector/      CSS y JavaScript
  tests.py              Pruebas
scripts/
  exportar_modelo.py    Cómo se generó el .onnx (opcional, requiere Ultralytics)
manage.py
requirements.txt
.env.example            Plantilla de configuración
```

## Instalación

Requisitos: Python 3.10+, PostgreSQL 14+ y una cámara web.

```bash
git clone <URL_DEL_REPOSITORIO>
cd <carpeta_del_repositorio>

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

Abre <http://127.0.0.1:8000/> y presiona **Iniciar**.

## Pruebas

```bash
python manage.py test
```

## Rutas

| Ruta | Método | Descripción |
|---|---|---|
| `/` | GET | Página principal con el video |
| `/video/` | GET | Flujo MJPEG de la cámara |
| `/foto/` | GET | Descarga el frame actual en JPEG |
| `/api/estado/` | GET | Estado de la cámara en JSON |
| `/api/camara/iniciar/` | POST | Enciende la cámara |
| `/api/camara/detener/` | POST | Apaga la cámara |
| `/api/deteccion/` | POST | Configura la detección: `{"activa": true, "confianza": 0.5}` |

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

## Solución de problemas

- **"No se pudo abrir la cámara"**: ciérrala en otras apps (Zoom, Teams, la app Cámara) o
  cambia `CAMERA_INDEX`.
- **"Falta el modelo"**: el archivo `detector/modelos/yolo11n.onnx` viene en el
  repositorio; recupéralo con `git checkout -- detector/modelos`.
- **Las cajas van un poco detrás del movimiento**: es normal en CPU (la red tarda ~0.1 s
  por imagen); el video en sí no se frena.
- **Error de conexión a PostgreSQL**: revisa que el servicio esté iniciado y que los datos
  del `.env` sean correctos.

## Créditos

- Modelo YOLO11n de [Ultralytics](https://github.com/ultralytics/ultralytics), distribuido
  bajo licencia AGPL-3.0, entrenado con el dataset [COCO](https://cocodataset.org/).
