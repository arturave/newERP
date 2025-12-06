# Analiza Algorytmów Nestingu dla NewERP

## 1. Przegląd Problemu

Nesting (zagnieżdżanie 2D) to problem optymalizacji rozmieszczenia nieregularnych kształtów
na arkuszach materiału. Jest to problem NP-trudny, więc stosuje się algorytmy heurystyczne
i metaheurystyczne.

### Typy algorytmów:

| Typ | Opis | Zalety | Wady |
|-----|------|--------|------|
| **Bounding Box (FFDH)** | Prostokąty obejmujące | Bardzo szybki | Niskie wykorzystanie dla kształtów nieregularnych |
| **NFP (No-Fit Polygon)** | Rzeczywiste kształty | Dobre wykorzystanie | Wolniejszy, wymaga obliczania NFP |
| **Genetic Algorithm** | Optymalizacja kolejności/rotacji | Może znaleźć globalne optimum | Długi czas obliczeń |
| **Simulated Annealing** | Losowe perturbacje | Unika lokalnych minimów | Wymaga dobrego tuningu |

## 2. Dostępne Rozwiązania

### 2.1 Python Libraries

#### pyclipper (✅ WYBRANE)
- **Źródło**: https://pypi.org/project/pyclipper/
- **Licencja**: MIT / Boost
- **Funkcje**: `MinkowskiSum`, `MinkowskiDiff` → NFP
- **Instalacja**: `pip install pyclipper`
- **Zalety**: Łatwa integracja, stabilna, aktywnie rozwijana
- **Używane w**: SVGnest, wielu projektach nestingowych

```python
import pyclipper
# NFP = Minkowski sum of A and -B
nfp = pyclipper.MinkowskiSum(poly_a, poly_b_negated, True)
```

#### nest2D / libnest2d
- **Źródło**: https://github.com/markfink/nest2D
- **Licencja**: GPL (ograniczona!)
- **Funkcje**: Pełny nester z Python bindings
- **Problem**: Trudna kompilacja (wymaga Boost, Clipper, CMake)
- **Status**: ⚠️ Problemy z instalacją na Windows

#### Shapely
- **Źródło**: https://pypi.org/project/shapely/
- **Funkcje**: Operacje geometryczne, ale **NIE MA** Minkowski sum
- **Użycie**: Walidacja, obliczanie pól, kolizje

### 2.2 C++/Rust Libraries (zewnętrzne wywołanie)

#### DeepNest (JavaScript/Electron)
- **Źródło**: https://github.com/Jack000/Deepnest
- **Licencja**: MIT
- **Algorytm**: NFP + Genetic Algorithm
- **Użycie**: Standalone aplikacja lub jako serwer
- **Integracja**: Można wywołać przez subprocess lub REST API

```bash
# Uruchomienie DeepNest CLI (jeśli dostępne)
deepnest --input parts.svg --output result.svg --sheets 1000x2000
```

#### DeepNestSharp (C#/.NET)
- **Źródło**: https://github.com/9swampy/DeepNestSharp
- **Licencja**: LGPL
- **Zalety**: WPF UI, zapisywanie projektów
- **Integracja**: .NET → można przez pythonnet lub subprocess

#### deepnest-rust-minkowski
- **Źródło**: https://lib.rs/crates/deepnest-rust-minkowski
- **Licencja**: MIT
- **Funkcje**: Obliczanie NFP w Rust (bardzo szybkie)
- **Integracja**: Przez PyO3 bindings lub subprocess

```rust
// Rust API
let nfp = minkowski::no_fit_polygon(&polygon_a, &polygon_b);
```

#### CGAL (C++)
- **Źródło**: https://www.cgal.org/
- **Licencja**: GPL/LGPL
- **Funkcje**: `minkowski_sum_2`, `offset_polygon_2`
- **Python bindings**: scikit-geometry (częściowe)

### 2.3 Zewnętrzne Serwisy

#### SVGnest Online
- **URL**: https://svgnest.com
- **Licencja**: MIT
- **Funkcje**: Web-based nester
- **Integracja**: Możliwa przez Puppeteer/Selenium lub self-hosted

## 3. Architektura Implementacji w NewERP

### Warstwa abstrakcji (Strategy Pattern):

```
┌─────────────────────────────────────────────────────────────┐
│                    NestingManager                            │
│  - select_algorithm(type: str) -> NesterInterface           │
│  - nest(parts, sheet) -> NestingResult                      │
└─────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ FFDHNester  │   │ NFPNester       │   │ DeepNestBridge  │
│ (bounding   │   │ (pyclipper)     │   │ (external)      │
│  box)       │   │                 │   │                 │
└─────────────┘   └─────────────────┘   └─────────────────┘
```

### Implementacja wybrana:

1. **Szybki (FFDH)** - Istniejący `nester.py` - prostokąty, O(n log n)
2. **Dokładny (NFP)** - Nowy `nester_advanced.py` - pyclipper, O(n² × rotacje)
3. **Premium (DeepNest)** - Przyszłość - zewnętrzne wywołanie, najlepsza jakość

## 4. Porównanie Wydajności

| Algorytm | 10 części | 100 części | 1000 części | Wykorzystanie |
|----------|-----------|------------|-------------|---------------|
| FFDH | 1ms | 10ms | 100ms | 60-75% |
| NFP (pyclipper) | 100ms | 2s | 30s | 75-85% |
| DeepNest GA | 5s | 60s | 600s | 85-95% |

## 5. Przyszłe Rozszerzenia

### 5.1 Integracja z DeepNest przez subprocess

```python
import subprocess
import json

def deepnest_external(parts_svg: str, sheet_size: tuple) -> str:
    """Wywołaj DeepNest jako zewnętrzny proces"""
    result = subprocess.run([
        'node', 'deepnest-cli.js',
        '--input', parts_svg,
        '--sheet', f'{sheet_size[0]}x{sheet_size[1]}',
        '--output', '-'  # stdout
    ], capture_output=True, text=True)
    
    return result.stdout
```

### 5.2 Rust NFP przez PyO3

```python
# Przyszła integracja z Rust
import deepnest_rust

nfp = deepnest_rust.compute_nfp(polygon_a, polygon_b)
placement = deepnest_rust.optimize_placement(parts, sheet)
```

### 5.3 GPU Acceleration (CUDA/OpenCL)

Dla bardzo dużych zbiorów części, możliwe przyspieszenie NFP na GPU.

## 6. Rekomendacje

### Dla produkcji:

1. **Domyślnie**: FFDH (szybki, wystarczający dla prostych kształtów)
2. **Dla nieregularnych**: NFP z pyclipper (zaimplementowane)
3. **Dla krytycznych wycen**: Rozważyć integrację z DeepNest

### Wymagania:

```bash
pip install pyclipper ezdxf
```

### Testowanie:

```bash
cd NewERP
python -m quotations.nesting.nester_advanced
```

## 7. Literatura

1. Bennell, J.A., Oliveira, J.F. (2008). "The geometry of nesting problems: A tutorial"
   European Journal of Operational Research, 184(2):397-415

2. Burke, E., Hellier, R., Kendall, G., Whitwell, G. (2006). "A new bottom-left-fill 
   heuristic algorithm for the two-dimensional irregular packing problem"

3. Dean, H.T., Tu, Y., Raffensperger, J.F. (2006). "An improved method for calculating
   the no-fit polygon" Computers & Operations Research, 33:1521-1539

4. Rocha, P. (2019). "Robust NFP generation for Nesting problems" arXiv:1903.11139

## 8. Changelog

- **2024-11**: Implementacja NFP z pyclipper
- **2024-11**: Dodanie wyboru algorytmu w GUI
- **TODO**: Integracja z DeepNest dla premium wycen
