"""
Snap Tool - Auto-przyciąganie do punktów CAD
=============================================
Endpoint, midpoint, center snap dla wymiarowania i edycji.
"""

import math
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Flag, auto

try:
    from core.dxf.entities import DXFPart, DXFContour, DXFEntity
except ImportError:
    DXFPart = None
    DXFContour = None
    DXFEntity = None


class SnapMode(Flag):
    """Tryby snap - można łączyć flagami"""
    NONE = 0
    ENDPOINT = auto()      # Końce linii/łuków
    MIDPOINT = auto()      # Środki linii/łuków
    CENTER = auto()        # Centra okręgów/łuków
    INTERSECTION = auto()  # Przecięcia (zaawansowane)
    PERPENDICULAR = auto() # Prostopadły (zaawansowane)

    # Predefiniowane kombinacje
    ALL = ENDPOINT | MIDPOINT | CENTER | INTERSECTION | PERPENDICULAR
    BASIC = ENDPOINT | MIDPOINT | CENTER


@dataclass
class SnapPoint:
    """Punkt snap z metadanymi"""
    x: float
    y: float
    mode: SnapMode
    source_entity: Optional[any] = None  # Entity źródłowa

    @property
    def position(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def distance_to(self, x: float, y: float) -> float:
        """Odległość do punktu"""
        return math.sqrt((self.x - x)**2 + (self.y - y)**2)


class SnapManager:
    """
    Manager snap points dla CAD Viewer.

    Automatycznie wykrywa i przechowuje punkty snap z entities.
    Podczas ruchu myszy znajduje najbliższy punkt snap w zasięgu.
    """

    # Wizualizacja
    SNAP_COLOR = "#00ff00"      # Zielony
    SNAP_INDICATOR_SIZE = 8     # Rozmiar znacznika w pikselach

    def __init__(self, snap_radius: float = 10.0):
        """
        Args:
            snap_radius: Promień wykrywania snap w pikselach screen
        """
        self.snap_radius = snap_radius
        self.enabled_modes: SnapMode = SnapMode.BASIC

        # Cache punktów snap (world coords)
        self._snap_points: List[SnapPoint] = []

        # Aktualny aktywny snap point
        self._active_snap: Optional[SnapPoint] = None

        # Canvas do rysowania wskaźników
        self._canvas = None
        self._indicator_id = None

    def set_canvas(self, canvas):
        """Ustaw canvas do rysowania wskaźników snap"""
        self._canvas = canvas

    def set_modes(self, modes: SnapMode):
        """Ustaw aktywne tryby snap"""
        self.enabled_modes = modes

    def enable_mode(self, mode: SnapMode):
        """Włącz tryb snap"""
        self.enabled_modes |= mode

    def disable_mode(self, mode: SnapMode):
        """Wyłącz tryb snap"""
        self.enabled_modes &= ~mode

    def toggle_mode(self, mode: SnapMode):
        """Toggle trybu snap"""
        self.enabled_modes ^= mode

    def build_snap_points(self, part: 'DXFPart'):
        """
        Zbuduj cache punktów snap z DXFPart.

        Wywoływane gdy wczytujemy nowy plik DXF.
        """
        self._snap_points.clear()

        if not part:
            return

        # Punkty z outer contour
        if part.outer_contour:
            self._extract_contour_snaps(part.outer_contour)

        # Punkty z otworów
        for hole in part.holes:
            self._extract_contour_snaps(hole)

        # Punkty z surowych entities (dla LINE, ARC, CIRCLE)
        for entity in part.entities:
            self._extract_entity_snaps(entity)

    def _extract_contour_snaps(self, contour: 'DXFContour'):
        """Wyciągnij punkty snap z konturu"""
        points = contour.points
        if not points:
            return

        for i, p in enumerate(points):
            # Endpoint - każdy wierzchołek konturu
            if self.enabled_modes & SnapMode.ENDPOINT:
                self._snap_points.append(SnapPoint(
                    x=p[0], y=p[1],
                    mode=SnapMode.ENDPOINT,
                    source_entity=contour
                ))

            # Midpoint - środek każdego segmentu
            if self.enabled_modes & SnapMode.MIDPOINT:
                next_i = (i + 1) % len(points)
                if next_i != 0 or contour.is_closed:
                    next_p = points[next_i]
                    mid_x = (p[0] + next_p[0]) / 2
                    mid_y = (p[1] + next_p[1]) / 2
                    self._snap_points.append(SnapPoint(
                        x=mid_x, y=mid_y,
                        mode=SnapMode.MIDPOINT,
                        source_entity=contour
                    ))

        # Center - centroid konturu (dla okręgów/otworów)
        if self.enabled_modes & SnapMode.CENTER:
            cx, cy = contour.centroid
            self._snap_points.append(SnapPoint(
                x=cx, y=cy,
                mode=SnapMode.CENTER,
                source_entity=contour
            ))

    def _extract_entity_snaps(self, entity: 'DXFEntity'):
        """Wyciągnij punkty snap z pojedynczej entity DXF"""
        if entity is None:
            return

        etype = entity.entity_type.value if hasattr(entity, 'entity_type') else ''

        if etype == 'LINE':
            # Endpoints linii
            if hasattr(entity, 'start') and hasattr(entity, 'end'):
                if self.enabled_modes & SnapMode.ENDPOINT:
                    self._snap_points.append(SnapPoint(
                        x=entity.start[0], y=entity.start[1],
                        mode=SnapMode.ENDPOINT,
                        source_entity=entity
                    ))
                    self._snap_points.append(SnapPoint(
                        x=entity.end[0], y=entity.end[1],
                        mode=SnapMode.ENDPOINT,
                        source_entity=entity
                    ))

                # Midpoint linii
                if self.enabled_modes & SnapMode.MIDPOINT:
                    mid_x = (entity.start[0] + entity.end[0]) / 2
                    mid_y = (entity.start[1] + entity.end[1]) / 2
                    self._snap_points.append(SnapPoint(
                        x=mid_x, y=mid_y,
                        mode=SnapMode.MIDPOINT,
                        source_entity=entity
                    ))

        elif etype == 'CIRCLE':
            # Centrum okręgu
            if hasattr(entity, 'center'):
                if self.enabled_modes & SnapMode.CENTER:
                    self._snap_points.append(SnapPoint(
                        x=entity.center[0], y=entity.center[1],
                        mode=SnapMode.CENTER,
                        source_entity=entity
                    ))

                # Endpoints okręgu (na 4 kierunkach: N, E, S, W)
                if self.enabled_modes & SnapMode.ENDPOINT:
                    r = entity.radius if hasattr(entity, 'radius') else 0
                    cx, cy = entity.center[0], entity.center[1]
                    for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                        self._snap_points.append(SnapPoint(
                            x=cx + dx * r, y=cy + dy * r,
                            mode=SnapMode.ENDPOINT,
                            source_entity=entity
                        ))

        elif etype == 'ARC':
            # Centrum łuku
            if hasattr(entity, 'center'):
                if self.enabled_modes & SnapMode.CENTER:
                    self._snap_points.append(SnapPoint(
                        x=entity.center[0], y=entity.center[1],
                        mode=SnapMode.CENTER,
                        source_entity=entity
                    ))

                # Endpoints łuku (start i end)
                if self.enabled_modes & SnapMode.ENDPOINT:
                    if hasattr(entity, 'start_angle') and hasattr(entity, 'end_angle'):
                        r = entity.radius if hasattr(entity, 'radius') else 0
                        cx, cy = entity.center[0], entity.center[1]

                        # Start point
                        start_rad = math.radians(entity.start_angle)
                        sx = cx + r * math.cos(start_rad)
                        sy = cy + r * math.sin(start_rad)
                        self._snap_points.append(SnapPoint(
                            x=sx, y=sy,
                            mode=SnapMode.ENDPOINT,
                            source_entity=entity
                        ))

                        # End point
                        end_rad = math.radians(entity.end_angle)
                        ex = cx + r * math.cos(end_rad)
                        ey = cy + r * math.sin(end_rad)
                        self._snap_points.append(SnapPoint(
                            x=ex, y=ey,
                            mode=SnapMode.ENDPOINT,
                            source_entity=entity
                        ))

                        # Midpoint łuku
                        if self.enabled_modes & SnapMode.MIDPOINT:
                            mid_angle = (entity.start_angle + entity.end_angle) / 2
                            # Korekta dla łuków przechodzących przez 0°
                            if entity.end_angle < entity.start_angle:
                                mid_angle = (entity.start_angle + entity.end_angle + 360) / 2
                                if mid_angle >= 360:
                                    mid_angle -= 360
                            mid_rad = math.radians(mid_angle)
                            mx = cx + r * math.cos(mid_rad)
                            my = cy + r * math.sin(mid_rad)
                            self._snap_points.append(SnapPoint(
                                x=mx, y=my,
                                mode=SnapMode.MIDPOINT,
                                source_entity=entity
                            ))

    def find_snap(self, world_x: float, world_y: float,
                  screen_transform: callable = None) -> Optional[SnapPoint]:
        """
        Znajdź najbliższy snap point w zasięgu.

        Args:
            world_x, world_y: Pozycja kursora w world coords
            screen_transform: Funkcja world_to_screen(x, y) -> (sx, sy)

        Returns:
            SnapPoint jeśli znaleziono w zasięgu, None otherwise
        """
        if not self._snap_points:
            return None

        best_snap = None
        best_dist = float('inf')

        for snap in self._snap_points:
            # Sprawdź czy tryb snap jest włączony
            if not (snap.mode & self.enabled_modes):
                continue

            # Oblicz odległość w screen coords (piksele)
            if screen_transform:
                sx1, sy1 = screen_transform(world_x, world_y)
                sx2, sy2 = screen_transform(snap.x, snap.y)
                dist = math.sqrt((sx1 - sx2)**2 + (sy1 - sy2)**2)
            else:
                # Fallback: world coords distance
                dist = snap.distance_to(world_x, world_y)

            if dist < self.snap_radius and dist < best_dist:
                best_dist = dist
                best_snap = snap

        self._active_snap = best_snap
        return best_snap

    def draw_indicator(self, screen_x: float, screen_y: float):
        """Rysuj wskaźnik snap na canvas"""
        if not self._canvas or not self._active_snap:
            self.clear_indicator()
            return

        self.clear_indicator()

        s = self.SNAP_INDICATOR_SIZE
        mode = self._active_snap.mode

        if mode & SnapMode.ENDPOINT:
            # Kwadrat dla endpoint
            self._indicator_id = self._canvas.create_rectangle(
                screen_x - s/2, screen_y - s/2,
                screen_x + s/2, screen_y + s/2,
                outline=self.SNAP_COLOR,
                width=2,
                tags="snap_indicator"
            )
        elif mode & SnapMode.MIDPOINT:
            # Trójkąt dla midpoint
            self._indicator_id = self._canvas.create_polygon(
                screen_x, screen_y - s,
                screen_x - s, screen_y + s/2,
                screen_x + s, screen_y + s/2,
                outline=self.SNAP_COLOR,
                fill="",
                width=2,
                tags="snap_indicator"
            )
        elif mode & SnapMode.CENTER:
            # Okrąg dla center
            self._indicator_id = self._canvas.create_oval(
                screen_x - s/2, screen_y - s/2,
                screen_x + s/2, screen_y + s/2,
                outline=self.SNAP_COLOR,
                width=2,
                tags="snap_indicator"
            )
        else:
            # Domyślny: krzyżyk
            self._canvas.create_line(
                screen_x - s, screen_y, screen_x + s, screen_y,
                fill=self.SNAP_COLOR, width=2, tags="snap_indicator"
            )
            self._indicator_id = self._canvas.create_line(
                screen_x, screen_y - s, screen_x, screen_y + s,
                fill=self.SNAP_COLOR, width=2, tags="snap_indicator"
            )

    def clear_indicator(self):
        """Usuń wskaźnik snap"""
        if self._canvas:
            self._canvas.delete("snap_indicator")
        self._indicator_id = None

    def get_snapped_position(self, world_x: float, world_y: float,
                             screen_transform: callable = None) -> Tuple[float, float]:
        """
        Zwróć pozycję snap lub oryginalną jeśli brak snap.

        Główna metoda do użycia przy wymiarowaniu/edycji.
        """
        snap = self.find_snap(world_x, world_y, screen_transform)
        if snap:
            return (snap.x, snap.y)
        return (world_x, world_y)

    @property
    def active_snap(self) -> Optional[SnapPoint]:
        """Aktualnie aktywny punkt snap"""
        return self._active_snap

    @property
    def snap_count(self) -> int:
        """Liczba punktów snap w cache"""
        return len(self._snap_points)


# Eksporty
__all__ = ['SnapManager', 'SnapPoint', 'SnapMode']
