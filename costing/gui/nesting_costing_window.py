"""
Nesting Costing Window - Full-screen costing GUI.

3-panel layout:
- Left: Source selection + parts list
- Middle: Sheets preview + LOG
- Right: Cost parameters + results

Based on costing.md specification.
"""

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog, Canvas
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import threading
import logging
import json
import re
import math

logger = logging.getLogger(__name__)


class Theme:
    """Color palette"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_CARD_HOVER = "#252525"
    BG_INPUT = "#2d2d2d"
    BG_SELECTED = "#3b3b3b"

    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#666666"

    ACCENT_PRIMARY = "#3b82f6"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"
    ACCENT_INFO = "#06b6d4"
    ACCENT_PURPLE = "#8b5cf6"


# =============================================================================
# Material/Thickness Parser
# =============================================================================

def parse_material_from_filename(filename: str) -> Tuple[str, float]:
    """
    Parse material and thickness from DXF filename.

    Examples:
        11-059654_INOX304_2mm_1szt -> (INOX304, 2.0)
        11-057621_S355_3mm_15szt -> (S355, 3.0)
        part_AL_1.5mm -> (AL, 1.5)
    """
    name = Path(filename).stem.upper()

    # Known materials
    materials = ['INOX304', 'INOX', '1.4301', '1.4404', 'S355', 'S235', 'DC01', 'DC04',
                 'AL', 'ALU', 'ALUMINIUM', 'HARDOX', 'CU', 'BRASS']

    found_material = 'S355'  # Default
    found_thickness = 2.0    # Default

    # Find material
    for mat in materials:
        if mat in name:
            found_material = mat
            # Normalize INOX variants
            if 'INOX' in mat:
                found_material = '1.4301'
            break

    # Find thickness (patterns: 2mm, 2.0mm, 2,0mm, 1.5mm, 1,5mm)
    thickness_patterns = [
        r'(\d+[.,]\d+)\s*mm',  # 2.0mm or 2,0mm
        r'(\d+)\s*mm',          # 2mm
        r'_(\d+[.,]\d+)_',      # _2.0_
        r'_(\d+)_',             # _2_
    ]

    for pattern in thickness_patterns:
        match = re.search(pattern, name)
        if match:
            thickness_str = match.group(1).replace(',', '.')
            try:
                found_thickness = float(thickness_str)
                break
            except ValueError:
                pass

    return found_material, found_thickness


# =============================================================================
# Log Panel
# =============================================================================

class LogPanel(ctk.CTkFrame):
    """Panel showing calculation log."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=Theme.BG_INPUT, corner_radius=8)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            header,
            text="LOG OBLICZEN",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.ACCENT_INFO
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Wyczysc",
            width=60,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            command=self.clear
        ).pack(side="right")

        # Text area
        self.text = ctk.CTkTextbox(
            self,
            fg_color=Theme.BG_DARK,
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="word"
        )
        self.text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def log(self, message: str, level: str = "INFO"):
        """Add log message."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        color_map = {
            "INFO": Theme.TEXT_SECONDARY,
            "CALC": Theme.ACCENT_INFO,
            "RESULT": Theme.ACCENT_SUCCESS,
            "WARN": Theme.ACCENT_WARNING,
            "ERROR": Theme.ACCENT_DANGER
        }

        prefix = f"[{timestamp}] [{level}] "
        self.text.insert("end", prefix + message + "\n")
        self.text.see("end")

    def clear(self):
        """Clear log."""
        self.text.delete("1.0", "end")


# =============================================================================
# Sheet Preview Canvas
# =============================================================================

class SheetPreviewCanvas(ctk.CTkFrame):
    """Canvas showing sheet layout preview."""

    PART_COLORS = [
        "#8b5cf6", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4",
        "#ec4899", "#84cc16", "#f97316", "#6366f1", "#14b8a6"
    ]

    def __init__(self, parent, width: int = 400, height: int = 300):
        super().__init__(parent, fg_color=Theme.BG_INPUT, corner_radius=8)

        self.canvas_width = width
        self.canvas_height = height
        self.sheet_width = 1500
        self.sheet_length = 3000
        self.parts: List[Dict] = []

        self.canvas = Canvas(
            self,
            width=width,
            height=height,
            bg=Theme.BG_DARK,
            highlightthickness=0
        )
        self.canvas.pack(padx=10, pady=10)

        self._draw_empty()

    def _draw_empty(self):
        """Draw empty state."""
        self.canvas.delete("all")
        self.canvas.create_text(
            self.canvas_width // 2,
            self.canvas_height // 2,
            text="Podglad arkusza",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 12)
        )

    def set_sheet(self, width_mm: float, length_mm: float, parts: List[Dict]):
        """Set sheet data and redraw."""
        self.sheet_width = width_mm
        self.sheet_length = length_mm
        self.parts = parts
        self._draw()

    def _draw(self, **kwargs):
        """Draw sheet with parts."""
        self.canvas.delete("all")

        if not self.parts:
            self._draw_empty()
            return

        # Calculate scale
        margin = 20
        available_w = self.canvas_width - 2 * margin
        available_h = self.canvas_height - 2 * margin

        scale_x = available_w / self.sheet_width
        scale_y = available_h / self.sheet_length
        scale = min(scale_x, scale_y)

        # Sheet dimensions on canvas
        sheet_w = self.sheet_width * scale
        sheet_h = self.sheet_length * scale

        offset_x = (self.canvas_width - sheet_w) / 2
        offset_y = (self.canvas_height - sheet_h) / 2

        # Draw sheet background
        self.canvas.create_rectangle(
            offset_x, offset_y,
            offset_x + sheet_w, offset_y + sheet_h,
            fill="#1a1a1a",
            outline=Theme.TEXT_MUTED,
            width=2
        )

        # Draw parts (simple rectangles based on occupied area)
        x_pos = 10
        y_pos = 10
        row_height = 0

        for i, part in enumerate(self.parts):
            color = self.PART_COLORS[i % len(self.PART_COLORS)]

            # Estimate part size from occupied area
            area = part.get('occupied_area_mm2', 10000)
            side = math.sqrt(area)

            part_w = side * scale
            part_h = side * scale

            # Simple row-based placement
            if x_pos + part_w > sheet_w - 10:
                x_pos = 10
                y_pos += row_height + 5
                row_height = 0

            if y_pos + part_h > sheet_h - 10:
                break  # No more space

            # Draw part
            px = offset_x + x_pos
            py = offset_y + y_pos

            self.canvas.create_rectangle(
                px, py,
                px + part_w, py + part_h,
                fill=color,
                outline="#ffffff",
                width=1
            )

            x_pos += part_w + 5
            row_height = max(row_height, part_h)

        # Draw dimensions
        self.canvas.create_text(
            offset_x + sheet_w / 2,
            offset_y + sheet_h + 12,
            text=f"{self.sheet_width:.0f} mm",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 9)
        )

        self.canvas.create_text(
            offset_x - 12,
            offset_y + sheet_h / 2,
            text=f"{self.sheet_length:.0f}",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 9),
            angle=90
        )


# =============================================================================
# Left Panel - Source & Parts
# =============================================================================

class SourcePartsPanel(ctk.CTkFrame):
    """Left panel: source selection and parts list."""

    def __init__(self, parent, on_source_changed: Callable = None, on_parts_loaded: Callable = None):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        self.on_source_changed = on_source_changed
        self.on_parts_loaded = on_parts_loaded
        self.parts_data: List[Dict] = []

        self._setup_ui()

    def _setup_ui(self):
        """Build UI components."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header,
            text="Zrodlo danych",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w")

        # Source type selector
        source_frame = ctk.CTkFrame(self, fg_color="transparent")
        source_frame.pack(fill="x", padx=15, pady=5)

        self.source_type_var = ctk.StringVar(value="order")

        ctk.CTkRadioButton(
            source_frame,
            text="Zamowienie",
            variable=self.source_type_var,
            value="order",
            command=self._on_source_type_changed,
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(side="left", padx=(0, 20))

        ctk.CTkRadioButton(
            source_frame,
            text="Oferta",
            variable=self.source_type_var,
            value="quotation",
            command=self._on_source_type_changed,
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(side="left")

        # Source selector (dropdown)
        selector_frame = ctk.CTkFrame(self, fg_color="transparent")
        selector_frame.pack(fill="x", padx=15, pady=10)

        self.source_selector = ctk.CTkComboBox(
            selector_frame,
            values=["-- Wybierz --"],
            width=250,
            height=35,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BG_INPUT,
            button_color=Theme.ACCENT_PRIMARY,
            dropdown_fg_color=Theme.BG_CARD,
            command=self._on_source_selected
        )
        self.source_selector.pack(fill="x")

        # Search entry
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)

        search_entry = ctk.CTkEntry(
            selector_frame,
            textvariable=self.search_var,
            placeholder_text="Szukaj...",
            height=35,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BG_INPUT
        )
        search_entry.pack(fill="x", pady=(10, 0))

        # Divider
        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=15, pady=10)

        # Parts list header
        parts_header = ctk.CTkFrame(self, fg_color="transparent")
        parts_header.pack(fill="x", padx=15, pady=(0, 5))

        # Collapse/expand button
        self.is_collapsed = False
        self.toggle_btn = ctk.CTkButton(
            parts_header,
            text="v",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=Theme.BG_INPUT,
            font=ctk.CTkFont(size=12),
            command=self._toggle_parts_list
        )
        self.toggle_btn.pack(side="left")

        ctk.CTkLabel(
            parts_header,
            text="Lista detali",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left")

        self.parts_count_label = ctk.CTkLabel(
            parts_header,
            text="(0)",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.parts_count_label.pack(side="left", padx=5)

        # Collapse info label (shown when collapsed)
        self.collapse_info_label = ctk.CTkLabel(
            parts_header,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED
        )
        self.collapse_info_label.pack(side="right")

        # Parts list container (for collapse functionality)
        self.parts_container = ctk.CTkFrame(self, fg_color="transparent")
        self.parts_container.pack(fill="both", expand=True, padx=0, pady=0)

        # Parts list (scrollable)
        self.parts_scroll = ctk.CTkScrollableFrame(
            self.parts_container,
            fg_color="transparent",
            scrollbar_button_color=Theme.BG_INPUT
        )
        self.parts_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Buttons
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            buttons_frame,
            text="Odswiez",
            width=100,
            height=32,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._refresh_parts
        ).pack(side="left")

        ctk.CTkButton(
            buttons_frame,
            text="Zaladuj DXF",
            width=100,
            height=32,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color=Theme.ACCENT_INFO,
            command=self._load_dxf_folder
        ).pack(side="right")

    def _on_source_type_changed(self):
        """Handle source type change."""
        source_type = self.source_type_var.get()
        logger.info(f"Source type changed to: {source_type}")
        if self.on_source_changed:
            self.on_source_changed(source_type, None)

    def _on_source_selected(self, selection: str):
        """Handle source selection."""
        logger.info(f"Source selected: {selection}")
        if self.on_source_changed:
            self.on_source_changed(self.source_type_var.get(), selection)

    def _on_search_changed(self, *args):
        """Filter parts by search term."""
        search_term = self.search_var.get().lower()
        self._update_parts_display(search_term)

    def _update_parts_display(self, search_term: str = ""):
        """Update parts list display."""
        # Clear existing
        for widget in self.parts_scroll.winfo_children():
            widget.destroy()

        filtered = self.parts_data
        if search_term:
            filtered = [
                p for p in self.parts_data
                if search_term in p.get('name', '').lower()
                or search_term in p.get('idx_code', '').lower()
            ]

        self.parts_count_label.configure(text=f"({len(filtered)})")

        for part in filtered:
            self._create_part_row(part)

    def _create_part_row(self, part: Dict):
        """Create a row for a single part."""
        row = ctk.CTkFrame(
            self.parts_scroll,
            fg_color=Theme.BG_INPUT,
            corner_radius=6,
            height=60
        )
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        # Content
        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=8)

        # Left: idx_code + name
        left = ctk.CTkFrame(content, fg_color="transparent")
        left.pack(side="left", fill="y")

        ctk.CTkLabel(
            left,
            text=part.get('idx_code', 'N/A'),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w")

        ctk.CTkLabel(
            left,
            text=part.get('name', 'Bez nazwy')[:30],
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w")

        # Right: material, thickness, qty
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.pack(side="right", fill="y")

        material = part.get('material', '?')
        thickness = part.get('thickness_mm', 0)
        qty = part.get('qty', 1)

        ctk.CTkLabel(
            right,
            text=f"{material} {thickness}mm",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="e")

        ctk.CTkLabel(
            right,
            text=f"x{qty}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.ACCENT_SUCCESS
        ).pack(anchor="e")

    def _refresh_parts(self):
        """Refresh parts list."""
        logger.info("Refreshing parts list")
        self._update_parts_display(self.search_var.get().lower())

    def _load_dxf_folder(self):
        """Load DXF files from folder."""
        folder = filedialog.askdirectory(title="Wybierz folder z plikami DXF")
        if not folder:
            return

        folder_path = Path(folder)
        dxf_files = list(set(folder_path.rglob("*.dxf")) | set(folder_path.rglob("*.DXF")))

        if not dxf_files:
            messagebox.showwarning("Brak plikow", "Nie znaleziono plikow DXF w wybranym folderze.")
            return

        logger.info(f"Found {len(dxf_files)} DXF files in {folder}")

        # Create parts from DXF files with material/thickness parsing
        self.parts_data = []
        for dxf in dxf_files:
            material, thickness = parse_material_from_filename(dxf.name)

            self.parts_data.append({
                'part_id': str(dxf),
                'idx_code': dxf.stem,
                'name': dxf.stem,
                'material': material,
                'thickness_mm': thickness,
                'qty': 1,
                'dxf_path': str(dxf)
            })

        self._update_parts_display()

        # Auto-expand when new parts are loaded
        self.expand_parts_list()

        if self.on_parts_loaded:
            self.on_parts_loaded(self.parts_data)

        messagebox.showinfo("Zaladowano", f"Zaladowano {len(dxf_files)} plikow DXF.")

    def set_parts(self, parts: List[Dict]):
        """Set parts data."""
        self.parts_data = parts
        self._update_parts_display()
        # Auto-expand when new parts are added
        self.expand_parts_list()

    def _toggle_parts_list(self):
        """Toggle parts list collapse/expand."""
        if self.is_collapsed:
            self.expand_parts_list()
        else:
            self.collapse_parts_list()

    def collapse_parts_list(self):
        """Collapse the parts list to save space."""
        if self.is_collapsed:
            return

        self.is_collapsed = True
        self.toggle_btn.configure(text=">")

        # Hide the parts container
        self.parts_container.pack_forget()

        # Show summary info
        if self.parts_data:
            materials = set(f"{p['material']}/{p['thickness_mm']}mm" for p in self.parts_data)
            self.collapse_info_label.configure(
                text=f"[zwiniete] {len(self.parts_data)} detali, {len(materials)} mat."
            )
        else:
            self.collapse_info_label.configure(text="[zwiniete]")

    def expand_parts_list(self):
        """Expand the parts list."""
        if not self.is_collapsed:
            return

        self.is_collapsed = False
        self.toggle_btn.configure(text="v")

        # Show the parts container
        self.parts_container.pack(fill="both", expand=True, padx=0, pady=0)

        # Hide summary info
        self.collapse_info_label.configure(text="")


# =============================================================================
# Middle Panel - Sheets
# =============================================================================

class SheetsPanel(ctk.CTkFrame):
    """Middle panel: sheets list, preview and log."""

    def __init__(self, parent, on_run_nesting: Callable = None, log_callback: Callable = None):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        self.on_run_nesting = on_run_nesting
        self.log_callback = log_callback
        self.sheets_data: List[Dict] = []
        self.selected_sheet_idx = 0

        self._setup_ui()

    def _setup_ui(self):
        """Build UI components."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header,
            text="Arkusze",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left")

        self.sheets_count_label = ctk.CTkLabel(
            header,
            text="(0)",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.sheets_count_label.pack(side="left", padx=5)

        # Buttons
        ctk.CTkButton(
            header,
            text="Uruchom Nesting",
            width=130,
            height=32,
            fg_color=Theme.ACCENT_SUCCESS,
            hover_color="#1ea34a",
            command=self._run_nesting
        ).pack(side="right")

        # Sheets list
        self.sheets_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=120,
            scrollbar_button_color=Theme.BG_INPUT
        )
        self.sheets_scroll.pack(fill="x", padx=10, pady=(0, 10))

        # Preview canvas
        self.preview = SheetPreviewCanvas(self, width=450, height=250)
        self.preview.pack(padx=10, pady=(0, 5))

        # Sheet stats
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=15, pady=(0, 5))

        self.stats_label = ctk.CTkLabel(
            stats_frame,
            text="Utylizacja: -- | Detali: -- | Dlugosc ciecia: --",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.stats_label.pack(anchor="w")

        # Dynamics info frame
        dynamics_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=6)
        dynamics_frame.pack(fill="x", padx=10, pady=(5, 5))

        dynamics_header = ctk.CTkFrame(dynamics_frame, fg_color="transparent")
        dynamics_header.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            dynamics_header,
            text="ANALIZA DYNAMIKI",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=Theme.ACCENT_INFO
        ).pack(side="left")

        # Dynamics stats
        dynamics_stats = ctk.CTkFrame(dynamics_frame, fg_color="transparent")
        dynamics_stats.pack(fill="x", padx=10, pady=(0, 5))

        # Contours count
        ctk.CTkLabel(
            dynamics_stats,
            text="Kontury:",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")

        self.contours_label = ctk.CTkLabel(
            dynamics_stats,
            text="--",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=Theme.ACCENT_WARNING
        )
        self.contours_label.pack(side="left", padx=(5, 15))

        # Short segments
        ctk.CTkLabel(
            dynamics_stats,
            text="Krotkie seg.:",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")

        self.short_seg_label = ctk.CTkLabel(
            dynamics_stats,
            text="--%",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=Theme.ACCENT_DANGER
        )
        self.short_seg_label.pack(side="left", padx=(5, 15))

        # Effective speed
        ctk.CTkLabel(
            dynamics_stats,
            text="Efekt. V:",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")

        self.effective_v_label = ctk.CTkLabel(
            dynamics_stats,
            text="--% V_max",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.effective_v_label.pack(side="left", padx=5)

        # Mini velocity profile canvas
        self.velocity_canvas = Canvas(
            dynamics_frame,
            width=430,
            height=50,
            bg=Theme.BG_DARK,
            highlightthickness=0
        )
        self.velocity_canvas.pack(padx=10, pady=(0, 8))
        self._draw_empty_velocity_chart()

        # Log panel
        self.log_panel = LogPanel(self)
        self.log_panel.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    def _run_nesting(self):
        """Run nesting algorithm."""
        self.log("Uruchamiam nesting...", "INFO")
        if self.on_run_nesting:
            self.on_run_nesting()

    def log(self, message: str, level: str = "INFO"):
        """Add log message."""
        self.log_panel.log(message, level)
        if self.log_callback:
            self.log_callback(message, level)

    def set_sheets(self, sheets: List[Dict]):
        """Set sheets data."""
        self.sheets_data = sheets
        self._update_sheets_display()

        if sheets:
            self._select_sheet(0)

    def _update_sheets_display(self):
        """Update sheets list display."""
        # Clear existing
        for widget in self.sheets_scroll.winfo_children():
            widget.destroy()

        self.sheets_count_label.configure(text=f"({len(self.sheets_data)})")

        for i, sheet in enumerate(self.sheets_data):
            self._create_sheet_row(i, sheet)

    def _create_sheet_row(self, index: int, sheet: Dict):
        """Create a row for a single sheet."""
        is_selected = index == self.selected_sheet_idx
        bg_color = Theme.BG_SELECTED if is_selected else Theme.BG_INPUT

        row = ctk.CTkFrame(
            self.sheets_scroll,
            fg_color=bg_color,
            corner_radius=6,
            height=50
        )
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        row.bind("<Button-1>", lambda e, i=index: self._select_sheet(i))

        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=8)
        content.bind("<Button-1>", lambda e, i=index: self._select_sheet(i))

        # Sheet info
        material = sheet.get('material_id', '?')
        thickness = sheet.get('thickness_mm', 0)
        width = sheet.get('sheet_width_mm', 1500)
        length = sheet.get('sheet_length_mm_nominal', 3000)
        utilization = sheet.get('utilization', 0)
        parts_count = len(sheet.get('parts', []))

        lbl1 = ctk.CTkLabel(
            content,
            text=f"Arkusz {index + 1}: {material} {thickness}mm",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        lbl1.pack(side="left")
        lbl1.bind("<Button-1>", lambda e, i=index: self._select_sheet(i))

        lbl2 = ctk.CTkLabel(
            content,
            text=f"{width}x{length}mm",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        lbl2.pack(side="left", padx=15)
        lbl2.bind("<Button-1>", lambda e, i=index: self._select_sheet(i))

        lbl3 = ctk.CTkLabel(
            content,
            text=f"Util: {utilization:.1%}",
            font=ctk.CTkFont(size=11),
            text_color=Theme.ACCENT_SUCCESS if utilization > 0.6 else Theme.ACCENT_WARNING
        )
        lbl3.pack(side="right")
        lbl3.bind("<Button-1>", lambda e, i=index: self._select_sheet(i))

        lbl4 = ctk.CTkLabel(
            content,
            text=f"{parts_count} detali",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        lbl4.pack(side="right", padx=15)
        lbl4.bind("<Button-1>", lambda e, i=index: self._select_sheet(i))

    def _select_sheet(self, index: int):
        """Select sheet and update preview."""
        self.selected_sheet_idx = index
        self._update_sheets_display()

        if index < len(self.sheets_data):
            sheet = self.sheets_data[index]
            self.preview.set_sheet(
                sheet.get('sheet_width_mm', 1500),
                sheet.get('sheet_length_mm_nominal', 3000),
                sheet.get('parts', [])
            )

            # Update stats
            utilization = sheet.get('utilization', 0)
            parts_count = len(sheet.get('parts', []))
            cut_length = sum(
                p.get('toolpath_stats', {}).get('cut_length_mm', 0)
                for p in sheet.get('parts', [])
            ) / 1000.0

            self.stats_label.configure(
                text=f"Utylizacja: {utilization:.1%} | Detali: {parts_count} | Dlugosc ciecia: {cut_length:.1f} m"
            )

    def update_stats(self, utilization: float, parts_count: int, cut_length_m: float):
        """Update stats display."""
        self.stats_label.configure(
            text=f"Utylizacja: {utilization:.1%} | Detali: {parts_count} | Dlugosc ciecia: {cut_length_m:.1f} m"
        )

    def _draw_empty_velocity_chart(self):
        """Draw empty velocity chart placeholder."""
        self.velocity_canvas.delete("all")
        self.velocity_canvas.create_text(
            215, 25,
            text="Wybierz arkusz z detalami DXF, aby zobaczyc profil predkosci",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 8)
        )

    def update_dynamics_info(self, contours: int, short_seg_pct: float,
                              effective_v_pct: float, velocities: List[float] = None,
                              v_max: float = 100):
        """Update dynamics info for selected sheet."""
        # Update labels
        self.contours_label.configure(text=str(contours))

        short_color = Theme.ACCENT_DANGER if short_seg_pct > 30 else Theme.ACCENT_WARNING if short_seg_pct > 10 else Theme.ACCENT_SUCCESS
        self.short_seg_label.configure(text=f"{short_seg_pct:.0f}%", text_color=short_color)

        eff_color = Theme.ACCENT_DANGER if effective_v_pct < 50 else Theme.ACCENT_WARNING if effective_v_pct < 80 else Theme.ACCENT_SUCCESS
        self.effective_v_label.configure(text=f"{effective_v_pct:.0f}% V_max", text_color=eff_color)

        # Draw velocity profile
        self._draw_velocity_chart(velocities, v_max)

    def _draw_velocity_chart(self, velocities: List[float], v_max: float):
        """Draw mini velocity chart."""
        self.velocity_canvas.delete("all")

        if not velocities or len(velocities) < 2:
            self._draw_empty_velocity_chart()
            return

        width = 430
        height = 50
        margin = 5

        # Limit to 200 points for visualization
        n = min(200, len(velocities))
        step = max(1, len(velocities) // n)
        sampled = velocities[::step][:n]

        # Draw baseline
        self.velocity_canvas.create_line(
            margin, height - margin, width - margin, height - margin,
            fill=Theme.TEXT_MUTED, width=1
        )

        # Draw v_max line
        y_max = margin + 5
        self.velocity_canvas.create_line(
            margin, y_max, width - margin, y_max,
            fill=Theme.ACCENT_WARNING, width=1, dash=(2, 2)
        )

        # Draw velocity profile
        points = []
        dx = (width - 2 * margin) / (len(sampled) - 1) if len(sampled) > 1 else 0
        plot_h = height - 2 * margin - 5

        for i, v in enumerate(sampled):
            x = margin + i * dx
            v_ratio = min(v / v_max, 1.0) if v_max > 0 else 0
            y = height - margin - v_ratio * plot_h
            points.extend([x, y])

        if len(points) >= 4:
            self.velocity_canvas.create_line(
                points,
                fill=Theme.ACCENT_SUCCESS,
                width=1,
                smooth=True
            )

        # Labels
        self.velocity_canvas.create_text(
            width - 30, y_max,
            text="V_max",
            fill=Theme.ACCENT_WARNING,
            font=("Arial", 7)
        )


# =============================================================================
# Right Panel - Cost Parameters
# =============================================================================

class CostParametersPanel(ctk.CTkFrame):
    """Right panel: cost parameters and results."""

    def __init__(self, parent, on_calculate: Callable = None):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        self.on_calculate = on_calculate

        self._setup_ui()

    def _setup_ui(self):
        """Build UI components."""
        # Scrollable content
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Theme.BG_INPUT
        )
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        # === Options Section ===
        self._create_section_header(scroll, "Opcje")

        options_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        options_frame.pack(fill="x", padx=10, pady=5)

        # Checkboxes
        self.include_piercing_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            options_frame,
            text="Uwzglednij przebicia",
            variable=self.include_piercing_var,
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=2)

        self.include_foil_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            options_frame,
            text="Uwzglednij usuwanie folii",
            variable=self.include_foil_var,
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=2)

        self.include_punch_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            options_frame,
            text="Uwzglednij punch",
            variable=self.include_punch_var,
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=2)

        # === Job Costs Section ===
        self._create_section_header(scroll, "Koszty zlecenia")

        job_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        job_frame.pack(fill="x", padx=10, pady=5)

        self.tech_cost_var = ctk.StringVar(value="0")
        self._create_cost_row(job_frame, "Technologia:", self.tech_cost_var)

        self.packaging_cost_var = ctk.StringVar(value="0")
        self._create_cost_row(job_frame, "Opakowanie:", self.packaging_cost_var)

        self.transport_cost_var = ctk.StringVar(value="0")
        self._create_cost_row(job_frame, "Transport:", self.transport_cost_var)

        # === Per Sheet Costs ===
        self._create_section_header(scroll, "Koszty per arkusz")

        sheet_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        sheet_frame.pack(fill="x", padx=10, pady=5)

        self.operational_cost_var = ctk.StringVar(value="40")
        self._create_cost_row(sheet_frame, "Operacyjne:", self.operational_cost_var)

        # === Allocation Model ===
        self._create_section_header(scroll, "Model alokacji")

        alloc_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        alloc_frame.pack(fill="x", padx=10, pady=5)

        self.allocation_var = ctk.StringVar(value="OCCUPIED_AREA")

        ctk.CTkRadioButton(
            alloc_frame,
            text="Occupied Area (zalecany)",
            variable=self.allocation_var,
            value="OCCUPIED_AREA",
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=2)

        ctk.CTkRadioButton(
            alloc_frame,
            text="Utilization Factor (legacy)",
            variable=self.allocation_var,
            value="UTILIZATION_FACTOR",
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=2)

        # === Sheet Mode ===
        self._create_section_header(scroll, "Tryb arkusza")

        mode_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        mode_frame.pack(fill="x", padx=10, pady=5)

        self.sheet_mode_var = ctk.StringVar(value="FIXED_SHEET")

        ctk.CTkRadioButton(
            mode_frame,
            text="Staly format (FIXED_SHEET)",
            variable=self.sheet_mode_var,
            value="FIXED_SHEET",
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=2)

        ctk.CTkRadioButton(
            mode_frame,
            text="Docinany (CUT_TO_LENGTH)",
            variable=self.sheet_mode_var,
            value="CUT_TO_LENGTH",
            fg_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=2)

        margin_row = ctk.CTkFrame(mode_frame, fg_color="transparent")
        margin_row.pack(fill="x", pady=5)

        ctk.CTkLabel(
            margin_row,
            text="Margines Y:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(side="left")

        self.margin_y_var = ctk.StringVar(value="10")
        ctk.CTkEntry(
            margin_row,
            textvariable=self.margin_y_var,
            width=60,
            height=28,
            fg_color=Theme.BG_INPUT
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            margin_row,
            text="mm",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")

        # === Time Calculation Method ===
        self._create_section_header(scroll, "Metoda obliczania czasu", color=Theme.ACCENT_INFO)

        method_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        method_frame.pack(fill="x", padx=10, pady=5)

        self.time_method_var = ctk.StringVar(value="DYNAMIC")

        ctk.CTkRadioButton(
            method_frame,
            text="Dynamiczna (Motion Planning) - ZALECANA",
            variable=self.time_method_var,
            value="DYNAMIC",
            fg_color=Theme.ACCENT_SUCCESS
        ).pack(anchor="w", pady=2)

        ctk.CTkLabel(
            method_frame,
            text="   Uwzglednia przyspieszenia, hamowania, limity w rogach",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")

        ctk.CTkRadioButton(
            method_frame,
            text="Klasyczna (dlugosc/predkosc) - uproszczona",
            variable=self.time_method_var,
            value="CLASSIC",
            fg_color=Theme.ACCENT_WARNING
        ).pack(anchor="w", pady=2)

        ctk.CTkLabel(
            method_frame,
            text="   Zaklada stala predkosc - zanizona wycena!",
            font=ctk.CTkFont(size=9),
            text_color=Theme.ACCENT_DANGER
        ).pack(anchor="w")

        # === Machine Dynamics Parameters ===
        self._create_section_header(scroll, "Parametry dynamiki maszyny")

        dynamics_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_INPUT, corner_radius=8)
        dynamics_frame.pack(fill="x", padx=10, pady=5)

        # Acceleration
        accel_row = ctk.CTkFrame(dynamics_frame, fg_color="transparent")
        accel_row.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            accel_row,
            text="Przyspieszenie:",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY,
            width=100
        ).pack(side="left")

        self.accel_var = ctk.StringVar(value="2000")
        ctk.CTkEntry(
            accel_row,
            textvariable=self.accel_var,
            width=70,
            height=26,
            fg_color=Theme.BG_DARK
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            accel_row,
            text="mm/s^2",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")

        # Corner velocity
        corner_row = ctk.CTkFrame(dynamics_frame, fg_color="transparent")
        corner_row.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            corner_row,
            text="V w rogu 90st:",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY,
            width=100
        ).pack(side="left")

        self.corner_v_var = ctk.StringVar(value="50")
        ctk.CTkEntry(
            corner_row,
            textvariable=self.corner_v_var,
            width=70,
            height=26,
            fg_color=Theme.BG_DARK
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            corner_row,
            text="mm/s",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")

        # Rapid speed
        rapid_row = ctk.CTkFrame(dynamics_frame, fg_color="transparent")
        rapid_row.pack(fill="x", padx=10, pady=(5, 10))

        ctk.CTkLabel(
            rapid_row,
            text="V szybka (rapid):",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY,
            width=100
        ).pack(side="left")

        self.rapid_v_var = ctk.StringVar(value="500")
        ctk.CTkEntry(
            rapid_row,
            textvariable=self.rapid_v_var,
            width=70,
            height=26,
            fg_color=Theme.BG_DARK
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            rapid_row,
            text="mm/s",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")

        # === Buffer Factor ===
        self._create_section_header(scroll, "Bufor czasowy")

        buffer_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        buffer_frame.pack(fill="x", padx=10, pady=5)

        self.buffer_var = ctk.StringVar(value="1.25")
        self._create_cost_row(buffer_frame, "Wspolczynnik:", self.buffer_var, suffix="")

        ctk.CTkLabel(
            buffer_frame,
            text="(1.25 = +25% bufor na czas)",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")

        # === Calculate Button ===
        ctk.CTkButton(
            scroll,
            text="PRZELICZ KOSZTY",
            height=40,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color=Theme.ACCENT_INFO,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._calculate
        ).pack(fill="x", padx=10, pady=15)

        # === Results Section ===
        self._create_section_header(scroll, "WYNIKI", color=Theme.ACCENT_SUCCESS)

        results_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_INPUT, corner_radius=8)
        results_frame.pack(fill="x", padx=10, pady=5)

        # Variant A
        var_a_frame = ctk.CTkFrame(results_frame, fg_color="transparent")
        var_a_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(
            var_a_frame,
            text="Wariant A (cennikowy):",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        ).pack(side="left")

        self.result_a_label = ctk.CTkLabel(
            var_a_frame,
            text="-- PLN",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.ACCENT_WARNING
        )
        self.result_a_label.pack(side="right")

        # Variant B
        var_b_frame = ctk.CTkFrame(results_frame, fg_color="transparent")
        var_b_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(
            var_b_frame,
            text="Wariant B (czasowy):",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        ).pack(side="left")

        self.result_b_label = ctk.CTkLabel(
            var_b_frame,
            text="-- PLN",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.result_b_label.pack(side="right")

        # Time info
        self.time_label = ctk.CTkLabel(
            results_frame,
            text="Czas ciecia: -- | Czas calkowity: --",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED
        )
        self.time_label.pack(pady=(0, 5))

        # === Time Comparison Section ===
        time_compare_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_INPUT, corner_radius=8)
        time_compare_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            time_compare_frame,
            text="POROWNANIE CZASOW",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.ACCENT_INFO
        ).pack(anchor="w", padx=10, pady=(8, 5))

        # Classic time
        classic_row = ctk.CTkFrame(time_compare_frame, fg_color="transparent")
        classic_row.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(
            classic_row,
            text="Metoda klasyczna:",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED,
            width=120
        ).pack(side="left")

        self.classic_time_label = ctk.CTkLabel(
            classic_row,
            text="-- min",
            font=ctk.CTkFont(size=10),
            text_color=Theme.ACCENT_WARNING
        )
        self.classic_time_label.pack(side="right")

        # Dynamic time
        dynamic_row = ctk.CTkFrame(time_compare_frame, fg_color="transparent")
        dynamic_row.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(
            dynamic_row,
            text="Metoda dynamiczna:",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED,
            width=120
        ).pack(side="left")

        self.dynamic_time_label = ctk.CTkLabel(
            dynamic_row,
            text="-- min",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.dynamic_time_label.pack(side="right")

        # Difference
        diff_row = ctk.CTkFrame(time_compare_frame, fg_color="transparent")
        diff_row.pack(fill="x", padx=10, pady=(2, 8))

        ctk.CTkLabel(
            diff_row,
            text="Roznica:",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED,
            width=120
        ).pack(side="left")

        self.time_diff_label = ctk.CTkLabel(
            diff_row,
            text="-- min (---%)",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=Theme.ACCENT_DANGER
        )
        self.time_diff_label.pack(side="right")

        # Effective speed info
        self.effective_speed_label = ctk.CTkLabel(
            time_compare_frame,
            text="Efektywna predkosc: --% nominalnej",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        )
        self.effective_speed_label.pack(pady=(0, 8))

        # === Save Button ===
        ctk.CTkButton(
            scroll,
            text="Zapisz wyniki",
            height=35,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._save_results
        ).pack(fill="x", padx=10, pady=(5, 15))

    def _create_section_header(self, parent, text: str, color: str = None):
        """Create section header."""
        if color is None:
            color = Theme.TEXT_PRIMARY

        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=color
        ).pack(anchor="w", padx=10, pady=(15, 5))

    def _create_cost_row(self, parent, label: str, var: ctk.StringVar, suffix: str = "PLN"):
        """Create a cost input row."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)

        ctk.CTkLabel(
            row,
            text=label,
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY,
            width=100
        ).pack(side="left")

        ctk.CTkEntry(
            row,
            textvariable=var,
            width=80,
            height=28,
            fg_color=Theme.BG_INPUT
        ).pack(side="left", padx=5)

        if suffix:
            ctk.CTkLabel(
                row,
                text=suffix,
                font=ctk.CTkFont(size=11),
                text_color=Theme.TEXT_MUTED
            ).pack(side="left")

    def _calculate(self):
        """Trigger cost calculation."""
        logger.info("Calculate costs triggered")
        if self.on_calculate:
            self.on_calculate()

    def _save_results(self):
        """Save results to database."""
        logger.info("Save results triggered")
        messagebox.showinfo("Info", "Zapisywanie wynikow do bazy danych...")

    def get_parameters(self) -> Dict:
        """Get all parameters."""
        def safe_float(var, default=0.0):
            try:
                return float(var.get())
            except (ValueError, TypeError):
                return default

        return {
            'include_piercing': self.include_piercing_var.get(),
            'include_foil_removal': self.include_foil_var.get(),
            'include_punch': self.include_punch_var.get(),
            'tech_cost_pln': safe_float(self.tech_cost_var),
            'packaging_cost_pln': safe_float(self.packaging_cost_var),
            'transport_cost_pln': safe_float(self.transport_cost_var),
            'operational_cost_per_sheet_pln': safe_float(self.operational_cost_var, 40.0),
            'allocation_model': self.allocation_var.get(),
            'sheet_mode': self.sheet_mode_var.get(),
            'margin_y_mm': safe_float(self.margin_y_var, 10.0),
            'buffer_factor': safe_float(self.buffer_var, 1.25),
            # Time calculation method
            'time_method': self.time_method_var.get(),
            # Machine dynamics parameters
            'max_accel_mm_s2': safe_float(self.accel_var, 2000.0),
            'square_corner_velocity_mm_s': safe_float(self.corner_v_var, 50.0),
            'max_rapid_mm_s': safe_float(self.rapid_v_var, 500.0),
        }

    def set_results(self, variant_a: float, variant_b: float, cut_time_s: float, total_time_s: float,
                    classic_time_s: float = None, dynamic_time_s: float = None,
                    cut_length_mm: float = None, v_max_mm_s: float = None):
        """Set calculation results with time comparison."""
        self.result_a_label.configure(text=f"{variant_a:.2f} PLN")
        self.result_b_label.configure(text=f"{variant_b:.2f} PLN")

        cut_min = cut_time_s / 60
        total_min = total_time_s / 60
        self.time_label.configure(
            text=f"Czas ciecia: {cut_min:.1f} min | Czas calkowity: {total_min:.1f} min"
        )

        # Update time comparison if both values provided
        if classic_time_s is not None and dynamic_time_s is not None:
            classic_min = classic_time_s / 60
            dynamic_min = dynamic_time_s / 60

            self.classic_time_label.configure(text=f"{classic_min:.1f} min")
            self.dynamic_time_label.configure(text=f"{dynamic_min:.1f} min")

            # Calculate difference
            diff_s = dynamic_time_s - classic_time_s
            diff_min = diff_s / 60
            diff_pct = (diff_s / classic_time_s * 100) if classic_time_s > 0 else 0

            sign = "+" if diff_s > 0 else ""
            color = Theme.ACCENT_DANGER if diff_s > 0 else Theme.ACCENT_SUCCESS
            self.time_diff_label.configure(
                text=f"{sign}{diff_min:.1f} min ({sign}{diff_pct:.0f}%)",
                text_color=color
            )

            # Calculate effective speed
            if cut_length_mm and v_max_mm_s and dynamic_time_s > 0:
                # Exclude pierce time from dynamic for effective speed calc
                effective_v = cut_length_mm / dynamic_time_s
                effective_pct = (effective_v / v_max_mm_s) * 100
                self.effective_speed_label.configure(
                    text=f"Efektywna predkosc: {effective_pct:.0f}% nominalnej ({effective_v:.0f} mm/s)"
                )


# =============================================================================
# Main Window
# =============================================================================

class NestingCostingWindow(ctk.CTkToplevel):
    """Main nesting costing window - fullscreen."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.title("NewERP - Nesting & Costing")
        self.configure(fg_color=Theme.BG_DARK)

        # Fullscreen on Windows
        self.state('zoomed')

        # Minimum size
        self.minsize(1200, 700)

        # Data
        self.nesting_result = None
        self.costing_result = None
        self.parts_by_material: Dict[str, List[Dict]] = {}

        self._setup_ui()
        self._setup_costing_service()

        # Focus
        self.focus_force()

    def _setup_ui(self):
        """Build main UI layout."""
        # Header bar
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="NESTING & COSTING",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left", padx=20, pady=10)

        ctk.CTkButton(
            header,
            text="X Zamknij",
            width=100,
            height=32,
            fg_color=Theme.ACCENT_DANGER,
            hover_color="#dc2626",
            command=self.destroy
        ).pack(side="right", padx=20, pady=10)

        # Main content (3 panels)
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=10)

        # Configure grid weights
        content.grid_columnconfigure(0, weight=1)  # Left panel
        content.grid_columnconfigure(1, weight=2)  # Middle panel
        content.grid_columnconfigure(2, weight=1)  # Right panel
        content.grid_rowconfigure(0, weight=1)

        # Left panel - Source & Parts
        self.parts_panel = SourcePartsPanel(
            content,
            on_source_changed=self._on_source_changed,
            on_parts_loaded=self._on_parts_loaded
        )
        self.parts_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Middle panel - Sheets
        self.sheets_panel = SheetsPanel(
            content,
            on_run_nesting=self._run_nesting
        )
        self.sheets_panel.grid(row=0, column=1, sticky="nsew", padx=5)

        # Right panel - Cost Parameters
        self.cost_panel = CostParametersPanel(
            content,
            on_calculate=self._calculate_costs
        )
        self.cost_panel.grid(row=0, column=2, sticky="nsew", padx=(5, 0))

    def _setup_costing_service(self):
        """Initialize costing service."""
        try:
            from costing import (
                NestingCostingService,
                create_pricing_from_config,
                create_machine_profile_from_config,
                load_config
            )

            config = load_config()
            self.pricing = create_pricing_from_config(config)
            machine_profile = create_machine_profile_from_config(config)
            self.costing_service = NestingCostingService(machine_profile)
            self.config = config

            self._log("Serwis costingu zainicjalizowany", "INFO")
            self._log(f"  Max accel: {machine_profile.max_accel_mm_s2} mm/s2", "INFO")
            self._log(f"  Corner velocity: {machine_profile.square_corner_velocity_mm_s} mm/s", "INFO")

        except Exception as e:
            logger.error(f"Failed to initialize costing service: {e}")
            self.costing_service = None
            self.pricing = None
            self._log(f"BLAD: Nie udalo sie zainicjalizowac serwisu: {e}", "ERROR")

    def _log(self, message: str, level: str = "INFO"):
        """Log message to sheets panel."""
        self.sheets_panel.log(message, level)

    def _on_source_changed(self, source_type: str, source_id: str):
        """Handle source selection change."""
        self._log(f"Zmiana zrodla: typ={source_type}, id={source_id}", "INFO")

    def _on_parts_loaded(self, parts: List[Dict]):
        """Handle parts loaded."""
        self._log(f"Zaladowano {len(parts)} detali", "INFO")

        # Group by material + thickness
        self.parts_by_material = {}
        for part in parts:
            key = f"{part['material']}_{part['thickness_mm']}"
            if key not in self.parts_by_material:
                self.parts_by_material[key] = []
            self.parts_by_material[key].append(part)

        self._log(f"Grupy materialowe: {len(self.parts_by_material)}", "INFO")
        for key, group_parts in self.parts_by_material.items():
            self._log(f"  {key}: {len(group_parts)} detali", "INFO")

    def _run_nesting(self):
        """Run nesting algorithm."""
        parts = self.parts_panel.parts_data
        if not parts:
            messagebox.showwarning("Brak detali", "Najpierw zaladuj detale do nestingu.")
            return

        self._log(f"Uruchamiam nesting dla {len(parts)} detali", "CALC")

        # Get sheet mode from parameters
        params = self.cost_panel.get_parameters()
        sheet_mode = params['sheet_mode']
        margin_y = params['margin_y_mm']

        self._log(f"Tryb arkusza: {sheet_mode}, margines Y: {margin_y}mm", "CALC")

        # Create nesting result with sheets grouped by material+thickness
        self._create_grouped_nesting_result(parts, sheet_mode, margin_y)

    def _create_grouped_nesting_result(self, parts: List[Dict], sheet_mode: str, margin_y: float):
        """Create nesting result with sheets grouped by material+thickness."""
        try:
            from costing.models.nesting_result import (
                NestingResult, NestingSheet, PartInstance, ToolpathStats,
                SheetMode, SourceType
            )
            from costing.toolpath import extract_toolpath_stats

            nesting = NestingResult(
                source_type=SourceType.ORDER,
                source_id="TEST-001"
            )

            # Group parts by material + thickness
            groups: Dict[str, List[Dict]] = {}
            for part in parts:
                key = f"{part['material']}_{part['thickness_mm']}"
                if key not in groups:
                    groups[key] = []
                groups[key].append(part)

            self._log(f"Tworzenie {len(groups)} arkuszy dla roznych materialow/grubosci", "CALC")

            sheets_data = []

            for group_key, group_parts in groups.items():
                material, thickness_str = group_key.rsplit('_', 1)
                thickness = float(thickness_str)

                self._log(f"Arkusz: {material} {thickness}mm - {len(group_parts)} detali", "CALC")

                mode = SheetMode.CUT_TO_LENGTH if sheet_mode == "CUT_TO_LENGTH" else SheetMode.FIXED_SHEET

                sheet = NestingSheet(
                    sheet_id=f"SHEET-{group_key}",
                    sheet_mode=mode,
                    material_id=material,
                    thickness_mm=thickness,
                    sheet_width_mm=1500,
                    sheet_length_mm_nominal=3000,
                    trim_margin_y_mm=margin_y
                )

                max_y = 0
                total_area = 0

                for i, part in enumerate(group_parts):
                    dxf_path = part.get('dxf_path', '')

                    # Try to extract toolpath stats if DXF exists
                    toolpath_stats = None
                    occupied_area = 50000  # Default

                    if dxf_path and Path(dxf_path).exists():
                        try:
                            stats = extract_toolpath_stats(dxf_path)
                            toolpath_stats = ToolpathStats(
                                cut_length_mm=stats.cut_length_mm,
                                pierce_count=stats.pierce_count,
                                contour_count=stats.contour_count,
                                short_segment_ratio=stats.short_segment_ratio,
                                entity_counts=stats.entity_counts
                            )
                            occupied_area = stats.occupied_area_mm2

                            self._log(f"  {part['idx_code']}: cut={stats.cut_length_mm:.0f}mm, pierces={stats.pierce_count}, short_ratio={stats.short_segment_ratio:.1%}", "CALC")

                        except Exception as e:
                            self._log(f"  {part['idx_code']}: BLAD - {e}", "WARN")

                    part_instance = PartInstance(
                        part_id=f"PART-{i+1}",
                        instance_id=f"INST-{group_key}-{i+1}",
                        idx_code=part.get('idx_code', ''),
                        name=part.get('name', ''),
                        qty_in_sheet=part.get('qty', 1),
                        occupied_area_mm2=occupied_area,
                        dxf_storage_path=dxf_path,
                        toolpath_stats=toolpath_stats
                    )
                    sheet.parts.append(part_instance)

                    total_area += occupied_area
                    # Estimate Y position for CUT_TO_LENGTH
                    side = math.sqrt(occupied_area)
                    max_y = max(max_y, side)

                # For CUT_TO_LENGTH, calculate used length
                if mode == SheetMode.CUT_TO_LENGTH:
                    # Simple estimation: sqrt of total area
                    estimated_y = math.sqrt(total_area / 1500) * 1500 / 0.7  # Assume 70% utilization
                    sheet.used_length_y_mm = min(estimated_y, 3000)
                    self._log(f"  CUT_TO_LENGTH: estimated Y = {sheet.used_length_y_mm:.0f}mm", "CALC")

                sheet.calculate_metrics()
                nesting.sheets.append(sheet)
                sheets_data.append(sheet.to_dict())

                self._log(f"  Utilization: {sheet.utilization:.1%}, Area: {sheet.occupied_area_mm2/1e6:.3f} m2", "CALC")

            self.nesting_result = nesting

            # Update UI
            self.sheets_panel.set_sheets(sheets_data)

            total_cut_length = 0
            total_parts = 0
            for sheet in nesting.sheets:
                for p in sheet.parts:
                    if p.toolpath_stats:
                        total_cut_length += p.toolpath_stats.cut_length_mm * p.qty_in_sheet
                    total_parts += p.qty_in_sheet

            self._log(f"Nesting zakonczony: {len(nesting.sheets)} arkuszy, {total_parts} detali, {total_cut_length/1000:.1f}m ciecia", "RESULT")

            # Auto-collapse parts list to give more space for results
            self.parts_panel.collapse_parts_list()
            self._log("Lista detali zwinieta - kliknij '>' aby rozwinac", "INFO")

        except Exception as e:
            self._log(f"BLAD nesting: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Blad", f"Nie udalo sie utworzyc nestingu: {e}")

    def _calculate_costs(self):
        """Calculate costs using costing service."""
        if not self.nesting_result:
            messagebox.showwarning("Brak nestingu", "Najpierw uruchom nesting.")
            return

        if not self.costing_service:
            messagebox.showerror("Blad", "Serwis costingu nie zostal zainicjalizowany.")
            return

        try:
            from costing import JobOverrides, AllocationModel, MachineProfile
            from costing.models.nesting_result import SheetMode
            from costing.motion.motion_planner import m_min_to_mm_s

            params = self.cost_panel.get_parameters()

            self._log("=== OBLICZANIE KOSZTOW ===", "CALC")
            self._log(f"Parametry:", "CALC")
            self._log(f"  Metoda czasu: {params['time_method']}", "CALC")
            self._log(f"  Tryb arkusza: {params['sheet_mode']}", "CALC")
            self._log(f"  Model alokacji: {params['allocation_model']}", "CALC")
            self._log(f"  Bufor czasowy: {params['buffer_factor']}", "CALC")
            self._log(f"  Przebicia: {params['include_piercing']}", "CALC")
            self._log(f"  Folia: {params['include_foil_removal']}", "CALC")

            # Update machine profile from GUI parameters
            self.costing_service.machine_profile = MachineProfile(
                max_accel_mm_s2=params['max_accel_mm_s2'],
                max_rapid_mm_s=params['max_rapid_mm_s'],
                square_corner_velocity_mm_s=params['square_corner_velocity_mm_s']
            )

            # Enable/disable detailed motion planning based on method selection
            use_dynamic = params['time_method'] == 'DYNAMIC'
            self.costing_service.use_detailed_motion_planning = use_dynamic

            self._log(f"  Machine Profile:", "CALC")
            self._log(f"    Accel: {params['max_accel_mm_s2']} mm/s^2", "CALC")
            self._log(f"    Corner V: {params['square_corner_velocity_mm_s']} mm/s", "CALC")
            self._log(f"    Rapid V: {params['max_rapid_mm_s']} mm/s", "CALC")
            self._log(f"  Motion Planning: {'DYNAMICZNA' if use_dynamic else 'KLASYCZNA'}", "CALC")

            # Update sheet modes based on current selection
            sheet_mode = SheetMode.CUT_TO_LENGTH if params['sheet_mode'] == "CUT_TO_LENGTH" else SheetMode.FIXED_SHEET
            for sheet in self.nesting_result.sheets:
                sheet.sheet_mode = sheet_mode
                sheet.trim_margin_y_mm = params['margin_y_mm']
                sheet.calculate_metrics()

            job_overrides = JobOverrides(
                tech_cost_pln=params['tech_cost_pln'],
                packaging_cost_pln=params['packaging_cost_pln'],
                transport_cost_pln=params['transport_cost_pln'],
                operational_cost_per_sheet_pln=params['operational_cost_per_sheet_pln'],
                include_piercing=params['include_piercing'],
                include_foil_removal=params['include_foil_removal'],
                include_punch=params['include_punch']
            )

            allocation = AllocationModel.OCCUPIED_AREA
            if params['allocation_model'] == 'UTILIZATION_FACTOR':
                allocation = AllocationModel.UTILIZATION_FACTOR

            result = self.costing_service.compute_costing(
                self.nesting_result,
                job_overrides,
                self.pricing,
                allocation_model=allocation,
                buffer_factor=params['buffer_factor']
            )

            self.costing_result = result

            # Log detailed results
            self._log("--- Wyniki per arkusz ---", "CALC")
            total_cut_time = 0
            total_time = 0

            for sheet_cost in result.sheet_costs:
                self._log(f"Arkusz {sheet_cost.sheet_id}:", "CALC")
                self._log(f"  Material: {sheet_cost.sheet_cost_pln:.2f} PLN", "CALC")
                self._log(f"  Ciecie (A): {sheet_cost.cut_cost_a_pln:.2f} PLN", "CALC")
                self._log(f"  Przebicia (A): {sheet_cost.pierce_cost_a_pln:.2f} PLN", "CALC")
                self._log(f"  Czas ciecia: {sheet_cost.cut_time_s:.1f}s", "CALC")
                self._log(f"  Czas calkowity: {sheet_cost.total_time_s:.1f}s (z buforem)", "CALC")
                self._log(f"  Laser (B): {sheet_cost.laser_cost_b_pln:.2f} PLN", "CALC")

                total_cut_time += sheet_cost.cut_time_s
                total_time += sheet_cost.total_time_s

            # Calculate classic time for comparison
            total_cut_length_mm = 0.0
            total_pierce_count = 0
            for sheet in self.nesting_result.sheets:
                for part in sheet.parts:
                    if part.toolpath_stats:
                        total_cut_length_mm += part.toolpath_stats.cut_length_mm * part.qty_in_sheet
                        total_pierce_count += part.toolpath_stats.pierce_count * part.qty_in_sheet

            # Get nominal cutting speed (from first sheet's material)
            v_max_m_min = 6.0  # Default
            pierce_time_s = 0.5  # Default
            if self.nesting_result.sheets and self.pricing:
                first_sheet = self.nesting_result.sheets[0]
                v_max_m_min = self.pricing.get_cutting_speed(
                    first_sheet.material_id, first_sheet.thickness_mm
                )
                pierce_time_s = self.pricing.get_pierce_time(
                    first_sheet.material_id, first_sheet.thickness_mm
                )

            v_max_mm_s = v_max_m_min * 1000 / 60

            # Classic time: length / speed + pierces
            classic_cut_time = total_cut_length_mm / v_max_mm_s if v_max_mm_s > 0 else 0
            classic_pierce_time = total_pierce_count * pierce_time_s
            classic_total_time = classic_cut_time + classic_pierce_time

            # Dynamic time from actual calculation
            dynamic_total_time = total_cut_time  # This includes motion planning if enabled

            self._log("--- PODSUMOWANIE ---", "RESULT")
            self._log(f"Wariant A (cennikowy): {result.variant_a_total_pln:.2f} PLN", "RESULT")
            self._log(f"Wariant B (czasowy):   {result.variant_b_total_pln:.2f} PLN", "RESULT")
            self._log(f"Czas ciecia:           {total_cut_time/60:.1f} min", "RESULT")
            self._log(f"Czas calkowity:        {total_time/60:.1f} min", "RESULT")
            self._log("--- POROWNANIE METOD ---", "RESULT")
            self._log(f"Czas klasyczny:        {classic_total_time/60:.1f} min", "RESULT")
            self._log(f"Czas dynamiczny:       {dynamic_total_time/60:.1f} min", "RESULT")

            diff_time = dynamic_total_time - classic_total_time
            diff_pct = (diff_time / classic_total_time * 100) if classic_total_time > 0 else 0
            self._log(f"Roznica:               {'+' if diff_time > 0 else ''}{diff_time/60:.1f} min ({'+' if diff_pct > 0 else ''}{diff_pct:.0f}%)", "RESULT")

            # Calculate effective speed
            if dynamic_total_time > 0:
                effective_v = total_cut_length_mm / dynamic_total_time
                effective_pct = (effective_v / v_max_mm_s * 100) if v_max_mm_s > 0 else 0
                self._log(f"Efektywna predkosc:    {effective_v:.0f} mm/s ({effective_pct:.0f}% nominalnej)", "RESULT")

            # Update UI
            self.cost_panel.set_results(
                result.variant_a_total_pln,
                result.variant_b_total_pln,
                total_cut_time,
                total_time,
                classic_time_s=classic_total_time,
                dynamic_time_s=dynamic_total_time,
                cut_length_mm=total_cut_length_mm,
                v_max_mm_s=v_max_mm_s
            )

        except Exception as e:
            self._log(f"BLAD obliczen: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Blad", f"Nie udalo sie obliczyc kosztow: {e}")


# =============================================================================
# Standalone launch
# =============================================================================

def launch_nesting_costing_window(parent=None):
    """Launch the nesting costing window."""
    window = NestingCostingWindow(parent)
    return window


if __name__ == "__main__":
    # Test standalone
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    window = NestingCostingWindow(root)
    window.mainloop()
