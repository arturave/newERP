@echo off
REM NewERP - Instalacja zależności
REM Uruchom w katalogu projektu z aktywnym venv

echo ==========================================
echo NewERP - Instalacja zaleznosci
echo ==========================================
echo.

REM Podstawowe
echo [1/6] Instalacja podstawowych zaleznosci...
pip install customtkinter pillow python-dotenv requests supabase

REM CAD/DXF
echo.
echo [2/6] Instalacja bibliotek CAD...
pip install ezdxf matplotlib numpy

REM Excel
echo.
echo [3/6] Instalacja obslugi Excel...
pip install openpyxl

REM Nesting zaawansowany
echo.
echo [4/6] Instalacja bibliotek nestingu...
pip install pyclipper shapely

REM Raporty PDF
echo.
echo [5/6] Instalacja generatora PDF...
pip install reportlab

REM Opcjonalne 3D (duże)
echo.
echo [6/6] Biblioteki 3D (opcjonalne, moze trwac dluzej)...
echo Czy chcesz zainstalowac VTK i CadQuery dla miniatur 3D? (T/N)
set /p install_3d=

if /i "%install_3d%"=="T" (
    echo Instalacja VTK...
    pip install vtk
    echo Instalacja CadQuery...
    pip install cadquery
) else (
    echo Pominięto biblioteki 3D
)

echo.
echo ==========================================
echo Instalacja zakonczona!
echo ==========================================
echo.
echo Uruchom: python main.py
echo.
pause
