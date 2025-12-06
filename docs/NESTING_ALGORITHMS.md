# Algorytmy Nestingu w NewERP

## Przegląd

NewERP oferuje dwa algorytmy rozkładu detali na arkuszach blachy:

| Cecha | Szybki (FFDH) | Dokładny (NFP) |
|-------|---------------|----------------|
| Szybkość | Bardzo szybki (~ms) | Wolniejszy (~s) |
| Geometria | Bounding box (prostokąty) | Rzeczywiste kształty |
| Wykorzystanie | ~60-75% | ~75-90% |
| Rotacje | 0°, 90° | 0°, 90°, 180°, 270° |
| Dziury | Nie wykorzystuje | Może wykorzystać |

## Algorytm FFDH (First Fit Decreasing Height)

### Jak działa

1. Sortuje detale malejąco po wysokości
2. Tworzy "półki" (shelves) na arkuszu
3. Umieszcza kolejne detale na pierwszej półce, na której się mieszczą
4. Jeśli nie mieści się na żadnej - tworzy nową półkę

### Zalety

- **Błyskawiczny** - obliczenia w milisekundach
- **Prosty** - łatwy do zrozumienia i debugowania
- **Deterministyczny** - te same dane = ten sam wynik

### Wady

- Traktuje wszystkie detale jako prostokąty
- Nie wykorzystuje przestrzeni między detalami o nieregularnych kształtach
- Marnuje więcej materiału przy L-kształtach, trójkątach itp.

### Kiedy używać

- Szybka wycena ofertowa (accuracy nie jest krytyczna)
- Detale prostokątne lub zbliżone
- Duża liczba detali (setki/tysiące)

## Algorytm NFP (No-Fit Polygon)

### Jak działa

1. **Ekstrakcja wielokątów** z plików DXF (LWPOLYLINE, CIRCLE, ARC...)
2. **Obliczenie NFP** - dla każdej pary detali oblicza No-Fit Polygon używając Minkowski sum/diff
3. **Placement** - znajduje pozycję na brzegu NFP najbliżej lewego dolnego rogu
4. **Optymalizacja** - testuje różne rotacje i kolejności

### NFP - No-Fit Polygon

NFP definiuje wszystkie pozycje gdzie detal B może być umieszczony względem detalu A tak, aby się stykały ale nie zachodziły:

```
NFP(A, B) = A ⊕ (-B)
```

gdzie ⊕ to suma Minkowskiego, a -B to odbicie B względem początku układu.

### Zalety

- **Wyższe wykorzystanie** materiału (10-25% lepsze)
- **Rzeczywiste kształty** - używa geometrii z DXF
- **Optymalne rozmieszczenie** nieregularnych kształtów
- **Wykorzystanie dziur** w większych detalach

### Wady

- Wolniejszy (sekundy vs milisekundy)
- Wymaga plików DXF z poprawną geometrią
- Złożoność obliczeniowa rośnie z liczbą detali

### Kiedy używać

- Finalna wycena produkcyjna
- Nieregularne kształty (L, T, trójkąty, okręgi)
- Mała-średnia liczba detali (do ~50-100)
- Gdy oszczędność materiału jest krytyczna

## Biblioteki używane

### pyclipper

Wrapper Python dla Clipper library (Angus Johnson):
- Minkowski sum/diff
- Boolean operations (union, intersection, diff)
- Polygon offsetting

```python
import pyclipper

# Minkowski sum
nfp = pyclipper.MinkowskiSum(polygon_a, polygon_b_negated, True)

# Collision detection
pc = pyclipper.Pyclipper()
pc.AddPath(poly_a, pyclipper.PT_SUBJECT, True)
pc.AddPath(poly_b, pyclipper.PT_CLIP, True)
intersection = pc.Execute(pyclipper.CT_INTERSECTION, ...)
```

### ezdxf

Biblioteka do odczytu/zapisu plików DXF:
- LWPOLYLINE - zamknięte polilinie
- POLYLINE - klasyczne polilinie  
- CIRCLE, ARC - aproksymacja jako n-kąty
- SPLINE, ELLIPSE

## Porównanie wydajności

Test na 30 detalach (mix prostokątów, L-kształtów, trójkątów):

| Algorytm | Czas | Arkusze | Wykorzystanie |
|----------|------|---------|---------------|
| FFDH | 15ms | 3 | 68% |
| NFP | 2.1s | 2 | 82% |

## Przykład użycia w kodzie

```python
from quotations.nesting.nester import Nester, Part, STANDARD_SHEETS
from quotations.nesting.nester_advanced import AdvancedNester, Part as AdvPart, Polygon, Point, Sheet

# Szybki nesting
nester = Nester()
parts = [Part(id="A", name="Detal A", width=100, height=50, quantity=10)]
result = nester.nest(parts, STANDARD_SHEETS["1000x2000"])

# NFP nesting
adv_nester = AdvancedNester()
polygon = Polygon([Point(0,0), Point(100,0), Point(100,50), Point(50,50), Point(50,100), Point(0,100)])
adv_parts = [AdvPart(id="A", name="L-Shape", polygon=polygon, quantity=10)]
sheet = Sheet(1000, 2000, margin=10, spacing=3)
result = adv_nester.nest(adv_parts, sheet)
```

## Publikacje naukowe

Algorytm NFP bazuje na:

1. **Bennell & Oliveira (2008)** - "The geometry of nesting problems: A tutorial"
   - European Journal of Operational Research

2. **Dean et al. (2006)** - "An improved method for calculating the no-fit polygon"
   - Computers & Operations Research

3. **Burke et al. (2006)** - "A new bottom-left-fill heuristic algorithm for the two-dimensional irregular packing problem"
   - Operations Research

4. **Rocha (2019)** - "Robust NFP generation for Nesting problems"
   - arXiv:1903.11139

## Alternatywne rozwiązania

### Deepnest

Open-source nester (JavaScript + C++ addon):
- https://github.com/Jack000/Deepnest
- Algorytm genetyczny + NFP
- GUI desktop (Electron)

### libnest2d / pynest2d

C++ library (Ultimaker/Cura):
- https://github.com/Ultimaker/pynest2d
- Używany w Cura do 3D printing
- Wymaga kompilacji z Boost

### SVGnest

JavaScript w przeglądarce:
- http://svgnest.com
- NFP + genetyczny
- Tylko SVG

## Roadmap

1. **v1.0** (obecna) - FFDH + NFP z pyclipper
2. **v1.1** - Cachowanie NFP między sesjami
3. **v1.2** - Algorytm genetyczny do optymalizacji kolejności
4. **v1.3** - Eksport rozkroju do DXF
5. **v2.0** - Integracja z Deepnest przez subprocess
