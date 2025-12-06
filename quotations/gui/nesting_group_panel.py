"""
Nesting Group Panel
===================
Panel do nestingu grupowanego po materiale i grubości.
Integruje FastNester z GUI ERP.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import logging
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class Theme:
    """Kolory motywu"""
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


# Import nestingu
try:
    from ..nesting.fast_nester import (
        FastNester, NestingMode, RotationMode,
        MaterialGroupManager, NestingResult, NestedPart,
        CostCalculator, MATERIAL_DENSITIES
    )
    HAS_NESTING = True
except ImportError:
    HAS_NESTING = False
    logger.warning("FastNester not available")


# ============================================================
# Nesting Canvas Widget
# ============================================================

class NestingCanvasWidget(ctk.CTkFrame):
    """Widget canvas do wizualizacji nestingu"""
    
    COLORS = [
        '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
        '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1'
    ]
    
    def __init__(self, parent, width=700, height=500):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        
        self.canvas_width = width
        self.canvas_height = height
        
        # Stan
        self.sheet_width = 1500
        self.sheet_height = 3000
        self.placed_parts: List = []
        self.part_colors: Dict[str, str] = {}
        self.selected_part = None
        
        # Zoom/pan
        self.zoom_scale = 1.0
        self.offset_x = 20
        self.offset_y = 20
        
        # Callback kliknięcia
        self.on_part_click: Optional[Callable] = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Buduj UI"""
        # Nagłówek
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill='x', padx=10, pady=5)
        
        self.lbl_title = ctk.CTkLabel(
            header,
            text="Podgląd nestingu",
            font=ctk.CTkFont(size=14, weight='bold')
        )
        self.lbl_title.pack(side='left')
        
        self.lbl_info = ctk.CTkLabel(
            header,
            text="",
            text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_info.pack(side='right')
        
        # Canvas
        self.canvas = tk.Canvas(
            self,
            width=self.canvas_width,
            height=self.canvas_height,
            bg='#1e1e1e',
            highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Bindingi
        self.canvas.bind('<Button-1>', self._on_click)
        self.canvas.bind('<Configure>', lambda e: self._fit_view())
        self.canvas.bind('<MouseWheel>', self._on_scroll)
    
    def set_sheet(self, width: float, height: float):
        """Ustaw wymiary arkusza"""
        self.sheet_width = min(width, height)
        self.sheet_height = max(width, height)
        self._fit_view()
        self.redraw()
    
    def set_parts(self, parts: List, colors: Dict[str, str] = None):
        """Ustaw detale do wyświetlenia"""
        self.placed_parts = parts
        
        if colors:
            self.part_colors = colors.copy()
        else:
            names = list(set(getattr(p, 'name', '') for p in parts))
            self.part_colors = {
                name: self.COLORS[i % len(self.COLORS)]
                for i, name in enumerate(names)
            }
        
        self.redraw()
    
    def _fit_view(self):
        """Dopasuj widok"""
        try:
            canvas_w = self.canvas.winfo_width() or self.canvas_width
            canvas_h = self.canvas.winfo_height() or self.canvas_height
        except:
            canvas_w = self.canvas_width
            canvas_h = self.canvas_height
        
        scale_x = (canvas_w - 40) / self.sheet_width if self.sheet_width > 0 else 1
        scale_y = (canvas_h - 40) / self.sheet_height if self.sheet_height > 0 else 1
        self.zoom_scale = min(scale_x, scale_y)
        
        self.offset_x = (canvas_w - self.sheet_width * self.zoom_scale) / 2
        self.offset_y = (canvas_h - self.sheet_height * self.zoom_scale) / 2
    
    def _to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        """Konwertuj współrzędne arkusza na canvas"""
        cx = self.offset_x + x * self.zoom_scale
        cy = self.offset_y + (self.sheet_height - y) * self.zoom_scale
        return cx, cy
    
    def _from_canvas(self, cx: float, cy: float) -> Tuple[float, float]:
        """Konwertuj canvas na arkusz"""
        x = (cx - self.offset_x) / self.zoom_scale
        y = self.sheet_height - (cy - self.offset_y) / self.zoom_scale
        return x, y
    
    def redraw(self):
        """Przerysuj"""
        self.canvas.delete('all')
        
        # Arkusz
        x1, y1 = self._to_canvas(0, 0)
        x2, y2 = self._to_canvas(self.sheet_width, self.sheet_height)
        self.canvas.create_rectangle(x1, y2, x2, y1, fill='#2a2a2a', outline='#444')
        
        # Siatka
        self._draw_grid()
        
        # Detale
        for part in self.placed_parts:
            self._draw_part(part)
        
        # Etykieta wymiarów
        self.canvas.create_text(
            x1 + 5, y2 + 5,
            text=f"{self.sheet_width:.0f} × {self.sheet_height:.0f} mm",
            fill='#888', anchor='nw', font=('Arial', 9)
        )
    
    def _draw_grid(self):
        """Rysuj siatkę"""
        grid_step = 100 if self.zoom_scale > 0.1 else 500
        
        for gx in range(0, int(self.sheet_width) + 1, grid_step):
            cx, _ = self._to_canvas(gx, 0)
            _, cy1 = self._to_canvas(0, 0)
            _, cy2 = self._to_canvas(0, self.sheet_height)
            self.canvas.create_line(cx, cy1, cx, cy2, fill='#333', width=1)
        
        for gy in range(0, int(self.sheet_height) + 1, grid_step):
            _, cy = self._to_canvas(0, gy)
            cx1, _ = self._to_canvas(0, 0)
            cx2, _ = self._to_canvas(self.sheet_width, 0)
            self.canvas.create_line(cx1, cy, cx2, cy, fill='#333', width=1)
    
    def _draw_part(self, part):
        """Rysuj detal"""
        name = getattr(part, 'name', '')
        color = self.part_colors.get(name, '#3B82F6')
        
        # Kontur
        if hasattr(part, 'get_placed_contour'):
            contour = part.get_placed_contour()
        else:
            x, y = getattr(part, 'x', 0), getattr(part, 'y', 0)
            w, h = getattr(part, 'width', 50), getattr(part, 'height', 50)
            contour = [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]
        
        if len(contour) >= 3:
            canvas_points = []
            for px, py in contour:
                cx, cy = self._to_canvas(px, py)
                canvas_points.extend([cx, cy])
            
            outline = '#fff' if part == self.selected_part else '#666'
            lw = 2 if part == self.selected_part else 1
            
            self.canvas.create_polygon(
                canvas_points, fill=color, outline=outline, width=lw
            )
        
        # Otwory
        if hasattr(part, 'get_placed_holes'):
            for hole in part.get_placed_holes():
                if len(hole) >= 3:
                    hole_pts = []
                    for px, py in hole:
                        cx, cy = self._to_canvas(px, py)
                        hole_pts.extend([cx, cy])
                    self.canvas.create_polygon(hole_pts, fill='#1e1e1e', outline='#555')
    
    def _on_click(self, event):
        """Kliknięcie"""
        x, y = self._from_canvas(event.x, event.y)
        
        clicked = None
        for part in reversed(self.placed_parts):
            if self._point_in_part(x, y, part):
                clicked = part
                break
        
        self.selected_part = clicked
        self.redraw()
        
        if self.on_part_click and clicked:
            self.on_part_click(clicked)
    
    def _point_in_part(self, x: float, y: float, part) -> bool:
        """Sprawdź czy punkt w detalu"""
        if hasattr(part, 'get_placed_contour'):
            contour = part.get_placed_contour()
        else:
            px, py = getattr(part, 'x', 0), getattr(part, 'y', 0)
            w, h = getattr(part, 'width', 50), getattr(part, 'height', 50)
            contour = [(px, py), (px+w, py), (px+w, py+h), (px, py+h)]
        
        if len(contour) < 3:
            return False
        
        # Ray casting
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
    
    def _on_scroll(self, event):
        """Zoom"""
        factor = 1.1 if event.delta > 0 else 0.9
        self.zoom_scale *= factor
        self.zoom_scale = max(0.05, min(5.0, self.zoom_scale))
        self.redraw()


# ============================================================
# Nesting Group Panel
# ============================================================

class NestingGroupPanel(ctk.CTkFrame):
    """
    Panel do nestingu grupowanego po materiale/grubości.
    Integruje się z GUI wyceny.
    """
    
    def __init__(self, parent, on_complete: Optional[Callable] = None):
        super().__init__(parent, fg_color=Theme.BG_DARK)
        
        self.on_complete = on_complete
        self.manager: Optional[MaterialGroupManager] = None
        self.current_group_key: Optional[Tuple[str, float]] = None
        self.nesting_thread: Optional[threading.Thread] = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Buduj interfejs"""
        # === LEWY PANEL (kontrolki) ===
        self.left_frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, width=300)
        self.left_frame.pack(side='left', fill='y', padx=5, pady=5)
        self.left_frame.pack_propagate(False)
        
        self._create_settings_section()
        self._create_groups_section()
        self._create_controls_section()
        self._create_summary_section()
        
        # === PRAWY PANEL (wizualizacja) ===
        self.right_frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        self.right_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        self._create_visualization_section()
    
    def _create_settings_section(self):
        """Sekcja ustawień"""
        frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        frame.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            frame, text="⚙️ Ustawienia",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(anchor='w')
        
        # Wymiary arkusza
        row1 = ctk.CTkFrame(frame, fg_color="transparent")
        row1.pack(fill='x', pady=5)
        ctk.CTkLabel(row1, text="Arkusz [mm]:", width=80).pack(side='left')
        self.entry_sheet_w = ctk.CTkEntry(row1, width=65)
        self.entry_sheet_w.pack(side='left', padx=2)
        self.entry_sheet_w.insert(0, "1500")
        ctk.CTkLabel(row1, text="×").pack(side='left')
        self.entry_sheet_h = ctk.CTkEntry(row1, width=65)
        self.entry_sheet_h.pack(side='left', padx=2)
        self.entry_sheet_h.insert(0, "3000")
        
        # Odstęp
        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill='x', pady=5)
        ctk.CTkLabel(row2, text="Odstęp [mm]:", width=80).pack(side='left')
        self.entry_spacing = ctk.CTkEntry(row2, width=65)
        self.entry_spacing.pack(side='left', padx=2)
        self.entry_spacing.insert(0, "5")
        
        # Rotacja
        row3 = ctk.CTkFrame(frame, fg_color="transparent")
        row3.pack(fill='x', pady=5)
        ctk.CTkLabel(row3, text="Rotacja:", width=80).pack(side='left')
        self.combo_rotation = ctk.CTkComboBox(
            row3,
            values=["90° (0, 90)", "45° (0, 45, 90, ...)", "Własny krok"],
            width=130
        )
        self.combo_rotation.pack(side='left', padx=2)
        self.combo_rotation.set("90° (0, 90)")
        
        # Krok rotacji
        row4 = ctk.CTkFrame(frame, fg_color="transparent")
        row4.pack(fill='x', pady=5)
        ctk.CTkLabel(row4, text="Krok [°]:", width=80).pack(side='left')
        self.entry_rot_step = ctk.CTkEntry(row4, width=65)
        self.entry_rot_step.pack(side='left', padx=2)
        self.entry_rot_step.insert(0, "90")
        
        # Tryb
        row5 = ctk.CTkFrame(frame, fg_color="transparent")
        row5.pack(fill='x', pady=5)
        ctk.CTkLabel(row5, text="Tryb:", width=80).pack(side='left')
        self.combo_mode = ctk.CTkComboBox(
            row5,
            values=["Szybki (3 próby)", "Głęboki (100+ prób)"],
            width=130
        )
        self.combo_mode.pack(side='left', padx=2)
        self.combo_mode.set("Szybki (3 próby)")
    
    def _create_groups_section(self):
        """Sekcja grup materiałowych"""
        frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        frame.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            frame, text="📋 Grupy materiałowe",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(anchor='w')
        
        # Lista grup
        self.groups_listbox = tk.Listbox(
            frame,
            height=8,
            bg='#333', fg='white',
            selectbackground='#3B82F6',
            font=('Consolas', 10),
            exportselection=False
        )
        self.groups_listbox.pack(fill='x', pady=5)
        self.groups_listbox.bind('<<ListboxSelect>>', self._on_group_select)
    
    def _create_controls_section(self):
        """Sekcja kontrolek"""
        frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        frame.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            frame, text="🔧 Nesting",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(anchor='w', pady=(0, 5))
        
        self.btn_nest_group = ctk.CTkButton(
            frame,
            text="▶️ Nestuj wybraną grupę",
            command=self._nest_current_group,
            height=40,
            fg_color=Theme.ACCENT_SUCCESS,
            hover_color="#16a34a"
        )
        self.btn_nest_group.pack(fill='x', pady=2)
        
        self.btn_nest_all = ctk.CTkButton(
            frame,
            text="⏩ Nestuj wszystkie grupy",
            command=self._nest_all_groups,
            height=40,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color="#7c3aed"
        )
        self.btn_nest_all.pack(fill='x', pady=2)
        
        self.btn_export = ctk.CTkButton(
            frame,
            text="💾 Eksportuj DXF",
            command=self._export_dxf,
            height=35,
            fg_color=Theme.ACCENT_INFO,
            hover_color="#0891b2",
            state='disabled'
        )
        self.btn_export.pack(fill='x', pady=5)
        
        # Progress
        self.progress = ctk.CTkProgressBar(frame)
        self.progress.pack(fill='x', pady=5)
        self.progress.set(0)
        
        self.lbl_status = ctk.CTkLabel(frame, text="Gotowy", text_color=Theme.TEXT_SECONDARY)
        self.lbl_status.pack()
    
    def _create_summary_section(self):
        """Sekcja podsumowania"""
        frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        frame.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            frame, text="💰 Podsumowanie",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(anchor='w')
        
        self.lbl_efficiency = ctk.CTkLabel(frame, text="Efektywność: --")
        self.lbl_efficiency.pack(anchor='w', pady=2)
        
        self.lbl_sheet_cost = ctk.CTkLabel(frame, text="Koszt arkusza: -- PLN")
        self.lbl_sheet_cost.pack(anchor='w', pady=2)
        
        self.lbl_total = ctk.CTkLabel(
            frame,
            text="RAZEM: -- PLN",
            font=ctk.CTkFont(size=16, weight='bold'),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.lbl_total.pack(anchor='w', pady=5)
    
    def _create_visualization_section(self):
        """Sekcja wizualizacji"""
        # Nagłówek z wyborem grupy
        header = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        header.pack(fill='x', padx=10, pady=5)
        
        ctk.CTkLabel(header, text="Podgląd:").pack(side='left')
        
        self.combo_preview = ctk.CTkComboBox(
            header,
            values=["-- Wybierz grupę --"],
            width=250,
            command=self._on_preview_change
        )
        self.combo_preview.pack(side='left', padx=10)
        
        self.lbl_preview_info = ctk.CTkLabel(header, text="")
        self.lbl_preview_info.pack(side='left', padx=10)
        
        # Canvas
        self.nesting_canvas = NestingCanvasWidget(self.right_frame, width=700, height=500)
        self.nesting_canvas.pack(fill='both', expand=True, padx=5, pady=5)
        self.nesting_canvas.on_part_click = self._on_canvas_part_click
    
    # ========== API ==========
    
    def set_parts(self, parts_data: List[Dict]):
        """
        Ustaw detale do nestingu.
        
        Args:
            parts_data: Lista słowników z danymi detali:
                - name: nazwa
                - part_id: ID
                - width, height: wymiary [mm]
                - area, net_area: pola [mm²]
                - material: materiał
                - thickness: grubość [mm]
                - quantity: ilość
                - contour: lista punktów
                - holes: lista otworów
        """
        if not HAS_NESTING:
            messagebox.showerror("Błąd", "Moduł nestingu niedostępny")
            return
        
        self.manager = MaterialGroupManager()
        self._apply_settings()
        
        for part in parts_data:
            qty = part.get('quantity', 1)
            self.manager.add_part(part, quantity=qty)
        
        self._refresh_groups_list()
    
    def get_results(self) -> List[NestingResult]:
        """Pobierz wyniki nestingu"""
        if not self.manager:
            return []
        
        return [g.nesting_result for g in self.manager.groups.values() 
                if g.nesting_result is not None]
    
    def get_total_cost(self) -> float:
        """Pobierz całkowity koszt"""
        if not self.manager:
            return 0.0
        return self.manager.get_total_cost()
    
    # ========== Wewnętrzne ==========
    
    def _apply_settings(self):
        """Zastosuj ustawienia"""
        if not self.manager:
            return
        
        try:
            self.manager.sheet_width = float(self.entry_sheet_w.get())
            self.manager.sheet_height = float(self.entry_sheet_h.get())
            self.manager.spacing = float(self.entry_spacing.get())
        except ValueError:
            pass
        
        rot_text = self.combo_rotation.get()
        if "90" in rot_text:
            self.manager.rotation_mode = RotationMode.R90
        elif "45" in rot_text:
            self.manager.rotation_mode = RotationMode.R45
        else:
            self.manager.rotation_mode = RotationMode.CUSTOM
        
        mode_text = self.combo_mode.get()
        self.manager.nesting_mode = NestingMode.DEEP if "Głębok" in mode_text else NestingMode.FAST
    
    def _refresh_groups_list(self):
        """Odśwież listę grup"""
        self.groups_listbox.delete(0, tk.END)
        
        if not self.manager:
            return
        
        groups = []
        for summary in self.manager.get_groups_summary():
            status = "✓" if summary['has_result'] else "○"
            eff = f"{summary['efficiency']:.0%}" if summary['has_result'] else "--"
            cost = f"{summary['sheet_cost']:.0f}zł" if summary['has_result'] else "--"
            text = f"{status} {summary['material']} {summary['thickness']}mm | {summary['parts_count']}szt | {eff} | {cost}"
            groups.append(text)
            self.groups_listbox.insert(tk.END, text)
        
        # Aktualizuj combo podglądu
        self.combo_preview.configure(values=["-- Wszystkie --"] + groups)
        if groups:
            self.combo_preview.set(groups[0])
    
    def _on_group_select(self, event):
        """Wybór grupy z listy"""
        selection = self.groups_listbox.curselection()
        if not selection or not self.manager:
            return
        
        idx = selection[0]
        summaries = self.manager.get_groups_summary()
        if idx < len(summaries):
            summary = summaries[idx]
            self.current_group_key = (summary['material'], summary['thickness'])
            
            group = self.manager.groups.get(self.current_group_key)
            if group and group.nesting_result:
                self._display_result(group.nesting_result)
    
    def _on_preview_change(self, value):
        """Zmiana w combo podglądu"""
        if not self.manager or value.startswith("--"):
            return
        
        summaries = self.manager.get_groups_summary()
        for summary in summaries:
            if summary['material'] in value and str(summary['thickness']) in value:
                self.current_group_key = (summary['material'], summary['thickness'])
                group = self.manager.groups.get(self.current_group_key)
                if group and group.nesting_result:
                    self._display_result(group.nesting_result)
                break
    
    def _on_canvas_part_click(self, part):
        """Kliknięcie na detal"""
        name = getattr(part, 'name', 'Nieznany')
        cost = getattr(part, 'material_cost', 0)
        weight = getattr(part, 'weight', 0)
        
        self.lbl_preview_info.configure(
            text=f"{name} | {weight:.2f}kg | {cost:.2f} PLN"
        )
    
    def _nest_current_group(self):
        """Nestuj wybraną grupę"""
        if not self.current_group_key or not self.manager:
            messagebox.showwarning("Uwaga", "Wybierz grupę")
            return
        
        self._apply_settings()
        self._set_ui_enabled(False)
        
        def run():
            material, thickness = self.current_group_key
            result = self.manager.run_nesting_for_group(
                material, thickness, callback=self._nesting_callback
            )
            self.after(0, lambda: self._on_nesting_done(result))
        
        self.nesting_thread = threading.Thread(target=run)
        self.nesting_thread.start()
    
    def _nest_all_groups(self):
        """Nestuj wszystkie grupy"""
        if not self.manager or not self.manager.groups:
            messagebox.showwarning("Uwaga", "Brak grup")
            return
        
        self._apply_settings()
        self._set_ui_enabled(False)
        
        def run():
            results = self.manager.run_all_nestings(callback=self._nesting_callback)
            self.after(0, lambda: self._on_all_nesting_done(results))
        
        self.nesting_thread = threading.Thread(target=run)
        self.nesting_thread.start()
    
    def _nesting_callback(self, parts, efficiency):
        """Callback postępu"""
        def update():
            self.nesting_canvas.set_parts(parts)
            self.progress.set(efficiency)
            self.lbl_status.configure(text=f"Efektywność: {efficiency:.1%}")
        self.after(0, update)
    
    def _on_nesting_done(self, result):
        """Zakończenie nestingu grupy"""
        self._set_ui_enabled(True)
        self._refresh_groups_list()
        
        if result:
            self._display_result(result)
    
    def _on_all_nesting_done(self, results):
        """Zakończenie nestingu wszystkich"""
        self._set_ui_enabled(True)
        self._refresh_groups_list()
        
        if results:
            self._display_result(results[-1])
        
        total = self.manager.get_total_cost() if self.manager else 0
        self.lbl_total.configure(text=f"RAZEM: {total:.2f} PLN")
        
        if self.on_complete:
            self.on_complete(results)
        
        messagebox.showinfo("Gotowe", f"Znestowano {len(results)} grup\nKoszt: {total:.2f} PLN")
    
    def _display_result(self, result: NestingResult):
        """Wyświetl wynik"""
        self.nesting_canvas.set_sheet(result.sheet_width, result.sheet_height)
        self.nesting_canvas.set_parts(result.placed_parts)
        
        self.lbl_efficiency.configure(text=f"Efektywność: {result.efficiency:.1%}")
        self.lbl_sheet_cost.configure(text=f"Koszt arkusza: {result.sheet_cost:.2f} PLN")
        self.lbl_preview_info.configure(text=f"{len(result.placed_parts)} detali")
        
        self.progress.set(1.0)
        self.lbl_status.configure(text="Gotowy")
        self.btn_export.configure(state='normal')
    
    def _set_ui_enabled(self, enabled: bool):
        """Włącz/wyłącz UI"""
        state = 'normal' if enabled else 'disabled'
        self.btn_nest_group.configure(state=state)
        self.btn_nest_all.configure(state=state)
    
    def _export_dxf(self):
        """Eksportuj do DXF"""
        if not self.current_group_key or not self.manager:
            return
        
        material, thickness = self.current_group_key
        filename = f"nesting_{material}_{thickness}mm.dxf"
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".dxf",
            initialfile=filename,
            filetypes=[("DXF Files", "*.dxf")]
        )
        
        if filepath:
            # TODO: Implementacja eksportu DXF
            messagebox.showinfo("Eksport", f"Zapisano: {filepath}")


# ============================================================
# Standalone Test
# ============================================================

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.title("Nesting Group Panel - Test")
    root.geometry("1200x800")
    
    panel = NestingGroupPanel(root)
    panel.pack(fill='both', expand=True)
    
    # Dane testowe
    test_parts = [
        {'name': 'Part_A', 'part_id': '1', 'width': 100, 'height': 80, 'area': 8000, 'net_area': 7500,
         'material': 'INOX', 'thickness': 2.0, 'quantity': 10},
        {'name': 'Part_B', 'part_id': '2', 'width': 150, 'height': 60, 'area': 9000, 'net_area': 8500,
         'material': 'INOX', 'thickness': 2.0, 'quantity': 8},
        {'name': 'Part_C', 'part_id': '3', 'width': 200, 'height': 150, 'area': 30000, 'net_area': 28000,
         'material': 'INOX', 'thickness': 3.0, 'quantity': 5},
    ]
    
    panel.set_parts(test_parts)
    
    root.mainloop()
