@echo off
rem Doble clic para ejecutar todas las pruebas y ver la cobertura del codigo.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Pruebas - Detector de objetos
set "PY=venv\Scripts\python.exe"
set "FALLO="

if not exist "%PY%" (
  echo.
  echo   Primero ejecuta iniciar.bat para instalar el proyecto.
  goto :fin
)

echo.
echo   Revisando que PostgreSQL y la base de datos esten listos...
"%PY%" iniciar.py --solo-instalar >nul || (
  "%PY%" iniciar.py --solo-instalar
  goto :fin
)
"%PY%" -m pip install -q --disable-pip-version-check -r requirements-dev.txt

echo.
echo   ============ 1/3  PRUEBAS UNITARIAS (sin base de datos ni camara) ============
"%PY%" -m coverage run manage.py test detector.tests.unitarias -v 2 || set "FALLO=1"

echo.
echo   ============ 2/3  PRUEBAS DE INTEGRACION (Django + PostgreSQL) ============
"%PY%" -m coverage run --append manage.py test detector.tests.integracion -v 2 || set "FALLO=1"

echo.
echo   ============ 3/3  PRUEBAS FUNCIONALES (navegador Edge automatico) ============
echo   Las capturas de cada paso quedan en docs\evidencias
"%PY%" -m coverage run --append manage.py test detector.tests.funcionales -v 2 || set "FALLO=1"

echo.
echo   ============ COBERTURA DEL CODIGO ============
"%PY%" -m coverage report
"%PY%" -m coverage html >nul && start "" "docs\cobertura\index.html"

echo.
if defined FALLO (
  echo   RESULTADO: hay pruebas que FALLARON. Revisa los mensajes de arriba.
) else (
  echo   RESULTADO: todas las pruebas pasaron.
)

:fin
echo.
pause
