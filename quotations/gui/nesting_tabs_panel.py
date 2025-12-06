"""
Nesting Tabs Panel - Zakładkowy panel nestingu z wieloma arkuszami
===================================================================
Każda kombinacja materiał+grubość ma własną zakładkę z:
- Przewijalną listą arkuszy (wiele arkuszy obok siebie)
- Live preview nestingu z zoom
- Interaktywnym wyborem detali (kliknięcie na arkuszu → lista, kliknięcie na liście → arkusz)
- Kolorowaniem nieznestowanych detali (czerwone tło)
- Podglądem wybranego detalu

Funkcjonalności:
- Kliknięcie na detal na nestingu → zaznacz na liście
- Kliknięcie na liście → podświetl na nestingu (wskaż arkusz)
- Nieznestowane detale mają czerwone tło na liście
- Podgląd detalu z możliwością powiększenia
- Edycja ilości przez podwójne kliknięcie
"""

import customtkinter as ctk
from tkinter import Canvas, ttk, messagebox, filedialog
import threading
import logging
from typing import List, Dict, Optional, Callable, Tuple, Any, Set
from dataclasses import dataclass, field
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Import motion dynamics modules
try:
    # Add project root to path for imports
    _project_root = Path(__file__).parent.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

    from costing.motion.motion_planner import MachineProfile, estimate_motion_time, m_min_to_mm_s
    from costing.toolpath.dxf_extractor import extract_motion_segments
    HAS_MOTION_DYNAMICS = True
except ImportError as e:
    logger.warning(f"Motion dynamics not available: {e}")
    HAS_MOTION_DYNAMICS = False

# Import pricing repository for cutting speeds from Supabase
try:
    from pricing.repository import PricingRepository
    from core.supabase_client import get_supabase_client
    _pricing_repo = PricingRepository(get_supabase_client())
    HAS_PRICING_REPO = True
except (ImportError, Exception) as e:
    logger.warning(f"Pricing repository not available: {e}")
    HAS_PRICING_REPO = False
    _pricing_repo = None


@dataclass
class MachineDynamicsSettings:
    """Machine dynamics settings for time calculation."""
    use_dynamic_method: bool = True
    max_accel_mm_s2: float = 2000.0
    square_corner_velocity_mm_s: float = 50.0
    max_rapid_mm_s: float = 500.0
    junction_deviation_mm: float = 0.05
    use_junction_deviation: bool = False

# Kolory dla detali (cykliczne)
PART_COLORS = [
    "#8b5cf6", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4",
    "#ec4899", "#84cc16", "#f97316", "#6366f1", "#14b8a6",
    "#a855f7", "#f43f5e", "#0ea5e9", "#eab308", "#64748b"
]


class VelocityProfileCanvas(Canvas):
    """Mini canvas showing velocity profile for a part."""

    def __init__(self, parent, width=280, height=60, **kwargs):
        super().__init__(parent, width=width, height=height,
                        bg="#1a1a1a", highlightthickness=1,
                        highlightbackground="#333333", **kwargs)
        self.velocity_data = []  # List of (distance, velocity) points
        self.v_max = 100.0
        self.total_distance = 0.0

    def set_velocity_profile(self, velocities: List[Tuple[float, float]], v_max: float = 100.0):
        """Set velocity profile data.

        Args:
            velocities: List of (cumulative_distance_mm, velocity_mm_s) tuples
            v_max: Maximum velocity for scaling
        """
        self.velocity_data = velocities
        self.v_max = v_max
        self.total_distance = velocities[-1][0] if velocities else 0
        self._redraw()

    def clear(self):
        """Clear the profile."""
        self.velocity_data = []
        self.delete("all")
        self.create_text(
            self.winfo_reqwidth() // 2,
            self.winfo_reqheight() // 2,
            text="Wybierz detal aby zobaczyć profil V",
            fill="#666666",
            font=("Arial", 8)
        )

    def _redraw(self):
        """Redraw the velocity profile."""
        self.delete("all")

        if not self.velocity_data or len(self.velocity_data) < 2:
            self.create_text(
                self.winfo_reqwidth() // 2,
                self.winfo_reqheight() // 2,
                text="Brak danych profilu",
                fill="#666666",
                font=("Arial", 8)
            )
            return

        w = self.winfo_reqwidth() - 20
        h = self.winfo_reqheight() - 20
        offset_x = 10
        offset_y = 10

        # Scale factors
        x_scale = w / self.total_distance if self.total_distance > 0 else 1
        y_scale = (h - 5) / self.v_max if self.v_max > 0 else 1

        # Draw velocity profile as filled area
        points = [(offset_x, offset_y + h)]  # Start at bottom left
        for dist, vel in self.velocity_data:
            x = offset_x + dist * x_scale
            y = offset_y + h - vel * y_scale
            points.append((x, y))
        points.append((offset_x + w, offset_y + h))  # End at bottom right

        # Convert to flat list
        flat_points = []
        for px, py in points:
            flat_points.extend([px, py])

        # Draw filled polygon (light blue fill to simulate transparency)
        self.create_polygon(flat_points, fill="#dbeafe", outline="#3b82f6", width=1)

        # Draw V_max reference line
        v_max_y = offset_y + h - self.v_max * y_scale
        self.create_line(offset_x, v_max_y, offset_x + w, v_max_y,
                        fill="#22c55e", dash=(3, 3), width=1)

        # Labels
        self.create_text(offset_x + 2, v_max_y - 5,
                        text=f"V_max: {self.v_max:.0f}",
                        fill="#22c55e", anchor="nw", font=("Arial", 7))

        # Distance label
        self.create_text(offset_x + w, offset_y + h + 5,
                        text=f"{self.total_distance:.0f}mm",
                        fill="#888888", anchor="ne", font=("Arial", 7))

    def calculate_from_dxf(self, filepath: str, dynamics_settings: MachineDynamicsSettings, v_max_mm_s: float):
        """Calculate velocity profile from DXF file."""
        if not HAS_MOTION_DYNAMICS or not filepath or not os.path.exists(filepath):
            self.clear()
            return

        try:
            from costing.motion.motion_planner import (
                MachineProfile, calculate_junction_angles, plan_speeds, corner_speed_limit
            )

            segments = extract_motion_segments(filepath)
            if not segments:
                self.clear()
                return

            machine = MachineProfile(
                max_accel_mm_s2=dynamics_settings.max_accel_mm_s2,
                max_rapid_mm_s=dynamics_settings.max_rapid_mm_s,
                square_corner_velocity_mm_s=dynamics_settings.square_corner_velocity_mm_s
            )

            # Filter cutting segments only
            cutting_segments = [s for s in segments if not s.is_rapid]
            if not cutting_segments:
                self.clear()
                return

            # Calculate junction angles
            angles = calculate_junction_angles(cutting_segments)

            # Calculate junction speed limits
            v_junction = []
            for angle in angles:
                v = corner_speed_limit(angle, machine.square_corner_velocity_mm_s, v_max_mm_s)
                v_junction.append(v)

            # First and last must be 0 (start/stop)
            v_junction[0] = 0.0
            v_junction[-1] = 0.0

            # Plan speeds
            lengths = [s.length_mm for s in cutting_segments]
            planned_v = plan_speeds(lengths, v_junction, v_max_mm_s, machine.max_accel_mm_s2)

            # Build velocity profile data
            velocity_data = []
            cumulative_dist = 0.0

            for i, length in enumerate(lengths):
                # Start of segment
                velocity_data.append((cumulative_dist, planned_v[i]))

                # End of segment (use same velocity for visualization simplicity)
                cumulative_dist += length
                velocity_data.append((cumulative_dist, planned_v[i + 1]))

            self.set_velocity_profile(velocity_data, v_max_mm_s)

        except Exception as e:
            logger.error(f"Error calculating velocity profile: {e}")
            self.clear()


class Theme:
    """Paleta kolorów"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_CARD_HOVER = "#252525"
    BG_INPUT = "#2d2d2d"
    
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#666666"
    
    ACCENT_PRIMARY = "#8b5cf6"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"
    ACCENT_INFO = "#06b6d4"
    
    # Kolory dla statusów detali
    UNPLACED_BG = "#4a1c1c"  # Ciemne czerwone tło dla nieznestowanych
    PLACED_BG = "#1c3a1c"    # Ciemne zielone tło dla znestowanych


# ============================================================
# Part Preview Canvas
# ============================================================

class PartPreviewCanvas(Canvas):
    """Canvas do podglądu pojedynczego detalu - kliknij aby powiększyć"""
    
    def __init__(self, parent, width=200, height=150, **kwargs):
        super().__init__(parent, width=width, height=height, 
                        bg="#1a1a1a", highlightthickness=1, 
                        highlightbackground="#333333", **kwargs)
        self.part_data: Optional[dict] = None
        self.part_color: str = "#3B82F6"
        
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self.configure(cursor="hand2"))
        self.bind("<Leave>", lambda e: self.configure(cursor=""))
    
    def _on_click(self, event):
        """Otwórz duże okno podglądu"""
        if self.part_data and self.part_data.get('contour'):
            self._open_large_preview()
    
    def _open_large_preview(self):
        """Otwórz duże okno z podglądem detalu"""
        root = self.winfo_toplevel()
        
        preview_window = ctk.CTkToplevel(root)
        preview_window.title(f"Podgląd: {self.part_data.get('name', 'Detal')}")
        preview_window.configure(fg_color="#1a1a1a")
        
        win_size = 800
        preview_window.geometry(f"{win_size}x{win_size}")
        preview_window.minsize(600, 600)
        
        preview_window.update_idletasks()
        x = (preview_window.winfo_screenwidth() - win_size) // 2
        y = (preview_window.winfo_screenheight() - win_size) // 2
        preview_window.geometry(f"+{x}+{y}")
        
        large_canvas = Canvas(preview_window, bg="#1a1a1a", highlightthickness=0)
        large_canvas.pack(fill="both", expand=True, padx=20, pady=20)
        
        def on_resize(event):
            self._draw_large_preview(large_canvas)
        
        large_canvas.bind("<Configure>", on_resize)
        preview_window.after(50, lambda: self._draw_large_preview(large_canvas))
        
        btn_close = ctk.CTkButton(preview_window, text="Zamknij", 
                                   command=preview_window.destroy, width=120)
        btn_close.pack(pady=10)
        
        preview_window.focus_set()
        preview_window.grab_set()
    
    def _draw_large_preview(self, canvas: Canvas):
        """Rysuj detal na dużym canvas"""
        canvas.delete("all")
        
        if not self.part_data:
            return
        
        contour = self.part_data.get('contour', [])
        if len(contour) < 3:
            return
        
        canvas.update_idletasks()
        canvas_w = canvas.winfo_width() - 40
        canvas_h = canvas.winfo_height() - 80
        
        if canvas_w <= 0 or canvas_h <= 0:
            return
        
        width = self.part_data.get('width', 100)
        height = self.part_data.get('height', 100)
        
        scale_x = canvas_w / width if width > 0 else 1
        scale_y = canvas_h / height if height > 0 else 1
        scale = min(scale_x, scale_y) * 0.9
        
        offset_x = (canvas_w - width * scale) / 2 + 20
        offset_y = (canvas_h - height * scale) / 2 + 20
        
        # Siatka
        grid_step = 10
        grid_scale = grid_step * scale
        if grid_scale > 5:
            for gx in range(0, int(width) + 1, grid_step):
                x = offset_x + gx * scale
                canvas.create_line(x, offset_y, x, offset_y + height * scale, fill="#333333", width=1)
            for gy in range(0, int(height) + 1, grid_step):
                y = offset_y + (height - gy) * scale
                canvas.create_line(offset_x, y, offset_x + width * scale, y, fill="#333333", width=1)
        
        # Kontur
        points = []
        for x, y in contour:
            cx = offset_x + x * scale
            cy = offset_y + (height - y) * scale
            points.extend([cx, cy])
        
        canvas.create_polygon(points, fill=self.part_color, outline="#ffffff", width=2)
        
        # Otwory
        for hole in self.part_data.get('holes', []):
            if len(hole) >= 3:
                hole_points = []
                for x, y in hole:
                    hx = offset_x + x * scale
                    hy = offset_y + (height - y) * scale
                    hole_points.extend([hx, hy])
                canvas.create_polygon(hole_points, fill="#1a1a1a", outline="#888888", width=1)
        
        name = self.part_data.get('name', 'Detal')
        canvas.create_text(canvas_w // 2 + 20, 30, text=name, fill="#ffffff", font=("Arial", 14, "bold"))
        
        dims_text = f"Wymiary: {width:.2f} x {height:.2f} mm"
        canvas.create_text(canvas_w // 2 + 20, canvas_h + 50, text=dims_text, fill="#aaaaaa", font=("Arial", 12))
    
    def set_part(self, part_data: Optional[dict], color: str = "#3B82F6"):
        """Ustaw detal do wyświetlenia"""
        self.part_data = part_data
        self.part_color = color
        self.delete("all")
        
        if not part_data:
            self.create_text(self.winfo_reqwidth() // 2, self.winfo_reqheight() // 2,
                           text="Wybierz detal", fill="#666666", font=("Arial", 10))
            return
        
        contour = part_data.get('contour', [])
        if len(contour) < 3:
            self.create_text(self.winfo_reqwidth() // 2, self.winfo_reqheight() // 2,
                           text="Brak konturu", fill="#666666", font=("Arial", 10))
            return
        
        canvas_w = self.winfo_reqwidth() - 20
        canvas_h = self.winfo_reqheight() - 20
        
        width = part_data.get('width', 100)
        height = part_data.get('height', 100)
        
        scale_x = canvas_w / width if width > 0 else 1
        scale_y = canvas_h / height if height > 0 else 1
        scale = min(scale_x, scale_y) * 0.85
        
        offset_x = (canvas_w - width * scale) / 2 + 10
        offset_y = (canvas_h - height * scale) / 2 + 10
        
        points = []
        for x, y in contour:
            cx = offset_x + x * scale
            cy = offset_y + (height - y) * scale
            points.extend([cx, cy])
        
        self.create_polygon(points, fill=color, outline="#ffffff", width=1.5)
        
        for hole in part_data.get('holes', []):
            if len(hole) >= 3:
                hole_points = []
                for x, y in hole:
                    hx = offset_x + x * scale
                    hy = offset_y + (height - y) * scale
                    hole_points.extend([hx, hy])
                self.create_polygon(hole_points, fill="#1a1a1a", outline="#666666", width=1)
        
        dims_text = f"{width:.1f} x {height:.1f} mm"
        self.create_text(canvas_w // 2 + 10, canvas_h - 5, text=dims_text, fill="#888888", font=("Arial", 8))


# ============================================================
# Single Sheet Canvas (jeden arkusz)
# ============================================================

class SheetCanvas(Canvas):
    """Canvas dla pojedynczego arkusza z zoom i interakcją"""
    
    def __init__(self, parent, sheet_index: int, sheet_width: float, sheet_height: float,
                 on_part_click: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg="#1a1a1a", highlightthickness=1,
                        highlightbackground="#444444", **kwargs)
        
        self.sheet_index = sheet_index
        self.sheet_width = sheet_width
        self.sheet_height = sheet_height
        self.placed_parts: List[Any] = []
        self.part_colors: Dict[str, str] = {}
        
        self.zoom_scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.is_panning = False
        self.last_x = 0
        self.last_y = 0
        
        self.on_part_click = on_part_click
        self.selected_part_name: Optional[str] = None
        
        # Binds
        self.bind("<ButtonPress-1>", self._on_click)
        self.bind("<ButtonPress-2>", self._start_pan)
        self.bind("<ButtonPress-3>", self._start_pan)
        self.bind("<B2-Motion>", self._pan)
        self.bind("<B3-Motion>", self._pan)
        self.bind("<ButtonRelease-2>", self._end_pan)
        self.bind("<ButtonRelease-3>", self._end_pan)
        self.bind("<MouseWheel>", self._zoom)
        self.bind("<Button-4>", lambda e: self._zoom(e, 1.1))
        self.bind("<Button-5>", lambda e: self._zoom(e, 0.9))
        self.bind("<Configure>", self._on_resize)
    
    def _on_click(self, event):
        """Obsłuż kliknięcie - znajdź detal"""
        if not self.placed_parts:
            return
        
        sheet_x, sheet_y = self._from_canvas(event.x, event.y)
        
        for i in range(len(self.placed_parts) - 1, -1, -1):
            part = self.placed_parts[i]
            if self._point_in_part(sheet_x, sheet_y, part):
                self.selected_part_name = part.name if hasattr(part, 'name') else None
                self.redraw()
                
                if self.on_part_click:
                    self.on_part_click(self.sheet_index, part)
                break
    
    def _from_canvas(self, cx: float, cy: float) -> Tuple[float, float]:
        x = (cx - self.offset_x) / self.zoom_scale
        y = self.sheet_height - (cy - self.offset_y) / self.zoom_scale
        return x, y
    
    def _point_in_part(self, x: float, y: float, part) -> bool:
        contour = part.get_placed_contour() if hasattr(part, 'get_placed_contour') else []
        if len(contour) < 3:
            px = part.x if hasattr(part, 'x') else 0
            py = part.y if hasattr(part, 'y') else 0
            pw = part.width if hasattr(part, 'width') else 0
            ph = part.height if hasattr(part, 'height') else 0
            return px <= x <= px + pw and py <= y <= py + ph
        
        n = len(contour)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = contour[i]
            xj, yj = contour[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside
    
    def select_part_by_name(self, part_name: str):
        """Zaznacz detal po nazwie"""
        self.selected_part_name = part_name
        self.redraw()
    
    def clear_selection(self):
        """Wyczyść zaznaczenie"""
        self.selected_part_name = None
        self.redraw()
    
    def set_parts(self, parts: List[Any], colors: Dict[str, str]):
        """Ustaw detale"""
        self.placed_parts = parts
        self.part_colors = colors
        # Upewnij się że canvas ma właściwe wymiary przed fit_view
        self.update_idletasks()
        self._fit_view()
        self.redraw()
        # Ponownie dopasuj widok po pełnym renderingu
        self.after(50, lambda: (self._fit_view(), self.redraw()))
    
    def _fit_view(self):
        canvas_w = self.winfo_width() or 300
        canvas_h = self.winfo_height() or 200
        
        scale_x = (canvas_w - 20) / self.sheet_width
        scale_y = (canvas_h - 20) / self.sheet_height
        self.zoom_scale = min(scale_x, scale_y)
        
        self.offset_x = (canvas_w - self.sheet_width * self.zoom_scale) / 2
        self.offset_y = (canvas_h - self.sheet_height * self.zoom_scale) / 2
    
    def _to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        cx = self.offset_x + x * self.zoom_scale
        cy = self.offset_y + (self.sheet_height - y) * self.zoom_scale
        return cx, cy
    
    def _start_pan(self, event):
        self.is_panning = True
        self.last_x = event.x
        self.last_y = event.y
    
    def _pan(self, event):
        if not self.is_panning:
            return
        dx = event.x - self.last_x
        dy = event.y - self.last_y
        self.offset_x += dx
        self.offset_y += dy
        self.last_x = event.x
        self.last_y = event.y
        self.redraw()
    
    def _end_pan(self, event):
        self.is_panning = False
    
    def _zoom(self, event, factor=None):
        if factor is None:
            factor = 1.1 if event.delta > 0 else 0.9
        
        old_scale = self.zoom_scale
        self.zoom_scale = max(0.05, min(self.zoom_scale * factor, 50))
        
        mouse_x = event.x
        mouse_y = event.y
        
        self.offset_x = mouse_x - (mouse_x - self.offset_x) * (self.zoom_scale / old_scale)
        self.offset_y = mouse_y - (mouse_y - self.offset_y) * (self.zoom_scale / old_scale)
        
        self.redraw()
    
    def zoom_in(self):
        """Powiększ widok (Zoom In)"""
        self.zoom_scale = min(self.zoom_scale * 1.2, 50)
        self.redraw()

    def zoom_out(self):
        """Pomniejsz widok (Zoom Out)"""
        self.zoom_scale = max(self.zoom_scale / 1.2, 0.05)
        self.redraw()

    def zoom_all(self):
        """Dopasuj widok do arkusza (Zoom All)"""
        self._fit_view()
        self.redraw()

    def zoom_fit(self):
        """Alias dla zoom_all (zgodność z CAD)"""
        self.zoom_all()

    def _on_resize(self, event):
        if not self.placed_parts:
            self._fit_view()
        self.redraw()

    def redraw(self):
        self.delete("all")
        
        # Ramka arkusza
        x1, y1 = self._to_canvas(0, 0)
        x2, y2 = self._to_canvas(self.sheet_width, self.sheet_height)
        
        self.create_rectangle(x1, y2, x2, y1, outline="#ffffff", width=2, fill="#2a2a2a")
        
        # Siatka
        grid_step = 100
        for gx in range(0, int(self.sheet_width) + 1, grid_step):
            cx, _ = self._to_canvas(gx, 0)
            _, cy1 = self._to_canvas(0, 0)
            _, cy2 = self._to_canvas(0, self.sheet_height)
            self.create_line(cx, cy1, cx, cy2, fill="#333333", width=1)
        
        for gy in range(0, int(self.sheet_height) + 1, grid_step):
            _, cy = self._to_canvas(0, gy)
            cx1, _ = self._to_canvas(0, 0)
            cx2, _ = self._to_canvas(self.sheet_width, 0)
            self.create_line(cx1, cy, cx2, cy, fill="#333333", width=1)
        
        # Detale
        for part in self.placed_parts:
            self._draw_part(part)
        
        # Numer arkusza
        self.create_text(x1 + 10, y2 + 15, text=f"Arkusz #{self.sheet_index + 1}",
                        fill="#888888", anchor="nw", font=("Arial", 10, "bold"))
    
    def _draw_part(self, part):
        name = part.name if hasattr(part, 'name') else ''
        color = self.part_colors.get(name, "#3B82F6")
        
        is_selected = (name == self.selected_part_name)
        outline_color = "#ffff00" if is_selected else "#ffffff"
        outline_width = 3 if is_selected else 1
        
        contour = part.get_placed_contour() if hasattr(part, 'get_placed_contour') else []
        
        if len(contour) >= 3:
            canvas_points = []
            for x, y in contour:
                cx, cy = self._to_canvas(x, y)
                canvas_points.extend([cx, cy])
            
            self.create_polygon(canvas_points, fill=color, outline=outline_color, width=outline_width)
        else:
            px = part.x if hasattr(part, 'x') else 0
            py = part.y if hasattr(part, 'y') else 0
            pw = part.width if hasattr(part, 'width') else 100
            ph = part.height if hasattr(part, 'height') else 100
            
            x1, y1 = self._to_canvas(px, py)
            x2, y2 = self._to_canvas(px + pw, py + ph)
            
            self.create_rectangle(x1, y1, x2, y2, fill=color, outline=outline_color, width=outline_width)
        
        # Otwory
        if hasattr(part, 'get_placed_holes'):
            for hole in part.get_placed_holes():
                if len(hole) >= 3:
                    hole_points = []
                    for x, y in hole:
                        cx, cy = self._to_canvas(x, y)
                        hole_points.extend([cx, cy])
                    self.create_polygon(hole_points, fill="#2a2a2a", outline="#666666", width=1)

    def export_to_image(self, width: int = 800, height: int = 600) -> bytes:
        """Eksportuj arkusz do obrazu PNG jako bytes"""
        try:
            from PIL import Image, ImageDraw

            # Oblicz skale dla eksportu
            scale_x = (width - 40) / self.sheet_width
            scale_y = (height - 40) / self.sheet_height
            export_scale = min(scale_x, scale_y)
            export_offset_x = (width - self.sheet_width * export_scale) / 2
            export_offset_y = (height - self.sheet_height * export_scale) / 2

            def to_export(x: float, y: float):
                ex = export_offset_x + x * export_scale
                ey = export_offset_y + (self.sheet_height - y) * export_scale
                return int(ex), int(ey)

            # Stworz obraz
            img = Image.new('RGB', (width, height), color=(26, 26, 26))
            draw = ImageDraw.Draw(img)

            # Ramka arkusza
            x1, y1 = to_export(0, 0)
            x2, y2 = to_export(self.sheet_width, self.sheet_height)
            draw.rectangle([x1, y2, x2, y1], outline='white', width=2, fill=(42, 42, 42))

            # Siatka
            grid_step = 100
            for gx in range(0, int(self.sheet_width) + 1, grid_step):
                cx, _ = to_export(gx, 0)
                _, cy1 = to_export(0, 0)
                _, cy2 = to_export(0, self.sheet_height)
                draw.line([(cx, cy1), (cx, cy2)], fill=(51, 51, 51), width=1)

            for gy in range(0, int(self.sheet_height) + 1, grid_step):
                _, cy = to_export(0, gy)
                cx1, _ = to_export(0, 0)
                cx2, _ = to_export(self.sheet_width, 0)
                draw.line([(cx1, cy), (cx2, cy)], fill=(51, 51, 51), width=1)

            # Detale
            for part in self.placed_parts:
                name = part.name if hasattr(part, 'name') else ''
                color_hex = self.part_colors.get(name, "#3B82F6")
                # Konwersja hex na RGB
                color = tuple(int(color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

                contour = part.get_placed_contour() if hasattr(part, 'get_placed_contour') else []

                if len(contour) >= 3:
                    points = [to_export(x, y) for x, y in contour]
                    draw.polygon(points, fill=color, outline='white')
                else:
                    px = part.x if hasattr(part, 'x') else 0
                    py = part.y if hasattr(part, 'y') else 0
                    pw = part.width if hasattr(part, 'width') else 100
                    ph = part.height if hasattr(part, 'height') else 100

                    ex1, ey1 = to_export(px, py)
                    ex2, ey2 = to_export(px + pw, py + ph)
                    draw.rectangle([ex1, ey1, ex2, ey2], fill=color, outline='white')

                # Otwory
                if hasattr(part, 'get_placed_holes'):
                    for hole in part.get_placed_holes():
                        if len(hole) >= 3:
                            hole_points = [to_export(x, y) for x, y in hole]
                            draw.polygon(hole_points, fill=(42, 42, 42), outline=(102, 102, 102))

            # Numer arkusza
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
                draw.text((x1 + 10, y2 + 5), f"Arkusz #{self.sheet_index + 1}",
                         fill=(136, 136, 136), font=font)
            except:
                pass

            # Zapisz do bytes
            import io
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return buffer.getvalue()

        except ImportError as e:
            logger.error(f"PIL not available for image export: {e}")
            return b''
        except Exception as e:
            logger.error(f"Error exporting sheet to image: {e}")
            return b''


# ============================================================
# Multi-Sheet Scrollable View
# ============================================================

class MultiSheetView(ctk.CTkFrame):
    """Przewijalna lista arkuszy wyświetlanych obok siebie"""

    def __init__(self, parent, sheet_width: float, sheet_height: float,
                 on_part_click: Optional[Callable] = None):
        super().__init__(parent, fg_color="transparent")

        self.sheet_width = sheet_width
        self.sheet_height = sheet_height
        self.on_part_click = on_part_click

        self.sheet_canvases: List[SheetCanvas] = []
        self.part_colors: Dict[str, str] = {}
        self.canvas_frames: List[ctk.CTkFrame] = []
        self.sheets_data: List[Any] = []
        self.all_parts: List[dict] = []

        self._setup_ui()

    def _setup_ui(self):
        # Scrollable frame dla arkuszy
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="#1a1a1a",
                                                    orientation="horizontal")
        self.scroll_frame.pack(fill="both", expand=True)

        # Binduj resize do aktualizacji wysokości canvasów
        self.bind("<Configure>", self._on_resize)
    
    def set_results(self, sheets: List[Any], colors: Dict[str, str], all_parts: List[dict] = None):
        """Ustaw wyniki nestingu (wiele arkuszy)"""
        self.part_colors = colors
        self.sheets_data = sheets
        self.all_parts = all_parts or []

        # Usuń stare canvas
        for canvas in self.sheet_canvases:
            canvas.destroy()
        self.sheet_canvases.clear()
        self.canvas_frames.clear()

        # Usuń stare frame'y
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # Oblicz dostępną wysokość dynamicznie
        self.update_idletasks()  # Upewnij się, że rozmiar jest aktualny
        available_height = self.winfo_height()

        # Jeśli jeszcze nie ma rozmiaru (pierwsze wywołanie), użyj domyślnej wartości
        if available_height <= 1:
            canvas_height = 400
        else:
            # Odejmij miejsce na padding i scroll bar
            canvas_height = max(200, available_height - 60)

        # Utwórz canvas dla każdego arkusza
        for i, sheet in enumerate(sheets):
            # Oblicz szerokość canvas proporcjonalnie do wysokości
            aspect = self.sheet_height / self.sheet_width if self.sheet_width > 0 else 0.5
            canvas_width = int(canvas_height / aspect) if aspect > 0 else 400
            canvas_width = min(canvas_width, 800)  # Max szerokość zwiększona z 600 na 800
            
            frame = ctk.CTkFrame(self.scroll_frame, fg_color="#252525", corner_radius=8)
            frame.pack(side="left", padx=5, pady=5)
            self.canvas_frames.append(frame)

            # Nagłówek
            header = ctk.CTkFrame(frame, fg_color="transparent", height=30)
            header.pack(fill="x", padx=5, pady=(5, 0))

            lbl_title = ctk.CTkLabel(header, text=f"Arkusz #{i+1}",
                                     font=ctk.CTkFont(size=12, weight="bold"))
            lbl_title.pack(side="left", padx=5)

            parts_count = len(sheet.placed_parts) if hasattr(sheet, 'placed_parts') else 0
            efficiency = sheet.efficiency if hasattr(sheet, 'efficiency') else 0

            lbl_info = ctk.CTkLabel(header, text=f"{parts_count} detali | {efficiency:.1%}",
                                    font=ctk.CTkFont(size=10), text_color="#888888")
            lbl_info.pack(side="right", padx=5)

            # Przycisk powiększenia
            btn_enlarge = ctk.CTkButton(header, text="🔍", width=30, height=25,
                                       fg_color=Theme.ACCENT_PRIMARY,
                                       command=lambda idx=i: self._open_sheet_detail(idx))
            btn_enlarge.pack(side="right", padx=2)
            
            # Canvas
            canvas = SheetCanvas(
                frame,
                sheet_index=i,
                sheet_width=self.sheet_width,
                sheet_height=self.sheet_height,
                on_part_click=self._handle_part_click,
                width=canvas_width,
                height=canvas_height
            )
            canvas.pack(padx=5, pady=5)
            
            # Ustaw detale
            parts = sheet.placed_parts if hasattr(sheet, 'placed_parts') else []
            canvas.set_parts(parts, colors)
            
            self.sheet_canvases.append(canvas)
    
    def _handle_part_click(self, sheet_index: int, part):
        """Obsłuż kliknięcie na detal"""
        # Zaznacz na tym arkuszu, odznacz na innych
        part_name = part.name if hasattr(part, 'name') else None
        for i, canvas in enumerate(self.sheet_canvases):
            if i == sheet_index:
                canvas.select_part_by_name(part_name)
            else:
                canvas.clear_selection()
        
        if self.on_part_click:
            self.on_part_click(sheet_index, part)
    
    def highlight_part(self, part_name: str, sheet_index: Optional[int] = None):
        """Podświetl detal po nazwie"""
        if sheet_index is not None and 0 <= sheet_index < len(self.sheet_canvases):
            # Zaznacz na konkretnym arkuszu
            for i, canvas in enumerate(self.sheet_canvases):
                if i == sheet_index:
                    canvas.select_part_by_name(part_name)
                else:
                    canvas.clear_selection()
        else:
            # Znajdź arkusz z tym detalem
            for canvas in self.sheet_canvases:
                for part in canvas.placed_parts:
                    if hasattr(part, 'name') and part.name == part_name:
                        canvas.select_part_by_name(part_name)
                        return
    
    def clear_selection(self):
        """Wyczyść zaznaczenie na wszystkich arkuszach"""
        for canvas in self.sheet_canvases:
            canvas.clear_selection()

    def _on_resize(self, event):
        """Aktualizuj wysokości canvasów przy zmianie rozmiaru"""
        # Ignoruj jeśli to nie zmiana rozmiaru całego frame'a
        if event.widget != self:
            return

        # Oblicz dostępną wysokość (odejmij margines dla scroll bara)
        available_height = self.winfo_height() - 60  # 60px zapas na scroll bar i padding

        if available_height < 100:
            return  # Za mało miejsca

        # Zaktualizuj wysokość wszystkich canvasów
        for canvas in self.sheet_canvases:
            canvas.configure(height=available_height)
            canvas._fit_view()
            canvas.redraw()

    def _open_sheet_detail(self, sheet_index: int):
        """Otwórz szczegółowe okno dla arkusza"""
        if 0 <= sheet_index < len(self.sheets_data):
            sheet_data = self.sheets_data[sheet_index]

            detail_window = SheetDetailWindow(
                self.winfo_toplevel(),
                sheet_index=sheet_index,
                sheet_data=sheet_data,
                sheet_width=self.sheet_width,
                sheet_height=self.sheet_height,
                all_parts=self.all_parts,
                part_colors=self.part_colors
            )


# ============================================================
# Sheet Detail Window (powiększone okno pojedynczego arkusza)
# ============================================================

class SheetDetailWindow(ctk.CTkToplevel):
    """Okno szczegółowe dla pojedynczego arkusza z listą detali"""

    def __init__(self, parent, sheet_index: int, sheet_data: Any,
                 sheet_width: float, sheet_height: float,
                 all_parts: List[dict], part_colors: Dict[str, str],
                 dynamics_settings: MachineDynamicsSettings = None):
        super().__init__(parent)

        self.sheet_index = sheet_index
        self.sheet_data = sheet_data
        self.sheet_width = sheet_width
        self.sheet_height = sheet_height
        self.all_parts = all_parts
        self.part_colors = part_colors
        self.dynamics_settings = dynamics_settings or MachineDynamicsSettings()

        # Konfiguracja okna - 75% rozmiaru ekranu
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = int(screen_w * 0.75)
        win_h = int(screen_h * 0.75)

        self.title(f"Arkusz #{sheet_index + 1} - Szczegóły")
        self.geometry(f"{win_w}x{win_h}")
        self.configure(fg_color=Theme.BG_DARK)

        # Wyśrodkuj okno
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.geometry(f"+{x}+{y}")

        self._setup_ui()

        # Ustawienia okna
        self.attributes('-topmost', True)  # Okno na pierwszym planie
        self.focus_set()

    def _setup_ui(self):
        """Buduj interfejs okna"""
        self.grid_columnconfigure(0, weight=0)  # Lista detali
        self.grid_columnconfigure(1, weight=1)  # Canvas arkusza
        self.grid_rowconfigure(0, weight=1)

        # === LEWY PANEL - Lista detali ===
        left_panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, width=438)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_panel.grid_propagate(False)

        # Nagłówek
        placed_parts = self.sheet_data.placed_parts if hasattr(self.sheet_data, 'placed_parts') else []
        efficiency = self.sheet_data.efficiency if hasattr(self.sheet_data, 'efficiency') else 0

        title = ctk.CTkLabel(left_panel,
                            text=f"📋 Detale na arkuszu ({len(placed_parts)})",
                            font=ctk.CTkFont(size=14, weight="bold"))
        title.pack(pady=(10, 5), padx=10, anchor="w")

        stats_text = f"Efektywność: {efficiency:.1%}"
        stats_label = ctk.CTkLabel(left_panel, text=stats_text,
                                   font=ctk.CTkFont(size=11), text_color=Theme.ACCENT_INFO)
        stats_label.pack(pady=(0, 10), padx=10, anchor="w")

        # Wyszukiwarka
        search_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(search_frame, text="🔍 Szukaj:",
                    font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 5))

        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="nazwa detalu...")
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search)

        # Lista detali
        tree_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Style
        style = ttk.Style()
        style.configure("DetailWindow.Treeview", background="#1a1a1a",
                       foreground="white", fieldbackground="#1a1a1a", rowheight=30)
        style.map("DetailWindow.Treeview", background=[("selected", "#8b5cf6")])

        self.tree = ttk.Treeview(tree_frame, columns=("name", "dims", "position"),
                                show="headings", height=15, style="DetailWindow.Treeview")
        self.tree.heading("name", text="Nazwa")
        self.tree.heading("dims", text="Wymiary")
        self.tree.heading("position", text="Pozycja (x, y)")
        self.tree.column("name", width=140)
        self.tree.column("dims", width=80, anchor="center")
        self.tree.column("position", width=100, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Wypełnij listę
        for i, part in enumerate(placed_parts):
            name = part.name if hasattr(part, 'name') else f'Part_{i}'
            w = part.width if hasattr(part, 'width') else 0
            h = part.height if hasattr(part, 'height') else 0
            px = part.x if hasattr(part, 'x') else 0
            py = part.y if hasattr(part, 'y') else 0

            dims = f"{w:.0f}×{h:.0f}"
            pos = f"({px:.0f}, {py:.0f})"

            self.tree.insert("", "end", iid=f"part_{i}",
                           values=(name, dims, pos))

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Podgląd detalu
        preview_label = ctk.CTkLabel(left_panel, text="Podgląd detalu",
                                     font=ctk.CTkFont(size=12))
        preview_label.pack(pady=(10, 5), padx=10, anchor="w")

        self.part_preview = PartPreviewCanvas(left_panel, width=388, height=180)
        self.part_preview.pack(padx=10, pady=5)

        self.lbl_part_info = ctk.CTkLabel(left_panel, text="Wybierz detal z listy",
                                         font=ctk.CTkFont(size=10),
                                         text_color=Theme.TEXT_MUTED)
        self.lbl_part_info.pack(pady=5)

        # Velocity profile
        velocity_label = ctk.CTkLabel(left_panel, text="Profil prędkości",
                                      font=ctk.CTkFont(size=11), text_color=Theme.TEXT_SECONDARY)
        velocity_label.pack(pady=(5, 2), padx=10, anchor="w")

        self.velocity_profile = VelocityProfileCanvas(left_panel, width=388, height=55)
        self.velocity_profile.pack(padx=10, pady=(0, 5))
        self.velocity_profile.clear()

        # === PRAWY PANEL - Canvas arkusza ===
        right_panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

        # Toolbar
        toolbar = ctk.CTkFrame(right_panel, fg_color="transparent", height=50)
        toolbar.pack(fill="x", padx=10, pady=10)

        lbl_title = ctk.CTkLabel(toolbar,
                                text=f"Arkusz #{self.sheet_index + 1}",
                                font=ctk.CTkFont(size=16, weight="bold"))
        lbl_title.pack(side="left", padx=10)

        lbl_dims = ctk.CTkLabel(toolbar,
                               text=f"{self.sheet_width:.0f} × {self.sheet_height:.0f} mm",
                               font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY)
        lbl_dims.pack(side="left", padx=10)

        # Przyciski zoom
        btn_zoom_in = ctk.CTkButton(toolbar, text="🔍+", width=40, height=40,
                                   font=ctk.CTkFont(size=16),
                                   command=self._zoom_in,
                                   fg_color=Theme.BG_INPUT,
                                   hover_color=Theme.ACCENT_PRIMARY)
        btn_zoom_in.pack(side="left", padx=2)
        self._create_tooltip(btn_zoom_in, "Powiększ (Zoom In)")

        btn_zoom_out = ctk.CTkButton(toolbar, text="🔍−", width=40, height=40,
                                    font=ctk.CTkFont(size=16),
                                    command=self._zoom_out,
                                    fg_color=Theme.BG_INPUT,
                                    hover_color=Theme.ACCENT_PRIMARY)
        btn_zoom_out.pack(side="left", padx=2)
        self._create_tooltip(btn_zoom_out, "Pomniejsz (Zoom Out)")

        btn_zoom_all = ctk.CTkButton(toolbar, text="⊡", width=40, height=40,
                                    font=ctk.CTkFont(size=18),
                                    command=self._zoom_all,
                                    fg_color=Theme.BG_INPUT,
                                    hover_color=Theme.ACCENT_PRIMARY)
        btn_zoom_all.pack(side="left", padx=2)
        self._create_tooltip(btn_zoom_all, "Dopasuj widok (Zoom All)")

        btn_zoom_fit = ctk.CTkButton(toolbar, text="⊞", width=40, height=40,
                                    font=ctk.CTkFont(size=18),
                                    command=self._zoom_fit,
                                    fg_color=Theme.BG_INPUT,
                                    hover_color=Theme.ACCENT_PRIMARY)
        btn_zoom_fit.pack(side="left", padx=2)
        self._create_tooltip(btn_zoom_fit, "Dopasuj do arkusza (Zoom Fit)")

        btn_close = ctk.CTkButton(toolbar, text="✕ Zamknij",
                                 command=self.destroy, width=100,
                                 fg_color=Theme.ACCENT_DANGER)
        btn_close.pack(side="right", padx=5)

        # Canvas
        canvas_frame = ctk.CTkFrame(right_panel, fg_color="#1a1a1a")
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.sheet_canvas = SheetCanvas(
            canvas_frame,
            sheet_index=self.sheet_index,
            sheet_width=self.sheet_width,
            sheet_height=self.sheet_height,
            on_part_click=self._on_canvas_part_click
        )
        self.sheet_canvas.pack(fill="both", expand=True, padx=5, pady=5)

        # Ustaw detale
        self.sheet_canvas.set_parts(placed_parts, self.part_colors)

        # Wywołaj Zoom All po załadowaniu arkusza (gwarantuje prawidłowe dopasowanie)
        self.after(150, self._zoom_all)

    def _on_search(self, event):
        """Filtruj listę detali według wyszukiwanego tekstu"""
        search_text = self.search_entry.get().lower()

        # Wyczyść listę
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Odfiltruj i dodaj ponownie
        placed_parts = self.sheet_data.placed_parts if hasattr(self.sheet_data, 'placed_parts') else []
        for i, part in enumerate(placed_parts):
            name = part.name if hasattr(part, 'name') else f'Part_{i}'

            if search_text in name.lower():
                w = part.width if hasattr(part, 'width') else 0
                h = part.height if hasattr(part, 'height') else 0
                px = part.x if hasattr(part, 'x') else 0
                py = part.y if hasattr(part, 'y') else 0

                dims = f"{w:.0f}×{h:.0f}"
                pos = f"({px:.0f}, {py:.0f})"

                self.tree.insert("", "end", iid=f"part_{i}",
                               values=(name, dims, pos))

    def _on_tree_select(self, event):
        """Obsłuż wybór detalu z listy"""
        selection = self.tree.selection()
        if not selection:
            return

        try:
            item = selection[0]
            idx = int(item.split("_")[1])

            placed_parts = self.sheet_data.placed_parts if hasattr(self.sheet_data, 'placed_parts') else []
            if 0 <= idx < len(placed_parts):
                part = placed_parts[idx]
                name = part.name if hasattr(part, 'name') else ''

                # Znajdź dane detalu w oryginalnej liście
                part_data = None
                for p in self.all_parts:
                    if p.get('name', '') == name:
                        part_data = p
                        break

                if part_data:
                    color = self.part_colors.get(name, "#3B82F6")
                    self.part_preview.set_part(part_data, color)

                    w = part_data.get('width', 0)
                    h = part_data.get('height', 0)
                    px = part.x if hasattr(part, 'x') else 0
                    py = part.y if hasattr(part, 'y') else 0

                    self.lbl_part_info.configure(
                        text=f"{name}\n{w:.1f} × {h:.1f} mm\nPozycja: ({px:.0f}, {py:.0f})"
                    )

                    # Calculate and show velocity profile
                    filepath = part_data.get('filepath', '')
                    v_max_mm_s = 83.3  # Default: 5 m/min
                    if HAS_MOTION_DYNAMICS:
                        v_max_mm_s = m_min_to_mm_s(5.0)
                    if hasattr(self, 'velocity_profile'):
                        self.velocity_profile.calculate_from_dxf(
                            filepath,
                            self.dynamics_settings,
                            v_max_mm_s
                        )

                # Podświetl na canvasie
                self.sheet_canvas.select_part_by_name(name)
        except Exception as e:
            logger.error(f"Error in tree select: {e}")

    def _on_canvas_part_click(self, sheet_index: int, part):
        """Obsłuż kliknięcie na detal na canvasie"""
        placed_parts = self.sheet_data.placed_parts if hasattr(self.sheet_data, 'placed_parts') else []

        for i, p in enumerate(placed_parts):
            if p == part:
                item_id = f"part_{i}"
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)
                self.tree.see(item_id)
                break

    def _zoom_in(self):
        """Obsługa przycisku Zoom In"""
        self.sheet_canvas.zoom_in()

    def _zoom_out(self):
        """Obsługa przycisku Zoom Out"""
        self.sheet_canvas.zoom_out()

    def _zoom_all(self):
        """Obsługa przycisku Zoom All"""
        self.sheet_canvas.zoom_all()

    def _zoom_fit(self):
        """Obsługa przycisku Zoom Fit"""
        self.sheet_canvas.zoom_fit()

    def _create_tooltip(self, widget, text):
        """Tworzy tooltip dla widgetu"""
        import tkinter as tk

        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

            label = tk.Label(
                tooltip,
                text=text,
                background="#333333",
                foreground="#ffffff",
                relief="solid",
                borderwidth=1,
                font=("Helvetica", 9),
                padx=8,
                pady=4
            )
            label.pack()

            widget._tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, '_tooltip'):
                widget._tooltip.destroy()
                del widget._tooltip

        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)


# ============================================================
# Single Nesting Tab
# ============================================================

class NestingTab(ctk.CTkFrame):
    """Pojedyncza zakładka nestingu dla kombinacji materiał+grubość"""

    def __init__(self, parent, material: str, thickness: float,
                 parts: List[dict], sheet_formats: List[Tuple[float, float]],
                 on_nesting_complete: Optional[Callable] = None,
                 dynamics_settings: MachineDynamicsSettings = None):
        super().__init__(parent, fg_color=Theme.BG_DARK)

        self.material = material
        self.thickness = thickness
        self.parts = parts
        self.sheet_formats = sheet_formats
        self.on_nesting_complete = on_nesting_complete
        self.dynamics_settings = dynamics_settings or MachineDynamicsSettings()

        self.nester = None
        self.nesting_result = None
        self.nesting_thread = None

        # Time comparison data
        self.time_classic_s = 0.0
        self.time_dynamic_s = 0.0

        # Mapowanie nazwa -> kolor
        self.part_colors: Dict[str, str] = {}
        for i, p in enumerate(parts):
            name = p.get('name', f'Part_{i}')
            self.part_colors[name] = PART_COLORS[i % len(PART_COLORS)]

        # Śledzenie statusu detali
        self.placed_parts_names: Set[str] = set()
        self.unplaced_parts_names: Set[str] = set()

        # Mapowanie nazwa -> sheet_index (dla znalezionych detali)
        self.part_sheet_map: Dict[str, int] = {}

        # Parts list collapse state
        self._parts_list_collapsed = False

        self._setup_ui()
    
    def _setup_ui(self):
        """Buduj interfejs zakładki"""
        self.grid_columnconfigure(0, weight=0)  # Lista detali
        self.grid_columnconfigure(1, weight=1)  # Arkusze
        self.grid_rowconfigure(0, weight=1)
        
        # === LEWY PANEL ===
        self.left_panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, width=320)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.left_panel.grid_propagate(False)

        # Header z przyciskiem zwijania
        header_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Tytuł
        self.lbl_parts_title = ctk.CTkLabel(header_frame, text=f"📋 Detale ({len(self.parts)})",
                            font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_parts_title.pack(side="left")

        # Przycisk zwijania
        self.btn_collapse = ctk.CTkButton(
            header_frame,
            text="◀",
            width=25,
            height=25,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._toggle_parts_list
        )
        self.btn_collapse.pack(side="right")

        # Container dla zawartości (do zwijania)
        self.parts_content = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.parts_content.pack(fill="both", expand=True)

        # Lista detali
        tree_frame = ctk.CTkFrame(self.parts_content, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Style dla kolorów tła
        style = ttk.Style()
        style.configure("Treeview", background="#1a1a1a", foreground="white",
                       fieldbackground="#1a1a1a", rowheight=25)
        style.map("Treeview", background=[("selected", "#8b5cf6")])
        
        self.tree = ttk.Treeview(tree_frame, columns=("name", "dims", "qty", "status"),
                                  show="headings", height=12)
        self.tree.heading("name", text="Nazwa")
        self.tree.heading("dims", text="Wymiary")
        self.tree.heading("qty", text="Ilość")
        self.tree.heading("status", text="Status")
        self.tree.column("name", width=120)
        self.tree.column("dims", width=70, anchor="center")
        self.tree.column("qty", width=40, anchor="center")
        self.tree.column("status", width=50, anchor="center")
        
        # Tagi dla kolorów
        self.tree.tag_configure("placed", background="#1c3a1c")
        self.tree.tag_configure("unplaced", background="#4a1c1c")
        self.tree.tag_configure("pending", background="#1a1a1a")
        
        self.tree.pack(fill="both", expand=True)
        
        # Wypełnij listę
        for i, p in enumerate(self.parts):
            name = p.get('name', f'Part_{i}')
            dims = f"{p.get('width', 0):.0f}x{p.get('height', 0):.0f}"
            qty = p.get('quantity', 1)
            self.tree.insert("", "end", iid=f"part_{i}", values=(name, dims, qty, "⏳"), tags=("pending",))
        
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._edit_quantity)
        
        # Podgląd detalu
        preview_label = ctk.CTkLabel(self.parts_content, text="Podgląd detalu",
                                     font=ctk.CTkFont(size=12))
        preview_label.pack(pady=(10, 5), padx=10, anchor="w")

        self.part_preview = PartPreviewCanvas(self.parts_content, width=280, height=120)
        self.part_preview.pack(padx=10, pady=5)

        self.lbl_part_info = ctk.CTkLabel(self.parts_content, text="Wybierz detal z listy",
                                          font=ctk.CTkFont(size=10), text_color=Theme.TEXT_MUTED)
        self.lbl_part_info.pack(pady=5)

        # Velocity profile
        velocity_label = ctk.CTkLabel(self.parts_content, text="Profil prędkości",
                                      font=ctk.CTkFont(size=11), text_color=Theme.TEXT_SECONDARY)
        velocity_label.pack(pady=(5, 2), padx=10, anchor="w")

        self.velocity_profile = VelocityProfileCanvas(self.parts_content, width=280, height=55)
        self.velocity_profile.pack(padx=10, pady=(0, 5))
        self.velocity_profile.clear()
        
        # === PRAWY PANEL ===
        right_panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        
        # Toolbar
        toolbar = ctk.CTkFrame(right_panel, fg_color="transparent", height=50)
        toolbar.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(toolbar, text="Format arkusza:").pack(side="left", padx=(0, 5))
        
        format_values = [f"{int(f[0])}x{int(f[1])}" for f in self.sheet_formats]
        self.format_var = ctk.StringVar(value=format_values[0] if format_values else "3000x1500")
        self.format_combo = ctk.CTkComboBox(toolbar, values=format_values,
                                            variable=self.format_var, width=120)
        self.format_combo.pack(side="left", padx=5)
        
        ctk.CTkLabel(toolbar, text="Odstęp:").pack(side="left", padx=(20, 5))
        self.spacing_entry = ctk.CTkEntry(toolbar, width=50)
        self.spacing_entry.insert(0, "5")
        self.spacing_entry.pack(side="left", padx=5)
        ctk.CTkLabel(toolbar, text="mm").pack(side="left")
        
        self.deep_var = ctk.BooleanVar(value=True)
        self.deep_check = ctk.CTkCheckBox(toolbar, text="🔬 Głęboka analiza",
                                          variable=self.deep_var)
        self.deep_check.pack(side="left", padx=20)
        
        self.btn_start = ctk.CTkButton(toolbar, text="▶ Start Nesting",
                                       command=self.start_nesting,
                                       fg_color=Theme.ACCENT_SUCCESS, width=120)
        self.btn_start.pack(side="right", padx=5)
        
        self.btn_export = ctk.CTkButton(toolbar, text="💾 Eksport DXF",
                                        command=self.export_dxf,
                                        fg_color=Theme.ACCENT_INFO, width=100,
                                        state="disabled")
        self.btn_export.pack(side="right", padx=5)
        
        # Multi-sheet view
        self.multi_sheet_view = MultiSheetView(
            right_panel,
            sheet_width=3000,
            sheet_height=1500,
            on_part_click=self._on_sheet_part_click
        )
        self.multi_sheet_view.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Statusbar - rozbudowany z porównaniem metod
        status_frame = ctk.CTkFrame(right_panel, fg_color=Theme.BG_INPUT, height=90)
        status_frame.pack(fill="x", padx=10, pady=(0, 10))
        status_frame.pack_propagate(False)

        # Górna linia statusu
        status_top = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_top.pack(fill="x", padx=10, pady=(5, 0))

        self.lbl_status = ctk.CTkLabel(status_top, text="Gotowy do nestingu",
                                       font=ctk.CTkFont(size=11), width=250, anchor="w")
        self.lbl_status.pack(side="left")

        self.progress = ctk.CTkProgressBar(status_top, width=450)
        self.progress.pack(side="left", padx=15)
        self.progress.set(0)

        self.lbl_sheets = ctk.CTkLabel(status_top, text="Arkusze: -",
                                       font=ctk.CTkFont(size=11), text_color=Theme.ACCENT_INFO)
        self.lbl_sheets.pack(side="right", padx=10)

        self.lbl_efficiency = ctk.CTkLabel(status_top, text="Efektywność: -",
                                           font=ctk.CTkFont(size=11, weight="bold"),
                                           text_color=Theme.ACCENT_PRIMARY)
        self.lbl_efficiency.pack(side="right", padx=10)

        # Panel porównania metod wyceny
        self.comparison_panel = ctk.CTkFrame(status_frame, fg_color=Theme.BG_CARD)
        self.comparison_panel.pack(fill="x", padx=5, pady=5)

        # Kolumna METODA KLASYCZNA
        classic_frame = ctk.CTkFrame(self.comparison_panel, fg_color="transparent")
        classic_frame.pack(side="left", fill="both", expand=True, padx=5, pady=3)

        ctk.CTkLabel(classic_frame, text="METODA KLASYCZNA",
                    font=ctk.CTkFont(size=9, weight="bold"),
                    text_color=Theme.TEXT_MUTED).pack(anchor="w")

        self.lbl_classic_time = ctk.CTkLabel(classic_frame, text="Czas: -",
                    font=ctk.CTkFont(size=10), text_color=Theme.TEXT_SECONDARY)
        self.lbl_classic_time.pack(anchor="w")

        self.lbl_classic_cost = ctk.CTkLabel(classic_frame, text="Koszt: -",
                    font=ctk.CTkFont(size=10, weight="bold"), text_color=Theme.ACCENT_WARNING)
        self.lbl_classic_cost.pack(anchor="w")

        # Separator pionowy
        ctk.CTkFrame(self.comparison_panel, width=1, fg_color=Theme.TEXT_MUTED).pack(side="left", fill="y", padx=5, pady=3)

        # Kolumna METODA DYNAMICZNA
        dynamic_frame = ctk.CTkFrame(self.comparison_panel, fg_color="transparent")
        dynamic_frame.pack(side="left", fill="both", expand=True, padx=5, pady=3)

        ctk.CTkLabel(dynamic_frame, text="METODA DYNAMICZNA",
                    font=ctk.CTkFont(size=9, weight="bold"),
                    text_color=Theme.TEXT_MUTED).pack(anchor="w")

        self.lbl_dynamic_time = ctk.CTkLabel(dynamic_frame, text="Czas: -",
                    font=ctk.CTkFont(size=10), text_color=Theme.TEXT_SECONDARY)
        self.lbl_dynamic_time.pack(anchor="w")

        self.lbl_dynamic_cost = ctk.CTkLabel(dynamic_frame, text="Koszt: -",
                    font=ctk.CTkFont(size=10, weight="bold"), text_color=Theme.ACCENT_SUCCESS)
        self.lbl_dynamic_cost.pack(anchor="w")

        # Separator pionowy
        ctk.CTkFrame(self.comparison_panel, width=1, fg_color=Theme.TEXT_MUTED).pack(side="left", fill="y", padx=5, pady=3)

        # Kolumna RÓŻNICA
        diff_frame = ctk.CTkFrame(self.comparison_panel, fg_color="transparent")
        diff_frame.pack(side="left", fill="both", expand=True, padx=5, pady=3)

        ctk.CTkLabel(diff_frame, text="RÓŻNICA",
                    font=ctk.CTkFont(size=9, weight="bold"),
                    text_color=Theme.TEXT_MUTED).pack(anchor="w")

        self.lbl_diff_time = ctk.CTkLabel(diff_frame, text="Czas: -",
                    font=ctk.CTkFont(size=10), text_color=Theme.ACCENT_DANGER)
        self.lbl_diff_time.pack(anchor="w")

        self.lbl_diff_cost = ctk.CTkLabel(diff_frame, text="Koszt: -",
                    font=ctk.CTkFont(size=10, weight="bold"), text_color=Theme.ACCENT_DANGER)
        self.lbl_diff_cost.pack(anchor="w")

        # Przycisk eksportu raportu
        self.btn_report = ctk.CTkButton(
            self.comparison_panel, text="📊 Raport MD",
            width=90, height=28,
            font=ctk.CTkFont(size=10),
            fg_color=Theme.ACCENT_INFO,
            command=self._export_report,
            state="disabled"
        )
        self.btn_report.pack(side="right", padx=10, pady=5)

        # Kompatybilność wsteczna
        self.lbl_time_comparison = ctk.CTkLabel(status_frame, text="")
        # Nie pakujemy go - tylko dla kompatybilności
    
    def _on_tree_select(self, event):
        """Obsłuż wybór detalu z listy"""
        selection = self.tree.selection()
        if not selection:
            return

        try:
            item = selection[0]
            idx = int(item.split("_")[1])

            if 0 <= idx < len(self.parts):
                part_data = self.parts[idx]
                name = part_data.get('name', '')
                color = self.part_colors.get(name, PART_COLORS[idx % len(PART_COLORS)])
                self.part_preview.set_part(part_data, color)

                w = part_data.get('width', 0)
                h = part_data.get('height', 0)

                # Status info
                if name in self.placed_parts_names:
                    sheet_idx = self.part_sheet_map.get(name, 0)
                    status_text = f"✓ Arkusz #{sheet_idx + 1}"
                elif name in self.unplaced_parts_names:
                    status_text = "✗ Nieznestowany"
                else:
                    status_text = ""

                self.lbl_part_info.configure(text=f"{name}\n{w:.1f} x {h:.1f} mm\n{status_text}")

                # Calculate and show velocity profile
                filepath = part_data.get('filepath', '')
                v_max_mm_s = m_min_to_mm_s(self._get_cutting_speed()) if HAS_MOTION_DYNAMICS else 83.3
                if hasattr(self, 'velocity_profile'):
                    self.velocity_profile.calculate_from_dxf(
                        filepath,
                        self.dynamics_settings,
                        v_max_mm_s
                    )

                # Podświetl na arkuszach
                if name in self.placed_parts_names:
                    sheet_idx = self.part_sheet_map.get(name)
                    self.multi_sheet_view.highlight_part(name, sheet_idx)
                else:
                    self.multi_sheet_view.clear_selection()

        except Exception as e:
            logger.error(f"Error in tree select: {e}")
    
    def _on_sheet_part_click(self, sheet_index: int, part):
        """Obsłuż kliknięcie na detal na arkuszu"""
        part_name = part.name if hasattr(part, 'name') else ''

        # Znajdź na liście i zaznacz
        for i, p in enumerate(self.parts):
            if p.get('name', '') == part_name:
                item_id = f"part_{i}"
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)
                self.tree.see(item_id)

                color = self.part_colors.get(part_name, PART_COLORS[i % len(PART_COLORS)])
                self.part_preview.set_part(p, color)

                w = p.get('width', 0)
                h = p.get('height', 0)
                self.lbl_part_info.configure(text=f"{part_name}\n{w:.1f} x {h:.1f} mm\n✓ Arkusz #{sheet_index + 1}")

                # Show velocity profile
                filepath = p.get('filepath', '')
                v_max_mm_s = m_min_to_mm_s(self._get_cutting_speed()) if HAS_MOTION_DYNAMICS else 83.3
                if hasattr(self, 'velocity_profile'):
                    self.velocity_profile.calculate_from_dxf(
                        filepath,
                        self.dynamics_settings,
                        v_max_mm_s
                    )
                break
    
    def _edit_quantity(self, event):
        """Edycja ilości przez podwójne kliknięcie"""
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        col = self.tree.identify_column(event.x)

        if col != "#3":
            return

        try:
            idx = int(item.split("_")[1])
        except:
            return

        x, y, w, h = self.tree.bbox(item, col)

        current_qty = self.parts[idx].get('quantity', 1)

        entry = ctk.CTkEntry(self.tree.master, width=50)
        entry.insert(0, str(current_qty))
        entry.place(x=x, y=y)
        entry.focus()

        def save(e=None):
            try:
                new_qty = int(entry.get())
                if new_qty > 0:
                    self.parts[idx]['quantity'] = new_qty
                    self.tree.set(item, "qty", str(new_qty))
            except:
                pass
            entry.destroy()
            # Expand parts list when quantity changed
            self.expand_parts_list()

        entry.bind("<Return>", save)
        entry.bind("<FocusOut>", save)

    def _toggle_parts_list(self):
        """Zwiń/rozwiń listę detali."""
        if self._parts_list_collapsed:
            self.expand_parts_list()
        else:
            self.collapse_parts_list()

    def collapse_parts_list(self):
        """Zwiń listę detali."""
        if self._parts_list_collapsed:
            return

        self._parts_list_collapsed = True
        self.parts_content.pack_forget()
        self.left_panel.configure(width=50)
        self.btn_collapse.configure(text="▶")
        self.lbl_parts_title.configure(text="📋")

    def expand_parts_list(self):
        """Rozwiń listę detali."""
        if not self._parts_list_collapsed:
            return

        self._parts_list_collapsed = False
        self.left_panel.configure(width=320)
        self.parts_content.pack(fill="both", expand=True)
        self.btn_collapse.configure(text="◀")
        self.lbl_parts_title.configure(text=f"📋 Detale ({len(self.parts)})")
    
    def start_nesting(self):
        """Rozpocznij nesting"""
        format_str = self.format_var.get()
        try:
            w, h = map(float, format_str.split('x'))
        except:
            w, h = 3000, 1500
        
        try:
            spacing = float(self.spacing_entry.get())
        except:
            spacing = 5.0
        
        from quotations.nesting.fast_nester import FastNester
        
        sheet_w = min(w, h)
        sheet_h = max(w, h)
        
        self.nester = FastNester(sheet_w, sheet_h, spacing)
        
        # Aktualizuj multi_sheet_view
        self.multi_sheet_view.sheet_width = sheet_w
        self.multi_sheet_view.sheet_height = sheet_h
        
        for p in self.parts:
            self.nester.add_part_from_dict(p, quantity=p.get('quantity', 1))
        
        if not self.nester.parts:
            messagebox.showerror("Błąd", "Brak detali do nestingu")
            return
        
        # Reset statusów
        self.placed_parts_names.clear()
        self.unplaced_parts_names.clear()
        self.part_sheet_map.clear()
        
        # Reset tagów na liście
        for item in self.tree.get_children():
            self.tree.item(item, tags=("pending",))
            self.tree.set(item, "status", "⏳")
        
        self.btn_start.configure(state="disabled")
        self.btn_export.configure(state="disabled")
        self.lbl_status.configure(text="Nesting w toku...")
        self.progress.set(0.1)
        
        deep = self.deep_var.get()
        
        def run():
            result = self.nester.run_nesting(callback=self._update_view, deep_analysis=deep)
            self.after(0, lambda: self._finish_nesting(result))
        
        self.nesting_thread = threading.Thread(target=run, daemon=True)
        self.nesting_thread.start()
    
    def _update_view(self, parts, efficiency: float):
        """Callback z nestera"""
        self.after(0, lambda: self._redraw(parts, efficiency))
    
    def _redraw(self, parts, efficiency: float):
        """Przerysuj podczas nestingu"""
        self.lbl_efficiency.configure(text=f"Efektywność: {efficiency:.1%}")
        self.progress.set(0.5 + efficiency * 0.5)
    
    def _finish_nesting(self, result):
        """Zakończ nesting"""
        self.nesting_result = result

        # Aktualizuj widok arkuszy
        if result.sheets:
            self.multi_sheet_view.set_results(result.sheets, self.part_colors, self.parts)

        # Zbierz informacje o statusach
        self.placed_parts_names.clear()
        self.unplaced_parts_names.clear()
        self.part_sheet_map.clear()

        for sheet in result.sheets:
            for part in sheet.placed_parts:
                name = part.name if hasattr(part, 'name') else ''
                self.placed_parts_names.add(name)
                self.part_sheet_map[name] = part.sheet_index if hasattr(part, 'sheet_index') else 0

        for up in result.unplaced_parts:
            self.unplaced_parts_names.add(up.name)

        # Aktualizuj listę
        for i, p in enumerate(self.parts):
            item_id = f"part_{i}"
            name = p.get('name', '')

            if name in self.placed_parts_names:
                sheet_idx = self.part_sheet_map.get(name, 0)
                self.tree.item(item_id, tags=("placed",))
                self.tree.set(item_id, "status", f"#{sheet_idx+1}")
            elif name in self.unplaced_parts_names:
                self.tree.item(item_id, tags=("unplaced",))
                self.tree.set(item_id, "status", "✗")
            else:
                self.tree.item(item_id, tags=("pending",))
                self.tree.set(item_id, "status", "?")

        self.btn_start.configure(state="normal")
        self.btn_export.configure(state="normal")

        # Calculate time comparison
        self._calculate_time_comparison()

        # Status
        placed_count = len(result.placed_parts)
        unplaced_count = result.unplaced_count
        sheets_count = result.sheets_used

        status_text = f"Gotowe! {placed_count} detali na {sheets_count} arkuszach"
        if unplaced_count > 0:
            status_text += f" | ⚠️ {unplaced_count} nieznestowanych"

        self.lbl_status.configure(text=status_text)
        self.lbl_sheets.configure(text=f"Arkusze: {sheets_count}")
        self.lbl_efficiency.configure(text=f"Efektywność: {result.total_efficiency:.1%}")

        # Display time comparison in new panel
        if self.time_classic_s > 0 or self.time_dynamic_s > 0:
            def format_time(seconds):
                if seconds >= 3600:
                    return f"{seconds/3600:.2f} h"
                elif seconds >= 60:
                    return f"{seconds/60:.1f} min"
                else:
                    return f"{seconds:.1f} s"

            # Oblicz koszty (zakładamy 300 PLN/h)
            machine_rate_pln_h = 300.0
            cost_classic = (self.time_classic_s / 3600) * machine_rate_pln_h
            cost_dynamic = (self.time_dynamic_s / 3600) * machine_rate_pln_h

            # Różnica
            time_diff = self.time_dynamic_s - self.time_classic_s
            cost_diff = cost_dynamic - cost_classic
            time_diff_pct = ((self.time_dynamic_s - self.time_classic_s) / self.time_classic_s * 100) if self.time_classic_s > 0 else 0

            # Aktualizuj labele METODA KLASYCZNA
            self.lbl_classic_time.configure(text=f"Czas: {format_time(self.time_classic_s)}")
            self.lbl_classic_cost.configure(text=f"Koszt: {cost_classic:.2f} PLN")

            # Aktualizuj labele METODA DYNAMICZNA
            self.lbl_dynamic_time.configure(text=f"Czas: {format_time(self.time_dynamic_s)}")
            self.lbl_dynamic_cost.configure(text=f"Koszt: {cost_dynamic:.2f} PLN")

            # Aktualizuj labele RÓŻNICA
            diff_sign = "+" if time_diff > 0 else ""
            self.lbl_diff_time.configure(text=f"Czas: {diff_sign}{format_time(abs(time_diff))} ({time_diff_pct:+.1f}%)")
            self.lbl_diff_cost.configure(text=f"Koszt: {diff_sign}{cost_diff:.2f} PLN")

            # Kolor różnicy
            diff_color = Theme.ACCENT_DANGER if time_diff > 0 else Theme.ACCENT_SUCCESS
            self.lbl_diff_time.configure(text_color=diff_color)
            self.lbl_diff_cost.configure(text_color=diff_color)

            # Aktywuj przycisk raportu
            self.btn_report.configure(state="normal")

            # Store for report generation
            self.cost_classic = cost_classic
            self.cost_dynamic = cost_dynamic
        else:
            self.lbl_classic_time.configure(text="Czas: -")
            self.lbl_classic_cost.configure(text="Koszt: -")
            self.lbl_dynamic_time.configure(text="Czas: -")
            self.lbl_dynamic_cost.configure(text="Koszt: -")
            self.lbl_diff_time.configure(text="Czas: -")
            self.lbl_diff_cost.configure(text="Koszt: -")

        self.progress.set(1.0)

        if self.on_nesting_complete:
            self.on_nesting_complete(self.material, self.thickness, result)
    
    def export_dxf(self):
        """Eksportuj wyniki do DXF"""
        if not self.nester or not self.nester.result:
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".dxf",
            filetypes=[("DXF Files", "*.dxf")],
            initialfile=f"nesting_{self.material}_{self.thickness}mm.dxf"
        )
        
        if filepath:
            saved = self.nester.export_all_dxf(filepath)
            if saved:
                messagebox.showinfo("Sukces", f"Zapisano {len(saved)} plików:\n" + "\n".join(os.path.basename(f) for f in saved))
            else:
                messagebox.showerror("Błąd", "Nie udało się zapisać plików")

    def export_images(self, width: int = 800, height: int = 600) -> List[bytes]:
        """Eksportuj wszystkie arkusze jako obrazy PNG (bytes)"""
        images = []
        if hasattr(self, 'multi_sheet_view') and self.multi_sheet_view:
            for canvas in self.multi_sheet_view.sheet_canvases:
                img_bytes = canvas.export_to_image(width, height)
                if img_bytes:
                    images.append(img_bytes)
        return images

    def _export_report(self):
        """Eksportuj raport porównania metod do pliku Markdown."""
        if not self.nesting_result:
            messagebox.showwarning("Uwaga", "Brak wyników nestingu do eksportu")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown Files", "*.md"), ("Text Files", "*.txt")],
            initialfile=f"raport_nesting_{self.material}_{self.thickness}mm.md"
        )

        if not filepath:
            return

        try:
            report = self._generate_markdown_report()
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
            messagebox.showinfo("Sukces", f"Raport zapisany:\n{filepath}")
        except Exception as e:
            logger.error(f"Error exporting report: {e}")
            messagebox.showerror("Błąd", f"Nie udało się zapisać raportu: {e}")

    def _generate_markdown_report(self) -> str:
        """Generuj raport Markdown z analizy nestingu."""
        from datetime import datetime

        def format_time(seconds):
            if seconds >= 3600:
                return f"{seconds/3600:.2f} h ({seconds:.0f} s)"
            elif seconds >= 60:
                return f"{seconds/60:.1f} min ({seconds:.0f} s)"
            else:
                return f"{seconds:.1f} s"

        # Dane do raportu
        result = self.nesting_result
        placed_count = len(result.placed_parts)
        sheets_count = result.sheets_used
        efficiency = result.total_efficiency

        v_max_m_min = self._get_cutting_speed()
        machine_rate = 300.0  # PLN/h

        cost_classic = getattr(self, 'cost_classic', 0)
        cost_dynamic = getattr(self, 'cost_dynamic', 0)

        time_diff = self.time_dynamic_s - self.time_classic_s
        time_diff_pct = ((time_diff / self.time_classic_s) * 100) if self.time_classic_s > 0 else 0
        cost_diff = cost_dynamic - cost_classic

        # Build report
        report = f"""# RAPORT ANALIZY NESTINGU
================================================================================
**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Materiał:** {self.material}
**Grubość:** {self.thickness} mm
**Prędkość cięcia:** {v_max_m_min:.1f} m/min

---

## PODSUMOWANIE NESTINGU

| Parametr | Wartość |
|----------|---------|
| Detali umieszczonych | {placed_count} |
| Arkuszy użytych | {sheets_count} |
| Efektywność | {efficiency:.1%} |
| Nieumieszczonych | {result.unplaced_count} |

---

## PARAMETRY DYNAMIKI MASZYNY

| Parametr | Wartość |
|----------|---------|
| Przyspieszenie max | {self.dynamics_settings.max_accel_mm_s2:.0f} mm/s² |
| Prędkość w narożniku | {self.dynamics_settings.square_corner_velocity_mm_s:.0f} mm/s |
| Prędkość rapid | {self.dynamics_settings.max_rapid_mm_s:.0f} mm/s |
| Junction deviation | {self.dynamics_settings.junction_deviation_mm:.3f} mm |
| Model JD aktywny | {"TAK" if self.dynamics_settings.use_junction_deviation else "NIE"} |

---

## PORÓWNANIE METOD WYCENY

### Metoda Klasyczna
**Wzór:** `czas = długość_cięcia / prędkość`

- **Czas cięcia:** {format_time(self.time_classic_s)}
- **Koszt:** {cost_classic:.2f} PLN

*Uwaga: Ta metoda zakłada stałą prędkość V_max na całej długości cięcia.
Ignoruje przyspieszenia, hamowania i ograniczenia w narożnikach.*

### Metoda Dynamiczna (Motion Planning)
**Algorytm:** Lookahead z profilem trapezoidowym (acc → cruise → dec)

- **Czas cięcia:** {format_time(self.time_dynamic_s)}
- **Koszt:** {cost_dynamic:.2f} PLN

*Metoda dynamiczna uwzględnia:*
- Start/stop dla każdego konturu
- Przyspieszanie do V_max i hamowanie do V=0
- Redukcję prędkości w narożnikach
- Ograniczenia kinematyczne maszyny

### RÓŻNICA

| Metryka | Wartość | Odchylenie |
|---------|---------|------------|
| Czas | {time_diff:+.1f} s | {time_diff_pct:+.1f}% |
| Koszt | {cost_diff:+.2f} PLN | {time_diff_pct:+.1f}% |

"""

        # Dodaj tabelę arkuszy
        if result.sheets:
            report += """---

## SZCZEGÓŁY ARKUSZY

| Arkusz | Detali | Czas klas. | Czas dyn. | Różnica |
|--------|--------|------------|-----------|---------|
"""
            for i, sheet in enumerate(result.sheets):
                t_classic = getattr(sheet, 'cut_time_classic_s', 0)
                t_dynamic = getattr(sheet, 'cut_time_dynamic_s', 0)
                parts_count = len(sheet.placed_parts)
                diff = t_dynamic - t_classic
                report += f"| #{i+1} | {parts_count} | {t_classic:.1f} s | {t_dynamic:.1f} s | {diff:+.1f} s |\n"

        # Dodaj tabelę detali
        report += """
---

## SZCZEGÓŁY DETALI

| Detal | Wymiary | Dł. cięcia | Czas klas. | Czas dyn. |
|-------|---------|------------|------------|-----------|
"""
        for sheet in result.sheets:
            for part in sheet.placed_parts:
                name = part.name if hasattr(part, 'name') else '?'
                w = part.width if hasattr(part, 'width') else 0
                h = part.height if hasattr(part, 'height') else 0
                cut_len = getattr(part, 'cut_length_mm', 0)
                t_classic = getattr(part, 'cut_time_classic_s', 0)
                t_dynamic = getattr(part, 'cut_time_dynamic_s', 0)
                report += f"| {name} | {w:.0f}×{h:.0f} | {cut_len:.0f} mm | {t_classic:.2f} s | {t_dynamic:.2f} s |\n"

        # Dodaj wyjaśnienie
        report += f"""
---

## DLACZEGO RÓŻNICA?

Metoda dynamiczna daje {"dłuższy" if time_diff > 0 else "krótszy"} czas o **{abs(time_diff_pct):.1f}%** ponieważ:

1. **Startów/stopów:** Każdy z konturów wymaga przyspieszenia od V=0 i wyhamowania do V=0
2. **Narożniki:** W rogach maszyna musi zwolnić do V_corner = {self.dynamics_settings.square_corner_velocity_mm_s:.0f} mm/s
3. **Przyspieszenie:** Maksymalne a = {self.dynamics_settings.max_accel_mm_s2:.0f} mm/s² ogranicza tempo nabierania prędkości

Dla detali z wieloma krótkimi segmentami lub ostrymi kątami różnica będzie większa.

---

## REKOMENDACJA

"""
        if time_diff_pct > 10:
            report += """⚠️ **UWAGA:** Metoda klasyczna znacząco zaniża rzeczywisty czas cięcia.
Zalecamy stosowanie metody dynamicznej dla dokładniejszych wycen."""
        elif time_diff_pct > 3:
            report += """ℹ️ Różnica jest umiarkowana. Dla prostych detali metoda klasyczna może być wystarczająca,
ale dla skomplikowanych kształtów zalecamy metodę dynamiczną."""
        else:
            report += """✅ Różnica jest minimalna. Dla prostych konturów obie metody dają zbliżone wyniki."""

        report += f"""

---

*Raport wygenerowany przez NewERP Nesting Module*
*Stawka maszyny: {machine_rate:.0f} PLN/h*
"""

        return report

    def get_result(self):
        return self.nesting_result

    def set_dynamics_settings(self, settings: MachineDynamicsSettings):
        """Ustaw ustawienia dynamiki maszyny."""
        self.dynamics_settings = settings
        logger.info(f"[NestingTab] Dynamics settings updated: {settings.use_dynamic_method}")

    def _calculate_time_comparison(self):
        """Calculate and compare classic vs dynamic cutting time for all parts.

        Updates:
        - self.time_classic_s, self.time_dynamic_s (for display)
        - result.cut_time_classic_s, result.cut_time_dynamic_s (for callback)
        - Per-sheet and per-part times in result objects
        """
        if not HAS_MOTION_DYNAMICS:
            logger.warning("Motion dynamics not available for time calculation")
            return

        self.time_classic_s = 0.0
        self.time_dynamic_s = 0.0

        # Get cutting speed based on material and thickness
        v_max_m_min = self._get_cutting_speed()
        v_max_mm_s = m_min_to_mm_s(v_max_m_min)

        # Create machine profile
        machine = MachineProfile(
            max_accel_mm_s2=self.dynamics_settings.max_accel_mm_s2,
            max_rapid_mm_s=self.dynamics_settings.max_rapid_mm_s,
            square_corner_velocity_mm_s=self.dynamics_settings.square_corner_velocity_mm_s,
            junction_deviation_mm=self.dynamics_settings.junction_deviation_mm,
            use_junction_deviation=self.dynamics_settings.use_junction_deviation
        )

        # Build filepath lookup from original parts data
        filepath_by_name = {}
        for part_data in self.parts:
            name = part_data.get('name', '')
            filepath = part_data.get('filepath', '')
            if name and filepath:
                filepath_by_name[name] = filepath

        # Calculate time for each placed part in result
        if self.nesting_result:
            for sheet in self.nesting_result.sheets:
                sheet.cut_time_classic_s = 0.0
                sheet.cut_time_dynamic_s = 0.0
                sheet.total_cut_length_mm = 0.0
                sheet.total_pierce_count = 0

                for part in sheet.placed_parts:
                    # Get filepath from original parts data
                    filepath = filepath_by_name.get(part.name, '')
                    part.filepath = filepath

                    # Estimate cut length from contour
                    cut_length_mm = self._estimate_cut_length_from_nested_part(part)
                    part.cut_length_mm = cut_length_mm

                    # Classic time: length / speed
                    if v_max_mm_s > 0:
                        part.cut_time_classic_s = cut_length_mm / v_max_mm_s
                    else:
                        part.cut_time_classic_s = 0.0

                    # Dynamic time: use motion planner if filepath available
                    if filepath and os.path.exists(filepath):
                        try:
                            segments = extract_motion_segments(filepath)
                            if segments:
                                cutting_time, rapid_time = estimate_motion_time(segments, machine, v_max_mm_s)
                                part.cut_time_dynamic_s = cutting_time + rapid_time
                                part.pierce_count = len(set(s.contour_id for s in segments if not s.is_rapid))
                            else:
                                part.cut_time_dynamic_s = part.cut_time_classic_s * 1.3
                                part.pierce_count = 1
                        except Exception as e:
                            logger.error(f"Error calculating dynamic time for {filepath}: {e}")
                            part.cut_time_dynamic_s = part.cut_time_classic_s * 1.3
                            part.pierce_count = 1
                    else:
                        # Estimate from contour complexity
                        holes_count = len(part.holes) if hasattr(part, 'holes') else 0
                        part.pierce_count = 1 + holes_count
                        part.cut_time_dynamic_s = part.cut_time_classic_s * (1.2 + holes_count * 0.1)

                    # Aggregate to sheet
                    sheet.cut_time_classic_s += part.cut_time_classic_s
                    sheet.cut_time_dynamic_s += part.cut_time_dynamic_s
                    sheet.total_cut_length_mm += part.cut_length_mm
                    sheet.total_pierce_count += part.pierce_count

                # Aggregate to totals
                self.time_classic_s += sheet.cut_time_classic_s
                self.time_dynamic_s += sheet.cut_time_dynamic_s

            # Store in result for callback
            self.nesting_result.cut_time_classic_s = self.time_classic_s
            self.nesting_result.cut_time_dynamic_s = self.time_dynamic_s
            self.nesting_result.total_cut_length_mm = sum(s.total_cut_length_mm for s in self.nesting_result.sheets)
            self.nesting_result.total_pierce_count = sum(s.total_pierce_count for s in self.nesting_result.sheets)

        logger.info(f"Time comparison: Classic={self.time_classic_s:.1f}s, Dynamic={self.time_dynamic_s:.1f}s")

    def _estimate_cut_length_from_nested_part(self, part) -> float:
        """Estimate cut length from NestedPart contour and holes."""
        cut_length = 0.0

        # Original contour perimeter
        contour = part.original_contour if hasattr(part, 'original_contour') else []
        if len(contour) >= 3:
            for i in range(len(contour)):
                x1, y1 = contour[i]
                x2, y2 = contour[(i + 1) % len(contour)]
                cut_length += ((x2 - x1)**2 + (y2 - y1)**2)**0.5

        # Holes perimeter
        holes = part.holes if hasattr(part, 'holes') else []
        for hole in holes:
            if len(hole) >= 3:
                for i in range(len(hole)):
                    x1, y1 = hole[i]
                    x2, y2 = hole[(i + 1) % len(hole)]
                    cut_length += ((x2 - x1)**2 + (y2 - y1)**2)**0.5

        return cut_length

    def _get_cutting_speed(self) -> float:
        """Get cutting speed in m/min based on material and thickness.

        First tries to fetch from Supabase cutting_prices table,
        falls back to hardcoded defaults if not available.
        """
        # Try Supabase first
        if HAS_PRICING_REPO and _pricing_repo:
            try:
                record = _pricing_repo.get_cutting_price(self.material, self.thickness)
                if record and record.get('cutting_speed'):
                    speed = float(record['cutting_speed'])
                    logger.info(f"[NestingTab] Got cutting speed from Supabase: {self.material} {self.thickness}mm = {speed} m/min")
                    return speed
            except Exception as e:
                logger.warning(f"[NestingTab] Failed to get cutting speed from Supabase: {e}")

        # Fallback: Simple lookup table
        speed_table = {
            # (material_prefix, max_thickness): speed_m_min
            ('S235', 3.0): 6.0,
            ('S235', 6.0): 4.0,
            ('S235', 10.0): 2.5,
            ('S355', 3.0): 5.5,
            ('S355', 6.0): 3.5,
            ('S355', 10.0): 2.0,
            ('AL', 3.0): 8.0,
            ('AL', 6.0): 5.0,
            ('INOX', 3.0): 4.0,
            ('INOX', 6.0): 2.5,
        }

        # Try to match material
        for (mat_prefix, max_th), speed in speed_table.items():
            if self.material.upper().startswith(mat_prefix) and self.thickness <= max_th:
                logger.info(f"[NestingTab] Using fallback speed: {self.material} {self.thickness}mm = {speed} m/min")
                return speed

        # Default based on thickness
        if self.thickness <= 3.0:
            default_speed = 5.0
        elif self.thickness <= 6.0:
            default_speed = 3.0
        elif self.thickness <= 10.0:
            default_speed = 2.0
        else:
            default_speed = 1.5

        logger.info(f"[NestingTab] Using default speed for {self.material} {self.thickness}mm = {default_speed} m/min")
        return default_speed

    def _estimate_cut_length(self, part_data: dict) -> float:
        """Estimate total cut length from part data."""
        cut_length = 0.0

        # Contour perimeter
        contour = part_data.get('contour', [])
        if len(contour) >= 3:
            for i in range(len(contour)):
                x1, y1 = contour[i]
                x2, y2 = contour[(i + 1) % len(contour)]
                cut_length += ((x2 - x1)**2 + (y2 - y1)**2)**0.5

        # Holes perimeter
        for hole in part_data.get('holes', []):
            if len(hole) >= 3:
                for i in range(len(hole)):
                    x1, y1 = hole[i]
                    x2, y2 = hole[(i + 1) % len(hole)]
                    cut_length += ((x2 - x1)**2 + (y2 - y1)**2)**0.5

        return cut_length

    def _estimate_dynamic_time(self, part_data: dict, v_max_mm_s: float, machine: MachineProfile) -> float:
        """Estimate dynamic time for a part without DXF file."""
        cut_length = self._estimate_cut_length(part_data)

        # Count holes to estimate pierce count
        holes_count = len(part_data.get('holes', []))
        pierce_count = 1 + holes_count  # 1 for outer contour + holes

        # Estimate complexity from contour
        contour = part_data.get('contour', [])
        corner_count = len(contour) if len(contour) >= 3 else 4

        # Calculate time with overhead for accel/decel
        # Each contour start needs acceleration from zero
        accel_overhead = v_max_mm_s / machine.max_accel_mm_s2 if machine.max_accel_mm_s2 > 0 else 0.5

        # Corner slowdowns
        corner_time = corner_count * 0.02  # ~20ms per corner average

        # Total time
        base_time = cut_length / v_max_mm_s if v_max_mm_s > 0 else 0
        total_time = base_time + (pierce_count * accel_overhead * 2) + corner_time

        return total_time


# ============================================================
# Main Tabs Panel
# ============================================================

class NestingTabsPanel(ctk.CTkFrame):
    """Panel z zakładkami nestingu dla każdej kombinacji materiał+grubość"""

    def __init__(self, parent, parts_by_group: Dict[Tuple[str, float], List[dict]],
                 sheet_formats: List[Tuple[float, float]] = None,
                 on_all_complete: Optional[Callable] = None,
                 dynamics_settings: MachineDynamicsSettings = None):
        super().__init__(parent, fg_color=Theme.BG_DARK)

        self.parts_by_group = parts_by_group
        self.sheet_formats = sheet_formats or [
            (3000, 1500), (2500, 1250), (2000, 1000), (1500, 750)
        ]
        self.on_all_complete = on_all_complete
        self.dynamics_settings = dynamics_settings or MachineDynamicsSettings()

        self.tabs: Dict[str, NestingTab] = {}
        self.results: Dict[Tuple[str, float], Any] = {}

        self._setup_ui()
    
    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.tabview = ctk.CTkTabview(self, fg_color=Theme.BG_CARD)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        for (material, thickness), parts in self.parts_by_group.items():
            tab_name = f"{material} {thickness}mm"

            self.tabview.add(tab_name)
            tab_frame = self.tabview.tab(tab_name)

            tab = NestingTab(
                tab_frame,
                material=material,
                thickness=thickness,
                parts=parts,
                sheet_formats=self.sheet_formats,
                on_nesting_complete=self._on_tab_complete,
                dynamics_settings=self.dynamics_settings
            )
            tab.pack(fill="both", expand=True)

            self.tabs[tab_name] = tab
        
        if not self.parts_by_group:
            empty_label = ctk.CTkLabel(
                self.tabview,
                text="Brak detali do nestingu.\nDodaj pliki DXF.",
                font=ctk.CTkFont(size=14),
                text_color=Theme.TEXT_MUTED
            )
            empty_label.pack(expand=True)
    
    def _on_tab_complete(self, material: str, thickness: float, result):
        self.results[(material, thickness)] = result
        
        if len(self.results) == len(self.parts_by_group):
            if self.on_all_complete:
                self.on_all_complete(self.results)
    
    def get_all_results(self) -> Dict[Tuple[str, float], Any]:
        return self.results

    def export_all_images(self, width: int = 800, height: int = 600) -> Dict[str, List[bytes]]:
        """Eksportuj obrazy ze wszystkich zakladek

        Returns:
            Dict[tab_name, List[png_bytes]] - slownik z lista obrazow per zakladka
        """
        all_images = {}
        for tab_name, tab in self.tabs.items():
            images = tab.export_images(width, height)
            if images:
                all_images[tab_name] = images
        return all_images

    def start_all_nesting(self):
        """Uruchom nesting na wszystkich zakładkach"""
        for tab in self.tabs.values():
            tab.start_nesting()

    def set_dynamics_settings(self, settings: MachineDynamicsSettings):
        """Ustaw ustawienia dynamiki maszyny."""
        self.dynamics_settings = settings
        for tab in self.tabs.values():
            tab.set_dynamics_settings(settings)


# ============================================================
# Compatibility exports
# ============================================================

# Dla kompatybilności wstecznej
NestingCanvas = SheetCanvas


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.title("Multi-Sheet Nesting Test")
    root.geometry("1400x900")
    
    # Dużo detali żeby wymusić wiele arkuszy
    test_data = {
        ("S355", 3.0): [
            {'name': f'Płyta_{i}', 'width': 400 + i*50, 'height': 300 + i*30, 'quantity': 5,
             'contour': [(0, 0), (400+i*50, 0), (400+i*50, 300+i*30), (0, 300+i*30)], 'holes': []}
            for i in range(8)
        ] + [
            {'name': 'ZaDuży', 'width': 5000, 'height': 3000, 'quantity': 2,
             'contour': [], 'holes': []}  # Za duży!
        ],
    }
    
    panel = NestingTabsPanel(
        root,
        parts_by_group=test_data,
        sheet_formats=[(1500, 1000), (2000, 1000), (3000, 1500)],
        on_all_complete=lambda r: print(f"Wszystkie zakończone!")
    )
    panel.pack(fill="both", expand=True)
    
    root.mainloop()
