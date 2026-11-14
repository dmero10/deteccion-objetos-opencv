#!/usr/bin/env sh
# Instala (la primera vez) y arranca el Detector de objetos en Linux / macOS.
# Uso: ./iniciar.sh   (necesita Python 3.10+ y PostgreSQL instalados)
cd "$(dirname "$0")" || exit 1
if [ -x venv/bin/python ]; then
  exec venv/bin/python iniciar.py "$@"
fi
exec python3 iniciar.py "$@"
