"""
NewERP - Quotation Window
=========================
Główne okno modułu wycen - wczytywanie detali, nesting, kalkulacja.

Workflow:
1. Wczytaj folder z plikami CAD
2. Parsuj nazwy → wyciągnij materiał, grubość, ilość
3. Pobierz wymiary z DXF (bounding box)
4. Uruchom nesting → dobierz format arkusza
5. Kalkuluj cenę
6. Generuj ofertę PDF
"""

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, List, Callable
from pathlib import Path
import threading
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Sprawdź dostępność bibliotek nestingu
try:
    import shapely
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

try:
    import pyclipper
    HAS_PYCLIPPER = True
except ImportError:
    HAS_PYCLIPPER = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# ============================================================
# KOLORY I STYLE
# ============================================================

class Theme:
    """Paleta kolorów"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_CARD_HOVER = "#252525"
    BG_INPUT = "#2d2d2d"
    
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#666666"
    
    ACCENT_PRIMARY = "#8b5cf6"   # Fioletowy - wyceny
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"
    ACCENT_INFO = "#06b6d4"


# ============================================================
# MAIN WINDOW
# ============================================================

class QuotationWindow(ctk.CTkToplevel):
    """
    Okno wycen - workflow od plików do oferty.
    """
    
    def __init__(self, parent=None, customer_id: str = None):
        super().__init__(parent)
        
        self.customer_id = customer_id
        self.customer_name = ""
        
        # Stan
        self.parts_list: List[Dict] = []
        self.nesting_result = None
        self.pricing_result = None
        
        # Konfiguracja okna
        self.title("💰 Nowa Wycena - NewERP")
        self.geometry("1400x900")
        self.minsize(1200, 700)
        self.configure(fg_color=Theme.BG_DARK)
        
        # Build UI
        self._setup_ui()
        self._setup_bindings()
        
        # Focus
        self.lift()
        self.focus_force()
    
    def _setup_ui(self):
        """Buduj interfejs"""
        # Grid główny - 2 kolumny
        self.grid_columnconfigure(0, weight=2)  # Lista detali
        self.grid_columnconfigure(1, weight=1)  # Panel kalkulacji
        self.grid_rowconfigure(1, weight=1)
        
        # === STATUSBAR (najpierw, bo używany przez inne metody) ===
        self._setup_statusbar()
        
        # === HEADER ===
        self._setup_header()
        
        # === LISTA DETALI (lewa) ===
        self._setup_parts_panel()
        
        # === PANEL KALKULACJI (prawa) ===
        self._setup_calculation_panel()
    
    def _setup_header(self):
        """Nagłówek z przyciskami akcji"""
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=70)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        header.grid_propagate(False)
        
        # Tytuł
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", padx=20, pady=10)
        
        title = ctk.CTkLabel(
            title_frame,
            text="💰 NOWA WYCENA",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        )
        title.pack(anchor="w")
        
        # Klient
        self.customer_label = ctk.CTkLabel(
            title_frame,
            text="Klient: nie wybrano",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.customer_label.pack(anchor="w")
        
        # Przyciski (prawa strona)
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=20, pady=10)
        
        # Wybierz klienta
        btn_customer = ctk.CTkButton(
            btn_frame,
            text="👥 Wybierz klienta",
            command=self._select_customer,
            width=140,
            height=35,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER
        )
        btn_customer.pack(side="left", padx=5)
        
        # Wczytaj folder
        btn_load = ctk.CTkButton(
            btn_frame,
            text="📁 Wczytaj folder",
            command=self._load_folder,
            width=140,
            height=35,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color="#7c4de3"
        )
        btn_load.pack(side="left", padx=5)
        
        # Wczytaj archiwum
        btn_archive = ctk.CTkButton(
            btn_frame,
            text="📦 Wczytaj ZIP",
            command=self._load_archive,
            width=120,
            height=35,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER
        )
        btn_archive.pack(side="left", padx=5)
        
        # Import cenników
        btn_prices = ctk.CTkButton(
            btn_frame,
            text="💲 Cenniki",
            command=self._import_pricing,
            width=100,
            height=35,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER
        )
        btn_prices.pack(side="left", padx=5)

        # Nesting
        self.btn_nesting = ctk.CTkButton(
            btn_frame,
            text="⇄ Nesting",
            command=self._open_nesting,
            width=100,
            height=35,
            fg_color=Theme.ACCENT_WARNING,
            hover_color="#d97706"
        )
        self.btn_nesting.pack(side="left", padx=5)

        # Separator
        sep = ctk.CTkFrame(btn_frame, width=2, height=30, fg_color=Theme.TEXT_MUTED)
        sep.pack(side="left", padx=15)
        
        # Kalkuluj (z podglądem live)
        self.btn_calculate = ctk.CTkButton(
            btn_frame,
            text="🧮 Kalkuluj",
            command=self._calculate_with_preview,
            width=120,
            height=35,
            fg_color=Theme.ACCENT_SUCCESS,
            hover_color="#1ea54d",
            state="disabled"
        )
        self.btn_calculate.pack(side="left", padx=5)
        
        # Generuj ofertę
        self.btn_generate = ctk.CTkButton(
            btn_frame,
            text="📄 Generuj ofertę",
            command=self._generate_quotation,
            width=140,
            height=35,
            fg_color=Theme.ACCENT_INFO,
            hover_color="#0598b8",
            state="disabled"
        )
        self.btn_generate.pack(side="left", padx=5)
    
    def _setup_parts_panel(self):
        """Panel listy detali"""
        panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        panel.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        
        # Nagłówek panelu
        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            header,
            text="DETALE DO WYCENY",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(side="left")
        
        self.parts_count_label = ctk.CTkLabel(
            header,
            text="0 pozycji",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        )
        self.parts_count_label.pack(side="right")
        
        # Toolbar
        toolbar = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=(0, 10))
        
        btn_add = ctk.CTkButton(
            toolbar, text="+ Dodaj", width=80, height=28,
            fg_color=Theme.BG_INPUT, hover_color=Theme.BG_CARD_HOVER,
            command=self._add_part_manually
        )
        btn_add.pack(side="left", padx=(0, 5))
        
        btn_remove = ctk.CTkButton(
            toolbar, text="- Usuń", width=80, height=28,
            fg_color=Theme.ACCENT_DANGER, hover_color="#c53030",
            command=self._remove_selected_part
        )
        btn_remove.pack(side="left", padx=5)
        
        btn_clear = ctk.CTkButton(
            toolbar, text="🗑️ Wyczyść", width=100, height=28,
            fg_color=Theme.BG_INPUT, hover_color=Theme.BG_CARD_HOVER,
            command=self._clear_parts
        )
        btn_clear.pack(side="left", padx=5)
        
        # TreeView dla detali
        tree_frame = ctk.CTkFrame(panel, fg_color=Theme.BG_INPUT)
        tree_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Style
        style = ttk.Style()
        style.configure(
            "Quotation.Treeview",
            background=Theme.BG_INPUT,
            foreground=Theme.TEXT_PRIMARY,
            fieldbackground=Theme.BG_INPUT,
            rowheight=32
        )
        style.configure(
            "Quotation.Treeview.Heading",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_PRIMARY,
            font=('Helvetica', 10, 'bold')
        )
        
        columns = ('name', 'material', 'thickness', 'dimensions', 'qty', 'bending', 'status')
        self.parts_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            style="Quotation.Treeview"
        )
        
        # Konfiguracja kolumn
        self.parts_tree.heading('name', text='Nazwa')
        self.parts_tree.heading('material', text='Materiał')
        self.parts_tree.heading('thickness', text='Grubość')
        self.parts_tree.heading('dimensions', text='Wymiary [mm]')
        self.parts_tree.heading('qty', text='Ilość')
        self.parts_tree.heading('bending', text='Gięcie')
        self.parts_tree.heading('status', text='Status')
        
        self.parts_tree.column('name', width=200)
        self.parts_tree.column('material', width=120)
        self.parts_tree.column('thickness', width=80)
        self.parts_tree.column('dimensions', width=120)
        self.parts_tree.column('qty', width=60)
        self.parts_tree.column('bending', width=60)
        self.parts_tree.column('status', width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.parts_tree.yview)
        self.parts_tree.configure(yscrollcommand=scrollbar.set)
        
        self.parts_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Double-click to edit
        self.parts_tree.bind('<Double-1>', self._edit_part)
        # Selekcja - pokaż miniaturę
        self.parts_tree.bind('<<TreeviewSelect>>', self._on_part_select)
        
        # === PANEL PODGLĄDU MINIATURY ===
        preview_frame = ctk.CTkFrame(panel, fg_color=Theme.BG_INPUT, corner_radius=8)
        preview_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # Nagłówek
        ctk.CTkLabel(
            preview_frame,
            text="📷 Podgląd detalu",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=10, pady=(8, 5))
        
        # Kontener na miniaturę i info
        preview_content = ctk.CTkFrame(preview_frame, fg_color="transparent")
        preview_content.pack(fill="x", padx=10, pady=(0, 10))
        
        # Miniatura (lewa strona)
        self.thumbnail_label = ctk.CTkLabel(
            preview_content,
            text="Wybierz detal",
            width=150,
            height=150,
            fg_color=Theme.BG_CARD,
            corner_radius=8
        )
        self.thumbnail_label.pack(side="left", padx=(0, 10))
        
        # Info o detalu (prawa strona)
        info_frame = ctk.CTkFrame(preview_content, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True)
        
        self.part_info_name = ctk.CTkLabel(
            info_frame, text="", font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.part_info_name.pack(fill="x", pady=2)
        
        self.part_info_material = ctk.CTkLabel(
            info_frame, text="", font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY, anchor="w"
        )
        self.part_info_material.pack(fill="x", pady=2)
        
        self.part_info_dims = ctk.CTkLabel(
            info_frame, text="", font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY, anchor="w"
        )
        self.part_info_dims.pack(fill="x", pady=2)
        
        self.part_info_file = ctk.CTkLabel(
            info_frame, text="", font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED, anchor="w", wraplength=200
        )
        self.part_info_file.pack(fill="x", pady=2)
        
        # Przechowuj referencję do obrazka CTkImage
        self._current_thumbnail = None
    
    def _setup_calculation_panel(self):
        """Panel kalkulacji i wyników"""
        panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        panel.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        
        # Scrollable content
        scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15, pady=15)
        
        # === PARAMETRY ===
        params_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_INPUT, corner_radius=8)
        params_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            params_frame,
            text="⚙️ PARAMETRY",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        # Format arkusza
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row, text="Format arkusza:", width=120, anchor="w").pack(side="left")
        self.sheet_combo = ctk.CTkComboBox(
            row,
            values=["Auto", "1000x2000", "1250x2500", "1500x3000", "2000x4000", "2000x6000"],
            width=150
        )
        self.sheet_combo.set("Auto")
        self.sheet_combo.pack(side="left")
        
        # Algorytm nestingu
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row, text="Algorytm:", width=120, anchor="w").pack(side="left")
        
        # Buduj listę dostępnych algorytmów
        algo_values = ["Szybki (FFDH)"]  # Zawsze dostępny
        if HAS_PYCLIPPER:
            algo_values.append("Dokładny (NFP)")
        if HAS_SHAPELY:
            algo_values.append("Shapely (True Shape)")
        
        self.algorithm_combo = ctk.CTkComboBox(
            row,
            values=algo_values,
            width=150
        )
        self.algorithm_combo.set("Szybki (FFDH)")
        self.algorithm_combo.pack(side="left")
        
        # Info o bibliotekach
        missing_libs = []
        if not HAS_SHAPELY:
            missing_libs.append("shapely")
        if not HAS_PYCLIPPER:
            missing_libs.append("pyclipper")
        if not HAS_OPENPYXL:
            missing_libs.append("openpyxl")
        
        if missing_libs:
            lib_info = ctk.CTkLabel(
                params_frame, 
                text=f"  ⚠️ Brak: {', '.join(missing_libs)} (pip install {' '.join(missing_libs)})",
                font=ctk.CTkFont(size=10),
                text_color=Theme.ACCENT_WARNING
            )
            lib_info.pack(anchor="w", padx=15, pady=(0, 2))
        
        # Tooltip o algorytmach
        algo_info = ctk.CTkLabel(
            params_frame, 
            text="  ℹ️ FFDH=prostokąty, NFP/Shapely=rzeczywiste kształty",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_MUTED
        )
        algo_info.pack(anchor="w", padx=15, pady=(0, 5))
        
        # === PARAMETRY NESTINGU ===
        nesting_label = ctk.CTkLabel(
            params_frame,
            text="📐 Parametry nestingu:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        )
        nesting_label.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Kerf width (szerokość rzazu)
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(row, text="Kerf (rzaz) [mm]:", width=120, anchor="w").pack(side="left")
        self.kerf_entry = ctk.CTkEntry(row, width=80, placeholder_text="0.2")
        self.kerf_entry.insert(0, "0.2")
        self.kerf_entry.pack(side="left")
        ctk.CTkLabel(row, text="szerokość cięcia", font=ctk.CTkFont(size=10), 
                     text_color=Theme.TEXT_MUTED).pack(side="left", padx=5)
        
        # Spacing (odstęp między detalami)
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(row, text="Odstęp [mm]:", width=120, anchor="w").pack(side="left")
        self.spacing_entry = ctk.CTkEntry(row, width=80, placeholder_text="3.0")
        self.spacing_entry.insert(0, "3.0")
        self.spacing_entry.pack(side="left")
        ctk.CTkLabel(row, text="między detalami", font=ctk.CTkFont(size=10),
                     text_color=Theme.TEXT_MUTED).pack(side="left", padx=5)
        
        # Sheet margin (margines arkusza)
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(row, text="Margines [mm]:", width=120, anchor="w").pack(side="left")
        self.sheet_margin_entry = ctk.CTkEntry(row, width=80, placeholder_text="10.0")
        self.sheet_margin_entry.insert(0, "10.0")
        self.sheet_margin_entry.pack(side="left")
        ctk.CTkLabel(row, text="od krawędzi arkusza", font=ctk.CTkFont(size=10),
                     text_color=Theme.TEXT_MUTED).pack(side="left", padx=5)
        
        # Rotacje
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(row, text="Rotacje:", width=120, anchor="w").pack(side="left")
        
        self.rot_0_var = ctk.BooleanVar(value=True)
        self.rot_90_var = ctk.BooleanVar(value=True)
        self.rot_180_var = ctk.BooleanVar(value=False)
        self.rot_270_var = ctk.BooleanVar(value=False)
        
        ctk.CTkCheckBox(row, text="0°", variable=self.rot_0_var, width=50).pack(side="left")
        ctk.CTkCheckBox(row, text="90°", variable=self.rot_90_var, width=50).pack(side="left")
        ctk.CTkCheckBox(row, text="180°", variable=self.rot_180_var, width=60).pack(side="left")
        ctk.CTkCheckBox(row, text="270°", variable=self.rot_270_var, width=60).pack(side="left")
        
        # Separator
        ctk.CTkFrame(params_frame, height=1, fg_color=Theme.TEXT_MUTED).pack(fill="x", padx=15, pady=10)
        
        # Marża
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(row, text="Marża [%]:", width=120, anchor="w").pack(side="left")
        self.margin_entry = ctk.CTkEntry(row, width=80, placeholder_text="25")
        self.margin_entry.insert(0, "25")
        self.margin_entry.pack(side="left")
        
        # Koszty setup
        row = ctk.CTkFrame(params_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(5, 15))
        self.include_setup_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            row,
            text="Dolicz koszty setup i programowania",
            variable=self.include_setup_var
        ).pack(side="left")
        
        # === NESTING ===
        nesting_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_INPUT, corner_radius=8)
        nesting_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            nesting_frame,
            text="📐 NESTING",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        self.nesting_info = ctk.CTkLabel(
            nesting_frame,
            text="Wczytaj detale aby uruchomić nesting",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_MUTED,
            justify="left"
        )
        self.nesting_info.pack(anchor="w", padx=15, pady=(5, 5))
        
        # Progress bar i kontrolki
        self.progress_frame = ctk.CTkFrame(nesting_frame, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=15, pady=(5, 15))
        
        # Pasek postępu
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=200)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)
        
        # Etykieta postępu
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="0%",
            font=ctk.CTkFont(size=11),
            width=45
        )
        self.progress_label.pack(side="left", padx=(0, 10))
        
        # Przycisk anuluj
        self.btn_cancel = ctk.CTkButton(
            self.progress_frame,
            text="✕ Anuluj",
            width=80,
            height=28,
            fg_color=Theme.ACCENT_DANGER,
            hover_color="#dc2626",
            command=self._cancel_calculation,
            state="disabled"
        )
        self.btn_cancel.pack(side="right")
        
        # Flaga anulowania
        self._cancel_requested = False
        self._calculation_thread = None
        
        # Ukryj progress bar początkowo
        self.progress_frame.pack_forget()
        
        # === KALKULACJA ===
        calc_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_INPUT, corner_radius=8)
        calc_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            calc_frame,
            text="💰 KALKULACJA",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        self.calc_info = ctk.CTkLabel(
            calc_frame,
            text="Uruchom kalkulację aby zobaczyć wyniki",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_MUTED,
            justify="left"
        )
        self.calc_info.pack(anchor="w", padx=15, pady=(5, 10))
        
        # Wyniki kalkulacji (ukryte początkowo)
        self.calc_results_frame = ctk.CTkFrame(calc_frame, fg_color="transparent")
        self.calc_results_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # === PODSUMOWANIE ===
        summary_frame = ctk.CTkFrame(scroll, fg_color=Theme.ACCENT_PRIMARY, corner_radius=8)
        summary_frame.pack(fill="x")
        
        ctk.CTkLabel(
            summary_frame,
            text="RAZEM",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        ).pack(anchor="w", padx=15, pady=(15, 5))
        
        self.total_label = ctk.CTkLabel(
            summary_frame,
            text="0.00 PLN",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="white"
        )
        self.total_label.pack(anchor="w", padx=15, pady=(0, 5))
        
        self.unit_price_label = ctk.CTkLabel(
            summary_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#cccccc"
        )
        self.unit_price_label.pack(anchor="w", padx=15, pady=(0, 15))
    
    def _setup_statusbar(self):
        """Pasek statusu"""
        statusbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=30)
        statusbar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        
        self.status_label = ctk.CTkLabel(
            statusbar,
            text="Gotowy",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.status_label.pack(side="left", padx=15, pady=5)
    
    def _setup_bindings(self):
        """Skróty klawiszowe"""
        self.bind('<Control-o>', lambda e: self._load_folder())
        self.bind('<F5>', lambda e: self._calculate())
        self.bind('<Escape>', lambda e: self.destroy())
    
    # ============================================================
    # ACTIONS
    # ============================================================
    
    def _set_status(self, text: str):
        """Ustaw status"""
        if self.winfo_exists():
            self.status_label.configure(text=text)
    
    def _select_customer(self):
        """Wybierz klienta"""
        # TODO: Dialog wyboru klienta
        messagebox.showinfo("Info", "Dialog wyboru klienta - w przygotowaniu")
    
    def _load_folder(self):
        """Wczytaj folder z plikami"""
        folder = filedialog.askdirectory(
            title="Wybierz folder z plikami CAD"
        )
        
        if not folder:
            return
        
        self._set_status(f"Wczytywanie folderu: {folder}")
        
        def load():
            try:
                from shared.parsers.folder_parser import FolderParser
                
                parser = FolderParser()
                result = parser.scan_folder(folder)
                
                # Aktualizuj UI w głównym wątku
                self.after(0, lambda: self._display_scan_result(result))
                
            except Exception as e:
                logger.error(f"Load folder error: {e}")
                self.after(0, lambda: messagebox.showerror("Błąd", f"Nie udało się wczytać folderu:\n{e}"))
        
        threading.Thread(target=load, daemon=True).start()
    
    def _load_archive(self):
        """Wczytaj archiwum ZIP"""
        archive = filedialog.askopenfilename(
            title="Wybierz archiwum",
            filetypes=[
                ("Archiwa", "*.zip *.7z"),
                ("ZIP", "*.zip"),
                ("7-Zip", "*.7z"),
                ("Wszystkie", "*.*")
            ]
        )
        
        if not archive:
            return
        
        self._set_status(f"Rozpakowywanie: {archive}")
        
        def load():
            try:
                from shared.parsers.folder_parser import FolderParser
                
                parser = FolderParser()
                result = parser.scan_archive(archive)
                
                self.after(0, lambda: self._display_scan_result(result))
                
            except Exception as e:
                logger.error(f"Load archive error: {e}")
                self.after(0, lambda: messagebox.showerror("Błąd", f"Nie udało się wczytać archiwum:\n{e}"))
        
        threading.Thread(target=load, daemon=True).start()
    
    def _display_scan_result(self, result):
        """Wyświetl wyniki skanowania"""
        from shared.parsers.folder_parser import FolderScanResult
        
        if not isinstance(result, FolderScanResult):
            return
        
        # Wyczyść listę
        for item in self.parts_tree.get_children():
            self.parts_tree.delete(item)
        
        self.parts_list.clear()
        
        # Dodaj produkty
        for idx, group in enumerate(result.product_groups):
            # Pomiń grupy bez pliku 2D (nie są produkcyjne)
            if not group.primary_2d:
                logger.debug(f"Pominięto grupę bez pliku 2D: {group.core_name}")
                continue
            
            # Pobierz wymiary z DXF (jeśli możliwe)
            width, height = 0, 0
            if group.primary_2d:
                try:
                    from quotations.nesting.nester import get_dxf_bounding_box
                    dims = get_dxf_bounding_box(str(group.primary_2d.path))
                    if dims:
                        width, height = dims
                except:
                    pass
            
            # Unikalny ID z indeksem
            unique_id = f"part_{idx}_{group.core_name}"
            
            part_data = {
                'id': unique_id,
                'name': group.core_name,
                'material': group.material or 'S235',
                'thickness_mm': group.thickness_mm or 2.0,
                'width_mm': width,
                'height_mm': height,
                'quantity': group.quantity or 1,
                'has_bending': group.has_bending,
                'file_2d': str(group.primary_2d.path) if group.primary_2d else None,
                'file_3d': str(group.primary_3d.path) if group.primary_3d else None,
            }
            
            self.parts_list.append(part_data)
            
            # Dodaj do TreeView
            dims_str = f"{width:.0f} x {height:.0f}" if width and height else "?"
            self.parts_tree.insert('', 'end',
                iid=unique_id,
                values=(
                    part_data['name'],
                    part_data['material'],
                    f"{part_data['thickness_mm']}mm",
                    dims_str,
                    part_data['quantity'],
                    "TAK" if part_data['has_bending'] else "NIE",
                    "✓" if width and height else "⚠️ brak wymiarów"
                )
            )
        
        # Aktualizuj licznik
        self.parts_count_label.configure(text=f"{len(self.parts_list)} pozycji")
        
        # Włącz przyciski kalkulacji
        if self.parts_list:
            self.btn_calculate.configure(state="normal")
            
        
        # Status
        self._set_status(f"Wczytano {len(self.parts_list)} detali z {result.root_path.name}")
        
        # Pokaż błędy
        if result.errors:
            error_msg = "\n".join(result.errors[:5])
            if len(result.errors) > 5:
                error_msg += f"\n... i {len(result.errors) - 5} więcej"
            messagebox.showwarning("Ostrzeżenia", f"Niektóre pliki nie zostały przetworzone:\n\n{error_msg}")
    
    def _on_part_select(self, event):
        """Obsługa selekcji detalu - pokaż miniaturę"""
        selection = self.parts_tree.selection()
        if not selection:
            self._clear_preview()
            return
        
        item_id = selection[0]
        
        # Znajdź detal
        part_data = next((p for p in self.parts_list if p['id'] == item_id), None)
        if not part_data:
            self._clear_preview()
            return
        
        # Aktualizuj info
        self.part_info_name.configure(text=part_data.get('name', 'Brak nazwy'))
        self.part_info_material.configure(
            text=f"Materiał: {part_data.get('material', '?')} {part_data.get('thickness_mm', '?')}mm"
        )
        
        w = part_data.get('width_mm', 0)
        h = part_data.get('height_mm', 0)
        if w and h:
            self.part_info_dims.configure(text=f"Wymiary: {w:.1f} x {h:.1f} mm")
        else:
            self.part_info_dims.configure(text="Wymiary: nieznane")
        
        file_2d = part_data.get('file_2d', '')
        if file_2d:
            self.part_info_file.configure(text=f"Plik: {Path(file_2d).name}")
        else:
            self.part_info_file.configure(text="Plik: brak")
        
        # Generuj miniaturę
        self._generate_thumbnail(part_data)
    
    def _generate_thumbnail(self, part_data: dict):
        """Generuj miniaturę dla detalu"""
        file_2d = part_data.get('file_2d')
        
        if not file_2d or not Path(file_2d).exists():
            self._show_placeholder("Brak pliku DXF")
            return
        
        # Generuj w tle
        def generate():
            try:
                from quotations.utils.dxf_thumbnail import generate_thumbnail
                
                img = generate_thumbnail(
                    file_2d,
                    img_size=(150, 150),
                    bg_color='#1a1a1a',
                    line_color='#8b5cf6'  # Fioletowy accent
                )
                
                if img:
                    # Aktualizuj UI w głównym wątku
                    self.after(0, lambda i=img: self._display_thumbnail(i))
                else:
                    self.after(0, lambda: self._show_placeholder("Błąd generowania"))
                    
            except Exception as e:
                logger.error(f"Thumbnail generation error: {e}")
                self.after(0, lambda: self._show_placeholder("Błąd"))
        
        # Pokaż placeholder podczas ładowania
        self._show_placeholder("Ładowanie...")
        
        import threading
        threading.Thread(target=generate, daemon=True).start()
    
    def _display_thumbnail(self, pil_image):
        """Wyświetl miniaturę w UI"""
        try:
            from PIL import Image, ImageTk
            
            # WAŻNE: dla CTkToplevel musimy podać master, inaczej będzie błąd "pyimage doesn't exist"
            # Użyj wewnętrznego widgetu CTkLabel jako mastera
            photo = ImageTk.PhotoImage(pil_image, master=self.thumbnail_label)
            
            # Przechowaj referencję (żeby GC nie usunął obrazka)
            self._current_thumbnail = photo
            
            # Ustaw obrazek na wewnętrznym Label (nie CTkLabel.configure)
            # CTkLabel ma wewnętrzny _label który jest zwykłym tk.Label
            if hasattr(self.thumbnail_label, '_label'):
                self.thumbnail_label._label.configure(image=photo)
                self.thumbnail_label._label.image = photo  # Dodatkowa referencja
            else:
                # Fallback dla starszych wersji CTk
                self.thumbnail_label.configure(image=photo, text="")
            
        except Exception as e:
            logger.error(f"Display thumbnail error: {e}")
            import traceback
            traceback.print_exc()
            self._show_placeholder_safe("Błąd")
    
    def _show_placeholder(self, text: str):
        """Pokaż placeholder zamiast miniatury"""
        self._show_placeholder_safe(text)
    
    def _show_placeholder_safe(self, text: str):
        """Bezpieczne ustawienie placeholdera"""
        try:
            # Wyczyść obrazek
            if hasattr(self.thumbnail_label, '_label'):
                self.thumbnail_label._label.configure(image='')
                self.thumbnail_label._label.image = None
            
            # Ustaw tekst przez CTkLabel
            self.thumbnail_label.configure(text=text)
            self._current_thumbnail = None
        except Exception:
            pass  # Ignoruj błędy podczas zamykania okna
    
    def _clear_preview(self):
        """Wyczyść podgląd"""
        try:
            self._show_placeholder_safe("Wybierz detal")
            self.part_info_name.configure(text="")
            self.part_info_material.configure(text="")
            self.part_info_dims.configure(text="")
            self.part_info_file.configure(text="")
        except Exception:
            pass
    
    def _add_part_manually(self):
        """Dodaj detal ręcznie"""
        # TODO: Dialog dodawania detalu
        messagebox.showinfo("Info", "Dialog dodawania detalu - w przygotowaniu")
    
    def _remove_selected_part(self):
        """Usuń zaznaczony detal"""
        selection = self.parts_tree.selection()
        if not selection:
            return
        
        for item_id in selection:
            self.parts_tree.delete(item_id)
            self.parts_list = [p for p in self.parts_list if p['id'] != item_id]
        
        self.parts_count_label.configure(text=f"{len(self.parts_list)} pozycji")
        
        if not self.parts_list:
            self.btn_calculate.configure(state="disabled")
    
    def _edit_part(self, event):
        """Edytuj detal (double-click)"""
        selection = self.parts_tree.selection()
        if not selection:
            return
        
        # TODO: Dialog edycji
        messagebox.showinfo("Info", "Dialog edycji detalu - w przygotowaniu")
    
    def _clear_parts(self):
        """Wyczyść listę"""
        if not self.parts_list:
            return
        
        if messagebox.askyesno("Potwierdzenie", "Czy na pewno wyczyścić listę detali?"):
            for item in self.parts_tree.get_children():
                self.parts_tree.delete(item)
            self.parts_list.clear()
            self.parts_count_label.configure(text="0 pozycji")
            self.btn_calculate.configure(state="disabled")
            self.btn_generate.configure(state="disabled")
            self._reset_results()
    
    def _reset_results(self):
        """Resetuj wyniki"""
        self.nesting_result = None
        self.pricing_result = None
        self.nesting_info.configure(text="Wczytaj detale aby uruchomić nesting")
        self.calc_info.configure(text="Uruchom kalkulację aby zobaczyć wyniki")
        self.total_label.configure(text="0.00 PLN")
        self.unit_price_label.configure(text="")
        
    
    def _calculate_with_preview(self):
        """Uruchom kalkulację z podglądem live nestingu"""
        if not self.parts_list:
            messagebox.showwarning("Uwaga", "Brak detali do wyceny")
            return
        
        from quotations.gui.live_nesting import LiveNestingWindow
        
        # Otwórz okno podglądu
        self.live_window = LiveNestingWindow(self, "Nesting i kalkulacja")
        
        # Resetuj flagę anulowania
        self._cancel_requested = False
        self.btn_calculate.configure(state="disabled")
        
        self._set_status("Kalkulowanie z podglądem...")
        
        def run_calculation():
            try:
                from quotations.nesting.nester import Nester, Part, STANDARD_SHEETS, NestingResult, NestedSheet
                from quotations.pricing.calculator import PricingCalculator, PricingInput
                
                # Sprawdź czy anulowano lub okno zamknięte
                if self._cancel_requested or not self.live_window.winfo_exists():
                    self.after(0, self._on_calculation_cancelled)
                    return
                
                self.live_window.after(0, lambda: self.live_window.log("Grupowanie detali..."))
                
                # Grupuj detale po materiale i grubości
                groups = {}
                for part_data in self.parts_list:
                    key = (part_data['material'], part_data['thickness_mm'])
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(part_data)
                
                # Parametry
                nester = Nester()
                calculator = PricingCalculator()
                
                total_cost = 0
                total_parts = 0
                nesting_summary = []
                all_nested_sheets = []
                
                try:
                    margin = float(self.margin_entry.get()) / 100
                except:
                    margin = 0.25
                
                include_setup = self.include_setup_var.get()
                
                # Parametry nestingu
                try:
                    kerf_width = float(self.kerf_entry.get())
                except:
                    kerf_width = 0.2
                
                try:
                    part_spacing = float(self.spacing_entry.get())
                except:
                    part_spacing = 3.0
                
                try:
                    sheet_margin = float(self.sheet_margin_entry.get())
                except:
                    sheet_margin = 10.0
                
                # Rotacje
                rotation_angles = []
                if self.rot_0_var.get():
                    rotation_angles.append(0)
                if self.rot_90_var.get():
                    rotation_angles.append(90)
                if not rotation_angles:
                    rotation_angles = [0]
                
                total_groups = len(groups)
                group_index = 0
                
                for (material, thickness), parts in groups.items():
                    if self._cancel_requested or not self.live_window.winfo_exists():
                        self.after(0, self._on_calculation_cancelled)
                        return
                    
                    group_index += 1
                    progress = group_index / total_groups
                    
                    self.live_window.after(0, lambda m=material, t=thickness: 
                        self.live_window.log(f"Nesting: {m} {t}mm..."))
                    self.live_window.after(0, lambda p=progress: self.live_window.set_progress(p * 0.8))
                    
                    # Przygotuj detale
                    nesting_parts = []
                    for p in parts:
                        if p['width_mm'] > 0 and p['height_mm'] > 0:
                            nesting_parts.append(Part(
                                id=p['id'],
                                name=p['name'],
                                width=p['width_mm'],
                                height=p['height_mm'],
                                quantity=p['quantity'],
                                material=material,
                                thickness_mm=thickness
                            ))
                    
                    if nesting_parts:
                        sheet_format = self.sheet_combo.get()
                        algorithm = self.algorithm_combo.get()
                        
                        if sheet_format == "Auto":
                            sheet = STANDARD_SHEETS["1000x2000"]
                        else:
                            sheet = STANDARD_SHEETS.get(sheet_format, STANDARD_SHEETS["1000x2000"])
                        
                        # Start arkusza w podglądzie
                        self.live_window.after(0, lambda s=sheet, m=sheet_margin:
                            self.live_window.start_nesting(s.width, s.height, m, f"{s.width}x{s.height}"))
                        
                        # Nesting
                        if "Shapely" in algorithm and HAS_SHAPELY:
                            try:
                                from quotations.nesting.nester_shapely import (
                                    ShapelyNester, NestingPart, NestingParams, 
                                    SheetFormat as ShapelySheet, create_rectangle
                                )
                                
                                shapely_params = NestingParams(
                                    kerf_width=kerf_width,
                                    part_spacing=part_spacing,
                                    sheet_margin=sheet_margin,
                                    rotation_angles=rotation_angles,
                                    placement_step=max(2.0, part_spacing / 2)
                                )
                                
                                shapely_parts = []
                                for p in nesting_parts:
                                    rect = create_rectangle(p.id, p.name, p.width, p.height, p.quantity)
                                    if rect:
                                        shapely_parts.append(rect)
                                
                                if shapely_parts:
                                    shapely_sheet = ShapelySheet(sheet.width, sheet.height, sheet_format)
                                    shapely_nester = ShapelyNester(shapely_params, observer=self.live_window)
                                    shapely_result = shapely_nester.nest(shapely_parts, shapely_sheet)
                                    
                                    # Konwertuj wynik
                                    from quotations.nesting.nester import PlacedPart as StdPlacedPart, Part as StdPart
                                    
                                    nested_sheets = []
                                    for sheet_placements in shapely_result.sheets:
                                        placements = []
                                        for placed in sheet_placements:
                                            std_part = StdPart(
                                                id=placed.part.id, name=placed.part.name,
                                                width=placed.part.width, height=placed.part.height,
                                                quantity=1, material=placed.part.material,
                                                thickness_mm=placed.part.thickness_mm
                                            )
                                            std_placed = StdPlacedPart(
                                                part=std_part, x=placed.x, y=placed.y,
                                                rotated=(placed.rotation in [90, 270])
                                            )
                                            std_placed.polygon = placed.polygon
                                            placements.append(std_placed)
                                        nested_sheets.append(NestedSheet(sheet=sheet, placements=placements))
                                    
                                    nest_result = NestingResult(sheets=nested_sheets, unplaced_parts=[])
                                else:
                                    nest_result = nester.nest(nesting_parts, sheet)
                            except Exception as e:
                                logger.warning(f"Shapely failed: {e}, using FFDH")
                                nest_result = nester.nest(nesting_parts, sheet)
                        else:
                            # FFDH - animuj ręcznie
                            nest_result = nester.nest(nesting_parts, sheet)
                            
                            # Animuj wyniki
                            for sheet_result in nest_result.sheets:
                                for placed in sheet_result.placements:
                                    self.live_window.after(0, lambda p=placed:
                                        self.live_window.place_part(
                                            p.x, p.y, p.width, p.height, p.part.name, p.rotated
                                        ))
                                    import time
                                    time.sleep(0.02)
                        
                        all_nested_sheets.extend(nest_result.sheets)
                        
                        nesting_summary.append(
                            f"{material} {thickness}mm: {nest_result.total_sheets} ark. "
                            f"({nest_result.average_utilization*100:.0f}%)"
                        )
                        
                        # Kalkulacja kosztów
                        for p in parts:
                            result = calculator.calculate(
                                PricingInput(
                                    part_name=p['name'],
                                    quantity=p['quantity'],
                                    width_mm=p['width_mm'] or 100,
                                    height_mm=p['height_mm'] or 100,
                                    thickness_mm=thickness,
                                    material_key=material,
                                    bending_count=4 if p['has_bending'] else 0,
                                    sheet_utilization=nest_result.average_utilization
                                ),
                                margin_percent=margin,
                                include_setup=include_setup and total_parts == 0
                            )
                            total_cost += result.total
                            total_parts += p['quantity']
                
                # Zakończ podgląd
                self.live_window.after(0, lambda: self.live_window.finish_nesting())
                self.live_window.after(0, lambda: self.live_window.set_progress(1.0))
                self.live_window.after(0, lambda tc=total_cost, tp=total_parts: 
                    self.live_window.log(f"✅ Gotowe! {tp} detali, {tc:,.2f} PLN"))
                
                # Zapisz wyniki
                if all_nested_sheets:
                    combined_result = NestingResult(sheets=all_nested_sheets, unplaced_parts=[])
                else:
                    combined_result = None
                
                # Aktualizuj UI
                self.after(0, lambda: self._display_calculation_results(
                    total_cost, total_parts, nesting_summary, combined_result
                ))
                
            except Exception as e:
                logger.error(f"Calculation error: {e}")
                import traceback
                traceback.print_exc()
                self.after(0, lambda: self._on_calculation_error(str(e)))
        
        import threading
        threading.Thread(target=run_calculation, daemon=True).start()
    
    def _calculate(self):
        """Uruchom kalkulację"""
        if not self.parts_list:
            messagebox.showwarning("Uwaga", "Brak detali do wyceny")
            return
        
        # Resetuj flagę anulowania i pokaż progress bar
        self._cancel_requested = False
        self.progress_frame.pack(fill="x", padx=15, pady=(5, 15))
        self.progress_bar.set(0)
        self.progress_label.configure(text="0%")
        self.btn_cancel.configure(state="normal")
        self.btn_calculate.configure(state="disabled")
        
        
        self._set_status("Kalkulowanie...")
        
        def update_progress(value: float, text: str = None):
            """Aktualizuj progress bar z głównego wątku"""
            self.after(0, lambda: self._update_progress(value, text))
        
        def calc():
            try:
                from quotations.nesting.nester import Nester, Part, STANDARD_SHEETS, NestingResult, NestedSheet
                from quotations.pricing.calculator import PricingCalculator, PricingInput
                
                # Sprawdź czy anulowano
                if self._cancel_requested:
                    self.after(0, self._on_calculation_cancelled)
                    return
                
                update_progress(0.05, "Grupowanie detali...")
                
                # Grupuj detale po materiale i grubości
                groups = {}
                for part_data in self.parts_list:
                    key = (part_data['material'], part_data['thickness_mm'])
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(part_data)
                
                # Sprawdź czy anulowano
                if self._cancel_requested:
                    self.after(0, self._on_calculation_cancelled)
                    return
                
                # Nesting i kalkulacja dla każdej grupy
                nester = Nester()
                calculator = PricingCalculator()
                
                total_cost = 0
                total_parts = 0
                nesting_summary = []
                
                # Zbierz wszystkie wyniki nestingu
                all_nested_sheets = []
                
                # Pobierz marżę
                try:
                    margin = float(self.margin_entry.get()) / 100
                except:
                    margin = 0.25
                
                include_setup = self.include_setup_var.get()
                
                # Pobierz parametry nestingu z GUI
                try:
                    kerf_width = float(self.kerf_entry.get())
                except:
                    kerf_width = 0.2
                
                try:
                    part_spacing = float(self.spacing_entry.get())
                except:
                    part_spacing = 3.0
                
                try:
                    sheet_margin = float(self.sheet_margin_entry.get())
                except:
                    sheet_margin = 10.0
                
                # Rotacje
                rotation_angles = []
                if self.rot_0_var.get():
                    rotation_angles.append(0)
                if self.rot_90_var.get():
                    rotation_angles.append(90)
                if self.rot_180_var.get():
                    rotation_angles.append(180)
                if self.rot_270_var.get():
                    rotation_angles.append(270)
                
                if not rotation_angles:
                    rotation_angles = [0]  # Minimum jedna rotacja
                
                logger.info(f"Nesting params: kerf={kerf_width}mm, spacing={part_spacing}mm, margin={sheet_margin}mm, rotations={rotation_angles}")
                
                update_progress(0.1, "Rozpoczynam nesting...")
                
                # Licznik grup dla postępu
                total_groups = len(groups)
                group_index = 0
                
                for (material, thickness), parts in groups.items():
                    # Sprawdź czy anulowano
                    if self._cancel_requested:
                        self.after(0, self._on_calculation_cancelled)
                        return
                    
                    group_index += 1
                    base_progress = 0.1 + (group_index - 1) / total_groups * 0.7
                    update_progress(base_progress, f"Nesting: {material} {thickness}mm ({group_index}/{total_groups})")
                    
                    # Przygotuj detale do nestingu
                    nesting_parts = []
                    for p in parts:
                        if p['width_mm'] > 0 and p['height_mm'] > 0:
                            nesting_parts.append(Part(
                                id=p['id'],
                                name=p['name'],
                                width=p['width_mm'],
                                height=p['height_mm'],
                                quantity=p['quantity'],
                                material=material,
                                thickness_mm=thickness
                            ))
                    
                    # Nesting - wybór algorytmu
                    if nesting_parts:
                        sheet_format = self.sheet_combo.get()
                        algorithm = self.algorithm_combo.get()
                        
                        # Określ format arkusza
                        if sheet_format == "Auto":
                            sheet = STANDARD_SHEETS["1000x2000"]  # Default dla auto
                        else:
                            sheet = STANDARD_SHEETS.get(sheet_format, STANDARD_SHEETS["1000x2000"])
                        
                        # Inicjalizacja wyniku
                        nest_result = None
                        shapely_result_raw = None  # Przechowaj surowy wynik Shapely
                        
                        # Wybierz algorytm
                        if "Shapely" in algorithm:
                            # Shapely nesting (True Shape)
                            if not HAS_SHAPELY:
                                logger.warning("Shapely not installed, falling back to FFDH")
                                algorithm = "Szybki (FFDH)"  # Force fallback
                            else:
                                try:
                                    # Sprawdź czy anulowano
                                    if self._cancel_requested:
                                        self.after(0, self._on_calculation_cancelled)
                                        return
                                    
                                    from quotations.nesting.nester_shapely import (
                                        ShapelyNester, NestingPart, NestingParams, SheetFormat as ShapelySheet,
                                        create_part_from_coords, create_rectangle, HAS_SHAPELY as SHAPELY_OK
                                    )
                                    
                                    if not SHAPELY_OK:
                                        raise ImportError("Shapely not installed")
                                    
                                    update_progress(base_progress + 0.1, f"Shapely: wczytywanie DXF...")
                                    
                                    # Parametry z GUI
                                    shapely_params = NestingParams(
                                        kerf_width=kerf_width,
                                        part_spacing=part_spacing,
                                        sheet_margin=sheet_margin,
                                        rotation_angles=rotation_angles,
                                        placement_step=max(2.0, part_spacing / 2)  # Krok proporcjonalny do spacing
                                    )
                                    
                                    # Konwertuj części
                                    shapely_parts = []
                                    for p in nesting_parts:
                                        # Sprawdź czy anulowano
                                        if self._cancel_requested:
                                            self.after(0, self._on_calculation_cancelled)
                                            return
                                        
                                        part_data = next(
                                            (pd for pd in parts if pd['id'] == p.id or pd['name'] == p.name),
                                            None
                                        )
                                        
                                        shapely_poly = None
                                        if part_data and part_data.get('file_2d'):
                                            try:
                                                shapely_nester_temp = ShapelyNester(shapely_params)
                                                shapely_poly_part = shapely_nester_temp.import_from_dxf(part_data['file_2d'])
                                                if shapely_poly_part:
                                                    shapely_poly = shapely_poly_part.polygon
                                            except Exception as e:
                                                logger.debug(f"Shapely DXF import error: {e}")
                                        
                                        # Fallback do prostokąta
                                        if shapely_poly is None:
                                            rect_part = create_rectangle(p.id, p.name, p.width, p.height, p.quantity)
                                            if rect_part:
                                                shapely_parts.append(rect_part)
                                        else:
                                            shapely_parts.append(NestingPart(
                                                id=p.id, name=p.name, polygon=shapely_poly,
                                                quantity=p.quantity, material=p.material,
                                                thickness_mm=p.thickness_mm
                                            ))
                                    
                                    if not shapely_parts:
                                        raise ValueError("No parts could be converted for Shapely nesting")
                                    
                                    update_progress(base_progress + 0.2, f"Shapely: obliczanie rozkładu...")
                                    
                                    shapely_sheet = ShapelySheet(sheet.width, sheet.height, sheet_format)
                                    shapely_nester = ShapelyNester(shapely_params)
                                    shapely_result = shapely_nester.nest(shapely_parts, shapely_sheet)
                                    
                                    # Zachowaj surowy wynik Shapely dla wizualizacji
                                    shapely_result_raw = shapely_result
                                    
                                    # Konwertuj do standardowego NestingResult
                                    from quotations.nesting.nester import NestingResult, NestedSheet, PlacedPart as StdPlacedPart, Part as StdPart
                                    
                                    nested_sheets = []
                                    for sheet_placements in shapely_result.sheets:
                                        placements = []
                                        for placed in sheet_placements:
                                            std_part = StdPart(
                                                id=placed.part.id, name=placed.part.name,
                                                width=placed.part.width, height=placed.part.height,
                                                quantity=1, material=placed.part.material,
                                                thickness_mm=placed.part.thickness_mm
                                            )
                                            # Dodaj informacje o wielokącie do placement
                                            std_placed = StdPlacedPart(
                                                part=std_part, x=placed.x, y=placed.y,
                                                rotated=(placed.rotation in [90, 270])
                                            )
                                            # Zachowaj polygon dla wizualizacji
                                            std_placed.polygon = placed.polygon
                                            std_placed.rotation_angle = placed.rotation
                                            placements.append(std_placed)
                                        nested_sheets.append(NestedSheet(sheet=sheet, placements=placements))
                                    
                                    nest_result = NestingResult(sheets=nested_sheets, unplaced_parts=[])
                                    logger.info(f"Shapely nesting: {shapely_result.total_parts} parts, {shapely_result.average_utilization*100:.1f}% utilization")
                                    
                                except (ImportError, ValueError) as e:
                                    logger.warning(f"Shapely nester not available: {e}, falling back to FFDH")
                                    algorithm = "Szybki (FFDH)"  # Force fallback
                        
                        # Fallback po nieudanym Shapely lub wybór NFP/FFDH
                        if "NFP" in algorithm and nest_result is None:
                            # Zaawansowany nesting (NFP)
                            if not HAS_PYCLIPPER:
                                logger.warning("pyclipper not installed, falling back to FFDH")
                                algorithm = "Szybki (FFDH)"
                            else:
                                try:
                                    from quotations.nesting.nester_advanced import (
                                        AdvancedNester, Part as AdvPart, Polygon, Point, Sheet as AdvSheet
                                    )
                                    from quotations.nesting.dxf_polygon import get_dxf_polygon
                                    
                                    # Konwertuj części do formatu advanced
                                    adv_parts = []
                                    use_real_polygons = True  # Flaga czy udało się pobrać wielokąty
                                    
                                    for p in nesting_parts:
                                        poly = None
                                        
                                        # Próbuj pobrać rzeczywisty wielokąt z DXF
                                        part_data = next(
                                            (pd for pd in parts if pd['id'] == p.id or pd['name'] == p.name),
                                            None
                                        )
                                        
                                        if part_data and part_data.get('file_2d'):
                                            try:
                                                dxf_poly = get_dxf_polygon(part_data['file_2d'])
                                                if dxf_poly and dxf_poly.is_valid:
                                                    # Konwertuj DXFPolygon do Polygon
                                                    verts = [Point(pt.x, pt.y) for pt in dxf_poly.vertices]
                                                    poly = Polygon(verts)
                                                    logger.debug(f"Używam wielokąta DXF dla {p.name}: {len(verts)} wierzchołków")
                                            except Exception as e:
                                                logger.debug(f"Nie udało się pobrać wielokąta dla {p.name}: {e}")
                                        
                                        # Fallback do prostokąta
                                        if poly is None:
                                            poly = Polygon([
                                                Point(0, 0), Point(p.width, 0),
                                                Point(p.width, p.height), Point(0, p.height)
                                            ])
                                            use_real_polygons = False
                                        
                                        adv_parts.append(AdvPart(
                                            id=p.id, name=p.name, polygon=poly,
                                            quantity=p.quantity, material=p.material,
                                            thickness_mm=p.thickness_mm
                                        ))
                                    
                                    if not use_real_polygons:
                                        logger.info("NFP: Niektóre części używają bounding box zamiast rzeczywistych kształtów")
                                    
                                    # Użyj parametrów z GUI
                                    adv_sheet = AdvSheet(
                                        width=sheet.width, height=sheet.height,
                                        margin=sheet_margin, spacing=part_spacing
                                    )
                                    
                                    adv_nester = AdvancedNester()
                                    adv_result = adv_nester.nest(adv_parts, adv_sheet)
                                    
                                    # Konwertuj wynik do standardowego formatu
                                    from quotations.nesting.nester_advanced import convert_to_nesting_result
                                    nest_result = convert_to_nesting_result(adv_result)
                                    
                                except ImportError as e:
                                    logger.warning(f"Advanced nester not available: {e}, falling back to FFDH")
                                    algorithm = "Szybki (FFDH)"
                        
                        # FFDH - fallback lub wybór użytkownika
                        if nest_result is None:
                            # Szybki nesting (FFDH)
                            if sheet_format == "Auto":
                                sheet, nest_result = nester.find_optimal_sheet(nesting_parts)
                            else:
                                nest_result = nester.nest(nesting_parts, sheet)
                        
                        # Dodaj arkusze do zbiorczej listy
                        all_nested_sheets.extend(nest_result.sheets)
                        
                        nesting_summary.append(
                            f"{material} {thickness}mm: {nest_result.total_sheets} ark. "
                            f"({nest_result.average_utilization*100:.0f}%)"
                        )
                        
                        # Kalkulacja dla każdego detalu
                        for p in parts:
                            result = calculator.calculate(
                                PricingInput(
                                    part_name=p['name'],
                                    quantity=p['quantity'],
                                    width_mm=p['width_mm'] or 100,
                                    height_mm=p['height_mm'] or 100,
                                    thickness_mm=thickness,
                                    material_key=material,
                                    bending_count=4 if p['has_bending'] else 0,
                                    sheet_utilization=nest_result.average_utilization
                                ),
                                margin_percent=margin,
                                include_setup=include_setup and total_parts == 0  # Setup raz
                            )
                            
                            total_cost += result.total
                            total_parts += p['quantity']
                    else:
                        # Brak wymiarów - szacunkowa kalkulacja
                        for p in parts:
                            result = calculator.calculate(
                                PricingInput(
                                    part_name=p['name'],
                                    quantity=p['quantity'],
                                    width_mm=100,
                                    height_mm=100,
                                    thickness_mm=thickness,
                                    material_key=material,
                                    bending_count=4 if p['has_bending'] else 0
                                ),
                                margin_percent=margin,
                                include_setup=include_setup and total_parts == 0
                            )
                            total_cost += result.total
                            total_parts += p['quantity']
                
                # Utwórz zbiorczy wynik nestingu
                update_progress(0.9, "Finalizowanie...")
                
                if all_nested_sheets:
                    combined_result = NestingResult(
                        sheets=all_nested_sheets,
                        unplaced_parts=[]
                    )
                else:
                    combined_result = None
                
                update_progress(1.0, "Gotowe!")
                
                # Aktualizuj UI
                self.after(0, lambda: self._display_calculation_results(
                    total_cost, total_parts, nesting_summary, combined_result
                ))
                
            except Exception as e:
                logger.error(f"Calculation error: {e}")
                import traceback
                traceback.print_exc()
                self.after(0, lambda: self._on_calculation_error(str(e)))
        
        self._calculation_thread = threading.Thread(target=calc, daemon=True)
        self._calculation_thread.start()
    
    def _update_progress(self, value: float, text: str = None):
        """Aktualizuj progress bar"""
        try:
            self.progress_bar.set(value)
            self.progress_label.configure(text=f"{int(value * 100)}%")
            if text:
                self._set_status(text)
        except Exception:
            pass
    
    def _cancel_calculation(self):
        """Anuluj bieżące obliczenia"""
        self._cancel_requested = True
        self.btn_cancel.configure(state="disabled", text="Anulowanie...")
        self._set_status("Anulowanie obliczeń...")
    
    def _on_calculation_cancelled(self):
        """Wywołane po anulowaniu obliczeń"""
        self._hide_progress()
        self._set_status("Kalkulacja anulowana")
        self.nesting_info.configure(text="Kalkulacja została anulowana")
    
    def _on_calculation_error(self, error_msg: str):
        """Wywołane po błędzie obliczeń"""
        self._hide_progress()
        messagebox.showerror("Błąd", f"Błąd kalkulacji:\n{error_msg}")
    
    def _hide_progress(self):
        """Ukryj progress bar i przywróć przyciski"""
        try:
            # Sprawdź czy progress_frame jest widoczny
            if hasattr(self, 'progress_frame') and self.progress_frame.winfo_ismapped():
                self.progress_frame.pack_forget()
            
            # Przywróć przycisk anulowania (jeśli istnieje)
            if hasattr(self, 'btn_cancel'):
                try:
                    self.btn_cancel.configure(state="disabled")
                except Exception:
                    pass
            
            # Włącz przycisk kalkulacji
            if hasattr(self, 'btn_calculate'):
                self.btn_calculate.configure(state="normal")
        except Exception as e:
            logger.warning(f"Error hiding progress: {e}")
        
    
    def _display_calculation_results(self, total_cost: float, total_parts: int, nesting_summary: List[str], nesting_result=None):
        """Wyświetl wyniki kalkulacji"""
        # Ukryj progress bar
        self._hide_progress()
        
        # Zapisz wyniki
        self.nesting_result = nesting_result
        self.last_total_cost = total_cost
        self.last_total_parts = total_parts
        self.last_nesting_summary = nesting_summary
        
        # Nesting
        if nesting_summary:
            self.nesting_info.configure(text="\n".join(nesting_summary))
        
        # Kalkulacja
        self.calc_info.configure(text=f"Detali: {total_parts}\nGrupy materiałowe: {len(nesting_summary)}")
        
        # Podsumowanie
        self.total_label.configure(text=f"{total_cost:,.2f} PLN")
        
        unit_price = total_cost / total_parts if total_parts > 0 else 0
        self.unit_price_label.configure(text=f"≈ {unit_price:.2f} PLN/szt średnio")
        
        # Włącz przyciski
        self.btn_generate.configure(state="normal")
        
        self._set_status(f"Kalkulacja zakończona: {total_cost:,.2f} PLN")
    
    def _show_nesting_preview(self):
        """Pokaż podgląd rozkroju"""
        if not self.nesting_result:
            messagebox.showinfo("Info", "Najpierw uruchom kalkulację")
            return
        
        from quotations.gui.nesting_visualizer import NestingVisualizerWindow
        
        preview_window = NestingVisualizerWindow(
            self,
            self.nesting_result,
            "Podgląd rozkroju detali"
        )
        preview_window.grab_set()
    
    def _start_live_nesting(self):
        """Uruchom nesting z podglądem na żywo"""
        if not self.parts_list:
            messagebox.showwarning("Uwaga", "Brak detali do wyceny")
            return
        
        # Otwórz okno live preview
        from quotations.gui.live_nesting import LiveNestingWindow
        
        live_window = LiveNestingWindow(self, "Nesting na żywo")
        
        # Uruchom nesting w tle
        def run_live_nesting():
            try:
                from quotations.nesting.nester import Part, STANDARD_SHEETS
                
                # Pobierz parametry
                sheet_format = self.sheet_combo.get()
                algorithm = self.algorithm_combo.get()
                
                try:
                    kerf_width = float(self.kerf_entry.get())
                except:
                    kerf_width = 0.2
                
                try:
                    part_spacing = float(self.spacing_entry.get())
                except:
                    part_spacing = 3.0
                
                try:
                    sheet_margin = float(self.sheet_margin_entry.get())
                except:
                    sheet_margin = 10.0
                
                # Rotacje
                rotation_angles = []
                if self.rot_0_var.get():
                    rotation_angles.append(0)
                if self.rot_90_var.get():
                    rotation_angles.append(90)
                if self.rot_180_var.get():
                    rotation_angles.append(180)
                if self.rot_270_var.get():
                    rotation_angles.append(270)
                if not rotation_angles:
                    rotation_angles = [0]
                
                # Określ arkusz
                if sheet_format == "Auto":
                    sheet = STANDARD_SHEETS["1000x2000"]
                else:
                    sheet = STANDARD_SHEETS.get(sheet_format, STANDARD_SHEETS["1000x2000"])
                
                # Grupuj detale po materiale i grubości
                groups = {}
                for part_data in self.parts_list:
                    key = (part_data['material'], part_data['thickness_mm'])
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(part_data)
                
                # Uruchom nesting dla pierwszej grupy
                for (material, thickness), parts in groups.items():
                    nesting_parts = []
                    for p in parts:
                        if p['width_mm'] > 0 and p['height_mm'] > 0:
                            nesting_parts.append(Part(
                                id=p['id'],
                                name=p['name'],
                                width=p['width_mm'],
                                height=p['height_mm'],
                                quantity=p['quantity'],
                                material=material,
                                thickness_mm=thickness
                            ))
                    
                    if not nesting_parts:
                        continue
                    
                    live_window.after(0, lambda m=material, t=thickness: 
                        live_window.log(f"📦 Materiał: {m} {t}mm"))
                    
                    # Wybierz algorytm
                    if "Shapely" in algorithm and HAS_SHAPELY:
                        self._run_shapely_live(
                            nesting_parts, sheet, live_window,
                            kerf_width, part_spacing, sheet_margin, rotation_angles
                        )
                    else:
                        self._run_ffdh_live(nesting_parts, sheet, live_window)
                    
                    break  # Tylko pierwsza grupa dla demo
                
            except Exception as e:
                logger.error(f"Live nesting error: {e}")
                import traceback
                traceback.print_exc()
                live_window.after(0, lambda: live_window.log(f"❌ Błąd: {e}"))
        
        import threading
        threading.Thread(target=run_live_nesting, daemon=True).start()
    
    def _run_shapely_live(self, parts, sheet, live_window, kerf_width, part_spacing, sheet_margin, rotation_angles):
        """Uruchom Shapely nesting z live preview"""
        from quotations.nesting.nester_shapely import (
            ShapelyNester, NestingPart, NestingParams, SheetFormat as ShapelySheet,
            create_rectangle, HAS_SHAPELY
        )
        
        shapely_params = NestingParams(
            kerf_width=kerf_width,
            part_spacing=part_spacing,
            sheet_margin=sheet_margin,
            rotation_angles=rotation_angles,
            placement_step=max(2.0, part_spacing / 2)
        )
        
        # Konwertuj części
        shapely_parts = []
        for p in parts:
            rect_part = create_rectangle(p.id, p.name, p.width, p.height, p.quantity)
            if rect_part:
                shapely_parts.append(rect_part)
        
        if not shapely_parts:
            live_window.after(0, lambda: live_window.log("❌ Brak detali do nestingu"))
            return
        
        shapely_sheet = ShapelySheet(sheet.width, sheet.height, f"{sheet.width}x{sheet.height}")
        
        # Nesting z obserwatorem
        nester = ShapelyNester(shapely_params, observer=live_window)
        result = nester.nest(shapely_parts, shapely_sheet)
        
        live_window.after(0, lambda: live_window.log(
            f"✅ Umieszczono {result.total_parts} detali na {result.total_sheets} arkuszach"
        ))
    
    def _run_ffdh_live(self, parts, sheet, live_window):
        """Uruchom FFDH nesting z live preview"""
        from quotations.nesting.nester import Nester
        
        # Start arkusza
        live_window.after(0, lambda: live_window.start_nesting(
            sheet.width, sheet.height, sheet.margin_left, f"{sheet.width}x{sheet.height}"
        ))
        
        nester = Nester()
        result = nester.nest(parts, sheet)
        
        if result.sheets:
            total_parts = sum(len(s.placements) for s in result.sheets)
            shown = 0
            
            for sheet_result in result.sheets:
                for placed in sheet_result.placements:
                    w = placed.part.width if not placed.rotated else placed.part.height
                    h = placed.part.height if not placed.rotated else placed.part.width
                    
                    # Wywołaj w głównym wątku
                    live_window.after(0, lambda x=placed.x, y=placed.y, 
                                     width=w, height=h, name=placed.part.name, 
                                     rot=placed.rotated:
                        live_window.place_part(x, y, width, height, name, rot)
                    )
                    
                    shown += 1
                    progress = shown / total_parts
                    live_window.after(0, lambda p=progress: live_window.set_progress(p))
                    
                    import time
                    time.sleep(0.05)  # Krótka pauza dla animacji
            
            live_window.after(0, lambda: live_window.finish_nesting())
            live_window.after(0, lambda: live_window.log(
                f"✅ Umieszczono {total_parts} detali"
            ))

    def _open_nesting(self):
        """Otwórz pełnoekranowy moduł Nesting z detalami z oferty"""
        from nesting_window import NestingWindow

        # Przygotuj dane detali
        parts_data = []
        for part in self.parts_list:
            part_dict = {
                'name': part.get('name', ''),
                'material': part.get('material', 'NIEZNANY'),
                'thickness_mm': part.get('thickness_mm', 0),
                'quantity': part.get('quantity', 1),
                'width': part.get('width', 0),
                'height': part.get('height', 0),
                'contour': part.get('contour', []),
                'holes': part.get('holes', []),
                'filepath': part.get('filepath', ''),
            }
            parts_data.append(part_dict)

        # Otwórz NestingWindow z kontekstem "quotation"
        nesting_win = NestingWindow(
            self,
            context_type="quotation",
            context_id=None,  # Nowa oferta
            parts_data=parts_data
        )
        nesting_win.state('zoomed')
        nesting_win.attributes('-topmost', True)
        nesting_win.lift()
        nesting_win.focus_force()
        nesting_win.after(100, lambda: nesting_win.attributes('-topmost', False))

    def _generate_quotation(self):
        """Generuj raporty (PDF, Excel, DXF)"""
        if not hasattr(self, 'last_total_cost'):
            messagebox.showinfo("Info", "Najpierw uruchom kalkulację")
            return
        
        # Utwórz QuotationReport z danych
        quotation_report = self._create_quotation_report()
        
        # Otwórz dialog raportów
        from quotations.reports.report_dialog import show_report_dialog
        
        def on_complete(output_dir):
            self._set_status(f"Raporty zapisane w: {output_dir}")
        
        show_report_dialog(self, quotation_report, on_complete)
    
    def _create_quotation_report(self) -> 'QuotationReport':
        """Utwórz QuotationReport z danych kalkulacji"""
        from quotations.reports import (
            QuotationReport, PartReport, NestingReport, SheetReport, CostBreakdown
        )
        
        report = QuotationReport()
        
        # Parametry nestingu
        try:
            report.kerf_width = float(self.kerf_entry.get())
        except:
            report.kerf_width = 0.2
        
        try:
            report.part_spacing = float(self.spacing_entry.get())
        except:
            report.part_spacing = 3.0
        
        try:
            report.sheet_margin = float(self.sheet_margin_entry.get())
        except:
            report.sheet_margin = 10.0
        
        report.algorithm = self.algorithm_combo.get()
        
        # Detale
        for part_data in self.parts_list:
            part_report = PartReport(
                id=part_data.get('id', ''),
                name=part_data.get('name', ''),
                material=part_data.get('material', ''),
                thickness_mm=part_data.get('thickness_mm', 0),
                width_mm=part_data.get('width_mm', 0),
                height_mm=part_data.get('height_mm', 0),
                quantity=part_data.get('quantity', 1),
                has_bending=part_data.get('has_bending', False),
                file_2d=part_data.get('file_2d', ''),
                file_3d=part_data.get('file_3d', '')
            )
            report.parts.append(part_report)
        
        # Nesting
        if self.nesting_result:
            sheets = []
            for i, nested_sheet in enumerate(self.nesting_result.sheets, 1):
                placed_parts = []
                for placed in nested_sheet.placements:
                    placed_parts.append({
                        'name': placed.part.name,
                        'x': placed.x,
                        'y': placed.y,
                        'width': placed.part.width,
                        'height': placed.part.height,
                        'rotated': placed.rotated,
                        'rotation': 90 if placed.rotated else 0
                    })
                
                sheet_report = SheetReport(
                    index=i,
                    width_mm=nested_sheet.sheet.width,
                    height_mm=nested_sheet.sheet.height,
                    format_name=f"{nested_sheet.sheet.width}x{nested_sheet.sheet.height}",
                    material=nested_sheet.placements[0].part.material if nested_sheet.placements else "",
                    thickness_mm=nested_sheet.placements[0].part.thickness_mm if nested_sheet.placements else 0,
                    parts_count=len(nested_sheet.placements),
                    utilization=nested_sheet.utilization,
                    placed_parts=placed_parts
                )
                sheets.append(sheet_report)
            
            report.nesting = NestingReport(sheets=sheets)
        
        # Koszty (szacunkowe rozbicie)
        total = getattr(self, 'last_total_cost', 0)
        try:
            margin_pct = float(self.margin_entry.get()) / 100
        except:
            margin_pct = 0.25
        
        # Rozbicie kosztów (szacunkowe proporcje)
        base_cost = total / (1 + margin_pct)
        
        report.costs = CostBreakdown(
            material_cost=base_cost * 0.50,  # 50% materiał
            cutting_cost=base_cost * 0.35,   # 35% cięcie
            bending_cost=base_cost * 0.10,   # 10% gięcie
            setup_cost=base_cost * 0.03,     # 3% setup
            programming_cost=base_cost * 0.02,  # 2% programowanie
            margin_percent=margin_pct
        )
        report.costs.calculate_total()
        
        return report
    
    def _import_pricing(self):
        """Importuj cenniki z plików XLSX"""
        from quotations.pricing.pricing_tables import get_pricing_tables
        
        # Dialog wyboru typu
        dialog = ctk.CTkToplevel(self)
        dialog.title("Import cenników")
        dialog.geometry("400x250")
        dialog.configure(fg_color=Theme.BG_DARK)
        dialog.transient(self)
        dialog.grab_set()
        
        # Centruj
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 250) // 2
        dialog.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(
            dialog,
            text="Wybierz typ cennika do importu:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=20)
        
        def import_materials():
            filepath = filedialog.askopenfilename(
                title="Wybierz plik z cennikiem materiałów",
                filetypes=[("Excel", "*.xlsx"), ("Wszystkie", "*.*")]
            )
            if filepath:
                tables = get_pricing_tables()
                if tables.load_materials_xlsx(filepath):
                    messagebox.showinfo("Sukces", f"Zaimportowano cennik materiałów z:\n{filepath}")
                else:
                    messagebox.showerror("Błąd", "Nie udało się zaimportować cennika")
            dialog.destroy()
        
        def import_cutting():
            filepath = filedialog.askopenfilename(
                title="Wybierz plik z cennikiem cięcia",
                filetypes=[("Excel", "*.xlsx"), ("Wszystkie", "*.*")]
            )
            if filepath:
                tables = get_pricing_tables()
                if tables.load_cutting_xlsx(filepath):
                    messagebox.showinfo("Sukces", f"Zaimportowano cennik cięcia z:\n{filepath}")
                else:
                    messagebox.showerror("Błąd", "Nie udało się zaimportować cennika")
            dialog.destroy()
        
        ctk.CTkButton(
            dialog,
            text="📦 Cennik materiałów (materials_prices.xlsx)",
            command=import_materials,
            width=350,
            height=40
        ).pack(pady=10)
        
        ctk.CTkButton(
            dialog,
            text="✂️ Cennik cięcia (cutting_prices.xlsx)",
            command=import_cutting,
            width=350,
            height=40
        ).pack(pady=10)
        
        ctk.CTkButton(
            dialog,
            text="Anuluj",
            command=dialog.destroy,
            width=100,
            height=30,
            fg_color=Theme.BG_INPUT
        ).pack(pady=20)


# ============================================================
# INIT
# ============================================================

def create_init_files():
    """Utwórz pliki __init__.py"""
    pass  # Handled separately


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    ctk.set_appearance_mode("dark")
    
    root = ctk.CTk()
    root.withdraw()
    
    window = QuotationWindow()
    window.mainloop()
