"""
Live Nesting Preview
====================
Podgląd nestingu w czasie rzeczywistym z wizualizacją postępów.
"""

import customtkinter as ctk
from tkinter import Canvas
import threading
import time
import logging
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass, field
from queue import Queue
import math

logger = logging.getLogger(__name__)


class Theme:
    """Kolory"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_INPUT = "#2d2d2d"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#666666"
    ACCENT_PRIMARY = "#8b5cf6"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"
    ACCENT_INFO = "#06b6d4"


# =============================================================================
# Progress Events
# =============================================================================

@dataclass
class NestingEvent:
    """Zdarzenie nestingu"""
    event_type: str  # 'start', 'sheet_start', 'part_placed', 'part_failed', 'sheet_done', 'done'
    message: str = ""
    sheet_index: int = 0
    part_name: str = ""
    part_x: float = 0
    part_y: float = 0
    part_width: float = 0
    part_height: float = 0
    part_rotated: bool = False
    progress: float = 0  # 0.0 - 1.0
    utilization: float = 0


# =============================================================================
# Nesting Observer Interface
# =============================================================================

class NestingObserver:
    """Interfejs obserwatora nestingu"""
    
    def on_nesting_event(self, event: NestingEvent):
        """Obsłuż zdarzenie nestingu"""
        pass


# =============================================================================
# Live Nesting Canvas
# =============================================================================

class LiveNestingCanvas(ctk.CTkFrame):
    """Canvas z wizualizacją nestingu w czasie rzeczywistym"""
    
    # Kolory detali (cykliczne)
    PART_COLORS = [
        "#8b5cf6", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4",
        "#ec4899", "#84cc16", "#f97316", "#6366f1", "#14b8a6"
    ]
    
    def __init__(self, parent, width: int = 600, height: int = 400):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        
        self.canvas_width = width
        self.canvas_height = height
        
        # Stan
        self.sheet_width = 1000
        self.sheet_height = 2000
        self.margin = 10
        self.placed_parts: List[Dict] = []
        self.current_part: Optional[Dict] = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.color_index = 0
        
        self._setup_canvas_ui()
    
    def _setup_canvas_ui(self):
        """Buduj UI"""
        # Info bar
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.info_frame.pack(fill="x", padx=10, pady=5)
        
        self.sheet_label = ctk.CTkLabel(
            self.info_frame,
            text="Arkusz: -",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.sheet_label.pack(side="left")
        
        self.util_label = ctk.CTkLabel(
            self.info_frame,
            text="Wykorzystanie: 0%",
            font=ctk.CTkFont(size=12),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.util_label.pack(side="right")
        
        self.parts_label = ctk.CTkLabel(
            self.info_frame,
            text="Detali: 0",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.parts_label.pack(side="right", padx=20)
        
        # Canvas
        self.canvas = Canvas(
            self,
            width=self.canvas_width,
            height=self.canvas_height,
            bg=Theme.BG_DARK,
            highlightthickness=0
        )
        self.canvas.pack(padx=10, pady=(0, 10))
        
        # Początkowy stan
        self.clear()
    
    def set_sheet(self, width: float, height: float, margin: float = 10, format_name: str = ""):
        """Ustaw arkusz"""
        self.sheet_width = width
        self.sheet_height = height
        self.margin = margin
        self.placed_parts = []
        self.current_part = None
        self.color_index = 0
        
        # Oblicz skalę
        self._calculate_scale()
        
        # Aktualizuj info
        self.sheet_label.configure(text=f"Arkusz: {format_name or f'{width}x{height}'}")
        self.util_label.configure(text="Wykorzystanie: 0%")
        self.parts_label.configure(text="Detali: 0")
        
        # Rysuj
        self.redraw()
    
    def _calculate_scale(self):
        """Oblicz skalę"""
        padding = 20
        available_width = self.canvas_width - 2 * padding
        available_height = self.canvas_height - 2 * padding
        
        scale_x = available_width / self.sheet_width
        scale_y = available_height / self.sheet_height
        self.scale = min(scale_x, scale_y)
        
        # Centruj
        scaled_width = self.sheet_width * self.scale
        scaled_height = self.sheet_height * self.scale
        self.offset_x = (self.canvas_width - scaled_width) / 2
        self.offset_y = (self.canvas_height - scaled_height) / 2
    
    def add_part(
        self, 
        x: float, y: float, 
        width: float, height: float,
        name: str = "", 
        rotated: bool = False,
        animate: bool = True
    ):
        """Dodaj detal"""
        color = self.PART_COLORS[self.color_index % len(self.PART_COLORS)]
        self.color_index += 1
        
        part = {
            'x': x, 'y': y,
            'width': width, 'height': height,
            'name': name, 'rotated': rotated,
            'color': color
        }
        
        if animate:
            self.current_part = part
            self.redraw()
            self.update_idletasks()
            time.sleep(0.05)  # Krótka pauza dla efektu
        
        self.placed_parts.append(part)
        self.current_part = None
        
        # Aktualizuj statystyki
        self._update_stats()
        self.redraw()
    
    def _update_stats(self):
        """Aktualizuj statystyki"""
        self.parts_label.configure(text=f"Detali: {len(self.placed_parts)}")
        
        # Oblicz wykorzystanie
        total_area = self.sheet_width * self.sheet_height
        used_area = sum(p['width'] * p['height'] for p in self.placed_parts)
        utilization = (used_area / total_area) * 100 if total_area > 0 else 0
        
        self.util_label.configure(text=f"Wykorzystanie: {utilization:.1f}%")
        
        # Kolor w zależności od wykorzystania
        if utilization >= 70:
            color = Theme.ACCENT_SUCCESS
        elif utilization >= 50:
            color = Theme.ACCENT_WARNING
        else:
            color = Theme.ACCENT_DANGER
        self.util_label.configure(text_color=color)
    
    def redraw(self):
        """Rysuj canvas"""
        self.canvas.delete("all")
        
        # Arkusz
        x1 = self.offset_x
        y1 = self.offset_y
        x2 = x1 + self.sheet_width * self.scale
        y2 = y1 + self.sheet_height * self.scale
        
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline=Theme.TEXT_MUTED,
            width=2
        )
        
        # Margines
        if self.margin > 0:
            mx1 = x1 + self.margin * self.scale
            my1 = y1 + self.margin * self.scale
            mx2 = x2 - self.margin * self.scale
            my2 = y2 - self.margin * self.scale
            
            self.canvas.create_rectangle(
                mx1, my1, mx2, my2,
                outline=Theme.TEXT_MUTED,
                dash=(4, 4)
            )
        
        # Umieszczone detale
        for part in self.placed_parts:
            self._draw_part(part, alpha=1.0)
        
        # Aktualnie umieszczany detal (animacja)
        if self.current_part:
            self._draw_part(self.current_part, alpha=0.7, highlight=True)
    
    def _draw_part(self, part: Dict, alpha: float = 1.0, highlight: bool = False):
        """Rysuj detal"""
        x = self.offset_x + part['x'] * self.scale
        y = self.offset_y + (self.sheet_height - part['y'] - part['height']) * self.scale  # Odwróć Y
        
        w = part['width'] * self.scale
        h = part['height'] * self.scale
        
        color = part['color']
        
        # Prostokąt detalu
        outline_width = 3 if highlight else 1
        self.canvas.create_rectangle(
            x, y, x + w, y + h,
            fill=color,
            outline=Theme.TEXT_PRIMARY if highlight else color,
            width=outline_width,
            stipple='gray50' if alpha < 1.0 else ''
        )
        
        # Nazwa (jeśli się mieści)
        if w > 30 and h > 15:
            name = part['name'][:10] if len(part['name']) > 10 else part['name']
            
            # Rozmiar fontu proporcjonalny do rozmiaru detalu
            font_size = max(7, min(10, int(min(w, h) / 8)))
            
            self.canvas.create_text(
                x + w/2, y + h/2,
                text=name,
                fill=Theme.TEXT_PRIMARY,
                font=('Arial', font_size)
            )
    
    def clear(self):
        """Wyczyść canvas"""
        self.placed_parts = []
        self.current_part = None
        self.color_index = 0
        self.canvas.delete("all")
        
        # Placeholder
        self.canvas.create_text(
            self.canvas_width / 2,
            self.canvas_height / 2,
            text="Oczekiwanie na nesting...",
            fill=Theme.TEXT_MUTED,
            font=('Arial', 14)
        )


# =============================================================================
# Live Nesting Window
# =============================================================================

class LiveNestingWindow(ctk.CTkToplevel):
    """Okno z podglądem nestingu w czasie rzeczywistym"""
    
    def __init__(self, parent, title: str = "Podgląd nestingu"):
        super().__init__(parent)
        
        self.title(f"📐 {title}")
        self.geometry("800x700")
        self.configure(fg_color=Theme.BG_DARK)
        
        # Stan
        self.is_running = False
        self.is_paused = False
        self.event_queue: Queue = Queue()
        self.current_sheet_index = 0
        
        self._setup_ui()
        
        # Centruj
        self.transient(parent)
        self.lift()
        self.focus_force()
    
    def _setup_ui(self):
        """Buduj UI"""
        # Nagłówek
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=0)
        header.pack(fill="x")
        
        ctk.CTkLabel(
            header,
            text="📐 PODGLĄD NESTINGU NA ŻYWO",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        ).pack(pady=15)
        
        # Progress bar
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.pack(fill="x", padx=20, pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(progress_frame, width=400)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(
            progress_frame,
            text="0%",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=60
        )
        self.progress_label.pack(side="right", padx=10)
        
        # Status
        self.status_label = ctk.CTkLabel(
            self,
            text="Gotowy do uruchomienia",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.status_label.pack(pady=5)
        
        # Canvas
        self.nesting_canvas = LiveNestingCanvas(self, width=700, height=450)
        self.nesting_canvas.pack(padx=20, pady=10)
        
        # Nawigacja arkuszy
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(fill="x", padx=20, pady=5)
        
        self.btn_prev = ctk.CTkButton(
            nav_frame,
            text="◀ Poprzedni",
            width=100,
            fg_color=Theme.BG_INPUT,
            state="disabled",
            command=self._prev_sheet
        )
        self.btn_prev.pack(side="left")
        
        self.sheet_info_label = ctk.CTkLabel(
            nav_frame,
            text="Arkusz 0 / 0",
            font=ctk.CTkFont(size=12)
        )
        self.sheet_info_label.pack(side="left", expand=True)
        
        self.btn_next = ctk.CTkButton(
            nav_frame,
            text="Następny ▶",
            width=100,
            fg_color=Theme.BG_INPUT,
            state="disabled",
            command=self._next_sheet
        )
        self.btn_next.pack(side="right")
        
        # Kontrolki
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", padx=20, pady=15)
        
        self.btn_pause = ctk.CTkButton(
            control_frame,
            text="⏸️ Pauza",
            width=100,
            fg_color=Theme.ACCENT_WARNING,
            state="disabled",
            command=self._toggle_pause
        )
        self.btn_pause.pack(side="left", padx=5)
        
        self.speed_label = ctk.CTkLabel(
            control_frame,
            text="Szybkość:",
            font=ctk.CTkFont(size=11)
        )
        self.speed_label.pack(side="left", padx=(20, 5))
        
        self.speed_slider = ctk.CTkSlider(
            control_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            width=150,
            command=self._on_speed_change
        )
        self.speed_slider.set(5)
        self.speed_slider.pack(side="left", padx=5)
        
        self.speed_value_label = ctk.CTkLabel(
            control_frame,
            text="5x",
            font=ctk.CTkFont(size=11),
            width=40
        )
        self.speed_value_label.pack(side="left")
        
        self.btn_close = ctk.CTkButton(
            control_frame,
            text="✕ Zamknij",
            width=100,
            fg_color=Theme.ACCENT_DANGER,
            command=self.destroy
        )
        self.btn_close.pack(side="right", padx=5)
        
        # Log
        log_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=8)
        log_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        self.log_text = ctk.CTkTextbox(log_frame, height=80, font=ctk.CTkFont(size=10))
        self.log_text.pack(fill="x", padx=5, pady=5)
        self.log_text.configure(state="disabled")
        
        # Animation speed (delay in ms)
        self.animation_delay = 100  # 100ms default
        
        # Przechowuj dane arkuszy
        self.sheets_data: List[Dict] = []
    
    def _on_speed_change(self, value):
        """Zmiana szybkości"""
        speed = int(value)
        self.speed_value_label.configure(text=f"{speed}x")
        # Delay: speed 1 = 500ms, speed 10 = 10ms
        self.animation_delay = max(10, 500 - (speed - 1) * 50)
    
    def _toggle_pause(self):
        """Przełącz pauzę"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.configure(text="▶️ Wznów", fg_color=Theme.ACCENT_SUCCESS)
        else:
            self.btn_pause.configure(text="⏸️ Pauza", fg_color=Theme.ACCENT_WARNING)
    
    def _prev_sheet(self):
        """Poprzedni arkusz"""
        if self.current_sheet_index > 0:
            self.current_sheet_index -= 1
            self._show_sheet(self.current_sheet_index)
    
    def _next_sheet(self):
        """Następny arkusz"""
        if self.current_sheet_index < len(self.sheets_data) - 1:
            self.current_sheet_index += 1
            self._show_sheet(self.current_sheet_index)
    
    def _show_sheet(self, index: int):
        """Pokaż arkusz o danym indeksie"""
        if 0 <= index < len(self.sheets_data):
            sheet = self.sheets_data[index]
            self.nesting_canvas.set_sheet(
                sheet['width'], sheet['height'],
                sheet.get('margin', 10),
                sheet.get('format_name', '')
            )
            
            # Dodaj wszystkie detale natychmiast
            for part in sheet.get('parts', []):
                self.nesting_canvas.add_part(
                    part['x'], part['y'],
                    part['width'], part['height'],
                    part.get('name', ''),
                    part.get('rotated', False),
                    animate=False
                )
            
            # Aktualizuj nawigację
            self._update_navigation()
    
    def _update_navigation(self):
        """Aktualizuj przyciski nawigacji"""
        total = len(self.sheets_data)
        current = self.current_sheet_index + 1
        
        self.sheet_info_label.configure(text=f"Arkusz {current} / {total}")
        
        self.btn_prev.configure(state="normal" if self.current_sheet_index > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.current_sheet_index < total - 1 else "disabled")
    
    def log(self, message: str):
        """Dodaj wpis do logu"""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    
    def set_status(self, text: str):
        """Ustaw status"""
        self.status_label.configure(text=text)
    
    def set_progress(self, value: float):
        """Ustaw postęp (0.0 - 1.0)"""
        self.progress_bar.set(value)
        self.progress_label.configure(text=f"{value*100:.0f}%")
    
    def start_nesting(
        self,
        sheet_width: float,
        sheet_height: float,
        margin: float = 10,
        format_name: str = ""
    ):
        """Rozpocznij nesting na nowym arkuszu"""
        self.is_running = True
        self.btn_pause.configure(state="normal")
        
        # Zapisz dane arkusza
        sheet_data = {
            'width': sheet_width,
            'height': sheet_height,
            'margin': margin,
            'format_name': format_name,
            'parts': []
        }
        self.sheets_data.append(sheet_data)
        self.current_sheet_index = len(self.sheets_data) - 1
        
        # Ustaw canvas
        self.nesting_canvas.set_sheet(sheet_width, sheet_height, margin, format_name)
        
        self.log(f"📋 Nowy arkusz: {format_name or f'{sheet_width}x{sheet_height}'}")
        self._update_navigation()
    
    def place_part(
        self,
        x: float, y: float,
        width: float, height: float,
        name: str = "",
        rotated: bool = False
    ):
        """Umieść detal"""
        # Zapisz w danych arkusza
        if self.sheets_data:
            self.sheets_data[-1]['parts'].append({
                'x': x, 'y': y,
                'width': width, 'height': height,
                'name': name, 'rotated': rotated
            })
        
        # Animacja
        self.nesting_canvas.add_part(x, y, width, height, name, rotated, animate=True)
        
        # Czekaj na pauzę
        while self.is_paused:
            self.update()
            time.sleep(0.1)
        
        # Delay dla animacji
        self.update()
        time.sleep(self.animation_delay / 1000)
    
    def finish_nesting(self):
        """Zakończ nesting"""
        self.is_running = False
        self.btn_pause.configure(state="disabled")
        self.set_progress(1.0)
        self.set_status("✅ Nesting zakończony")
        self.log("✅ Nesting zakończony pomyślnie")
        self._update_navigation()


# =============================================================================
# Observable Nester Wrapper
# =============================================================================

class ObservableNester:
    """Wrapper dla nestera z obserwacją postępów"""
    
    def __init__(self, observer: LiveNestingWindow = None):
        self.observer = observer
    
    def nest_with_preview(
        self,
        parts: List,
        sheet,
        algorithm: str = "FFDH",
        params: Dict = None
    ):
        """
        Uruchom nesting z podglądem.
        
        Returns:
            NestingResult
        """
        params = params or {}
        
        if self.observer:
            self.observer.set_status(f"Uruchamianie algorytmu: {algorithm}")
            self.observer.log(f"🔧 Algorytm: {algorithm}")
            self.observer.log(f"📦 Detali: {sum(p.quantity for p in parts)}")
        
        # Wybierz algorytm
        if "Shapely" in algorithm:
            return self._nest_shapely(parts, sheet, params)
        elif "NFP" in algorithm:
            return self._nest_nfp(parts, sheet, params)
        else:
            return self._nest_ffdh(parts, sheet, params)
    
    def _nest_ffdh(self, parts, sheet, params):
        """Nesting FFDH z podglądem"""
        from quotations.nesting.nester import Nester
        
        nester = Nester()
        
        # Start arkusza
        if self.observer:
            format_name = f"{sheet.width}x{sheet.height}"
            self.observer.start_nesting(
                sheet.width, sheet.height,
                sheet.margin_left, format_name
            )
        
        # Wykonaj nesting
        result = nester.nest(parts, sheet)
        
        # Pokaż wyniki
        if self.observer and result.sheets:
            total_parts = sum(len(s.placements) for s in result.sheets)
            shown = 0
            
            for sheet_result in result.sheets:
                for placed in sheet_result.placements:
                    self.observer.place_part(
                        placed.x, placed.y,
                        placed.part.width if not placed.rotated else placed.part.height,
                        placed.part.height if not placed.rotated else placed.part.width,
                        placed.part.name,
                        placed.rotated
                    )
                    shown += 1
                    self.observer.set_progress(shown / total_parts)
            
            self.observer.finish_nesting()
        
        return result
    
    def _nest_shapely(self, parts, sheet, params):
        """Nesting Shapely z podglądem"""
        try:
            from quotations.nesting.nester_shapely import ShapelyNester, NestingParams, SheetFormat
            
            shapely_params = NestingParams(
                kerf_width=params.get('kerf_width', 0.2),
                part_spacing=params.get('part_spacing', 3.0),
                sheet_margin=params.get('sheet_margin', 10.0),
                rotation_angles=params.get('rotation_angles', [0, 90]),
                placement_step=params.get('placement_step', 5.0)
            )
            
            nester = ShapelyNester(shapely_params, observer=self.observer)
            shapely_sheet = SheetFormat(sheet.width, sheet.height, f"{sheet.width}x{sheet.height}")
            
            return nester.nest(parts, shapely_sheet)
            
        except ImportError:
            if self.observer:
                self.observer.log("⚠️ Shapely niedostępne, używam FFDH")
            return self._nest_ffdh(parts, sheet, params)
    
    def _nest_nfp(self, parts, sheet, params):
        """Nesting NFP z podglądem"""
        try:
            from quotations.nesting.nester_advanced import AdvancedNester, Sheet as AdvSheet
            
            adv_sheet = AdvSheet(
                width=sheet.width,
                height=sheet.height,
                margin=params.get('sheet_margin', 10.0),
                spacing=params.get('part_spacing', 3.0)
            )
            
            nester = AdvancedNester(observer=self.observer)
            return nester.nest(parts, adv_sheet)
            
        except ImportError:
            if self.observer:
                self.observer.log("⚠️ pyclipper niedostępne, używam FFDH")
            return self._nest_ffdh(parts, sheet, params)
