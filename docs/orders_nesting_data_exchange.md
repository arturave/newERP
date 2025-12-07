# Wymiana Danych: Modul Zamowienia - Nesting
## Dokumentacja Techniczna v1.0

---

## 1. Przeglad Architektury

```
┌─────────────────────────────────────────────────────────────────┐
│                     MODULE: NESTING                              │
│  quotations/nesting/fast_nester.py                              │
├─────────────────────────────────────────────────────────────────┤
│  FastNester                                                      │
│  ├── nest_parts(parts) → NestingResult                          │
│  └── NestingResult:                                             │
│      ├── sheets: List[NestingSheet]                             │
│      ├── placed_parts: List[PlacedPart]                         │
│      └── statistics (efficiency, utilization)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ NestingResult
┌─────────────────────────────────────────────────────────────────┐
│                     MODULE: ORDERS                               │
│  orders/gui/order_window.py                                      │
├─────────────────────────────────────────────────────────────────┤
│  OrderWindow                                                     │
│  ├── NestingGroupPanel → otrzymuje NestingResult                │
│  ├── DetailedPartsPanel → koszty z nestingu                     │
│  └── CostSummaryPanel → podsumowanie kosztow                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ order_data (z metadata)
┌─────────────────────────────────────────────────────────────────┐
│                     SUPABASE                                     │
│  orders/repository.py → OrderRepository                          │
├─────────────────────────────────────────────────────────────────┤
│  Tabela: orders                                                  │
│  ├── metadata JSONB:                                            │
│  │   ├── cost_params: {...}                                     │
│  │   ├── cost_result: {...}                                     │
│  │   └── nesting_results: {...}  ← Problem: uproszczone dane    │
│  Tabela: order_items                                            │
│  ├── product_snapshot JSONB                                     │
│  Tabela: nesting_results                                        │
│  └── nesting_data JSONB  ← pelne dane nestingu                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Struktury Danych

### 2.1 NestingResult (z modulu nesting)

Lokalizacja: `costing/models/nesting_result.py`

```python
@dataclass
class NestingResult:
    nesting_run_id: str              # UUID
    source_type: SourceType          # ORDER | QUOTATION
    source_id: str                   # ID zamowienia/oferty
    created_at: str                  # ISO timestamp
    machine_profile_id: str          # Profil maszyny
    sheets: List[NestingSheet]       # Lista arkuszy
```

### 2.2 NestingSheet (pojedynczy arkusz)

```python
@dataclass
class NestingSheet:
    sheet_id: str
    sheet_mode: SheetMode            # FIXED_SHEET | CUT_TO_LENGTH
    material_id: str                 # Kod materialu (np. "1.4301")
    thickness_mm: float

    # Wymiary
    sheet_width_mm: float            # Szerokosc arkusza
    sheet_length_mm_nominal: float   # Dlugosc nominalna
    used_length_y_mm: float          # Wykorzystana dlugosc
    trim_margin_y_mm: float          # Margines ciecia

    # Metryki
    sheet_area_used_mm2: float
    occupied_area_mm2: float
    utilization: float               # 0.0 - 1.0

    # Preview
    preview_image_path: str          # Sciezka do obrazu arkusza

    # Detale na arkuszu
    parts: List[PartInstance]
```

### 2.3 PartInstance (detal na arkuszu)

```python
@dataclass
class PartInstance:
    part_id: str                     # ID detalu
    instance_id: str                 # ID instancji
    idx_code: str                    # Kod indeksu
    name: str                        # Nazwa detalu
    qty_in_sheet: int                # Ilosc na tym arkuszu

    # Pozycja
    transform: Transform             # x_mm, y_mm, rotation_deg

    # Plik
    dxf_storage_path: str            # Sciezka w Storage

    # Powierzchnia
    occupied_area_mm2: float         # Zajeta powierzchnia
    net_area_mm2: float              # Netto powierzchnia

    # Statystyki ciecia
    toolpath_stats: ToolpathStats    # cut_length, pierce_count, etc.
```

### 2.4 ToolpathStats (statystyki ciecia)

```python
@dataclass
class ToolpathStats:
    cut_length_mm: float             # Dlugosc ciecia
    rapid_length_mm: float           # Dlugosc szybkich ruchow
    pierce_count: int                # Liczba przebic
    contour_count: int               # Liczba konturow
    entity_counts: Dict[str, int]    # Liczniki encji DXF
    short_segment_ratio: float       # Wspolczynnik krotkich segmentow
```

---

## 3. Przeplyw Danych: Nesting → Zamowienie

### 3.1 Uruchomienie Nestingu

```python
# W NestingGroupPanel.py
def _run_nesting(self):
    # 1. Przygotuj detale
    parts_to_nest = self._get_parts_from_panel()

    # 2. Uruchom nesting
    from quotations.nesting.fast_nester import FastNester
    nester = FastNester(sheet_width, sheet_height)
    result = nester.nest_parts(parts_to_nest)

    # 3. Zwroc wynik do OrderWindow
    self.nesting_results[(material, thickness)] = result
    self._notify_nesting_complete(result)
```

### 3.2 Przekazanie do Panelu Kosztow

```python
# W OrderWindow.py
def _on_nesting_complete(self, result: NestingResult):
    # 1. Zapisz wynik
    self.nesting_results = result

    # 2. Zaktualizuj panel kosztow
    self.detailed_parts_panel.update_from_nesting(result)
    self.cost_summary_panel.recalculate()
```

### 3.3 Obliczenie Kosztow

```python
# W DetailedPartsPanel.py
def update_from_nesting(self, nesting_result):
    for sheet in nesting_result.sheets:
        # Koszt arkusza
        sheet_cost = self._calculate_sheet_cost(sheet)

        for part in sheet.parts:
            # Alokuj koszt materialu
            part_material_cost = self._allocate_material(
                sheet_cost,
                part.occupied_area_mm2,
                sheet.occupied_area_mm2
            )

            # Koszt ciecia
            cut_cost = part.toolpath_stats.cut_length_mm * rate_per_m

            # Aktualizuj w tabeli
            self._update_part_cost(part.part_id, part_material_cost, cut_cost)
```

---

## 4. Przeplyw Danych: Zapis do Bazy

### 4.1 Aktualna Implementacja (PROBLEM!)

```python
# W OrderRepository.py - _serialize_nesting_results()
def _serialize_nesting_results(self, results: Dict) -> Dict:
    # PROBLEM: Tylko uproszczone dane!
    serialized = {
        'sheets_used': results.sheets_used,
        'efficiency': results.total_efficiency,
        'placed_parts': len(results.placed_parts),  # Tylko liczba!
        'total_cost': results.total_cost
    }
    return serialized
```

**Utracone dane:**
- Pozycje detali na arkuszach (transform x, y, rotation)
- Podglady arkuszy (preview_image_path)
- Statystyki toolpath per detal
- Relacje detal-arkusz

### 4.2 Wymagana Implementacja (ROZWIAZANIE)

```python
# Pelna serializacja do tabeli nesting_results
def save_complete_nesting(self, order_id: str, nesting_result: NestingResult):
    nesting_data = {
        'context_type': 'order',
        'context_id': order_id,
        'material': nesting_result.sheets[0].material_id if nesting_result.sheets else '',
        'thickness': nesting_result.sheets[0].thickness_mm if nesting_result.sheets else 0,
        'sheets_used': len(nesting_result.sheets),
        'utilization': sum(s.utilization for s in nesting_result.sheets) / len(nesting_result.sheets),
        'nesting_data': nesting_result.to_json()  # Pełne dane JSON!
    }

    self.client.table('nesting_results').insert(nesting_data).execute()
```

---

## 5. Przeplyw Danych: Odczyt z Bazy

### 5.1 Aktualna Implementacja (PROBLEM!)

```python
# W OrderRepository.py - get_by_id()
def get_by_id(self, order_id: str):
    order = self._get_order_from_db(order_id)

    # PROBLEM: Tylko uproszczone dane z metadata
    order['nesting_results'] = metadata.get('nesting_results', {})
    # Brak pelnych danych - nie mozna odtworzyc wizualizacji!
```

### 5.2 Wymagana Implementacja (ROZWIAZANIE)

```python
def get_by_id(self, order_id: str):
    order = self._get_order_from_db(order_id)

    # Pobierz pelne dane nestingu z nesting_results
    nesting_response = self.client.table('nesting_results').select('*').eq(
        'context_id', order_id
    ).eq('context_type', 'order').order('created_at', desc=True).limit(1).execute()

    if nesting_response.data:
        nesting_json = nesting_response.data[0]['nesting_data']
        order['nesting_results'] = NestingResult.from_json(nesting_json)
    else:
        order['nesting_results'] = None

    return order
```

---

## 6. Krzywe Predkosci (Speed Curves)

### 6.1 Zrodlo Danych

Krzywe predkosci sa przechowywane w:
- `data/pricing/cutting_prices.xlsx` - predkosci ciecia [mm/min] per material/grubosc
- `cost_config.laser_hourly_rate` - stawka godzinowa [PLN/h]

### 6.2 Struktura Danych Predkosci

```python
# W PricingTables (quotations/pricing/pricing_tables.py)
@dataclass
class CuttingRate:
    material: str           # Typ materialu
    thickness_mm: float     # Grubosc [mm]
    gas_type: str          # Gaz ciecia (O2, N2, AIR)
    speed_mm_min: float    # Predkosc ciecia [mm/min]
    cost_per_meter: float  # Koszt [PLN/m]
    cost_per_hour: float   # Stawka godzinowa [PLN/h]
```

### 6.3 Wykorzystanie w Obliczeniach

```python
# Wariant A (cennikowy)
cutting_cost = cutting_length_m * cost_per_meter

# Wariant B (czasowy)
cutting_time_min = cutting_length_mm / speed_mm_min
cutting_cost = (cutting_time_min / 60) * cost_per_hour * buffer_factor
```

---

## 7. Format Danych Arkuszy do Zapisu

### 7.1 Minimalny Zestaw Danych (dla odtworzenia wizualizacji)

```json
{
  "sheet_id": "uuid",
  "sheet_index": 0,
  "material_id": "1.4301",
  "thickness_mm": 3.0,
  "width_mm": 3000,
  "height_mm": 1500,
  "used_height_mm": 1200,
  "utilization": 0.72,
  "parts": [
    {
      "part_id": "uuid",
      "name": "Detal_A",
      "x_mm": 10,
      "y_mm": 10,
      "rotation_deg": 0,
      "width_mm": 200,
      "height_mm": 150,
      "contour_points": [[0,0], [200,0], [200,150], [0,150]],
      "cut_length_mm": 700,
      "pierce_count": 3
    }
  ],
  "preview_image_base64": "data:image/png;base64,..."
}
```

### 7.2 Pelny Zestaw Danych (dla pelnej funkcjonalnosci)

```json
{
  "nesting_run_id": "uuid",
  "source_type": "order",
  "source_id": "order-uuid",
  "created_at": "2025-12-07T12:00:00Z",
  "machine_profile_id": "default",

  "sheets": [
    {
      "sheet_id": "uuid",
      "sheet_mode": "FIXED_SHEET",
      "material_id": "1.4301",
      "thickness_mm": 3.0,
      "sheet_width_mm": 3000,
      "sheet_length_mm_nominal": 1500,
      "used_length_y_mm": 1200,
      "trim_margin_y_mm": 10,
      "sheet_area_used_mm2": 4500000,
      "occupied_area_mm2": 3240000,
      "utilization": 0.72,
      "preview_image_path": "storage://nestings/order-uuid/sheet-0.png",

      "parts": [
        {
          "part_id": "part-uuid",
          "instance_id": "instance-uuid",
          "idx_code": "A001",
          "name": "Detal_A",
          "qty_in_sheet": 5,
          "transform": {
            "x_mm": 10,
            "y_mm": 10,
            "rotation_deg": 0
          },
          "dxf_storage_path": "storage://parts/part-uuid.dxf",
          "occupied_area_mm2": 30000,
          "net_area_mm2": 28500,
          "toolpath_stats": {
            "cut_length_mm": 700,
            "rapid_length_mm": 50,
            "pierce_count": 3,
            "contour_count": 3,
            "entity_counts": {"LINE": 4, "ARC": 2},
            "short_segment_ratio": 0.1
          }
        }
      ]
    }
  ],

  "summary": {
    "total_sheets": 1,
    "total_parts": 5,
    "total_cut_length_mm": 3500,
    "total_pierce_count": 15,
    "average_utilization": 0.72,
    "total_material_cost": 250.00,
    "total_cutting_cost": 45.00
  }
}
```

---

## 8. Tabele Supabase

### 8.1 Tabela: nesting_results

```sql
CREATE TABLE nesting_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    context_type VARCHAR(20) NOT NULL,  -- 'order' | 'quotation'
    context_id UUID NOT NULL,
    material VARCHAR(50),
    thickness DECIMAL(6,2),
    sheet_format VARCHAR(20),           -- np. '3000x1500'
    sheets_used INTEGER,
    utilization DECIMAL(5,4),           -- 0.0000 - 1.0000
    total_cutting_length DECIMAL(12,2),
    total_pierces INTEGER,
    nesting_data JSONB,                 -- Pelne dane nestingu
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_nesting_context ON nesting_results(context_type, context_id);
```

### 8.2 Tabela: order_costs

```sql
CREATE TABLE order_costs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    context_type VARCHAR(20) NOT NULL,
    context_id UUID NOT NULL,
    nesting_result_id UUID REFERENCES nesting_results(id),
    cost_variant VARCHAR(1),            -- 'A' | 'B'
    allocation_model VARCHAR(50),
    material_cost DECIMAL(12,2),
    cutting_cost DECIMAL(12,2),
    foil_removal_cost DECIMAL(12,2),
    piercing_cost DECIMAL(12,2),
    operational_cost DECIMAL(12,2),
    technology_cost DECIMAL(12,2),
    packaging_cost DECIMAL(12,2),
    transport_cost DECIMAL(12,2),
    total_cost DECIMAL(12,2),
    cost_breakdown JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 9. Znane Problemy i Rozwiazania

### Problem 1: Brak wizualizacji po otwarciu zamowienia

**Przyczyna:** `_serialize_nesting_results()` zapisuje tylko podstawowe metryki.

**Rozwiazanie:** Zapisywac pelne dane do tabeli `nesting_results` z `nesting_data JSONB`.

### Problem 2: Utrata pozycji detali

**Przyczyna:** Transformacje (x, y, rotation) nie sa zapisywane.

**Rozwiazanie:** Uzywac `NestingResult.to_json()` do pelnej serializacji.

### Problem 3: Brak podgladow arkuszy

**Przyczyna:** Obrazy preview generowane tylko tymczasowo.

**Rozwiazanie:** Upload obrazow do Supabase Storage, zapisac sciezki w `nesting_data`.

---

## 10. Rekomendacje

1. **Zapisywac pelne dane nestingu** do `nesting_results.nesting_data`
2. **Uploadowac podglady arkuszy** do Supabase Storage
3. **Przy odczycie** deserializowac przez `NestingResult.from_json()`
4. **Wersjonowac** wyniki nestingu (mozliwosc powrotu do poprzednich)
5. **Indeksowac** po `context_id` dla szybkiego wyszukiwania

---

*Dokumentacja wygenerowana 2025-12-07*
