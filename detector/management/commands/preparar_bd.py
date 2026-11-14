"""Crea en PostgreSQL la base de datos configurada en el .env, si todavía no existe.

Uso:  python manage.py preparar_bd

Códigos de salida (los usa iniciar.py para guiar al usuario):
  0  la base existe o se creó
  3  PostgreSQL responde pero rechazó el usuario o la contraseña
  4  no hay un servidor PostgreSQL escuchando en DB_HOST:DB_PORT
"""
import socket

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SIN_ACCESO = 3
SIN_SERVIDOR = 4


def puerto_abierto(host, puerto, espera=2.0):
    try:
        with socket.create_connection((host, int(puerto)), timeout=espera):
            return True
    except OSError:
        return False


class Command(BaseCommand):
    help = "Crea la base de datos PostgreSQL del .env si no existe."

    def handle(self, *args, **opciones):
        cfg = settings.DATABASES["default"]
        if "postgresql" not in cfg["ENGINE"]:
            self.stdout.write("La base configurada no es PostgreSQL; no hay nada que preparar.")
            return

        host, puerto = cfg.get("HOST") or "localhost", cfg.get("PORT") or "5432"
        nombre = cfg["NAME"]
        if not puerto_abierto(host, puerto):
            raise CommandError(
                f"No hay un servidor PostgreSQL en {host}:{puerto}. ¿Está instalado y encendido?",
                returncode=SIN_SERVIDOR,
            )

        import psycopg
        from psycopg import sql

        try:
            # Se conecta a la base de mantenimiento "postgres", que siempre existe
            with psycopg.connect(
                dbname="postgres", user=cfg["USER"], password=cfg["PASSWORD"],
                host=host, port=puerto, autocommit=True, connect_timeout=5,
            ) as conexion:
                existe = conexion.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", [nombre]
                ).fetchone()
                if existe:
                    self.stdout.write(f"La base de datos '{nombre}' ya existe.")
                    return
                conexion.execute(
                    sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(nombre))
                )
        except psycopg.OperationalError as exc:
            lineas = [l.strip() for l in str(exc).splitlines() if l.strip()]
            detalle = next((l for l in lineas if "FATAL" in l), lineas[0] if lineas else "")
            # PostgreSQL en español a veces llega con caracteres mal codificados
            detalle = detalle.replace("\\ufffd", "?").replace("�", "?")
            raise CommandError(
                f"PostgreSQL rechazó la conexión del usuario '{cfg['USER']}'. "
                f"Revisa DB_USER y DB_PASSWORD en el .env.\nDetalle: {detalle}",
                returncode=SIN_ACCESO,
            ) from exc

        self.stdout.write(self.style.SUCCESS(f"Base de datos '{nombre}' creada."))
