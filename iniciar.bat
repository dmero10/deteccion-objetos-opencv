@echo off
rem Doble clic para instalar (la primera vez) y arrancar el Detector de objetos.
rem Toda la logica esta en iniciar.py; este archivo solo busca Python y lo ejecuta.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Detector de objetos

if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" iniciar.py %*
  goto :fin
)

call :buscar_python
if not defined PYTHON (
  echo.
  echo   No se encontro Python 3.10 o superior en este equipo.
  where winget >nul 2>nul || goto :sin_python
  choice /c SN /m "  Instalar Python 3.12 ahora (S = si, N = no)"
  if errorlevel 2 goto :sin_python
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  call :buscar_python
)
if not defined PYTHON goto :sin_python

%PYTHON% iniciar.py %*
goto :fin

:buscar_python
set "PYTHON="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && (set "PYTHON=py -3" & exit /b 0)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && (set "PYTHON=python" & exit /b 0)
for %%V in (313 312 311 310) do (
  if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
    set PYTHON="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    exit /b 0
  )
)
exit /b 0

:sin_python
echo.
echo   Instala Python 3.12 desde https://www.python.org/downloads/
echo   (marca la casilla "Add python.exe to PATH") y vuelve a abrir iniciar.bat
goto :fin

:fin
echo.
pause
