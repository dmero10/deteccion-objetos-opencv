"""Comando `manage.py preparar_bd`, que usa iniciar.py para crear la base de datos."""
from io import StringIO
from unittest import mock

import psycopg
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

BD = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "mi_base", "USER": "postgres",
                  "PASSWORD": "x", "HOST": "localhost", "PORT": "5432"}}


def conexion_falsa(existe):
    conexion = mock.MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.execute.return_value.fetchone.return_value = (1,) if existe else None
    return conexion


@override_settings(DATABASES=BD)
@mock.patch("detector.management.commands.preparar_bd.puerto_abierto", return_value=True)
class PrepararBdTests(SimpleTestCase):
    def test_crea_la_base_si_no_existe(self, _):
        conexion = conexion_falsa(existe=False)
        salida = StringIO()
        with mock.patch("psycopg.connect", return_value=conexion):
            call_command("preparar_bd", stdout=salida)
        self.assertIn("creada", salida.getvalue())
        self.assertEqual(conexion.execute.call_count, 2)  # consulta + CREATE DATABASE

    def test_no_hace_nada_si_ya_existe(self, _):
        conexion = conexion_falsa(existe=True)
        salida = StringIO()
        with mock.patch("psycopg.connect", return_value=conexion):
            call_command("preparar_bd", stdout=salida)
        self.assertIn("ya existe", salida.getvalue())
        self.assertEqual(conexion.execute.call_count, 1)

    def test_contrasena_incorrecta_devuelve_codigo_3(self, _):
        error = psycopg.OperationalError('password authentication failed for user "postgres"')
        with mock.patch("psycopg.connect", side_effect=error):
            with self.assertRaises(CommandError) as ctx:
                call_command("preparar_bd")
        self.assertEqual(ctx.exception.returncode, 3)
        self.assertIn("DB_PASSWORD", str(ctx.exception))

    def test_sin_servidor_devuelve_codigo_4(self, puerto_abierto):
        puerto_abierto.return_value = False
        with self.assertRaises(CommandError) as ctx:
            call_command("preparar_bd")
        self.assertEqual(ctx.exception.returncode, 4)
