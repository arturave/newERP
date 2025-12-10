"""
DXF Loader - Uniwersalny odczyt plików DXF
==========================================
Oparty na sprawdzonym algorytmie z poprzednich prac.
Obsługuje: LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE
Auto-detekcja warstw: IV_OUTER_PROFILE, 0, 2, Domyślne
"""

import math
import logging
import os
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.warning("ezdxf not installed")

# Warstwy do ignorowania
IGNORE_LAYERS = {
    "RAMKA", "WYMIARY", "DIM", "TEXT", "TEKST", "OPIS", "DEFPOINTS",
    "ASSEMBLY", "HIDDEN", "CENTER", "CUTLINE", "GRID", "TITLE", 
    "BLOCK", "LOGO", "INFO", "FRAME", "BORDER", "AM_"
}

# Warstwy preferowane dla konturu zewnętrznego
OUTER_LAYERS = ['IV_OUTER_PROFILE', 'OUTER', 'KONTUR', 'OUTLINE', '0', '2', 'Domyślne']

# Warstwy dla otworów
INNER_LAYERS = ['IV_INTERIOR_PROFILES', 'INNER', 'OTWORY', 'HOLES']


@dataclass
class DXFPart:
    """Detal odczytany z DXF"""
    name: str
    filepath: str = ""
    outer_contour: List[Tuple[float, float]] = field(default_factory=list)  # Punkty konturu zewnętrznego (mm)
    holes: List[List[Tuple[float, float]]] = field(default_factory=list)
    
    # Bounding box
    min_x: float = 0
    max_x: float = 0
    min_y: float = 0
    max_y: float = 0
    
    # Dane z nazwy pliku (uzupełniane przez name_parser)
    material: str = ""
    thickness: Optional[float] = None
    quantity: int = 1
    
    @property
    def width(self) -> float:
        return self.max_x - self.min_x
    
    @property
    def height(self) -> float:
        return self.max_y - self.min_y
    
    @property
    def bounding_area(self) -> float:
        """Pole bounding box w mm²"""
        return self.width * self.height
    
    @property
    def contour_area(self) -> float:
        """
        Rzeczywiste pole powierzchni konturu (bez otworów) - używając formuły Shoelace.
        To jest dokładniejsze niż bounding box.
        """
        if len(self.outer_contour) < 3:
            return self.bounding_area
        
        # Formuła Shoelace dla wielokąta
        n = len(self.outer_contour)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.outer_contour[i][0] * self.outer_contour[j][1]
            area -= self.outer_contour[j][0] * self.outer_contour[i][1]
        outer_area = abs(area) / 2.0
        
        # Odejmij otwory
        holes_area = 0.0
        for hole in self.holes:
            if len(hole) >= 3:
                n_h = len(hole)
                hole_area = 0.0
                for i in range(n_h):
                    j = (i + 1) % n_h
                    hole_area += hole[i][0] * hole[j][1]
                    hole_area -= hole[j][0] * hole[i][1]
                holes_area += abs(hole_area) / 2.0
        
        return outer_area - holes_area
    
    @property
    def weight_kg(self) -> float:
        """
        Przybliżona waga w kg (dla stali ~7.85 g/cm³).
        Wymaga ustawienia thickness.
        """
        if not self.thickness:
            return 0.0
        
        # Pole w cm² × grubość w cm × gęstość g/cm³ = masa w g
        area_cm2 = self.contour_area / 100  # mm² -> cm²
        thickness_cm = self.thickness / 10  # mm -> cm
        density = 7.85  # g/cm³ dla stali
        
        mass_g = area_cm2 * thickness_cm * density
        return mass_g / 1000  # g -> kg
    
    def get_normalized_contour(self) -> List[Tuple[float, float]]:
        """Zwróć kontur znormalizowany do (0,0)"""
        if not self.outer_contour:
            return []
        return [(x - self.min_x, y - self.min_y) for x, y in self.outer_contour]
    
    def get_scaled_contour(self, scale: float = 10.0) -> List[Tuple[int, int]]:
        """Zwróć kontur przeskalowany do int (dla rectpack)"""
        normalized = self.get_normalized_contour()
        return [(int(x * scale), int(y * scale)) for x, y in normalized]


def _is_ignored_layer(layer: str) -> bool:
    """Sprawdź czy warstwa powinna być ignorowana"""
    if not layer:
        return False
    layer_upper = layer.upper()
    return any(ign in layer_upper for ign in IGNORE_LAYERS)


def arc_to_points(
    center_x: float, center_y: float,
    radius: float,
    start_angle: float, end_angle: float,
    segments_per_90deg: int = 8
) -> List[Tuple[float, float]]:
    """Konwertuj łuk na listę punktów"""
    points = []
    
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)
    
    # Obsłuż przypadek gdy end < start
    if end_angle < start_angle:
        end_rad += 2 * math.pi
    
    arc_length = abs(end_rad - start_rad)
    num_points = max(3, int(arc_length / (math.pi / 2) * segments_per_90deg) + 1)
    
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
    resolution: int = 24
) -> List[Tuple[float, float]]:
    """Konwertuj okrąg na listę punktów"""
    points = []
    for i in range(resolution):
        angle = 2 * math.pi * i / resolution
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))
    points.append(points[0])  # Zamknij
    return points


def build_contour_from_entities(
    entities: List,
    arc_resolution: int = 8
) -> List[Tuple[float, float]]:
    """
    Zbuduj zamknięty kontur z encji DXF.
    Łączy segmenty end-to-start.
    """
    if not entities:
        return []
    
    # Konwertuj encje na segmenty
    segments = []  # [(start, end, points), ...]
    
    for entity in entities:
        try:
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
            
            elif entity.dxftype() == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                points = circle_to_points(cx, cy, r, resolution=24)
                if points:
                    segments.append((points[0], points[-1], points))
            
            elif entity.dxftype() == 'LWPOLYLINE':
                pts = []
                # Obsługa bulge (łuki w polyline)
                has_bulge = False
                try:
                    for i, pt in enumerate(entity.get_points('xyb')):
                        x, y, bulge = pt[0], pt[1], pt[2] if len(pt) > 2 else 0
                        pts.append((x, y))
                        
                        if bulge != 0:
                            has_bulge = True
                            # Konwertuj bulge na łuk
                            try:
                                next_idx = (i + 1) % len(list(entity.get_points()))
                                next_pt = list(entity.get_points('xy'))[next_idx]
                                center, radius, start_a, end_a = ezdxf.math.bulge_to_arc(
                                    (x, y), (next_pt[0], next_pt[1]), bulge
                                )
                                arc_pts = arc_to_points(center[0], center[1], radius, 
                                                       math.degrees(start_a), math.degrees(end_a), 
                                                       arc_resolution)
                                pts.extend(arc_pts[1:])
                            except:
                                pass
                except:
                    pts = [(p[0], p[1]) for p in entity.get_points('xy')]
                
                if entity.closed and pts:
                    pts.append(pts[0])
                    
                if len(pts) >= 2:
                    segments.append((pts[0], pts[-1], pts))
                    
            elif entity.dxftype() == 'POLYLINE':
                pts = []
                try:
                    for v in entity.vertices:
                        pts.append((v.dxf.location.x, v.dxf.location.y))
                except:
                    pass
                if entity.is_closed and pts:
                    pts.append(pts[0])
                if len(pts) >= 2:
                    segments.append((pts[0], pts[-1], pts))
                    
        except Exception as e:
            logger.debug(f"Error processing entity: {e}")
            continue
    
    if not segments:
        return []
    
    # Zbuduj kontur łącząc segmenty
    contour = list(segments[0][2])
    used = {0}
    
    tolerance = 1.0  # mm
    max_iterations = len(segments) * 2
    iteration = 0
    
    while len(used) < len(segments) and iteration < max_iterations:
        iteration += 1
        current_end = contour[-1]
        found = False
        
        for i, (start, end, points) in enumerate(segments):
            if i in used:
                continue
            
            dist_start = math.sqrt((current_end[0] - start[0])**2 + (current_end[1] - start[1])**2)
            dist_end = math.sqrt((current_end[0] - end[0])**2 + (current_end[1] - end[1])**2)
            
            if dist_start < tolerance:
                contour.extend(points[1:])
                used.add(i)
                found = True
                break
            elif dist_end < tolerance:
                reversed_pts = list(reversed(points))
                contour.extend(reversed_pts[1:])
                used.add(i)
                found = True
                break
        
        if not found:
            break
    
    return contour


def load_dxf(filepath: str, arc_resolution: int = 8) -> Optional[DXFPart]:
    """
    Wczytaj detal z pliku DXF.
    
    Args:
        filepath: Ścieżka do pliku DXF
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
        
        # Zbierz encje po warstwach
        all_entities = list(msp)
        layer_entities: Dict[str, List] = {}
        
        for entity in all_entities:
            layer = entity.dxf.layer
            if _is_ignored_layer(layer):
                continue
            if layer not in layer_entities:
                layer_entities[layer] = []
            layer_entities[layer].append(entity)
        
        # Znajdź encje konturu zewnętrznego
        outer_entities = []
        
        # Najpierw szukaj w preferowanych warstwach
        for candidate in OUTER_LAYERS:
            # Szukanie case-insensitive
            found_layer = next((l for l in layer_entities if l.upper() == candidate.upper()), None)
            if found_layer:
                ents = [e for e in layer_entities[found_layer] 
                        if e.dxftype() in ('LINE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'CIRCLE')]
                if ents:
                    outer_entities = ents
                    logger.debug(f"Using outer layer: {found_layer}")
                    break
        
        # Jeśli nie znaleziono, użyj wszystkich (bez ignorowanych)
        if not outer_entities:
            for layer, ents in layer_entities.items():
                outer_entities.extend([e for e in ents 
                                       if e.dxftype() in ('LINE', 'ARC', 'LWPOLYLINE', 'POLYLINE')])
        
        # Zbuduj kontur zewnętrzny
        outer_contour = build_contour_from_entities(outer_entities, arc_resolution)

        # Znajdź wszystkie okręgi (potencjalne kontury zewnętrzne lub otwory)
        circles = [e for e in all_entities if e.dxftype() == 'CIRCLE'
                   and not _is_ignored_layer(e.dxf.layer)]

        # Sprawdź czy istnieje okrąg większy niż zbudowany kontur
        # To może być prawdziwy kontur zewnętrzny (np. okrągła podkładka z otworami)
        if circles:
            largest_circle = max(circles, key=lambda c: c.dxf.radius)
            largest_radius = largest_circle.dxf.radius
            largest_diameter = largest_radius * 2

            # Oblicz rozmiar zbudowanego konturu
            if outer_contour and len(outer_contour) >= 3:
                contour_min_x = min(p[0] for p in outer_contour)
                contour_max_x = max(p[0] for p in outer_contour)
                contour_min_y = min(p[1] for p in outer_contour)
                contour_max_y = max(p[1] for p in outer_contour)
                contour_width = contour_max_x - contour_min_x
                contour_height = contour_max_y - contour_min_y
                contour_max_dim = max(contour_width, contour_height)
            else:
                contour_max_dim = 0

            # Jeśli największy okrąg jest znacznie większy niż zbudowany kontur,
            # użyj go jako konturu zewnętrznego
            if largest_diameter > contour_max_dim * 1.5:
                logger.info(f"Using largest CIRCLE (r={largest_radius:.2f}mm) as outer contour "
                           f"instead of built contour ({contour_max_dim:.2f}mm)")
                cx, cy = largest_circle.dxf.center.x, largest_circle.dxf.center.y
                outer_contour = circle_to_points(cx, cy, largest_radius, resolution=64)

        # Jeśli nie udało się zbudować konturu, spróbuj z okręgami (np. detal to tylko podkładka)
        if not outer_contour or len(outer_contour) < 3:
            if circles:
                # Znajdź największy okrąg
                largest = max(circles, key=lambda c: c.dxf.radius)
                cx, cy = largest.dxf.center.x, largest.dxf.center.y
                r = largest.dxf.radius
                outer_contour = circle_to_points(cx, cy, r, resolution=64)

        if not outer_contour or len(outer_contour) < 3:
            logger.warning(f"Could not build contour from {filepath}")
            return None
        
        # Zbierz otwory (okręgi wewnętrzne)
        holes = []
        for layer_name in layer_entities:
            # Sprawdź czy to warstwa otworów
            is_hole_layer = any(ih in layer_name.upper() for ih in INNER_LAYERS)
            
            # Jeśli nie znaleziono dedykowanej warstwy, sprawdź czy to nie okręgi wewnątrz konturu
            # (Tutaj uproszczona logika: bierzemy z dedykowanych warstw)
            if is_hole_layer:
                for entity in layer_entities[layer_name]:
                    if entity.dxftype() == 'CIRCLE':
                        cx, cy = entity.dxf.center.x, entity.dxf.center.y
                        r = entity.dxf.radius
                        hole_points = circle_to_points(cx, cy, r, resolution=16)
                        holes.append(hole_points)
        
        # Oblicz bounding box
        min_x = min(p[0] for p in outer_contour)
        max_x = max(p[0] for p in outer_contour)
        min_y = min(p[1] for p in outer_contour)
        max_y = max(p[1] for p in outer_contour)
        
        # Nazwa z pliku
        name = os.path.splitext(os.path.basename(filepath))[0]
        
        return DXFPart(
            name=name,
            filepath=filepath,
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


def load_dxf_as_path(filepath: str, scale: float = 10.0) -> Optional[List[Tuple[int, int]]]:
    """
    Wczytaj DXF i zwróć przeskalowany kontur (kompatybilność z rectpack).
    
    Args:
        filepath: Ścieżka do pliku DXF
        scale: Skala (10 = 0.1mm precyzja)
    
    Returns:
        Lista punktów (int, int) lub None
    """
    part = load_dxf(filepath)
    if not part:
        return None
    
    return part.get_scaled_contour(scale)


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        
        print(f"Loading: {filepath}")
        
        part = load_dxf(filepath)
        if part:
            print(f"  Name: {part.name}")
            print(f"  Dimensions: {part.width:.2f} x {part.height:.2f} mm")
            print(f"  Bounding area: {part.bounding_area:.2f} mm²")
            print(f"  Contour area: {part.contour_area:.2f} mm²")
            print(f"  Contour points: {len(part.outer_contour)}")
            print(f"  Holes: {len(part.holes)}")
        else:
            print("  FAILED to load")
    else:
        print("Usage: python dxf_loader.py <path_to_dxf>")