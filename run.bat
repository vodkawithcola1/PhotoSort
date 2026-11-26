@echo off
REM Uruchamia PhotoSort ze zrodel (pierwsze uruchomienie instaluje biblioteki)
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
start "" pythonw main.py
