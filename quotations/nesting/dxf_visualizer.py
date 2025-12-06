"""
DXF Visualizer - Moduł do wizualizacji i testowania odczytu plików DXF
======================================================================

Służy do:
1. Odczytu konturu zewnętrznego z DXF
2. Konwersji łuków na punkty wielokąta
3. Wizualizacji wyniku
"""

import math
import logging
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Import ezdxf
try:
    import ezdxf
    from ezdxf.entities import Line, Arc, Circle, LWPolyline, Spline
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.warning("ezdxf not installed")

# Import shapely dla operacji geometrycznych
try:
    from shapely.geometry import Polygon, Point, LineString
    from shapely.ops import unary_union
    from shapely import affinity
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    logger.warning("shapely not installed")


@dataclass
class DXFPart:
    """Detal odczytany z DXF"""
    name: str
    outer_contour: List[Tuple[float, float]]  # Punkty konturu zewnętrznego
    holes: List[List[Tuple[float, float]]]    # Punkty otworów wewnętrznych
    
    # Bounding box
    min_x: float = 0
    max_x: float = 0
    min_y: float = 0
    max_y: float = 0
    
    @property
    def width(self) -> float:
        return self.max_x - self.min_x
    
    @property
    def height(self) -> float:
        return self.max_y - self.min_y
    
    @property
    def area(self) -> float:
        """Pole powierzchni (kontur - otwory)"""
        if not HAS_SHAPELY:
            return self.width * self.height
        
        try:
            if len(self.outer_contour) < 3:
                return 0
            outer = Polygon(self.outer_contour)
            if not outer.is_valid:
                outer = outer.buffer(0)
            
            # Odejmij otwory
            for hole in self.holes:
                if len(hole) >= 3:
                    h = Polygon(hole)
                    if h.is_valid:
                        outer = outer.difference(h)
            
            return outer.area
        except Exception:
            return self.width * self.height


def arc_to_points(
    center_x: float, center_y: float,
    radius: float,
    start_angle: float, end_angle: float,
    resolution: int = 8
) -> List[Tuple[float, float]]:
    """
    Konwertuj łuk na listę punktów.
    
    Args:
        center_x, center_y: Środek łuku
        radius: Promień
        start_angle, end_angle: Kąty w stopniach
        resolution: Liczba punktów na 90 stopni
    
    Returns:
        Lista punktów (x, y)
    """
    points = []
    
    # Normalizuj kąty
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)
    
    # Obsłuż przypadek gdy end < start (łuk przechodzi przez 0°)
    if end_angle < start_angle:
        end_rad += 2 * math.pi
    
    # Oblicz liczbę punktów na podstawie długości łuku
    arc_length = abs(end_rad - start_rad)
    num_points = max(3, int(arc_length / (math.pi / 2) * resolution) + 1)
    
    for i in range(num_points + 1):
        t = i / num_points
        angle = start_rad + t * (end_rad - start_rad)
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))
    
    return points


def circle_to_points(
    center_x: float, center_y: float,
    radius: float,
    resolution: int = 16
) -> List[Tuple[float, float]]:
    """
    Konwertuj okrąg na listę punktów.
    """
    points = []
    for i in range(resolution):
        angle = 2 * math.pi * i / resolution
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))
    points.append(points[0])  # Zamknij
    return points


def find_nearest_point(
    point: Tuple[float, float],
    candidates: List[Tuple[float, float]],
    tolerance: float = 0.1
) -> Optional[int]:
    """Znajdź najbliższy punkt w liście."""
    min_dist = float('inf')
    min_idx = None
    
    for i, c in enumerate(candidates):
        dist = math.sqrt((point[0] - c[0])**2 + (point[1] - c[1])**2)
        if dist < min_dist and dist < tolerance:
            min_dist = dist
            min_idx = i
    
    return min_idx


def build_contour_from_entities(
    entities: List,
    arc_resolution: int = 8
) -> List[Tuple[float, float]]:
    """
    Zbuduj zamknięty kontur z encji DXF (linie, łuki).
    
    Algorytm:
    1. Konwertuj wszystkie encje na segmenty (listy punktów)
    2. Znajdź początek
    3. Łącz segmenty end-to-start
    """
    if not entities:
        return []
    
    # Konwertuj encje na segmenty
    segments = []  # [(start, end, points), ...]
    
    for entity in entities:
        if entity.dxftype() == 'LINE':
            start = (entity.dxf.start.x, entity.dxf.start.y)
            end = (entity.dxf.end.x, entity.dxf.end.y)
            segments.append((start, end, [start, end]))
            
        elif entity.dxftype() == 'ARC':
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            sa, ea = entity.dxf.start_angle, entity.dxf.end_angle
            
            points = arc_to_points(cx, cy, r, sa, ea, arc_resolution)
            if points:
                segments.append((points[0], points[-1], points))
        
        elif entity.dxftype() == 'LWPOLYLINE':
            pts = [(p[0], p[1]) for p in entity.get_points()]
            if entity.closed and pts:
                pts.append(pts[0])
            if len(pts) >= 2:
                segments.append((pts[0], pts[-1], pts))
    
    if not segments:
        return []
    
    # Zbuduj kontur łącząc segmenty
    contour = list(segments[0][2])
    used = {0}
    
    tolerance = 1.0  # mm
    
    while len(used) < len(segments):
        current_end = contour[-1]
        found = False
        
        for i, (start, end, points) in enumerate(segments):
            if i in used:
                continue
            
            # Sprawdź czy start pasuje do current_end
            dist_start = math.sqrt((current_end[0] - start[0])**2 + (current_end[1] - start[1])**2)
            dist_end = math.sqrt((current_end[0] - end[0])**2 + (current_end[1] - end[1])**2)
            
            if dist_start < tolerance:
                # Dodaj punkty (bez pierwszego który jest duplikatem)
                contour.extend(points[1:])
                used.add(i)
                found = True
                break
            elif dist_end < tolerance:
                # Odwróć segment i dodaj
                reversed_pts = list(reversed(points))
                contour.extend(reversed_pts[1:])
                used.add(i)
                found = True
                break
        
        if not found:
            # Nie znaleziono pasującego segmentu
            logger.warning(f"Cannot connect segment, used {len(used)}/{len(segments)}")
            break
    
    return contour


def read_dxf_part(
    filepath: str,
    outer_layer: str = None,  # None = auto-detect
    inner_layer: str = None,  # None = auto-detect
    arc_resolution: int = 8
) -> Optional[DXFPart]:
    """
    Odczytaj detal z pliku DXF.
    
    Args:
        filepath: Ścieżka do pliku DXF
        outer_layer: Nazwa warstwy z konturem zewnętrznym (None = auto)
        inner_layer: Nazwa warstwy z otworami (None = auto)
        arc_resolution: Rozdzielczość aproksymacji łuków
    
    Returns:
        DXFPart lub None w przypadku błędu
    """
    if not HAS_EZDXF:
        logger.error("ezdxf not installed")
        return None
    
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        
        # Zbierz wszystkie encje i warstwy
        all_entities = list(msp)
        layer_entities = {}
        
        for entity in all_entities:
            layer = entity.dxf.layer
            if layer not in layer_entities:
                layer_entities[layer] = []
            layer_entities[layer].append(entity)
        
        # Auto-detect warstwy jeśli nie podano
        outer_candidates = ['IV_OUTER_PROFILE', 'OUTER', 'KONTUR', 'OUTLINE', '0', '2', 'Domyślne']
        inner_candidates = ['IV_INTERIOR_PROFILES', 'INNER', 'OTWORY', 'HOLES', 'Domyślne']
        
        # Znajdź warstwę z konturem zewnętrznym
        outer_entities = []
        if outer_layer and outer_layer in layer_entities:
            outer_entities = [e for e in layer_entities[outer_layer] 
                             if e.dxftype() in ('LINE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'SPLINE')]
        else:
            # Auto-detect: znajdź warstwę z liniami/łukami
            for candidate in outer_candidates:
                if candidate in layer_entities:
                    ents = [e for e in layer_entities[candidate] 
                           if e.dxftype() in ('LINE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'SPLINE')]
                    if ents:
                        outer_entities = ents
                        logger.debug(f"Auto-detected outer layer: {candidate}")
                        break
            
            # Jeśli nie znaleziono, użyj wszystkich linii/łuków
            if not outer_entities:
                outer_entities = [e for e in all_entities 
                                 if e.dxftype() in ('LINE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'SPLINE')]
        
        # Zbierz otwory (okręgi)
        inner_entities = []
        if inner_layer and inner_layer in layer_entities:
            inner_entities = [e for e in layer_entities[inner_layer] if e.dxftype() == 'CIRCLE']
        else:
            # Auto-detect: zbierz wszystkie okręgi które nie są konturem
            for candidate in inner_candidates:
                if candidate in layer_entities:
                    ents = [e for e in layer_entities[candidate] if e.dxftype() == 'CIRCLE']
                    inner_entities.extend(ents)
            
            # Dodaj okręgi z innych warstw
            for layer, ents in layer_entities.items():
                circles = [e for e in ents if e.dxftype() == 'CIRCLE']
                for c in circles:
                    if c not in inner_entities:
                        inner_entities.append(c)
        
        # Zbuduj kontur zewnętrzny
        outer_contour = build_contour_from_entities(outer_entities, arc_resolution)
        
        if not outer_contour or len(outer_contour) < 3:
            logger.warning(f"Could not build outer contour from {filepath}")
            # Spróbuj zbudować z wszystkich encji
            outer_contour = build_contour_from_entities(all_entities, arc_resolution)
        
        # Zbuduj otwory
        holes = []
        for entity in inner_entities:
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            hole_points = circle_to_points(cx, cy, r, resolution=16)
            holes.append(hole_points)
        
        # Oblicz bounding box
        if outer_contour:
            min_x = min(p[0] for p in outer_contour)
            max_x = max(p[0] for p in outer_contour)
            min_y = min(p[1] for p in outer_contour)
            max_y = max(p[1] for p in outer_contour)
        else:
            min_x = max_x = min_y = max_y = 0
        
        # Nazwa z pliku
        import os
        name = os.path.splitext(os.path.basename(filepath))[0]
        
        return DXFPart(
            name=name,
            outer_contour=outer_contour,
            holes=holes,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y
        )
        
    except Exception as e:
        logger.error(f"Error reading DXF {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None


def normalize_contour(contour: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Przesuń kontur tak aby min_x = min_y = 0.
    """
    if not contour:
        return contour
    
    min_x = min(p[0] for p in contour)
    min_y = min(p[1] for p in contour)
    
    return [(p[0] - min_x, p[1] - min_y) for p in contour]


def dxf_part_to_shapely(part: DXFPart) -> Optional['Polygon']:
    """
    Konwertuj DXFPart na Shapely Polygon.
    """
    if not HAS_SHAPELY:
        return None
    
    if len(part.outer_contour) < 3:
        return None
    
    try:
        # Kontur zewnętrzny
        outer = Polygon(part.outer_contour)
        if not outer.is_valid:
            outer = outer.buffer(0)
        
        # Odejmij otwory
        for hole in part.holes:
            if len(hole) >= 3:
                h = Polygon(hole)
                if h.is_valid:
                    outer = outer.difference(h)
        
        return outer
    except Exception as e:
        logger.error(f"Error converting to Shapely: {e}")
        return None


# ============================================================
# Wizualizacja z matplotlib
# ============================================================

def visualize_dxf_part(part: DXFPart, output_path: str = None, title: str = None):
    """
    Wizualizuj DXFPart używając matplotlib.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        from matplotlib.patches import Polygon as MplPolygon
    except ImportError:
        logger.error("matplotlib not installed")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    
    # Tło
    ax.set_facecolor('#1a1a1a')
    
    # Kontur zewnętrzny
    if part.outer_contour:
        poly = MplPolygon(
            part.outer_contour,
            closed=True,
            facecolor='#3b82f6',
            edgecolor='white',
            linewidth=1.5,
            alpha=0.8
        )
        ax.add_patch(poly)
    
    # Otwory
    for hole in part.holes:
        if hole:
            hole_poly = MplPolygon(
                hole,
                closed=True,
                facecolor='#1a1a1a',
                edgecolor='white',
                linewidth=1
            )
            ax.add_patch(hole_poly)
    
    # Ustaw limity
    margin = 5
    ax.set_xlim(part.min_x - margin, part.max_x + margin)
    ax.set_ylim(part.min_y - margin, part.max_y + margin)
    ax.set_aspect('equal')
    
    # Tytuł
    if title:
        ax.set_title(title, color='white', fontsize=14)
    else:
        ax.set_title(f"{part.name}\n{part.width:.2f} x {part.height:.2f} mm", color='white', fontsize=12)
    
    # Osie
    ax.tick_params(colors='white')
    for spine in ax.spines.values():
        spine.set_color('white')
    
    ax.set_xlabel('X [mm]', color='white')
    ax.set_ylabel('Y [mm]', color='white')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, facecolor='#1a1a1a', edgecolor='none')
        plt.close()
        print(f"Saved: {output_path}")
    else:
        plt.show()


def compare_dxf_with_reference(dxf_path: str, ref_image_path: str, output_path: str):
    """
    Porównaj odczyt DXF z obrazem referencyjnym.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        from matplotlib.patches import Polygon as MplPolygon
    except ImportError:
        logger.error("matplotlib not installed")
        return
    
    # Odczytaj DXF
    part = read_dxf_part(dxf_path)
    if not part:
        print(f"Failed to read DXF: {dxf_path}")
        return
    
    # Wczytaj obraz referencyjny
    ref_img = mpimg.imread(ref_image_path)
    
    # Utwórz figurę z dwoma wykresami
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.patch.set_facecolor('#1a1a1a')
    
    # Lewy: Obraz referencyjny
    ax1.imshow(ref_img)
    ax1.set_title('Referencja (JPG)', color='white', fontsize=14)
    ax1.axis('off')
    
    # Prawy: Nasz odczyt
    ax2.set_facecolor('#1a1a1a')
    
    if part.outer_contour:
        poly = MplPolygon(
            part.outer_contour,
            closed=True,
            facecolor='#3b82f6',
            edgecolor='white',
            linewidth=1.5,
            alpha=0.8
        )
        ax2.add_patch(poly)
    
    for hole in part.holes:
        if hole:
            hole_poly = MplPolygon(
                hole,
                closed=True,
                facecolor='#1a1a1a',
                edgecolor='white',
                linewidth=1
            )
            ax2.add_patch(hole_poly)
    
    margin = 5
    ax2.set_xlim(part.min_x - margin, part.max_x + margin)
    ax2.set_ylim(part.min_y - margin, part.max_y + margin)
    ax2.set_aspect('equal')
    ax2.set_title(f'Odczyt DXF\n{part.width:.2f} x {part.height:.2f} mm', color='white', fontsize=14)
    ax2.tick_params(colors='white')
    for spine in ax2.spines.values():
        spine.set_color('white')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor='#1a1a1a', edgecolor='none')
    plt.close()
    print(f"Comparison saved: {output_path}")


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    import sys
    import os
    
    # Test z plikami przykładowymi
    samples_dir = "/home/claude/dxf_samples"
    output_dir = "/home/claude/dxf_test_output"
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Znajdź pliki DXF
    dxf_files = [f for f in os.listdir(samples_dir) if f.endswith('.dxf')]
    
    print(f"Found {len(dxf_files)} DXF files\n")
    
    for dxf_file in sorted(dxf_files)[:4]:  # Pierwsze 4
        dxf_path = os.path.join(samples_dir, dxf_file)
        jpg_path = dxf_path + ".jpg"
        
        print(f"Processing: {dxf_file}")
        
        # Odczytaj DXF
        part = read_dxf_part(dxf_path)
        
        if part:
            print(f"  Contour points: {len(part.outer_contour)}")
            print(f"  Holes: {len(part.holes)}")
            print(f"  Dimensions: {part.width:.2f} x {part.height:.2f} mm")
            print(f"  Area: {part.area:.2f} mm²")
            
            # Wizualizuj
            output_path = os.path.join(output_dir, f"{dxf_file}_visualized.png")
            visualize_dxf_part(part, output_path)
            
            # Porównaj z referencją
            if os.path.exists(jpg_path):
                compare_path = os.path.join(output_dir, f"{dxf_file}_compare.png")
                compare_dxf_with_reference(dxf_path, jpg_path, compare_path)
        else:
            print("  FAILED to read")
        
        print()
