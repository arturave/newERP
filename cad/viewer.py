"""
CAD 2D Viewer - Główne okno podglądu i edycji DXF
=================================================
Interaktywny viewer CAD 2D z funkcjami zoom, pan, wymiarowanie i edycja.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

# Kolory przycisków toggle
TOGGLE_ACTIVE_COLOR = "#2d5a2d"    # Zielony - aktywny
TOGGLE_INACTIVE_COLOR = "#333333"  # Ciemnoszary - nieaktywny


class ToolTip:
    """Prosty tooltip dla widgetów Tkinter/CTk"""

    def __init__(self, widget, text: str, delay: int = 500):
        """
        Args:
            widget: Widget do którego przypisany jest tooltip
            text: Tekst tooltipa
            delay: Opóźnienie w ms przed pokazaniem
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.scheduled_id = None

        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<ButtonPress>", self._on_leave)

    def _on_enter(self, event=None):
        """Zaplanuj pokazanie tooltipa"""
        self._cancel_scheduled()
        self.scheduled_id = self.widget.after(self.delay, self._show_tooltip)

    def _on_leave(self, event=None):
        """Ukryj tooltip"""
        self._cancel_scheduled()
        self._hide_tooltip()

    def _cancel_scheduled(self):
        """Anuluj zaplanowane pokazanie"""
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None

    def _show_tooltip(self):
        """Pokaż tooltip"""
        if self.tooltip_window:
            return

        # Pozycja - poniżej widgetu
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Utwórz okno tooltipa
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        # Etykieta z tekstem
        label = tk.Label(
            tw, text=self.text,
            background="#ffffe0",  # Jasny żółty
            foreground="#000000",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=6, pady=3
        )
        label.pack()

        # Wycentruj względem pozycji x
        tw.update_idletasks()
        width = tw.winfo_width()
        tw.wm_geometry(f"+{x - width // 2}+{y}")

    def _hide_tooltip(self):
        """Ukryj tooltip"""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    ctk = tk  # Fallback

from .canvas import CADCanvas
from .tools.dimension import DimensionTool

# Import DXF readers
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Primary: dxfgrabber reader (proven 100% accurate)
try:
    from .dxf_grabber_reader import DXFGrabberReader, SimplePart
    HAS_DXFGRABBER = True
except ImportError:
    DXFGrabberReader = None
    SimplePart = None
    HAS_DXFGRABBER = False

# Fallback: core.dxf reader
try:
    from core.dxf import UnifiedDXFReader, DXFPart
    HAS_UNIFIED = True
except ImportError:
    UnifiedDXFReader = None
    DXFPart = None
    HAS_UNIFIED = False


class CAD2DViewer(ctk.CTkToplevel if HAS_CTK else tk.Toplevel):
    """
    Główne okno CAD 2D Viewer.

    Layout:
    +----------------------------------+
    | Toolbar: File | Zoom | Tools     |
    +----------------------------------+
    |                |                 |
    |    Canvas      |  Info Panel     |
    |                |                 |
    +----------------------------------+
    | Status: Scale | Position | Size  |
    +----------------------------------+
    """

    def __init__(
        self,
        parent=None,
        filepath: str = None,
        part: 'DXFPart' = None,
        on_close: Callable = None,
        on_engrave_change: Callable = None,
        part_index: int = None,
        **kwargs
    ):
        """
        Args:
            parent: Widget rodzica
            filepath: Ścieżka do pliku DXF do otwarcia
            part: DXFPart do wyświetlenia (alternatywa dla filepath)
            on_close: Callback przy zamknięciu okna
            on_engrave_change: Callback przy zmianie wyboru warstw grawerowania
                               Signature: on_engrave_change(filepath, engraving_length_mm, selected_layers)
            part_index: Indeks detalu w liście (opcjonalny, dla callback)
        """
        super().__init__(parent, **kwargs)

        self.title("CAD 2D Viewer")
        self.geometry("1200x800")

        # Stan
        self._part = None  # SimplePart or DXFPart
        self._filepath: str = ""
        # Use dxfgrabber as primary reader (proven 100% accurate)
        if HAS_DXFGRABBER:
            self._reader = DXFGrabberReader()
            logger.info("Using DXFGrabberReader (primary)")
        elif HAS_UNIFIED:
            self._reader = UnifiedDXFReader()
            logger.info("Using UnifiedDXFReader (fallback)")
        else:
            self._reader = None
            logger.warning("No DXF reader available!")
        self._on_close = on_close
        self._on_engrave_change = on_engrave_change
        self._part_index = part_index
        self._modified = False

        # UI
        self._setup_ui()
        self._setup_bindings()

        # Załaduj dane
        if part:
            self.set_part(part)
        elif filepath:
            self.load_file(filepath)

        # Focus
        self.focus_force()

    def _setup_ui(self):
        """Skonfiguruj interfejs użytkownika"""
        # Główna ramka
        self._main_frame = ctk.CTkFrame(self) if HAS_CTK else ttk.Frame(self)
        self._main_frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar
        self._setup_toolbar()

        # Środkowa część (canvas + info panel)
        self._center_frame = ctk.CTkFrame(self._main_frame) if HAS_CTK else ttk.Frame(self._main_frame)
        self._center_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Canvas (lewa strona)
        self._canvas_frame = ctk.CTkFrame(self._center_frame) if HAS_CTK else ttk.Frame(self._center_frame)
        self._canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas = CADCanvas(self._canvas_frame)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Narzędzie wymiarowania
        self._dimension_tool = DimensionTool(self._canvas)

        # Zarejestruj callback do przerysowywania wymiarów po zoom/pan
        self._canvas.add_redraw_callback(self._dimension_tool.redraw_all)

        # Info panel (prawa strona)
        self._setup_info_panel()

        # Status bar
        self._setup_statusbar()

        # Motion callback dla status bar (NIE nadpisuj bindu!)
        self._canvas.add_motion_callback(self._on_canvas_motion)

    def _setup_toolbar(self):
        """Skonfiguruj toolbar z ikonami i tooltipami"""
        self._toolbar = ctk.CTkFrame(self._main_frame, height=40) if HAS_CTK else ttk.Frame(self._main_frame)
        self._toolbar.pack(fill=tk.X, padx=5, pady=(5, 0))
        self._toolbar.pack_propagate(False)

        # Lista tooltipów (przechowujemy referencje)
        self._tooltips = []

        # Style dla przycisków z ikonami
        icon_btn = {"width": 36, "height": 28, "font": ("Segoe UI Symbol", 14)} if HAS_CTK else {}

        # File section
        if HAS_CTK:
            btn_open = ctk.CTkButton(self._toolbar, text="\U0001F4C2", command=self._on_open, **icon_btn)
            btn_open.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(btn_open, "Otwórz plik DXF (Ctrl+O)"))

            btn_save = ctk.CTkButton(self._toolbar, text="\U0001F4BE", command=self._on_save, **icon_btn)
            btn_save.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(btn_save, "Zapisz plik DXF (Ctrl+S)"))
        else:
            btn_open = ttk.Button(self._toolbar, text="Open", command=self._on_open)
            btn_open.pack(side=tk.LEFT, padx=2)
            btn_save = ttk.Button(self._toolbar, text="Save", command=self._on_save)
            btn_save.pack(side=tk.LEFT, padx=2)

        # Separator
        ttk.Separator(self._toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=5)

        # Zoom section
        if HAS_CTK:
            btn_fit = ctk.CTkButton(self._toolbar, text="\U0001F50D", command=self._on_zoom_fit, **icon_btn)
            btn_fit.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(btn_fit, "Dopasuj do okna (Home)"))

            btn_zin = ctk.CTkButton(self._toolbar, text="+", command=self._on_zoom_in, **icon_btn)
            btn_zin.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(btn_zin, "Powiększ (Ctrl++)"))

            btn_zout = ctk.CTkButton(self._toolbar, text="-", command=self._on_zoom_out, **icon_btn)
            btn_zout.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(btn_zout, "Pomniejsz (Ctrl+-)"))
        else:
            ttk.Button(self._toolbar, text="Fit", command=self._on_zoom_fit).pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="+", command=self._on_zoom_in).pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="-", command=self._on_zoom_out).pack(side=tk.LEFT, padx=2)

        # Separator
        ttk.Separator(self._toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=5)

        # Grid toggle button
        self._grid_var = tk.BooleanVar(value=True)
        if HAS_CTK:
            self._grid_btn = ctk.CTkButton(
                self._toolbar, text="#", command=self._on_grid_toggle,
                fg_color=TOGGLE_ACTIVE_COLOR, **icon_btn
            )
        else:
            self._grid_btn = ttk.Button(self._toolbar, text="#", command=self._on_grid_toggle)
        self._grid_btn.pack(side=tk.LEFT, padx=2)
        self._tooltips.append(ToolTip(self._grid_btn, "Siatka wł/wył"))

        # Snap toggle button
        self._snap_var = tk.BooleanVar(value=True)
        if HAS_CTK:
            self._snap_btn = ctk.CTkButton(
                self._toolbar, text="\U0001F4CD", command=self._on_snap_toggle,
                fg_color=TOGGLE_ACTIVE_COLOR, **icon_btn
            )
        else:
            self._snap_btn = ttk.Button(self._toolbar, text="Snap", command=self._on_snap_toggle)
        self._snap_btn.pack(side=tk.LEFT, padx=2)
        self._tooltips.append(ToolTip(self._snap_btn, "Przyciąganie do punktów wł/wył"))

        # Separator
        ttk.Separator(self._toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=5)

        # Dimension section
        self._dim_active = False  # Stan przycisku wymiarowania
        if HAS_CTK:
            btn_auto = ctk.CTkButton(self._toolbar, text="Auto", command=self._on_auto_dimension, width=50, height=28)
            btn_auto.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(btn_auto, "Automatyczne wymiary bbox"))

            self._dim_btn = ctk.CTkButton(
                self._toolbar, text="\U0001F4CF", command=self._on_dimension_tool,
                fg_color=TOGGLE_INACTIVE_COLOR, **icon_btn
            )
            self._dim_btn.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(self._dim_btn, "Wymiarowanie ręczne wł/wył"))

            btn_clear = ctk.CTkButton(self._toolbar, text="\U0001F5D1", command=self._on_clear_dimensions, **icon_btn)
            btn_clear.pack(side=tk.LEFT, padx=2)
            self._tooltips.append(ToolTip(btn_clear, "Usuń wszystkie wymiary"))
        else:
            ttk.Button(self._toolbar, text="Auto", command=self._on_auto_dimension).pack(side=tk.LEFT, padx=2)
            self._dim_btn = ttk.Button(self._toolbar, text="Dim", command=self._on_dimension_tool)
            self._dim_btn.pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="Clear", command=self._on_clear_dimensions).pack(side=tk.LEFT, padx=2)

        # Zoom label (prawa strona)
        self._zoom_label = ctk.CTkLabel(self._toolbar, text="100%", font=("Consolas", 11)) if HAS_CTK else ttk.Label(self._toolbar, text="100%")
        self._zoom_label.pack(side=tk.RIGHT, padx=10)

    def _setup_info_panel(self):
        """Skonfiguruj panel informacyjny"""
        self._info_frame = ctk.CTkFrame(self._center_frame, width=280) if HAS_CTK else ttk.Frame(self._center_frame)
        self._info_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        self._info_frame.pack_propagate(False)

        # Tytuł
        title = ctk.CTkLabel(
            self._info_frame, text="Part Info",
            font=("Arial", 14, "bold") if HAS_CTK else None
        ) if HAS_CTK else ttk.Label(self._info_frame, text="Part Info", font=("Arial", 14, "bold"))
        title.pack(pady=10)

        # Info text
        self._info_text = tk.Text(
            self._info_frame,
            width=30, height=12,
            bg="#2d2d2d" if HAS_CTK else "white",
            fg="white" if HAS_CTK else "black",
            font=("Consolas", 10),
            state=tk.DISABLED
        )
        self._info_text.pack(fill=tk.X, padx=5, pady=5)

        # Layers section
        layers_label = ctk.CTkLabel(
            self._info_frame, text="Layers",
            font=("Arial", 12, "bold") if HAS_CTK else None
        ) if HAS_CTK else ttk.Label(self._info_frame, text="Layers", font=("Arial", 12, "bold"))
        layers_label.pack(pady=(10, 5))

        self._layers_frame = ctk.CTkScrollableFrame(self._info_frame, height=120) if HAS_CTK else ttk.Frame(self._info_frame)
        self._layers_frame.pack(fill=tk.X, padx=5, pady=5)

        # === ENGRAVING SECTION ===
        self._setup_engraving_section()

    def _setup_engraving_section(self):
        """Skonfiguruj sekcję wyboru warstwy grawerowania"""
        # Separator
        sep = ttk.Separator(self._info_frame, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=5, pady=10)

        # Tytuł sekcji
        engrave_title = ctk.CTkLabel(
            self._info_frame, text="Engraving Selection",
            font=("Arial", 12, "bold"), text_color="#f59e0b"
        ) if HAS_CTK else ttk.Label(self._info_frame, text="Engraving Selection", font=("Arial", 12, "bold"))
        engrave_title.pack(pady=(0, 5))

        # Info o auto-detekcji
        auto_info = ctk.CTkLabel(
            self._info_frame, text="Select layers to mark as engraving:",
            font=("Arial", 9), text_color="#888888"
        ) if HAS_CTK else ttk.Label(self._info_frame, text="Select layers to mark as engraving:")
        auto_info.pack(pady=(0, 5))

        # Scrollable frame dla checkboxów warstw
        self._engrave_layers_frame = ctk.CTkScrollableFrame(
            self._info_frame, height=100,
            fg_color="#1a1a1a" if HAS_CTK else None
        ) if HAS_CTK else ttk.Frame(self._info_frame)
        self._engrave_layers_frame.pack(fill=tk.X, padx=5, pady=5)

        # Etykieta z sumaryczną długością graweru
        self._engrave_length_frame = ctk.CTkFrame(self._info_frame, fg_color="#2d2d2d") if HAS_CTK else ttk.Frame(self._info_frame)
        self._engrave_length_frame.pack(fill=tk.X, padx=5, pady=5)

        engrave_icon = ctk.CTkLabel(
            self._engrave_length_frame, text="Engraving:",
            font=("Arial", 10, "bold"), text_color="#f59e0b"
        ) if HAS_CTK else ttk.Label(self._engrave_length_frame, text="Engraving:")
        engrave_icon.pack(side=tk.LEFT, padx=5, pady=5)

        self._engrave_length_label = ctk.CTkLabel(
            self._engrave_length_frame, text="0.00 mm (0.00 m)",
            font=("Consolas", 11), text_color="#22c55e"
        ) if HAS_CTK else ttk.Label(self._engrave_length_frame, text="0.00 mm (0.00 m)")
        self._engrave_length_label.pack(side=tk.LEFT, padx=5, pady=5)

        # Przycisk "Zastosuj" do zatwierdzenia wyboru
        self._apply_engrave_btn = ctk.CTkButton(
            self._info_frame, text="Apply Engraving Selection",
            command=self._on_apply_engraving,
            fg_color="#f59e0b", hover_color="#d97706",
            height=30
        ) if HAS_CTK else ttk.Button(self._info_frame, text="Apply Engraving Selection", command=self._on_apply_engraving)
        self._apply_engrave_btn.pack(fill=tk.X, padx=5, pady=5)

        # Stan wyboru warstw do grawerowania
        self._engrave_layer_vars = {}  # {layer_name: BooleanVar}
        self._layer_lengths = {}  # {layer_name: length_mm}

    def _setup_statusbar(self):
        """Skonfiguruj status bar"""
        self._statusbar = ctk.CTkFrame(self._main_frame, height=25) if HAS_CTK else ttk.Frame(self._main_frame)
        self._statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        self._statusbar.pack_propagate(False)

        # Pozycja myszy
        self._pos_label = ctk.CTkLabel(
            self._statusbar, text="X: 0.00  Y: 0.00",
            font=("Consolas", 10)
        ) if HAS_CTK else ttk.Label(self._statusbar, text="X: 0.00  Y: 0.00")
        self._pos_label.pack(side=tk.LEFT, padx=10)

        # Separator
        sep = ttk.Separator(self._statusbar, orient=tk.VERTICAL)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Wymiary detalu
        self._size_label = ctk.CTkLabel(
            self._statusbar, text="Size: - x - mm",
            font=("Consolas", 10)
        ) if HAS_CTK else ttk.Label(self._statusbar, text="Size: - x - mm")
        self._size_label.pack(side=tk.LEFT, padx=10)

        # Separator
        sep2 = ttk.Separator(self._statusbar, orient=tk.VERTICAL)
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Plik
        self._file_label = ctk.CTkLabel(
            self._statusbar, text="No file loaded",
            font=("Consolas", 10)
        ) if HAS_CTK else ttk.Label(self._statusbar, text="No file loaded")
        self._file_label.pack(side=tk.RIGHT, padx=10)

    def _setup_bindings(self):
        """Skonfiguruj skróty klawiszowe"""
        self.bind("<Control-o>", lambda e: self._on_open())
        self.bind("<Control-s>", lambda e: self._on_save())
        self.bind("<Control-plus>", lambda e: self._on_zoom_in())
        self.bind("<Control-minus>", lambda e: self._on_zoom_out())
        self.bind("<Control-0>", lambda e: self._on_zoom_fit())
        self.bind("<Home>", lambda e: self._on_zoom_fit())
        self.bind("<Escape>", lambda e: self._on_close_window())

        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

    # ==================== Actions ====================

    def load_file(self, filepath: str) -> bool:
        """
        Załaduj plik DXF.

        Args:
            filepath: Ścieżka do pliku DXF

        Returns:
            True jeśli sukces
        """
        if not self._reader:
            messagebox.showerror("Error", "DXF reader not available")
            return False

        if not os.path.exists(filepath):
            messagebox.showerror("Error", f"File not found: {filepath}")
            return False

        try:
            part = self._reader.read(filepath)
            if part:
                self._filepath = filepath
                self.set_part(part)
                return True
            else:
                messagebox.showerror("Error", f"Failed to read DXF: {filepath}")
                return False
        except Exception as e:
            logger.error(f"Error loading file: {e}")
            messagebox.showerror("Error", f"Error loading file: {e}")
            return False

    def set_part(self, part: 'DXFPart'):
        """Ustaw detal do wyświetlenia"""
        self._part = part
        self._canvas.set_part(part)
        self._update_info()
        self._update_layers()
        self._update_status()
        self._modified = False

    def _update_info(self):
        """Aktualizuj panel informacyjny"""
        self._info_text.config(state=tk.NORMAL)
        self._info_text.delete("1.0", tk.END)

        if self._part:
            # Handle SimplePart (dxfgrabber) vs DXFPart (core.dxf)
            if hasattr(self._part, 'paths'):
                # SimplePart
                info = f"""Name: {self._part.name}

Dimensions:
  Width:  {self._part.width:.2f} mm
  Height: {self._part.height:.2f} mm

Paths: {self._part.path_count}

Reader: DXFGrabberReader
"""
            else:
                # DXFPart
                info = f"""Name: {self._part.name}

Dimensions:
  Width:  {self._part.width:.2f} mm
  Height: {self._part.height:.2f} mm

Area:
  Bbox:    {self._part.bounding_area:.2f} mm²
  Contour: {self._part.contour_area:.2f} mm²

Cutting:
  Length:  {self._part.cut_length_mm:.2f} mm
  Pierces: {self._part.pierce_count}

Material: {self._part.material or '-'}
Thickness: {self._part.thickness or '-'} mm
Quantity: {self._part.quantity}

Contour points: {len(self._part.outer_contour.points) if self._part.outer_contour else 0}
Holes: {len(self._part.holes)}

Reader: UnifiedDXFReader
"""
            self._info_text.insert("1.0", info)

        self._info_text.config(state=tk.DISABLED)

    def _update_layers(self):
        """Aktualizuj listę warstw"""
        # Wyczyść
        for widget in self._layers_frame.winfo_children():
            widget.destroy()

        if not self._part:
            return

        # SimplePart doesn't have layers dict
        if not hasattr(self._part, 'layers'):
            return

        for name, layer in self._part.layers.items():
            frame = ctk.CTkFrame(self._layers_frame) if HAS_CTK else ttk.Frame(self._layers_frame)
            frame.pack(fill=tk.X, pady=2)

            # Checkbox widoczności
            var = tk.BooleanVar(value=layer.visible)
            if HAS_CTK:
                ctk.CTkCheckBox(
                    frame, text="",
                    variable=var,
                    width=20,
                    command=lambda n=name, v=var: self._on_layer_toggle(n, v)
                ).pack(side=tk.LEFT)
            else:
                ttk.Checkbutton(
                    frame, text="",
                    variable=var,
                    command=lambda n=name, v=var: self._on_layer_toggle(n, v)
                ).pack(side=tk.LEFT)

            # Kolor
            color_btn = tk.Label(
                frame,
                bg=layer.display_color,
                width=2, height=1
            )
            color_btn.pack(side=tk.LEFT, padx=2)

            # Nazwa
            label = ctk.CTkLabel(frame, text=f"{name} ({layer.entity_count})") if HAS_CTK else ttk.Label(frame, text=f"{name} ({layer.entity_count})")
            label.pack(side=tk.LEFT, padx=5)

        # Po aktualizacji warstw, aktualizuj też panel grawerowania
        self._update_engrave_layers()

    def _update_engrave_layers(self):
        """Aktualizuj panel wyboru warstw grawerowania"""
        # Wyczyść poprzednie checkboxy
        for widget in self._engrave_layers_frame.winfo_children():
            widget.destroy()

        self._engrave_layer_vars.clear()
        self._layer_lengths.clear()

        if not self._part:
            self._engrave_length_label.configure(text="0.00 mm (0.00 m)")
            return

        # Wczytaj ustawienia słów kluczowych graweru
        marking_keywords = self._get_marking_keywords()

        # Oblicz długości dla każdej warstwy
        if hasattr(self._part, 'paths'):
            # SimplePart - grupuj paths po warstwie
            layer_paths = {}
            for path in self._part.paths:
                layer = path.layer
                if layer not in layer_paths:
                    layer_paths[layer] = []
                layer_paths[layer].append(path)

            for layer_name, paths in sorted(layer_paths.items()):
                # Oblicz długość ścieżek w tej warstwie
                length_mm = self._calculate_paths_length(paths)
                self._layer_lengths[layer_name] = length_mm

                # Sprawdź czy warstwa jest automatycznie wykryta jako grawer
                is_auto_engrave = self._is_marking_layer(layer_name, marking_keywords)

                # Utwórz wiersz dla warstwy
                frame = ctk.CTkFrame(self._engrave_layers_frame, fg_color="transparent") if HAS_CTK else ttk.Frame(self._engrave_layers_frame)
                frame.pack(fill=tk.X, pady=2)

                # Checkbox do wyboru jako grawer
                var = tk.BooleanVar(value=is_auto_engrave)
                self._engrave_layer_vars[layer_name] = var

                if HAS_CTK:
                    cb = ctk.CTkCheckBox(
                        frame, text="",
                        variable=var,
                        width=20,
                        command=self._on_engrave_selection_change,
                        fg_color="#f59e0b", hover_color="#d97706"
                    )
                else:
                    cb = ttk.Checkbutton(
                        frame, text="",
                        variable=var,
                        command=self._on_engrave_selection_change
                    )
                cb.pack(side=tk.LEFT)

                # Nazwa warstwy
                color = "#f59e0b" if is_auto_engrave else "#ffffff"
                name_label = ctk.CTkLabel(
                    frame, text=layer_name,
                    font=("Arial", 10), text_color=color
                ) if HAS_CTK else ttk.Label(frame, text=layer_name)
                name_label.pack(side=tk.LEFT, padx=5)

                # Długość
                length_text = f"{length_mm:.1f} mm"
                length_label = ctk.CTkLabel(
                    frame, text=length_text,
                    font=("Consolas", 9), text_color="#888888"
                ) if HAS_CTK else ttk.Label(frame, text=length_text)
                length_label.pack(side=tk.RIGHT, padx=5)

        elif hasattr(self._part, 'layers'):
            # DXFPart z layers dict - placeholder (rzadko używane)
            for name in sorted(self._part.layers.keys()):
                self._layer_lengths[name] = 0.0
                var = tk.BooleanVar(value=False)
                self._engrave_layer_vars[name] = var

        # Aktualizuj sumaryczną długość
        self._on_engrave_selection_change()

    def _calculate_paths_length(self, paths) -> float:
        """Oblicz sumaryczną długość ścieżek"""
        import math
        total_length = 0.0
        for path in paths:
            points = path.points
            for i in range(len(points) - 1):
                p1, p2 = points[i], points[i + 1]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                total_length += math.sqrt(dx * dx + dy * dy)
            # Jeśli zamknięta, dodaj odcinek powrotny
            if path.is_closed and len(points) >= 2:
                p1, p2 = points[-1], points[0]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                total_length += math.sqrt(dx * dx + dy * dy)
        return total_length

    def _get_marking_keywords(self) -> set:
        """Pobierz słowa kluczowe graweru z ustawień"""
        try:
            from orders.gui.settings_dialog import load_layer_settings
            settings = load_layer_settings()
            return set(kw.lower() for kw in settings.get('marking_keywords', []))
        except ImportError:
            # Domyślne słowa kluczowe
            return {'grawer', 'marking', 'opis', 'text', 'engrave', 'mark', 'sign'}

    def _is_marking_layer(self, layer_name: str, keywords: set) -> bool:
        """Sprawdź czy warstwa to warstwa grawerowania"""
        layer_lower = layer_name.lower()
        for keyword in keywords:
            if keyword in layer_lower:
                return True
        return False

    def _on_engrave_selection_change(self):
        """Callback przy zmianie wyboru warstwy grawerowania"""
        total_length = 0.0
        for layer_name, var in self._engrave_layer_vars.items():
            if var.get():
                total_length += self._layer_lengths.get(layer_name, 0.0)

        # Aktualizuj etykietę
        length_m = total_length / 1000.0
        self._engrave_length_label.configure(
            text=f"{total_length:.2f} mm ({length_m:.3f} m)"
        )

    def _on_apply_engraving(self):
        """Zastosuj wybór warstw grawerowania"""
        # Oblicz całkowitą długość wybranych warstw
        total_length = 0.0
        selected_layers = []
        for layer_name, var in self._engrave_layer_vars.items():
            if var.get():
                total_length += self._layer_lengths.get(layer_name, 0.0)
                selected_layers.append(layer_name)

        logger.info(f"[CADViewer] Apply engraving: {total_length:.2f} mm, layers: {selected_layers}")

        # Wywołaj callback jeśli ustawiony
        if self._on_engrave_change:
            try:
                self._on_engrave_change(
                    filepath=self._filepath,
                    engraving_length_mm=total_length,
                    selected_layers=selected_layers,
                    part_index=self._part_index
                )
                messagebox.showinfo("Success", f"Engraving updated:\n{total_length:.2f} mm ({total_length/1000:.3f} m)")
            except Exception as e:
                logger.error(f"Error in engrave callback: {e}")
                messagebox.showerror("Error", f"Could not update engraving: {e}")
        else:
            messagebox.showinfo("Info", f"Engraving length: {total_length:.2f} mm\n\n"
                               f"Selected layers:\n" + "\n".join(f"  - {l}" for l in selected_layers))

    def get_engraving_info(self) -> dict:
        """Pobierz informacje o wybranym grawerowaniu"""
        total_length = 0.0
        selected_layers = []
        for layer_name, var in self._engrave_layer_vars.items():
            if var.get():
                total_length += self._layer_lengths.get(layer_name, 0.0)
                selected_layers.append(layer_name)

        return {
            'engraving_length_mm': total_length,
            'selected_layers': selected_layers,
            'all_layers': list(self._layer_lengths.keys()),
            'layer_lengths': dict(self._layer_lengths)
        }

    def _update_status(self):
        """Aktualizuj status bar"""
        if self._part:
            self._size_label.configure(
                text=f"Size: {self._part.width:.1f} x {self._part.height:.1f} mm"
            )
        else:
            self._size_label.configure(text="Size: - x - mm")

        if self._filepath:
            self._file_label.configure(text=os.path.basename(self._filepath))
        else:
            self._file_label.configure(text="No file loaded")

        # Zoom
        zoom_pct = self._canvas.current_zoom_percent
        self._zoom_label.configure(text=f"{zoom_pct:.0f}%")

    # ==================== Event handlers ====================

    def _on_open(self):
        """Otwórz plik"""
        filepath = filedialog.askopenfilename(
            title="Open DXF File",
            filetypes=[
                ("DXF Files", "*.dxf"),
                ("All Files", "*.*")
            ]
        )
        if filepath:
            self.load_file(filepath)

    def _on_save(self):
        """Zapisz plik"""
        if not self._part:
            return

        filepath = filedialog.asksaveasfilename(
            title="Save DXF File",
            defaultextension=".dxf",
            filetypes=[
                ("DXF Files", "*.dxf"),
                ("All Files", "*.*")
            ]
        )
        if filepath:
            # TODO: Implementacja zapisu
            messagebox.showinfo("Info", "Save not implemented yet")

    def _on_zoom_fit(self):
        """Zoom fit"""
        self._canvas.zoom_fit()
        self._update_status()

    def _on_zoom_in(self):
        """Zoom in"""
        self._canvas.zoom_in()
        self._update_status()

    def _on_zoom_out(self):
        """Zoom out"""
        self._canvas.zoom_out()
        self._update_status()

    def _on_grid_toggle(self):
        """Włącz/wyłącz siatkę"""
        self._grid_var.set(not self._grid_var.get())
        self._canvas.set_grid_visible(self._grid_var.get())
        # Update button color (Active/Inactive)
        if HAS_CTK:
            color = TOGGLE_ACTIVE_COLOR if self._grid_var.get() else TOGGLE_INACTIVE_COLOR
            self._grid_btn.configure(fg_color=color)

    def _on_snap_toggle(self):
        """Włącz/wyłącz snap"""
        self._snap_var.set(not self._snap_var.get())
        self._canvas.set_snap_enabled(self._snap_var.get())
        # Update button color (Active/Inactive)
        if HAS_CTK:
            color = TOGGLE_ACTIVE_COLOR if self._snap_var.get() else TOGGLE_INACTIVE_COLOR
            self._snap_btn.configure(fg_color=color)

    def _on_auto_dimension(self):
        """Automatyczne wymiarowanie (bbox + otwory)"""
        if not self._part:
            return

        # 1) Zawsze wymiaruj bounding box, jeśli są min/max
        if hasattr(self._part, "min_x") and hasattr(self._part, "max_x"):
            self._dimension_tool.auto_dimension_bbox(self._part)

        # 2) Otwory – tylko jeśli obiekt ma atrybut holes
        if hasattr(self._part, "holes") and getattr(self._part, "holes", None):
            self._dimension_tool.auto_dimension_holes(self._part, max_holes=5)

        self._modified = True

    def _on_dimension_tool(self):
        """Aktywuj ręczne wymiarowanie (toggle)"""
        if not self._part:
            return

        # Toggle aktywacji
        self._dim_active = not self._dim_active
        if self._dim_active:
            self._dimension_tool.activate(mode="linear")
        else:
            self._dimension_tool.deactivate()

        # Update button color (Active/Inactive)
        if HAS_CTK:
            color = TOGGLE_ACTIVE_COLOR if self._dim_active else TOGGLE_INACTIVE_COLOR
            self._dim_btn.configure(fg_color=color)

    def _on_clear_dimensions(self):
        """Wyczyść wszystkie wymiary"""
        self._dimension_tool.clear_dimensions()
        self._canvas.redraw()
        self._modified = True

    def _on_layer_toggle(self, layer_name: str, var: tk.BooleanVar):
        """Włącz/wyłącz widoczność warstwy"""
        if self._part and layer_name in self._part.layers:
            self._part.layers[layer_name].visible = var.get()
            self._canvas.redraw()

    def _on_canvas_motion(self, event, wx: float, wy: float, snapped_x: float, snapped_y: float):
        """
        Motion callback - aktualizuj pozycję w status bar.

        Args:
            event: Tkinter event
            wx, wy: World coordinates (bez snap)
            snapped_x, snapped_y: World coordinates (ze snap jeśli aktywny)
        """
        # Pokaż pozycję snap jeśli jest aktywny
        if (snapped_x, snapped_y) != (wx, wy):
            self._pos_label.configure(text=f"X: {snapped_x:.2f}  Y: {snapped_y:.2f} [SNAP]")
        else:
            self._pos_label.configure(text=f"X: {wx:.2f}  Y: {wy:.2f}")

        # Aktualizuj zoom label
        zoom_pct = self._canvas.current_zoom_percent
        self._zoom_label.configure(text=f"{zoom_pct:.0f}%")

    def _on_close_window(self):
        """Zamknij okno"""
        if self._modified:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "Do you want to save changes before closing?"
            )
            if result is None:  # Cancel
                return
            elif result:  # Yes
                self._on_save()

        if self._on_close:
            self._on_close()

        self.destroy()


def open_cad_viewer(
    parent=None,
    filepath: str = None,
    part: 'DXFPart' = None,
    on_engrave_change: Callable = None,
    part_index: int = None
) -> CAD2DViewer:
    """
    Otwórz okno CAD Viewer.

    Args:
        parent: Widget rodzica
        filepath: Ścieżka do pliku DXF
        part: DXFPart do wyświetlenia
        on_engrave_change: Callback przy zmianie wyboru warstw grawerowania
                           Signature: on_engrave_change(filepath, engraving_length_mm, selected_layers, part_index)
        part_index: Indeks detalu w liście (dla callback)

    Returns:
        Instancja CAD2DViewer
    """
    viewer = CAD2DViewer(
        parent,
        filepath=filepath,
        part=part,
        on_engrave_change=on_engrave_change,
        part_index=part_index
    )
    return viewer


# Eksporty
__all__ = ['CAD2DViewer', 'open_cad_viewer']
