"""Configuración del proyecto Django.

Los valores sensibles (clave secreta, credenciales de PostgreSQL) se leen
del archivo .env, que no se sube al repositorio. Ver .env.example.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env():
    """Carga un archivo .env sencillo (CLAVE=valor) sin dependencias extra."""
    ruta = BASE_DIR / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip())


_cargar_env()

SECRET_KEY = os.environ.get("SECRET_KEY", "clave-solo-para-desarrollo-cambiar")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "detector",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de datos: PostgreSQL (requisito de la práctica).
# DB_ENGINE=sqlite solo existe para correr pruebas rápidas sin PostgreSQL.
if os.environ.get("DB_ENGINE") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "deteccion_objetos"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cámara (OpenCV) ---
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAMERA_ANCHO = int(os.environ.get("CAMERA_ANCHO", "640"))
CAMERA_ALTO = int(os.environ.get("CAMERA_ALTO", "480"))
CAMERA_ESPEJO = os.environ.get("CAMERA_ESPEJO", "1") == "1"
CAMERA_CALIDAD_JPEG = int(os.environ.get("CAMERA_CALIDAD_JPEG", "80"))
# Segundos sin espectadores antes de apagar la cámara automáticamente
CAMERA_APAGADO_INACTIVO = float(os.environ.get("CAMERA_APAGADO_INACTIVO", "15"))

# --- Detector de objetos (YOLO11 en ONNX, ejecutado con cv2.dnn) ---
MODELOS_DIR = BASE_DIR / "detector" / "modelos"
# Nombre del archivo en detector/modelos/<nombre>.onnx (ver scripts/exportar_modelo.py)
DETECTOR_MODELO = os.environ.get("DETECTOR_MODELO", "yolo11n")
DETECTOR_ACTIVO = os.environ.get("DETECTOR_ACTIVO", "1") == "1"
# Confianza mínima (0-1) para mostrar un objeto
DETECTOR_CONFIANZA = float(os.environ.get("DETECTOR_CONFIANZA", "0.45"))
# Umbral de NMS para eliminar cajas repetidas sobre el mismo objeto
DETECTOR_NMS = float(os.environ.get("DETECTOR_NMS", "0.45"))

# --- Bitácora de avistamientos (PostgreSQL) ---
# Guardar automáticamente los objetos detectados (1/0)
DETECTOR_REGISTRAR = os.environ.get("DETECTOR_REGISTRAR", "1") == "1"
# Segundos mínimos entre dos registros de la misma clase de objeto
DETECTOR_INTERVALO_REGISTRO = float(os.environ.get("DETECTOR_INTERVALO_REGISTRO", "15"))
# Tamaño máximo de una imagen subida en "Analizar imagen" (MB)
ANALIZAR_MAX_MB = float(os.environ.get("ANALIZAR_MAX_MB", "8"))
