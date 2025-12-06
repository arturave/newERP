# Analiza Algorytmów Nestingu dla NewERP

## Podsumowanie

Nesting (układanie detali na arkuszach blachy) to problem NP-trudny. Zaimplementowano trzy podejścia:

1. **FFDH (Bounding Box)** - szybkie, układa prostokąty
2. **NFP (pyclipper)** - dokładniejsze, Minkowski sum
3. **Shapely (True Shape)** ⭐ - najdokładniejsze, buffer + kolizje

## Zaimplementowane w NewERP

### 1. Szybki Nesting (FFDH) 
- **Plik**: `/quotations/nesting/nester.py`
- **Algorytm**: First Fit Decreasing Height
- **Wykorzystanie**: 50-70%
- **Czas**: ~10ms

### 2. NFP Nesting (pyclipper)
- **Plik**: `/quotations/nesting/nester_advanced.py`
- **Algorytm**: No-Fit Polygon + Bottom-Left
- **Wykorzystanie**: 70-85%
- **Czas**: ~100ms

### 3. Shapely Nesting (True Shape) ⭐ NOWE
- **Plik**: `/quotations/nesting/nester_shapely.py`
- **Algorytm**: Buffer + Intersects + Bottom-Left Fill
- **Wykorzystanie**: 75-90%
- **Czas**: ~200ms
- **Zalety**:
  - Poprawna obsługa kerf (szerokość rzazu)
  - Poprawna obsługa spacing (odstęp między detalami)
  - Eksport do DXF dla maszyny laserowej
  - Obsługa otworów (holes)

## Kluczowe Parametry Nestingu

```python
@dataclass
class NestingParams:
    kerf_width: float = 0.2        # Szerokość rzazu lasera [mm]
    part_spacing: float = 3.0      # Minimalny odstęp między detalami [mm]
    sheet_margin: float = 10.0     # Margines arkusza [mm]
    rotation_angles: List[float]   # [0, 90, 180, 270] lub [0, 15, 30, ...]
```

**Buffer distance** = `kerf_width/2 + part_spacing/2`

To jest kluczowe: każdy detal jest "powiększany" o buffer_distance, dzięki czemu:
- Laser ma miejsce na przejście (kerf)
- Jest bezpieczny odstęp między detalami (spacing)

## Architektura Shapely Nester

```
┌─────────────────┐
│   DXF File      │
└────────┬────────┘
         │ import
         ▼
┌─────────────────┐
│ DXFHandler      │ ezdxf + aproksymacja łuków
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Shapely Polygon │ buffer(), intersects(), contains()
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ShapelyNester   │ Bottom-Left Fill + Rotacje
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ NestingResult   │
└────────┬────────┘
         │ export
         ▼
┌─────────────────┐
│   DXF File      │ Gotowy do cięcia
└─────────────────┘
```

## Algorytm Bottom-Left Fill

```python
def nest(parts, sheet):
    # 1. Sortuj malejąco po polu (duże pierwsze)
    parts.sort(key=lambda p: p.area, reverse=True)
    
    # 2. Dla każdego detalu
    for part in parts:
        best_position = None
        
        # 3. Próbuj każdą rotację
        for angle in [0, 90, 180, 270]:
            rotated = rotate(part, angle)
            buffered = rotated.buffer(kerf/2 + spacing/2)
            
            # 4. Szukaj pozycji od lewego dolnego rogu
            for y in range(margin, sheet_height, step):
                for x in range(margin, sheet_width, step):
                    test = translate(buffered, x, y)
                    
                    # 5. Sprawdź czy mieści się w arkuszu
                    if not sheet.contains(test):
                        continue
                    
                    # 6. Sprawdź kolizję z umieszczonymi
                    if placed_union.intersects(test):
                        continue
                    
                    # 7. Znaleziono!
                    best_position = (x, y, angle)
                    break
        
        if best_position:
            place(part, best_position)
```

## Użycie

```python
from quotations.nesting.nester_shapely import *

# Parametry
params = NestingParams(
    kerf_width=0.2,      # 0.2mm rzaz lasera
    part_spacing=3.0,    # 3mm odstęp
    sheet_margin=10.0,   # 10mm margines
)

# Detale
parts = [
    create_l_shape("L1", "L-Shape", 100, 100, 50, 50, quantity=5),
    create_rectangle("R1", "Rectangle", 80, 40, quantity=10),
]

# Arkusz
sheet = SheetFormat(1000, 2000, "1000x2000")

# Nesting
nester = ShapelyNester(params)
result = nester.nest(parts, sheet)

# Wyniki
print(f"Arkuszy: {result.total_sheets}")
print(f"Wykorzystanie: {result.average_utilization*100:.1f}%")

# Eksport do DXF
nester.export_to_dxf("output.dxf", result, sheet_index=0)
```

## Porównanie Bibliotek

| Biblioteka | Rola | Zalety |
|------------|------|--------|
| **ezdxf** | Import/Export DXF | Pełna obsługa formatu, aktywnie rozwijana |
| **Shapely** | Geometria 2D | buffer(), intersects(), contains(), GEOS backend |
| **pyclipper** | Minkowski sum | Szybkie NFP dla prostych przypadków |

## Obsługa Formatu DWG

Python nie obsługuje natywnie zamkniętego formatu DWG. Rozwiązania:

1. **ODA File Converter** (darmowy) - konwersja DWG → DXF
2. **LibreCAD** - otwarty CAD z konwersją
3. **FreeCAD** - może eksportować do DXF

Workflow:
```
DWG → ODA Converter → DXF → ezdxf → Shapely → Nesting
```

## Przyszłe Ulepszenia

1. **No-Fit Polygon (NFP)** - dokładniejsze granice kolizji
2. **Algorytm Genetyczny** - optymalizacja kolejności i rotacji
3. **GPU Acceleration** - równoległe sprawdzanie kolizji
4. **Obsługa otworów** - nesting wewnątrz otworów innych detali
