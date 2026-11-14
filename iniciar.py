#!/usr/bin/env python3
"""Instala (la primera vez) y arranca el Detector de objetos con un solo comando.

    Windows:            doble clic en iniciar.bat
    Cualquier sistema:  python iniciar.py

Primera vez: crea el entorno virtual, instala las dependencias, configura la conexión a
PostgreSQL (.env), crea la base de datos y aplica las migraciones.
Siguientes veces: revisa que todo siga en orden (en segundos) y arranca el servidor.

Opciones:
    --reconfigurar     vuelve a preguntar los datos de PostgreSQL (rehace el .env)
    --solo-instalar    prepara todo pero no arranca el servidor
    --sin-navegador    no abre el navegador automáticamente
    --puerto 8000      puerto preferido (si está ocupado se usa el siguiente libre)
"""
import argparse
import getpass
import hashlib
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / "venv"
ES_WINDOWS = os.name == "nt"
PY_VENV = VENV / ("Scripts/python.exe" if ES_WINDOWS else "bin/python")
ENV = RAIZ / ".env"
ENV_EJEMPLO = RAIZ / ".env.example"
REQUISITOS = RAIZ / "requirements.txt"
MARCA_REQUISITOS = VENV / ".requisitos.sha256"
TOTAL_PASOS = 5

# Códigos de salida de "manage.py preparar_bd"
SIN_ACCESO, SIN_SERVIDOR = 3, 4

try:  # acentos y símbolos bien en cualquier consola, y cada línea se muestra al momento
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except (AttributeError, ValueError):
    pass


# --------------------------------------------------------------- mensajes
def paso(n, texto):
    print(f"\n[{n}/{TOTAL_PASOS}] {texto}")


def ok(texto):
    print(f"      ✔ {texto}")


def nota(texto):
    print(f"      · {texto}")


def fallar(texto):
    print(f"\n  ✘ {texto}\n")
    sys.exit(1)


def preguntar(texto, defecto=""):
    sufijo = f" [{defecto}]" if defecto else ""
    try:
        respuesta = input(f"      {texto}{sufijo}: ").strip()
    except EOFError:
        respuesta = ""
    return respuesta or defecto


def preguntar_clave(texto):
    if sys.stdin.isatty():
        return getpass.getpass(f"      {texto} (no se muestra al escribir): ")
    return input(f"      {texto}: ")


def confirmar(texto):
    return preguntar(f"{texto} (S/n)", "s").lower() in ("s", "si", "sí", "y", "yes")


def ejecutar(*args, **kwargs):
    return subprocess.run([str(a) for a in args], cwd=RAIZ, **kwargs)


def manage(*args, **kwargs):
    return ejecutar(PY_VENV, "manage.py", *args, **kwargs)


# --------------------------------------------------------------- utilidades
def leer_env():
    datos = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                datos[clave.strip()] = valor.strip()
    return datos


def escribir_env(cambios):
    """Crea el .env desde .env.example (o actualiza el existente) cambiando solo esas claves."""
    base = ENV if ENV.exists() else ENV_EJEMPLO
    lineas, pendientes = [], dict(cambios)
    for linea in base.read_text(encoding="utf-8").splitlines():
        clave = linea.split("=", 1)[0].strip()
        if "=" in linea and not linea.lstrip().startswith("#") and clave in pendientes:
            linea = f"{clave}={pendientes.pop(clave)}"
        lineas.append(linea)
    lineas += [f"{clave}={valor}" for clave, valor in pendientes.items()]
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def puerto_abierto(host, puerto, espera=1.5):
    try:
        with socket.create_connection((host, int(puerto)), timeout=espera):
            return True
    except OSError:
        return False


def esperar_puerto(host, puerto, segundos):
    limite = time.time() + segundos
    while time.time() < limite:
        if puerto_abierto(host, puerto):
            return True
        time.sleep(1)
    return False


def primer_puerto_libre(desde):
    for puerto in range(desde, desde + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", puerto))
                return puerto
            except OSError:
                continue
    fallar(f"No hay puertos libres entre {desde} y {desde + 19}.")


# ------------------------------------------------------ paso 1: entorno
def preparar_entorno():
    paso(1, "Entorno virtual de Python")
    if sys.version_info < (3, 10):
        fallar(f"Se necesita Python 3.10 o superior (tienes {sys.version.split()[0]}).")
    if PY_VENV.exists():
        ok("ya existe (carpeta venv)")
        return
    nota(f"creando con Python {sys.version.split()[0]}...")
    if ejecutar(sys.executable, "-m", "venv", VENV).returncode != 0 or not PY_VENV.exists():
        fallar("No se pudo crear el entorno virtual.")
    ok("creado en la carpeta venv")


# ------------------------------------------------- paso 2: dependencias
def instalar_dependencias():
    paso(2, "Dependencias (Django, OpenCV, psycopg)")
    huella = hashlib.sha256(REQUISITOS.read_bytes()).hexdigest()
    if MARCA_REQUISITOS.exists() and MARCA_REQUISITOS.read_text().strip() == huella:
        ok("ya instaladas")
        return
    nota("instalando... la primera vez tarda 1-3 minutos (descarga ~70 MB)")
    r = ejecutar(PY_VENV, "-m", "pip", "install", "--disable-pip-version-check", "-r", REQUISITOS)
    if r.returncode != 0:
        fallar("Falló la instalación de dependencias. Revisa tu conexión a internet y vuelve a intentar.")
    MARCA_REQUISITOS.write_text(huella)
    ok("instaladas")


# --------------------------------------------------- paso 3: PostgreSQL
def servicios_postgresql_windows():
    """Nombres de los servicios de PostgreSQL instalados en Windows (o lista vacía)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Service postgresql* -ErrorAction SilentlyContinue | ForEach-Object { $_.Name + '|' + $_.Status }"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [linea.split("|") for linea in r.stdout.split() if "|" in linea]


def encender_servicio_windows(nombre):
    nota(f"el servicio '{nombre}' está detenido; Windows pedirá permiso para encenderlo")
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command','Start-Service {nombre}'"],
    )


def pedir_clave_nueva():
    while True:
        clave = preguntar_clave("Elige una contraseña para PostgreSQL")
        if len(clave) < 4 or any(c in clave for c in " \"'"):
            nota("usa al menos 4 caracteres, sin espacios ni comillas")
            continue
        if preguntar_clave("Repítela") == clave:
            return clave
        nota("no coinciden, intenta de nuevo")


def instalar_postgresql_windows():
    if not shutil.which("winget"):
        fallar("No encontré winget para instalar PostgreSQL automáticamente.\n"
               "    Descárgalo de https://www.postgresql.org/download/windows/ , instálalo y vuelve a ejecutar.")
    print("\n      PostgreSQL no está instalado. Se puede instalar ahora (PostgreSQL 17, ~300 MB).")
    print("      Windows pedirá permiso de administrador.")
    if not confirmar("¿Instalar PostgreSQL ahora?"):
        fallar("Instala PostgreSQL y vuelve a ejecutar iniciar.")
    clave = pedir_clave_nueva()
    nota("instalando PostgreSQL... puede tardar unos minutos")
    r = subprocess.run([
        "winget", "install", "-e", "--id", "PostgreSQL.PostgreSQL.17", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements", "--override",
        f"--mode unattended --unattendedmodeui minimal --superpassword {clave} "
        "--serverport 5432 --disable-components stackbuilder",
    ])
    if r.returncode != 0 or not esperar_puerto("localhost", 5432, 90):
        fallar("No se pudo instalar o encender PostgreSQL. Instálalo a mano desde postgresql.org.")
    ok("PostgreSQL instalado (usuario: postgres, guarda bien la contraseña que elegiste)")
    return clave


def asegurar_servidor_postgresql(host, puerto):
    """Devuelve una contraseña si hubo que instalar PostgreSQL, o None si ya estaba."""
    if puerto_abierto(host, puerto):
        ok(f"PostgreSQL responde en {host}:{puerto}")
        return None
    if host not in ("localhost", "127.0.0.1") or not ES_WINDOWS:
        fallar(f"No hay PostgreSQL en {host}:{puerto}. Instálalo o enciéndelo y vuelve a ejecutar.")

    servicios = servicios_postgresql_windows()
    if servicios:
        for nombre, estado in servicios:
            if estado.lower() != "running":
                encender_servicio_windows(nombre)
        if esperar_puerto(host, puerto, 30):
            ok("PostgreSQL encendido")
            return None
        fallar(f"PostgreSQL está instalado pero no responde en el puerto {puerto}.\n"
               "    Ábrelo desde 'Servicios' de Windows o revisa DB_PORT en el .env.")
    return instalar_postgresql_windows()


def configurar_postgresql(reconfigurar):
    paso(3, "Conexión a PostgreSQL")
    env = leer_env() if ENV.exists() and not reconfigurar else {}
    host, puerto = env.get("DB_HOST", "localhost"), env.get("DB_PORT", "5432")
    clave_instalacion = asegurar_servidor_postgresql(host, puerto)

    if env and clave_instalacion is None:
        ok(".env ya configurado")
    else:
        cambios = {"SECRET_KEY": leer_env().get("SECRET_KEY") or secrets.token_urlsafe(40)}
        if clave_instalacion:
            cambios.update(DB_USER="postgres", DB_PASSWORD=clave_instalacion)
        else:
            print("\n      Escribe los datos de tu PostgreSQL (los que pusiste al instalarlo).")
            cambios["DB_USER"] = preguntar("Usuario", "postgres")
            cambios["DB_PASSWORD"] = preguntar_clave("Contraseña")
        escribir_env(cambios)
        ok(".env creado (no se sube a GitHub)")

    for intento in range(3):
        r = manage("preparar_bd", capture_output=True, text=True)
        if r.returncode == 0:
            ok(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "base de datos lista")
            return
        if r.returncode == SIN_ACCESO and intento < 2:
            nota("PostgreSQL rechazó el usuario o la contraseña")
            usuario = preguntar("Usuario", leer_env().get("DB_USER", "postgres"))
            escribir_env({"DB_USER": usuario, "DB_PASSWORD": preguntar_clave("Contraseña")})
            continue
        mensaje = (r.stderr or r.stdout).strip().replace("CommandError: ", "")
        fallar(mensaje or "No se pudo preparar la base de datos.")
    fallar("Demasiados intentos. Revisa DB_USER y DB_PASSWORD en el archivo .env.")


# ---------------------------------------------------- paso 4: migraciones
def migrar():
    paso(4, "Tablas de la base de datos (migraciones)")
    r = manage("migrate", "--noinput", capture_output=True, text=True)
    if r.returncode != 0:
        fallar(f"Falló 'migrate':\n{r.stderr or r.stdout}")
    aplicadas = [l for l in r.stdout.splitlines() if l.strip().startswith("Applying")]
    ok(f"{len(aplicadas)} migraciones aplicadas" if aplicadas else "al día")


# ------------------------------------------------------- paso 5: servidor
def arrancar(puerto_preferido, abrir_navegador):
    paso(5, "Servidor")
    puerto = primer_puerto_libre(puerto_preferido)
    if puerto != puerto_preferido:
        nota(f"el puerto {puerto_preferido} está ocupado, uso el {puerto}")
    url = f"http://127.0.0.1:{puerto}/"
    proceso = subprocess.Popen([str(PY_VENV), "manage.py", "runserver", f"127.0.0.1:{puerto}"], cwd=RAIZ)

    limite = time.time() + 60
    while time.time() < limite and proceso.poll() is None:
        try:
            urllib.request.urlopen(url + "api/estado/", timeout=2)
            break
        except OSError:
            time.sleep(0.7)
    if proceso.poll() is not None:
        fallar("El servidor se cerró al arrancar; revisa el mensaje de arriba.")

    ancho = 54
    print("\n  ┌" + "─" * ancho + "┐")
    print(f"  │  {'Listo: abre ' + url:<{ancho - 2}}│")
    print(f"  │  {'Para detener el servidor: Ctrl + C en esta ventana':<{ancho - 2}}│")
    print("  └" + "─" * ancho + "┘\n")
    if abrir_navegador:
        webbrowser.open(url)
    try:
        proceso.wait()
    except KeyboardInterrupt:
        print("\nDeteniendo el servidor...")
        proceso.terminate()
        try:
            proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proceso.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reconfigurar", action="store_true")
    parser.add_argument("--solo-instalar", action="store_true")
    parser.add_argument("--sin-navegador", action="store_true")
    parser.add_argument("--puerto", type=int, default=8000)
    args = parser.parse_args()

    print("\n  Detector de objetos — Django + OpenCV + PostgreSQL")
    preparar_entorno()
    instalar_dependencias()
    configurar_postgresql(args.reconfigurar)
    migrar()
    if args.solo_instalar:
        print("\n  Todo listo. Para arrancar: iniciar.bat (o python iniciar.py)\n")
        return
    arrancar(args.puerto, not args.sin_navegador)


if __name__ == "__main__":
    main()
