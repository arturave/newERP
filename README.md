# 🏭 NewERP - Manufacturing System

System ERP do zarządzania produkcją laserowego cięcia blach.

## 🚀 Szybki start

### 1. Instalacja zależności

**Windows (zalecane):**
```cmd
cd NewERP
install_deps.bat
```

**Lub ręcznie:**
```bash
pip install -r requirements.txt
```

### 2. Uruchomienie
```bash
python main.py
```

## 📦 Biblioteki nestingu

System obsługuje 3 algorytmy nestingu z różnymi wymaganiami:

| Algorytm | Biblioteka | Jakość | Szybkość |
|----------|------------|--------|----------|
| **FFDH** | (wbudowany) | ⭐⭐ | ⚡⚡⚡⚡⚡ |
| **NFP** | `pyclipper` | ⭐⭐⭐⭐ | ⚡⚡⚡ |
| **Shapely** | `shapely` | ⭐⭐⭐⭐⭐ | ⚡⚡ |

**Instalacja bibliotek nestingu:**
```bash
pip install pyclipper shapely
```

**Instalacja obsługi Excel (cenniki):**
```bash
pip install openpyxl
```

## 📁 Struktura projektu

```
NewERP/
├── venv/                        # 🔒 Wirtualne środowisko (po instalacji)
├── config/                      # Konfiguracja
│   ├── __init__.py
│   └── settings.py              # Ustawienia (Supabase, Storage, GUI)
│
├── core/                        # Podstawowe komponenty
│   ├── __init__.py
│   └── supabase_client.py       # Singleton klienta Supabase
│
├── products/                    # 🎯 Moduł produktów
│   ├── __init__.py              # Eksporty modułu
│   ├── paths.py                 # StoragePaths - deterministyczne ścieżki
│   ├── storage.py               # StorageRepository - operacje na plikach
│   ├── repository.py            # ProductRepository - operacje DB
│   ├── service.py               # ProductService - logika biznesowa
│   ├── gui/                     # Interfejs użytkownika
│   │   ├── __init__.py
│   │   ├── products_window.py   # Główne okno katalogu produktów
│   │   └── product_edit_dialog.py # Dialog edycji produktu
│   └── utils/                   # Narzędzia (miniatury, walidacja)
│
├── migrations/                  # Migracje SQL
│   └── 001_products_url_to_path.sql
│
├── tests/                       # Testy
│
├── .env                         # 🔒 Konfiguracja lokalna (po instalacji)
├── .env.example                 # Szablon konfiguracji
├── .gitignore                   # Ignorowane pliki Git
├── main.py                      # 🚀 Główny plik uruchomieniowy
├── setup.bat                    # 🛠️ Instalacja (Windows)
├── setup.sh                     # 🛠️ Instalacja (Linux/Mac)
├── run.bat                      # ▶️ Uruchomienie (Windows)
├── requirements.txt             # Zależności Python
├── test_connection.py           # Test połączenia
└── README.md                    # Ten plik
```

## 🚀 Szybki start

### Opcja 1: Automatyczna instalacja (zalecana)

**Windows:**
```cmd
cd C:\Users\artur\source\repos\arturave\NewERP
setup.bat
```

**Linux/Mac:**
```bash
cd NewERP
chmod +x setup.sh
./setup.sh
```

Skrypt automatycznie:
- Utworzy wirtualne środowisko `venv/`
- Zainstaluje wszystkie zależności
- Utworzy plik `.env` z szablonu
- Uruchomi test połączenia

### Opcja 2: Ręczna instalacja

```bash
# 1. Utwórz wirtualne środowisko
python -m venv venv

# 2. Aktywuj środowisko
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Zainstaluj zależności
pip install -r requirements.txt

# 4. Skopiuj konfigurację (opcjonalne - klucz jest w settings.py)
copy .env.example .env

# 5. Test połączenia
python test_connection.py
```

### Uruchomienie aplikacji

**Windows (po instalacji):**
```cmd
run.bat
```

**Lub ręcznie:**
```bash
# Aktywuj środowisko (jeśli nie aktywne)
venv\Scripts\activate   # Windows
source venv/bin/activate # Linux/Mac

# Uruchom
python main.py
```

### Migracja bazy (opcjonalna)

**UWAGA:** Twoja baza już ma kolumny `*_path` - migracja NIE jest potrzebna!

## 📖 Użycie

### Podstawowe operacje na produktach

```python
from products import create_product_service

# Utwórz serwis
service = create_product_service()

# Lista produktów
products = service.list_products(
    filters={'category': 'BLACHY'},
    search='wspornik',
    limit=20
)

# Utwórz produkt
with open('rysunek.dxf', 'rb') as f:
    dxf_data = f.read()

success, product_id = service.create_product(
    data={
        'name': 'Wspornik montażowy A',
        'thickness_mm': 2.0,
        'material_id': 'uuid-materiału',
        'category': 'WSPORNIKI',
        'bending_cost': 15.0
    },
    files={'cad_2d': dxf_data},
    file_extensions={'cad_2d': 'dxf'}
)

# Pobierz produkt z URL do plików
product = service.get_product(product_id)
print(product['thumbnail_100_url'])

# Dodaj załącznik
with open('dokumentacja.pdf', 'rb') as f:
    pdf_data = f.read()

success, att_id = service.add_attachment(
    product_id,
    pdf_data,
    'dokumentacja_techniczna.pdf',
    note='Dokumentacja dla klienta'
)

# Pobierz załączniki
attachments = service.get_attachments(product_id)
for att in attachments:
    print(f"{att['original_filename']}: {att['signed_url']}")
```

### Generowanie ścieżek Storage

```python
from products import StoragePaths

product_id = "abc-123-def"

# Ścieżki do plików
cad_path = StoragePaths.cad_2d(product_id, "dxf")
# → "products/abc-123-def/cad/2d/cad_2d.dxf"

thumb_path = StoragePaths.thumbnail_100(product_id)
# → "products/abc-123-def/images/previews/thumbnail_100.png"

# URL publiczny
url = StoragePaths.get_public_url(thumb_path)
```

## 🏗️ Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                         GUI LAYER                            │
│  (products.gui - w trakcie implementacji)                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ProductService                            │
│  - create_product()   - update_product()                    │
│  - delete_product()   - get_product()                       │
│  - list_products()    - add_attachment()                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
┌─────────────────────────┐   ┌─────────────────────────────┐
│   ProductRepository     │   │     StorageRepository       │
│   (Supabase DB)         │   │     (Supabase Storage)      │
└─────────────────────────┘   └─────────────────────────────┘
```

## 📂 Struktura Storage

```
product_files/
└── products/
    └── {product_id}/
        ├── cad/
        │   ├── 2d/cad_2d.{ext}      ← STAŁA NAZWA (upsert=true)
        │   └── 3d/cad_3d.{ext}      ← STAŁA NAZWA (upsert=true)
        ├── images/
        │   ├── source/user_image.{ext}
        │   └── previews/
        │       ├── thumbnail_100.png
        │       ├── preview_800.png
        │       └── preview_4k.png
        └── attachments/
            └── {attachment_id}/
                └── {original_filename}
```

## 🔧 Konfiguracja

Główne ustawienia w `config/settings.py`:

| Ustawienie | Opis | Domyślna wartość |
|------------|------|------------------|
| `SUPABASE_URL` | URL projektu Supabase | - |
| `SUPABASE_SERVICE_KEY` | Klucz SERVICE_ROLE | - |
| `STORAGE_BUCKET` | Nazwa bucketa | `product_files` |
| `MAX_FILE_SIZE_MB` | Max rozmiar pliku | `50` MB |
| `THUMBNAIL_SIZES` | Rozmiary miniatur | `100, 800, 4096` |

## 📝 Migracja z poprzedniej wersji

1. **Backup bazy i Storage** - KRYTYCZNE!
2. Uruchom migrację SQL
3. Skopiuj pliki do nowej struktury katalogów
4. Zaktualizuj importy w aplikacji

## 🧪 Testy

```bash
# Test połączenia
python test_connection.py

# Testy jednostkowe (TODO)
pytest tests/
```

## 📅 Historia zmian

- **v2.1.0** (2025-12-02) - Nowy moduł nestingu:
  - FastNester (rectpack) z trybami FAST/DEEP
  - Grupowanie detali po materiale/grubości
  - Alokacja kosztów proporcjonalna do powierzchni netto
  - Panel NestingGroupPanel z wizualizacją
- **v2.0.0** (2025-11-28) - Nowa architektura, refaktoryzacja modułu produktów
- **v1.x** - Poprzednia wersja (ManufacturingSystem)

## 🔧 Moduł Nestingu

### FastNester (nowy!)

```python
from quotations.nesting import FastNester, NestingMode, MaterialGroupManager

# Prosty nesting
nester = FastNester(sheet_width=1500, sheet_height=3000, spacing=5)
nester.add_part({'name': 'Part_A', 'width': 100, 'height': 80, 'area': 8000}, quantity=10)
result = nester.run(NestingMode.DEEP)
print(f"Efektywność: {result.efficiency:.1%}")

# Grupowany nesting per materiał/grubość
manager = MaterialGroupManager()
manager.add_part({'name': 'Part_A', 'material': 'INOX', 'thickness': 2.0, ...}, quantity=10)
manager.add_part({'name': 'Part_B', 'material': 'INOX', 'thickness': 3.0, ...}, quantity=5)
results = manager.run_all_nestings()
print(f"Koszt całkowity: {manager.get_total_cost():.2f} PLN")
```

### Algorytmy nestingu

| Algorytm | Biblioteka | Tryb | Próby | Czas |
|----------|------------|------|-------|------|
| **FastNester FAST** | rectpack | Szybki | 3 | ~0.1s |
| **FastNester DEEP** | rectpack | Głęboki | 74+ | ~0.5s |
| **FFDH** | (wbudowany) | Legacy | 1 | <0.01s |
| **NFP** | pyclipper | Legacy | 1 | ~1s |
| **Shapely** | shapely | Legacy | 1 | ~2s |

## 👥 Autorzy

NewERP Team
