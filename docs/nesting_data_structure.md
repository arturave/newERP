# Struktura Danych Nestingu

Dokumentacja struktury danych zwracanych przez modul nestingu (`quotations/nesting/fast_nester.py`).

## Hierarchia Klas

```
NestingResult
├── sheets: List[SheetResult]
│   └── placed_parts: List[NestedPart]
├── placed_parts: List[NestedPart]  (flat view)
└── unplaced_parts: List[UnplacedPart]
```

## NestingResult

Glowny wynik operacji nestingu. Moze zawierac wiele arkuszy.

| Pole | Typ | Opis |
|------|-----|------|
| `sheets` | `List[SheetResult]` | Lista arkuszy z umieszczonymi detalami |
| `placed_parts` | `List[NestedPart]` | Plaska lista wszystkich umieszczonych detali |
| `unplaced_parts` | `List[UnplacedPart]` | Detale ktore nie zmiescily sie |
| `unplaced_count` | `int` | Liczba nieumieszczonych detali |
| `sheets_used` | `int` | Liczba uzytych arkuszy |
| `total_efficiency` | `float` | Calkowita efektywnosc (0-1) |
| `sheet_width` | `float` | Szerokosc arkusza [mm] |
| `sheet_height` | `float` | **Nominalna** wysokosc arkusza [mm] |
| `used_width` | `float` | Uzyta szerokosc [mm] |
| `used_height` | `float` | **maxY - uzyta wysokosc [mm]** |

## SheetResult

Wynik nestingu dla pojedynczego arkusza.

| Pole | Typ | Opis |
|------|-----|------|
| `sheet_index` | `int` | Indeks arkusza (0-based) |
| `placed_parts` | `List[NestedPart]` | Detale na tym arkuszu |
| `sheet_width` | `float` | Szerokosc arkusza [mm] |
| `sheet_height` | `float` | Nominalna wysokosc arkusza [mm] |
| `used_width` | `float` | Maksymalna uzyta szerokosc [mm] |
| `used_height` | `float` | **maxY - maksymalna uzyta wysokosc [mm]** |
| `total_parts_area` | `float` | Suma powierzchni detali [mm2] |
| `used_sheet_area` | `float` | Powierzchnia uzyta [mm2] |
| `efficiency` | `float` | Efektywnosc wykorzystania (0-1) |
| `sheet_cost` | `float` | Koszt pelnego arkusza [PLN] |
| `used_sheet_cost` | `float` | Koszt uzytej czesci [PLN] |
| `total_cut_length_mm` | `float` | Laczna dlugosc ciecia [mm] |
| `total_pierce_count` | `int` | Laczna liczba przebic |
| `cut_time_classic_s` | `float` | Czas ciecia klasyczny [s] |
| `cut_time_dynamic_s` | `float` | Czas ciecia dynamiczny [s] |

## NestedPart

Pojedynczy detal umieszczony na arkuszu.

| Pole | Typ | Opis |
|------|-----|------|
| `name` | `str` | Nazwa detalu |
| `source_part_name` | `str` | Oryginalna nazwa |
| `x` | `float` | Pozycja X na arkuszu [mm] |
| `y` | `float` | Pozycja Y na arkuszu [mm] |
| `width` | `float` | Szerokosc po rotacji [mm] |
| `height` | `float` | Wysokosc po rotacji [mm] |
| `rotation` | `float` | Rotacja (0 lub 90 stopni) |
| `contour_area` | `float` | Powierzchnia konturu [mm2] |
| `weight_kg` | `float` | Waga detalu [kg] |
| `material_cost` | `float` | Koszt materialu [PLN] |
| `cut_length_mm` | `float` | Dlugosc ciecia [mm] |
| `pierce_count` | `int` | Liczba przebic |
| `cut_time_classic_s` | `float` | Czas ciecia klasyczny [s] |
| `cut_time_dynamic_s` | `float` | Czas ciecia dynamiczny [s] |
| `sheet_index` | `int` | Indeks arkusza |
| `part_index` | `int` | Indeks detalu |
| `filepath` | `str` | Sciezka do pliku DXF |

## Regula 94% (FULL_SHEET_THRESHOLD)

### Definicja

Jesli `used_height` (maxY z nestingu) >= 94% nominalnej wysokosci arkusza, traktujemy arkusz jako **pelny**.

```python
FULL_SHEET_THRESHOLD = 0.94

if used_height >= sheet_height * 0.94:
    # Uzyj pelny arkusz - pozostaly pasek za maly
    effective_area = sheet_width * sheet_height  # nominal
else:
    # Tryb CUT_TO_LENGTH
    effective_area = sheet_width * (used_height + trim_margin)
```

### Uzasadnienie

Pozostaly pasek blachy (6% lub mniej z nominalnej wysokosci) jest zazwyczaj:
- Za maly do dalszego wykorzystania
- Trudny w obrobce
- Zostanie zlomowany

Dlatego lepiej obliczyc koszt na podstawie pelnego arkusza.

### Przyklady

| Arkusz | Nominalna wys. | maxY | Procent | Decyzja |
|--------|----------------|------|---------|---------|
| 1500x3000 | 3000 mm | 2850 mm | 95% | PELNY ARKUSZ |
| 1500x3000 | 3000 mm | 2700 mm | 90% | CUT_TO_LENGTH |
| 1500x3000 | 3000 mm | 2820 mm | 94% | PELNY ARKUSZ |
| 1500x3000 | 3000 mm | 2819 mm | 93.9% | CUT_TO_LENGTH |

### Implementacja

Regula jest zaimplementowana w:
- `costing/material/allocation.py` - stala `FULL_SHEET_THRESHOLD` i metoda `SheetSpec.should_use_full_sheet()`
- Wliczona w obliczenia `area_used_mm2`

## Eksport do JSON

Uzyj skryptu `scripts/test_nesting_data_export.py`:

```python
from scripts.test_nesting_data_export import export_nesting_result

# Po wykonaniu nestingu:
data = export_nesting_result(nesting_result, "output.json")
```

### Przykladowy JSON

```json
{
  "export_timestamp": "2025-12-08T16:30:00",
  "summary": {
    "sheets_used": 1,
    "total_efficiency_percent": 72.5,
    "total_placed_parts": 15,
    "total_unplaced_parts": 0,
    "used_height_mm": 2850.0
  },
  "sheets": [
    {
      "sheet_index": 0,
      "sheet_height_mm": 3000.0,
      "used_height_mm": 2850.0,
      "_94_percent_rule": {
        "utilization_percent": 95.0,
        "should_use_full_sheet": true
      },
      "placed_parts": [...]
    }
  ]
}
```

## Wazne pola dla kalkulacji kosztow

### Koszty materialowe
- `sheet_cost` - koszt pelnego arkusza
- `used_sheet_cost` - koszt z uwzglednieniem reguly 94%
- `material_cost` (NestedPart) - koszt materialu przypisany do detalu

### Koszty ciecia
- `cut_length_mm` - dlugosc ciecia [mm]
- `pierce_count` - liczba przebic
- `cut_time_classic_s` - czas klasyczny (dlugosc/predkosc)
- `cut_time_dynamic_s` - czas z planera ruchu

### maxY = used_height

Kluczowe dla reguly 94%:
- `SheetResult.used_height` = max(y + height) dla wszystkich detali
- `NestingResult.used_height` = max ze wszystkich arkuszy
