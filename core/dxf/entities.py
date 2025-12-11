"""
DXF Entities - Dataclasses dla reprezentacji geometrii DXF
==========================================================
Centralne struktury danych używane przez UnifiedDXFReader i CAD Viewer.
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum


class EntityType(Enum):
    """Typy entities DXF"""
    LINE = "LINE"
    ARC = "ARC"
    CIRCLE = "CIRCLE"
    LWPOLYLINE = "LWPOLYLINE"
    POLYLINE = "POLYLINE"
    SPLINE = "SPLINE"
    ELLIPSE = "ELLIPSE"
    POINT = "POINT"
    INSERT = "INSERT"  # Block reference
    TEXT = "TEXT"
    MTEXT = "MTEXT"
    DIMENSION = "DIMENSION"


@dataclass
class DXFEntity:
    """
    Pojedyncza entity DXF (LINE, ARC, CIRCLE, etc.)
    Przechowuje oryginalne dane + skonwertowane punkty.
    """
    entity_type: EntityType
    layer: str
    color: int = 256  # 256 = ByLayer

    # Punkty geometrii (skonwertowane na listę punktów)
    points: List[Tuple[float, float]] = field(default_factory=list)

    # Oryginalne dane entity (dla edycji/zapisu)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # Czy to zamknięta figura
    is_closed: bool = False

    # Długość entity (dla obliczeń cięcia)
    length_mm: float = 0.0

    @property
    def start_point(self) -> Optional[Tuple[float, float]]:
        """Punkt początkowy"""
        return self.points[0] if self.points else None

    @property
    def end_point(self) -> Optional[Tuple[float, float]]:
        """Punkt końcowy"""
        return self.points[-1] if self.points else None

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Bounding box (min_x, min_y, max_x, max_y)"""
        if not self.points:
            return (0, 0, 0, 0)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class DXFContour:
    """
    Zamknięty kontur złożony z wielu entities.
    Może być konturem zewnętrznym lub otworem.
    """
    points: List[Tuple[float, float]] = field(default_factory=list)
    entities: List[DXFEntity] = field(default_factory=list)  # Składowe entities

    is_closed: bool = True
    is_outer: bool = True  # True = kontur zewnętrzny, False = otwór
    layer: str = ""

    @property
    def area(self) -> float:
        """Pole powierzchni (Shoelace formula)"""
        if len(self.points) < 3:
            return 0.0

        n = len(self.points)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.points[i][0] * self.points[j][1]
            area -= self.points[j][0] * self.points[i][1]
        return abs(area) / 2.0

    @property
    def perimeter(self) -> float:
        """Obwód konturu"""
        if len(self.points) < 2:
            return 0.0

        total = 0.0
        for i in range(len(self.points) - 1):
            dx = self.points[i+1][0] - self.points[i][0]
            dy = self.points[i+1][1] - self.points[i][1]
            total += math.sqrt(dx*dx + dy*dy)

        # Zamknij jeśli potrzeba
        if self.is_closed and len(self.points) >= 2:
            dx = self.points[0][0] - self.points[-1][0]
            dy = self.points[0][1] - self.points[-1][1]
            total += math.sqrt(dx*dx + dy*dy)

        return total

    @property
    def centroid(self) -> Tuple[float, float]:
        """Centroid konturu"""
        if not self.points:
            return (0.0, 0.0)
        cx = sum(p[0] for p in self.points) / len(self.points)
        cy = sum(p[1] for p in self.points) / len(self.points)
        return (cx, cy)

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Bounding box (min_x, min_y, max_x, max_y)"""
        if not self.points:
            return (0, 0, 0, 0)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def get_normalized_points(self) -> List[Tuple[float, float]]:
        """Zwróć punkty przesunięte do (0, 0)"""
        if not self.points:
            return []
        min_x, min_y, _, _ = self.bounds
        return [(x - min_x, y - min_y) for x, y in self.points]


@dataclass
class DXFDimension:
    """Wymiar (liniowy, kątowy, promień, etc.)"""
    dim_type: str = "linear"  # linear, angular, radius, diameter
    start_point: Tuple[float, float] = (0, 0)
    end_point: Tuple[float, float] = (0, 0)
    text_position: Tuple[float, float] = (0, 0)
    text: str = ""
    value: float = 0.0
    layer: str = "DIMENSIONS"


@dataclass
class LayerInfo:
    """Informacje o warstwie DXF"""
    name: str
    color: int = 7  # Domyślnie biały
    visible: bool = True
    locked: bool = False
    frozen: bool = False
    entity_count: int = 0

    # Customowe kolory dla GUI
    display_color: str = "#FFFFFF"


@dataclass
class DXFPart:
    """
    Kompletny detal z pliku DXF.
    Zawiera kontur zewnętrzny, otwory, wymiary i metadane.
    """
    name: str
    filepath: str = ""

    # Geometria
    outer_contour: Optional[DXFContour] = None
    holes: List[DXFContour] = field(default_factory=list)

    # Wszystkie entities (dla edycji)
    entities: List[DXFEntity] = field(default_factory=list)

    # Wymiary (dodawane przez użytkownika lub automatycznie)
    dimensions: List[DXFDimension] = field(default_factory=list)

    # Warstwy
    layers: Dict[str, LayerInfo] = field(default_factory=dict)

    # Bounding box
    min_x: float = 0.0
    max_x: float = 0.0
    min_y: float = 0.0
    max_y: float = 0.0

    # Metadane z nazwy pliku
    material: str = ""
    thickness: Optional[float] = None
    quantity: int = 1

    # Obliczone wartości (dla kosztorysowania)
    cut_length_mm: float = 0.0
    pierce_count: int = 0

    @property
    def width(self) -> float:
        """Szerokość detalu"""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Wysokość detalu"""
        return self.max_y - self.min_y

    @property
    def bounding_area(self) -> float:
        """Pole bounding box w mm²"""
        return self.width * self.height

    @property
    def contour_area(self) -> float:
        """Rzeczywiste pole powierzchni (kontur - otwory)"""
        if not self.outer_contour:
            return self.bounding_area

        area = self.outer_contour.area
        for hole in self.holes:
            area -= hole.area
        return max(0, area)

    @property
    def weight_kg(self) -> float:
        """Przybliżona waga w kg (stal ~7.85 g/cm³)"""
        if not self.thickness:
            return 0.0

        area_cm2 = self.contour_area / 100  # mm² -> cm²
        thickness_cm = self.thickness / 10  # mm -> cm
        density = 7.85  # g/cm³

        return (area_cm2 * thickness_cm * density) / 1000  # g -> kg

    def get_normalized_contour(self) -> List[Tuple[float, float]]:
        """Kontur zewnętrzny znormalizowany do (0, 0)"""
        if not self.outer_contour:
            return []
        return [(x - self.min_x, y - self.min_y)
                for x, y in self.outer_contour.points]

    def get_normalized_holes(self) -> List[List[Tuple[float, float]]]:
        """Otwory znormalizowane do (0, 0)"""
        result = []
        for hole in self.holes:
            normalized = [(x - self.min_x, y - self.min_y)
                         for x, y in hole.points]
            result.append(normalized)
        return result

    def update_bounds(self):
        """Przelicz bounding box na podstawie konturu"""
        if self.outer_contour and self.outer_contour.points:
            xs = [p[0] for p in self.outer_contour.points]
            ys = [p[1] for p in self.outer_contour.points]
            self.min_x = min(xs)
            self.max_x = max(xs)
            self.min_y = min(ys)
            self.max_y = max(ys)
