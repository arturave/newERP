# dxf_area_calculator.py
"""
DXF Area Calculator - Obliczanie powierzchni i wagi detali z plików DXF
========================================================================
Wykorzystuje biblioteki ezdxf i shapely do precyzyjnego obliczania:
- Powierzchni brutto (kontur zewnętrzny)
- Powierzchni netto (kontur - otwory = rzeczywisty materiał)
- Powierzchni bounding box
- Wagi na podstawie grubości i gęstości materiału
"""

from __future__ import annotations

import math
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# Sprawdź dostępność bibliotek
try:
    import ezdxf
    from ezdxf.entities import LWPolyline, Line, Arc, Circle, Spline, Polyline
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.warning("Brak biblioteki 'ezdxf'. Zainstaluj: pip install ezdxf")

try:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    logger.warning("Brak biblioteki 'shapely'. Zainstaluj: pip install shapely")

HAS_LIBS = HAS_EZDXF and HAS_SHAPELY

# Warstwy do ignorowania
IGNORE_LAYERS = {
    "RAMKA", "WYMIARY", "DIM", "TEXT", "TEKST", "OPIS", "DEFPOINTS",
    "ASSEMBLY", "HIDDEN", "CENTER", "CUTLINE", "GRID", "TITLE",
    "BLOCK", "LOGO", "INFO", "FRAME", "BORDER", "AM_",
    "NOTES", "KOTY", "ZAKRES",
}

# --- ROZPOZNAWANIE OPERACJI TECHNOLOGICZNYCH ---

# Słowa kluczowe dla Grawerowania/Markowania (w nazwie warstwy)
MARKING_KEYWORDS = {
    "grawer", "marking", "opis", "text", "engrave", "mark", "sign"
}

# Słowa kluczowe dla Gięcia (w nazwie warstwy)
BENDING_KEYWORDS = {
    "bend", "gięcie", "big", "inner_bend", "outer_bend", "k-factor", "folding"
}

# Priorytetowy kolor dla graweru (AutoCAD Color Index: 2 = Żółty)
GRAWER_COLOR_INDEX = 2

# Gęstości materiałów [kg/m³]
MATERIAL_DENSITIES = {
    # Stale konstrukcyjne
    'S235': 7850,
    'S355': 7850,
    'S235JR': 7850,
    'S355J2': 7850,
    'DC01': 7850,
    'DC04': 7850,
    'DX51': 7850,
    'DD11': 7850,
    'DD13': 7850,

    # Stale nierdzewne (INOX)
    '1.4301': 7900,
    '1.4307': 7900,
    '1.4404': 7950,
    '1.4571': 7950,
    '304': 7900,
    '316': 7950,
    '316L': 7950,
    'INOX': 7900,
    'INOX304': 7900,
    'INOX316': 7950,

    # Aluminium
    'AL': 2700,
    'ALU': 2700,
    'ALUMINIUM': 2700,
    '5754': 2660,
    '5083': 2660,
    '6061': 2700,
    '6082': 2700,
    '1050': 2710,
    '2024': 2780,
    'AlMg3': 2660,

    # Miedź i mosiądz
    'CU': 8960,
    'COPPER': 8960,
    'BRASS': 8500,
    'MOSIADZ': 8500,

    # Domyślna wartość dla stali
    'DEFAULT': 7850,
    'NIEZNANY': 7850,
    'UNKNOWN': 7850,
}


def get_density(material: str) -> float:
    """
    Pobierz gęstość materiału [kg/m³].

    Args:
        material: Nazwa materiału (np. 'S355', '1.4301', 'ALU')

    Returns:
        Gęstość w kg/m³
    """
    if not material:
        return MATERIAL_DENSITIES['DEFAULT']

    # Normalizuj nazwę
    mat_upper = material.upper().strip()

    # Szukaj dokładnego dopasowania
    if mat_upper in MATERIAL_DENSITIES:
        return MATERIAL_DENSITIES[mat_upper]

    # Szukaj częściowego dopasowania
    for key, density in MATERIAL_DENSITIES.items():
        if key in mat_upper or mat_upper in key:
            return density

    # Wykryj typ materiału po prefiksie
    if mat_upper.startswith('1.4'):
        return 7900  # INOX
    elif mat_upper.startswith('S') and mat_upper[1:].isdigit():
        return 7850  # Stal konstrukcyjna
    elif mat_upper.startswith('AL') or mat_upper.startswith('50') or mat_upper.startswith('60'):
        return 2700  # Aluminium
    elif mat_upper.startswith('DC') or mat_upper.startswith('DD') or mat_upper.startswith('DX'):
        return 7850  # Stal do tłoczenia

    return MATERIAL_DENSITIES['DEFAULT']


@dataclass
class AreaResult:
    """Struktura danych przechowująca wyniki obliczeń powierzchni i wagi."""
    filepath: str

    # Powierzchnie [mm²]
    area_gross_sq_mm: float   # Brutto: kontur zewnętrzny bez otworów
    area_net_sq_mm: float     # Netto: kontur - otwory (rzeczywisty materiał)
    area_bbox_sq_mm: float    # Bounding box

    # Wagi [kg]
    weight_gross_kg: float    # Waga na podstawie Area Gross
    weight_net_kg: float      # Waga na podstawie Area Net (rzeczywista)
    weight_bbox_kg: float     # Waga na podstawie Area BBox

    # --- OPERACJE TECHNOLOGICZNE ---
    piercing_count: int = 0         # Liczba przebić (= liczba konturów: 1 zewnętrzny + N otworów)
    len_total_contour_mm: float = 0.0   # Całkowita długość wszystkich linii
    len_marking_mm: float = 0.0     # Długość linii grawerowania
    len_bending_mm: float = 0.0     # Długość linii gięcia
    len_laser_cut_mm: float = 0.0   # Długość cięcia laserem (total - grawer - gięcie opcjonalnie)

    # Metadane
    thickness_mm: float = 0.0
    density_kg_m3: float = 0.0
    material: str = ""


def calculate_weight_kg(area_sq_mm: float, thickness_mm: float, density_kg_m3: float) -> float:
    """
    Oblicza wagę w kilogramach.

    Wzór: Waga [kg] = Powierzchnia [m²] × Grubość [m] × Gęstość [kg/m³]

    Konwersje:
    - mm² → m²: dzielenie przez 10^6
    - mm → m: dzielenie przez 10^3

    Ostateczny wzór: Waga = (Area [mm²] × Thickness [mm] × Density [kg/m³]) / 10^9

    Args:
        area_sq_mm: Powierzchnia w mm²
        thickness_mm: Grubość w mm
        density_kg_m3: Gęstość w kg/m³

    Returns:
        Waga w kg
    """
    if area_sq_mm <= 0 or thickness_mm <= 0 or density_kg_m3 <= 0:
        return 0.0

    return (area_sq_mm * thickness_mm * density_kg_m3) / 1_000_000_000.0


def _is_layer_match(layer_name: str, keywords: set) -> bool:
    """Sprawdza czy nazwa warstwy zawiera słowo kluczowe (case-insensitive)."""
    lname = layer_name.lower()
    for kw in keywords:
        if kw in lname:
            return True
    return False


def _calculate_entity_length(entity) -> float:
    """
    Oblicza długość pojedynczej encji DXF (LINE, CIRCLE, ARC, LWPOLYLINE, SPLINE).
    """
    import math
    length = 0.0
    dxftype = entity.dxftype()

    try:
        if dxftype == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            length = math.dist((start.x, start.y), (end.x, end.y))

        elif dxftype == 'CIRCLE':
            length = 2 * math.pi * entity.dxf.radius

        elif dxftype == 'ARC':
            start_angle = entity.dxf.start_angle
            end_angle = entity.dxf.end_angle
            radius = entity.dxf.radius
            angle_diff = end_angle - start_angle
            if angle_diff < 0:
                angle_diff += 360
            length = math.radians(angle_diff) * radius

        elif dxftype in ('LWPOLYLINE', 'POLYLINE'):
            if hasattr(entity, 'get_points'):
                try:
                    from ezdxf import path
                    p = path.make_path(entity)
                    length = p.length()
                except:
                    pts = entity.get_points('xy')
                    for i in range(len(pts) - 1):
                        length += math.dist(pts[i], pts[i+1])
                    if entity.is_closed:
                        length += math.dist(pts[-1], pts[0])

        elif dxftype == 'SPLINE':
            try:
                from ezdxf import path
                p = path.make_path(entity)
                length = p.length()
            except:
                pass

        elif dxftype == 'ELLIPSE':
            try:
                from ezdxf import path
                p = path.make_path(entity)
                length = p.length()
            except:
                pass

    except Exception as e:
        pass

    return length


def _extract_polyline_points(entity) -> List[Tuple[float, float]]:
    """Ekstrahuj punkty z encji typu polyline/lwpolyline"""
    points = []
    try:
        if entity.dxftype() == 'LWPOLYLINE':
            points = [(p[0], p[1]) for p in entity.get_points('xy')]
        elif entity.dxftype() == 'POLYLINE':
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        elif entity.dxftype() == 'LINE':
            points = [
                (entity.dxf.start.x, entity.dxf.start.y),
                (entity.dxf.end.x, entity.dxf.end.y)
            ]
        elif entity.dxftype() == 'CIRCLE':
            # Aproksymuj okrąg jako wielokąt 32-punktowy
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            points = [(cx + r * math.cos(2 * math.pi * i / 32),
                       cy + r * math.sin(2 * math.pi * i / 32)) for i in range(32)]
    except Exception:
        pass
    return points


def _chain_lines_to_polygon(lines: List[Tuple[Tuple[float, float], Tuple[float, float]]],
                            tolerance: float = 0.1) -> Optional[List[Tuple[float, float]]]:
    """
    Łączy listę linii w zamknięty kontur.

    Args:
        lines: Lista linii jako ((x1,y1), (x2,y2))
        tolerance: Tolerancja łączenia punktów [mm]

    Returns:
        Lista punktów zamkniętego konturu lub None
    """
    if not lines:
        return None

    def dist(p1, p2):
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    # Kopiuj linie (można je odwracać)
    remaining = list(lines)
    chain = list(remaining.pop(0))  # Zacznij od pierwszej linii

    max_iterations = len(lines) * 2
    iterations = 0

    while remaining and iterations < max_iterations:
        iterations += 1
        found = False

        for i, line in enumerate(remaining):
            p1, p2 = line

            # Sprawdź połączenie z końcem łańcucha
            if dist(chain[-1], p1) < tolerance:
                chain.append(p2)
                remaining.pop(i)
                found = True
                break
            elif dist(chain[-1], p2) < tolerance:
                chain.append(p1)
                remaining.pop(i)
                found = True
                break

        if not found:
            break

    # Sprawdź czy kontur jest zamknięty
    if len(chain) >= 3 and dist(chain[0], chain[-1]) < tolerance:
        return chain

    return None


def _build_polygon_from_entities(msp, ignore_layers: set) -> Optional[Polygon]:
    """
    Buduje wielokąt ze wszystkich encji geometrycznych w modelspace.

    Zbiera punkty z LINE, CIRCLE, ARC, LWPOLYLINE i tworzy convex hull.
    """
    all_points = []
    outer_lines = []  # Linie z warstwy "OUTER" lub podobnej

    for entity in msp:
        etype = entity.dxftype()
        layer = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else ''

        if any(ign in layer for ign in ignore_layers):
            continue

        try:
            if etype == 'LINE':
                p1 = (entity.dxf.start.x, entity.dxf.start.y)
                p2 = (entity.dxf.end.x, entity.dxf.end.y)
                all_points.extend([p1, p2])
                if 'OUTER' in layer or 'EXTERNAL' in layer or 'CONTOUR' in layer:
                    outer_lines.append((p1, p2))

            elif etype == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                # 8 punktów na okręgu dla convex hull
                for i in range(8):
                    angle = 2 * math.pi * i / 8
                    all_points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

            elif etype == 'ARC':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                start_angle = math.radians(entity.dxf.start_angle)
                end_angle = math.radians(entity.dxf.end_angle)
                # Punkty na łuku
                if end_angle < start_angle:
                    end_angle += 2 * math.pi
                steps = max(4, int((end_angle - start_angle) / (math.pi / 4)))
                for i in range(steps + 1):
                    angle = start_angle + (end_angle - start_angle) * i / steps
                    all_points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

            elif etype == 'LWPOLYLINE':
                for p in entity.get_points('xy'):
                    all_points.append((p[0], p[1]))

            elif etype == 'POLYLINE':
                for v in entity.vertices:
                    all_points.append((v.dxf.location.x, v.dxf.location.y))

        except Exception:
            pass

    if not all_points:
        return None

    # Metoda 1: Jeśli mamy linie zewnętrzne, spróbuj je połączyć
    if outer_lines and len(outer_lines) >= 3:
        chain = _chain_lines_to_polygon(outer_lines, tolerance=0.5)
        if chain and len(chain) >= 3:
            try:
                poly = Polygon(chain)
                if poly.is_valid and poly.area > 0:
                    return poly
            except Exception:
                pass

    # Metoda 2: Convex hull wszystkich punktów (przybliżenie konturu zewnętrznego)
    if len(all_points) >= 3:
        try:
            from shapely.geometry import MultiPoint
            hull = MultiPoint(all_points).convex_hull
            if hull.geom_type == 'Polygon' and hull.area > 0:
                return hull
        except Exception:
            pass

    return None


# Alias dla kompatybilności
_build_polygon_from_lines = _build_polygon_from_entities


def _get_shapely_polygon(dxf_path: Path) -> Optional[Polygon]:
    """
    Ładuje DXF i ekstrahuje główny wielokąt (kontur + otwory) jako obiekt Shapely.

    Ręcznie ekstrahuje kontury z encji LWPOLYLINE, POLYLINE, CIRCLE.
    """
    if not HAS_LIBS:
        return None

    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        # Zbierz wszystkie zamknięte kontury
        polygons = []

        for entity in msp:
            # Pomijaj warstwy ignorowane
            layer = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else ''
            if any(ign in layer for ign in IGNORE_LAYERS):
                continue

            # Sprawdź czy to zamknięty kontur
            is_closed = False
            if entity.dxftype() == 'LWPOLYLINE':
                is_closed = entity.closed
            elif entity.dxftype() == 'POLYLINE':
                is_closed = entity.is_closed
            elif entity.dxftype() == 'CIRCLE':
                is_closed = True

            if not is_closed:
                continue

            points = _extract_polyline_points(entity)
            if len(points) >= 3:
                try:
                    poly = Polygon(points)
                    if poly.is_valid and poly.area > 0:
                        polygons.append(poly)
                except Exception:
                    pass

        # Największy wielokąt = kontur główny
        main_polygon = max(polygons, key=lambda p: p.area) if polygons else None

        # Zawsze oblicz convex hull jako alternatywę
        line_polygon = _build_polygon_from_lines(msp, IGNORE_LAYERS)

        # Wybierz większy wielokąt między znalezionym a convex hull
        # (convex hull lepiej reprezentuje zewnętrzny kontur gdy są małe elementy jak otwory)
        if line_polygon:
            if not main_polygon:
                logger.debug(f"Używam convex hull dla: {dxf_path.name} (area={line_polygon.area:.0f}mm²)")
                return line_polygon
            elif line_polygon.area > main_polygon.area * 2:
                # Convex hull jest znacznie większy - użyj go
                logger.debug(f"Convex hull większy dla: {dxf_path.name} (hull={line_polygon.area:.0f} vs poly={main_polygon.area:.0f}mm²)")
                return line_polygon

        if not main_polygon:
            logger.warning(f"Brak zamkniętych konturów w pliku: {dxf_path.name}")
            return None

        # Mniejsze wielokąty wewnątrz głównego = otwory
        holes = []
        for poly in polygons:
            if poly != main_polygon and main_polygon.contains(poly):
                holes.append(poly.exterior.coords)

        # Utwórz wielokąt z otworami
        if holes:
            polygon_with_holes = Polygon(main_polygon.exterior.coords, holes)
        else:
            polygon_with_holes = main_polygon

        # Naprawa nieprawidłowej geometrii
        if not polygon_with_holes.is_valid:
            polygon_with_holes = polygon_with_holes.buffer(0)

        # Obsługa MultiPolygon
        if polygon_with_holes.geom_type == 'MultiPolygon':
            return max(polygon_with_holes.geoms, key=lambda g: g.area)

        return polygon_with_holes

    except ezdxf.DXFError as e:
        logger.error(f"Błąd odczytu DXF {dxf_path.name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd dla {dxf_path.name}: {e}")
        return None


def calculate_area_from_contour(
    outer_contour: List[Tuple[float, float]],
    holes: List[List[Tuple[float, float]]] = None
) -> Tuple[float, float, float]:
    """
    Oblicz powierzchnie na podstawie konturu i otworów (bez pliku DXF).

    Używa formuły Shoelace dla wielokątów.

    Args:
        outer_contour: Lista punktów konturu zewnętrznego [(x, y), ...]
        holes: Lista otworów, każdy jako lista punktów

    Returns:
        Tuple (area_gross, area_net, area_bbox) w mm²
    """
    if not outer_contour or len(outer_contour) < 3:
        return 0.0, 0.0, 0.0

    # Formuła Shoelace dla konturu zewnętrznego
    def shoelace(points):
        n = len(points)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]
        return abs(area) / 2.0

    area_gross = shoelace(outer_contour)

    # Odejmij otwory
    holes_area = 0.0
    if holes:
        for hole in holes:
            if len(hole) >= 3:
                holes_area += shoelace(hole)

    area_net = area_gross - holes_area

    # Bounding box
    xs = [p[0] for p in outer_contour]
    ys = [p[1] for p in outer_contour]
    area_bbox = (max(xs) - min(xs)) * (max(ys) - min(ys))

    return area_gross, area_net, area_bbox


def calculate_weight_from_contour(
    outer_contour: List[Tuple[float, float]],
    holes: List[List[Tuple[float, float]]] = None,
    thickness_mm: float = 1.0,
    material: str = "S355"
) -> float:
    """
    Oblicz wagę detalu na podstawie konturu.

    Args:
        outer_contour: Lista punktów konturu zewnętrznego
        holes: Lista otworów
        thickness_mm: Grubość w mm
        material: Nazwa materiału

    Returns:
        Waga w kg (na podstawie area_net - rzeczywista waga materiału)
    """
    _, area_net, _ = calculate_area_from_contour(outer_contour, holes)
    density = get_density(material)
    return calculate_weight_kg(area_net, thickness_mm, density)


def process_dxf_file(
    filepath: str,
    thickness_mm: float = 1.0,
    material: str = "S355",
    bending_line_as_grawer: bool = False
) -> Optional[AreaResult]:
    """
    Główna funkcja przetwarzająca plik DXF i obliczająca wszystkie metryki.

    Args:
        filepath: Ścieżka do pliku DXF
        thickness_mm: Grubość materiału w mm
        material: Nazwa materiału (dla gęstości)
        bending_line_as_grawer: Jeśli True, linie gięcia odejmowane od długości cięcia

    Returns:
        AreaResult z obliczonymi powierzchniami, wagami i parametrami operacyjnymi lub None
    """
    path = Path(filepath)
    if not path.is_file():
        logger.error(f"Plik nie istnieje: {filepath}")
        return None

    density = get_density(material)

    # Domyślne wartości
    area_gross_sq_mm = 0.0
    area_net_sq_mm = 0.0
    area_bbox_sq_mm = 0.0
    weight_gross_kg = 0.0
    weight_net_kg = 0.0
    weight_bbox_kg = 0.0
    piercing_count = 0
    len_total = 0.0
    len_marking = 0.0
    len_bending = 0.0

    if not HAS_LIBS:
        logger.warning(f"Brak bibliotek ezdxf/shapely dla {path.name}")
        return None

    try:
        doc = ezdxf.readfile(str(path))
        msp = doc.modelspace()
    except Exception as e:
        logger.error(f"Błąd odczytu pliku {path.name}: {e}")
        return None

    # --- 1. OBLICZENIA POWIERZCHNI ---
    polygon = _get_shapely_polygon(path)
    if polygon:
        area_net_sq_mm = polygon.area
        area_gross_sq_mm = Polygon(polygon.exterior).area
        min_x, min_y, max_x, max_y = polygon.bounds
        area_bbox_sq_mm = (max_x - min_x) * (max_y - min_y)

        weight_net_kg = calculate_weight_kg(area_net_sq_mm, thickness_mm, density)
        weight_gross_kg = calculate_weight_kg(area_gross_sq_mm, thickness_mm, density)
        weight_bbox_kg = calculate_weight_kg(area_bbox_sq_mm, thickness_mm, density)

        # --- PIERCING COUNT = 1 (kontur zewnętrzny) + liczba otworów ---
        piercing_count = 1 + len(polygon.interiors)

    # --- 2. OBLICZENIA DŁUGOŚCI (Iteracja po encjach) ---
    for entity in msp:
        layer_name = entity.dxf.layer

        # Pomijamy warstwy ignorowane
        if layer_name.upper() in IGNORE_LAYERS:
            continue

        # Oblicz długość encji
        length = _calculate_entity_length(entity)
        if length <= 0:
            continue

        len_total += length

        # Klasyfikacja operacji
        try:
            color = entity.dxf.color
        except:
            color = 0

        # A. GRAWER: Priorytet 1 - Kolor Żółty (index 2), Priorytet 2 - Nazwa warstwy
        is_grawer = False
        if color == GRAWER_COLOR_INDEX:
            is_grawer = True
        elif _is_layer_match(layer_name, MARKING_KEYWORDS):
            is_grawer = True

        if is_grawer:
            len_marking += length
            continue

        # B. GIĘCIE: Na podstawie nazwy warstwy
        if _is_layer_match(layer_name, BENDING_KEYWORDS):
            len_bending += length
            continue

    # --- 3. LOGIKA KOŃCOWA ---
    # Długość cięcia = Całość - Grawer
    len_laser_cut = len_total - len_marking

    if bending_line_as_grawer:
        # Linie gięcia traktowane jako niecięte (pomocnicze)
        len_laser_cut -= len_bending

    return AreaResult(
        filepath=filepath,
        area_gross_sq_mm=area_gross_sq_mm,
        area_net_sq_mm=area_net_sq_mm,
        area_bbox_sq_mm=area_bbox_sq_mm,
        weight_gross_kg=weight_gross_kg,
        weight_net_kg=weight_net_kg,
        weight_bbox_kg=weight_bbox_kg,
        piercing_count=piercing_count,
        len_total_contour_mm=len_total,
        len_marking_mm=len_marking,
        len_bending_mm=len_bending,
        len_laser_cut_mm=len_laser_cut,
        thickness_mm=thickness_mm,
        density_kg_m3=density,
        material=material
    )


# === TEST ===
if __name__ == "__main__":
    print("=== Test DXF Area Calculator ===")
    print(f"HAS_EZDXF: {HAS_EZDXF}")
    print(f"HAS_SHAPELY: {HAS_SHAPELY}")
    print()

    # Test gęstości
    test_materials = ['S355', '1.4301', 'ALU', 'DC01', 'NIEZNANY', '']
    for mat in test_materials:
        print(f"Gęstość '{mat}': {get_density(mat)} kg/m³")

    print()

    # Test obliczania wagi z konturu (prosty prostokąt 100x50mm)
    contour = [(0, 0), (100, 0), (100, 50), (0, 50)]
    hole = [(40, 20), (60, 20), (60, 30), (40, 30)]  # Otwór 20x10mm

    area_gross, area_net, area_bbox = calculate_area_from_contour(contour, [hole])
    print(f"Prostokąt 100x50mm z otworem 20x10mm:")
    print(f"  Area Gross: {area_gross:.0f} mm² (oczekiwane: 5000)")
    print(f"  Area Net:   {area_net:.0f} mm² (oczekiwane: 4800)")
    print(f"  Area BBox:  {area_bbox:.0f} mm²")

    weight = calculate_weight_from_contour(contour, [hole], thickness_mm=2.0, material='S355')
    print(f"  Waga (2mm S355): {weight:.3f} kg")

    print()
    print("=== Słowa kluczowe operacji ===")
    print(f"MARKING_KEYWORDS: {MARKING_KEYWORDS}")
    print(f"BENDING_KEYWORDS: {BENDING_KEYWORDS}")
    print(f"GRAWER_COLOR_INDEX: {GRAWER_COLOR_INDEX} (żółty)")
    print()
    print("Nowe pola AreaResult:")
    print("  - piercing_count: liczba przebić (1 kontur + N otworów)")
    print("  - len_total_contour_mm: całkowita długość linii")
    print("  - len_marking_mm: długość grawerowania")
    print("  - len_bending_mm: długość linii gięcia")
    print("  - len_laser_cut_mm: długość cięcia laserem")
