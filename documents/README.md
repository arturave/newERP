# Moduł Dokumentów - NewERP

## Spis treści

1. [Wprowadzenie](#wprowadzenie)
2. [Architektura](#architektura)
3. [Instalacja](#instalacja)
4. [Szybki start](#szybki-start)
5. [Typy dokumentów](#typy-dokumentów)
6. [API Reference](#api-reference)
7. [Szablony HTML](#szablony-html)
8. [Baza danych](#baza-danych)
9. [Konfiguracja](#konfiguracja)
10. [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Wprowadzenie

Moduł dokumentów zapewnia elastyczny mechanizm generowania dokumentów PDF w systemie NewERP. Obsługuje dokumenty handlowe (oferty, faktury), magazynowe (WZ) oraz transportowe (CMR).

### Główne funkcje

- Generowanie PDF z szablonów HTML/CSS (Jinja2 + WeasyPrint)
- Automatyczna numeracja dokumentów z gwarancją unikalności
- Wersjonowanie szablonów w bazie danych
- Przechowywanie dokumentów w Supabase Storage
- Podgląd HTML przed generowaniem PDF
- Pełna obsługa polskich znaków i formatów

---

## Architektura

```
┌─────────────────┐
│   GUI / API     │
└────────┬────────┘
         │ (1) Request: Generate QUOTATION for ID xyz
         ▼
┌─────────────────┐     ┌──────────────────────┐
│ DocumentService │◄────┤ DocumentRepository   │
└────────┬────────┘     │ - get_next_number()  │
         │              │ - save_metadata()    │
         │              │ - get_template()     │
         │              └──────────────────────┘
         │
         ├──► (2) QuotationContextBuilder
         │         - pobiera dane z DB
         │         - tworzy DocumentContext
         │
         ├──► (3) DocumentRenderer
         │         - Jinja2 → HTML
         │         - WeasyPrint → PDF
         │
         └──► (4) Supabase Storage
                   - upload PDF
                   - save metadata
```

### Struktura katalogów

```
documents/
├── __init__.py           # Eksporty modułu
├── constants.py          # DocumentType enum, stałe
├── models.py             # Pydantic: DocumentContext, CompanyInfo
├── utils.py              # format_currency, number_to_text_pl
├── renderer.py           # Jinja2 + WeasyPrint
├── repository.py         # DocumentRepository
├── service.py            # DocumentService (główna fasada)
├── migrations.sql        # SQL dla Supabase
├── builders/
│   ├── __init__.py
│   ├── base.py           # BaseContextBuilder (ABC)
│   ├── quotation_builder.py
│   ├── wz_builder.py
│   └── cmr_builder.py
└── templates/
    ├── base.html         # Szablon bazowy
    ├── quotation.html    # Oferta handlowa
    ├── wz.html           # Wydanie zewnętrzne
    └── cmr.html          # List przewozowy CMR
```

---

## Instalacja

### 1. Zależności Python

```bash
pip install jinja2 weasyprint pydantic
```

### 2. GTK3 Runtime (Windows)

WeasyPrint wymaga bibliotek GTK3.

**Opcja A - Instalator GTK3:**
1. Pobierz z: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
2. Zainstaluj z opcją "Set up PATH"
3. Restart komputera

**Opcja B - MSYS2:**
```bash
# W terminalu MSYS2
pacman -S mingw-w64-x86_64-gtk3

# Dodaj do PATH systemowego:
C:\msys64\mingw64\bin
```

### 3. Baza danych

Wykonaj skrypt SQL w Supabase:
```sql
-- Plik: documents/migrations.sql
```

### 4. Storage

Utwórz bucket `documents` w Supabase Dashboard → Storage.

---

## Szybki start

### Generowanie PDF

```python
from documents.service import DocumentService
from documents.constants import DocumentType
from core.supabase_client import get_supabase_client

# Inicjalizacja
client = get_supabase_client()
service = DocumentService(client)

# Generuj ofertę PDF
result = service.generate_document(
    doc_type=DocumentType.QUOTATION,
    entity_id="uuid-oferty",
    user_id="uuid-usera"
)

if result['success']:
    print(f"Wygenerowano: {result['doc_number']}")
    print(f"Ścieżka: {result['storage_path']}")
else:
    print(f"Błąd: {result['error']}")
```

### Podgląd HTML

```python
# Podgląd bez zapisywania
result = service.generate_document(
    doc_type=DocumentType.QUOTATION,
    entity_id="uuid-oferty",
    preview=True
)

html_content = result['html']
```

### Pobieranie dokumentu

```python
# URL do pobrania (ważny 1h)
url = service.get_document_url(document_id)

# Pobranie bajtów PDF
pdf_bytes = service.download_document(document_id)
```

---

## Typy dokumentów

| Typ | Enum | Opis |
|-----|------|------|
| Oferta handlowa | `DocumentType.QUOTATION` | Dokument z cenami, warunkami |
| Wydanie zewnętrzne | `DocumentType.WZ` | Dokument magazynowy bez cen |
| CMR | `DocumentType.CMR` | Międzynarodowy list przewozowy |
| Faktura | `DocumentType.INVOICE` | Faktura VAT |
| List przewozowy | `DocumentType.DELIVERY_NOTE` | Wewnętrzny list przewozowy |
| Lista pakunkowa | `DocumentType.PACKING_LIST` | Specyfikacja paczek |

---

## API Reference

### DocumentService

Główna klasa do generowania dokumentów.

#### `generate_document()`

```python
def generate_document(
    doc_type: DocumentType,
    entity_id: str,
    user_id: str = None,
    preview: bool = False,
    custom_context: Dict[str, Any] = None
) -> Dict[str, Any]
```

**Parametry:**
- `doc_type` - Typ dokumentu (DocumentType enum)
- `entity_id` - ID encji (zamówienia, oferty)
- `user_id` - ID użytkownika generującego
- `preview` - True = zwróć HTML, nie zapisuj
- `custom_context` - Dodatkowe dane do szablonu

**Zwraca:**
```python
{
    'success': True,
    'doc_number': 'QUOTATION/2025/000001',
    'storage_path': 'documents/QUOTATION/2025/...',
    'document_id': 'uuid',
    'pdf_size': 12345
}
# lub przy błędzie:
{
    'success': False,
    'error': 'Opis błędu'
}
```

#### `get_document_url()`

```python
def get_document_url(document_id: str) -> Optional[str]
```

Zwraca podpisany URL do pobrania (ważny 1 godzinę).

#### `download_document()`

```python
def download_document(document_id: str) -> Optional[bytes]
```

Zwraca zawartość PDF jako bytes.

#### `get_documents_for_entity()`

```python
def get_documents_for_entity(
    entity_type: str,
    entity_id: str
) -> List[Dict]
```

Zwraca wszystkie dokumenty powiązane z encją.

---

### DocumentRepository

Repozytorium do operacji na bazie danych.

#### `get_next_number()`

```python
def get_next_number(
    doc_type: str,
    year: int = None
) -> Tuple[int, str]
```

Generuje atomowo kolejny numer dokumentu.

**Zwraca:** `(123, 'WZ/2025/000123')`

#### `save_document_metadata()`

```python
def save_document_metadata(metadata: Dict) -> Tuple[bool, Optional[str]]
```

Zapisuje metadane dokumentu w rejestrze.

#### `get_active_template()`

```python
def get_active_template(doc_type: str) -> Optional[Dict]
```

Pobiera aktywny szablon z bazy (jeśli istnieje).

---

### DocumentRenderer

Renderer HTML/PDF.

#### `render_html()`

```python
def render_html(
    template_name: str,
    context: Dict[str, Any]
) -> str
```

Renderuje szablon Jinja2 do HTML.

#### `render_pdf_bytes()`

```python
def render_pdf_bytes(
    html_content: str,
    css_content: str = None
) -> bytes
```

Konwertuje HTML na PDF (WeasyPrint).

---

### Modele danych

#### DocumentContext

```python
class DocumentContext(BaseModel):
    doc_type: str
    doc_type_label: str      # "OFERTA HANDLOWA"
    doc_number: str          # "QUOTATION/2025/000001"
    issue_date: date
    place: str = "Polska"

    seller: CompanyInfo
    buyer: CompanyInfo

    items: List[DocumentItem]

    total_net: Optional[Decimal]
    total_vat: Optional[Decimal]
    total_gross: Optional[Decimal]
    currency: str = "PLN"

    notes: Optional[str]
    footer_text: Optional[str]
    extra_data: Dict[str, Any] = {}
```

#### CompanyInfo

```python
class CompanyInfo(BaseModel):
    name: str
    address: str
    nip: Optional[str]
    bank_account: Optional[str]
    logo_base64: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    country: str = "Polska"
```

#### DocumentItem

```python
class DocumentItem(BaseModel):
    position: int
    name: str
    quantity: float
    unit: str = "szt"
    price_net: Optional[Decimal]
    value_net: Optional[Decimal]
    vat_rate: Optional[int] = 23

    # Dla CMR:
    weight: Optional[float]      # kg
    volume: Optional[float]      # m³
    hs_code: Optional[str]
    package_type: Optional[str]
```

---

## Szablony HTML

### Dziedziczenie szablonów

Szablony używają dziedziczenia Jinja2:

```html
<!-- quotation.html -->
{% extends "base.html" %}

{% block content %}
    <!-- Zawartość specyficzna dla oferty -->
{% endblock %}
```

### Dostępne filtry Jinja2

| Filtr | Użycie | Wynik |
|-------|--------|-------|
| `currency` | `{{ value \| currency }}` | `1 234,56 PLN` |
| `date_pl` | `{{ date \| date_pl }}` | `07.12.2025` |
| `number_to_text` | `{{ value \| number_to_text }}` | `jeden tysiąc dwieście... złotych` |

### Zmienne w szablonach

```html
<!-- Dane dokumentu -->
{{ doc_type_label }}     <!-- OFERTA HANDLOWA -->
{{ doc_number }}         <!-- QUOTATION/2025/000001 -->
{{ issue_date }}         <!-- 2025-12-07 -->
{{ place }}              <!-- Polska -->

<!-- Sprzedawca -->
{{ seller.name }}
{{ seller.address }}
{{ seller.nip }}
{{ seller.logo_base64 }}

<!-- Nabywca -->
{{ buyer.name }}
{{ buyer.address }}
{{ buyer.nip }}

<!-- Pozycje -->
{% for item in items %}
    {{ item.position }}
    {{ item.name }}
    {{ item.quantity }}
    {{ item.unit }}
    {{ item.price_net | currency }}
    {{ item.value_net | currency }}
{% endfor %}

<!-- Podsumowanie -->
{{ total_net | currency }}
{{ total_vat | currency }}
{{ total_gross | currency }}

<!-- Dane dodatkowe -->
{{ extra_data.valid_until }}
{{ extra_data.payment_terms }}
```

### Tworzenie własnego szablonu

1. Utwórz plik w `documents/templates/`:

```html
{% extends "base.html" %}

{% block content %}
<h3>Mój dokument</h3>
<table>
    {% for item in items %}
    <tr>
        <td>{{ item.name }}</td>
        <td>{{ item.quantity }}</td>
    </tr>
    {% endfor %}
</table>
{% endblock %}
```

2. Dodaj typ do `constants.py`:

```python
class DocumentType(str, Enum):
    MY_DOC = "MY_DOC"

TEMPLATE_FILES = {
    DocumentType.MY_DOC: "my_doc.html",
}
```

3. Utwórz builder w `builders/`:

```python
class MyDocContextBuilder(BaseContextBuilder):
    def build(self, entity_id, doc_number, user_id):
        # Pobierz dane i zwróć DocumentContext
        pass
```

---

## Baza danych

### Tabele

#### document_counters

Liczniki dla numeracji dokumentów.

| Kolumna | Typ | Opis |
|---------|-----|------|
| doc_type | VARCHAR(20) | Typ dokumentu (PK) |
| year | INTEGER | Rok (PK) |
| last_number | INTEGER | Ostatni numer |
| updated_at | TIMESTAMP | Data aktualizacji |

#### documents_registry

Rejestr wygenerowanych dokumentów.

| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID | Klucz główny |
| doc_type | VARCHAR(20) | Typ dokumentu |
| doc_number_full | VARCHAR(50) | Pełny numer |
| year | INTEGER | Rok |
| number_seq | INTEGER | Numer sekwencyjny |
| customer_id | UUID | FK do customers |
| related_table | VARCHAR(50) | Tabela źródłowa |
| related_id | UUID | ID w tabeli źródłowej |
| storage_path | VARCHAR(255) | Ścieżka w Storage |
| created_at | TIMESTAMP | Data utworzenia |
| created_by | UUID | Użytkownik |
| is_deleted | BOOLEAN | Soft delete |

#### document_templates

Szablony dokumentów (opcjonalne).

| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID | Klucz główny |
| doc_type | VARCHAR(20) | Typ dokumentu |
| name | VARCHAR(100) | Nazwa szablonu |
| content_html | TEXT | Kod HTML/Jinja2 |
| styles_css | TEXT | Dodatkowy CSS |
| meta_json | JSONB | Konfiguracja |
| version | INTEGER | Wersja |
| is_active | BOOLEAN | Czy aktywny |

### Funkcja numeracji

```sql
SELECT get_next_document_number('WZ', 2025);
-- Zwraca: 1, 2, 3... (atomowo)
```

---

## Konfiguracja

### Stałe w constants.py

```python
# Domyślna waluta
DEFAULT_CURRENCY = "PLN"

# Bucket w Supabase Storage
STORAGE_BUCKET = "documents"

# Ścieżka bazowa
STORAGE_BASE_PATH = "documents"

# Stawki VAT
VAT_RATES = {
    'standard': 23,
    'reduced': 8,
    'super_reduced': 5,
    'zero': 0
}
```

### Dane firmy (sprzedawcy)

Domyślnie pobierane z tabeli `company_settings`. Fallback w `builders/base.py`:

```python
def get_seller_info(self) -> CompanyInfo:
    # Najpierw próbuje z bazy
    # Fallback:
    return CompanyInfo(
        name="NewERP Sp. z o.o.",
        address="ul. Przemysłowa 1, 00-001 Warszawa",
        nip="000-000-00-00",
    )
```

---

## Rozwiązywanie problemów

### WeasyPrint nie działa na Windows

**Błąd:** `OSError: cannot load library 'gobject-2.0-0'`

**Rozwiązanie:**
1. Zainstaluj GTK3 Runtime
2. Dodaj `C:\Program Files\GTK3-Runtime Win64\bin` do PATH
3. Restart komputera

**Alternatywnie:** Użyj MSYS2 (patrz [Instalacja](#instalacja))

### Polskie znaki nie wyświetlają się

**Rozwiązanie:**
1. Upewnij się, że szablon ma `<meta charset="UTF-8">`
2. Użyj fontu z polskimi znakami (Open Sans, DejaVu Sans)

### Brak numeracji (DRAFT)

**Przyczyna:** Funkcja RPC `get_next_document_number` nie istnieje w bazie.

**Rozwiązanie:** Wykonaj `migrations.sql` w Supabase.

### Szablon nie znaleziony

**Błąd:** `Szablon nie istnieje: quotation.html`

**Rozwiązanie:**
1. Sprawdź czy plik istnieje w `documents/templates/`
2. Sprawdź mapowanie w `constants.py` → `TEMPLATE_FILES`

### Upload do Storage nie działa

**Przyczyny:**
1. Bucket `documents` nie istnieje
2. Brak uprawnień (RLS)

**Rozwiązanie:**
1. Utwórz bucket w Supabase Dashboard
2. Ustaw polityki RLS lub wyłącz dla testów

---

## Przykłady użycia

### Generowanie WZ dla zamówienia

```python
result = service.generate_document(
    doc_type=DocumentType.WZ,
    entity_id=order_id,
    user_id=current_user_id
)
```

### Generowanie CMR z dodatkowymi danymi

```python
result = service.generate_document(
    doc_type=DocumentType.CMR,
    entity_id=delivery_id,
    custom_context={
        'carrier_name': 'DHL Express',
        'driver_phone': '+48 123 456 789'
    }
)
```

### Lista dokumentów dla klienta

```python
docs = service.get_documents_for_entity('orders', order_id)
for doc in docs:
    print(f"{doc['doc_number_full']} - {doc['created_at']}")
```

---

## Changelog

### v2.0.0 (2025-12-11)

**Nowa kluczowa funkcjonalność: Thumbnails detali**

Wszystkie dokumenty teraz zawierają podglądy wizualne detali (thumbnails) dla łatwej identyfikacji:

- **Rozszerzone modele:**
  - `DocumentItem.thumbnail_base64` - obrazek detalu w Base64
  - `DocumentItem.material`, `thickness_mm`, `width_mm`, `height_mm` - dane techniczne
  - `DocumentItem.material_cost`, `cutting_cost`, `bending_cost`, `other_cost` - koszty szczegółowe

- **Nowe typy dokumentów:**
  - `COST_REPORT` - Raport kosztowy ze szczegółową kalkulacją

- **Nowe szablony z thumbnailami:**
  - `wz.html` - WZ z podglądami detali i grupowaniem po materiałach
  - `packing_list.html` - Lista pakunkowa z wagami i checklistą
  - `order_confirmation.html` - Potwierdzenie zamówienia z akceptacją
  - `cost_report.html` - Raport kosztowy (landscape A4) z wykresami kosztów

- **Nowe buildery:**
  - `OrderConfirmationContextBuilder` - potwierdzenia zamówień
  - `PackingListContextBuilder` - listy pakunkowe
  - `CostReportContextBuilder` - raporty kosztowe

- **GUI:**
  - `DocumentGeneratorDialog` - dialog do wyboru i generowania dokumentów
  - `open_document_generator()` - funkcja pomocnicza

### v1.0.0 (2025-12-07)

- Inicjalna wersja modułu
- Obsługa dokumentów: Oferta, WZ, CMR
- Szablony HTML z dziedziczeniem Jinja2
- Integracja z Supabase Storage
- Automatyczna numeracja dokumentów
- Formatowanie walut i dat po polsku
- Kwoty słownie (number_to_text_pl)

---

## Autor

Moduł utworzony dla systemu NewERP.

**Technologie:** Python 3.10+, Jinja2, WeasyPrint, Pydantic, Supabase
