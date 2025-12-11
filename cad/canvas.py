"""
CAD Canvas - Interaktywny canvas do rysowania 2D CAD
====================================================
Tkinter Canvas z funkcjami zoom, pan i transformacjami współrzędnych.
"""

import math
import tkinter as tk
from tkinter import ttk
from typing import Tuple, Optional, List, Dict, Callable, Any
import logging

logger = logging.getLogger(__name__)

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False


class CADCanvas(tk.Canvas):
    """
    Interaktywny canvas CAD z zoom i pan.

    Cechy:
    - Transformacje world <-> screen
    - Zoom wheel + zoom fit/all
    - Pan z środkowym przyciskiem myszy
    - Siatka pomocnicza
    - Wsparcie dla selection i hover
    """

    # Kolory
    BG_COLOR = "#1a1a1a"
    GRID_COLOR = "#2d2d2d"
    GRID_COLOR_MAJOR = "#3d3d3d"
    CONTOUR_COLOR = "#22c55e"  # Green
    HOLE_COLOR = "#ef4444"     # Red
    FILL_COLOR = "#3b82f6"     # Blue
    DIMENSION_COLOR = "#f59e0b"  # Orange
    SELECTION_COLOR = "#fbbf24"  # Yellow
    TEXT_COLOR = "#ffffff"

    def __init__(
        self,
        parent,
        width: int = 800,
        height: int = 600,
        bg: str = None,
        **kwargs
    ):
        """
        Args:
            parent: Widget rodzica
            width: Szerokość canvas
            height: Wysokość canvas
            bg: Kolor tła
        """
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg or self.BG_COLOR,
            highlightthickness=0,
            **kwargs
        )

        # Transformacje
        self._scale = 1.0       # Skala (piksele na mm)
        self._offset_x = 0.0    # Przesunięcie X w pikselach
        self._offset_y = 0.0    # Przesunięcie Y w pikselach

        # World bounds (zakres danych)
        self._world_min_x = 0.0
        self._world_max_x = 100.0
        self._world_min_y = 0.0
        self._world_max_y = 100.0

        # Pan state
        self._pan_start_x = 0
        self._pan_start_y = 0
        self._is_panning = False

        # Zoom limits
        self._min_scale = 0.01
        self._max_scale = 100.0
        self._zoom_factor = 1.2

        # Grid settings
        self._show_grid = True
        self._grid_spacing = 10.0  # mm

        # Dane
        self._part = None

        # Bindings
        self._setup_bindings()

    def _setup_bindings(self):
        """Skonfiguruj bindingi myszy"""
        # Zoom wheel
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)  # Linux
        self.bind("<Button-5>", self._on_mousewheel)  # Linux

        # Pan (środkowy przycisk)
        self.bind("<Button-2>", self._on_pan_start)
        self.bind("<B2-Motion>", self._on_pan_move)
        self.bind("<ButtonRelease-2>", self._on_pan_end)

        # Pan alternatywny (Shift + lewy przycisk)
        self.bind("<Shift-Button-1>", self._on_pan_start)
        self.bind("<Shift-B1-Motion>", self._on_pan_move)
        self.bind("<Shift-ButtonRelease-1>", self._on_pan_end)

        # Resize
        self.bind("<Configure>", self._on_resize)

    # ==================== Transformacje ====================

    def world_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        """
        Konwertuj współrzędne świata (mm) na screen (piksele).

        Y jest odwrócone (CAD: Y w górę, screen: Y w dół).
        """
        sx = self._offset_x + x * self._scale
        sy = self._offset_y + (self._world_max_y - y) * self._scale
        return sx, sy

    def screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        """Konwertuj współrzędne screen (piksele) na world (mm)."""
        x = (sx - self._offset_x) / self._scale
        y = self._world_max_y - (sy - self._offset_y) / self._scale
        return x, y

    def world_to_screen_points(
        self, points: List[Tuple[float, float]]
    ) -> List[float]:
        """Konwertuj listę punktów world na flat list dla canvas.create_polygon"""
        result = []
        for x, y in points:
            sx, sy = self.world_to_screen(x, y)
            result.extend([sx, sy])
        return result

    # ==================== Zoom ====================

    def zoom_fit(self, margin_pct: float = 0.1):
        """Dopasuj zoom żeby cały obiekt był widoczny"""
        if self._part is None:
            return

        canvas_width = self.winfo_width()
        canvas_height = self.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        world_width = self._world_max_x - self._world_min_x
        world_height = self._world_max_y - self._world_min_y

        if world_width <= 0 or world_height <= 0:
            return

        # Oblicz skalę z marginesem
        margin = margin_pct
        available_width = canvas_width * (1 - 2 * margin)
        available_height = canvas_height * (1 - 2 * margin)

        scale_x = available_width / world_width
        scale_y = available_height / world_height
        self._scale = min(scale_x, scale_y)

        # Wycentruj
        self._offset_x = (canvas_width - world_width * self._scale) / 2
        self._offset_y = (canvas_height - world_height * self._scale) / 2

        self.redraw()

    def zoom_all(self):
        """Alias dla zoom_fit"""
        self.zoom_fit()

    def zoom_in(self, center: Tuple[float, float] = None, factor: float = None):
        """
        Przybliż.

        Args:
            center: Punkt centralny zoom (screen coords), domyślnie środek canvas
            factor: Współczynnik zoom, domyślnie self._zoom_factor
        """
        if factor is None:
            factor = self._zoom_factor

        if center is None:
            center = (self.winfo_width() / 2, self.winfo_height() / 2)

        self._zoom_at(center[0], center[1], factor)

    def zoom_out(self, center: Tuple[float, float] = None, factor: float = None):
        """Oddal"""
        if factor is None:
            factor = self._zoom_factor

        if center is None:
            center = (self.winfo_width() / 2, self.winfo_height() / 2)

        self._zoom_at(center[0], center[1], 1.0 / factor)

    def _zoom_at(self, sx: float, sy: float, factor: float):
        """Zoom w określonym punkcie screen"""
        # Punkt w world przed zoom
        wx, wy = self.screen_to_world(sx, sy)

        # Nowa skala
        new_scale = self._scale * factor
        new_scale = max(self._min_scale, min(self._max_scale, new_scale))

        if new_scale == self._scale:
            return

        self._scale = new_scale

        # Przelicz offset żeby punkt world był w tym samym miejscu screen
        self._offset_x = sx - wx * self._scale
        self._offset_y = sy - (self._world_max_y - wy) * self._scale

        self.redraw()

    # ==================== Pan ====================

    def pan_by(self, dx: float, dy: float):
        """Przesuń widok o dx, dy pikseli"""
        self._offset_x += dx
        self._offset_y += dy
        self.redraw()

    def _on_pan_start(self, event):
        """Rozpocznij pan"""
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._is_panning = True
        self.config(cursor="fleur")

    def _on_pan_move(self, event):
        """Pan w trakcie ruchu"""
        if not self._is_panning:
            return

        dx = event.x - self._pan_start_x
        dy = event.y - self._pan_start_y

        self._offset_x += dx
        self._offset_y += dy

        self._pan_start_x = event.x
        self._pan_start_y = event.y

        self.redraw()

    def _on_pan_end(self, event):
        """Zakończ pan"""
        self._is_panning = False
        self.config(cursor="")

    # ==================== Event handlers ====================

    def _on_mousewheel(self, event):
        """Obsługa scroll wheel dla zoom"""
        # Określ kierunek
        if event.num == 4 or event.delta > 0:
            factor = self._zoom_factor
        elif event.num == 5 or event.delta < 0:
            factor = 1.0 / self._zoom_factor
        else:
            return

        # Zoom w punkcie kursora
        self._zoom_at(event.x, event.y, factor)

    def _on_resize(self, event):
        """Obsługa zmiany rozmiaru canvas"""
        if event.width > 1 and event.height > 1:
            # Przerysuj po resize
            self.after(10, self.redraw)

    # ==================== Drawing ====================

    def set_part(self, part):
        """
        Ustaw detal do wyświetlenia.

        Args:
            part: DXFPart z core.dxf
        """
        self._part = part

        if part:
            # Ustaw world bounds
            self._world_min_x = part.min_x
            self._world_max_x = part.max_x
            self._world_min_y = part.min_y
            self._world_max_y = part.max_y

            # Dodaj margines
            margin = max(part.width, part.height) * 0.05
            self._world_min_x -= margin
            self._world_max_x += margin
            self._world_min_y -= margin
            self._world_max_y += margin

        # Zoom fit i redraw
        self.after(10, self.zoom_fit)

    def redraw(self):
        """Przerysuj canvas"""
        self.delete("all")

        if self._show_grid:
            self._draw_grid()

        if self._part:
            self._draw_part()

        self._draw_axes_indicator()

    def _draw_grid(self):
        """Rysuj siatkę pomocniczą"""
        canvas_width = self.winfo_width()
        canvas_height = self.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        # Oblicz widoczny zakres w world coords
        world_x1, world_y1 = self.screen_to_world(0, canvas_height)
        world_x2, world_y2 = self.screen_to_world(canvas_width, 0)

        # Dostosuj grid spacing do zoom
        grid_spacing = self._grid_spacing
        while grid_spacing * self._scale < 20:
            grid_spacing *= 2
        while grid_spacing * self._scale > 100:
            grid_spacing /= 2

        # Linie pionowe
        x = math.floor(world_x1 / grid_spacing) * grid_spacing
        while x <= world_x2:
            sx, _ = self.world_to_screen(x, 0)
            is_major = abs(x) < 0.001 or abs(x % (grid_spacing * 5)) < 0.001
            color = self.GRID_COLOR_MAJOR if is_major else self.GRID_COLOR
            width = 2 if abs(x) < 0.001 else 1
            self.create_line(sx, 0, sx, canvas_height, fill=color, width=width, tags="grid")
            x += grid_spacing

        # Linie poziome
        y = math.floor(world_y1 / grid_spacing) * grid_spacing
        while y <= world_y2:
            _, sy = self.world_to_screen(0, y)
            is_major = abs(y) < 0.001 or abs(y % (grid_spacing * 5)) < 0.001
            color = self.GRID_COLOR_MAJOR if is_major else self.GRID_COLOR
            width = 2 if abs(y) < 0.001 else 1
            self.create_line(0, sy, canvas_width, sy, fill=color, width=width, tags="grid")
            y += grid_spacing

    def _draw_part(self):
        """Rysuj detal"""
        part = self._part
        if not part:
            return

        # Rysuj kontur zewnętrzny
        if part.outer_contour and part.outer_contour.points:
            coords = self.world_to_screen_points(part.outer_contour.points)
            if len(coords) >= 6:
                self.create_polygon(
                    coords,
                    fill=self.FILL_COLOR,
                    outline=self.CONTOUR_COLOR,
                    width=2,
                    tags="contour"
                )

        # Rysuj otwory
        for hole in part.holes:
            if hole.points:
                coords = self.world_to_screen_points(hole.points)
                if len(coords) >= 6:
                    self.create_polygon(
                        coords,
                        fill=self.BG_COLOR,
                        outline=self.HOLE_COLOR,
                        width=1.5,
                        tags="hole"
                    )

        # Rysuj wymiary
        for dim in part.dimensions:
            self._draw_dimension(dim)

    def _draw_dimension(self, dim):
        """Rysuj wymiar"""
        sx1, sy1 = self.world_to_screen(*dim.start_point)
        sx2, sy2 = self.world_to_screen(*dim.end_point)
        stx, sty = self.world_to_screen(*dim.text_position)

        # Linia wymiarowa
        self.create_line(
            sx1, sy1, sx2, sy2,
            fill=self.DIMENSION_COLOR,
            width=1,
            tags="dimension"
        )

        # Tekst
        text = dim.text or f"{dim.value:.1f}"
        self.create_text(
            stx, sty,
            text=text,
            fill=self.DIMENSION_COLOR,
            font=("Arial", 10),
            tags="dimension"
        )

    def _draw_axes_indicator(self):
        """Rysuj wskaźnik osi w rogu"""
        # Pozycja w lewym dolnym rogu
        size = 50
        margin = 20
        x0 = margin + size / 2
        y0 = self.winfo_height() - margin - size / 2

        # Oś X (czerwona)
        self.create_line(x0, y0, x0 + size / 2, y0, fill="#ef4444", width=2, arrow=tk.LAST)
        self.create_text(x0 + size / 2 + 10, y0, text="X", fill="#ef4444", font=("Arial", 10))

        # Oś Y (zielona)
        self.create_line(x0, y0, x0, y0 - size / 2, fill="#22c55e", width=2, arrow=tk.LAST)
        self.create_text(x0, y0 - size / 2 - 10, text="Y", fill="#22c55e", font=("Arial", 10))

    # ==================== Grid settings ====================

    def set_grid_visible(self, visible: bool):
        """Włącz/wyłącz siatkę"""
        self._show_grid = visible
        self.redraw()

    def set_grid_spacing(self, spacing: float):
        """Ustaw odstęp siatki (mm)"""
        self._grid_spacing = spacing
        self.redraw()

    # ==================== Info ====================

    @property
    def scale(self) -> float:
        """Aktualna skala (px/mm)"""
        return self._scale

    @property
    def current_zoom_percent(self) -> float:
        """Aktualny zoom w procentach"""
        # 100% = 1 pixel = 1 mm
        return self._scale * 100

    def get_visible_world_rect(self) -> Tuple[float, float, float, float]:
        """Pobierz widoczny obszar w world coords (min_x, min_y, max_x, max_y)"""
        w = self.winfo_width()
        h = self.winfo_height()
        x1, y1 = self.screen_to_world(0, h)
        x2, y2 = self.screen_to_world(w, 0)
        return (x1, y1, x2, y2)


# Eksporty
__all__ = ['CADCanvas']
