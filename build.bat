@echo off
REM Buduje PhotoSort.exe (wymaga Pythona 3.12+ w PATH)
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt || goto :error
python tools\make_icon.py
pyinstaller PhotoSort.spec --noconfirm || goto :error
echo.
echo Gotowe: dist\PhotoSort\PhotoSort.exe
dist\PhotoSort\PhotoSort.exe --selftest dist\selftest.txt
type dist\selftest.txt
goto :eof
:error
echo Budowanie nie powiodlo sie.
exit /b 1
