"""
Motion Dynamics Test Window - GUI for testing machine dynamics costing model.

Features:
- Machine profile parameter editor (acceleration, corner velocity, etc.)
- DXF file loading and toolpath analysis
- Comparison: Classic (length/speed) vs Dynamic (motion planning)
- Detailed calculation report
- Velocity profile visualization
"""

# Ensure costing module is importable when running standalone
import sys
from pathlib import Path as _Path
_project_root = _Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog, Canvas
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import threading
import logging
import json
import math

logger = logging.getLogger(__name__)


class Theme:
    """Color palette - consistent with project style."""
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
# Machine Profile Panel
# =============================================================================

class MachineProfilePanel(ctk.CTkFrame):
    """Panel for editing machine dynamics parameters."""

    def __init__(self, parent, on_profile_changed: callable = None):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        self.on_profile_changed = on_profile_changed
        self._setup_ui()

    def _setup_ui(self):
        """Build UI components."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header,
            text="PARAMETRY DYNAMIKI MASZYNY",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.ACCENT_INFO
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="MachineProfile - model dynamiki CNC",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")

        # Parameters frame
        params_frame = ctk.CTkFrame(self, fg_color="transparent")
        params_frame.pack(fill="x", padx=15, pady=10)

        # Max Acceleration
        self.accel_var = ctk.StringVar(value="2000")
        self._create_param_row(
            params_frame,
            "Przyspieszenie max:",
            self.accel_var,
            "mm/s^2",
            "Maksymalne przyspieszenie/hamowanie maszyny"
        )

        # Max Rapid Speed
        self.rapid_var = ctk.StringVar(value="500")
        self._create_param_row(
            params_frame,
            "Predkosc szybka (rapid):",
            self.rapid_var,
            "mm/s",
            "Predkosc ruchow szybkich (laser OFF)"
        )

        # Square Corner Velocity
        self.corner_var = ctk.StringVar(value="50")
        self._create_param_row(
            params_frame,
            "Predkosc w rogu 90st:",
            self.corner_var,
            "mm/s",
            "Limit predkosci przy skretach 90 stopni"
        )

        # Junction Deviation
        self.jd_var = ctk.StringVar(value="0.05")
        self._create_param_row(
            params_frame,
            "Junction deviation:",
            self.jd_var,
            "mm",
            "Tolerancja odchylenia w naroznikach (model Klipper)"
        )

        # Use Junction Deviation checkbox
        self.use_jd_var = ctk.BooleanVar(value=False)
        jd_frame = ctk.CTkFrame(params_frame, fg_color="transparent")
        jd_frame.pack(fill="x", pady=5)

        ctk.CTkCheckBox(
            jd_frame,
            text="Uzywaj modelu Junction Deviation",
            variable=self.use_jd_var,
            fg_color=Theme.ACCENT_PRIMARY,
            command=self._on_param_changed
        ).pack(anchor="w")

        ctk.CTkLabel(
            jd_frame,
            text="(zaawansowany model naroznikow z Klipper/Marlin)",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", padx=25)

        # Divider
        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=15, pady=10)

        # Cutting Speed Section
        ctk.CTkLabel(
            self,
            text="PARAMETRY CIECIA",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.ACCENT_WARNING
        ).pack(anchor="w", padx=15, pady=(5, 5))

        cut_frame = ctk.CTkFrame(self, fg_color="transparent")
        cut_frame.pack(fill="x", padx=15, pady=5)

        # Cutting Speed
        self.cut_speed_var = ctk.StringVar(value="6.0")
        self._create_param_row(
            cut_frame,
            "Predkosc ciecia:",
            self.cut_speed_var,
            "m/min",
            "Nominalna predkosc ciecia dla materialu"
        )

        # Pierce Time
        self.pierce_time_var = ctk.StringVar(value="0.5")
        self._create_param_row(
            cut_frame,
            "Czas przebicia:",
            self.pierce_time_var,
            "s",
            "Czas na jedno przebicie materialu"
        )

        # Machine Rate
        self.rate_var = ctk.StringVar(value="300")
        self._create_param_row(
            cut_frame,
            "Stawka maszyny:",
            self.rate_var,
            "PLN/h",
            "Koszt godziny pracy maszyny"
        )

        # Presets section
        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=15, pady=10)

        presets_frame = ctk.CTkFrame(self, fg_color="transparent")
        presets_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            presets_frame,
            text="Presety:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(side="left")

        ctk.CTkButton(
            presets_frame,
            text="Fiber 3kW",
            width=80,
            height=28,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._load_preset("fiber_3kw")
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            presets_frame,
            text="Fiber 6kW",
            width=80,
            height=28,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._load_preset("fiber_6kw")
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            presets_frame,
            text="CO2",
            width=60,
            height=28,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._load_preset("co2")
        ).pack(side="left", padx=5)

    def _create_param_row(self, parent, label: str, var: ctk.StringVar,
                           unit: str, tooltip: str = ""):
        """Create a parameter input row."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)

        ctk.CTkLabel(
            row,
            text=label,
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY,
            width=170
        ).pack(side="left")

        entry = ctk.CTkEntry(
            row,
            textvariable=var,
            width=80,
            height=28,
            fg_color=Theme.BG_INPUT
        )
        entry.pack(side="left", padx=5)
        entry.bind("<KeyRelease>", lambda e: self._on_param_changed())

        ctk.CTkLabel(
            row,
            text=unit,
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED,
            width=50
        ).pack(side="left")

        if tooltip:
            ctk.CTkLabel(
                row,
                text=f"({tooltip[:40]}...)" if len(tooltip) > 40 else f"({tooltip})",
                font=ctk.CTkFont(size=9),
                text_color=Theme.TEXT_MUTED
            ).pack(side="left", padx=5)

    def _on_param_changed(self):
        """Notify about parameter change."""
        if self.on_profile_changed:
            self.on_profile_changed(self.get_profile())

    def _load_preset(self, preset_name: str):
        """Load preset values."""
        presets = {
            "fiber_3kw": {
                "accel": "2000",
                "rapid": "500",
                "corner": "50",
                "jd": "0.05",
                "use_jd": False,
                "cut_speed": "6.0",
                "pierce": "0.5",
                "rate": "300"
            },
            "fiber_6kw": {
                "accel": "3000",
                "rapid": "600",
                "corner": "60",
                "jd": "0.03",
                "use_jd": False,
                "cut_speed": "8.0",
                "pierce": "0.3",
                "rate": "400"
            },
            "co2": {
                "accel": "1200",
                "rapid": "300",
                "corner": "40",
                "jd": "0.1",
                "use_jd": False,
                "cut_speed": "4.0",
                "pierce": "1.0",
                "rate": "250"
            }
        }

        if preset_name in presets:
            p = presets[preset_name]
            self.accel_var.set(p["accel"])
            self.rapid_var.set(p["rapid"])
            self.corner_var.set(p["corner"])
            self.jd_var.set(p["jd"])
            self.use_jd_var.set(p["use_jd"])
            self.cut_speed_var.set(p["cut_speed"])
            self.pierce_time_var.set(p["pierce"])
            self.rate_var.set(p["rate"])
            self._on_param_changed()

    def get_profile(self) -> Dict:
        """Get current profile as dict."""
        def safe_float(var, default):
            try:
                return float(var.get())
            except (ValueError, TypeError):
                return default

        return {
            "max_accel_mm_s2": safe_float(self.accel_var, 2000),
            "max_rapid_mm_s": safe_float(self.rapid_var, 500),
            "square_corner_velocity_mm_s": safe_float(self.corner_var, 50),
            "junction_deviation_mm": safe_float(self.jd_var, 0.05),
            "use_junction_deviation": self.use_jd_var.get(),
            "cutting_speed_m_min": safe_float(self.cut_speed_var, 6.0),
            "pierce_time_s": safe_float(self.pierce_time_var, 0.5),
            "machine_rate_pln_h": safe_float(self.rate_var, 300)
        }


# =============================================================================
# DXF Analysis Panel
# =============================================================================

class DXFAnalysisPanel(ctk.CTkFrame):
    """Panel for loading and analyzing DXF files."""

    def __init__(self, parent, on_dxf_loaded: callable = None):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        self.on_dxf_loaded = on_dxf_loaded
        self.current_dxf_path = None
        self.toolpath_stats = None
        self.motion_segments = None
        self._setup_ui()

    def _setup_ui(self):
        """Build UI components."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header,
            text="ANALIZA DXF / TOOLPATH",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.ACCENT_SUCCESS
        ).pack(anchor="w")

        # Load buttons
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkButton(
            buttons_frame,
            text="Zaladuj DXF",
            width=120,
            height=35,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color=Theme.ACCENT_INFO,
            command=self._load_dxf
        ).pack(side="left")

        ctk.CTkButton(
            buttons_frame,
            text="Z folderu testowego",
            width=140,
            height=35,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._load_from_test_folder
        ).pack(side="left", padx=10)

        # Current file label
        self.file_label = ctk.CTkLabel(
            self,
            text="Nie zaladowano pliku",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_MUTED
        )
        self.file_label.pack(anchor="w", padx=15, pady=5)

        # Stats frame
        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=15, pady=10)

        stats_header = ctk.CTkLabel(
            self,
            text="STATYSTYKI TOOLPATH",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        stats_header.pack(anchor="w", padx=15, pady=(5, 10))

        self.stats_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=8)
        self.stats_frame.pack(fill="x", padx=15, pady=5)

        # Stats labels (will be updated)
        self.stats_labels = {}
        stats_items = [
            ("cut_length", "Dlugosc ciecia:", "-- mm"),
            ("pierce_count", "Liczba przebic:", "--"),
            ("contour_count", "Liczba konturow (encji):", "--"),
            ("segments", "Segmenty ruchu:", "--"),
            ("short_ratio", "Krotkie segmenty:", "--%"),
            ("area", "Pole pow. (bbox):", "-- mm2"),
            ("avg_seg_len", "Srednia dl. segmentu:", "-- mm"),
        ]

        for key, label, default in stats_items:
            row = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)

            ctk.CTkLabel(
                row,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color=Theme.TEXT_SECONDARY,
                width=140
            ).pack(side="left")

            lbl = ctk.CTkLabel(
                row,
                text=default,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=Theme.TEXT_PRIMARY
            )
            lbl.pack(side="left")
            self.stats_labels[key] = lbl

        # Entity counts
        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(
            self,
            text="ENCJE DXF",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", padx=15, pady=(5, 5))

        self.entities_label = ctk.CTkLabel(
            self,
            text="LINE: 0 | ARC: 0 | CIRCLE: 0 | LWPOLYLINE: 0 | SPLINE: 0",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY
        )
        self.entities_label.pack(anchor="w", padx=15, pady=5)

        # Segment distribution
        ctk.CTkLabel(
            self,
            text="ROZKLAD DLUGOSCI SEGMENTOW",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.dist_canvas = Canvas(
            self,
            width=350,
            height=80,
            bg=Theme.BG_DARK,
            highlightthickness=0
        )
        self.dist_canvas.pack(padx=15, pady=5)
        self._draw_empty_histogram()

    def _draw_empty_histogram(self):
        """Draw empty histogram placeholder."""
        self.dist_canvas.delete("all")
        self.dist_canvas.create_text(
            175, 40,
            text="Zaladuj DXF, aby zobaczyc rozklad",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 10)
        )

    def _load_dxf(self):
        """Load DXF file from dialog."""
        file_path = filedialog.askopenfilename(
            title="Wybierz plik DXF",
            filetypes=[("DXF Files", "*.dxf"), ("All Files", "*.*")]
        )
        if file_path:
            self._analyze_dxf(file_path)

    def _load_from_test_folder(self):
        """Load first DXF from test folder."""
        test_folder = Path(__file__).parent.parent / "tests" / "test_dxfs"
        if test_folder.exists():
            dxf_files = list(test_folder.glob("*.dxf")) + list(test_folder.glob("*.DXF"))
            if dxf_files:
                self._analyze_dxf(str(dxf_files[0]))
            else:
                messagebox.showinfo("Info", f"Brak plikow DXF w: {test_folder}")
        else:
            messagebox.showwarning("Blad", f"Folder testowy nie istnieje: {test_folder}")

    def _analyze_dxf(self, file_path: str):
        """Analyze DXF file and extract toolpath."""
        try:
            from costing.toolpath.dxf_extractor import (
                extract_toolpath_stats, extract_motion_segments
            )

            self.current_dxf_path = file_path
            self.file_label.configure(
                text=f"Plik: {Path(file_path).name}",
                text_color=Theme.TEXT_PRIMARY
            )

            # Extract stats
            self.toolpath_stats = extract_toolpath_stats(file_path)

            # Extract motion segments for detailed analysis
            self.motion_segments = extract_motion_segments(file_path)

            # Update stats labels
            stats = self.toolpath_stats
            # Count unique contours from motion segments (more accurate)
            unique_contours = len(set(s.contour_id for s in self.motion_segments))

            # Calculate average segment length
            lengths = [s.length_mm for s in self.motion_segments]
            avg_seg_len = sum(lengths) / len(lengths) if lengths else 0

            self.stats_labels["cut_length"].configure(
                text=f"{stats.cut_length_mm:,.1f} mm ({stats.cut_length_mm/1000:.2f} m)"
            )
            self.stats_labels["pierce_count"].configure(text=str(stats.pierce_count))
            self.stats_labels["contour_count"].configure(
                text=f"{unique_contours} (= {unique_contours} start/stop)"
            )
            self.stats_labels["segments"].configure(text=str(len(self.motion_segments)))
            self.stats_labels["short_ratio"].configure(
                text=f"{stats.short_segment_ratio:.1%}"
            )
            self.stats_labels["area"].configure(
                text=f"{stats.occupied_area_mm2:,.0f} mm2 ({stats.occupied_area_mm2/1e6:.4f} m2)"
            )
            self.stats_labels["avg_seg_len"].configure(
                text=f"{avg_seg_len:.2f} mm"
            )

            # Update entity counts
            ec = stats.entity_counts
            self.entities_label.configure(
                text=f"LINE: {ec.get('LINE', 0)} | ARC: {ec.get('ARC', 0)} | "
                     f"CIRCLE: {ec.get('CIRCLE', 0)} | LWPOLYLINE: {ec.get('LWPOLYLINE', 0)} | "
                     f"SPLINE: {ec.get('SPLINE', 0)}"
            )

            # Draw histogram
            self._draw_segment_histogram()

            # Notify parent
            if self.on_dxf_loaded:
                self.on_dxf_loaded(file_path, stats, self.motion_segments)

        except Exception as e:
            logger.error(f"Failed to analyze DXF: {e}")
            messagebox.showerror("Blad", f"Nie udalo sie przeanalizowac DXF:\n{e}")

    def _draw_segment_histogram(self):
        """Draw histogram of segment lengths."""
        self.dist_canvas.delete("all")

        if not self.motion_segments:
            self._draw_empty_histogram()
            return

        # Create bins
        lengths = [s.length_mm for s in self.motion_segments]
        bins = [0, 1, 2, 5, 10, 20, 50, 100, float('inf')]
        bin_labels = ["<1", "1-2", "2-5", "5-10", "10-20", "20-50", "50-100", ">100"]
        counts = [0] * (len(bins) - 1)

        for length in lengths:
            for i in range(len(bins) - 1):
                if bins[i] <= length < bins[i + 1]:
                    counts[i] += 1
                    break

        # Draw bars
        max_count = max(counts) if counts else 1
        bar_width = 40
        bar_spacing = 5
        x_start = 10
        y_bottom = 70

        for i, (count, label) in enumerate(zip(counts, bin_labels)):
            x = x_start + i * (bar_width + bar_spacing)
            bar_height = (count / max_count) * 50 if max_count > 0 else 0

            # Bar
            color = Theme.ACCENT_PRIMARY if i < 3 else Theme.ACCENT_SUCCESS
            self.dist_canvas.create_rectangle(
                x, y_bottom - bar_height,
                x + bar_width, y_bottom,
                fill=color, outline=""
            )

            # Label
            self.dist_canvas.create_text(
                x + bar_width / 2, y_bottom + 8,
                text=label,
                fill=Theme.TEXT_MUTED,
                font=("Arial", 7)
            )

            # Count
            if count > 0:
                self.dist_canvas.create_text(
                    x + bar_width / 2, y_bottom - bar_height - 6,
                    text=str(count),
                    fill=Theme.TEXT_SECONDARY,
                    font=("Arial", 8)
                )

    def get_data(self) -> Tuple[Optional[str], Optional[Any], Optional[List]]:
        """Get current DXF data."""
        return self.current_dxf_path, self.toolpath_stats, self.motion_segments


# =============================================================================
# Results & Comparison Panel
# =============================================================================

class ResultsComparisonPanel(ctk.CTkFrame):
    """Panel showing comparison between classic and dynamic costing."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        self._setup_ui()

    def _setup_ui(self):
        """Build UI components."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header,
            text="POROWNANIE: KLASYCZNY vs DYNAMICZNY",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.ACCENT_WARNING
        ).pack(anchor="w")

        # Calculate button
        self.calc_button = ctk.CTkButton(
            header,
            text="OBLICZ",
            width=100,
            height=32,
            fg_color=Theme.ACCENT_SUCCESS,
            hover_color="#1ea34a",
            state="disabled"
        )
        self.calc_button.pack(side="right")

        # Classic method section
        ctk.CTkLabel(
            self,
            text="METODA KLASYCZNA",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.ACCENT_DANGER
        ).pack(anchor="w", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            self,
            text="Wzor: czas = (dlugosc_ciecia / predkosc) + (przebicia * czas_przebicia)",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", padx=15)

        classic_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=8)
        classic_frame.pack(fill="x", padx=15, pady=10)

        self.classic_labels = {}
        classic_items = [
            ("motion_time", "Czas ruchu:"),
            ("pierce_time", "Czas przebic:"),
            ("total_time", "CZAS CALKOWITY:"),
            ("cost", "KOSZT:")
        ]

        for key, label in classic_items:
            row = ctk.CTkFrame(classic_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)

            is_total = key in ["total_time", "cost"]
            ctk.CTkLabel(
                row,
                text=label,
                font=ctk.CTkFont(size=11, weight="bold" if is_total else "normal"),
                text_color=Theme.TEXT_PRIMARY if is_total else Theme.TEXT_SECONDARY,
                width=150
            ).pack(side="left")

            lbl = ctk.CTkLabel(
                row,
                text="--",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=Theme.ACCENT_DANGER if is_total else Theme.TEXT_PRIMARY
            )
            lbl.pack(side="right")
            self.classic_labels[key] = lbl

        # Dynamic method section
        ctk.CTkLabel(
            self,
            text="METODA DYNAMICZNA (Motion Planning)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.ACCENT_SUCCESS
        ).pack(anchor="w", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            self,
            text="Algorytm lookahead z profilem trapezoidowym (acc -> cruise -> dec)",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", padx=15)

        dynamic_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=8)
        dynamic_frame.pack(fill="x", padx=15, pady=10)

        self.dynamic_labels = {}
        dynamic_items = [
            ("cutting_time", "Czas ciecia:"),
            ("rapid_time", "Czas ruchow szybkich:"),
            ("pierce_time", "Czas przebic:"),
            ("total_time", "CZAS CALKOWITY:"),
            ("cost", "KOSZT:")
        ]

        for key, label in dynamic_items:
            row = ctk.CTkFrame(dynamic_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)

            is_total = key in ["total_time", "cost"]
            ctk.CTkLabel(
                row,
                text=label,
                font=ctk.CTkFont(size=11, weight="bold" if is_total else "normal"),
                text_color=Theme.TEXT_PRIMARY if is_total else Theme.TEXT_SECONDARY,
                width=150
            ).pack(side="left")

            lbl = ctk.CTkLabel(
                row,
                text="--",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=Theme.ACCENT_SUCCESS if is_total else Theme.TEXT_PRIMARY
            )
            lbl.pack(side="right")
            self.dynamic_labels[key] = lbl

        # Difference section
        ctk.CTkFrame(self, height=2, fg_color=Theme.ACCENT_WARNING).pack(fill="x", padx=15, pady=10)

        diff_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=8)
        diff_frame.pack(fill="x", padx=15, pady=5)

        diff_header = ctk.CTkFrame(diff_frame, fg_color="transparent")
        diff_header.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(
            diff_header,
            text="ROZNICA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.ACCENT_WARNING
        ).pack(side="left")

        self.diff_labels = {}

        diff_row1 = ctk.CTkFrame(diff_frame, fg_color="transparent")
        diff_row1.pack(fill="x", padx=10, pady=3)

        ctk.CTkLabel(
            diff_row1,
            text="Roznica czasu:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY,
            width=150
        ).pack(side="left")

        self.diff_labels["time"] = ctk.CTkLabel(
            diff_row1,
            text="-- s (---%)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.ACCENT_WARNING
        )
        self.diff_labels["time"].pack(side="right")

        diff_row2 = ctk.CTkFrame(diff_frame, fg_color="transparent")
        diff_row2.pack(fill="x", padx=10, pady=(3, 10))

        ctk.CTkLabel(
            diff_row2,
            text="Roznica kosztu:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY,
            width=150
        ).pack(side="left")

        self.diff_labels["cost"] = ctk.CTkLabel(
            diff_row2,
            text="-- PLN (---%)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.ACCENT_WARNING
        )
        self.diff_labels["cost"].pack(side="right")

        # Interpretation
        self.interpretation_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED,
            wraplength=350
        )
        self.interpretation_label.pack(anchor="w", padx=15, pady=10)

    def set_calc_command(self, command: callable):
        """Set calculate button command."""
        self.calc_button.configure(command=command, state="normal")

    def enable_calc(self, enabled: bool = True):
        """Enable/disable calculate button."""
        self.calc_button.configure(state="normal" if enabled else "disabled")

    def set_classic_results(self, motion_time_s: float, pierce_time_s: float,
                            total_time_s: float, cost_pln: float):
        """Set classic method results."""
        self.classic_labels["motion_time"].configure(text=f"{motion_time_s:.2f} s ({motion_time_s/60:.2f} min)")
        self.classic_labels["pierce_time"].configure(text=f"{pierce_time_s:.2f} s")
        self.classic_labels["total_time"].configure(text=f"{total_time_s:.2f} s ({total_time_s/60:.2f} min)")
        self.classic_labels["cost"].configure(text=f"{cost_pln:.2f} PLN")

    def set_dynamic_results(self, cutting_time_s: float, rapid_time_s: float,
                             pierce_time_s: float, total_time_s: float, cost_pln: float):
        """Set dynamic method results."""
        self.dynamic_labels["cutting_time"].configure(text=f"{cutting_time_s:.2f} s ({cutting_time_s/60:.2f} min)")
        self.dynamic_labels["rapid_time"].configure(text=f"{rapid_time_s:.2f} s")
        self.dynamic_labels["pierce_time"].configure(text=f"{pierce_time_s:.2f} s")
        self.dynamic_labels["total_time"].configure(text=f"{total_time_s:.2f} s ({total_time_s/60:.2f} min)")
        self.dynamic_labels["cost"].configure(text=f"{cost_pln:.2f} PLN")

    def set_difference(self, time_diff_s: float, time_diff_pct: float,
                        cost_diff_pln: float, cost_diff_pct: float):
        """Set difference results."""
        # Time
        sign = "+" if time_diff_s > 0 else ""
        color = Theme.ACCENT_DANGER if time_diff_s > 0 else Theme.ACCENT_SUCCESS
        self.diff_labels["time"].configure(
            text=f"{sign}{time_diff_s:.2f} s ({sign}{time_diff_pct:.1f}%)",
            text_color=color
        )

        # Cost
        sign = "+" if cost_diff_pln > 0 else ""
        color = Theme.ACCENT_DANGER if cost_diff_pln > 0 else Theme.ACCENT_SUCCESS
        self.diff_labels["cost"].configure(
            text=f"{sign}{cost_diff_pln:.2f} PLN ({sign}{cost_diff_pct:.1f}%)",
            text_color=color
        )

        # Interpretation
        if time_diff_pct < -10:
            interp = "Metoda dynamiczna wykrywa znacznie dluzszy rzeczywisty czas ciecia ze wzgledu na ograniczenia dynamiki maszyny (hamowanie w naroznikach, przyspieszanie). Roznica ta jest typowa dla detali z duza iloscia krotkch segmentow i ostrych katow."
        elif time_diff_pct < -3:
            interp = "Metoda dynamiczna pokazuje dluzszy czas - uwzglednia przyspieszenia/hamowania i limity predkosci w naroznikach."
        elif time_diff_pct > 3:
            interp = "Metoda klasyczna daje dluzszy czas - moze to wynikac z konserwatywnych parametrow lub prostych konturow bez ostrych katow."
        else:
            interp = "Roznica minimalna - dla prostych konturow obie metody daja podobne wyniki."

        self.interpretation_label.configure(text=interp)


# =============================================================================
# Detailed Report Panel
# =============================================================================

class DetailedReportPanel(ctk.CTkFrame):
    """Panel showing detailed calculation report."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        self._setup_ui()

    def _setup_ui(self):
        """Build UI components."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header,
            text="RAPORT SZCZEGOLOWY",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.ACCENT_PURPLE
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Eksport",
            width=80,
            height=28,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._export_report
        ).pack(side="right")

        ctk.CTkButton(
            header,
            text="Kopiuj",
            width=60,
            height=28,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._copy_report
        ).pack(side="right", padx=5)

        # Report text
        self.report_text = ctk.CTkTextbox(
            self,
            fg_color=Theme.BG_DARK,
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="word"
        )
        self.report_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._set_default_text()

    def _set_default_text(self):
        """Set default placeholder text."""
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", """
========================================
    RAPORT ANALIZY DYNAMIKI MASZYNY
========================================

Zaladuj plik DXF i kliknij OBLICZ,
aby wygenerowac raport.

Raport zawiera:
- Parametry dynamiki maszyny
- Statystyki toolpath
- Obliczenia klasyczne
- Obliczenia dynamiczne (motion planning)
- Porownanie i roznice
- Analiza segmentow i predkosci
""")

    def set_report(self, report_text: str):
        """Set report content."""
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", report_text)

    def _copy_report(self):
        """Copy report to clipboard."""
        text = self.report_text.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Skopiowano", "Raport skopiowany do schowka.")

    def _export_report(self):
        """Export report to file."""
        file_path = filedialog.asksaveasfilename(
            title="Zapisz raport",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.report_text.get("1.0", "end"))
                messagebox.showinfo("Zapisano", f"Raport zapisany: {file_path}")
            except Exception as e:
                messagebox.showerror("Blad", f"Nie udalo sie zapisac: {e}")


# =============================================================================
# Velocity Profile Canvas
# =============================================================================

class VelocityProfileCanvas(ctk.CTkFrame):
    """Canvas showing velocity profile visualization."""

    def __init__(self, parent, width: int = 700, height: int = 150):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=10)

        self.canvas_width = width
        self.canvas_height = height

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            header,
            text="PROFIL PREDKOSCI (Motion Planning)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.ACCENT_INFO
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Uproszczona wizualizacja - pierwsze 100 segmentow",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED
        ).pack(side="right")

        # Canvas
        self.canvas = Canvas(
            self,
            width=width,
            height=height,
            bg=Theme.BG_DARK,
            highlightthickness=0
        )
        self.canvas.pack(padx=10, pady=(0, 10))

        self._draw_empty()

    def _draw_empty(self):
        """Draw empty state."""
        self.canvas.delete("all")
        self.canvas.create_text(
            self.canvas_width // 2,
            self.canvas_height // 2,
            text="Zaladuj DXF i oblicz, aby zobaczyc profil predkosci",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 11)
        )

    def draw_velocity_profile(self, velocities: List[float], v_max: float,
                               segment_lengths: List[float]):
        """Draw velocity profile."""
        self.canvas.delete("all")

        if not velocities or len(velocities) < 2:
            self._draw_empty()
            return

        margin = 40
        plot_w = self.canvas_width - 2 * margin
        plot_h = self.canvas_height - 2 * margin

        # Limit to first 100 for visualization
        n = min(100, len(velocities))
        velocities = velocities[:n]

        # Draw axes
        # Y axis
        self.canvas.create_line(
            margin, margin, margin, self.canvas_height - margin,
            fill=Theme.TEXT_MUTED, width=1
        )
        # X axis
        self.canvas.create_line(
            margin, self.canvas_height - margin,
            self.canvas_width - margin, self.canvas_height - margin,
            fill=Theme.TEXT_MUTED, width=1
        )

        # Y axis labels
        self.canvas.create_text(
            margin - 5, margin,
            text=f"{v_max:.0f}",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 8),
            anchor="e"
        )
        self.canvas.create_text(
            margin - 5, self.canvas_height - margin,
            text="0",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 8),
            anchor="e"
        )
        self.canvas.create_text(
            15, self.canvas_height // 2,
            text="v\n(mm/s)",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 8)
        )

        # X axis label
        self.canvas.create_text(
            self.canvas_width // 2, self.canvas_height - 5,
            text="Segmenty (junction points)",
            fill=Theme.TEXT_MUTED,
            font=("Arial", 8)
        )

        # Draw v_max line
        y_max = margin
        self.canvas.create_line(
            margin, y_max, self.canvas_width - margin, y_max,
            fill=Theme.ACCENT_WARNING, width=1, dash=(4, 4)
        )

        # Draw velocity profile
        points = []
        dx = plot_w / (n - 1)

        for i, v in enumerate(velocities):
            x = margin + i * dx
            y = self.canvas_height - margin - (v / v_max) * plot_h
            points.extend([x, y])

        if len(points) >= 4:
            self.canvas.create_line(
                points,
                fill=Theme.ACCENT_SUCCESS,
                width=2,
                smooth=True
            )

        # Draw junction points
        for i, v in enumerate(velocities):
            x = margin + i * dx
            y = self.canvas_height - margin - (v / v_max) * plot_h
            self.canvas.create_oval(
                x - 2, y - 2, x + 2, y + 2,
                fill=Theme.ACCENT_PRIMARY,
                outline=""
            )


# =============================================================================
# Main Window
# =============================================================================

class MotionDynamicsTestWindow(ctk.CTkToplevel):
    """Main window for testing motion dynamics costing."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.title("NewERP - Test Dynamiki Maszyny (Costing)")
        self.configure(fg_color=Theme.BG_DARK)

        # Fullscreen on Windows
        self.state('zoomed')
        self.minsize(1400, 800)

        # Data
        self.current_dxf = None
        self.toolpath_stats = None
        self.motion_segments = None
        self.planned_velocities = None

        self._setup_ui()

        self.focus_force()

    def _setup_ui(self):
        """Build main UI layout."""
        # Header bar
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="TEST DYNAMIKI MASZYNY - Porownanie wyceny klasycznej vs dynamicznej",
            font=ctk.CTkFont(size=16, weight="bold"),
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

        # Main content - 2 rows
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=10)

        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        content.grid_columnconfigure(2, weight=1)
        content.grid_rowconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=0)

        # Row 1: 3 panels
        # Left: Machine Profile
        self.profile_panel = MachineProfilePanel(
            content,
            on_profile_changed=self._on_profile_changed
        )
        self.profile_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))

        # Middle: DXF Analysis
        self.dxf_panel = DXFAnalysisPanel(
            content,
            on_dxf_loaded=self._on_dxf_loaded
        )
        self.dxf_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=(0, 5))

        # Right: Results Comparison
        self.results_panel = ResultsComparisonPanel(content)
        self.results_panel.grid(row=0, column=2, sticky="nsew", padx=(5, 0), pady=(0, 5))
        self.results_panel.set_calc_command(self._calculate)

        # Row 2: Bottom panels (velocity chart + report)
        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 0))

        bottom.grid_columnconfigure(0, weight=2)
        bottom.grid_columnconfigure(1, weight=1)

        # Velocity profile
        self.velocity_canvas = VelocityProfileCanvas(bottom, width=700, height=150)
        self.velocity_canvas.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # Detailed report
        self.report_panel = DetailedReportPanel(bottom)
        self.report_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

    def _on_profile_changed(self, profile: Dict):
        """Handle machine profile change."""
        logger.debug(f"Profile changed: {profile}")

    def _on_dxf_loaded(self, file_path: str, stats, segments):
        """Handle DXF loaded."""
        self.current_dxf = file_path
        self.toolpath_stats = stats
        self.motion_segments = segments
        self.results_panel.enable_calc(True)
        logger.info(f"DXF loaded: {file_path}, {len(segments)} segments")

    def _calculate(self):
        """Perform calculation and comparison."""
        if not self.toolpath_stats or not self.motion_segments:
            messagebox.showwarning("Brak danych", "Najpierw zaladuj plik DXF.")
            return

        try:
            from costing.motion.motion_planner import (
                MachineProfile, estimate_motion_time, estimate_simple_time,
                plan_speeds, calculate_junction_angles, corner_speed_limit,
                junction_deviation_speed, m_min_to_mm_s
            )

            profile_data = self.profile_panel.get_profile()
            stats = self.toolpath_stats
            segments = self.motion_segments

            # Create machine profile
            machine = MachineProfile(
                max_accel_mm_s2=profile_data["max_accel_mm_s2"],
                max_rapid_mm_s=profile_data["max_rapid_mm_s"],
                square_corner_velocity_mm_s=profile_data["square_corner_velocity_mm_s"],
                junction_deviation_mm=profile_data["junction_deviation_mm"],
                use_junction_deviation=profile_data["use_junction_deviation"]
            )

            v_max_m_min = profile_data["cutting_speed_m_min"]
            v_max_mm_s = m_min_to_mm_s(v_max_m_min)
            pierce_time = profile_data["pierce_time_s"]
            rate_pln_h = profile_data["machine_rate_pln_h"]

            # --- Classic calculation ---
            classic_motion_time = stats.cut_length_mm / v_max_mm_s
            classic_pierce_time = stats.pierce_count * pierce_time
            classic_total_time = classic_motion_time + classic_pierce_time
            classic_cost = (classic_total_time / 3600) * rate_pln_h

            # --- Dynamic calculation ---
            cutting_time, rapid_time = estimate_motion_time(
                segments, machine, v_max_mm_s
            )
            dynamic_pierce_time = stats.pierce_count * pierce_time
            dynamic_total_time = cutting_time + rapid_time + dynamic_pierce_time
            dynamic_cost = (dynamic_total_time / 3600) * rate_pln_h

            # --- Calculate velocities for visualization ---
            cutting_segments = [s for s in segments if not s.is_rapid]
            if cutting_segments:
                lengths = [s.length_mm for s in cutting_segments[:100]]
                angles = calculate_junction_angles(cutting_segments[:100])

                v_junction = []
                for angle in angles:
                    if machine.use_junction_deviation:
                        v = junction_deviation_speed(
                            angle, machine.junction_deviation_mm,
                            machine.max_accel_mm_s2, v_max_mm_s
                        )
                    else:
                        v = corner_speed_limit(
                            angle, machine.square_corner_velocity_mm_s, v_max_mm_s
                        )
                    v_junction.append(v)

                self.planned_velocities = plan_speeds(
                    lengths, v_junction, v_max_mm_s, machine.max_accel_mm_s2
                )
            else:
                self.planned_velocities = []

            # --- Update UI ---
            self.results_panel.set_classic_results(
                classic_motion_time, classic_pierce_time, classic_total_time, classic_cost
            )

            self.results_panel.set_dynamic_results(
                cutting_time, rapid_time, dynamic_pierce_time, dynamic_total_time, dynamic_cost
            )

            # Difference (dynamic - classic)
            time_diff = dynamic_total_time - classic_total_time
            time_diff_pct = (time_diff / classic_total_time * 100) if classic_total_time > 0 else 0
            cost_diff = dynamic_cost - classic_cost
            cost_diff_pct = (cost_diff / classic_cost * 100) if classic_cost > 0 else 0

            self.results_panel.set_difference(
                time_diff, time_diff_pct, cost_diff, cost_diff_pct
            )

            # Velocity profile
            if self.planned_velocities:
                self.velocity_canvas.draw_velocity_profile(
                    self.planned_velocities, v_max_mm_s, lengths
                )

            # Generate report
            report = self._generate_report(
                profile_data, stats, segments, machine,
                classic_motion_time, classic_pierce_time, classic_total_time, classic_cost,
                cutting_time, rapid_time, dynamic_pierce_time, dynamic_total_time, dynamic_cost,
                time_diff, time_diff_pct, cost_diff, cost_diff_pct
            )
            self.report_panel.set_report(report)

            logger.info(f"Calculation complete: classic={classic_total_time:.2f}s, dynamic={dynamic_total_time:.2f}s")

        except Exception as e:
            logger.error(f"Calculation error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Blad obliczen", f"Wystapil blad:\n{e}")

    def _generate_report(self, profile, stats, segments, machine,
                          classic_motion, classic_pierce, classic_total, classic_cost,
                          dynamic_cut, dynamic_rapid, dynamic_pierce, dynamic_total, dynamic_cost,
                          time_diff, time_diff_pct, cost_diff, cost_diff_pct) -> str:
        """Generate detailed text report."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dxf_name = Path(self.current_dxf).name if self.current_dxf else "N/A"

        # Segment analysis
        lengths = [s.length_mm for s in segments]
        short_count = sum(1 for l in lengths if l < 5)
        medium_count = sum(1 for l in lengths if 5 <= l < 20)
        long_count = sum(1 for l in lengths if l >= 20)

        avg_length = sum(lengths) / len(lengths) if lengths else 0
        min_length = min(lengths) if lengths else 0
        max_length = max(lengths) if lengths else 0

        # Count unique contours
        unique_contours = len(set(s.contour_id for s in segments))

        # Calculate effective cutting speed (classic assumes constant v_max)
        v_max_mm_s = profile['cutting_speed_m_min'] * 1000 / 60
        effective_v = stats.cut_length_mm / dynamic_cut if dynamic_cut > 0 else v_max_mm_s
        effective_v_pct = (effective_v / v_max_mm_s) * 100 if v_max_mm_s > 0 else 0

        report = f"""
================================================================================
              RAPORT ANALIZY DYNAMIKI MASZYNY - POROWNANIE WYCEN
================================================================================
Wygenerowano: {timestamp}
Plik DXF: {dxf_name}

================================================================================
                          PARAMETRY DYNAMIKI MASZYNY
================================================================================
  Przyspieszenie max:        {profile['max_accel_mm_s2']:,.0f} mm/s^2
  Predkosc szybka (rapid):   {profile['max_rapid_mm_s']:,.0f} mm/s
  Predkosc w rogu 90st:      {profile['square_corner_velocity_mm_s']:,.0f} mm/s
  Junction deviation:        {profile['junction_deviation_mm']:.3f} mm
  Model Junction Deviation:  {'TAK' if profile['use_junction_deviation'] else 'NIE'}

  Predkosc ciecia:           {profile['cutting_speed_m_min']:.1f} m/min ({v_max_mm_s:.1f} mm/s)
  Czas przebicia:            {profile['pierce_time_s']:.2f} s
  Stawka maszyny:            {profile['machine_rate_pln_h']:.0f} PLN/h

================================================================================
                            STATYSTYKI TOOLPATH
================================================================================
  Dlugosc ciecia:            {stats.cut_length_mm:,.1f} mm ({stats.cut_length_mm/1000:.2f} m)
  Liczba przebic:            {stats.pierce_count}
  LICZBA KONTUROW (encji):   {unique_contours} <- KAZDY KONTUR = START/STOP
  Liczba segmentow ruchu:    {len(segments)}
  Krotkie segmenty (<5mm):   {stats.short_segment_ratio:.1%}
  Pole powierzchni:          {stats.occupied_area_mm2:,.0f} mm^2

  Analiza dlugosci segmentow:
    - Krotkie (<5mm):        {short_count} ({short_count/len(segments)*100:.1f}%)
    - Srednie (5-20mm):      {medium_count} ({medium_count/len(segments)*100:.1f}%)
    - Dlugie (>20mm):        {long_count} ({long_count/len(segments)*100:.1f}%)
    - Min: {min_length:.2f} mm, Max: {max_length:.2f} mm, Srednia: {avg_length:.2f} mm

================================================================================
                         OBLICZENIA - METODA KLASYCZNA
================================================================================
  Wzor: czas = dlugosc_ciecia / predkosc + przebicia * czas_przebicia

  BLAD TEJ METODY: Zaklada stala predkosc V_max na calej dlugosci!
                   Ignoruje przyspieszenia, hamowania i limity w rogach.

  Czas ruchu:                {classic_motion:.2f} s ({classic_motion/60:.2f} min)
    = {stats.cut_length_mm:.1f} mm / {v_max_mm_s:.1f} mm/s

  Czas przebic:              {classic_pierce:.2f} s
    = {stats.pierce_count} x {profile['pierce_time_s']:.2f} s

  CZAS CALKOWITY:            {classic_total:.2f} s ({classic_total/60:.2f} min)

  KOSZT:                     {classic_cost:.2f} PLN
    = ({classic_total:.2f} s / 3600) x {profile['machine_rate_pln_h']:.0f} PLN/h

================================================================================
                      OBLICZENIA - METODA DYNAMICZNA
================================================================================
  Algorytm: Lookahead z profilem trapezoidowym (acc -> cruise -> dec)

  KLUCZOWE: Kazdy z {unique_contours} konturow:
    - START od V=0 (po przebiciu)
    - Przyspieszanie do V_max (profil trapezoidowy)
    - Hamowanie w rogach (V_junction)
    - STOP do V=0 na koncu konturu

  Czas ciecia:               {dynamic_cut:.2f} s ({dynamic_cut/60:.2f} min)
    (uwzglednia przyspieszenia/hamowania i limity w naroznikach)

  Czas ruchow szybkich:      {dynamic_rapid:.2f} s

  Czas przebic:              {dynamic_pierce:.2f} s

  CZAS CALKOWITY:            {dynamic_total:.2f} s ({dynamic_total/60:.2f} min)

  KOSZT:                     {dynamic_cost:.2f} PLN

  EFEKTYWNA PREDKOSC CIECIA: {effective_v:.1f} mm/s = {effective_v_pct:.1f}% nominalnej V_max
    (to jest rzeczywista srednia predkosc uwzgledniajaca dynamike)

================================================================================
                              POROWNANIE
================================================================================
  Roznica czasu:             {'+' if time_diff > 0 else ''}{time_diff:.2f} s ({'+' if time_diff_pct > 0 else ''}{time_diff_pct:.1f}%)
  Roznica kosztu:            {'+' if cost_diff > 0 else ''}{cost_diff:.2f} PLN ({'+' if cost_diff_pct > 0 else ''}{cost_diff_pct:.1f}%)

  Interpretacja:
  {'Metoda dynamiczna daje DLUZSZY czas - to PRAWIDLOWY wynik!' if time_diff > 0 else 'Metoda dynamiczna daje KROTSZY czas - nietypowe.'}

  DLACZEGO ROZNICA JEST TAK DUZA?
  Dla {unique_contours} konturow maszyna musi:
    - {unique_contours}x przyspieszyc od zera do V_max
    - {unique_contours}x wyhamowac do zera
    - Hamowac w kazdym rogu/zakrecie

  Na krotkich segmentach (srednia {avg_length:.1f}mm) maszyna nie osiaga V_max!
  Dlatego efektywna predkosc ({effective_v:.1f} mm/s) << nominalna ({v_max_mm_s:.1f} mm/s)

================================================================================
                         WPLYW PARAMETROW DYNAMIKI
================================================================================
  Wyzsze przyspieszenie     -> szybsze osiaganie predkosci max -> krotszy czas
  Wyzsza predkosc w rogach  -> mniejsze hamowanie w naroznikach -> krotszy czas
  Wiecej konturow           -> wiecej startow/stopow -> DUZO dluzszy czas

  Dla tego detalu ({unique_contours} konturow, sredni segment {avg_length:.1f}mm):
    - {'!!! BARDZO DUZY wplyw dynamiki - setki start/stop i krotkie segmenty !!!' if unique_contours > 50 and avg_length < 10 else 'DUZY wplyw dynamiki - wiele konturow' if unique_contours > 20 else 'UMIARKOWANY wplyw dynamiki' if unique_contours > 5 else 'MALY wplyw dynamiki'}

================================================================================
                              KONIEC RAPORTU
================================================================================
"""
        return report


# =============================================================================
# Standalone launch
# =============================================================================

def launch_motion_dynamics_test_window(parent=None):
    """Launch the motion dynamics test window."""
    window = MotionDynamicsTestWindow(parent)
    return window


if __name__ == "__main__":
    # Test standalone
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    window = MotionDynamicsTestWindow(root)
    window.mainloop()
