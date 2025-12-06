#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konfiguracja aplikacji NewERP
Manufacturing System dla laserowego cięcia blach

UWAGA: W produkcji użyj pliku .env dla wrażliwych danych!
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Wczytaj zmienne środowiskowe z .env
load_dotenv()

# ============================================================
# SUPABASE - KONFIGURACJA BAZY DANYCH I STORAGE
# ============================================================

SUPABASE_URL = os.getenv(
    "SUPABASE_URL", 
    "https://xcehmhxaoqfpehrfofbu.supabase.co"
)

# SERVICE_ROLE_KEY - pełne uprawnienia (obejście RLS)
# W produkcji ZAWSZE z .env!
SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhjZWhtaHhhb3FmcGVocmZvZmJ1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MDAwMjk3OSwiZXhwIjoyMDc1NTc4OTc5fQ.VojIv2uEU52NSNKcY2Olt1T-s9qdzjvZwWR8lCwaQBA"
)

# ============================================================
# STORAGE - KONFIGURACJA PLIKÓW
# ============================================================

# Nazwa bucketa dla plików produktów
STORAGE_BUCKET = "product_files"

# Bazowa ścieżka w bucket (nowa struktura)
STORAGE_BASE_PATH = "products"

# Rozmiary miniatur (w pikselach)
THUMBNAIL_SIZES = {
    "small": 100,      # Miniatura do list
    "medium": 800,     # Podgląd
}

# Maksymalny rozmiar pliku (50 MB)
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# ============================================================
# KOMPRESJA PLIKÓW
# ============================================================

# Strategia kompresji:
# - "none" = bez kompresji
# - "individual" = każdy plik CAD skompresowany osobno (.gz)
# - "bundle" = wszystkie pliki (bez miniatur) w jednym .zip
# - "hybrid" = CAD i źródła w .gz, miniatury bez kompresji (ZALECANE)
COMPRESSION_STRATEGY = os.getenv("COMPRESSION_STRATEGY", "hybrid")

# Poziom kompresji gzip (1-9, wyższy = lepsza kompresja, wolniejsza)
COMPRESSION_LEVEL = int(os.getenv("COMPRESSION_LEVEL", "6"))

# Czy kompresować obrazy źródłowe (PNG, BMP, TIFF)
COMPRESS_SOURCE_IMAGES = os.getenv("COMPRESS_SOURCE_IMAGES", "true").lower() == "true"

# ============================================================
# DOZWOLONE ROZSZERZENIA PLIKÓW
# ============================================================

ALLOWED_CAD_2D = {'.dxf', '.dwg'}
ALLOWED_CAD_3D = {'.step', '.stp', '.iges', '.igs', '.stl'}
ALLOWED_IMAGES = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff'}
ALLOWED_DOCS = {'.pdf', '.zip', '.7z', '.doc', '.docx', '.xls', '.xlsx', '.rar'}

# Wszystkie dozwolone rozszerzenia
ALLOWED_EXTENSIONS = ALLOWED_CAD_2D | ALLOWED_CAD_3D | ALLOWED_IMAGES | ALLOWED_DOCS

# ============================================================
# CACHE
# ============================================================

# Katalog cache (miniatury, tymczasowe pliki)
CACHE_DIR = Path(os.getenv("CACHE_DIR", Path.home() / ".newerp_cache"))

# Rozmiar cache miniatur w pamięci
THUMBNAIL_CACHE_SIZE = 500

# Czas ważności signed URL (sekundy) - 24h
URL_CACHE_TTL = 86400

# ============================================================
# GUI - USTAWIENIA INTERFEJSU
# ============================================================

# Domyślny rozmiar okna
DEFAULT_WINDOW_SIZE = "1600x900"

# Liczba produktów na stronę w listach
PRODUCTS_PAGE_SIZE = 50

# Wysokość wiersza w TreeView (dla miniatur)
TREEVIEW_ROW_HEIGHT = 45

# Motyw CustomTkinter
CTK_APPEARANCE_MODE = "dark"  # "dark", "light", "system"
CTK_COLOR_THEME = "blue"       # "blue", "green", "dark-blue"

# ============================================================
# PERFORMANCE - OPTYMALIZACJA
# ============================================================

# Rozmiar batch dla operacji bazodanowych
DB_BATCH_SIZE = 50

# Maksymalna liczba równoległych uploadów
MAX_CONCURRENT_UPLOADS = 4

# Timeout dla generowania miniatur (sekundy)
THUMBNAIL_TIMEOUT = 10

# Lazy loading - liczba elementów do załadowania na raz
LAZY_LOAD_BATCH = 20

# ============================================================
# MIME TYPES - MAPOWANIE ROZSZERZEŃ
# ============================================================

MIME_TYPES = {
    # Obrazy
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    
    # CAD 2D
    ".dxf": "application/dxf",
    ".dwg": "application/acad",
    
    # CAD 3D
    ".step": "application/step",
    ".stp": "application/step",
    ".stl": "model/stl",
    ".iges": "model/iges",
    ".igs": "model/iges",
    
    # Dokumenty
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    
    # Archiwa
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/x-rar-compressed",
}


def get_mime_type(filename: str) -> str:
    """
    Zwróć MIME type dla pliku na podstawie rozszerzenia.
    
    Args:
        filename: Nazwa pliku lub ścieżka
        
    Returns:
        MIME type string
    """
    ext = Path(filename).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


def is_allowed_file(filename: str, file_type: str = None) -> bool:
    """
    Sprawdź czy plik ma dozwolone rozszerzenie.
    
    Args:
        filename: Nazwa pliku
        file_type: Opcjonalny typ ('cad_2d', 'cad_3d', 'image', 'doc')
        
    Returns:
        True jeśli dozwolone
    """
    ext = Path(filename).suffix.lower()
    
    if file_type == 'cad_2d':
        return ext in ALLOWED_CAD_2D
    elif file_type == 'cad_3d':
        return ext in ALLOWED_CAD_3D
    elif file_type == 'image':
        return ext in ALLOWED_IMAGES
    elif file_type == 'doc':
        return ext in ALLOWED_DOCS
    else:
        return ext in ALLOWED_EXTENSIONS


# ============================================================
# PRODUKCYJNE INDEKSY KODÓW
# ============================================================

# Prefix dla kodów produktów
PRODUCT_CODE_PREFIX = "PC"

# Prefix dla kodów zamówień
ORDER_CODE_PREFIX = "ZAM"

# Prefix dla kodów ofert
QUOTE_CODE_PREFIX = "OF"


# ============================================================
# WALIDACJA KONFIGURACJI
# ============================================================

def validate_config():
    """
    Sprawdź czy konfiguracja jest poprawna.
    Wywołaj przy starcie aplikacji.
    """
    errors = []
    
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL nie jest ustawiony")
    
    if not SUPABASE_SERVICE_KEY:
        errors.append("SUPABASE_SERVICE_KEY nie jest ustawiony")
    
    if SUPABASE_SERVICE_KEY and len(SUPABASE_SERVICE_KEY) < 100:
        errors.append("SUPABASE_SERVICE_KEY wygląda na niepoprawny (za krótki)")
    
    if errors:
        raise ValueError(f"Błędy konfiguracji: {', '.join(errors)}")
    
    return True


# ============================================================
# INICJALIZACJA
# ============================================================

# Utwórz katalog cache jeśli nie istnieje
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"[WARN] Nie można utworzyć katalogu cache: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("KONFIGURACJA NewERP")
    print("=" * 60)
    print(f"Supabase URL: {SUPABASE_URL}")
    print(f"Storage Bucket: {STORAGE_BUCKET}")
    print(f"Cache Dir: {CACHE_DIR}")
    print(f"Max File Size: {MAX_FILE_SIZE_MB} MB")
    print()
    
    try:
        validate_config()
        print("✅ Konfiguracja poprawna")
    except ValueError as e:
        print(f"❌ {e}")
