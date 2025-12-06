# Plan naprawy modułu Orders

## Status obecny (aktualizacja 2025-12-04 v2)
- [x] Zapis zamówienia do Supabase - działa
- [x] Zapis pozycji (order_items) - działa
- [x] Mapowanie kolumn bazy ↔ aplikacja - działa
- [x] Ładowanie pozycji przy otwieraniu zamówienia - NAPRAWIONE
- [x] Zapis wyników nestingu do metadata - NAPRAWIONE
- [x] Zapis wyników kosztów do metadata - NAPRAWIONE
- [x] Odczyt wyników nestingu z metadata - NAPRAWIONE
- [x] Odczyt wyników kosztów z metadata - NAPRAWIONE
- [x] Eksport grafik nestingu jako PNG - ZAIMPLEMENTOWANE
- [x] Przesyłanie grafik w callback do OrderWindow - ZAIMPLEMENTOWANE
- [x] Konwersja grafik do base64 dla serializacji JSON - ZAIMPLEMENTOWANE
- [x] Kolumna "Wyfakturowano" w liscie zamowien - ZAIMPLEMENTOWANE
- [x] Modul wysylania emaili (SMTP/IMAP/Exchange) - ZAIMPLEMENTOWANE
- [x] DetailedPartsPanel z thumbnails i kosztami jednostkowymi - ZAIMPLEMENTOWANE
- [x] Obsluga modeli 3D (STEP/IGES) - ZAIMPLEMENTOWANE
- [x] Reczne dodawanie detali bez plikow - ZAIMPLEMENTOWANE
- [x] Checkbox "Kalkuluj z materialem" (globalny + per detal) - ZAIMPLEMENTOWANE
- [ ] Wyświetlanie grafik w panelu wyników (results_panel) - do implementacji
- [ ] Zapis grafik do Supabase Storage - opcjonalne

## Zrealizowane zmiany (2025-12-04)

### 0. Nowe funkcjonalnosci GUI

#### a) Kolumna "Wyfakturowano" w liscie zamowien
**Plik:** `main_dashboard.py`
- Dodano kolumne "faktura" z kolorowym wskaznikiem
- Zielone kolko = wyfakturowane, czerwone = nie

#### b) Modul wysylania emaili
**Plik:** `core/email_service.py` (NOWY)
- `EmailConfig` - konfiguracja SMTP/IMAP/Exchange
- `EmailService.send_email()` - wysylanie przez SMTP
- `EmailService.send_via_exchange()` - integracja z Office365
- `EmailService.send_invoice()` - wysylka faktury z zalacznikami
- `create_xlsx_summary()` - generowanie podsumowania XLSX

#### c) Panel szczegolowych detali
**Plik:** `orders/gui/detailed_parts_panel.py` (NOWY)
Komponenty:
- `ThumbnailGenerator` - miniaturki z konturow detali
- `Model3DLoader` - ladowanie STEP/IGES (OCC lub fallback)
- `EnhancedTreeview` - tabela z miniaturkami i inline editing
- `DetailedPartsPanel` - glowny panel

Funkcje:
- Thumbnails dla kazdego detalu
- Kolumny: Nr, Mat, Name, Material, Thick, Qty, Bends, L+M, Bend$, Add$, Weight, Cut len, Total/pc
- Globalny checkbox "Kalkuluj z materialem"
- Per-detal checkbox materialu (+ / -)
- Przyciski: +Dodaj, +3D, Dup, Usun, Przelicz
- Filtrowanie po nazwie/materiale
- Podsumowanie kosztow na dole

#### d) Integracja z OrderWindow
**Plik:** `orders/gui/order_window.py`
- Import i inicjalizacja DetailedPartsPanel
- Synchronizacja detali miedzy panelami
- Callback `_on_detailed_parts_change()` dla przeliczania kosztow

### 1. Skrypty testowe
- `scripts/tests/test_order_repository.py` - testy CRUD dla zamówień
- `scripts/tests/test_nesting_save.py` - testy zapisu/odczytu wyników nestingu

### 2. Fix ładowania zamówień
**Plik:** `orders/gui/order_window.py` → `_load_order_data()`
- Automatyczne pobieranie items z repozytorium jeśli brak w order_data
- Ładowanie nesting_results z metadata
- Ładowanie cost_result z metadata

### 3. Eksport grafik nestingu
**Pliki:**
- `quotations/gui/nesting_tabs_panel.py`
  - `SheetCanvas.export_to_image()` - renderowanie arkusza do PIL Image → PNG bytes
  - `NestingTab.export_images()` - eksport wszystkich arkuszy z zakładki
  - `NestingTabsPanel.export_all_images()` - eksport ze wszystkich zakładek

- `nesting_window.py` → `_submit_results()`
  - Eksport obrazów przed wywołaniem callback
  - Przekazanie `sheet_images` w callback_data

- `orders/gui/order_window.py` → `_on_nesting_complete()`
  - Konwersja obrazów do base64 dla serializacji JSON
  - Zapis w `nesting_results['sheet_images_base64']`

## Zidentyfikowane problemy

### 1. Brak ładowania items przy otwieraniu zamówienia
**Lokalizacja:** `main_dashboard.py` → `_open_order()`
**Problem:** Przekazuje tylko dane z listy (bez items), nie pobiera pełnych danych z repozytorium
**Fix:** Przed otwarciem okna pobrać pełne dane przez `repository.get_by_id()`

### 2. Wyniki nestingu nie są zapisywane/ładowane
**Lokalizacja:** `orders/repository.py`
**Problem:** `nesting_results` zapisywane w `metadata`, ale nie odtwarzane w GUI
**Fix:** Deserializować i przekazać do `NestingResultsPanel`

### 3. Grafiki nestingu nie są zapisywane
**Problem:** Brak mechanizmu generowania i zapisywania obrazów nestingu
**Fix:** Dodać funkcję eksportu PNG z `nesting_window.py`

---

## Plan testów jednostkowych

### Faza 1: Skrypty testowe (bez GUI)

```
scripts/
  tests/
    test_order_repository.py    # CRUD zamówień
    test_order_items.py         # CRUD pozycji
    test_nesting_save.py        # Zapis wyników nestingu
    test_full_workflow.py       # Pełny flow
```

### test_order_repository.py
```python
# Test: Tworzenie zamówienia
# Test: Pobieranie zamówienia z items
# Test: Aktualizacja zamówienia
# Test: Usuwanie zamówienia
```

### test_order_items.py
```python
# Test: Zapis pozycji z product_snapshot
# Test: Odczyt pozycji i mapowanie do formatu aplikacji
# Test: Aktualizacja pozycji (usuń stare, dodaj nowe)
```

### test_nesting_save.py
```python
# Test: Serializacja wyników nestingu do JSON
# Test: Zapis w metadata zamówienia
# Test: Odtworzenie wyników z metadata
```

---

## Faza 2: Naprawy kodu

### 2.1 Fix: Ładowanie zamówienia z items
**Plik:** `main_dashboard.py`
```python
def _open_order(self, order_id: str):
    # Pobierz PEŁNE dane z repozytorium (włącznie z items)
    from orders.repository import OrderRepository
    repo = OrderRepository(self.supabase_client)
    order_data = repo.get_by_id(order_id)  # To już pobiera items!

    # Otwórz okno z pełnymi danymi
    OrderWindow(self, order_id=order_id, order_data=order_data, ...)
```

### 2.2 Fix: Ładowanie danych w OrderWindow
**Plik:** `orders/gui/order_window.py`
```python
def _load_order_data(self):
    # Jeśli brak items w order_data, pobierz z repozytorium
    if not self.order_data.get('items'):
        from orders.repository import OrderRepository
        repo = OrderRepository(...)
        full_data = repo.get_by_id(self.order_id)
        if full_data:
            self.order_data = full_data

    # Załaduj items do listy
    if self.order_data.get('items'):
        self.parts_panel.set_parts(self.order_data['items'])

    # Załaduj wyniki nestingu
    if self.order_data.get('nesting_results'):
        self._restore_nesting_results()
```

### 2.3 Feature: Zapisywanie grafik nestingu
**Plik:** `nesting_window.py`
```python
def _export_nesting_image(self, sheet_index: int) -> bytes:
    """Eksportuj arkusz nestingu jako PNG"""
    # Renderuj canvas do obrazu
    # Zwróć bytes PNG
    pass

def _submit_to_order(self):
    # Generuj grafiki dla każdego arkusza
    images = []
    for i, sheet in enumerate(self.sheets):
        img_bytes = self._export_nesting_image(i)
        images.append(img_bytes)

    # Przekaż do callback razem z wynikami
    self.on_complete_callback({
        'sheets': [...],
        'images': images,  # Lista PNG bytes
        ...
    })
```

---

## Faza 3: Nowe funkcje

### 3.1 Panel wyników nestingu - podgląd grafik
**Plik:** `orders/gui/order_window.py` → `NestingResultsPanel`
- Dodać miniaturki arkuszy
- Po kliknięciu pokazać pełny podgląd
- Zapisywać grafiki w Supabase Storage

### 3.2 Supabase Storage dla załączników
```python
# Upload grafiki
storage = supabase.storage.from_('order-attachments')
storage.upload(f'orders/{order_id}/nesting_{sheet_idx}.png', img_bytes)

# Download grafiki
url = storage.get_public_url(f'orders/{order_id}/nesting_{sheet_idx}.png')
```

---

## Kolejność implementacji

1. **Jutro rano:** Skrypt testowy `test_order_repository.py`
2. **Po testach:** Fix ładowania zamówień w `main_dashboard.py`
3. **Następnie:** Fix `_load_order_data()` w `order_window.py`
4. **Później:** Eksport grafik nestingu
5. **Na końcu:** Podgląd grafik w panelu wyników

---

## Komendy testowe

```bash
# Test repozytorium
python -m scripts.tests.test_order_repository

# Test pełnego flow
python -m scripts.tests.test_full_workflow

# Uruchom aplikację
python main_dashboard.py
```
