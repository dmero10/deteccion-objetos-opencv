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

## Estructura

```
config/                 Configuración del proyecto (settings, urls)
detector/
  camera.py             Captura con OpenCV, procesamiento y generador MJPEG
  views.py / urls.py    Página, flujo de video, foto y API de estado/control
  templates/detector/   Plantillas HTML
  static/detector/      CSS y JavaScript
  tests.py              Pruebas
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

## Configuración (`.env`)

| Variable | Descripción | Por defecto |
|---|---|---|
| `CAMERA_INDEX` | Índice de la cámara (prueba 1 si la 0 no abre) | 0 |
| `CAMERA_ANCHO` / `CAMERA_ALTO` | Resolución solicitada | 640 / 480 |
| `CAMERA_ESPEJO` | Voltear la imagen horizontalmente (1/0) | 1 |
| `CAMERA_CALIDAD_JPEG` | Calidad del JPEG enviado (1-100) | 80 |
| `CAMERA_APAGADO_INACTIVO` | Segundos sin espectadores antes de apagar la cámara | 15 |

## Solución de problemas

- **"No se pudo abrir la cámara"**: ciérrala en otras apps (Zoom, Teams, la app Cámara) o
  cambia `CAMERA_INDEX`.
- **Error de conexión a PostgreSQL**: revisa que el servicio esté iniciado y que los datos
  del `.env` sean correctos.
