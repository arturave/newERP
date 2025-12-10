"""
NewERP - Main Dashboard v2
===========================
Główny ekran systemu ERP skoncentrowany na zarządzaniu zleceniami.

Layout:
┌────────────────────────────────────────────────────────────────────────┐
│  NAVBAR: [Oferty] [Produkty] [Nesting] [Klienci]  + Nowe | Actions     │
├────────────┬───────────────────────────────────────────────────────────┤
│  FILTRY    │  LISTA ZAMÓWIEŃ (tabela)                                  │
│  ----------│  Nr | Klient | Tytuł | Status | Cena | Data | Planowana  │
│  Klient    │                                                           │
│  Status    │                                                           │
│  Data      │                                                           │
│  ----------│                                                           │
│  DASHBOARD │                                                           │
│  Statusy   │                                                           │
│  Terminy   │                                                           │
├────────────┴───────────────────────────────────────────────────────────┤
│  STATUSBAR: System gotowy | Wersja 1.21 Zintegrowana | Połączono       │
└────────────────────────────────────────────────────────────────────────┘
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional, Callable, List, Tuple
from datetime import datetime, timedelta
import threading
import logging

# Opcjonalny import tkcalendar
try:
    from tkcalendar import DateEntry
    HAS_TKCALENDAR = True
except ImportError:
    HAS_TKCALENDAR = False

logger = logging.getLogger(__name__)


# ============================================================
# KOLORY I STYLE
# ============================================================

class Theme:
    """Paleta kolorów - przemysłowy dark mode"""

    # Tła
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_CARD_HOVER = "#252525"
    BG_ACCENT = "#2d2d2d"
    BG_INPUT = "#2d2d2d"

    # Teksty
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#666666"

    # Akcenty - przemysłowe
    ACCENT_PRIMARY = "#3b82f6"    # Niebieski - akcje główne
    ACCENT_SUCCESS = "#22c55e"    # Zielony - sukces, gotowe
    ACCENT_WARNING = "#f59e0b"    # Pomarańczowy - uwaga, w trakcie
    ACCENT_DANGER = "#ef4444"     # Czerwony - błąd, pilne
    ACCENT_INFO = "#06b6d4"       # Cyan - informacje

    # Moduły - unikalne kolory
    COLOR_QUOTATION = "#22c55e"   # Zielony - oferty
    COLOR_ORDER = "#3b82f6"       # Niebieski - zlecenia
    COLOR_PRODUCT = "#06b6d4"     # Cyan - produkty
    COLOR_NESTING = "#f59e0b"     # Pomarańczowy - nesting
    COLOR_CUSTOMER = "#8b5cf6"    # Fioletowy - klienci
    COLOR_DOCUMENT = "#06b6d4"    # Cyan - dokumenty
    COLOR_REPORT = "#ec4899"      # Różowy - raporty

    # Statusy zamówień
    STATUS_COLORS = {
        'wplynelo': '#f59e0b',        # Pomarańczowy
        'potwierdzone': '#3b82f6',    # Niebieski
        'na_planie': '#8b5cf6',       # Fioletowy
        'w_realizacji': '#eab308',    # Żółty
        'gotowe': '#22c55e',          # Zielony
        'wyfakturowane': '#64748b',   # Szary
    }


# ============================================================
# KOMPONENTY
# ============================================================

class NavButton(ctk.CTkButton):
    """Przycisk nawigacyjny w górnym pasku"""

    def __init__(self, parent, text: str, color: str, command: Callable = None, **kwargs):
        super().__init__(
            parent,
            text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=color,
            hover_color=self._darken_color(color),
            corner_radius=6,
            height=36,
            command=command,
            **kwargs
        )

    @staticmethod
    def _darken_color(hex_color: str, factor: float = 0.8) -> str:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darkened = tuple(int(c * factor) for c in rgb)
        return f"#{darkened[0]:02x}{darkened[1]:02x}{darkened[2]:02x}"


class StatusIndicator(ctk.CTkFrame):
    """Wskaźnik statusu z kolorową kropką i liczbą"""

    def __init__(self, parent, label: str, count: int = 0, color: str = "#666666", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.color = color
        self.count = count

        # Kropka
        self.dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(size=14),
            text_color=color,
            width=20
        )
        self.dot.pack(side="left")

        # Etykieta
        self.label = ctk.CTkLabel(
            self,
            text=f"{label}:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_PRIMARY,
            anchor="w"
        )
        self.label.pack(side="left", padx=(0, 5))

        # Liczba
        self.count_label = ctk.CTkLabel(
            self,
            text=str(count),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        )
        self.count_label.pack(side="right")

    def update_count(self, count: int):
        self.count = count
        self.count_label.configure(text=str(count))


class FilterPanel(ctk.CTkFrame):
    """Panel filtrów po lewej stronie"""

    def __init__(self, parent, on_filter_change: Callable = None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=0, **kwargs)

        self.on_filter_change = on_filter_change
        self._setup_ui()

    def _setup_ui(self):
        # Tytuł
        title = ctk.CTkLabel(
            self,
            text="Filtry",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        title.pack(pady=(15, 20), padx=15, anchor="w")

        # Klient
        ctk.CTkLabel(
            self,
            text="Klient:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(padx=15, anchor="w")

        self.client_combo = ctk.CTkComboBox(
            self,
            values=["Wszystkie"],
            width=180,
            height=30,
            font=ctk.CTkFont(size=11)
        )
        self.client_combo.set("Wszystkie")
        self.client_combo.pack(padx=15, pady=(5, 15), anchor="w")

        # Status
        ctk.CTkLabel(
            self,
            text="Status:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(padx=15, anchor="w")

        self.status_combo = ctk.CTkComboBox(
            self,
            values=["Wszystkie", "Wpłynęło", "Potwierdzone", "Na planie",
                   "W realizacji", "Gotowe", "Wyfakturowane"],
            width=180,
            height=30,
            font=ctk.CTkFont(size=11)
        )
        self.status_combo.set("Wszystkie")
        self.status_combo.pack(padx=15, pady=(5, 15), anchor="w")

        # Data od
        ctk.CTkLabel(
            self,
            text="Data od:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(padx=15, anchor="w")

        date_frame_from = ctk.CTkFrame(self, fg_color="transparent")
        date_frame_from.pack(padx=15, pady=(5, 15), anchor="w")

        if HAS_TKCALENDAR:
            self.date_from = DateEntry(
                date_frame_from,
                width=15,
                background=Theme.BG_INPUT,
                foreground='white',
                borderwidth=0,
                date_pattern='dd/mm/yy'
            )
            self.date_from.pack()
        else:
            self.date_from = ctk.CTkEntry(date_frame_from, width=120, height=28)
            self.date_from.insert(0, datetime.now().strftime("%d/%m/%y"))
            self.date_from.pack()

        # Data do
        ctk.CTkLabel(
            self,
            text="Data do:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(padx=15, anchor="w")

        date_frame_to = ctk.CTkFrame(self, fg_color="transparent")
        date_frame_to.pack(padx=15, pady=(5, 15), anchor="w")

        if HAS_TKCALENDAR:
            self.date_to = DateEntry(
                date_frame_to,
                width=15,
                background=Theme.BG_INPUT,
                foreground='white',
                borderwidth=0,
                date_pattern='dd/mm/yy'
            )
            self.date_to.pack()
        else:
            self.date_to = ctk.CTkEntry(date_frame_to, width=120, height=28)
            self.date_to.insert(0, datetime.now().strftime("%d/%m/%y"))
            self.date_to.pack()

        # Szukaj w tytule
        ctk.CTkLabel(
            self,
            text="Szukaj w tytule:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        ).pack(padx=15, anchor="w")

        self.search_entry = ctk.CTkEntry(
            self,
            width=180,
            height=30,
            placeholder_text="",
            font=ctk.CTkFont(size=11)
        )
        self.search_entry.pack(padx=15, pady=(5, 20), anchor="w")

        # Przycisk Zastosuj filtry
        self.btn_apply = ctk.CTkButton(
            self,
            text="Zastosuj filtry",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color="#2563eb",
            height=36,
            width=180,
            command=self._apply_filters
        )
        self.btn_apply.pack(padx=15, pady=(0, 20))

        # Separator
        sep = ctk.CTkFrame(self, height=1, fg_color=Theme.BG_ACCENT)
        sep.pack(fill="x", padx=15, pady=10)

        # Dashboard statusów
        dashboard_title = ctk.CTkLabel(
            self,
            text="Dashboard",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        dashboard_title.pack(pady=(10, 15), padx=15, anchor="w")

        # Statusy zamówień
        status_title = ctk.CTkLabel(
            self,
            text="Statusy zamówień:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        )
        status_title.pack(padx=15, anchor="w", pady=(0, 10))

        self.status_indicators = {}

        statuses = [
            ("Wpłynęło", "wplynelo", Theme.STATUS_COLORS['wplynelo']),
            ("Potwierdzone", "potwierdzone", Theme.STATUS_COLORS['potwierdzone']),
            ("Na planie", "na_planie", Theme.STATUS_COLORS['na_planie']),
            ("W realizacji", "w_realizacji", Theme.STATUS_COLORS['w_realizacji']),
            ("Gotowe", "gotowe", Theme.STATUS_COLORS['gotowe']),
            ("Wyfakturowane", "wyfakturowane", Theme.STATUS_COLORS['wyfakturowane']),
        ]

        for label, key, color in statuses:
            indicator = StatusIndicator(self, label=label, count=0, color=color)
            indicator.pack(padx=15, pady=2, fill="x")
            self.status_indicators[key] = indicator

        # Separator
        sep2 = ctk.CTkFrame(self, height=1, fg_color=Theme.BG_ACCENT)
        sep2.pack(fill="x", padx=15, pady=15)

        # Terminy realizacji
        deadline_title = ctk.CTkLabel(
            self,
            text="Terminy realizacji:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        )
        deadline_title.pack(padx=15, anchor="w", pady=(0, 10))

        self.deadline_indicators = {}

        deadlines = [
            ("Przeterminowane", "overdue", Theme.ACCENT_DANGER),
            ("Zbliżające się (≤2 dni)", "soon", Theme.ACCENT_WARNING),
            ("W terminie", "on_time", Theme.ACCENT_SUCCESS),
        ]

        for label, key, color in deadlines:
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.pack(padx=15, pady=2, fill="x")

            dot = ctk.CTkLabel(frame, text="○", font=ctk.CTkFont(size=10),
                              text_color=color, width=20)
            dot.pack(side="left")

            lbl = ctk.CTkLabel(frame, text=f"{label}:",
                              font=ctk.CTkFont(size=11),
                              text_color=Theme.TEXT_PRIMARY, anchor="w")
            lbl.pack(side="left", padx=(0, 5))

            count_lbl = ctk.CTkLabel(frame, text="0",
                                    font=ctk.CTkFont(size=11, weight="bold"),
                                    text_color=Theme.TEXT_SECONDARY)
            count_lbl.pack(side="right")

            self.deadline_indicators[key] = count_lbl

    def _apply_filters(self):
        """Zastosuj filtry"""
        if self.on_filter_change:
            filters = {
                'client': self.client_combo.get(),
                'status': self.status_combo.get(),
                'search': self.search_entry.get()
            }
            self.on_filter_change(filters)

    def update_dashboard(self, status_counts: Dict[str, int], deadline_counts: Dict[str, int]):
        """Aktualizuj dashboard"""
        for key, indicator in self.status_indicators.items():
            count = status_counts.get(key, 0)
            indicator.update_count(count)

        for key, label in self.deadline_indicators.items():
            count = deadline_counts.get(key, 0)
            label.configure(text=str(count))

    def set_clients(self, clients: List[str]):
        """Ustaw listę klientów"""
        self.client_combo.configure(values=["Wszystkie"] + clients)


# ============================================================
# GŁÓWNY DASHBOARD
# ============================================================

class MainDashboard(ctk.CTk):
    """
    Główny ekran systemu NewERP - skoncentrowany na zarządzaniu zleceniami.
    """

    def __init__(self):
        super().__init__()

        # Konfiguracja okna
        self.title("System Zarządzania Produkcją - Wersja Zintegrowana 1.21")

        # Pełny ekran
        self.state('zoomed')  # Windows
        self.minsize(1200, 700)

        # Dark mode
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=Theme.BG_DARK)

        # Stan
        self.orders_data = []

        # Build UI
        self._setup_ui()

        # Load data
        self.after(100, self._load_data)

        # Auto-refresh co 60s
        self._schedule_refresh()

    def _setup_ui(self):
        """Buduj interfejs"""

        # Grid główny
        self.grid_columnconfigure(0, weight=0, minsize=220)  # Lewy panel
        self.grid_columnconfigure(1, weight=1)               # Główna tabela
        self.grid_rowconfigure(1, weight=1)

        # === NAVBAR (górny pasek) ===
        self._setup_navbar()

        # === FILTER PANEL (lewy) ===
        self.filter_panel = FilterPanel(
            self,
            on_filter_change=self._on_filter_change
        )
        self.filter_panel.grid(row=1, column=0, sticky="nsew")

        # === ORDERS TABLE (główny) ===
        self._setup_orders_table()

        # === STATUSBAR ===
        self._setup_statusbar()

    def _setup_navbar(self):
        """Górny pasek nawigacji"""
        navbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        navbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        navbar.grid_propagate(False)

        # Logo
        logo_frame = ctk.CTkFrame(navbar, fg_color="transparent")
        logo_frame.pack(side="left", padx=15, pady=10)

        logo_icon = ctk.CTkLabel(
            logo_frame,
            text="◼",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        logo_icon.pack(side="left")

        logo_text = ctk.CTkLabel(
            logo_frame,
            text=" AVE",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        logo_text.pack(side="left")

        # Moduły nawigacyjne
        modules_frame = ctk.CTkFrame(navbar, fg_color="transparent")
        modules_frame.pack(side="left", padx=20, pady=10)

        # Przyciski modułów
        self.btn_offers = NavButton(
            modules_frame, text="≡ Oferty",
            color=Theme.COLOR_QUOTATION,
            command=lambda: self._open_module('quotations'),
            width=90
        )
        self.btn_offers.pack(side="left", padx=3)

        self.btn_products = NavButton(
            modules_frame, text="≡ Produkty",
            color=Theme.COLOR_PRODUCT,
            command=lambda: self._open_module('products'),
            width=95
        )
        self.btn_products.pack(side="left", padx=3)

        self.btn_nesting = NavButton(
            modules_frame, text="⇄ Nesting",
            color=Theme.COLOR_NESTING,
            command=lambda: self._open_module('nesting'),
            width=90
        )
        self.btn_nesting.pack(side="left", padx=3)

        self.btn_about = ctk.CTkButton(
            modules_frame,
            text="ⓘ O systemie",
            font=ctk.CTkFont(size=11),
            fg_color=Theme.BG_ACCENT,
            hover_color=Theme.BG_CARD_HOVER,
            corner_radius=6,
            height=36,
            width=95,
            command=self._show_about
        )
        self.btn_about.pack(side="left", padx=3)

        # Tytuł systemu (środek)
        title_frame = ctk.CTkFrame(navbar, fg_color="transparent")
        title_frame.pack(side="left", padx=30, pady=10, expand=True)

        title = ctk.CTkLabel(
            title_frame,
            text="System Zarządzania Produkcją - Laser/Prasa",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        title.pack()

        # Przyciski akcji (prawa strona)
        actions_frame = ctk.CTkFrame(navbar, fg_color="transparent")
        actions_frame.pack(side="right", padx=15, pady=10)

        # Nowe zamówienie
        self.btn_new_order = ctk.CTkButton(
            actions_frame,
            text="+ Nowe zamówienie",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Theme.ACCENT_SUCCESS,
            hover_color="#1ea54d",
            corner_radius=6,
            height=36,
            width=150,
            command=lambda: self._open_module('orders', action='new')
        )
        self.btn_new_order.pack(side="left", padx=5)

        # Generuj WZ
        self.btn_wz = ctk.CTkButton(
            actions_frame,
            text="✎ Generuj WZ",
            font=ctk.CTkFont(size=11),
            fg_color=Theme.BG_ACCENT,
            hover_color=Theme.BG_CARD_HOVER,
            corner_radius=6,
            height=36,
            width=100,
            command=self._generate_wz
        )
        self.btn_wz.pack(side="left", padx=3)

        # Klienci
        self.btn_clients = ctk.CTkButton(
            actions_frame,
            text="👥 Klienci",
            font=ctk.CTkFont(size=11),
            fg_color=Theme.BG_ACCENT,
            hover_color=Theme.BG_CARD_HOVER,
            corner_radius=6,
            height=36,
            width=80,
            command=lambda: self._open_module('customers')
        )
        self.btn_clients.pack(side="left", padx=3)

        # Raporty
        self.btn_reports = ctk.CTkButton(
            actions_frame,
            text="📊 Raporty",
            font=ctk.CTkFont(size=11),
            fg_color=Theme.BG_ACCENT,
            hover_color=Theme.BG_CARD_HOVER,
            corner_radius=6,
            height=36,
            width=80,
            command=lambda: self._open_module('reports')
        )
        self.btn_reports.pack(side="left", padx=3)

        # Odśwież
        self.btn_refresh = ctk.CTkButton(
            actions_frame,
            text="⟳ Odśwież",
            font=ctk.CTkFont(size=11),
            fg_color=Theme.BG_ACCENT,
            hover_color=Theme.BG_CARD_HOVER,
            corner_radius=6,
            height=36,
            width=80,
            command=self._load_data
        )
        self.btn_refresh.pack(side="left", padx=3)

        # Ustawienia
        self.btn_settings = ctk.CTkButton(
            actions_frame,
            text="⚙ Ustawienia",
            font=ctk.CTkFont(size=11),
            fg_color=Theme.BG_ACCENT,
            hover_color=Theme.BG_CARD_HOVER,
            corner_radius=6,
            height=36,
            width=95,
            command=self._show_settings
        )
        self.btn_settings.pack(side="left", padx=3)

    def _setup_orders_table(self):
        """Tabela zamówień"""
        main_frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        main_frame.grid(row=1, column=1, sticky="nsew", padx=(0, 10), pady=10)

        # Nagłówek tabeli
        header = ctk.CTkFrame(main_frame, fg_color="transparent", height=50)
        header.pack(fill="x", padx=15, pady=(15, 10))

        title = ctk.CTkLabel(
            header,
            text="Lista zamówień",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        title.pack(side="left")

        # Przyciski eksportu
        export_frame = ctk.CTkFrame(header, fg_color="transparent")
        export_frame.pack(side="right")

        btn_excel = ctk.CTkButton(
            export_frame, text="📊 Excel",
            font=ctk.CTkFont(size=10),
            fg_color=Theme.BG_ACCENT,
            hover_color="#1d6f42",
            width=70, height=28,
            command=lambda: self._export('excel')
        )
        btn_excel.pack(side="left", padx=2)

        btn_word = ctk.CTkButton(
            export_frame, text="📝 Word",
            font=ctk.CTkFont(size=10),
            fg_color=Theme.BG_ACCENT,
            hover_color="#2b579a",
            width=70, height=28,
            command=lambda: self._export('word')
        )
        btn_word.pack(side="left", padx=2)

        btn_pdf = ctk.CTkButton(
            export_frame, text="📄 PDF",
            font=ctk.CTkFont(size=10),
            fg_color=Theme.BG_ACCENT,
            hover_color="#c13b2e",
            width=70, height=28,
            command=lambda: self._export('pdf')
        )
        btn_pdf.pack(side="left", padx=2)

        # Tabela
        table_frame = ctk.CTkFrame(main_frame, fg_color=Theme.BG_INPUT)
        table_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Style - biały tekst w liście zamówień
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Orders.Treeview",
            background=Theme.BG_INPUT,
            foreground="white",  # Biały kolor tekstu
            fieldbackground=Theme.BG_INPUT,
            rowheight=35,
            font=('Segoe UI', 10)
        )
        style.configure(
            "Orders.Treeview.Heading",
            background="#1e3a5f",
            foreground="white",  # Biały kolor nagłówków
            font=('Segoe UI', 10, 'bold'),
            relief="flat"
        )
        style.map(
            "Orders.Treeview",
            background=[("selected", Theme.ACCENT_PRIMARY)],
            foreground=[("selected", "white")]
        )

        columns = ('nr_procesu', 'faktura', 'klient', 'tytul', 'status', 'cena',
                  'data_wplywu', 'planowana', 'zakonczona')

        self.orders_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show='headings',
            style="Orders.Treeview"
        )

        # Naglowki
        self.orders_tree.heading('nr_procesu', text='Nr procesu')
        self.orders_tree.heading('faktura', text='FV')
        self.orders_tree.heading('klient', text='Klient')
        self.orders_tree.heading('tytul', text='Tytul')
        self.orders_tree.heading('status', text='Status')
        self.orders_tree.heading('cena', text='Cena [PLN]')
        self.orders_tree.heading('data_wplywu', text='Data wplywu')
        self.orders_tree.heading('planowana', text='Planowana')
        self.orders_tree.heading('zakonczona', text='Zakonczona')

        # Szerokosci
        self.orders_tree.column('nr_procesu', width=100, anchor='center')
        self.orders_tree.column('faktura', width=40, anchor='center')
        self.orders_tree.column('klient', width=180)
        self.orders_tree.column('tytul', width=230)
        self.orders_tree.column('status', width=100, anchor='center')
        self.orders_tree.column('cena', width=100, anchor='e')
        self.orders_tree.column('data_wplywu', width=100, anchor='center')
        self.orders_tree.column('planowana', width=100, anchor='center')
        self.orders_tree.column('zakonczona', width=100, anchor='center')

        # Tag tylko dla niewyfakturowanych - czerwony
        # Wyfakturowane i pozostale wiersze maja domyslny bialy kolor
        self.orders_tree.tag_configure('not_invoiced', foreground=Theme.ACCENT_DANGER)

        # Scrollbary
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.orders_tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.orders_tree.xview)
        self.orders_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Układ
        self.orders_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        # Eventy
        self.orders_tree.bind('<Double-1>', self._on_order_double_click)
        self.orders_tree.bind('<Button-3>', self._show_context_menu)

    def _setup_statusbar(self):
        """Pasek statusu"""
        statusbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=30)
        statusbar.grid(row=2, column=0, columnspan=2, sticky="ew")
        statusbar.grid_propagate(False)

        # Lewy tekst
        self.status_left = ctk.CTkLabel(
            statusbar,
            text="System gotowy | Wszystkie moduły załadowane | Wersja 1.21 Zintegrowana",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY
        )
        self.status_left.pack(side="left", padx=15, pady=5)

        # Prawy tekst (połączenie)
        self.status_right = ctk.CTkLabel(
            statusbar,
            text="● Połączono",
            font=ctk.CTkFont(size=10),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.status_right.pack(side="right", padx=15, pady=5)

    # ============================================================
    # DATA LOADING
    # ============================================================

    def _load_data(self):
        """Załaduj dane"""
        logger.info("[MainDashboard] Loading data...")

        def load():
            try:
                orders_from_db = []
                orders_from_json = []

                # 1. Próba ładowania z Supabase
                try:
                    from orders.repository import OrderRepository
                    from core.supabase_client import get_supabase_client

                    client = get_supabase_client()
                    repo = OrderRepository(client)
                    orders_from_db = repo.get_all(limit=100)
                    logger.info(f"[MainDashboard] Loaded {len(orders_from_db)} orders from Supabase")

                except ImportError as e:
                    logger.warning(f"[MainDashboard] OrderRepository not available: {e}")
                except Exception as e:
                    logger.warning(f"[MainDashboard] Supabase error: {e}")

                # 2. Fallback - ładowanie z lokalnych plików JSON
                from pathlib import Path
                import json

                orders_dir = Path("data/orders")
                if orders_dir.exists():
                    for json_file in orders_dir.glob("*.json"):
                        try:
                            with open(json_file, 'r', encoding='utf-8') as f:
                                order_data = json.load(f)
                                orders_from_json.append(order_data)
                        except Exception as e:
                            logger.error(f"[MainDashboard] Error loading {json_file}: {e}")

                    logger.info(f"[MainDashboard] Loaded {len(orders_from_json)} orders from JSON files")

                # 3. Połącz dane (Supabase ma pierwszeństwo)
                seen_ids = set()
                all_orders = []

                for order in orders_from_db:
                    order_id = order.get('id')
                    if order_id and order_id not in seen_ids:
                        seen_ids.add(order_id)
                        all_orders.append(order)

                for order in orders_from_json:
                    order_id = order.get('id')
                    if order_id and order_id not in seen_ids:
                        seen_ids.add(order_id)
                        all_orders.append(order)

                # Sortuj po dacie utworzenia (najnowsze pierwsze)
                all_orders.sort(
                    key=lambda x: x.get('created_at', x.get('updated_at', '')),
                    reverse=True
                )

                self.orders_data = all_orders
                logger.info(f"[MainDashboard] Total orders: {len(self.orders_data)}")

                # Aktualizuj UI w głównym wątku
                self.after(0, self._update_ui)

            except Exception as e:
                logger.error(f"[MainDashboard] Load data error: {e}")
                import traceback
                traceback.print_exc()
                self.after(0, lambda: self._show_error(f"Błąd ładowania danych: {e}"))

        threading.Thread(target=load, daemon=True).start()

    def _update_ui(self):
        """Aktualizuj UI po załadowaniu danych"""
        logger.debug(f"[MainDashboard] Updating UI with {len(self.orders_data)} orders")

        # Wyczyść tabelę
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)

        # Mapowanie statusów
        status_map = {
            'new': 'Nowe',
            'draft': 'Szkic',
            'in_progress': 'W realizacji',
            'nesting_done': 'Nesting',
            'production': 'Produkcja',
            'completed': 'Gotowe',
            'cancelled': 'Anulowane',
            # Stare statusy
            'wplynelo': 'Wpłynęło',
            'potwierdzone': 'Potwierdzone',
            'na_planie': 'Na planie',
            'w_realizacji': 'W realizacji',
            'gotowe': 'Gotowe',
            'wyfakturowane': 'Wyfakturowane'
        }

        # Liczniki statusów
        status_counts = {
            'wplynelo': 0,
            'potwierdzone': 0,
            'na_planie': 0,
            'w_realizacji': 0,
            'gotowe': 0,
            'wyfakturowane': 0
        }

        # Dodaj zamówienia
        for order in self.orders_data:
            # Pobierz dane
            order_id = order.get('id', '')[:8] if order.get('id') else ''
            name = order.get('name', order.get('tytul', ''))
            client = order.get('client', order.get('klient', ''))
            status_raw = order.get('status', 'new')
            status_display = status_map.get(status_raw, status_raw)

            # Koszt
            total_cost = 0
            if order.get('cost_result'):
                total_cost = order['cost_result'].get('total_cost', 0)
            elif order.get('total_cost'):
                total_cost = order['total_cost']
            elif order.get('cena'):
                total_cost = order['cena']

            # Daty
            date_in = order.get('date_in', order.get('data_wplywu', ''))
            date_due = order.get('date_due', order.get('planowana', ''))
            date_end = order.get('zakonczona', '')

            # Liczenie statusów
            if status_raw in ['new', 'wplynelo']:
                status_counts['wplynelo'] += 1
            elif status_raw in ['potwierdzone']:
                status_counts['potwierdzone'] += 1
            elif status_raw in ['na_planie', 'nesting_done']:
                status_counts['na_planie'] += 1
            elif status_raw in ['in_progress', 'w_realizacji', 'production']:
                status_counts['w_realizacji'] += 1
            elif status_raw in ['completed', 'gotowe']:
                status_counts['gotowe'] += 1

            # Status faktury - tylko niewyfakturowane sa czerwone
            is_invoiced = order.get('invoiced', False) or order.get('invoice_sent', False)
            invoice_indicator = "\u25cf" if is_invoiced else "\u25cb"  # Pelne/puste kolko
            row_tags = () if is_invoiced else ('not_invoiced',)

            self.orders_tree.insert('', 'end', iid=order.get('id'), values=(
                order_id,
                invoice_indicator,
                client,
                name,
                status_display,
                f"{total_cost:,.2f}" if total_cost else "-",
                date_in[:10] if date_in else '',
                date_due[:10] if date_due else '',
                date_end[:10] if date_end else ''
            ), tags=row_tags)

        # Aktualizuj dashboard
        deadline_counts = {
            'overdue': 0,
            'soon': 0,
            'on_time': len(self.orders_data)
        }

        self.filter_panel.update_dashboard(status_counts, deadline_counts)

        # Status bar
        self.status_left.configure(
            text=f"System gotowy | {len(self.orders_data)} zamówień | Wersja 1.21 Zintegrowana"
        )

    def _schedule_refresh(self):
        """Zaplanuj auto-refresh"""
        self.after(60000, self._auto_refresh)

    def _auto_refresh(self):
        """Auto-refresh"""
        self._load_data()
        self._schedule_refresh()

    # ============================================================
    # NAVIGATION
    # ============================================================

    def _open_module(self, module: str, action: str = None):
        """Otwórz moduł"""
        logger.info(f"Opening module: {module}, action: {action}")

        window = None

        if module == 'products':
            from products.gui import ProductsWindow
            window = ProductsWindow(self)

        elif module == 'customers':
            from core import get_supabase_client
            from customers.service import CustomerService
            from customers.gui import CustomersWindow

            client = get_supabase_client()
            service = CustomerService(client)
            window = CustomersWindow(self, service)

        elif module == 'quotations':
            from quotations.gui.quotation_window import QuotationWindow
            window = QuotationWindow(self)

        elif module == 'nesting':
            self._open_nesting_fullscreen()
            return

        elif module == 'orders':
            if action == 'new':
                self._create_new_order()
            else:
                self._show_coming_soon("Moduł Zamówień")
            return

        elif module == 'reports':
            self._show_coming_soon("Raporty")
            return

        if window:
            # Wymuś pierwszy plan
            window.attributes('-topmost', True)
            window.lift()
            window.focus_force()
            window.after(100, lambda: window.attributes('-topmost', False))

    def _open_nesting_fullscreen(self):
        """Otwórz moduł Nesting w trybie pełnoekranowym"""
        from nesting_window import NestingWindow

        nesting_win = NestingWindow(self)
        nesting_win.state('zoomed')
        # Wymuś pierwszy plan
        nesting_win.attributes('-topmost', True)
        nesting_win.lift()
        nesting_win.focus_force()
        nesting_win.after(100, lambda: nesting_win.attributes('-topmost', False))

    def _create_new_order(self):
        """Utwórz nowe zamówienie"""
        from orders.gui.order_window import OrderWindow

        logger.info("[MainDashboard] Creating new order")

        def on_order_saved(order_data):
            """Callback po zapisaniu zamówienia"""
            logger.info(f"[MainDashboard] Order saved callback: {order_data.get('id')}")
            self._load_data()  # Odśwież listę

        order_win = OrderWindow(self, on_save_callback=on_order_saved)
        order_win.attributes('-topmost', True)
        order_win.lift()
        order_win.focus_force()
        order_win.after(100, lambda: order_win.attributes('-topmost', False))

    def _generate_wz(self):
        """Generuj dokument WZ"""
        messagebox.showinfo("Generuj WZ", "Funkcja generowania WZ - w przygotowaniu")

    def _show_settings(self):
        """Pokaż ustawienia kosztów"""
        from orders.gui.settings_dialog import CostSettingsDialog

        def on_settings_saved(settings):
            logger.info(f"[MainDashboard] Cost settings saved: {settings}")

        settings_dialog = CostSettingsDialog(self, on_save=on_settings_saved)
        settings_dialog.attributes('-topmost', True)
        settings_dialog.lift()
        settings_dialog.focus_force()
        settings_dialog.after(100, lambda: settings_dialog.attributes('-topmost', False))

    def _show_about(self):
        """Pokaż informacje o systemie"""
        about_text = """
System Zarządzania Produkcją
Wersja 1.21 Zintegrowana

NewERP - System dla cięcia laserowego

Moduły:
• Oferty i wyceny
• Produkty i katalog CAD
• Nesting 2D
• Klienci
• Zamówienia (w przygotowaniu)
• Raporty (w przygotowaniu)

© 2024-2025 AVE
        """
        messagebox.showinfo("O systemie", about_text.strip())

    def _show_coming_soon(self, module_name: str):
        """Pokaż info o module w przygotowaniu"""
        messagebox.showinfo(
            "W przygotowaniu",
            f"Moduł '{module_name}' jest w trakcie implementacji.\n\n"
            "Dostępne moduły:\n"
            "• Oferty ✓\n"
            "• Produkty ✓\n"
            "• Nesting ✓\n"
            "• Klienci ✓"
        )

    def _show_error(self, message: str):
        """Pokaż błąd"""
        messagebox.showerror("Błąd", message)

    # ============================================================
    # TABLE EVENTS
    # ============================================================

    def _on_filter_change(self, filters: Dict):
        """Obsługa zmiany filtrów"""
        logger.info(f"Filters changed: {filters}")
        # TODO: Filtrowanie tabeli

    def _on_order_double_click(self, event):
        """Obsługa podwójnego kliknięcia na zamówienie"""
        selection = self.orders_tree.selection()
        if not selection:
            return

        order_id = selection[0]  # iid to pełne ID zamówienia
        logger.info(f"[MainDashboard] Opening order: {order_id}")

        # Znajdź dane zamówienia
        order_data = None
        for order in self.orders_data:
            if order.get('id') == order_id:
                order_data = order
                break

        if not order_data:
            logger.warning(f"[MainDashboard] Order not found: {order_id}")
            return

        # Otwórz okno zamówienia
        from orders.gui.order_window import OrderWindow

        def on_order_saved(saved_data):
            logger.info(f"[MainDashboard] Order updated: {saved_data.get('id')}")
            self._load_data()

        order_win = OrderWindow(
            self,
            order_id=order_id,
            order_data=order_data,
            on_save_callback=on_order_saved
        )
        order_win.attributes('-topmost', True)
        order_win.lift()
        order_win.focus_force()
        order_win.after(100, lambda: order_win.attributes('-topmost', False))

    def _show_context_menu(self, event):
        """Pokaż menu kontekstowe dla zamówienia"""
        # Zaznacz wiersz pod kursorem
        item = self.orders_tree.identify_row(event.y)
        if item:
            self.orders_tree.selection_set(item)

        # Utwórz menu kontekstowe
        menu = tk.Menu(self, tearoff=0, bg=Theme.BG_CARD, fg="white",
                      activebackground=Theme.ACCENT_PRIMARY, activeforeground="white",
                      font=('Segoe UI', 10))

        # Nowe zamówienie
        menu.add_command(label="➕ Nowe zamówienie", command=self._open_new_order)
        menu.add_separator()

        # Opcje wymagające zaznaczenia
        if item:
            menu.add_command(label="📝 Edytuj", command=lambda: self._edit_order(item))
            menu.add_command(label="📋 Duplikuj", command=lambda: self._duplicate_order(item))
            menu.add_separator()

            # Podmenu "Oznacz jako"
            status_menu = tk.Menu(menu, tearoff=0, bg=Theme.BG_CARD, fg="white",
                                 activebackground=Theme.ACCENT_PRIMARY, activeforeground="white",
                                 font=('Segoe UI', 10))
            status_menu.add_command(label="📥 Otrzymane (RECEIVED)",
                                   command=lambda: self._change_order_status(item, 'RECEIVED'))
            status_menu.add_command(label="⏳ W trakcie (IN_PROGRESS)",
                                   command=lambda: self._change_order_status(item, 'IN_PROGRESS'))
            status_menu.add_command(label="✅ Zakończone (COMPLETED)",
                                   command=lambda: self._change_order_status(item, 'COMPLETED'))
            status_menu.add_command(label="📦 Wysłane (SHIPPED)",
                                   command=lambda: self._change_order_status(item, 'SHIPPED'))
            status_menu.add_command(label="❌ Anulowane (CANCELLED)",
                                   command=lambda: self._change_order_status(item, 'CANCELLED'))
            menu.add_cascade(label="🏷️ Oznacz jako", menu=status_menu)

            menu.add_separator()
            menu.add_command(label="🗑️ Usuń", command=lambda: self._delete_order(item),
                           foreground=Theme.ACCENT_DANGER)
        else:
            # Opcje gdy brak zaznaczenia
            menu.add_command(label="📝 Edytuj", state="disabled")
            menu.add_command(label="📋 Duplikuj", state="disabled")
            menu.add_command(label="🏷️ Oznacz jako", state="disabled")
            menu.add_separator()
            menu.add_command(label="🗑️ Usuń", state="disabled")

        menu.add_separator()
        menu.add_command(label="🔄 Odśwież listę", command=self._load_data)

        # Pokaż menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _edit_order(self, item):
        """Edytuj zamówienie (otwórz w oknie)"""
        self._on_order_double_click(None)

    def _duplicate_order(self, item):
        """Duplikuj zamówienie"""
        selection = self.orders_tree.selection()
        if not selection:
            return

        # Pobierz dane zamówienia
        values = self.orders_tree.item(selection[0], 'values')
        order_id = self.orders_tree.item(selection[0], 'tags')

        if order_id:
            order_id = order_id[0] if order_id else None

        try:
            from orders.repository import OrderRepository
            from core.supabase_client import get_supabase_client
            import uuid

            client = get_supabase_client()
            repo = OrderRepository(client)

            # Pobierz oryginalne zamówienie
            if order_id:
                original = repo.get_by_id(order_id)
                if original:
                    # Stwórz kopię z nowym ID i nazwą
                    new_order = original.copy()
                    new_order['id'] = str(uuid.uuid4())
                    new_order['name'] = f"{original.get('name', 'Zamówienie')} (kopia)"
                    new_order['title'] = new_order['name']
                    new_order['status'] = 'RECEIVED'

                    # Zapisz kopię
                    saved = repo.save(new_order)
                    if saved:
                        messagebox.showinfo("Sukces", f"Utworzono kopię: {new_order['name']}")
                        self._load_data()
                        return

            messagebox.showerror("Błąd", "Nie można zduplikować zamówienia")

        except Exception as e:
            logger.error(f"[MainDashboard] Error duplicating order: {e}")
            messagebox.showerror("Błąd", f"Błąd duplikowania: {e}")

    def _change_order_status(self, item, new_status: str):
        """Zmień status zamówienia"""
        selection = self.orders_tree.selection()
        if not selection:
            return

        order_id = self.orders_tree.item(selection[0], 'tags')
        if order_id:
            order_id = order_id[0] if order_id else None

        try:
            from orders.repository import OrderRepository
            from core.supabase_client import get_supabase_client

            client = get_supabase_client()
            repo = OrderRepository(client)

            if order_id:
                # Aktualizuj status
                success = repo.update_status(order_id, new_status)
                if success:
                    logger.info(f"[MainDashboard] Order {order_id} status changed to {new_status}")
                    self._load_data()
                    return

            messagebox.showerror("Błąd", "Nie można zmienić statusu")

        except Exception as e:
            logger.error(f"[MainDashboard] Error changing status: {e}")
            messagebox.showerror("Błąd", f"Błąd zmiany statusu: {e}")

    def _delete_order(self, item):
        """Usuń zamówienie"""
        selection = self.orders_tree.selection()
        if not selection:
            return

        values = self.orders_tree.item(selection[0], 'values')
        order_name = values[3] if len(values) > 3 else "zamówienie"

        # Potwierdzenie
        if not messagebox.askyesno("Potwierdź usunięcie",
                                   f"Czy na pewno chcesz usunąć zamówienie:\n\n{order_name}?\n\n"
                                   "Ta operacja jest nieodwracalna."):
            return

        order_id = self.orders_tree.item(selection[0], 'tags')
        if order_id:
            order_id = order_id[0] if order_id else None

        try:
            from orders.repository import OrderRepository
            from core.supabase_client import get_supabase_client

            client = get_supabase_client()
            repo = OrderRepository(client)

            if order_id:
                success = repo.delete(order_id)
                if success:
                    logger.info(f"[MainDashboard] Order {order_id} deleted")
                    messagebox.showinfo("Sukces", f"Zamówienie '{order_name}' zostało usunięte")
                    self._load_data()
                    return

            messagebox.showerror("Błąd", "Nie można usunąć zamówienia")

        except Exception as e:
            logger.error(f"[MainDashboard] Error deleting order: {e}")
            messagebox.showerror("Błąd", f"Błąd usuwania: {e}")

    def _export(self, format_type: str):
        """Eksportuj dane"""
        messagebox.showinfo("Eksport", f"Eksport do {format_type.upper()} - w przygotowaniu")


# ============================================================
# ENTRY POINT
# ============================================================

def run_dashboard():
    """Uruchom dashboard"""
    app = MainDashboard()
    app.mainloop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_dashboard()
