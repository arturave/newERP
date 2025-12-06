#!/bin/bash
# ============================================================
# NewERP - Skrypt instalacyjny dla Linux/Mac
# ============================================================

echo ""
echo "========================================"
echo "  NewERP - Instalacja"
echo "========================================"
echo ""

# Sprawdź Python
if ! command -v python3 &> /dev/null; then
    echo "[BŁĄD] Python3 nie jest zainstalowany"
    exit 1
fi

echo "[OK] Python znaleziony:"
python3 --version

# Sprawdź czy venv istnieje
if [ -d "venv" ]; then
    echo ""
    echo "[INFO] Wirtualne środowisko już istnieje."
    read -p "Czy chcesz je usunąć i utworzyć ponownie? (t/n): " RECREATE
    if [ "$RECREATE" = "t" ] || [ "$RECREATE" = "T" ]; then
        echo "[INFO] Usuwanie starego venv..."
        rm -rf venv
    else
        echo "[INFO] Używam istniejącego środowiska."
        source venv/bin/activate
        pip install -r requirements.txt
        exit 0
    fi
fi

# Utwórz venv
echo ""
echo "[INFO] Tworzenie wirtualnego środowiska..."
python3 -m venv venv

if [ $? -ne 0 ]; then
    echo "[BŁĄD] Nie udało się utworzyć venv"
    exit 1
fi

echo "[OK] Wirtualne środowisko utworzone"

# Aktywuj
echo ""
echo "[INFO] Aktywacja środowiska..."
source venv/bin/activate

# Aktualizuj pip
echo ""
echo "[INFO] Aktualizacja pip..."
pip install --upgrade pip

# Instaluj zależności
echo ""
echo "[INFO] Instalacja zależności..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "[BŁĄD] Nie udało się zainstalować zależności"
    exit 1
fi

# .env
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo ""
    echo "[INFO] Tworzenie pliku .env z szablonu..."
    cp .env.example .env
    echo "[INFO] Edytuj plik .env i uzupełnij SUPABASE_SERVICE_KEY"
fi

# Test
echo ""
echo "========================================"
echo "  Test połączenia z Supabase"
echo "========================================"
echo ""
python test_connection.py

echo ""
echo "========================================"
echo "  Instalacja zakończona!"
echo "========================================"
echo ""
echo "Aby uruchomić aplikację:"
echo "  1. Aktywuj środowisko: source venv/bin/activate"
echo "  2. Uruchom: python main.py"
echo ""
