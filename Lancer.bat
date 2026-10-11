@echo off
rem Double-cliquez sur ce fichier pour lancer le generateur de formes.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Premiere utilisation : creation de l environnement Python...
    python -m venv .venv || py -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Python est introuvable. Installez-le depuis https://www.python.org puis relancez.
    pause
    exit /b 1
)
echo Verification des dependances...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
".venv\Scripts\python.exe" lancer.py
pause
