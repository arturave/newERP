@echo off
REM ============================================================
REM NewERP - Skrypt instalacyjny dla Windows
REM ============================================================

echo.
echo ========================================
echo   NewERP - Instalacja
echo ========================================
echo.

REM Sprawdź czy Python jest dostępny
python --version >nul 2>&1
if errorlevel 1 (
    echo [BŁĄD] Python nie jest zainstalowany lub nie jest w PATH
    echo Pobierz Python z https://python.org
    pause
    exit /b 1
)

echo [OK] Python znaleziony:
python --version

REM Sprawdź czy venv już istnieje
if exist "venv" (
    echo.
    echo [INFO] Wirtualne środowisko już istnieje.
    set /p RECREATE="Czy chcesz je usunąć i utworzyć ponownie? (t/n): "
    if /i "%RECREATE%"=="t" (
        echo [INFO] Usuwanie starego venv...
        rmdir /s /q venv
    ) else (
        echo [INFO] Używam istniejącego środowiska.
        goto :activate
    )
)

REM Utwórz wirtualne środowisko
echo.
echo [INFO] Tworzenie wirtualnego środowiska...
python -m venv venv

if errorlevel 1 (
    echo [BŁĄD] Nie udało się utworzyć venv
    pause
    exit /b 1
)

echo [OK] Wirtualne środowisko utworzone

:activate
REM Aktywuj środowisko
echo.
echo [INFO] Aktywacja środowiska...
call venv\Scripts\activate.bat

REM Aktualizuj pip
echo.
echo [INFO] Aktualizacja pip...
python -m pip install --upgrade pip

REM Instaluj zależności
echo.
echo [INFO] Instalacja zależności...
pip install -r requirements.txt

if errorlevel 1 (
    echo [BŁĄD] Nie udało się zainstalować zależności
    pause
    exit /b 1
)

REM Sprawdź czy .env istnieje
if not exist ".env" (
    if exist ".env.example" (
        echo.
        echo [INFO] Tworzenie pliku .env z szablonu...
        copy .env.example .env
        echo [INFO] Edytuj plik .env i uzupełnij SUPABASE_SERVICE_KEY
    )
)

REM Test połączenia
echo.
echo ========================================
echo   Test połączenia z Supabase
echo ========================================
echo.
python test_connection.py

echo.
echo ========================================
echo   Instalacja zakończona!
echo ========================================
echo.
echo Aby uruchomić aplikację:
echo   1. Aktywuj środowisko: venv\Scripts\activate
echo   2. Uruchom: python main.py
echo.
echo Lub użyj skryptu: run.bat
echo.

pause
