"""
Dimension Tool - Narzędzie do wymiarowania CAD
==============================================
Automatyczne i ręczne wymiarowanie detali.
"""

import math
import tkinter as tk
from typing import List, Tuple, Optional, Callable
import logging

logger = logging.getLogger(__name__)

try:
    from core.dxf.entities import DXFDimension, DXFPart
except ImportError:
    DXFDimension = None
    DXFPart = None


class DimensionTool:
    """
    Narzędzie do wymiarowania.

    Tryby:
    - auto_bbox: Automatyczne wymiarowanie bounding box
    - auto_holes: Automatyczne wymiarowanie otworów
    - linear: Ręczne wymiarowanie liniowe (klik 2 punkty)
    - radius: Wymiarowanie promienia (klik na okrąg)
    """

    # Kolory
    DIM_COLOR = "#f59e0b"      # Orange
    DIM_TEXT_COLOR = "#ffffff"  # White
    DIM_LINE_WIDTH = 1

    def __init__(self, canvas, on_dimension_added: Callable = None):
        """
        Args:
            canvas: CADCanvas do rysowania
            on_dimension_added: Callback gdy dodano wymiar
        """
        self.canvas = canvas
        self.on_dimension_added = on_dimension_added

        # Stan
        self._active = False
        self._mode = "linear"  # linear, radius
        self._first_point = None
        self._temp_line_id = None

        # Lista wymiarów
        self.dimensions: List['DXFDimension'] = []

    def activate(self, mode: str = "linear"):
        """Aktywuj narzędzie wymiarowania"""
        self._active = True
        self._mode = mode
        self._first_point = None
        self.canvas.config(cursor="crosshair")

        # Bindingi
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Escape>", self._on_cancel)

    def deactivate(self):
        """Dezaktywuj narzędzie"""
        self._active = False
        self._first_point = None
        self.canvas.config(cursor="")

        # Usuń temp line
        if self._temp_line_id:
            self.canvas.delete(self._temp_line_id)
            self._temp_line_id = None

        # Unbind
        try:
            self.canvas.unbind("<Button-1>")
            self.canvas.unbind("<Motion>")
            self.canvas.unbind("<Escape>")
        except:
            pass

    def _on_click(self, event):
        """Obsługa kliknięcia"""
        if not self._active:
            return

        # Konwertuj na world coords z uwzględnieniem snap
        wx, wy = self.canvas.screen_to_world(event.x, event.y)

        # Użyj snap jeśli dostępny
        if hasattr(self.canvas, 'get_snapped_position'):
            wx, wy = self.canvas.get_snapped_position(wx, wy)

        if self._mode == "linear":
            if self._first_point is None:
                # Pierwszy punkt
                self._first_point = (wx, wy)
            else:
                # Drugi punkt - utwórz wymiar
                self._create_linear_dimension(self._first_point, (wx, wy))
                self._first_point = None

                # Usuń temp line
                if self._temp_line_id:
                    self.canvas.delete(self._temp_line_id)
                    self._temp_line_id = None

    def _on_motion(self, event):
        """Obsługa ruchu myszy"""
        if not self._active or self._first_point is None:
            return

        # Rysuj tymczasową linię
        wx, wy = self.canvas.screen_to_world(event.x, event.y)

        sx1, sy1 = self.canvas.world_to_screen(*self._first_point)
        sx2, sy2 = event.x, event.y

        if self._temp_line_id:
            self.canvas.delete(self._temp_line_id)

        self._temp_line_id = self.canvas.create_line(
            sx1, sy1, sx2, sy2,
            fill=self.DIM_COLOR,
            dash=(4, 4),
            tags="temp_dim"
        )

    def _on_cancel(self, event):
        """Anuluj wymiarowanie"""
        self._first_point = None
        if self._temp_line_id:
            self.canvas.delete(self._temp_line_id)
            self._temp_line_id = None

    def _create_linear_dimension(self, p1: Tuple[float, float], p2: Tuple[float, float]):
        """Utwórz wymiar liniowy"""
        # Oblicz długość
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.sqrt(dx*dx + dy*dy)

        # Pozycja tekstu (środek + offset)
        offset = 10.0  # mm
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2

        # Offset prostopadły do linii
        if length > 0.001:
            nx = -dy / length * offset
            ny = dx / length * offset
        else:
            nx, ny = 0, offset

        text_pos = (mid_x + nx, mid_y + ny)

        # Utwórz wymiar
        dim = DXFDimension(
            dim_type="linear",
            start_point=p1,
            end_point=p2,
            text_position=text_pos,
            text=f"{length:.1f}",
            value=length,
            layer="DIMENSIONS"
        ) if DXFDimension else {
            'type': 'linear',
            'start': p1,
            'end': p2,
            'text_pos': text_pos,
            'value': length
        }

        self.dimensions.append(dim)

        # Rysuj
        self._draw_dimension(dim)

        # Callback
        if self.on_dimension_added:
            self.on_dimension_added(dim)

    def _draw_dimension(self, dim):
        """Rysuj wymiar na canvas"""
        if isinstance(dim, dict):
            p1 = dim['start']
            p2 = dim['end']
            text_pos = dim['text_pos']
            text = f"{dim['value']:.1f}"
        else:
            p1 = dim.start_point
            p2 = dim.end_point
            text_pos = dim.text_position
            text = dim.text

        # Konwertuj na screen
        sx1, sy1 = self.canvas.world_to_screen(*p1)
        sx2, sy2 = self.canvas.world_to_screen(*p2)
        stx, sty = self.canvas.world_to_screen(*text_pos)

        # Linia wymiarowa
        self.canvas.create_line(
            sx1, sy1, sx2, sy2,
            fill=self.DIM_COLOR,
            width=self.DIM_LINE_WIDTH,
            tags="dimension"
        )

        # Strzałki na końcach
        self._draw_arrow(sx1, sy1, sx2, sy2)
        self._draw_arrow(sx2, sy2, sx1, sy1)

        # Linie pomocnicze
        # Oblicz prostopadły kierunek
        dx = sx2 - sx1
        dy = sy2 - sy1
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0.001:
            nx = -dy / length * 15
            ny = dx / length * 15

            # Linia pomocnicza przy p1
            self.canvas.create_line(
                sx1, sy1, sx1 + nx, sy1 + ny,
                fill=self.DIM_COLOR,
                width=self.DIM_LINE_WIDTH,
                tags="dimension"
            )
            # Linia pomocnicza przy p2
            self.canvas.create_line(
                sx2, sy2, sx2 + nx, sy2 + ny,
                fill=self.DIM_COLOR,
                width=self.DIM_LINE_WIDTH,
                tags="dimension"
            )

        # Tekst
        self.canvas.create_text(
            stx, sty,
            text=text,
            fill=self.DIM_TEXT_COLOR,
            font=("Arial", 10, "bold"),
            tags="dimension"
        )

    def _draw_arrow(self, x1, y1, x2, y2, size=8):
        """Rysuj strzałkę na końcu linii"""
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx*dx + dy*dy)

        if length < 0.001:
            return

        # Normalizuj
        dx /= length
        dy /= length

        # Punkty strzałki
        arrow_x = x1 + dx * size
        arrow_y = y1 + dy * size

        # Kąt strzałki
        angle = 25  # stopni
        rad = math.radians(angle)

        # Lewe skrzydło
        lx = x1 + size * (dx * math.cos(rad) - dy * math.sin(rad))
        ly = y1 + size * (dx * math.sin(rad) + dy * math.cos(rad))

        # Prawe skrzydło
        rx = x1 + size * (dx * math.cos(-rad) - dy * math.sin(-rad))
        ry = y1 + size * (dx * math.sin(-rad) + dy * math.cos(-rad))

        self.canvas.create_polygon(
            x1, y1, lx, ly, rx, ry,
            fill=self.DIM_COLOR,
            outline=self.DIM_COLOR,
            tags="dimension"
        )

    def auto_dimension_bbox(self, part: 'DXFPart'):
        """
        Automatyczne wymiarowanie bounding box.

        Dodaje:
        - Wymiar szerokości (na dole)
        - Wymiar wysokości (po lewej)
        """
        if not part:
            return

        # Szerokość (na dole)
        width_dim = DXFDimension(
            dim_type="linear",
            start_point=(part.min_x, part.min_y - 15),
            end_point=(part.max_x, part.min_y - 15),
            text_position=((part.min_x + part.max_x) / 2, part.min_y - 25),
            text=f"{part.width:.1f}",
            value=part.width,
            layer="DIMENSIONS"
        ) if DXFDimension else {
            'type': 'linear',
            'start': (part.min_x, part.min_y - 15),
            'end': (part.max_x, part.min_y - 15),
            'text_pos': ((part.min_x + part.max_x) / 2, part.min_y - 25),
            'value': part.width
        }

        # Wysokość (po lewej)
        height_dim = DXFDimension(
            dim_type="linear",
            start_point=(part.min_x - 15, part.min_y),
            end_point=(part.min_x - 15, part.max_y),
            text_position=(part.min_x - 25, (part.min_y + part.max_y) / 2),
            text=f"{part.height:.1f}",
            value=part.height,
            layer="DIMENSIONS"
        ) if DXFDimension else {
            'type': 'linear',
            'start': (part.min_x - 15, part.min_y),
            'end': (part.min_x - 15, part.max_y),
            'text_pos': (part.min_x - 25, (part.min_y + part.max_y) / 2),
            'value': part.height
        }

        self.dimensions.append(width_dim)
        self.dimensions.append(height_dim)

        self._draw_dimension(width_dim)
        self._draw_dimension(height_dim)

    def auto_dimension_holes(self, part: 'DXFPart', max_holes: int = 5):
        """
        Automatyczne wymiarowanie otworów (średnice).

        Args:
            part: DXFPart z otworami
            max_holes: Maksymalna liczba otworów do wymiarowania
        """
        if not part or not part.holes:
            return

        for i, hole in enumerate(part.holes[:max_holes]):
            if len(hole) < 3:
                continue

            # Oblicz centroid i przybliżoną średnicę
            cx = sum(p[0] for p in hole) / len(hole)
            cy = sum(p[1] for p in hole) / len(hole)

            # Przybliżona średnica (zakładamy okrąg)
            max_dist = 0
            for p in hole:
                dist = math.sqrt((p[0] - cx)**2 + (p[1] - cy)**2)
                max_dist = max(max_dist, dist)

            diameter = max_dist * 2

            # Wymiar średnicy
            dim = DXFDimension(
                dim_type="diameter",
                start_point=(cx - max_dist, cy),
                end_point=(cx + max_dist, cy),
                text_position=(cx, cy + max_dist + 10),
                text=f"Ø{diameter:.1f}",
                value=diameter,
                layer="DIMENSIONS"
            ) if DXFDimension else {
                'type': 'diameter',
                'start': (cx - max_dist, cy),
                'end': (cx + max_dist, cy),
                'text_pos': (cx, cy + max_dist + 10),
                'value': diameter
            }

            self.dimensions.append(dim)
            self._draw_dimension(dim)

    def clear_dimensions(self):
        """Usuń wszystkie wymiary"""
        self.dimensions.clear()
        self.canvas.delete("dimension")

    def redraw_all(self):
        """Przerysuj wszystkie wymiary"""
        self.canvas.delete("dimension")
        for dim in self.dimensions:
            self._draw_dimension(dim)


# Eksporty
__all__ = ['DimensionTool']
