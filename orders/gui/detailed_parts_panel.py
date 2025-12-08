"""
Detailed Parts Panel - Panel z szczegolowa lista detali
========================================================
Panel z edytowalna tabela detali, filtrami i automatycznym
przeliczaniem kosztow jednostkowych.

Funkcje:
- Thumbnails detali
- Checkbox "Kalkulowac z materialem" (globalny i per detal)
- Edycja wszystkich pol
- Obsluga modeli 3D (STEP, IGES)
- Reczne dodawanie detali bez plikow
"""

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog, Canvas
from typing import List, Dict, Optional, Callable, Any, Tuple
from pathlib import Path
import logging
import threading
from PIL import Image, ImageTk, ImageDraw
import io

logger = logging.getLogger(__name__)

# Import cost debug logger
try:
    from orders.cost_debug_logger import get_cost_debug_logger
    cost_logger = get_cost_debug_logger()
except ImportError:
    cost_logger = None

# Import cost calculation logger (dla analityka finansowego)
try:
    from orders.cost_calculation_logger import (
        CostCalculationLogger, get_cost_logger, log_calculation_start,
        log_part_cost, save_cost_log, get_cost_report
    )
except ImportError:
    CostCalculationLogger = None
    get_cost_logger = None


class Theme:
    """Paleta kolorow"""
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


# ============================================================
# Thumbnail Generator
# ============================================================

class ThumbnailGenerator:
    """Generator miniaturek dla detali"""

    def __init__(self, size: Tuple[int, int] = (60, 40)):
        self.size = size
        self.cache: Dict[str, ImageTk.PhotoImage] = {}

    def generate_from_contour(self, contour: List, color: str = "#8b5cf6") -> ImageTk.PhotoImage:
        """Generuj miniaturke z konturu"""
        if not contour or len(contour) < 3:
            return self._generate_placeholder()

        try:
            # Znajdz bounding box
            xs = [p[0] for p in contour]
            ys = [p[1] for p in contour]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)

            width = max_x - min_x
            height = max_y - min_y

            if width <= 0 or height <= 0:
                return self._generate_placeholder()

            # Skaluj do rozmiaru miniaturki
            scale_x = (self.size[0] - 4) / width
            scale_y = (self.size[1] - 4) / height
            scale = min(scale_x, scale_y)

            # Stworz obraz
            img = Image.new('RGBA', self.size, (26, 26, 26, 255))
            draw = ImageDraw.Draw(img)

            # Przeksztalc punkty
            offset_x = (self.size[0] - width * scale) / 2
            offset_y = (self.size[1] - height * scale) / 2

            points = []
            for x, y in contour:
                px = offset_x + (x - min_x) * scale
                py = offset_y + (y - min_y) * scale
                points.append((int(px), int(py)))

            # Rysuj polygon
            if len(points) >= 3:
                # Konwersja koloru hex na RGB
                rgb = tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                draw.polygon(points, fill=rgb + (200,), outline=(255, 255, 255, 255))

            return ImageTk.PhotoImage(img)

        except Exception as e:
            logger.warning(f"Error generating thumbnail: {e}")
            return self._generate_placeholder()

    def _generate_placeholder(self) -> ImageTk.PhotoImage:
        """Generuj placeholder"""
        img = Image.new('RGBA', self.size, (42, 42, 42, 255))
        draw = ImageDraw.Draw(img)
        # Prosty prostokat
        draw.rectangle([2, 2, self.size[0]-3, self.size[1]-3],
                       outline=(100, 100, 100, 255), width=1)
        draw.line([2, 2, self.size[0]-3, self.size[1]-3], fill=(100, 100, 100, 255))
        draw.line([self.size[0]-3, 2, 2, self.size[1]-3], fill=(100, 100, 100, 255))
        return ImageTk.PhotoImage(img)


# ============================================================
# 3D Model Loader
# ============================================================

class Model3DLoader:
    """Loader dla modeli 3D (STEP, IGES)"""

    SUPPORTED_EXTENSIONS = ['.step', '.stp', '.iges', '.igs']

    @staticmethod
    def can_load(filepath: str) -> bool:
        """Sprawdz czy plik jest obslugiwany"""
        ext = Path(filepath).suffix.lower()
        return ext in Model3DLoader.SUPPORTED_EXTENSIONS

    @staticmethod
    def load_model_data(filepath: str) -> Optional[Dict]:
        """
        Wczytaj dane z modelu 3D

        Returns:
            Dict z: weight_kg, bends_count, thickness_mm, width, height, thumbnail_bytes
        """
        try:
            # Proba uzycia OCC (OpenCASCADE)
            try:
                from OCC.Core.STEPControl import STEPControl_Reader
                from OCC.Core.IFSelect import IFSelect_RetDone
                from OCC.Core.BRepGProp import brepgprop_VolumeProperties
                from OCC.Core.GProp import GProp_GProps

                reader = STEPControl_Reader()
                status = reader.ReadFile(filepath)

                if status == IFSelect_RetDone:
                    reader.TransferRoots()
                    shape = reader.OneShape()

                    # Oblicz objetosc
                    props = GProp_GProps()
                    brepgprop_VolumeProperties(shape, props)
                    volume_mm3 = props.Mass()  # w mm3

                    # Zaloz gestosc stali 7850 kg/m3
                    density = 7850  # kg/m3
                    volume_m3 = volume_mm3 / 1e9
                    weight_kg = volume_m3 * density

                    # Bounding box
                    from OCC.Core.Bnd import Bnd_Box
                    from OCC.Core.BRepBndLib import brepbndlib_Add
                    bbox = Bnd_Box()
                    brepbndlib_Add(shape, bbox)
                    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

                    return {
                        'weight_kg': round(weight_kg, 3),
                        'bends_count': 0,  # Trudne do wykrycia automatycznie
                        'thickness_mm': round(zmax - zmin, 2),
                        'width': round(xmax - xmin, 2),
                        'height': round(ymax - ymin, 2),
                        'contour': [],  # Projekcja 2D wymaga wiecej pracy
                        'source': '3D_model'
                    }

            except ImportError:
                logger.warning("OCC not available, using fallback 3D parser")

            # Fallback - podstawowe parsowanie
            return Model3DLoader._parse_basic(filepath)

        except Exception as e:
            logger.error(f"Error loading 3D model {filepath}: {e}")
            return None

    @staticmethod
    def _parse_basic(filepath: str) -> Optional[Dict]:
        """Podstawowe parsowanie pliku STEP/IGES"""
        try:
            file_size = Path(filepath).stat().st_size

            # Heurystyka - wieksza czesc = wiekszy detal
            estimated_weight = file_size / 50000  # Bardzo przyblizone

            return {
                'weight_kg': round(estimated_weight, 3),
                'bends_count': 0,
                'thickness_mm': 0,
                'width': 0,
                'height': 0,
                'contour': [],
                'source': '3D_model_estimated',
                'note': 'Dane szacunkowe - brak biblioteki OCC'
            }

        except Exception as e:
            logger.error(f"Basic parse error: {e}")
            return None


# ============================================================
# Editable Treeview with Thumbnails
# ============================================================

class EnhancedTreeview(ttk.Treeview):
    """Treeview z miniaturkami i edytowalnymi komorkami"""

    def __init__(self, parent, columns: List[str], editable_columns: List[str] = None,
                 on_edit: Callable = None, **kwargs):
        # Pierwsza kolumna to miniaturka (tree column)
        super().__init__(parent, columns=columns, show="tree headings", **kwargs)

        self.editable_columns = editable_columns or []
        self.on_edit = on_edit
        self.entry_popup = None
        self.thumbnails: Dict[str, ImageTk.PhotoImage] = {}
        self.thumbnail_generator = ThumbnailGenerator()

        # Kolumna na miniaturki
        self.column("#0", width=70, anchor='center')
        self.heading("#0", text="")

        # Bind double-click for editing
        self.bind("<Double-1>", self._on_double_click)
        self.bind("<Escape>", self._close_entry)

    def insert_with_thumbnail(self, parent: str, index: str, iid: str,
                              values: tuple, contour: List = None,
                              color: str = "#8b5cf6", tags: tuple = None):
        """Wstaw wiersz z miniaturka"""
        # Generuj miniaturke
        if contour and len(contour) >= 3:
            thumb = self.thumbnail_generator.generate_from_contour(contour, color)
        else:
            thumb = self.thumbnail_generator._generate_placeholder()

        self.thumbnails[iid] = thumb

        # Wstaw wiersz
        self.insert(parent, index, iid=iid, values=values, image=thumb, tags=tags)

    def _on_double_click(self, event):
        """Obsluz podwojne klikniecie - rozpocznij edycje"""
        region = self.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self.identify_column(event.x)
        if column == "#0":  # Miniaturka - nie edytowalna
            return

        col_index = int(column.replace('#', '')) - 1
        if col_index < 0 or col_index >= len(self['columns']):
            return

        col_name = self['columns'][col_index]

        if col_name not in self.editable_columns:
            return

        item = self.identify_row(event.y)
        if not item:
            return

        self._create_entry(item, column, col_name)

    def _create_entry(self, item: str, column: str, col_name: str):
        """Stworz pole edycji"""
        self._close_entry()

        x, y, width, height = self.bbox(item, column)
        current_value = self.set(item, col_name)

        self.entry_popup = ctk.CTkEntry(
            self, width=width, height=height,
            fg_color=Theme.BG_INPUT, text_color=Theme.TEXT_PRIMARY,
            border_width=1, border_color=Theme.ACCENT_PRIMARY
        )
        self.entry_popup.place(x=x, y=y)
        self.entry_popup.insert(0, current_value)
        self.entry_popup.select_range(0, 'end')
        self.entry_popup.focus_set()

        self.entry_popup._item = item
        self.entry_popup._column = col_name

        self.entry_popup.bind("<Return>", self._save_entry)
        self.entry_popup.bind("<Tab>", self._save_and_next)
        self.entry_popup.bind("<Escape>", self._close_entry)
        self.entry_popup.bind("<FocusOut>", self._save_entry)

    def _save_entry(self, event=None):
        """Zapisz wartosc z entry"""
        if not self.entry_popup:
            return

        item = self.entry_popup._item
        column = self.entry_popup._column
        new_value = self.entry_popup.get()

        self.set(item, column, new_value)

        if self.on_edit:
            self.on_edit(item, column, new_value)

        self._close_entry()

    def _save_and_next(self, event=None):
        """Zapisz i przejdz do nastepnej komorki"""
        self._save_entry()
        return "break"

    def _close_entry(self, event=None):
        """Zamknij entry bez zapisu"""
        if self.entry_popup:
            self.entry_popup.destroy()
            self.entry_popup = None


# ============================================================
# Allocation Help Dialog
# ============================================================

class AllocationHelpDialog(ctk.CTkToplevel):
    """Dialog z opisem modeli alokacji kosztów"""

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Model Alokacji Kosztów - Pomoc")
        self.geometry("700x600")
        self.configure(fg_color=Theme.BG_DARK)

        # Wyśrodkuj
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 700) // 2
        y = (self.winfo_screenheight() - 600) // 2
        self.geometry(f"+{x}+{y}")

        self._setup_ui()

        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _setup_ui(self):
        """Buduj interfejs"""
        # Header
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50)
        header.pack(fill="x", padx=10, pady=10)
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="Model Alokacji Kosztów",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color=Theme.ACCENT_INFO).pack(side="left", padx=15, pady=10)

        # Content - scrollable
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=5)

        # === PROPORCJONALNY ===
        self._add_model_section(
            content,
            title="1. Proporcjonalny",
            color=Theme.ACCENT_SUCCESS,
            description="""Koszty arkusza (materiał, cięcie, obsługa) są rozdzielane
proporcjonalnie do powierzchni każdego detalu.

Wzór: Koszt_detalu = Koszt_arkusza × (Powierzchnia_detalu / Powierzchnia_wszystkich)

Przykład:
• Arkusz 1000×2000mm, koszt 500 PLN
• Detal A: 200×300mm = 0.06m² (30% powierzchni) → 150 PLN
• Detal B: 400×350mm = 0.14m² (70% powierzchni) → 350 PLN

Zalety: Sprawiedliwy podział, większe detale = większy koszt
Zastosowanie: Standardowa produkcja, wyceny dla klientów""",
            graphic_type="proportional"
        )

        # === PROSTOKĄT OTACZAJĄCY ===
        self._add_model_section(
            content,
            title="2. Prostokąt otaczający",
            color=Theme.ACCENT_WARNING,
            description="""Koszty arkusza są dzielone równo między wszystkie detale
bez względu na ich rozmiar.

Wzór: Koszt_detalu = Koszt_arkusza / Liczba_detali

Przykład:
• Arkusz 1000×2000mm, koszt 500 PLN
• 10 detali na arkuszu → każdy detal: 50 PLN

Zalety: Prosty w obliczeniach, przewidywalny koszt jednostkowy
Zastosowanie: Produkcja seryjna identycznych części""",
            graphic_type="unit"
        )

        # === NA ARKUSZ ===
        self._add_model_section(
            content,
            title="3. Na arkusz",
            color=Theme.ACCENT_DANGER,
            description="""Każdy detal ponosi pełny koszt arkusza z którego jest wycinany.
Używane gdy detal zajmuje większość arkusza lub przy pojedynczych sztukach.

Wzór: Koszt_detalu = Koszt_arkusza (pełny)

Przykład:
• Arkusz 1000×2000mm, koszt 500 PLN
• Jeden duży detal 900×1900mm → 500 PLN
• Odpad nie jest uwzględniany w wycenie

Zalety: Bezpieczna wycena, pokrywa ryzyko odpadu
Zastosowanie: Prototypy, duże pojedyncze detale, niski nesting""",
            graphic_type="sheet"
        )

        # Close button
        btn_close = ctk.CTkButton(
            self, text="Zamknij", width=100,
            fg_color=Theme.ACCENT_PRIMARY,
            command=self.destroy
        )
        btn_close.pack(pady=15)

    def _add_model_section(self, parent, title: str, color: str,
                          description: str, graphic_type: str):
        """Dodaj sekcję z opisem modelu"""
        frame = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD, corner_radius=8)
        frame.pack(fill="x", pady=8, padx=5)

        # Title
        title_frame = ctk.CTkFrame(frame, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(title_frame, text=title,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=color).pack(side="left")

        # Content row: graphic + description
        content_row = ctk.CTkFrame(frame, fg_color="transparent")
        content_row.pack(fill="x", padx=15, pady=(5, 15))

        # Graphic canvas
        canvas_frame = ctk.CTkFrame(content_row, fg_color=Theme.BG_INPUT,
                                    width=180, height=120, corner_radius=4)
        canvas_frame.pack(side="left", padx=(0, 15))
        canvas_frame.pack_propagate(False)

        canvas = Canvas(canvas_frame, width=170, height=110,
                       bg=Theme.BG_INPUT, highlightthickness=0)
        canvas.pack(padx=5, pady=5)

        self._draw_allocation_graphic(canvas, graphic_type, color)

        # Description
        desc_label = ctk.CTkLabel(
            content_row, text=description,
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY,
            justify="left", anchor="nw",
            wraplength=450
        )
        desc_label.pack(side="left", fill="both", expand=True)

    def _draw_allocation_graphic(self, canvas: Canvas, graphic_type: str, color: str):
        """Rysuj grafikę ilustrującą model alokacji"""
        w, h = 170, 110

        # Tło arkusza
        canvas.create_rectangle(10, 10, w-10, h-10, fill="#2a2a2a", outline="#444")

        if graphic_type == "proportional":
            # Proporcjonalny - różne rozmiary, różne kolory intensywności
            canvas.create_rectangle(15, 15, 70, 55, fill="#22c55e", outline="#fff")
            canvas.create_text(42, 35, text="30%", fill="#fff", font=("Arial", 8, "bold"))

            canvas.create_rectangle(75, 15, 155, 100, fill="#166534", outline="#fff")
            canvas.create_text(115, 57, text="70%", fill="#fff", font=("Arial", 10, "bold"))

            canvas.create_rectangle(15, 60, 70, 100, fill="#444", outline="#666")
            canvas.create_text(42, 80, text="odpad", fill="#666", font=("Arial", 7))

        elif graphic_type == "unit":
            # Prostokąt otaczający - równe części
            colors = ["#f59e0b", "#fbbf24", "#fcd34d", "#fef3c7"]
            positions = [(15, 15, 80, 50), (85, 15, 155, 50),
                        (15, 55, 80, 100), (85, 55, 155, 100)]
            for i, (x1, y1, x2, y2) in enumerate(positions):
                canvas.create_rectangle(x1, y1, x2, y2, fill=colors[i % len(colors)], outline="#fff")
                canvas.create_text((x1+x2)//2, (y1+y2)//2, text="25%", fill="#000", font=("Arial", 8, "bold"))

        elif graphic_type == "sheet":
            # Na arkusz - jeden duży detal
            canvas.create_rectangle(15, 15, 150, 95, fill="#ef4444", outline="#fff", width=2)
            canvas.create_text(82, 55, text="100%", fill="#fff", font=("Arial", 12, "bold"))

            # Mały odpad
            canvas.create_rectangle(152, 15, 160, 95, fill="#444", outline="#666")
            canvas.create_rectangle(15, 97, 160, 105, fill="#444", outline="#666")


# ============================================================
# Main Panel
# ============================================================

class DetailedPartsPanel(ctk.CTkFrame):
    """Panel z szczegolowa lista detali i kosztami jednostkowymi"""

    # Definicja kolumn (bez thumbnail - to jest #0)
    # Usunięto kolumnę Mat (zawsze '+'), przesunięto Bends w prawo
    COLUMNS = [
        ("nr", "Nr", 35),
        ("name", "Name", 160),
        ("material", "Material", 70),
        ("thickness", "Thick", 50),
        ("quantity", "Qty", 40),
        ("lm_cost", "L+M", 65),
        ("bends", "Bends", 45),
        ("bending_cost", "Bend$", 55),
        ("additional", "Add$", 50),
        ("weight", "Weight", 55),
        ("cutting_len", "Cut len", 65),
        ("total_unit", "Total/pc", 70),
    ]

    EDITABLE = ["name", "material", "thickness", "quantity",
                "lm_cost", "bends", "bending_cost", "additional", "weight", "cutting_len"]

    # Kolory dla detali (cykliczne)
    PART_COLORS = [
        "#8b5cf6", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4",
        "#ec4899", "#84cc16", "#f97316", "#6366f1", "#14b8a6"
    ]

    def __init__(self, parent, on_parts_change: Callable = None,
                 cost_service=None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=8, **kwargs)

        self.on_parts_change = on_parts_change
        self.cost_service = cost_service
        self.parts_data: List[Dict] = []
        self.filter_var = ctk.StringVar()
        self.next_nr = 1

        # Globalne ustawienia
        self.calc_with_material_var = ctk.BooleanVar(value=True)

        # Flaga: czy nesting zostal wykonany (alokacja dostepna dopiero po nestingu)
        self._nesting_completed = False

        # Załaduj cenniki z PricingTables
        self.pricing_tables = None
        self._load_pricing_tables()

        self._setup_ui()

    def _load_pricing_tables(self):
        """Załaduj cenniki z modułu pricing"""
        try:
            from quotations.pricing.pricing_tables import get_pricing_tables
            self.pricing_tables = get_pricing_tables()
            logger.info("[DetailedParts] Pricing tables loaded successfully")
        except Exception as e:
            logger.warning(f"[DetailedParts] Could not load pricing tables: {e}")
            self.pricing_tables = None

    def _setup_ui(self):
        """Buduj interfejs"""
        # === HEADER ===
        header = ctk.CTkFrame(self, fg_color="transparent", height=35)
        header.pack(fill="x", padx=10, pady=(8, 3))

        title = ctk.CTkLabel(
            header, text="LISTA POZYCJI ZAMOWIENIA",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        )
        title.pack(side="left")

        # Model Alokacji z helpem
        alloc_frame = ctk.CTkFrame(header, fg_color="transparent")
        alloc_frame.pack(side="right", padx=5)

        self.alloc_label = ctk.CTkLabel(alloc_frame, text="Model Alokacji:",
                     font=ctk.CTkFont(size=10), text_color=Theme.TEXT_MUTED
                     )
        self.alloc_label.pack(side="left", padx=(0, 3))

        self.allocation_model_var = ctk.StringVar(value="Proporcjonalny")
        self.allocation_combo = ctk.CTkComboBox(
            alloc_frame,
            values=["Proporcjonalny", "Prostokąt otaczający", "Na arkusz"],
            variable=self.allocation_model_var,
            command=self._on_allocation_change,
            width=120, height=24,
            font=ctk.CTkFont(size=10),
            state="disabled"  # Domyslnie wylaczony - aktywny dopiero po nestingu
        )
        self.allocation_combo.pack(side="left", padx=2)

        # Etykieta informujaca o koniecznosci nestingu
        self.alloc_info_label = ctk.CTkLabel(
            alloc_frame, text="(wymaga nestingu)",
            font=ctk.CTkFont(size=9), text_color=Theme.TEXT_MUTED
        )
        self.alloc_info_label.pack(side="left", padx=(3, 0))

        btn_help = ctk.CTkButton(
            alloc_frame, text="?", width=24, height=24,
            fg_color=Theme.ACCENT_INFO, hover_color="#0599b8",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._show_allocation_help
        )
        btn_help.pack(side="left", padx=2)

        # === FILTER BAR ===
        filter_frame = ctk.CTkFrame(self, fg_color="transparent", height=30)
        filter_frame.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(filter_frame, text="Filter:", text_color=Theme.TEXT_MUTED,
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 3))

        self.filter_entry = ctk.CTkEntry(
            filter_frame, width=120, height=24, fg_color=Theme.BG_INPUT,
            textvariable=self.filter_var, font=ctk.CTkFont(size=10)
        )
        self.filter_entry.pack(side="left", padx=3)
        self.filter_entry.bind("<KeyRelease>", self._apply_filter)

        self.filter_combo = ctk.CTkComboBox(
            filter_frame, values=["All", "Material", "Thickness", "Name"],
            width=80, height=24, fg_color=Theme.BG_INPUT, font=ctk.CTkFont(size=10)
        )
        self.filter_combo.set("All")
        self.filter_combo.pack(side="left", padx=3)

        # Spacer
        ctk.CTkLabel(filter_frame, text="").pack(side="left", expand=True)

        # === ACTION BUTTONS ===
        btn_add = ctk.CTkButton(
            filter_frame, text="+ Dodaj", width=60, height=24,
            fg_color=Theme.ACCENT_SUCCESS, hover_color="#1a9f4a",
            font=ctk.CTkFont(size=10), command=self._add_part
        )
        btn_add.pack(side="left", padx=2)

        btn_add_3d = ctk.CTkButton(
            filter_frame, text="+ 3D", width=45, height=24,
            fg_color=Theme.ACCENT_INFO, hover_color="#0599b8",
            font=ctk.CTkFont(size=10), command=self._add_3d_model
        )
        btn_add_3d.pack(side="left", padx=2)

        btn_from_catalog = ctk.CTkButton(
            filter_frame, text="Z katalogu", width=70, height=24,
            fg_color="#6366f1", hover_color="#5855e0",
            font=ctk.CTkFont(size=10), command=self._open_catalog_picker
        )
        btn_from_catalog.pack(side="left", padx=2)

        btn_duplicate = ctk.CTkButton(
            filter_frame, text="Dup", width=40, height=24,
            fg_color=Theme.ACCENT_PRIMARY, hover_color="#7c4fe0",
            font=ctk.CTkFont(size=10), command=self._duplicate_part
        )
        btn_duplicate.pack(side="left", padx=2)

        btn_delete = ctk.CTkButton(
            filter_frame, text="Usun", width=45, height=24,
            fg_color=Theme.ACCENT_DANGER, hover_color="#d93636",
            font=ctk.CTkFont(size=10), command=self._delete_part
        )
        btn_delete.pack(side="left", padx=2)

        btn_recalc = ctk.CTkButton(
            filter_frame, text="Przelicz", width=60, height=24,
            fg_color=Theme.ACCENT_WARNING, hover_color="#db8f0a",
            font=ctk.CTkFont(size=10), command=self._recalculate_all
        )
        btn_recalc.pack(side="left", padx=2)

        # Przycisk do otwierania okna logu kosztow
        btn_debug_log = ctk.CTkButton(
            filter_frame, text="Log", width=40, height=24,
            fg_color="#4a4a4a", hover_color="#5a5a5a",
            font=ctk.CTkFont(size=10), command=self._open_debug_log
        )
        btn_debug_log.pack(side="left", padx=2)

        # === TREEVIEW TABLE ===
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=10, pady=(3, 5))

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "DetailedParts.Treeview",
            background=Theme.BG_DARK,
            foreground=Theme.TEXT_PRIMARY,
            fieldbackground=Theme.BG_DARK,
            rowheight=45,
            font=('Segoe UI', 9)
        )
        style.configure(
            "DetailedParts.Treeview.Heading",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_PRIMARY,
            font=('Segoe UI', 9, 'bold')
        )
        style.map("DetailedParts.Treeview",
                  background=[("selected", Theme.ACCENT_PRIMARY)],
                  foreground=[("selected", Theme.TEXT_PRIMARY)])

        # Treeview
        columns = [c[0] for c in self.COLUMNS]
        self.tree = EnhancedTreeview(
            table_frame, columns=columns, editable_columns=self.EDITABLE,
            on_edit=self._on_cell_edit, style="DetailedParts.Treeview", height=6
        )

        # Konfiguracja kolumn
        for col_id, col_name, col_width in self.COLUMNS:
            self.tree.heading(col_id, text=col_name, anchor="center")
            self.tree.column(col_id, width=col_width, anchor="center", minwidth=30)

        # Tagi
        self.tree.tag_configure('with_material', background='#1a2a1a')
        self.tree.tag_configure('without_material', background='#2a1a1a')

        # Scrollbars
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        # === SUMMARY BAR ===
        summary_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, height=25)
        summary_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.lbl_summary = ctk.CTkLabel(
            summary_frame,
            text="Pozycji: 0 | Suma qty: 0 | L+M: 0.00 | Total: 0.00 PLN",
            font=ctk.CTkFont(size=10), text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_summary.pack(pady=4)

    def _on_allocation_change(self, value: str):
        """Zmiana modelu alokacji kosztów"""
        logger.info(f"[DetailedParts] Allocation model changed to: {value}")
        self._recalculate_all()

    def _show_allocation_help(self):
        """Pokaż okno pomocy z opisem modeli alokacji"""
        AllocationHelpDialog(self.winfo_toplevel())

    def _generate_cost_report(self) -> str:
        """Generuj szczegółowy raport z ostatnich obliczeń kosztów"""
        from datetime import datetime

        if not self.parts_data:
            return "Brak detali do wyświetlenia."

        allocation_model = self.allocation_model_var.get()

        lines = [
            "=" * 65,
            "RAPORT KALKULACJI KOSZTÓW",
            f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "METODA OBLICZANIA KOSZTU MATERIAŁU:",
            "  Waga = Powierzchnia brutto DXF × Grubość × Gęstość × 1.35",
            f"  Naddatek na wykorzystanie arkusza: +{(self.SHEET_UTILIZATION_FACTOR-1)*100:.0f}%",
            "",
            f"Model alokacji kosztów arkusza: {allocation_model}",
            "=" * 65,
            ""
        ]

        for part in self.parts_data:
            nr = part.get('nr', '?')
            name = part.get('name', 'Bez nazwy')
            material = part.get('material', '?')
            thickness = part.get('thickness', 0)
            qty = part.get('quantity', 1)

            # Pobierz dane o powierzchni i wadze
            area_gross = part.get('_area_gross_mm2', part.get('area_gross_mm2', 0))
            area_with_factor = part.get('_area_with_factor_mm2', area_gross * self.SHEET_UTILIZATION_FACTOR if area_gross else 0)
            weight_kg = part.get('weight', part.get('weight_kg', 0))

            lines.extend([
                f"[{nr}] {name}",
                f"    Materiał: {material} {thickness}mm × {qty}szt",
                f"    Powierzchnia brutto: {area_gross:.0f} mm² (× {self.SHEET_UTILIZATION_FACTOR:.0%} = {area_with_factor:.0f} mm²)",
                f"    Waga (z naddatkiem 35%): {weight_kg:.3f} kg",
                "",
                "    SKŁADNIKI KOSZTOWE:",
                f"      Materiał:   {part.get('material_cost', 0):>10.2f} PLN  {part.get('_material_formula', '')}",
                f"      Cięcie:     {part.get('cutting_cost', 0):>10.2f} PLN  ({part.get('cutting_len', 0)/1000:.3f}m × PLN/m)",
                f"      Grawer:     {part.get('engraving_cost', 0):>10.2f} PLN  ({part.get('engraving_len', 0)/1000:.3f}m)",
                f"      Folia:      {part.get('foil_cost', 0):>10.2f} PLN  {part.get('_foil_formula', '')}",
                f"      Piercing:   {part.get('piercing_cost', 0):>10.2f} PLN  {part.get('_piercing_formula', '')}",
                f"      ─────────────────────────────────",
                f"      L+M:        {part.get('lm_cost', 0):>10.2f} PLN",
                "",
                f"      Gięcie:     {part.get('bending_cost', 0):>10.2f} PLN  ({part.get('bends', 0)} gięć × {self.BEND_PRICE:.2f})",
                f"      Dodatkowe:  {part.get('additional', 0):>10.2f} PLN",
                f"      ═════════════════════════════════",
                f"      TOTAL/szt:  {part.get('total_unit', 0):>10.2f} PLN",
                f"      TOTAL×{qty}:   {part.get('total_unit', 0) * qty:>10.2f} PLN",
                ""
            ])

        # Podsumowanie
        total_material = sum(float(p.get('material_cost', 0) or 0) for p in self.parts_data)
        total_cutting = sum(float(p.get('cutting_cost', 0) or 0) for p in self.parts_data)
        total_engraving = sum(float(p.get('engraving_cost', 0) or 0) for p in self.parts_data)
        total_foil = sum(float(p.get('foil_cost', 0) or 0) for p in self.parts_data)
        total_piercing = sum(float(p.get('piercing_cost', 0) or 0) for p in self.parts_data)
        total_lm = sum(float(p.get('lm_cost', 0) or 0) for p in self.parts_data)
        total_bending = sum(float(p.get('bending_cost', 0) or 0) for p in self.parts_data)
        total_all = sum(float(p.get('total_unit', 0) or 0) * int(p.get('quantity', 1) or 1) for p in self.parts_data)

        # Sumy długości
        total_cutting_m = sum(float(p.get('cutting_len', 0) or 0) * int(p.get('quantity', 1) or 1) for p in self.parts_data) / 1000
        total_engraving_m = sum(float(p.get('engraving_len', 0) or 0) * int(p.get('quantity', 1) or 1) for p in self.parts_data) / 1000

        lines.extend([
            "-" * 65,
            "PODSUMOWANIE (sumy jednostkowe)",
            "-" * 65,
            f"  Materiał:         {total_material:>12.2f} PLN",
            f"  Cięcie:           {total_cutting:>12.2f} PLN  ({total_cutting_m:.2f} m)",
            f"  Grawer:           {total_engraving:>12.2f} PLN  ({total_engraving_m:.2f} m)",
            f"  Folia:            {total_foil:>12.2f} PLN",
            f"  Piercing:         {total_piercing:>12.2f} PLN",
            f"  L+M razem:        {total_lm:>12.2f} PLN",
            f"  Gięcie:           {total_bending:>12.2f} PLN",
            "",
            "=" * 65,
            f"  SUMA (z ilościami): {total_all:>12.2f} PLN",
            "=" * 65,
            "",
            "UWAGI:",
            "  - Powierzchnia brutto = największa zamknięta LWPOLYLINE z DXF",
            "  - Koszty cięcia, graweru, folii, piercingu są STAŁE (zależą od geometrii detalu)",
            f"  - Model alokacji ({allocation_model}) wpływa na podział kosztu arkusza",
        ])

        return "\n".join(lines)

    def _open_debug_log(self):
        """Otwórz okno z raportem kalkulacji kosztów"""
        # Wygeneruj raport jeśli nie ma
        if not hasattr(self, '_last_cost_report') or not self._last_cost_report:
            self._last_cost_report = self._generate_cost_report()

        report = self._last_cost_report

        # Zapisz do pliku
        filepath = self._save_cost_report_to_file(report)

        # Pokaż okno z raportem
        self._show_cost_report_window(report, filepath)

    def _save_cost_report_to_file(self, report: str) -> str:
        """Zapisz raport do pliku w logs/costs/"""
        import os
        from datetime import datetime

        log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'costs')
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        order_name = getattr(self, 'order_name', 'unknown')
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in str(order_name))
        filename = f"cost_report_{timestamp}_{safe_name}.log"
        filepath = os.path.join(log_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"[DetailedParts] Zapisano raport do: {filepath}")
        except Exception as e:
            logger.error(f"[DetailedParts] Błąd zapisu raportu: {e}")
            filepath = ""

        return filepath

    def _show_cost_report_window(self, report: str, filepath: str):
        """Pokaż okno z raportem kosztów"""
        window = ctk.CTkToplevel(self)
        window.title("Raport kalkulacji kosztów")
        window.geometry("750x650")
        window.transient(self.winfo_toplevel())

        # Textbox z raportem
        textbox = ctk.CTkTextbox(
            window,
            font=("Consolas", 11),
            fg_color=Theme.BG_CARD,
            text_color=Theme.TEXT_PRIMARY,
            wrap="none"
        )
        textbox.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        textbox.insert("1.0", report)
        textbox.configure(state="disabled")

        # Footer z info o pliku
        footer_frame = ctk.CTkFrame(window, fg_color="transparent")
        footer_frame.pack(fill="x", padx=10, pady=(0, 10))

        if filepath:
            ctk.CTkLabel(
                footer_frame,
                text=f"Zapisano: {filepath}",
                font=ctk.CTkFont(size=10),
                text_color=Theme.TEXT_MUTED
            ).pack(side="left")

        ctk.CTkButton(
            footer_frame,
            text="Zamknij",
            command=window.destroy,
            width=80
        ).pack(side="right")

    def enable_allocation_model(self):
        """Włącz dropdown alokacji po wykonaniu nestingu"""
        self._nesting_completed = True
        self.allocation_combo.configure(state="normal")
        self.alloc_label.configure(text_color=Theme.TEXT_SECONDARY)
        self.alloc_info_label.configure(text="")  # Ukryj info
        logger.info("[DetailedParts] Allocation model enabled (nesting completed)")

    def disable_allocation_model(self):
        """Wyłącz dropdown alokacji (reset do stanu przed nestingiem)"""
        self._nesting_completed = False
        self.allocation_combo.configure(state="disabled")
        self.allocation_model_var.set("Proporcjonalny")  # Reset do domyslnego
        self.alloc_label.configure(text_color=Theme.TEXT_MUTED)
        self.alloc_info_label.configure(text="(wymaga nestingu)")
        logger.info("[DetailedParts] Allocation model disabled (reset)")

    def _on_cell_edit(self, item: str, column: str, new_value: str):
        """Obsluz edycje komorki"""
        idx = self._find_part_index(item)
        if idx is None:
            return

        # Walidacja i konwersja
        try:
            if column in ["quantity", "bends"]:
                self.parts_data[idx][column] = int(new_value)
                # Jeśli zmieniono ilość gięć, zresetuj flagę manualnego kosztu gięć
                if column == "bends":
                    self.parts_data[idx]['_manual_bending_cost'] = False
            elif column in ["thickness", "lm_cost", "bending_cost", "additional",
                            "weight", "cutting_len"]:
                self.parts_data[idx][column] = float(new_value.replace(",", "."))
                # Oznacz ręcznie edytowane koszty
                if column == "lm_cost":
                    self.parts_data[idx]['_manual_lm_cost'] = True
                elif column == "bending_cost":
                    self.parts_data[idx]['_manual_bending_cost'] = True
            elif column == "calc_mat":
                # Toggle material calculation
                self.parts_data[idx]['calc_with_material'] = new_value.lower() in ['1', 'true', 'yes', 'tak']
            else:
                self.parts_data[idx][column] = new_value
        except ValueError:
            logger.warning(f"Invalid value for {column}: {new_value}")
            return

        # Aktualizuj tylko total bez nadpisywania ręcznych wartości
        self._update_total_only(idx)
        self._update_row(idx)
        self._update_summary()

    def _find_part_index(self, item_id: str) -> Optional[int]:
        """Znajdz indeks czesci po ID wiersza"""
        try:
            for i, part in enumerate(self.parts_data):
                if part.get('_item_id') == item_id:
                    return i
            values = self.tree.item(item_id, 'values')
            nr = int(values[0])
            for i, part in enumerate(self.parts_data):
                if part.get('nr') == nr:
                    return i
        except:
            pass
        return None

    # Cena za jedno gięcie [PLN]
    BEND_PRICE = 3.0

    def _update_total_only(self, idx: int):
        """Aktualizuj tylko total_unit bez nadpisywania ręcznych wartości L+M i Bend$"""
        part = self.parts_data[idx]
        lm_cost = float(part.get('lm_cost', 0) or 0)
        bending_cost = float(part.get('bending_cost', 0) or 0)
        additional = float(part.get('additional', 0) or 0)
        part['total_unit'] = lm_cost + bending_cost + additional

    def _recalculate_part(self, idx: int):
        """Przelicz koszty dla detalu - wywołuje pełne przeliczenie z alokacją"""
        # Przy edycji pojedynczego detalu przeliczamy wszystkie,
        # bo modele alokacji (Prostokąt otaczający, Na arkusz) zależą od wszystkich detali
        self._recalculate_all()

    def _recalculate_all(self):
        """Przelicz wszystkie detale z uwzględnieniem modelu alokacji"""
        if not self.parts_data:
            self._update_summary()
            return

        allocation_model = self.allocation_model_var.get()
        logger.info(f"[DetailedParts] Przeliczanie z modelem: {allocation_model}")

        # Rozpocznij logowanie dla analityka finansowego
        if get_cost_logger is not None:
            order_name = getattr(self, 'order_name', 'unknown')
            log_calculation_start(allocation_model, order_name)

        # Krok 1: Oblicz koszty bazowe (proporcjonalne) dla wszystkich detali
        for idx in range(len(self.parts_data)):
            self._recalculate_part_base(idx)

        # Krok 2: Zastosuj model alokacji
        if allocation_model == "Prostokąt otaczający":
            self._apply_unit_allocation()
        elif allocation_model == "Na arkusz":
            self._apply_per_sheet_allocation()
        # Proporcjonalny - koszty bazowe są już poprawne

        # Krok 3: Aktualizuj wiersze w tabeli
        for idx in range(len(self.parts_data)):
            self._update_row(idx)

        # Krok 4: Loguj koszty dla analityka finansowego
        if get_cost_logger is not None:
            for part in self.parts_data:
                log_part_cost(part)
            # Zapisz log do pliku
            try:
                log_filepath = save_cost_log()
                logger.info(f"[DetailedParts] Zapisano log kosztów do: {log_filepath}")
            except Exception as e:
                logger.error(f"[DetailedParts] Błąd zapisu logu kosztów: {e}")

        self._update_summary()

        # Krok 5: Generuj raport kosztów (do wyświetlenia w oknie debug)
        self._last_cost_report = self._generate_cost_report()

    def _recalculate_part_base(self, idx: int):
        """Oblicz bazowe koszty dla detalu (bez alokacji) - respektuje manualne wartości.

        Zapisuje osobne składniki kosztowe:
        - material_cost: koszt materiału (zmieniany przez model alokacji)
        - cutting_cost: koszt cięcia (STAŁY)
        - engraving_cost: koszt graweru (STAŁY)
        - foil_cost: koszt folii (STAŁY)
        - piercing_cost: koszt przebicia (STAŁY)
        - base_material_cost: bazowy koszt materiału (przed alokacją)
        """
        part = self.parts_data[idx]

        # Oblicz składniki kosztu L+M - tylko jeśli nie było ręcznie ustawione
        if not part.get('_manual_lm_cost', False):
            costs = self._calculate_lm_cost(part)  # Zwraca słownik ze składnikami

            # Zapisz osobne składniki kosztowe
            part['material_cost'] = costs['material_cost']
            part['cutting_cost'] = costs['cutting_cost']
            part['engraving_cost'] = costs['engraving_cost']
            part['foil_cost'] = costs['foil_cost']
            part['piercing_cost'] = costs.get('piercing_cost', 0)
            part['base_material_cost'] = costs['material_cost']  # Dla alokacji

            # Zapisz formuły dla loggera
            part['_material_formula'] = costs.get('material_formula', '')
            part['_cutting_formula'] = costs.get('cutting_formula', '')
            part['_foil_formula'] = costs.get('foil_formula', '')
            part['_piercing_formula'] = costs.get('piercing_formula', '')

            # Jeśli nie kalkulujemy z materiałem - wyzeruj koszt materiału
            if not part.get('calc_with_material', True):
                part['material_cost'] = 0.0
                part['base_material_cost'] = 0.0

            # L+M jako suma składników
            lm_cost = (part['material_cost'] + part['cutting_cost'] +
                      part['engraving_cost'] + part['foil_cost'] + part['piercing_cost'])
            part['lm_cost'] = lm_cost
            part['base_lm_cost'] = lm_cost
        else:
            # Użyj ręcznie ustawionej wartości - zachowaj poprzednie składniki
            lm_cost = float(part.get('lm_cost', 0) or 0)
            part['base_lm_cost'] = lm_cost
            # Jeśli brak składników - użyj L+M jako materiału
            if 'material_cost' not in part:
                part['material_cost'] = lm_cost
                part['cutting_cost'] = 0.0
                part['engraving_cost'] = 0.0
                part['foil_cost'] = 0.0
                part['piercing_cost'] = 0.0
                part['base_material_cost'] = lm_cost

        # Przelicz koszt gięć - tylko jeśli nie było ręcznie ustawione
        if not part.get('_manual_bending_cost', False):
            bends = int(part.get('bends', 0) or 0)
            bending_cost = bends * self.BEND_PRICE
            part['bending_cost'] = bending_cost
        else:
            bending_cost = float(part.get('bending_cost', 0) or 0)

        additional = float(part.get('additional', 0) or 0)
        total_unit = lm_cost + bending_cost + additional
        part['total_unit'] = total_unit

    def _apply_unit_allocation(self):
        """Prostokąt otaczający: równy podział kosztów MATERIAŁU między detale.

        WAŻNE: Tylko material_cost jest dzielony równo.
        Koszty cięcia, graweru i folii pozostają STAŁE (zależą od geometrii).
        """
        if not self.parts_data:
            return

        # Oblicz sumę kosztów MATERIAŁU tylko dla nie-manualnych detali
        non_manual_parts = [p for p in self.parts_data if not p.get('_manual_lm_cost', False)]
        if not non_manual_parts:
            # Wszystkie są manualne - tylko aktualizuj total
            for part in self.parts_data:
                lm_cost = float(part.get('lm_cost', 0) or 0)
                bending_cost = float(part.get('bending_cost', 0) or 0)
                additional = float(part.get('additional', 0) or 0)
                part['total_unit'] = lm_cost + bending_cost + additional
            return

        # Suma kosztów MATERIAŁU (nie całego L+M!)
        total_material = sum(float(p.get('material_cost', 0) or 0) for p in non_manual_parts)
        num_parts = len(non_manual_parts)
        equal_material = total_material / num_parts if num_parts > 0 else 0

        logger.info(f"[Alokacja Jednostkowa] Suma materiału: {total_material:.2f}, "
                   f"Detali: {num_parts}, Mat/detal: {equal_material:.2f}")

        for part in self.parts_data:
            # Nie zmieniaj manualnych wartości L+M
            if not part.get('_manual_lm_cost', False):
                # Zmień TYLKO koszt materiału - reszta pozostaje stała
                part['material_cost'] = equal_material
                # Przelicz L+M jako sumę składników (cięcie, grawer, folia, piercing pozostają bez zmian)
                part['lm_cost'] = (part['material_cost'] +
                                  float(part.get('cutting_cost', 0) or 0) +
                                  float(part.get('engraving_cost', 0) or 0) +
                                  float(part.get('foil_cost', 0) or 0) +
                                  float(part.get('piercing_cost', 0) or 0))

            lm_cost = float(part.get('lm_cost', 0) or 0)
            bending_cost = float(part.get('bending_cost', 0) or 0)
            additional = float(part.get('additional', 0) or 0)
            part['total_unit'] = lm_cost + bending_cost + additional

    def _apply_per_sheet_allocation(self):
        """Na arkusz: koszt arkusza podzielony równo między detale.

        WAŻNE: Tylko material_cost jest modyfikowany.
        Koszty cięcia, graweru, folii i piercingu pozostają STAŁE (zależą od geometrii).

        Logika: Suma kosztów materiału (lub koszt arkusza z nestingu) dzielona
        równo między wszystkie detale.
        """
        if not self.parts_data:
            return

        non_manual_parts = [p for p in self.parts_data if not p.get('_manual_lm_cost', False)]
        if not non_manual_parts:
            # Wszystkie są manualne - tylko aktualizuj total
            for part in self.parts_data:
                lm_cost = float(part.get('lm_cost', 0) or 0)
                bending_cost = float(part.get('bending_cost', 0) or 0)
                additional = float(part.get('additional', 0) or 0)
                part['total_unit'] = lm_cost + bending_cost + additional
            return

        # Oblicz całkowity koszt materiału (bounding boxes)
        total_sheet_cost = sum(float(p.get('base_material_cost', 0) or 0) for p in non_manual_parts)

        # Jeśli mamy wyniki nestingu z kosztem arkuszy - użyj ich
        if hasattr(self, 'nesting_results') and self.nesting_results:
            sheets = self.nesting_results.get('sheets', [])
            if sheets:
                # Suma kosztów wszystkich użytych arkuszy
                sheet_costs = sum(float(s.get('sheet_cost', 0) or 0) for s in sheets)
                if sheet_costs > 0:
                    total_sheet_cost = sheet_costs
                    logger.info(f"[Alokacja Na Arkusz] Używam kosztów arkuszy z nestingu: {total_sheet_cost:.2f}")

        # Podziel równo na wszystkie nie-manualne detale
        num_parts = len(non_manual_parts)
        equal_material = total_sheet_cost / num_parts if num_parts > 0 else 0

        logger.info(f"[Alokacja Na Arkusz] Koszt arkuszy: {total_sheet_cost:.2f}, "
                   f"Detali: {num_parts}, Mat/detal: {equal_material:.2f}")

        for part in self.parts_data:
            # Nie zmieniaj manualnych wartości L+M
            if not part.get('_manual_lm_cost', False):
                # Zmień TYLKO koszt materiału - reszta pozostaje stała
                part['material_cost'] = equal_material
                # Przelicz L+M jako sumę składników (cięcie, grawer, folia, piercing pozostają bez zmian)
                part['lm_cost'] = (part['material_cost'] +
                                  float(part.get('cutting_cost', 0) or 0) +
                                  float(part.get('engraving_cost', 0) or 0) +
                                  float(part.get('foil_cost', 0) or 0) +
                                  float(part.get('piercing_cost', 0) or 0))

            lm_cost = float(part.get('lm_cost', 0) or 0)
            bending_cost = float(part.get('bending_cost', 0) or 0)
            additional = float(part.get('additional', 0) or 0)
            part['total_unit'] = lm_cost + bending_cost + additional

    def _update_row(self, idx: int):
        """Aktualizuj wiersz w tabeli"""
        part = self.parts_data[idx]
        item_id = part.get('_item_id')
        if item_id:
            self.tree.item(item_id, values=self._part_to_values(part))

    def _part_to_values(self, part: Dict) -> tuple:
        """Konwertuj dane detalu na wartosci dla tabeli"""
        qty = int(part.get('quantity', 1) or 1)
        bends = int(part.get('bends', 0) or 0)
        bending_cost_unit = float(part.get('bending_cost', 0) or 0)

        return (
            part.get('nr', ''),
            part.get('name', ''),
            part.get('material', ''),
            f"{part.get('thickness', 0):.1f}",
            qty,
            f"{part.get('lm_cost', 0):.2f}",
            bends,  # Bends per unit
            f"{bending_cost_unit:.2f}",  # Bend$ per unit
            f"{part.get('additional', 0):.2f}",
            f"{part.get('weight', 0):.2f}",
            f"{part.get('cutting_len', 0):.0f}",
            f"{part.get('total_unit', 0):.2f}",
        )

    def _update_summary(self):
        """Aktualizuj podsumowanie z sumami długości cięcia i graweru"""
        total_parts = len(self.parts_data)
        total_qty = sum(int(p.get('quantity', 1) or 1) for p in self.parts_data)
        total_lm = sum(float(p.get('lm_cost', 0) or 0) * int(p.get('quantity', 1) or 1) for p in self.parts_data)
        total_bends = sum(int(p.get('bends', 0) or 0) * int(p.get('quantity', 1) or 1) for p in self.parts_data)
        total_bend_cost = sum(float(p.get('bending_cost', 0) or 0) * int(p.get('quantity', 1) or 1) for p in self.parts_data)
        total_all = sum(float(p.get('total_unit', 0) or 0) * int(p.get('quantity', 1) or 1) for p in self.parts_data)

        # Sumy długości cięcia i graweru (z ilością)
        total_cutting_mm = sum(float(p.get('cutting_len', 0) or 0) * int(p.get('quantity', 1) or 1)
                              for p in self.parts_data)
        total_engraving_mm = sum(float(p.get('engraving_len', 0) or 0) * int(p.get('quantity', 1) or 1)
                                for p in self.parts_data)

        # Konwersja na metry
        total_cutting_m = total_cutting_mm / 1000.0
        total_engraving_m = total_engraving_mm / 1000.0

        self.lbl_summary.configure(
            text=f"Pozycji: {total_parts} | Qty: {total_qty} | "
                 f"L+M: {total_lm:,.2f} | Bends: {total_bends} ({total_bend_cost:,.2f}) | Total: {total_all:,.2f} PLN\n"
                 f"Suma cięcia: {total_cutting_m:,.2f} m | Suma graweru: {total_engraving_m:,.2f} m"
        )

        # Wywołaj callback do aktualizacji kosztów w głównym oknie
        if self.on_parts_change:
            self.on_parts_change(self.parts_data)

    def _refresh_table(self):
        """Odswiez cala tabele"""
        self.tree.delete(*self.tree.get_children())

        for idx, part in enumerate(self.parts_data):
            color = self.PART_COLORS[idx % len(self.PART_COLORS)]
            tag = 'with_material' if part.get('calc_with_material', True) else 'without_material'
            item_id = f"part_{part.get('nr', idx)}"
            part['_item_id'] = item_id

            self.tree.insert_with_thumbnail(
                '', 'end', iid=item_id,
                values=self._part_to_values(part),
                contour=part.get('contour', []),
                color=color,
                tags=(tag,)
            )

    def _add_part(self):
        """Dodaj nowy detal (recznie)"""
        new_part = {
            'nr': self.next_nr,
            'name': f'Detal_{self.next_nr}',
            'material': 'S355',
            'thickness': 2.0,
            'quantity': 1,
            'bends': 0,
            'lm_cost': 0.0,
            'bending_cost': 0.0,
            'additional': 0.0,
            'weight': 0.0,
            'cutting_len': 0,
            'total_unit': 0.0,
            'calc_with_material': self.calc_with_material_var.get(),
            'contour': [],
            'filepath': '',
            'source': 'manual'
        }

        self.next_nr += 1
        self.parts_data.append(new_part)
        self._refresh_table()
        self._update_summary()

        if self.on_parts_change:
            self.on_parts_change(self.parts_data)

    def _add_3d_model(self):
        """Dodaj detal z modelu 3D"""
        filetypes = [
            ("3D Models", "*.step *.stp *.iges *.igs"),
            ("STEP Files", "*.step *.stp"),
            ("IGES Files", "*.iges *.igs"),
            ("All Files", "*.*")
        ]

        files = filedialog.askopenfilenames(
            title="Wybierz modele 3D",
            filetypes=filetypes
        )

        if not files:
            return

        added = 0
        for filepath in files:
            model_data = Model3DLoader.load_model_data(filepath)

            if model_data:
                new_part = {
                    'nr': self.next_nr,
                    'name': Path(filepath).stem,
                    'material': 'S355',
                    'thickness': model_data.get('thickness_mm', 0),
                    'quantity': 1,
                    'bends': model_data.get('bends_count', 0),
                    'lm_cost': 0.0,
                    'bending_cost': 0.0,
                    'additional': 0.0,
                    'weight': model_data.get('weight_kg', 0),
                    'cutting_len': 0,
                    'width': model_data.get('width', 0),
                    'height': model_data.get('height', 0),
                    'total_unit': 0.0,
                    'calc_with_material': self.calc_with_material_var.get(),
                    'contour': model_data.get('contour', []),
                    'filepath': filepath,
                    'source': model_data.get('source', '3D_model')
                }

                self.next_nr += 1
                self.parts_data.append(new_part)
                added += 1
            else:
                logger.warning(f"Could not load 3D model: {filepath}")

        if added > 0:
            self._refresh_table()
            self._update_summary()
            messagebox.showinfo("Sukces", f"Dodano {added} detali z modeli 3D")

            if self.on_parts_change:
                self.on_parts_change(self.parts_data)

    def _open_catalog_picker(self):
        """Otwórz okno wyboru produktów z katalogu"""
        try:
            from orders.gui.product_catalog_picker import ProductCatalogPicker
            picker = ProductCatalogPicker(
                self.winfo_toplevel(),
                on_select_callback=self.add_from_catalog
            )
        except ImportError as e:
            logger.error(f"[DetailedParts] Cannot import ProductCatalogPicker: {e}")
            messagebox.showerror("Błąd", "Moduł ProductCatalogPicker niedostępny")
        except Exception as e:
            logger.error(f"[DetailedParts] Error opening catalog picker: {e}")
            messagebox.showerror("Błąd", f"Nie można otworzyć katalogu: {e}")

    def add_from_catalog(self, product_ids: list):
        """Dodaj produkty z katalogu do listy detali (bez nestingu/DXF)"""
        if not product_ids:
            return

        try:
            from core.supabase_client import get_supabase_client
            from products.repository import ProductRepository

            client = get_supabase_client()
            product_repo = ProductRepository(client)

            added = 0
            for product_id in product_ids:
                product = product_repo.get_by_id(product_id)
                if not product:
                    logger.warning(f"[DetailedParts] Product not found: {product_id}")
                    continue

                # Pobierz nazwę materiału
                material_name = 'S355'  # Domyślny
                if product.get('materials_dict'):
                    material_name = product['materials_dict'].get('name', material_name)

                part_data = {
                    'nr': self.next_nr,
                    'name': product.get('name', 'Bez nazwy'),
                    'material': material_name,
                    'thickness': float(product.get('thickness_mm', 0) or 0),
                    'quantity': 1,
                    'weight_kg': float(product.get('weight_kg', 0) or 0),
                    'cutting_len': float(product.get('cutting_length_mm', 0) or 0),
                    'engraving_len': float(product.get('engraving_length_mm', 0) or 0),
                    'bends': int(product.get('bends_count', 0) or 0),
                    'width': float(product.get('width_mm', 0) or 0),
                    'height': float(product.get('height_mm', 0) or 0),
                    'source': 'catalog',
                    'catalog_id': product_id,
                    'filepath': product.get('cad_2d_path', ''),
                    'lm_cost': 0.0,
                    'bending_cost': 0.0,
                    'additional': 0.0,
                    'total_unit': 0.0,
                    'calc_with_material': self.calc_with_material_var.get(),
                }

                # Oblicz koszty
                costs = self._calculate_lm_cost(part_data)
                part_data.update({
                    'material_cost': costs['material_cost'],
                    'cutting_cost': costs['cutting_cost'],
                    'engraving_cost': costs['engraving_cost'],
                    'foil_cost': costs['foil_cost'],
                    'piercing_cost': costs.get('piercing_cost', 0),
                    'lm_cost': costs['total_lm'],
                    'base_lm_cost': costs['total_lm'],
                    'base_material_cost': costs['material_cost'],
                    '_material_formula': costs.get('material_formula', ''),
                    '_cutting_formula': costs.get('cutting_formula', ''),
                    '_foil_formula': costs.get('foil_formula', ''),
                    '_piercing_formula': costs.get('piercing_formula', ''),
                })

                if part_data['bends'] > 0:
                    part_data['bending_cost'] = part_data['bends'] * self.BEND_PRICE

                part_data['total_unit'] = (
                    part_data['lm_cost'] +
                    part_data['bending_cost'] +
                    part_data['additional']
                )

                self.next_nr += 1
                self.parts_data.append(part_data)
                added += 1
                logger.info(f"[DetailedParts] Added from catalog: {part_data['name']}")

            if added > 0:
                self._refresh_table()
                self._update_summary()
                messagebox.showinfo("Sukces", f"Dodano {added} produktów z katalogu")

                if self.on_parts_change:
                    self.on_parts_change(self.parts_data)

        except Exception as e:
            logger.error(f"[DetailedParts] Error adding from catalog: {e}")
            messagebox.showerror("Błąd", f"Nie można dodać produktów: {e}")

    def _duplicate_part(self):
        """Duplikuj zaznaczony detal"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Uwaga", "Wybierz detal do duplikacji")
            return

        idx = self._find_part_index(selection[0])
        if idx is None:
            return

        original = self.parts_data[idx]
        new_part = original.copy()
        new_part['nr'] = self.next_nr
        new_part['name'] = f"{original['name']}_kopia"
        new_part['_item_id'] = None

        self.next_nr += 1
        self.parts_data.append(new_part)
        self._refresh_table()
        self._update_summary()

        if self.on_parts_change:
            self.on_parts_change(self.parts_data)

    def _delete_part(self):
        """Usun zaznaczony detal"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Uwaga", "Wybierz detal do usuniecia")
            return

        if not messagebox.askyesno("Potwierdzenie", "Usunac zaznaczony detal?"):
            return

        idx = self._find_part_index(selection[0])
        if idx is not None:
            del self.parts_data[idx]

        self._refresh_table()
        self._update_summary()

        if self.on_parts_change:
            self.on_parts_change(self.parts_data)

    def _apply_filter(self, event=None):
        """Zastosuj filtr"""
        # W przyszlosci - filtrowanie widocznych wierszy
        pass

    # === MATERIAL PRICES, SPEEDS & DENSITIES ===
    # DEPRECATED: Te stale to fallback - glowne zrodlo danych to PricingDataCache!
    # Patrz: core/pricing_cache.py

    CUTTING_SPEEDS = {  # m/min (referencyjne)
        'S355': 3.0, 'S235': 3.2, 'DC01': 3.5, 'DC04': 3.5,
        '1.4301': 2.5, '1.4404': 2.3, 'INOX': 2.5,
        'AL': 4.0, 'ALU': 4.0, 'ALUMINIUM': 4.0,
        'DEFAULT': 3.0
    }

    MATERIAL_DENSITIES = {  # kg/m³
        'S355': 7850, 'S235': 7850, 'DC01': 7850, 'DC04': 7850,
        '1.4301': 7900, '1.4404': 7950, 'INOX': 7900,
        'AL': 2700, 'ALU': 2700, 'ALUMINIUM': 2700,
        'DEFAULT': 7850
    }

    # Ceny graweru [PLN/m] - fallback
    ENGRAVING_PRICE = 2.5  # PLN/m

    # POPRAWKA: Cena folii w PLN/m (NIE PLN/m2!)
    # Poprzednia wartosc 5.0 byla BLEDNA - powinna byc ~0.15-0.20 PLN/m
    FOIL_REMOVAL_PRICE = 0.20  # PLN/m - fallback, pobierane z PricingDataCache

    # Współczynnik naddatku na wykorzystanie arkusza (35% = 1.35)
    # Przy nestingu typowo wykorzystuje się ok. 65-75% arkusza,
    # więc dodajemy 35% naddatku do powierzchni brutto detalu
    SHEET_UTILIZATION_FACTOR = 1.35

    def _calculate_weight_from_gross_area(self, part_data: Dict) -> float:
        """
        Oblicz wagę z powierzchni brutto detalu (kontur zewnętrzny DXF).

        Powierzchnia brutto = największa zamknięta LWPOLYLINE w pliku DXF.
        Jest to rzeczywista powierzchnia detalu BEZ uwzględniania otworów.

        Dodaje współczynnik 35% naddatku na teoretyczne wykorzystanie arkusza
        (typowa efektywność nestingu = 65-75%).

        Wzór: Waga [kg] = Area [mm²] × 1.35 × Thickness [mm] × Density [kg/m³] / 10^9
        """
        thickness_mm = float(part_data.get('thickness', 0) or 0)
        material = part_data.get('material', '').upper()

        if thickness_mm <= 0:
            return 0.0

        # Preferuj area_gross_mm2 (powierzchnia brutto z DXF)
        area_gross_mm2 = float(part_data.get('area_gross_mm2', 0) or 0)

        if area_gross_mm2 <= 0:
            # Fallback: spróbuj z weight_kg jeśli już obliczone przy ładowaniu DXF
            existing_weight = float(part_data.get('weight_kg', 0) or 0)
            if existing_weight > 0:
                # Istniejąca waga już bez naddatku - dodaj naddatek
                return existing_weight * self.SHEET_UTILIZATION_FACTOR

            # Ostateczny fallback: bounding box (width × height)
            width_mm = float(part_data.get('width', 0) or 0)
            height_mm = float(part_data.get('height', 0) or 0)
            if width_mm > 0 and height_mm > 0:
                area_gross_mm2 = width_mm * height_mm
            else:
                return 0.0

        # Dodaj naddatek 35% na wykorzystanie arkusza
        area_with_factor = area_gross_mm2 * self.SHEET_UTILIZATION_FACTOR

        # Oblicz wagę: Area [mm²] × 1.35 × Thickness [mm] × Density [kg/m³] / 10^9
        density = self.MATERIAL_DENSITIES.get(material, self.MATERIAL_DENSITIES['DEFAULT'])
        weight_kg = (area_with_factor * thickness_mm * density) / 1_000_000_000.0

        # Zapisz dane do logowania
        part_data['_area_gross_mm2'] = area_gross_mm2
        part_data['_area_with_factor_mm2'] = area_with_factor

        return weight_kg

    def _get_cutting_price(self, material: str, thickness: float) -> float:
        """Pobierz cenę cięcia z cennika [PLN/m] - najpierw Supabase, potem fallback"""
        material = material.upper()

        # 1. PRIORYTET: Pobierz z Supabase
        try:
            from pricing.repository import PricingRepository
            from core.supabase_client import get_supabase_client

            repo = PricingRepository(get_supabase_client())
            price_data = repo.get_cutting_price(material, thickness, gas='N')
            if price_data and price_data.get('price_per_meter', 0) > 0:
                price = price_data['price_per_meter']
                logger.debug(f"[Pricing] Cutting {material}/{thickness}mm: {price:.4f} PLN/m (Supabase)")
                return price
        except Exception as e:
            logger.debug(f"[Pricing] Supabase error for cutting price: {e}")

        # 2. FALLBACK: Pobierz z PricingDataCache (Supabase cached)
        try:
            from core.pricing_cache import get_pricing_cache
            cache = get_pricing_cache()
            if cache.is_loaded:
                rate = cache.get_cutting_price(material, thickness, 'N')
                if rate is not None:
                    logger.debug(f"[Pricing] Cutting {material}/{thickness}mm: {rate:.4f} PLN/m (PricingCache)")
                    return rate
        except Exception as e:
            logger.debug(f"[Pricing] PricingCache error: {e}")

        # 3. OSTATNI FALLBACK: DEFAULT_RATES z cost_engine
        from orders.cost_engine import DEFAULT_RATES

        # Określ typ materiału
        if material.startswith('1.4') or 'INOX' in material:
            material_type = 'stainless'
        elif material in ['AL', 'ALU', 'ALUMINIUM'] or material.startswith('AL'):
            material_type = 'aluminum'
        else:
            material_type = 'steel'

        price_table = DEFAULT_RATES['cutting_pln_per_m'].get(material_type, DEFAULT_RATES['cutting_pln_per_m']['steel'])

        # Znajdź najbliższą grubość
        thicknesses = sorted(price_table.keys())
        closest = min(thicknesses, key=lambda x: abs(x - thickness))

        logger.debug(f"[Pricing] Cutting {material}/{thickness}mm: {price_table[closest]:.4f} PLN/m (DEFAULT_RATES)")
        return price_table[closest]

    def _calculate_lm_cost(self, part_data: Dict) -> Dict[str, float]:
        """
        Oblicz składniki kosztu L+M (Laser + Material) dla detalu.

        Zwraca słownik z osobnymi składnikami:
        - material_cost: koszt z prostokąta otaczającego (bounding box) wg cennika
        - cutting_cost: koszt na bazie długości cięcia z cenników
        - engraving_cost: koszt z długości graweru
        - foil_cost: koszt odparowania folii (tylko dla INOX ≤5mm)
        - total_lm: suma wszystkich składników

        Model alokacji operuje TYLKO na material_cost - pozostałe są stałe.
        """
        material = part_data.get('material', '').upper()
        thickness = float(part_data.get('thickness', 0) or 0)
        width_mm = float(part_data.get('width', 0) or 0)
        height_mm = float(part_data.get('height', 0) or 0)
        quantity = int(part_data.get('quantity', 1) or 1)

        # Długości cięcia
        cutting_len_mm = float(part_data.get('cutting_len', 0) or 0)
        engraving_len_mm = float(part_data.get('engraving_len', 0) or 0)

        # Gestosc materialu
        density = self.MATERIAL_DENSITIES.get(material, self.MATERIAL_DENSITIES['DEFAULT'])

        # === START LOGGING ===
        if cost_logger:
            cost_logger.start_part(
                part_name=part_data.get('name', '?'),
                quantity=quantity,
                material=material,
                thickness=thickness,
                width=width_mm,
                height=height_mm
            )

        # === KOSZT MATERIAŁU z powierzchni brutto DXF ===
        # Oblicz wagę z powierzchni brutto (kontur zewnętrzny bez otworów)
        weight_kg = self._calculate_weight_from_gross_area(part_data)
        if weight_kg > 0:
            part_data['weight'] = round(weight_kg, 3)

        # Pobierz cenę materiału z cennika lub użyj domyślnej
        mat_price = self._get_material_price(material, thickness)
        material_cost = weight_kg * mat_price

        if cost_logger:
            cost_logger.log_material(
                weight_kg=weight_kg,
                price_per_kg=mat_price,
                cost=material_cost,
                density=density
            )

        # === KOSZT CIĘCIA z cennika ===
        cutting_price_per_m = self._get_cutting_price(material, thickness)
        cutting_len_m = cutting_len_mm / 1000.0
        cutting_cost = cutting_len_m * cutting_price_per_m

        if cost_logger:
            cost_logger.log_cutting(
                length_mm=cutting_len_mm,
                price_per_m=cutting_price_per_m,
                cost=cutting_cost
            )

        # === KOSZT GRAWERU ===
        engraving_len_m = engraving_len_mm / 1000.0
        engraving_price = self._get_engraving_price()
        engraving_cost = engraving_len_m * engraving_price

        if cost_logger:
            cost_logger.log_engraving(
                length_mm=engraving_len_mm,
                price_per_m=engraving_price,
                cost=engraving_cost
            )

        # === KOSZT ODPAROWANIA FOLII ===
        # Tylko dla INOX (1.4xxx) o grubości ≤5mm
        foil_cost = 0.0
        is_inox = material.startswith('1.4') or 'INOX' in material
        foil_applicable = is_inox and thickness <= 5.0

        if foil_applicable:
            # Folia liczona z dlugosci ciecia + graweru (PLN/m)
            foil_len_m = (cutting_len_mm + engraving_len_mm) / 1000.0
            foil_price = self._get_foil_removal_price(material, thickness)
            foil_cost = foil_len_m * foil_price

            if cost_logger:
                cost_logger.log_foil(
                    area_m2=foil_len_m,
                    price=foil_price,
                    cost=foil_cost,
                    applicable=True
                )
        else:
            if cost_logger:
                reason = "material nie jest INOX" if not is_inox else f"grubosc {thickness}mm > 5mm"
                cost_logger.log_foil(applicable=False, reason=reason)

        # === KOSZT PRZEBICIA (PIERCING) ===
        pierce_count = int(part_data.get('piercing_count', 1) or 1)
        pierce_rate = self._get_pierce_rate(material, thickness)
        piercing_cost = pierce_count * pierce_rate

        if cost_logger:
            cost_logger.log_piercing(
                count=pierce_count,
                price_per_pierce=pierce_rate,
                cost=piercing_cost
            )

        total_lm = material_cost + cutting_cost + engraving_cost + foil_cost + piercing_cost

        # === END LOGGING ===
        if cost_logger:
            bending_cost = float(part_data.get('bending_cost', 0) or 0)
            additional = float(part_data.get('additional', 0) or 0)
            cost_logger.end_part(
                total_lm=total_lm,
                bending_cost=bending_cost,
                additional=additional
            )

        logger.debug(f"[LM Cost] {part_data.get('name', '?')}: mat={material_cost:.2f}, "
                    f"cut={cutting_cost:.2f}, engr={engraving_cost:.2f}, foil={foil_cost:.2f}, "
                    f"pierce={piercing_cost:.2f} = {total_lm:.2f}")

        # Formuła dla folii
        if foil_applicable:
            foil_formula = f"{foil_len_m:.3f}m × {foil_price:.2f}PLN/m"
        else:
            foil_formula = "nie dotyczy" if not is_inox else f"grubość {thickness}mm > 5mm"

        # Pobierz powierzchnię do formuły
        area_gross = part_data.get('_area_gross_mm2', part_data.get('area_gross_mm2', 0))

        # Zwróć słownik ze wszystkimi składnikami - model alokacji operuje TYLKO na material_cost
        return {
            'material_cost': material_cost,
            'cutting_cost': cutting_cost,
            'engraving_cost': engraving_cost,
            'foil_cost': foil_cost,
            'piercing_cost': piercing_cost,
            'total_lm': total_lm,
            # Formuły dla logowania
            'material_formula': f"{weight_kg:.3f}kg × {mat_price:.2f}PLN/kg (pow.brutto {area_gross:.0f}mm² + 35%)",
            'cutting_formula': f"{cutting_len_m:.3f}m × {cutting_price_per_m:.2f}PLN/m",
            'foil_formula': foil_formula,
            'piercing_formula': f"{pierce_count} × {pierce_rate:.2f}PLN"
        }

    def _get_material_price(self, material: str, thickness: float) -> float:
        """Pobierz cenę materiału z cennika [PLN/kg] - najpierw Supabase, potem fallback"""
        material = material.upper()

        # 1. PRIORYTET: Pobierz z Supabase
        try:
            from pricing.repository import PricingRepository
            from core.supabase_client import get_supabase_client

            repo = PricingRepository(get_supabase_client())
            price_data = repo.get_material_price(material, thickness)
            if price_data and price_data.get('price_per_kg', 0) > 0:
                price = price_data['price_per_kg']
                logger.debug(f"[Pricing] Material {material}/{thickness}mm: {price:.2f} PLN/kg (Supabase)")
                return price
        except Exception as e:
            logger.debug(f"[Pricing] Supabase error for material price: {e}")

        # 2. FALLBACK: Pobierz z PricingDataCache (Supabase cached)
        try:
            from core.pricing_cache import get_pricing_cache
            cache = get_pricing_cache()
            if cache.is_loaded:
                price = cache.get_material_price(material, thickness)
                if price is not None:
                    logger.debug(f"[Pricing] Material {material}/{thickness}mm: {price:.2f} PLN/kg (PricingCache)")
                    return price
        except Exception as e:
            logger.debug(f"[Pricing] PricingCache error: {e}")

        # 3. OSTATNI FALLBACK: Domyślne ceny wg typu materiału
        # Określ typ materiału
        if material.startswith('1.4') or 'INOX' in material:
            price = 18.0  # stainless
        elif material in ['AL', 'ALU', 'ALUMINIUM'] or material.startswith('AL'):
            price = 12.0  # aluminum
        else:
            price = 5.0  # steel

        logger.debug(f"[Pricing] Material {material}/{thickness}mm: {price:.2f} PLN/kg (DEFAULT)")
        return price

    def _get_engraving_price(self) -> float:
        """
        Pobierz cenę graweru [PLN/m].

        UWAGA: Grawer nie jest w PricingDataCache - używamy DEFAULT_RATES.
        """
        from orders.cost_engine import DEFAULT_RATES
        return DEFAULT_RATES.get('engraving_pln_per_m', self.ENGRAVING_PRICE)

    def _get_foil_removal_price(self, material: str, thickness: float) -> float:
        """
        Pobierz cene usuwania folii [PLN/m].

        POPRAWKA: Zwraca PLN/m (nie PLN/m2!) z PricingDataCache.
        Poprzedni kod zwracal bledna wartosc 5.0 PLN.

        Args:
            material: Nazwa materialu
            thickness: Grubosc [mm]

        Returns:
            Cena PLN/m (ok. 0.15-0.20)
        """
        try:
            from core.pricing_cache import get_pricing_cache
            cache = get_pricing_cache()
            if cache.is_loaded:
                rate = cache.get_foil_rate(material, thickness)
                if rate is not None:
                    return rate
        except Exception:
            pass
        return self.FOIL_REMOVAL_PRICE  # 0.20 PLN/m fallback

    def _get_pierce_rate(self, material: str, thickness: float) -> float:
        """
        Pobierz koszt pojedynczego przebicia [PLN/szt].

        Zrodlo: PricingDataCache -> Supabase piercing_rates
        """
        try:
            from core.pricing_cache import get_pricing_cache
            cache = get_pricing_cache()
            if cache.is_loaded:
                rate = cache.get_piercing_rate(material, thickness)
                if rate is not None:
                    return rate
        except Exception:
            pass
        # Domyslna stawka: 0.40 PLN za przebicie
        return 0.40

    # === PUBLIC API ===

    def set_parts(self, parts: List[Dict]):
        """Ustaw liste detali"""
        self.parts_data = []
        self.next_nr = 1

        for part in parts:
            weight = float(part.get('weight_kg', part.get('weight', 0)) or 0)
            cutting_len = float(part.get('cutting_len', part.get('cutting_length_mm', part.get('cutting_length', 0))) or 0)
            # Mapowanie pola graweru: DXF loader uzywa 'marking_length_mm', panel uzywa 'engraving_len'
            engraving_len = float(part.get('marking_length_mm',
                                           part.get('engraving_len',
                                                    part.get('engraving_length', 0))) or 0)

            part_data = {
                'nr': self.next_nr,
                'name': part.get('name', ''),
                'material': part.get('material', ''),
                'thickness': float(part.get('thickness_mm', part.get('thickness', 0)) or 0),
                'quantity': int(part.get('quantity', 1) or 1),
                'bends': int(part.get('bends', part.get('bends_count', 0)) or 0),
                'lm_cost': 0.0,  # Obliczony ponizej
                'bending_cost': float(part.get('bending_cost', part.get('bending', 0)) or 0),
                'additional': float(part.get('additional', 0) or 0),
                'weight': weight,
                'weight_kg': weight,  # Alias dla kompatybilności
                'cutting_len': cutting_len,
                'engraving_len': engraving_len,  # Dlugosc graweru
                'piercing_count': int(part.get('piercing_count', 1) or 1),
                'total_unit': 0.0,
                'calc_with_material': self.calc_with_material_var.get(),
                'contour': part.get('contour', []),
                'holes': part.get('holes', []),
                'filepath': part.get('filepath', ''),
                'width': part.get('width', 0),
                'height': part.get('height', 0),
                # Powierzchnie z DXF - kluczowe dla obliczenia wagi!
                'area_gross_mm2': float(part.get('area_gross_mm2', 0) or 0),
                'area_net_mm2': float(part.get('area_net_mm2', 0) or 0),
                'area_bbox_mm2': float(part.get('area_bbox_mm2', 0) or 0),
                'source': part.get('source', 'dxf')
            }

            # Oblicz L+M cost jesli nie podano
            existing_lm = float(part.get('lm_cost', part.get('unit_cost', 0)) or 0)
            if existing_lm > 0:
                part_data['lm_cost'] = existing_lm
            else:
                # _calculate_lm_cost zwraca Dict ze skladnikami
                costs = self._calculate_lm_cost(part_data)
                part_data['material_cost'] = costs['material_cost']
                part_data['cutting_cost'] = costs['cutting_cost']
                part_data['engraving_cost'] = costs['engraving_cost']
                part_data['foil_cost'] = costs['foil_cost']
                part_data['piercing_cost'] = costs.get('piercing_cost', 0)
                part_data['base_material_cost'] = costs['material_cost']
                part_data['lm_cost'] = costs['total_lm']
                part_data['base_lm_cost'] = costs['total_lm']
                # Zapisz formuly dla loggera
                part_data['_material_formula'] = costs.get('material_formula', '')
                part_data['_cutting_formula'] = costs.get('cutting_formula', '')
                part_data['_foil_formula'] = costs.get('foil_formula', '')
                part_data['_piercing_formula'] = costs.get('piercing_formula', '')

            # Oblicz bending cost jesli sa giecia
            if part_data['bends'] > 0 and part_data['bending_cost'] == 0:
                part_data['bending_cost'] = part_data['bends'] * self.BEND_PRICE

            # Oblicz total
            part_data['total_unit'] = (
                part_data['lm_cost'] +
                part_data['bending_cost'] +
                part_data['additional']
            )

            self.next_nr += 1
            self.parts_data.append(part_data)

        self._refresh_table()
        self._update_summary()

    def get_parts(self) -> List[Dict]:
        """Pobierz liste detali"""
        return self.parts_data

    def get_total_cost(self) -> float:
        """Pobierz calkowity koszt"""
        return sum(p.get('total_unit', 0) * p.get('quantity', 1) for p in self.parts_data)


# === TEST ===
if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")

    root = ctk.CTk()
    root.title("Detailed Parts Panel Test")
    root.geometry("1100x450")

    panel = DetailedPartsPanel(root)
    panel.pack(fill="both", expand=True, padx=10, pady=10)

    # Test data
    test_parts = [
        {'name': 'Plyta_A', 'material': 'S355', 'thickness_mm': 3.0, 'quantity': 5,
         'weight_kg': 2.5, 'cutting_length': 1500, 'unit_cost': 45.0,
         'contour': [(0,0), (100,0), (100,50), (0,50)]},
        {'name': 'Plyta_B', 'material': 'DC01', 'thickness_mm': 1.5, 'quantity': 10,
         'weight_kg': 0.8, 'cutting_length': 800, 'unit_cost': 15.0,
         'contour': [(0,0), (80,0), (80,40), (0,40)]},
        {'name': 'Wspornik', 'material': 'S355', 'thickness_mm': 5.0, 'quantity': 2,
         'weight_kg': 4.2, 'cutting_length': 2200, 'unit_cost': 85.0, 'bending': 12.0,
         'bends': 3, 'contour': [(0,0), (60,0), (60,80), (30,100), (0,80)]},
    ]

    panel.set_parts(test_parts)

    root.mainloop()
