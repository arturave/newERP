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

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    ctk = tk  # Fallback

from .canvas import CADCanvas
from .tools.dimension import DimensionTool

# Import core.dxf
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from core.dxf import UnifiedDXFReader, DXFPart
except ImportError:
    UnifiedDXFReader = None
    DXFPart = None


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
        **kwargs
    ):
        """
        Args:
            parent: Widget rodzica
            filepath: Ścieżka do pliku DXF do otwarcia
            part: DXFPart do wyświetlenia (alternatywa dla filepath)
            on_close: Callback przy zamknięciu okna
        """
        super().__init__(parent, **kwargs)

        self.title("CAD 2D Viewer")
        self.geometry("1200x800")

        # Stan
        self._part: Optional['DXFPart'] = None
        self._filepath: str = ""
        self._reader = UnifiedDXFReader() if UnifiedDXFReader else None
        self._on_close = on_close
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

        # Info panel (prawa strona)
        self._setup_info_panel()

        # Status bar
        self._setup_statusbar()

        # Bind mouse move dla status bar
        self._canvas.bind("<Motion>", self._on_mouse_move)

    def _setup_toolbar(self):
        """Skonfiguruj toolbar"""
        self._toolbar = ctk.CTkFrame(self._main_frame, height=40) if HAS_CTK else ttk.Frame(self._main_frame)
        self._toolbar.pack(fill=tk.X, padx=5, pady=(5, 0))
        self._toolbar.pack_propagate(False)

        # Przyciski
        btn_style = {"width": 80, "height": 28} if HAS_CTK else {}

        # File section
        if HAS_CTK:
            ctk.CTkButton(self._toolbar, text="Open", command=self._on_open, **btn_style).pack(side=tk.LEFT, padx=2)
            ctk.CTkButton(self._toolbar, text="Save", command=self._on_save, **btn_style).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Button(self._toolbar, text="Open", command=self._on_open).pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="Save", command=self._on_save).pack(side=tk.LEFT, padx=2)

        # Separator
        sep = ttk.Separator(self._toolbar, orient=tk.VERTICAL)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)

        # Zoom section
        if HAS_CTK:
            ctk.CTkButton(self._toolbar, text="Fit", command=self._on_zoom_fit, **btn_style).pack(side=tk.LEFT, padx=2)
            ctk.CTkButton(self._toolbar, text="Zoom +", command=self._on_zoom_in, **btn_style).pack(side=tk.LEFT, padx=2)
            ctk.CTkButton(self._toolbar, text="Zoom -", command=self._on_zoom_out, **btn_style).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Button(self._toolbar, text="Fit", command=self._on_zoom_fit).pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="Zoom +", command=self._on_zoom_in).pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="Zoom -", command=self._on_zoom_out).pack(side=tk.LEFT, padx=2)

        # Separator
        sep2 = ttk.Separator(self._toolbar, orient=tk.VERTICAL)
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)

        # Grid checkbox
        self._grid_var = tk.BooleanVar(value=True)
        if HAS_CTK:
            ctk.CTkCheckBox(
                self._toolbar, text="Grid",
                variable=self._grid_var,
                command=self._on_grid_toggle
            ).pack(side=tk.LEFT, padx=5)
        else:
            ttk.Checkbutton(
                self._toolbar, text="Grid",
                variable=self._grid_var,
                command=self._on_grid_toggle
            ).pack(side=tk.LEFT, padx=5)

        # Separator
        sep3 = ttk.Separator(self._toolbar, orient=tk.VERTICAL)
        sep3.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)

        # Wymiarowanie section
        if HAS_CTK:
            ctk.CTkButton(self._toolbar, text="Auto Dim", command=self._on_auto_dimension, **btn_style).pack(side=tk.LEFT, padx=2)
            ctk.CTkButton(self._toolbar, text="Dimension", command=self._on_dimension_tool, **btn_style).pack(side=tk.LEFT, padx=2)
            ctk.CTkButton(self._toolbar, text="Clear Dim", command=self._on_clear_dimensions, **btn_style).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Button(self._toolbar, text="Auto Dim", command=self._on_auto_dimension).pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="Dimension", command=self._on_dimension_tool).pack(side=tk.LEFT, padx=2)
            ttk.Button(self._toolbar, text="Clear Dim", command=self._on_clear_dimensions).pack(side=tk.LEFT, padx=2)

        # Zoom label (prawa strona)
        self._zoom_label = ctk.CTkLabel(self._toolbar, text="100%") if HAS_CTK else ttk.Label(self._toolbar, text="100%")
        self._zoom_label.pack(side=tk.RIGHT, padx=10)

        zoom_text = ctk.CTkLabel(self._toolbar, text="Zoom:") if HAS_CTK else ttk.Label(self._toolbar, text="Zoom:")
        zoom_text.pack(side=tk.RIGHT)

    def _setup_info_panel(self):
        """Skonfiguruj panel informacyjny"""
        self._info_frame = ctk.CTkFrame(self._center_frame, width=250) if HAS_CTK else ttk.Frame(self._center_frame)
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
            width=30, height=20,
            bg="#2d2d2d" if HAS_CTK else "white",
            fg="white" if HAS_CTK else "black",
            font=("Consolas", 10),
            state=tk.DISABLED
        )
        self._info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Layers section
        layers_label = ctk.CTkLabel(
            self._info_frame, text="Layers",
            font=("Arial", 12, "bold") if HAS_CTK else None
        ) if HAS_CTK else ttk.Label(self._info_frame, text="Layers", font=("Arial", 12, "bold"))
        layers_label.pack(pady=(10, 5))

        self._layers_frame = ctk.CTkScrollableFrame(self._info_frame, height=150) if HAS_CTK else ttk.Frame(self._info_frame)
        self._layers_frame.pack(fill=tk.X, padx=5, pady=5)

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
        self._canvas.set_grid_visible(self._grid_var.get())

    def _on_auto_dimension(self):
        """Automatyczne wymiarowanie (bbox + otwory)"""
        if not self._part:
            messagebox.showwarning("Warning", "No part loaded")
            return

        # Wymiarowanie bbox
        self._dimension_tool.auto_dimension_bbox(self._part)

        # Wymiarowanie otworów (max 5)
        if self._part.holes:
            self._dimension_tool.auto_dimension_holes(self._part, max_holes=5)

        self._modified = True
        messagebox.showinfo("Info", f"Added auto dimensions:\n- BBox (width + height)\n- {min(5, len(self._part.holes))} hole diameters")

    def _on_dimension_tool(self):
        """Aktywuj ręczne wymiarowanie"""
        if not self._part:
            messagebox.showwarning("Warning", "No part loaded")
            return

        # Toggle aktywacji
        if self._dimension_tool._active:
            self._dimension_tool.deactivate()
            messagebox.showinfo("Info", "Dimension tool deactivated")
        else:
            self._dimension_tool.activate(mode="linear")
            messagebox.showinfo("Info", "Dimension tool activated\n\nClick two points to add a dimension.\nPress Escape to cancel.")

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

    def _on_mouse_move(self, event):
        """Aktualizuj pozycję myszy w status bar"""
        wx, wy = self._canvas.screen_to_world(event.x, event.y)
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
    part: 'DXFPart' = None
) -> CAD2DViewer:
    """
    Otwórz okno CAD Viewer.

    Args:
        parent: Widget rodzica
        filepath: Ścieżka do pliku DXF
        part: DXFPart do wyświetlenia

    Returns:
        Instancja CAD2DViewer
    """
    viewer = CAD2DViewer(parent, filepath=filepath, part=part)
    return viewer


# Eksporty
__all__ = ['CAD2DViewer', 'open_cad_viewer']
