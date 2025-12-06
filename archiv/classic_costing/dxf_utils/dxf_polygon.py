"""
NewERP - DXF Polygon Extractor
==============================
Ekstrakcja wielokątów z plików DXF do użycia w zaawansowanym nestingu.
"""

import math
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

logger = logging.getLogger(__name__)

# Spróbuj zaimportować ezdxf
try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.warning("ezdxf not installed. DXF polygon extraction unavailable.")


@dataclass
class Point2D:
    """Punkt 2D"""
    x: float
    y: float
    
    def distance_to(self, other: 'Point2D') -> float:
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Point2D):
            return False
        return abs(self.x - other.x) < 0.01 and abs(self.y - other.y) < 0.01
    
    def __hash__(self):
        return hash((round(self.x, 2), round(self.y, 2)))


@dataclass
class DXFPolygon:
    """Wielokąt wyekstrahowany z DXF"""
    vertices: List[Point2D]
    holes: List[List[Point2D]] = field(default_factory=list)
    source_file: str = ""
    
    @property
    def is_valid(self) -> bool:
        return len(self.vertices) >= 3
    
    @property
    def is_closed(self) -> bool:
        if len(self.vertices) < 3:
            return False
        return self.vertices[0].distance_to(self.vertices[-1]) < 0.1
    
    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y)"""
        if not self.vertices:
            return (0, 0, 0, 0)
        xs = [p.x for p in self.vertices]
        ys = [p.y for p in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))
    
    @property
    def width(self) -> float:
        b = self.bounds
        return b[2] - b[0]
    
    @property
    def height(self) -> float:
        b = self.bounds
        return b[3] - b[1]
    
    @property
    def area(self) -> float:
        """Shoelace formula"""
        n = len(self.vertices)
        if n < 3:
            return 0
        area = 0
        for i in range(n):
            j = (i + 1) % n
            area += self.vertices[i].x * self.vertices[j].y
            area -= self.vertices[j].x * self.vertices[i].y
        return abs(area) / 2
    
    @property
    def perimeter(self) -> float:
        """Obwód wielokąta"""
        if len(self.vertices) < 2:
            return 0
        total = 0
        for i in range(len(self.vertices)):
            j = (i + 1) % len(self.vertices)
            total += self.vertices[i].distance_to(self.vertices[j])
        return total
    
    def normalize(self) -> 'DXFPolygon':
        """Przesuń do (0, 0)"""
        b = self.bounds
        new_verts = [Point2D(p.x - b[0], p.y - b[1]) for p in self.vertices]
        new_holes = [[Point2D(p.x - b[0], p.y - b[1]) for p in hole] for hole in self.holes]
        return DXFPolygon(new_verts, new_holes, self.source_file)


class DXFPolygonExtractor:
    """
    Ekstraktor wielokątów z plików DXF.
    
    Obsługuje:
    - LWPOLYLINE (najpopularniejsze)
    - POLYLINE (3D/2D)
    - LINE (łączy w wielokąt)
    - CIRCLE (aproksymacja jako n-kąt)
    """
    
    def __init__(self, circle_segments: int = 32):
        self.circle_segments = circle_segments
    
    def extract(self, filepath: str | Path) -> Optional[DXFPolygon]:
        """
        Wyekstrahuj główny wielokąt z pliku DXF.
        """
        if not HAS_EZDXF:
            logger.error("ezdxf not installed")
            return None
        
        filepath = Path(filepath)
        if not filepath.exists():
            logger.error(f"File not found: {filepath}")
            return None
        
        try:
            doc = ezdxf.readfile(str(filepath))
            msp = doc.modelspace()
            
            polygons = []
            
            # 1. LWPOLYLINE
            for entity in msp.query('LWPOLYLINE'):
                poly = self._extract_lwpolyline(entity)
                if poly and poly.is_valid:
                    polygons.append(poly)
            
            # 2. POLYLINE
            for entity in msp.query('POLYLINE'):
                poly = self._extract_polyline(entity)
                if poly and poly.is_valid:
                    polygons.append(poly)
            
            # 3. CIRCLE
            for entity in msp.query('CIRCLE'):
                poly = self._extract_circle(entity)
                if poly and poly.is_valid:
                    polygons.append(poly)
            
            # 4. LINE (jeśli brak innych)
            if not polygons:
                lines = list(msp.query('LINE'))
                if lines:
                    poly = self._connect_lines(lines)
                    if poly and poly.is_valid:
                        polygons.append(poly)
            
            # Wybierz największy wielokąt
            if polygons:
                result = max(polygons, key=lambda p: p.area)
                result.source_file = str(filepath)
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting polygon from {filepath}: {e}")
            return None
    
    def _extract_lwpolyline(self, entity) -> Optional[DXFPolygon]:
        """Wyekstrahuj z LWPOLYLINE"""
        try:
            points = []
            for x, y in entity.get_points(format='xy'):
                points.append(Point2D(x, y))
            
            if len(points) >= 3:
                return DXFPolygon(points)
            return None
            
        except Exception as e:
            logger.debug(f"Error in LWPOLYLINE: {e}")
            return None
    
    def _extract_polyline(self, entity) -> Optional[DXFPolygon]:
        """Wyekstrahuj z POLYLINE"""
        try:
            points = []
            for vertex in entity.vertices:
                loc = vertex.dxf.location
                points.append(Point2D(loc.x, loc.y))
            
            if len(points) >= 3:
                return DXFPolygon(points)
            return None
            
        except Exception as e:
            logger.debug(f"Error in POLYLINE: {e}")
            return None
    
    def _extract_circle(self, entity) -> Optional[DXFPolygon]:
        """Aproksymacja okręgu jako wielokąt"""
        try:
            cx = entity.dxf.center.x
            cy = entity.dxf.center.y
            r = entity.dxf.radius
            
            points = []
            for i in range(self.circle_segments):
                angle = 2 * math.pi * i / self.circle_segments
                points.append(Point2D(
                    cx + r * math.cos(angle),
                    cy + r * math.sin(angle)
                ))
            
            return DXFPolygon(points)
            
        except Exception as e:
            logger.debug(f"Error in CIRCLE: {e}")
            return None
    
    def _connect_lines(self, lines: list) -> Optional[DXFPolygon]:
        """Połącz oddzielne linie w wielokąt"""
        if not lines:
            return None
        
        try:
            # Zbierz segmenty
            segments = []
            for line in lines:
                start = Point2D(line.dxf.start.x, line.dxf.start.y)
                end = Point2D(line.dxf.end.x, line.dxf.end.y)
                segments.append((start, end))
            
            if not segments:
                return None
            
            # Buduj ścieżkę
            result = [segments[0][0], segments[0][1]]
            used = {0}
            
            while len(used) < len(segments):
                found = False
                current_end = result[-1]
                
                for i, (start, end) in enumerate(segments):
                    if i in used:
                        continue
                    
                    if current_end.distance_to(start) < 0.1:
                        result.append(end)
                        used.add(i)
                        found = True
                        break
                    elif current_end.distance_to(end) < 0.1:
                        result.append(start)
                        used.add(i)
                        found = True
                        break
                
                if not found:
                    break
            
            if len(result) >= 3:
                return DXFPolygon(result)
            return None
            
        except Exception as e:
            logger.debug(f"Error connecting lines: {e}")
            return None


# Cache dla wielokątów
_polygon_cache: Dict[str, Optional[DXFPolygon]] = {}


def get_dxf_polygon(filepath: str | Path, use_cache: bool = True) -> Optional[DXFPolygon]:
    """
    Pobierz wielokąt z pliku DXF (z cache).
    """
    filepath = str(filepath)
    
    if use_cache and filepath in _polygon_cache:
        return _polygon_cache[filepath]
    
    extractor = DXFPolygonExtractor()
    polygon = extractor.extract(filepath)
    
    if use_cache:
        _polygon_cache[filepath] = polygon
    
    return polygon


def clear_polygon_cache():
    """Wyczyść cache wielokątów"""
    _polygon_cache.clear()


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("DXF POLYGON EXTRACTOR TEST")
    print("="*60)
    print(f"ezdxf available: {HAS_EZDXF}")
    print()
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"Processing: {filepath}")
        
        polygon = get_dxf_polygon(filepath)
        
        if polygon:
            print(f"  Vertices: {len(polygon.vertices)}")
            print(f"  Size: {polygon.width:.1f} x {polygon.height:.1f} mm")
            print(f"  Area: {polygon.area:.1f} mm²")
            print(f"  Perimeter: {polygon.perimeter:.1f} mm")
        else:
            print("  Failed to extract polygon")
    else:
        print("Usage: python dxf_polygon.py <file.dxf>")
        print()
        
        # Test z prostym wielokątem
        test_poly = DXFPolygon([
            Point2D(0, 0),
            Point2D(100, 0),
            Point2D(100, 50),
            Point2D(50, 50),
            Point2D(50, 100),
            Point2D(0, 100),
        ])
        
        print(f"Test L-shape: {test_poly.width:.0f}x{test_poly.height:.0f}mm")
        print(f"  Area: {test_poly.area:.0f} mm²")
        print(f"  Perimeter: {test_poly.perimeter:.0f} mm")
