"""
NewERP - Nesting Visualizer
===========================
Graficzna wizualizacja rozkroju detali na arkuszach blachy.

Używa Tkinter Canvas do rysowania:
- Arkusz blachy (szary)
- Detale (kolorowe prostokąty)
- Etykiety z nazwami
- Legenda i statystyki
"""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import math
import colorsys

# Import typów z nestera
try:
    from quotations.nesting.nester import NestedSheet, PlacedPart, SheetFormat, NestingResult
except ImportError:
    # Standalone mode
    pass


class Theme:
    """Kolory"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_SHEET = "#2d2d2d"      # Arkusz blachy
    SHEET_BORDER = "#404040"
    MARGIN_AREA = "#1f1f1f"   # Strefa martwa
    
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_ON_PART = "#000000"
    
    GRID_LINE = "#333333"
    
    # Paleta kolorów dla detali (wysycone, różne odcienie)
    PART_COLORS = [
        "#3b82f6",  # Niebieski
        "#22c55e",  # Zielony
        "#f59e0b",  # Pomarańczowy
        "#ef4444",  # Czerwony
        "#8b5cf6",  # Fioletowy
        "#06b6d4",  # Cyan
        "#ec4899",  # Różowy
        "#84cc16",  # Limonka
        "#f97316",  # Pomarańcz ciemny
        "#6366f1",  # Indygo
    ]


def generate_colors(n: int) -> List[str]:
    """Generuj n różnych kolorów"""
    if n <= len(Theme.PART_COLORS):
        return Theme.PART_COLORS[:n]
    
    colors = []
    for i in range(n):
        hue = i / n
        rgb = colorsys.hsv_to_rgb(hue, 0.7, 0.9)
        color = "#{:02x}{:02x}{:02x}".format(
            int(rgb[0] * 255),
            int(rgb[1] * 255),
            int(rgb[2] * 255)
        )
        colors.append(color)
    return colors


class NestingCanvas(tk.Canvas):
    """
    Canvas do rysowania pojedynczego arkusza z detalami.
    """
    
    def __init__(
        self,
        parent,
        sheet: 'SheetFormat' = None,
        placements: List['PlacedPart'] = None,
        **kwargs
    ):
        # Domyślne ustawienia
        kwargs.setdefault('bg', Theme.BG_CARD)
        kwargs.setdefault('highlightthickness', 0)
        
        super().__init__(parent, **kwargs)
        
        self.sheet = sheet
        self.placements = placements or []
        
        # Skala i offset
        self.scale = 1.0
        self.offset_x = 20
        self.offset_y = 20
        self.padding = 40
        
        # Mapowanie części → kolor
        self.part_colors: Dict[str, str] = {}
        
        # Tooltip
        self.tooltip = None
        self.tooltip_id = None
        
        # Bindy
        self.bind('<Configure>', self._on_resize)
        self.bind('<Motion>', self._on_mouse_move)
        self.bind('<Leave>', self._hide_tooltip)
        
        # Rysuj
        if self.sheet:
            self.after(10, self.redraw)
    
    def set_data(
        self,
        sheet: 'SheetFormat',
        placements: List['PlacedPart'],
        part_colors: Dict[str, str] = None
    ):
        """Ustaw dane do wyświetlenia"""
        self.sheet = sheet
        self.placements = placements
        self.part_colors = part_colors or {}
        self.redraw()
    
    def _calculate_scale(self):
        """Oblicz skalę aby arkusz mieścił się w canvas"""
        if not self.sheet:
            return
        
        canvas_w = self.winfo_width() - 2 * self.padding
        canvas_h = self.winfo_height() - 2 * self.padding
        
        if canvas_w <= 0 or canvas_h <= 0:
            return
        
        scale_x = canvas_w / self.sheet.width
        scale_y = canvas_h / self.sheet.height
        
        self.scale = min(scale_x, scale_y)
        
        # Centruj arkusz
        sheet_w = self.sheet.width * self.scale
        sheet_h = self.sheet.height * self.scale
        
        self.offset_x = (self.winfo_width() - sheet_w) / 2
        self.offset_y = (self.winfo_height() - sheet_h) / 2
    
    def _to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        """Konwertuj współrzędne arkusza na canvas"""
        cx = self.offset_x + x * self.scale
        cy = self.offset_y + (self.sheet.height - y) * self.scale  # Odwróć Y
        return cx, cy
    
    def _from_canvas(self, cx: float, cy: float) -> Tuple[float, float]:
        """Konwertuj współrzędne canvas na arkusz"""
        x = (cx - self.offset_x) / self.scale
        y = self.sheet.height - (cy - self.offset_y) / self.scale
        return x, y
    
    def redraw(self):
        """Przerysuj wszystko"""
        self.delete('all')
        
        if not self.sheet:
            return
        
        self._calculate_scale()
        self._draw_sheet()
        self._draw_margins()
        self._draw_grid()
        self._draw_parts()
        self._draw_dimensions()
    
    def _draw_sheet(self):
        """Rysuj arkusz blachy"""
        x1, y1 = self._to_canvas(0, self.sheet.height)
        x2, y2 = self._to_canvas(self.sheet.width, 0)
        
        # Tło arkusza
        self.create_rectangle(
            x1, y1, x2, y2,
            fill=Theme.BG_SHEET,
            outline=Theme.SHEET_BORDER,
            width=2,
            tags='sheet'
        )
    
    def _draw_margins(self):
        """Rysuj strefy martwe (marginesy)"""
        if not self.sheet:
            return
        
        margin_color = Theme.MARGIN_AREA
        
        # Lewy margines
        x1, y1 = self._to_canvas(0, self.sheet.height)
        x2, y2 = self._to_canvas(self.sheet.margin_left, 0)
        self.create_rectangle(x1, y1, x2, y2, fill=margin_color, outline='', tags='margin')
        
        # Prawy margines
        x1, y1 = self._to_canvas(self.sheet.width - self.sheet.margin_right, self.sheet.height)
        x2, y2 = self._to_canvas(self.sheet.width, 0)
        self.create_rectangle(x1, y1, x2, y2, fill=margin_color, outline='', tags='margin')
        
        # Górny margines
        x1, y1 = self._to_canvas(0, self.sheet.height)
        x2, y2 = self._to_canvas(self.sheet.width, self.sheet.height - self.sheet.margin_top)
        self.create_rectangle(x1, y1, x2, y2, fill=margin_color, outline='', tags='margin')
        
        # Dolny margines
        x1, y1 = self._to_canvas(0, self.sheet.margin_bottom)
        x2, y2 = self._to_canvas(self.sheet.width, 0)
        self.create_rectangle(x1, y1, x2, y2, fill=margin_color, outline='', tags='margin')
    
    def _draw_grid(self):
        """Rysuj siatkę pomocniczą"""
        if not self.sheet:
            return
        
        # Siatka co 100mm
        grid_step = 100
        
        # Pionowe linie
        x = grid_step
        while x < self.sheet.width:
            cx1, cy1 = self._to_canvas(x, 0)
            cx2, cy2 = self._to_canvas(x, self.sheet.height)
            self.create_line(cx1, cy1, cx2, cy2, fill=Theme.GRID_LINE, dash=(2, 4), tags='grid')
            x += grid_step
        
        # Poziome linie
        y = grid_step
        while y < self.sheet.height:
            cx1, cy1 = self._to_canvas(0, y)
            cx2, cy2 = self._to_canvas(self.sheet.width, y)
            self.create_line(cx1, cy1, cx2, cy2, fill=Theme.GRID_LINE, dash=(2, 4), tags='grid')
            y += grid_step
    
    def _draw_parts(self):
        """Rysuj detale"""
        for i, placement in enumerate(self.placements):
            self._draw_part(placement, i)
    
    def _draw_part(self, placement: 'PlacedPart', index: int):
        """Rysuj pojedynczy detal"""
        # Pobierz kolor
        part_id = placement.part.id.rsplit('_', 1)[0]  # Usuń suffix _1, _2...
        
        if part_id in self.part_colors:
            color = self.part_colors[part_id]
        else:
            color = Theme.PART_COLORS[index % len(Theme.PART_COLORS)]
        
        # Sprawdź czy mamy wielokąt (True Shape)
        polygon_coords = None
        if hasattr(placement, 'polygon') and placement.polygon is not None:
            try:
                if hasattr(placement.polygon, 'exterior'):
                    polygon_coords = list(placement.polygon.exterior.coords)
            except Exception:
                pass
        elif hasattr(placement, 'get_polygon_coords'):
            polygon_coords = placement.get_polygon_coords()
        
        if polygon_coords and len(polygon_coords) > 2:
            # Rysuj wielokąt (True Shape)
            canvas_coords = []
            for px, py in polygon_coords:
                cx, cy = self._to_canvas(px, py)
                canvas_coords.extend([cx, cy])
            
            # Wielokąt
            poly_id = self.create_polygon(
                canvas_coords,
                fill=color,
                outline='#ffffff',
                width=1,
                tags=('part', f'part_{index}')
            )
            
            # Oblicz środek dla etykiety
            min_x = min(c[0] for c in polygon_coords)
            max_x = max(c[0] for c in polygon_coords)
            min_y = min(c[1] for c in polygon_coords)
            max_y = max(c[1] for c in polygon_coords)
            
            center_x, center_y = self._to_canvas(
                (min_x + max_x) / 2,
                (min_y + max_y) / 2
            )
            
            part_w = abs(max_x - min_x) * self.scale
            part_h = abs(max_y - min_y) * self.scale
            
            # Zapisz dane dla tooltip
            self.itemconfig(poly_id, tags=('part', f'part_{index}', f'data_{index}'))
        else:
            # Rysuj prostokąt (fallback)
            x1, y1 = placement.x, placement.y
            x2, y2 = placement.right, placement.top
            
            cx1, cy1 = self._to_canvas(x1, y2)  # Top-left w canvas
            cx2, cy2 = self._to_canvas(x2, y1)  # Bottom-right w canvas
            
            # Prostokąt detalu
            rect_id = self.create_rectangle(
                cx1, cy1, cx2, cy2,
                fill=color,
                outline='#ffffff',
                width=1,
                tags=('part', f'part_{index}')
            )
            
            center_x = (cx1 + cx2) / 2
            center_y = (cy1 + cy2) / 2
            part_w = abs(cx2 - cx1)
            part_h = abs(cy2 - cy1)
            
            # Zapisz dane dla tooltip
            self.itemconfig(rect_id, tags=('part', f'part_{index}', f'data_{index}'))
        
        # Etykieta (nazwa) - tylko jeśli detal wystarczająco duży
        if part_w > 40 and part_h > 20:
            # Skrócona nazwa
            name = placement.part.name
            if len(name) > 15:
                name = name[:12] + "..."
            
            # Wybierz rozmiar czcionki
            font_size = 8
            if part_w > 80 and part_h > 40:
                font_size = 10
            if part_w > 120 and part_h > 60:
                font_size = 12
            
            self.create_text(
                center_x, center_y,
                text=name,
                fill=Theme.TEXT_ON_PART,
                font=('Helvetica', font_size, 'bold'),
                tags=('part_label', f'label_{index}')
            )
    
    def _draw_dimensions(self):
        """Rysuj wymiary arkusza"""
        if not self.sheet:
            return
        
        # Wymiar szerokości (na dole)
        cx1, cy1 = self._to_canvas(0, 0)
        cx2, cy2 = self._to_canvas(self.sheet.width, 0)
        
        self.create_text(
            (cx1 + cx2) / 2,
            cy1 + 15,
            text=f"{self.sheet.width:.0f} mm",
            fill=Theme.TEXT_SECONDARY,
            font=('Helvetica', 9),
            tags='dimension'
        )
        
        # Wymiar wysokości (po lewej)
        cx1, cy1 = self._to_canvas(0, 0)
        cx2, cy2 = self._to_canvas(0, self.sheet.height)
        
        self.create_text(
            cx1 - 15,
            (cy1 + cy2) / 2,
            text=f"{self.sheet.height:.0f} mm",
            fill=Theme.TEXT_SECONDARY,
            font=('Helvetica', 9),
            angle=90,
            tags='dimension'
        )
    
    def zoom_in(self):
        """Przybliż widok"""
        self.scale *= 1.2
        self.redraw()

    def zoom_out(self):
        """Oddal widok"""
        self.scale /= 1.2
        self.redraw()

    def zoom_all(self):
        """Dopasuj widok do całego arkusza"""
        self._calculate_scale()
        self.redraw()

    def zoom_fit(self):
        """Alias dla zoom_all (zgodność z CAD)"""
        self.zoom_all()

    def _on_resize(self, event):
        """Obsługa zmiany rozmiaru"""
        self.redraw()

    def _on_mouse_move(self, event):
        """Obsługa ruchu myszy - tooltip"""
        # Znajdź element pod kursorem
        items = self.find_overlapping(event.x - 2, event.y - 2, event.x + 2, event.y + 2)
        
        part_item = None
        for item in items:
            tags = self.gettags(item)
            if 'part' in tags:
                part_item = item
                break
        
        if part_item:
            # Znajdź index
            tags = self.gettags(part_item)
            index = None
            for tag in tags:
                if tag.startswith('part_'):
                    try:
                        index = int(tag.split('_')[1])
                        break
                    except:
                        pass
            
            if index is not None and index < len(self.placements):
                placement = self.placements[index]
                self._show_tooltip(event.x, event.y, placement)
                return
        
        self._hide_tooltip()
    
    def _show_tooltip(self, x: int, y: int, placement: 'PlacedPart'):
        """Pokaż tooltip z informacjami o detalu"""
        self._hide_tooltip()
        
        text = (
            f"{placement.part.name}\n"
            f"Wymiary: {placement.width:.0f} × {placement.height:.0f} mm\n"
            f"Pozycja: ({placement.x:.0f}, {placement.y:.0f})\n"
            f"Obrócony: {'Tak' if placement.rotated else 'Nie'}"
        )
        
        # Tło tooltip
        self.tooltip_id = self.create_rectangle(
            x + 10, y + 10,
            x + 200, y + 80,
            fill='#333333',
            outline='#555555',
            tags='tooltip'
        )
        
        # Tekst
        self.create_text(
            x + 15, y + 15,
            text=text,
            fill=Theme.TEXT_PRIMARY,
            font=('Helvetica', 9),
            anchor='nw',
            tags='tooltip'
        )
    
    def _hide_tooltip(self, event=None):
        """Ukryj tooltip"""
        self.delete('tooltip')
        self.tooltip_id = None


class NestingVisualizerWindow(ctk.CTkToplevel):
    """
    Okno wizualizacji nestingu z wieloma arkuszami.
    """
    
    def __init__(
        self,
        parent,
        nesting_result: 'NestingResult' = None,
        title: str = "Podgląd rozkroju"
    ):
        super().__init__(parent)
        
        self.nesting_result = nesting_result
        self.current_sheet_index = 0
        
        # Konfiguracja okna
        self.title(f"📐 {title}")
        self.geometry("1000x700")
        self.minsize(800, 600)
        self.configure(fg_color=Theme.BG_DARK)
        
        # Generuj kolory dla części
        self._generate_part_colors()
        
        # Build UI
        self._setup_ui()
        
        # Wyświetl pierwszy arkusz
        if self.nesting_result and self.nesting_result.sheets:
            self._display_sheet(0)

        # Ustawienia okna
        self.attributes('-topmost', True)  # Okno na pierwszym planie
        self.lift()
        self.focus_force()

        # Wywołaj Zoom All przy starcie
        self.after(100, self._zoom_all)
    
    def _generate_part_colors(self):
        """Przypisz kolory do unikalnych części"""
        self.part_colors: Dict[str, str] = {}
        
        if not self.nesting_result:
            return
        
        unique_parts = set()
        for sheet in self.nesting_result.sheets:
            for placement in sheet.placements:
                part_id = placement.part.id.rsplit('_', 1)[0]
                unique_parts.add(part_id)
        
        colors = generate_colors(len(unique_parts))
        for i, part_id in enumerate(sorted(unique_parts)):
            self.part_colors[part_id] = colors[i]
    
    def _setup_ui(self):
        """Buduj interfejs"""
        # Header
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        header.pack(fill="x", padx=10, pady=10)
        header.pack_propagate(False)
        
        # Tytuł
        ctk.CTkLabel(
            header,
            text="📐 PODGLĄD ROZKROJU",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left", padx=20, pady=15)
        
        # Nawigacja arkuszy
        nav_frame = ctk.CTkFrame(header, fg_color="transparent")
        nav_frame.pack(side="right", padx=20)
        
        self.btn_prev = ctk.CTkButton(
            nav_frame,
            text="◀ Poprzedni",
            width=100,
            command=self._prev_sheet,
            state="disabled"
        )
        self.btn_prev.pack(side="left", padx=5)
        
        self.sheet_label = ctk.CTkLabel(
            nav_frame,
            text="Arkusz 1/1",
            font=ctk.CTkFont(size=14)
        )
        self.sheet_label.pack(side="left", padx=20)
        
        self.btn_next = ctk.CTkButton(
            nav_frame,
            text="Następny ▶",
            width=100,
            command=self._next_sheet
        )
        self.btn_next.pack(side="left", padx=5)

        # Toolbar Zoom
        toolbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50)
        toolbar.pack(fill="x", padx=10, pady=(0, 10))
        toolbar.pack_propagate(False)

        # Przyciski zoom z ikonami
        btn_zoom_in = ctk.CTkButton(
            toolbar,
            text="🔍+",
            width=40,
            height=40,
            font=ctk.CTkFont(size=16),
            command=self._zoom_in,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.ACCENT_PRIMARY
        )
        btn_zoom_in.pack(side="left", padx=5, pady=5)
        self._create_tooltip(btn_zoom_in, "Powiększ (Zoom In)")

        btn_zoom_out = ctk.CTkButton(
            toolbar,
            text="🔍−",
            width=40,
            height=40,
            font=ctk.CTkFont(size=16),
            command=self._zoom_out,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.ACCENT_PRIMARY
        )
        btn_zoom_out.pack(side="left", padx=5, pady=5)
        self._create_tooltip(btn_zoom_out, "Pomniejsz (Zoom Out)")

        btn_zoom_all = ctk.CTkButton(
            toolbar,
            text="⊡",
            width=40,
            height=40,
            font=ctk.CTkFont(size=18),
            command=self._zoom_all,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.ACCENT_PRIMARY
        )
        btn_zoom_all.pack(side="left", padx=5, pady=5)
        self._create_tooltip(btn_zoom_all, "Dopasuj widok (Zoom All)")

        btn_zoom_fit = ctk.CTkButton(
            toolbar,
            text="⊞",
            width=40,
            height=40,
            font=ctk.CTkFont(size=18),
            command=self._zoom_fit,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.ACCENT_PRIMARY
        )
        btn_zoom_fit.pack(side="left", padx=5, pady=5)
        self._create_tooltip(btn_zoom_fit, "Dopasuj do arkusza (Zoom Fit)")

        # Main content - Canvas + Stats
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        
        # Canvas
        canvas_frame = ctk.CTkFrame(content, fg_color=Theme.BG_CARD, corner_radius=10)
        canvas_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        self.canvas = NestingCanvas(canvas_frame, width=700, height=500)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Panel statystyk
        stats_frame = ctk.CTkFrame(content, fg_color=Theme.BG_CARD, corner_radius=10)
        stats_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        
        self._setup_stats_panel(stats_frame)
    
    def _setup_stats_panel(self, parent):
        """Panel statystyk"""
        # Nagłówek
        ctk.CTkLabel(
            parent,
            text="📊 STATYSTYKI",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Statystyki arkusza
        self.stats_sheet_frame = ctk.CTkFrame(parent, fg_color=Theme.BG_DARK, corner_radius=8)
        self.stats_sheet_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(
            self.stats_sheet_frame,
            text="Bieżący arkusz",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.lbl_sheet_format = ctk.CTkLabel(
            self.stats_sheet_frame,
            text="Format: -",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_sheet_format.pack(anchor="w", padx=10)
        
        self.lbl_sheet_parts = ctk.CTkLabel(
            self.stats_sheet_frame,
            text="Detali: -",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_sheet_parts.pack(anchor="w", padx=10)
        
        self.lbl_sheet_util = ctk.CTkLabel(
            self.stats_sheet_frame,
            text="Wykorzystanie: -",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_sheet_util.pack(anchor="w", padx=10, pady=(0, 10))
        
        # Pasek wykorzystania
        self.progress_util = ctk.CTkProgressBar(
            self.stats_sheet_frame,
            width=200,
            height=15,
            progress_color="#22c55e"
        )
        self.progress_util.pack(padx=10, pady=(0, 15))
        self.progress_util.set(0)
        
        # Statystyki całkowite
        self.stats_total_frame = ctk.CTkFrame(parent, fg_color=Theme.BG_DARK, corner_radius=8)
        self.stats_total_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            self.stats_total_frame,
            text="Podsumowanie",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.lbl_total_sheets = ctk.CTkLabel(
            self.stats_total_frame,
            text="Arkuszy: -",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_total_sheets.pack(anchor="w", padx=10)
        
        self.lbl_total_parts = ctk.CTkLabel(
            self.stats_total_frame,
            text="Detali łącznie: -",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_total_parts.pack(anchor="w", padx=10)
        
        self.lbl_avg_util = ctk.CTkLabel(
            self.stats_total_frame,
            text="Śr. wykorzystanie: -",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_avg_util.pack(anchor="w", padx=10)
        
        self.lbl_total_waste = ctk.CTkLabel(
            self.stats_total_frame,
            text="Odpad: -",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_total_waste.pack(anchor="w", padx=10, pady=(0, 10))
        
        # Legenda
        legend_frame = ctk.CTkFrame(parent, fg_color=Theme.BG_DARK, corner_radius=8)
        legend_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        ctk.CTkLabel(
            legend_frame,
            text="Legenda",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.legend_container = ctk.CTkScrollableFrame(
            legend_frame,
            fg_color="transparent"
        )
        self.legend_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Wypełnij legendę
        self._populate_legend()
        
        # Aktualizuj statystyki całkowite
        self._update_total_stats()
    
    def _populate_legend(self):
        """Wypełnij legendę kolorami części"""
        for widget in self.legend_container.winfo_children():
            widget.destroy()
        
        for part_id, color in sorted(self.part_colors.items()):
            row = ctk.CTkFrame(self.legend_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            # Kolorowy kwadrat
            color_box = tk.Canvas(row, width=16, height=16, bg=Theme.BG_DARK, highlightthickness=0)
            color_box.pack(side="left", padx=(5, 10))
            color_box.create_rectangle(2, 2, 14, 14, fill=color, outline='white')
            
            # Nazwa
            ctk.CTkLabel(
                row,
                text=part_id[:20] + "..." if len(part_id) > 20 else part_id,
                font=ctk.CTkFont(size=10),
                text_color=Theme.TEXT_PRIMARY
            ).pack(side="left")
    
    def _update_total_stats(self):
        """Aktualizuj statystyki całkowite"""
        if not self.nesting_result:
            return
        
        self.lbl_total_sheets.configure(text=f"Arkuszy: {self.nesting_result.total_sheets}")
        self.lbl_total_parts.configure(text=f"Detali łącznie: {self.nesting_result.total_parts}")
        self.lbl_avg_util.configure(text=f"Śr. wykorzystanie: {self.nesting_result.average_utilization * 100:.1f}%")
        
        waste_m2 = self.nesting_result.total_waste / 1_000_000
        self.lbl_total_waste.configure(text=f"Odpad: {waste_m2:.3f} m²")
    
    def _display_sheet(self, index: int):
        """Wyświetl arkusz o podanym indeksie"""
        if not self.nesting_result or not self.nesting_result.sheets:
            return
        
        if index < 0 or index >= len(self.nesting_result.sheets):
            return
        
        self.current_sheet_index = index
        nested_sheet = self.nesting_result.sheets[index]
        
        # Aktualizuj canvas
        self.canvas.set_data(
            nested_sheet.sheet,
            nested_sheet.placements,
            self.part_colors
        )
        
        # Aktualizuj nawigację
        total = len(self.nesting_result.sheets)
        self.sheet_label.configure(text=f"Arkusz {index + 1}/{total}")
        self.btn_prev.configure(state="normal" if index > 0 else "disabled")
        self.btn_next.configure(state="normal" if index < total - 1 else "disabled")
        
        # Aktualizuj statystyki arkusza
        self.lbl_sheet_format.configure(text=f"Format: {nested_sheet.sheet.name}")
        self.lbl_sheet_parts.configure(text=f"Detali: {nested_sheet.parts_count}")
        self.lbl_sheet_util.configure(text=f"Wykorzystanie: {nested_sheet.utilization_percent:.1f}%")
        
        self.progress_util.set(nested_sheet.utilization)
        
        # Kolor paska w zależności od wykorzystania
        if nested_sheet.utilization >= 0.7:
            self.progress_util.configure(progress_color="#22c55e")  # Zielony
        elif nested_sheet.utilization >= 0.5:
            self.progress_util.configure(progress_color="#f59e0b")  # Pomarańczowy
        else:
            self.progress_util.configure(progress_color="#ef4444")  # Czerwony
    
    def _prev_sheet(self):
        """Poprzedni arkusz"""
        self._display_sheet(self.current_sheet_index - 1)
    
    def _next_sheet(self):
        """Następny arkusz"""
        self._display_sheet(self.current_sheet_index + 1)

    def _zoom_in(self):
        """Obsługa przycisku Zoom In"""
        self.canvas.zoom_in()

    def _zoom_out(self):
        """Obsługa przycisku Zoom Out"""
        self.canvas.zoom_out()

    def _zoom_all(self):
        """Obsługa przycisku Zoom All"""
        self.canvas.zoom_all()

    def _zoom_fit(self):
        """Obsługa przycisku Zoom Fit"""
        self.canvas.zoom_fit()

    def _create_tooltip(self, widget, text):
        """Tworzy tooltip dla widgetu"""
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

    def set_result(self, nesting_result: 'NestingResult'):
        """Ustaw nowy wynik nestingu"""
        self.nesting_result = nesting_result
        self._generate_part_colors()
        self._populate_legend()
        self._update_total_stats()
        
        if self.nesting_result.sheets:
            self._display_sheet(0)


# ============================================================
# Standalone Test
# ============================================================

if __name__ == "__main__":
    from quotations.nesting.nester import Nester, Part, SheetFormat, STANDARD_SHEETS
    
    # Przykładowe dane
    parts = [
        Part("PLYTA_01", "Płyta główna", 400, 300, quantity=5),
        Part("WSPORNIK_A", "Wspornik A", 150, 80, quantity=20),
        Part("WSPORNIK_B", "Wspornik B", 200, 100, quantity=15),
        Part("UCHWYT", "Uchwyt mały", 50, 50, quantity=50),
        Part("OSLONA", "Osłona duża", 600, 400, quantity=3),
    ]
    
    sheet = STANDARD_SHEETS["1000x2000"]
    nester = Nester()
    result = nester.nest(parts, sheet)
    
    print(f"Wynik: {result.total_sheets} arkuszy, {result.total_parts} detali")
    
    # GUI
    ctk.set_appearance_mode("dark")
    
    root = ctk.CTk()
    root.withdraw()
    
    window = NestingVisualizerWindow(root, result, "Test wizualizacji")
    window.mainloop()
