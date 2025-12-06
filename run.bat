@echo off
REM ============================================================
REM NewERP - Uruchomienie aplikacji
REM ============================================================

REM Sprawdź czy venv istnieje
if not exist "venv\Scripts\activate.bat" (
    echo [BŁĄD] Wirtualne środowisko nie istnieje!
    echo Uruchom najpierw: setup.bat
    pause
    exit /b 1
)

REM Aktywuj środowisko i uruchom
call venv\Scripts\activate.bat
python main.py %*
