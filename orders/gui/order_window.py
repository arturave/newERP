"""
NewERP - Order Window
=====================
Okno zarządzania zamówieniem z integracją Nesting.

Changelog:
- Fix: Focus okna po dodaniu folderu
- Fix: Focus okna Nesting
- Fix: Focus po MessageBox
- Add: Generowanie miniatur w tle
- Add: Pola zamówienia (nazwa, klient, daty, status)
- Add: Callback dla wyników nestingu
- Add: Persystencja zamówień
- Add: Szczegółowe logowanie do pliku
- Add: Wybór klienta z listy
- Add: Domyślny termin +10 dni
- Add: Lepszy layout (nesting pod listą detali)
"""

import os
import uuid
import math
import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog, simpledialog
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, date, timedelta
import threading
import queue
import logging
import json
from PIL import Image, ImageDraw, ImageTk

# ============================================================
# KONFIGURACJA LOGOWANIA DO PLIKU
# ============================================================

def setup_file_logging():
    """Konfiguruj logowanie do pliku"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"order_window_{date.today().isoformat()}.log"

    # File handler z rotacją
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    ))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Usuń istniejące handlery
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return log_file

# Inicjalizuj logowanie
LOG_FILE = setup_file_logging()
logger = logging.getLogger(__name__)
logger.info(f"[OrderWindow] Log file: {LOG_FILE}")


# ============================================================
# USTAWIENIA UI - pozycja splittera, checkbox nestingu
# ============================================================

UI_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "ui_settings.json"


def load_ui_settings() -> Dict:
    """Wczytaj ustawienia UI (pozycja splittera, checkbox nestingu)"""
    default_settings = {
        "show_nesting_panel": True,  # Domyślnie pokazuj panel nestingu
        "splitter_position": 0.55,   # 55% dla górnej listy
    }

    try:
        if UI_SETTINGS_PATH.exists():
            with open(UI_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                for key in default_settings:
                    if key not in settings:
                        settings[key] = default_settings[key]
                return settings
    except Exception as e:
        logger.error(f"Błąd wczytywania ustawień UI: {e}")

    return default_settings


def save_ui_settings(settings: Dict) -> bool:
    """Zapisz ustawienia UI"""
    try:
        UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(UI_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        logger.debug(f"Zapisano ustawienia UI do {UI_SETTINGS_PATH}")
        return True
    except Exception as e:
        logger.error(f"Błąd zapisywania ustawień UI: {e}")
        return False


class Theme:
    """Paleta kolorów"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_CARD_HOVER = "#252525"
    BG_INPUT = "#2d2d2d"

    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#666666"

    ACCENT_PRIMARY = "#3b82f6"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"
    ACCENT_INFO = "#06b6d4"


# ============================================================
# STATUS ZAMÓWIENIA
# ============================================================

class OrderStatus:
    """Statusy zamówienia - zgodne z ENUM order_status w Supabase"""
    # Wartości ENUM z bazy danych
    RECEIVED = "RECEIVED"
    CONFIRMED = "CONFIRMED"
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    INVOICED = "INVOICED"

    # Domyślny status dla nowych zamówień
    DEFAULT = RECEIVED

    LABELS = {
        RECEIVED: "Przyjęte",
        CONFIRMED: "Potwierdzone",
        PLANNED: "Zaplanowane",
        IN_PROGRESS: "W realizacji",
        DONE: "Wykonane",
        INVOICED: "Zafakturowane"
    }

    COLORS = {
        RECEIVED: Theme.ACCENT_INFO,
        CONFIRMED: Theme.ACCENT_PRIMARY,
        PLANNED: Theme.ACCENT_WARNING,
        IN_PROGRESS: Theme.ACCENT_WARNING,
        DONE: Theme.ACCENT_SUCCESS,
        INVOICED: Theme.TEXT_MUTED
    }

    @classmethod
    def all_values(cls):
        return [cls.RECEIVED, cls.CONFIRMED, cls.PLANNED, cls.IN_PROGRESS, cls.DONE, cls.INVOICED]


# ============================================================
# GENERATOR MINIATUR (W TLE)
# ============================================================

class ThumbnailGenerator:
    """Generator miniatur w osobnym wątku"""

    def __init__(self, callback: Callable = None):
        self.callback = callback
        self.queue = queue.Queue()
        self.results = {}
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Uruchom wątek generatora"""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
            logger.info("[ThumbnailGenerator] Worker thread started")

    def stop(self):
        """Zatrzymaj wątek"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("[ThumbnailGenerator] Worker thread stopped")

    def add_part(self, part_id: str, contour: List, holes: List = None):
        """Dodaj detal do kolejki generowania miniatur"""
        self.queue.put((part_id, contour, holes or []))
        logger.debug(f"[ThumbnailGenerator] Added part to queue: {part_id}")

    def get_thumbnail(self, part_id: str) -> Optional[ImageTk.PhotoImage]:
        """Pobierz miniaturę (jeśli gotowa)"""
        return self.results.get(part_id)

    def _worker(self):
        """Wątek roboczy"""
        logger.info("[ThumbnailGenerator] Worker started")
        while not self._stop_event.is_set():
            try:
                part_id, contour, holes = self.queue.get(timeout=0.5)
                logger.debug(f"[ThumbnailGenerator] Processing: {part_id}")

                thumbnail = self._generate_thumbnail(contour, holes)
                self.results[part_id] = thumbnail

                if self.callback:
                    self.callback(part_id, thumbnail)

                self.queue.task_done()
                logger.debug(f"[ThumbnailGenerator] Completed: {part_id}")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[ThumbnailGenerator] Error: {e}")

        logger.info("[ThumbnailGenerator] Worker stopped")

    def _generate_thumbnail(self, contour: List, holes: List, size: int = 48) -> Optional[ImageTk.PhotoImage]:
        """Generuj miniaturę detalu"""
        try:
            if not contour or len(contour) < 3:
                return None

            # Oblicz bounding box
            xs = [p[0] for p in contour]
            ys = [p[1] for p in contour]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            width = max_x - min_x
            height = max_y - min_y

            if width <= 0 or height <= 0:
                return None

            # Skalowanie
            scale = min((size - 8) / width, (size - 8) / height)
            offset_x = (size - width * scale) / 2
            offset_y = (size - height * scale) / 2

            # Twórz obraz
            img = Image.new('RGBA', (size, size), (45, 45, 45, 255))
            draw = ImageDraw.Draw(img)

            # Rysuj kontur
            scaled_contour = [
                (int((x - min_x) * scale + offset_x), int((y - min_y) * scale + offset_y))
                for x, y in contour
            ]
            if len(scaled_contour) >= 3:
                draw.polygon(scaled_contour, fill=(59, 130, 246, 200), outline=(255, 255, 255, 255))

            # Rysuj otwory
            for hole in holes:
                if len(hole) >= 3:
                    scaled_hole = [
                        (int((x - min_x) * scale + offset_x), int((y - min_y) * scale + offset_y))
                        for x, y in hole
                    ]
                    draw.polygon(scaled_hole, fill=(45, 45, 45, 255), outline=(200, 200, 200, 200))

            return ImageTk.PhotoImage(img)

        except Exception as e:
            logger.error(f"[ThumbnailGenerator] Error generating thumbnail: {e}")
            return None


# ============================================================
# PANEL INFORMACJI O ZAMÓWIENIU
# ============================================================

class OrderInfoPanel(ctk.CTkFrame):
    """Panel z podstawowymi informacjami o zamówieniu"""

    def __init__(self, parent, on_change: Callable = None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=8, **kwargs)
        self.on_change = on_change
        self.customers_list = []  # Lista klientów
        self._load_customers()
        self._setup_ui()

    def _load_customers(self):
        """Wczytaj listę klientów"""
        logger.debug("[OrderInfoPanel] Loading customers list")
        try:
            from core.supabase_client import get_supabase_client
            client = get_supabase_client()
            response = client.table('customers').select('id,name,short_name').eq('is_active', True).order('name').execute()
            self.customers_list = response.data or []
            logger.info(f"[OrderInfoPanel] Loaded {len(self.customers_list)} customers from DB")
        except Exception as e:
            logger.warning(f"[OrderInfoPanel] Cannot load customers from DB: {e}")
            # Fallback - wczytaj z lokalnego JSON
            try:
                customers_file = Path("data/customers.json")
                if customers_file.exists():
                    with open(customers_file, 'r', encoding='utf-8') as f:
                        self.customers_list = json.load(f)
                    logger.info(f"[OrderInfoPanel] Loaded {len(self.customers_list)} customers from JSON")
            except Exception as e2:
                logger.warning(f"[OrderInfoPanel] Cannot load customers from JSON: {e2}")
                self.customers_list = []

    def _setup_ui(self):
        # Nagłówek
        title = ctk.CTkLabel(
            self,
            text="Informacje o zamówieniu",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        title.pack(pady=(10, 10), padx=10, anchor="w")

        # Nazwa zamówienia
        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.pack(fill="x", padx=10, pady=3)

        ctk.CTkLabel(name_frame, text="Nazwa:", width=80, anchor="w",
                     text_color=Theme.TEXT_SECONDARY).pack(side="left")
        self.entry_name = ctk.CTkEntry(name_frame, placeholder_text="Nazwa zamówienia")
        self.entry_name.pack(side="left", fill="x", expand=True)

        # Klient - dropdown z opcją dodania nowego
        client_frame = ctk.CTkFrame(self, fg_color="transparent")
        client_frame.pack(fill="x", padx=10, pady=3)

        ctk.CTkLabel(client_frame, text="Klient:", width=80, anchor="w",
                     text_color=Theme.TEXT_SECONDARY).pack(side="left")

        # Lista klientów dla combo
        customer_names = ["-- Wybierz --"] + [c.get('name', c.get('short_name', '?')) for c in self.customers_list]
        customer_names.append("+ Dodaj nowego...")

        self.client_combo = ctk.CTkComboBox(
            client_frame,
            values=customer_names,
            width=200,
            command=self._on_client_selected
        )
        self.client_combo.set("-- Wybierz --")
        self.client_combo.pack(side="left", fill="x", expand=True)

        # Przycisk odświeżenia klientów
        btn_refresh = ctk.CTkButton(
            client_frame,
            text="⟳",
            width=30,
            height=28,
            command=self._refresh_customers,
            fg_color=Theme.BG_INPUT
        )
        btn_refresh.pack(side="left", padx=(5, 0))

        # Daty w jednym wierszu
        dates_frame = ctk.CTkFrame(self, fg_color="transparent")
        dates_frame.pack(fill="x", padx=10, pady=3)

        # Data wpływu
        ctk.CTkLabel(dates_frame, text="Wpływ:", width=80, anchor="w",
                     text_color=Theme.TEXT_SECONDARY).pack(side="left")
        self.entry_date_in = ctk.CTkEntry(dates_frame, width=100)
        self.entry_date_in.pack(side="left")
        self.entry_date_in.insert(0, date.today().strftime("%Y-%m-%d"))

        # Data realizacji - domyślnie +10 dni
        ctk.CTkLabel(dates_frame, text="Termin:", width=60, anchor="w",
                     text_color=Theme.TEXT_SECONDARY).pack(side="left", padx=(15, 0))
        self.entry_date_due = ctk.CTkEntry(dates_frame, width=100)
        self.entry_date_due.pack(side="left")
        # Domyślnie +10 dni
        default_due = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        self.entry_date_due.insert(0, default_due)
        logger.debug(f"[OrderInfoPanel] Default due date set to +10 days: {default_due}")

        # Status i priorytet w jednym wierszu
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.pack(fill="x", padx=10, pady=3)

        ctk.CTkLabel(status_frame, text="Status:", width=80, anchor="w",
                     text_color=Theme.TEXT_SECONDARY).pack(side="left")

        self.status_var = ctk.StringVar(value=OrderStatus.DEFAULT)
        status_values = [f"{v} ({OrderStatus.LABELS[v]})" for v in OrderStatus.all_values()]
        self.status_combo = ctk.CTkComboBox(
            status_frame,
            values=status_values,
            width=170
        )
        self.status_combo.set(f"{OrderStatus.DEFAULT} ({OrderStatus.LABELS[OrderStatus.DEFAULT]})")
        self.status_combo.pack(side="left")

        # Priorytet
        ctk.CTkLabel(status_frame, text="Priorytet:", width=70, anchor="w",
                     text_color=Theme.TEXT_SECONDARY).pack(side="left", padx=(15, 0))
        self.prio_combo = ctk.CTkComboBox(
            status_frame,
            values=["Niski", "Normalny", "Wysoki", "Pilny"],
            width=100
        )
        self.prio_combo.set("Normalny")
        self.prio_combo.pack(side="left")

        # Uwagi
        notes_frame = ctk.CTkFrame(self, fg_color="transparent")
        notes_frame.pack(fill="x", padx=10, pady=3)

        ctk.CTkLabel(notes_frame, text="Uwagi:", width=80, anchor="w",
                     text_color=Theme.TEXT_SECONDARY).pack(side="left", anchor="n")
        self.text_notes = ctk.CTkTextbox(notes_frame, height=50)
        self.text_notes.pack(side="left", fill="x", expand=True)

    def _on_client_selected(self, selection):
        """Obsługa wyboru klienta"""
        logger.debug(f"[OrderInfoPanel] Client selected: {selection}")
        if selection == "+ Dodaj nowego...":
            self._add_new_customer()

    def _add_new_customer(self):
        """Dodaj nowego klienta"""
        logger.info("[OrderInfoPanel] Adding new customer")

        # Prosty dialog
        name = simpledialog.askstring("Nowy klient", "Nazwa klienta:", parent=self.winfo_toplevel())
        if not name:
            self.client_combo.set("-- Wybierz --")
            return

        logger.info(f"[OrderInfoPanel] New customer name: {name}")

        # Zapisz do bazy/JSON
        new_customer = {
            'id': str(uuid.uuid4()),
            'name': name,
            'is_active': True,
            'created_at': datetime.now().isoformat()
        }

        try:
            from core.supabase_client import get_supabase_client
            client = get_supabase_client()
            client.table('customers').insert(new_customer).execute()
            logger.info(f"[OrderInfoPanel] Customer saved to Supabase: {name}")
        except Exception as e:
            logger.warning(f"[OrderInfoPanel] Cannot save to Supabase: {e}")
            # Fallback - zapisz lokalnie
            try:
                customers_file = Path("data/customers.json")
                customers_file.parent.mkdir(parents=True, exist_ok=True)
                existing = []
                if customers_file.exists():
                    with open(customers_file, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                existing.append(new_customer)
                with open(customers_file, 'w', encoding='utf-8') as f:
                    json.dump(existing, f, indent=2, ensure_ascii=False)
                logger.info(f"[OrderInfoPanel] Customer saved to JSON: {name}")
            except Exception as e2:
                logger.error(f"[OrderInfoPanel] Cannot save customer: {e2}")

        # Odśwież listę
        self._refresh_customers()
        self.client_combo.set(name)

        # Przywróć focus
        self.winfo_toplevel().after(100, lambda: self.winfo_toplevel().focus_force())

    def _refresh_customers(self):
        """Odśwież listę klientów"""
        logger.info("[OrderInfoPanel] Refreshing customers list")
        self._load_customers()
        customer_names = ["-- Wybierz --"] + [c.get('name', c.get('short_name', '?')) for c in self.customers_list]
        customer_names.append("+ Dodaj nowego...")
        self.client_combo.configure(values=customer_names)

    def get_data(self) -> Dict:
        """Pobierz dane zamówienia"""
        status_text = self.status_combo.get()
        # Wyciągnij wartość ENUM (przed nawiasem)
        status = status_text.split(" ")[0] if status_text else OrderStatus.DEFAULT

        # Walidacja - upewnij się że status jest prawidłowy
        if status not in OrderStatus.all_values():
            logger.warning(f"[OrderInfoPanel] Invalid status '{status}', using default")
            status = OrderStatus.DEFAULT

        # Pobierz klienta z combo
        client_selection = self.client_combo.get()
        client = "" if client_selection in ["-- Wybierz --", "+ Dodaj nowego..."] else client_selection

        return {
            'name': self.entry_name.get().strip(),
            'client': client,
            'customer_name': client,  # alternatywna kolumna
            'date_in': self.entry_date_in.get().strip(),
            'date_due': self.entry_date_due.get().strip(),
            'status': status,
            'priority': self.prio_combo.get(),
            'notes': self.text_notes.get("1.0", "end-1c").strip()
        }

    def set_data(self, data: Dict):
        """Ustaw dane zamówienia"""
        if data.get('name'):
            self.entry_name.delete(0, 'end')
            self.entry_name.insert(0, data['name'])

        # Ustaw klienta w combo
        client = data.get('client') or data.get('customer_name', '')
        if client:
            # Sprawdź czy klient jest na liście
            current_values = self.client_combo.cget('values')
            if client in current_values:
                self.client_combo.set(client)
            else:
                # Dodaj klienta do listy i ustaw
                self.customers_list.append({'name': client})
                self._refresh_customers()
                self.client_combo.set(client)

        if data.get('date_in'):
            self.entry_date_in.delete(0, 'end')
            self.entry_date_in.insert(0, data['date_in'])

        if data.get('date_due'):
            self.entry_date_due.delete(0, 'end')
            self.entry_date_due.insert(0, data['date_due'])

        if data.get('status'):
            status = data['status']
            label = OrderStatus.LABELS.get(status, status)
            self.status_combo.set(f"{status} ({label})")

        if data.get('priority'):
            self.prio_combo.set(data['priority'])

        if data.get('notes'):
            self.text_notes.delete("1.0", "end")
            self.text_notes.insert("1.0", data['notes'])


# ============================================================
# PANEL LISTY DETALI (Z MINIATURAMI)
# ============================================================

class PartsListPanel(ctk.CTkFrame):
    """Panel z listą detali"""

    def __init__(self, parent, on_parts_change: Callable = None,
                 on_loading_complete: Callable = None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=8, **kwargs)

        self.on_parts_change = on_parts_change
        self.on_loading_complete = on_loading_complete
        self.parts: List[Dict] = []
        self.thumbnails: Dict[str, ImageTk.PhotoImage] = {}

        # Generator miniatur
        self.thumbnail_generator = ThumbnailGenerator(callback=self._on_thumbnail_ready)
        self.thumbnail_generator.start()

        self._setup_ui()

    def _setup_ui(self):
        # Nagłówek
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))

        title = ctk.CTkLabel(
            header,
            text="Lista detali",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        title.pack(side="left")

        self.lbl_count = ctk.CTkLabel(
            header,
            text="(0 pozycji)",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_count.pack(side="left", padx=10)

        self.lbl_loading = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=Theme.ACCENT_WARNING
        )
        self.lbl_loading.pack(side="left", padx=5)

        # Przyciski
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")

        btn_add = ctk.CTkButton(
            btn_frame,
            text="+ Dodaj DXF",
            command=self._add_files,
            fg_color=Theme.ACCENT_SUCCESS,
            width=100,
            height=28
        )
        btn_add.pack(side="left", padx=2)

        btn_folder = ctk.CTkButton(
            btn_frame,
            text="Folder",
            command=self._add_folder,
            fg_color=Theme.ACCENT_INFO,
            width=70,
            height=28
        )
        btn_folder.pack(side="left", padx=2)

        btn_remove = ctk.CTkButton(
            btn_frame,
            text="Usuń",
            command=self._remove_selected,
            fg_color=Theme.ACCENT_DANGER,
            width=60,
            height=28
        )
        btn_remove.pack(side="left", padx=2)

        # Tabela
        table_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Style
        style = ttk.Style()
        style.configure(
            "Parts.Treeview",
            background=Theme.BG_INPUT,
            foreground=Theme.TEXT_PRIMARY,
            fieldbackground=Theme.BG_INPUT,
            rowheight=36
        )
        style.configure(
            "Parts.Treeview.Heading",
            background="#1e3a5f",
            foreground=Theme.TEXT_PRIMARY,
            font=('Segoe UI', 9, 'bold')
        )
        style.map("Parts.Treeview", background=[("selected", Theme.ACCENT_PRIMARY)])

        columns = ('name', 'material', 'thickness', 'qty', 'dims', 'weight', 'cost')
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show='headings',
            style="Parts.Treeview"
        )

        self.tree.heading('name', text='Nazwa')
        self.tree.heading('material', text='Materiał')
        self.tree.heading('thickness', text='Grubość')
        self.tree.heading('qty', text='Ilość')
        self.tree.heading('dims', text='Wymiary')
        self.tree.heading('weight', text='Waga')
        self.tree.heading('cost', text='Koszt')

        self.tree.column('name', width=180)
        self.tree.column('material', width=80, anchor='center')
        self.tree.column('thickness', width=70, anchor='center')
        self.tree.column('qty', width=50, anchor='center')
        self.tree.column('dims', width=100, anchor='center')
        self.tree.column('weight', width=70, anchor='e')
        self.tree.column('cost', width=80, anchor='e')

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Double-click do edycji ilości
        self.tree.bind('<Double-1>', self._edit_quantity)

    def _add_files(self):
        """Dodaj pliki DXF"""
        logger.info("[PartsListPanel] Opening file dialog for DXF files")
        files = filedialog.askopenfilenames(
            title="Wybierz pliki DXF",
            filetypes=[("DXF Files", "*.dxf"), ("All Files", "*.*")]
        )
        if files:
            logger.info(f"[PartsListPanel] Selected {len(files)} files")
            self._load_files_async(list(files))

    def _add_folder(self):
        """Dodaj folder z plikami DXF"""
        logger.info("[PartsListPanel] Opening folder dialog")
        folder = filedialog.askdirectory(title="Wybierz folder z plikami DXF")
        if folder:
            logger.info(f"[PartsListPanel] Selected folder: {folder}")
            folder_path = Path(folder)
            # Użyj set() aby uniknąć duplikatów (Windows jest case-insensitive)
            dxf_files = list(set(folder_path.rglob("*.dxf")) | set(folder_path.rglob("*.DXF")))
            if dxf_files:
                logger.info(f"[PartsListPanel] Found {len(dxf_files)} DXF files")
                self._load_files_async([str(f) for f in dxf_files], folder)
            else:
                parent_win = self.winfo_toplevel()
                messagebox.showwarning("Uwaga", "Nie znaleziono plików DXF w folderze", parent=parent_win)
                # Przywróć focus
                parent_win.after(50, lambda: parent_win.focus_force())

    def _load_files_async(self, filepaths: List[str], base_folder: str = None):
        """Wczytaj pliki DXF w osobnym wątku"""
        self.lbl_loading.configure(text="Ładowanie...")
        logger.info(f"[PartsListPanel] Starting async load of {len(filepaths)} files")

        def load_thread():
            try:
                from quotations.utils.dxf_loader import load_dxf
                from quotations.utils.name_parser import parse_filename_with_folder_context
                from quotations.utils.dxf_area_calculator import (
                    calculate_weight_from_contour,
                    calculate_area_from_contour,
                    get_density,
                    process_dxf_file
                )

                loaded_count = 0
                for i, filepath in enumerate(filepaths):
                    try:
                        logger.debug(f"[PartsListPanel] Loading file {i+1}/{len(filepaths)}: {filepath}")
                        part = load_dxf(filepath)
                        if not part:
                            logger.warning(f"[PartsListPanel] Failed to load: {filepath}")
                            continue

                        # Parsuj nazwę
                        path = Path(filepath)
                        stop_at = Path(base_folder) if base_folder else None
                        parsed = parse_filename_with_folder_context(path, stop_at=stop_at)

                        part_id = str(uuid.uuid4())
                        contour = part.get_normalized_contour()
                        holes = [[(x - part.min_x, y - part.min_y) for x, y in hole] for hole in part.holes]

                        # Pobierz materiał i grubość
                        material = parsed.get('material', '') or 'NIEZNANY'
                        thickness_mm = parsed.get('thickness_mm') or 0.0

                        # --- Pełna analiza DXF (powierzchnie, wagi, operacje) ---
                        dxf_result = process_dxf_file(filepath, thickness_mm, material)

                        if dxf_result:
                            # Użyj wyników z pełnej analizy DXF
                            area_gross = dxf_result.area_gross_sq_mm
                            area_net = dxf_result.area_net_sq_mm
                            area_bbox = dxf_result.area_bbox_sq_mm
                            weight_kg = dxf_result.weight_net_kg
                            cutting_length = dxf_result.len_laser_cut_mm
                            piercing_count = dxf_result.piercing_count
                            marking_length = dxf_result.len_marking_mm
                            bending_length = dxf_result.len_bending_mm
                            total_contour_length = dxf_result.len_total_contour_mm
                        else:
                            # Fallback: oblicz z konturu (bez operacji)
                            area_gross, area_net, area_bbox = calculate_area_from_contour(contour, holes)
                            weight_kg = calculate_weight_from_contour(
                                contour, holes, thickness_mm, material
                            ) if thickness_mm > 0 else 0.0

                            # Oblicz długość cięcia z konturu (fallback)
                            cutting_length = 0.0
                            if len(contour) >= 2:
                                for j in range(len(contour)):
                                    k = (j + 1) % len(contour)
                                    dx = contour[k][0] - contour[j][0]
                                    dy = contour[k][1] - contour[j][1]
                                    cutting_length += math.sqrt(dx*dx + dy*dy)
                            for hole in holes:
                                if len(hole) >= 2:
                                    for j in range(len(hole)):
                                        k = (j + 1) % len(hole)
                                        dx = hole[k][0] - hole[j][0]
                                        dy = hole[k][1] - hole[j][1]
                                        cutting_length += math.sqrt(dx*dx + dy*dy)

                            # Liczba przebić = 1 (kontur zewn.) + liczba otworów
                            piercing_count = 1 + len(holes)
                            marking_length = 0.0
                            bending_length = 0.0
                            total_contour_length = cutting_length

                        part_data = {
                            'id': part_id,
                            'name': part.name,
                            'material': material,
                            'thickness_mm': thickness_mm,
                            'quantity': parsed.get('quantity') or 1,
                            'width': part.width,
                            'height': part.height,
                            'weight_kg': weight_kg,
                            'area_gross_mm2': area_gross,
                            'area_net_mm2': area_net,
                            'area_bbox_mm2': area_bbox,
                            'cutting_length_mm': cutting_length,
                            'density_kg_m3': get_density(material),
                            # Nowe pola operacyjne
                            'piercing_count': piercing_count,
                            'marking_length_mm': marking_length,
                            'bending_length_mm': bending_length,
                            'total_contour_length_mm': total_contour_length,
                            'filepath': filepath,
                            'contour': contour,
                            'holes': holes,
                        }
                        self.parts.append(part_data)
                        loaded_count += 1

                        # Dodaj do generatora miniatur
                        self.thumbnail_generator.add_part(part_id, contour, holes)

                        logger.debug(f"[PartsListPanel] Loaded: {part.name} ({part.width:.0f}x{part.height:.0f}) "
                                   f"area_net={area_net:.0f}mm² weight={weight_kg:.3f}kg "
                                   f"cut={cutting_length:.0f}mm piercing={piercing_count} "
                                   f"marking={marking_length:.0f}mm bending={bending_length:.0f}mm")

                    except Exception as e:
                        logger.error(f"[PartsListPanel] Error loading {filepath}: {e}")

                logger.info(f"[PartsListPanel] Load complete: {loaded_count}/{len(filepaths)} files")

                # Aktualizuj UI w głównym wątku
                self.after(0, self._on_load_complete, loaded_count)

            except ImportError as e:
                logger.error(f"[PartsListPanel] Import error: {e}")
                def show_error():
                    parent_win = self.winfo_toplevel()
                    messagebox.showerror("Błąd", f"Brak wymaganych modułów: {e}", parent=parent_win)
                    parent_win.after(50, lambda: parent_win.focus_force())
                self.after(0, show_error)

        thread = threading.Thread(target=load_thread, daemon=True)
        thread.start()

    def _on_load_complete(self, count: int):
        """Callback po zakończeniu ładowania"""
        logger.info(f"[PartsListPanel] Load complete callback, refreshing table")
        self.lbl_loading.configure(text="")
        self._refresh_table()

        if self.on_parts_change:
            self.on_parts_change(self.parts)

        if self.on_loading_complete:
            self.on_loading_complete(count)

    def _on_thumbnail_ready(self, part_id: str, thumbnail):
        """Callback gdy miniatura jest gotowa"""
        if thumbnail:
            self.thumbnails[part_id] = thumbnail
            # Opcjonalnie: odśwież wiersz w tabeli
            logger.debug(f"[PartsListPanel] Thumbnail ready for {part_id}")

    def _refresh_table(self):
        """Odśwież tabelę"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, part in enumerate(self.parts):
            dims = f"{part['width']:.0f}×{part['height']:.0f}"
            weight = f"{part.get('weight_kg', 0):.2f} kg"
            cost = f"{part.get('total_cost', 0):.2f}" if part.get('total_cost') else "-"

            self.tree.insert('', 'end', iid=str(i), values=(
                part['name'],
                part['material'],
                f"{part['thickness_mm']:.1f}mm",
                part['quantity'],
                dims,
                weight,
                cost
            ))

        self.lbl_count.configure(text=f"({len(self.parts)} pozycji)")

    def _remove_selected(self):
        """Usuń zaznaczone pozycje"""
        selection = self.tree.selection()
        if not selection:
            return

        indices = sorted([int(s) for s in selection], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.parts):
                logger.info(f"[PartsListPanel] Removing part: {self.parts[idx]['name']}")
                del self.parts[idx]

        self._refresh_table()

        if self.on_parts_change:
            self.on_parts_change(self.parts)

    def _edit_quantity(self, event):
        """Edycja ilości przez podwójne kliknięcie"""
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        col = self.tree.identify_column(event.x)

        if col != "#4":  # Kolumna qty
            return

        try:
            idx = int(item)
        except:
            return

        bbox = self.tree.bbox(item, col)
        if not bbox:
            return

        x, y, w, h = bbox
        current_qty = self.parts[idx].get('quantity', 1)

        entry = ctk.CTkEntry(self.tree.master, width=50)
        entry.insert(0, str(current_qty))
        entry.place(x=x, y=y)
        entry.focus()

        def save(e=None):
            try:
                new_qty = int(entry.get())
                if new_qty > 0:
                    self.parts[idx]['quantity'] = new_qty
                    logger.info(f"[PartsListPanel] Quantity changed: {self.parts[idx]['name']} -> {new_qty}")
                    self._refresh_table()
                    if self.on_parts_change:
                        self.on_parts_change(self.parts)
            except:
                pass
            entry.destroy()

        entry.bind("<Return>", save)
        entry.bind("<FocusOut>", save)

    def get_parts(self) -> List[Dict]:
        """Pobierz listę detali"""
        return self.parts

    def set_parts(self, parts: List[Dict]):
        """Ustaw listę detali"""
        self.parts = parts
        self._refresh_table()

    def get_parts_by_group(self) -> Dict[Tuple[str, float], List[Dict]]:
        """Pobierz detale pogrupowane po materiale i grubości"""
        groups = {}
        for part in self.parts:
            key = (part['material'], part['thickness_mm'])
            if key not in groups:
                groups[key] = []
            groups[key].append(part)
        return groups

    def destroy(self):
        """Cleanup"""
        self.thumbnail_generator.stop()
        super().destroy()


# ============================================================
# PANEL PARAMETRÓW KOSZTÓW
# ============================================================

class CostParametersPanel(ctk.CTkFrame):
    """Panel parametrów kosztowych"""

    def __init__(self, parent, on_params_change: Callable = None,
                 allocation_model_getter: Callable = None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=8, **kwargs)
        self.on_params_change = on_params_change
        self.allocation_model_getter = allocation_model_getter
        self._setup_ui()

    def _setup_ui(self):
        # Nagłówek
        title = ctk.CTkLabel(
            self,
            text="Parametry kosztów",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        title.pack(pady=(10, 15), padx=10, anchor="w")

        # Checkboxy kosztów
        self.chk_material = ctk.CTkCheckBox(self, text="Koszt materiału", command=self._on_change)
        self.chk_material.pack(anchor="w", padx=10, pady=3)
        self.chk_material.select()

        self.chk_cutting = ctk.CTkCheckBox(self, text="Koszt cięcia", command=self._on_change)
        self.chk_cutting.pack(anchor="w", padx=10, pady=3)
        self.chk_cutting.select()

        self.chk_foil = ctk.CTkCheckBox(self, text="Usuwanie folii (INOX ≤5mm)", command=self._on_change)
        self.chk_foil.pack(anchor="w", padx=10, pady=3)
        self.chk_foil.select()

        self.chk_piercing = ctk.CTkCheckBox(self, text="Piercing (przebicia)", command=self._on_change)
        self.chk_piercing.pack(anchor="w", padx=10, pady=3)
        self.chk_piercing.select()

        self.chk_operational = ctk.CTkCheckBox(self, text="Koszty operacyjne (40 PLN/arkusz)", command=self._on_change)
        self.chk_operational.pack(anchor="w", padx=10, pady=3)
        self.chk_operational.select()

        # Separator
        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=10, pady=10)

        # Koszty per zlecenie
        ctk.CTkLabel(self, text="Koszty per zlecenie:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=Theme.TEXT_SECONDARY).pack(anchor="w", padx=10, pady=(0, 5))

        # Technologia
        tech_frame = ctk.CTkFrame(self, fg_color="transparent")
        tech_frame.pack(fill="x", padx=10, pady=3)
        self.chk_technology = ctk.CTkCheckBox(tech_frame, text="Technologia:", width=120, command=self._on_change)
        self.chk_technology.pack(side="left")
        self.entry_technology = ctk.CTkEntry(tech_frame, width=80, placeholder_text="0.00")
        self.entry_technology.pack(side="left", padx=5)
        ctk.CTkLabel(tech_frame, text="PLN", text_color=Theme.TEXT_SECONDARY).pack(side="left")

        # Opakowania
        pack_frame = ctk.CTkFrame(self, fg_color="transparent")
        pack_frame.pack(fill="x", padx=10, pady=3)
        self.chk_packaging = ctk.CTkCheckBox(pack_frame, text="Opakowania:", width=120, command=self._on_change)
        self.chk_packaging.pack(side="left")
        self.entry_packaging = ctk.CTkEntry(pack_frame, width=80, placeholder_text="0.00")
        self.entry_packaging.pack(side="left", padx=5)
        ctk.CTkLabel(pack_frame, text="PLN", text_color=Theme.TEXT_SECONDARY).pack(side="left")

        # Transport
        trans_frame = ctk.CTkFrame(self, fg_color="transparent")
        trans_frame.pack(fill="x", padx=10, pady=3)
        self.chk_transport = ctk.CTkCheckBox(trans_frame, text="Transport:", width=120, command=self._on_change)
        self.chk_transport.pack(side="left")
        self.entry_transport = ctk.CTkEntry(trans_frame, width=80, placeholder_text="0.00")
        self.entry_transport.pack(side="left", padx=5)
        ctk.CTkLabel(trans_frame, text="PLN", text_color=Theme.TEXT_SECONDARY).pack(side="left")

        # Separator
        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=10, pady=10)

        # === NARZUT PROCENTOWY ===
        markup_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=6)
        markup_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(markup_frame, text="📈 Narzut procentowy:", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=Theme.ACCENT_WARNING).pack(side="left", padx=10, pady=8)

        self.markup_entry = ctk.CTkEntry(markup_frame, width=60, placeholder_text="0")
        self.markup_entry.pack(side="left", padx=5, pady=8)
        self.markup_entry.insert(0, "0")
        self.markup_entry.bind("<KeyRelease>", lambda e: self._on_change())

        ctk.CTkLabel(markup_frame, text="%", font=ctk.CTkFont(size=12),
                     text_color=Theme.TEXT_SECONDARY).pack(side="left", padx=(0, 10), pady=8)

        # Szybkie przyciski narzutu
        quick_frame = ctk.CTkFrame(markup_frame, fg_color="transparent")
        quick_frame.pack(side="left", padx=5, pady=5)

        for pct in [5, 10, 15, 20]:
            btn = ctk.CTkButton(
                quick_frame, text=f"+{pct}%", width=40, height=24,
                fg_color=Theme.ACCENT_PRIMARY, hover_color="#7c4fe0",
                font=ctk.CTkFont(size=9),
                command=lambda p=pct: self._set_markup(p)
            )
            btn.pack(side="left", padx=1)

        # Wczytaj wartości z ustawień
        self._load_cost_settings()

    def _load_cost_settings(self):
        """Wczytaj wartości 'Koszty per zlecenie' z config/cost_settings.json"""
        settings_path = Path(__file__).parent.parent.parent / "config" / "cost_settings.json"

        try:
            if settings_path.exists():
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                logger.debug(f"[CostParametersPanel] Wczytano ustawienia kosztów: {settings}")

                # Technologia
                if settings.get('tech_cost_enabled', False):
                    self.chk_technology.select()
                else:
                    self.chk_technology.deselect()
                tech_value = settings.get('tech_cost_value', 0.0)
                self.entry_technology.delete(0, "end")
                self.entry_technology.insert(0, f"{tech_value:.2f}")

                # Opakowania
                if settings.get('packaging_cost_enabled', False):
                    self.chk_packaging.select()
                else:
                    self.chk_packaging.deselect()
                packaging_value = settings.get('packaging_cost_value', 0.0)
                self.entry_packaging.delete(0, "end")
                self.entry_packaging.insert(0, f"{packaging_value:.2f}")

                # Transport
                if settings.get('transport_cost_enabled', False):
                    self.chk_transport.select()
                else:
                    self.chk_transport.deselect()
                transport_value = settings.get('transport_cost_value', 0.0)
                self.entry_transport.delete(0, "end")
                self.entry_transport.insert(0, f"{transport_value:.2f}")

                # Narzut procentowy
                markup = settings.get('default_markup_percent', 0.0)
                self.markup_entry.delete(0, "end")
                self.markup_entry.insert(0, f"{markup:.0f}")

                logger.info(f"[CostParametersPanel] Wczytano koszty per zlecenie: "
                           f"Tech={tech_value}, Pack={packaging_value}, Trans={transport_value}")

        except Exception as e:
            logger.error(f"[CostParametersPanel] Błąd wczytywania ustawień kosztów: {e}")

    def _set_markup(self, percent: int):
        """Ustaw wartość narzutu procentowego"""
        self.markup_entry.delete(0, "end")
        self.markup_entry.insert(0, str(percent))
        self._on_change()

    def _on_change(self, *args):
        if self.on_params_change:
            self.on_params_change(self.get_params())

    def get_params(self) -> Dict:
        def safe_float(entry):
            try:
                return float(entry.get() or 0)
            except:
                return 0.0

        # Pobierz model alokacji z detailed_panel (przez getter)
        alloc_map = {
            "Proporcjonalny": "PROPORTIONAL",
            "Prostokąt otaczający": "UNIT",
            "Na arkusz": "PER_SHEET"
        }
        alloc_value = self.allocation_model_getter() if self.allocation_model_getter else "Proporcjonalny"
        allocation = alloc_map.get(alloc_value, "PROPORTIONAL")

        return {
            'allocation_model': allocation,
            'include_material': self.chk_material.get(),
            'include_cutting': self.chk_cutting.get(),
            'include_foil': self.chk_foil.get(),
            'include_piercing': self.chk_piercing.get(),
            'include_operational': self.chk_operational.get(),
            'technology_cost': safe_float(self.entry_technology) if self.chk_technology.get() else 0,
            'packaging_cost': safe_float(self.entry_packaging) if self.chk_packaging.get() else 0,
            'transport_cost': safe_float(self.entry_transport) if self.chk_transport.get() else 0,
            'markup_percent': safe_float(self.markup_entry),
        }


# ============================================================
# PANEL PODSUMOWANIA KOSZTÓW
# ============================================================

class CostSummaryPanel(ctk.CTkFrame):
    """Panel podsumowania kosztów"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=8, **kwargs)
        self._setup_ui()

    def _setup_ui(self):
        title = ctk.CTkLabel(self, text="Podsumowanie kosztów",
                             font=ctk.CTkFont(size=14, weight="bold"),
                             text_color=Theme.TEXT_PRIMARY)
        title.pack(pady=(10, 15), padx=10, anchor="w")

        self.cost_labels = {}

        for key, label in [('material', 'Materiał:'), ('cutting', 'Cięcie:'),
                           ('foil', 'Folia:'), ('piercing', 'Piercing:'),
                           ('operational', 'Operacyjne:')]:
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                         text_color=Theme.TEXT_SECONDARY, width=100, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(frame, text="0.00 PLN", font=ctk.CTkFont(size=11),
                               text_color=Theme.TEXT_PRIMARY, anchor="e")
            lbl.pack(side="right")
            self.cost_labels[key] = lbl

        ctk.CTkFrame(self, height=1, fg_color=Theme.TEXT_MUTED).pack(fill="x", padx=10, pady=8)

        prod_frame = ctk.CTkFrame(self, fg_color="transparent")
        prod_frame.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(prod_frame, text="Suma produkcji:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=Theme.TEXT_PRIMARY).pack(side="left")
        self.lbl_subtotal = ctk.CTkLabel(prod_frame, text="0.00 PLN",
                                          font=ctk.CTkFont(size=11, weight="bold"),
                                          text_color=Theme.ACCENT_INFO)
        self.lbl_subtotal.pack(side="right")

        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=10, pady=8)

        for key, label in [('technology', '+ Technologia:'), ('packaging', '+ Opakowania:'),
                           ('transport', '+ Transport:')]:
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                         text_color=Theme.TEXT_MUTED, width=100, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(frame, text="0.00 PLN", font=ctk.CTkFont(size=11),
                               text_color=Theme.TEXT_MUTED, anchor="e")
            lbl.pack(side="right")
            self.cost_labels[key] = lbl

        # Narzut procentowy
        markup_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT, corner_radius=4)
        markup_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(markup_frame, text="📈 Narzut:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=Theme.ACCENT_WARNING, width=100, anchor="w").pack(side="left", padx=5, pady=3)
        self.lbl_markup_pct = ctk.CTkLabel(markup_frame, text="(0%)", font=ctk.CTkFont(size=10),
                                           text_color=Theme.TEXT_MUTED)
        self.lbl_markup_pct.pack(side="left", padx=2, pady=3)
        self.lbl_markup = ctk.CTkLabel(markup_frame, text="+0.00 PLN", font=ctk.CTkFont(size=11, weight="bold"),
                                       text_color=Theme.ACCENT_WARNING, anchor="e")
        self.lbl_markup.pack(side="right", padx=5, pady=3)
        self.cost_labels['markup'] = self.lbl_markup

        ctk.CTkFrame(self, height=2, fg_color=Theme.ACCENT_PRIMARY).pack(fill="x", padx=10, pady=10)

        total_frame = ctk.CTkFrame(self, fg_color="transparent")
        total_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(total_frame, text="RAZEM:", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Theme.TEXT_PRIMARY).pack(side="left")
        self.lbl_total = ctk.CTkLabel(total_frame, text="0.00 PLN",
                                       font=ctk.CTkFont(size=16, weight="bold"),
                                       text_color=Theme.ACCENT_SUCCESS)
        self.lbl_total.pack(side="right")

        ctk.CTkFrame(self, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=10, pady=10)

        self.lbl_stats = ctk.CTkLabel(self, text="Arkuszy: - | Efektywność: - | Waga: -",
                                       font=ctk.CTkFont(size=10), text_color=Theme.TEXT_MUTED)
        self.lbl_stats.pack(padx=10, pady=5)

    def update_costs(self, result: Dict):
        self.cost_labels['material'].configure(text=f"{result.get('material_cost', 0):,.2f} PLN")
        self.cost_labels['cutting'].configure(text=f"{result.get('cutting_cost', 0):,.2f} PLN")
        self.cost_labels['foil'].configure(text=f"{result.get('foil_cost', 0):,.2f} PLN")
        self.cost_labels['piercing'].configure(text=f"{result.get('piercing_cost', 0):,.2f} PLN")
        self.cost_labels['operational'].configure(text=f"{result.get('operational_cost', 0):,.2f} PLN")
        self.lbl_subtotal.configure(text=f"{result.get('subtotal', 0):,.2f} PLN")
        self.cost_labels['technology'].configure(text=f"{result.get('technology_cost', 0):,.2f} PLN")
        self.cost_labels['packaging'].configure(text=f"{result.get('packaging_cost', 0):,.2f} PLN")
        self.cost_labels['transport'].configure(text=f"{result.get('transport_cost', 0):,.2f} PLN")

        # Narzut procentowy
        markup_pct = result.get('markup_percent', 0)
        markup_value = result.get('markup_value', 0)
        self.lbl_markup_pct.configure(text=f"({markup_pct:g}%)")
        sign = "+" if markup_value >= 0 else ""
        self.lbl_markup.configure(text=f"{sign}{markup_value:,.2f} PLN")

        self.lbl_total.configure(text=f"{result.get('total_cost', 0):,.2f} PLN")

        sheets = result.get('total_sheets', 0)
        efficiency = result.get('average_efficiency', 0) * 100
        weight = result.get('total_weight_kg', 0)
        self.lbl_stats.configure(text=f"Arkuszy: {sheets} | Efektywność: {efficiency:.1f}% | Waga: {weight:.1f} kg")


# ============================================================
# POPUP WYNIKÓW NESTINGU
# ============================================================

class NestingResultsPopup(ctk.CTkToplevel):
    """Okno popup z wynikami nestingu i grafikami arkuszy"""

    def __init__(self, parent, nesting_results: Dict = None, **kwargs):
        super().__init__(parent, **kwargs)

        self.nesting_results = nesting_results or {}
        self.sheet_images: List[ImageTk.PhotoImage] = []
        self.current_sheet_index = 0

        self.title("Wyniki nestingu")
        self.configure(fg_color=Theme.BG_DARK)
        self.geometry("900x700")
        self.minsize(700, 500)

        # Na pierwszym planie
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))

        self._setup_ui()
        self._load_images()

    def _setup_ui(self):
        """Buduj interfejs"""
        # Header
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50)
        header.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            header, text="Wyniki nestingu",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        ).pack(side="left", padx=15, pady=10)

        ctk.CTkButton(
            header, text="Zamknij", command=self.destroy,
            fg_color=Theme.ACCENT_DANGER, width=80, height=30
        ).pack(side="right", padx=15, pady=10)

        # Main content - 2 kolumny
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=5)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        # Lewa kolumna - lista arkuszy
        left_frame = ctk.CTkFrame(main, fg_color=Theme.BG_CARD, corner_radius=8)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(
            left_frame, text="Arkusze",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(pady=10, padx=10, anchor="w")

        self.sheets_listbox = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
        self.sheets_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        # Prawa kolumna - podgląd grafiki
        right_frame = ctk.CTkFrame(main, fg_color=Theme.BG_CARD, corner_radius=8)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        preview_header = ctk.CTkFrame(right_frame, fg_color="transparent")
        preview_header.pack(fill="x", padx=10, pady=10)

        self.lbl_preview_title = ctk.CTkLabel(
            preview_header, text="Podgląd arkusza",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        )
        self.lbl_preview_title.pack(side="left")

        # Nawigacja
        nav_frame = ctk.CTkFrame(preview_header, fg_color="transparent")
        nav_frame.pack(side="right")

        self.btn_prev = ctk.CTkButton(
            nav_frame, text="< Poprz", width=70, height=28,
            command=self._prev_sheet, fg_color=Theme.BG_INPUT
        )
        self.btn_prev.pack(side="left", padx=2)

        self.lbl_page = ctk.CTkLabel(
            nav_frame, text="1 / 1", width=60,
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_page.pack(side="left", padx=5)

        self.btn_next = ctk.CTkButton(
            nav_frame, text="Nast >", width=70, height=28,
            command=self._next_sheet, fg_color=Theme.BG_INPUT
        )
        self.btn_next.pack(side="left", padx=2)

        # Canvas do wyświetlania grafiki
        self.preview_canvas = ctk.CTkCanvas(
            right_frame, bg=Theme.BG_DARK,
            highlightthickness=0
        )
        self.preview_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Info o arkuszu
        self.lbl_sheet_info = ctk.CTkLabel(
            right_frame, text="",
            font=ctk.CTkFont(size=10), text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_sheet_info.pack(pady=(0, 10))

    def _load_images(self):
        """Wczytaj grafiki z base64"""
        import base64
        from io import BytesIO

        images_data = self.nesting_results.get('sheet_images_base64', [])

        if not images_data:
            self._show_no_images()
            return

        for i, img_data in enumerate(images_data):
            try:
                b64_str = img_data.get('image_base64', '')
                if b64_str:
                    img_bytes = base64.b64decode(b64_str)
                    pil_img = Image.open(BytesIO(img_bytes))
                    # Skaluj do rozmiaru canvas
                    pil_img.thumbnail((600, 450), Image.Resampling.LANCZOS)
                    tk_img = ImageTk.PhotoImage(pil_img)
                    self.sheet_images.append({
                        'image': tk_img,
                        'tab_name': img_data.get('tab_name', f'Arkusz {i+1}'),
                        'sheet_index': img_data.get('sheet_index', i)
                    })
            except Exception as e:
                logger.warning(f"[NestingResultsPopup] Error loading image {i}: {e}")

        # Dodaj wpisy do listy
        self._populate_sheets_list()

        # Pokaż pierwszy arkusz
        if self.sheet_images:
            self._show_sheet(0)

    def _populate_sheets_list(self):
        """Wypełnij listę arkuszy"""
        sheets = self.nesting_results.get('sheets', [])

        for i, img_data in enumerate(self.sheet_images):
            frame = ctk.CTkFrame(self.sheets_listbox, fg_color=Theme.BG_CARD_HOVER, corner_radius=4)
            frame.pack(fill="x", pady=2)

            # Pobierz info o arkuszu
            sheet_info = sheets[i] if i < len(sheets) else {}
            eff = sheet_info.get('efficiency', 0)
            if isinstance(eff, (int, float)):
                eff_pct = eff * 100 if eff <= 1 else eff
            else:
                eff_pct = 0

            btn = ctk.CTkButton(
                frame,
                text=f"#{i+1} {img_data['tab_name']} ({eff_pct:.0f}%)",
                command=lambda idx=i: self._show_sheet(idx),
                fg_color="transparent",
                hover_color=Theme.ACCENT_PRIMARY,
                anchor="w",
                height=30
            )
            btn.pack(fill="x", padx=5, pady=2)

    def _show_sheet(self, index: int):
        """Pokaż arkusz o podanym indeksie"""
        if not self.sheet_images or index < 0 or index >= len(self.sheet_images):
            return

        self.current_sheet_index = index
        img_data = self.sheet_images[index]

        # Aktualizuj canvas
        self.preview_canvas.delete("all")
        canvas_w = self.preview_canvas.winfo_width() or 600
        canvas_h = self.preview_canvas.winfo_height() or 450
        x = canvas_w // 2
        y = canvas_h // 2
        self.preview_canvas.create_image(x, y, image=img_data['image'], anchor="center")

        # Aktualizuj tytuł i nawigację
        self.lbl_preview_title.configure(text=f"Arkusz #{index+1}: {img_data['tab_name']}")
        self.lbl_page.configure(text=f"{index+1} / {len(self.sheet_images)}")

        # Info o arkuszu
        sheets = self.nesting_results.get('sheets', [])
        if index < len(sheets):
            s = sheets[index]
            info = f"Detali: {s.get('parts_count', 0)} | Efektywność: {s.get('efficiency', 0)*100:.0f}% | Koszt: {s.get('cost', 0):.2f} PLN"
            self.lbl_sheet_info.configure(text=info)

    def _show_no_images(self):
        """Pokaż komunikat gdy brak grafik"""
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(
            300, 225, text="Brak zapisanych grafik nestingu",
            fill=Theme.TEXT_MUTED, font=("Segoe UI", 12)
        )

    def _prev_sheet(self):
        """Poprzedni arkusz"""
        if self.current_sheet_index > 0:
            self._show_sheet(self.current_sheet_index - 1)

    def _next_sheet(self):
        """Następny arkusz"""
        if self.current_sheet_index < len(self.sheet_images) - 1:
            self._show_sheet(self.current_sheet_index + 1)


# ============================================================
# PANEL WYNIKÓW NESTINGU
# ============================================================

class NestingResultsPanel(ctk.CTkFrame):
    """Panel wyników nestingu"""

    def __init__(self, parent, on_click_popup: Callable = None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=8, **kwargs)
        self.on_click_popup = on_click_popup
        self.nesting_results = {}
        self._setup_ui()

    def _setup_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(header, text="Wyniki nestingu", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=Theme.TEXT_PRIMARY).pack(side="left")

        # Przycisk otwierania popup
        self.btn_popup = ctk.CTkButton(
            header, text="Pokaż grafiki",
            command=self._open_popup,
            fg_color=Theme.ACCENT_INFO,
            hover_color="#0599b8",
            width=100, height=26,
            font=ctk.CTkFont(size=10)
        )
        self.btn_popup.pack(side="right", padx=5)

        self.lbl_summary = ctk.CTkLabel(header, text="Brak danych", font=ctk.CTkFont(size=11),
                                         text_color=Theme.TEXT_SECONDARY)
        self.lbl_summary.pack(side="right", padx=10)

        list_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.sheets_list = ctk.CTkScrollableFrame(list_frame, fg_color="transparent")
        self.sheets_list.pack(fill="both", expand=True)

        self.placeholder = ctk.CTkLabel(self.sheets_list, text="Uruchom nesting aby zobaczyć wyniki",
                                         font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED)
        self.placeholder.pack(expand=True, pady=30)

    def _open_popup(self):
        """Otwórz popup z wynikami"""
        if self.on_click_popup:
            self.on_click_popup()
        else:
            # Fallback - otwórz bezpośrednio
            if self.nesting_results:
                popup = NestingResultsPopup(self.winfo_toplevel(), self.nesting_results)
                popup.focus_force()

    def set_nesting_results(self, results: Dict):
        """Ustaw wyniki nestingu (do użycia przez popup)"""
        self.nesting_results = results

    def update_results(self, sheets_data: List[Dict]):
        for widget in self.sheets_list.winfo_children():
            widget.destroy()

        if not sheets_data:
            ctk.CTkLabel(self.sheets_list, text="Brak arkuszy", font=ctk.CTkFont(size=11),
                         text_color=Theme.TEXT_MUTED).pack(expand=True, pady=30)
            self.lbl_summary.configure(text="Brak danych")
            return

        total_sheets = len(sheets_data)
        total_parts = sum(s.get('parts_count', 0) for s in sheets_data)
        avg_eff = sum(s.get('efficiency', 0) for s in sheets_data) / total_sheets if total_sheets else 0

        self.lbl_summary.configure(text=f"{total_sheets} arkuszy | {total_parts} detali | {avg_eff:.0%} śr. efektywność")

        for i, sheet in enumerate(sheets_data):
            frame = ctk.CTkFrame(self.sheets_list, fg_color=Theme.BG_CARD_HOVER, corner_radius=6)
            frame.pack(fill="x", pady=2, padx=2)
            # Kliknięcie na wiersz otwiera popup
            frame.bind("<Button-1>", lambda e: self._open_popup())

            ctk.CTkLabel(frame, text=f"#{i+1}", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=Theme.ACCENT_PRIMARY, width=30).pack(side="left", padx=10, pady=8)

            mat_text = f"{sheet.get('material', '?')} {sheet.get('thickness_mm', 0):.1f}mm"
            ctk.CTkLabel(frame, text=mat_text, font=ctk.CTkFont(size=11),
                         text_color=Theme.TEXT_PRIMARY, width=100).pack(side="left", padx=5)

            eff = sheet.get('efficiency', 0) * 100
            eff_color = Theme.ACCENT_SUCCESS if eff >= 70 else Theme.ACCENT_WARNING if eff >= 50 else Theme.ACCENT_DANGER
            ctk.CTkLabel(frame, text=f"{eff:.0f}%", font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=eff_color, width=50).pack(side="left", padx=5)

            ctk.CTkLabel(frame, text=f"{sheet.get('parts_count', 0)} det.", font=ctk.CTkFont(size=11),
                         text_color=Theme.TEXT_SECONDARY, width=60).pack(side="left", padx=5)

            ctk.CTkLabel(frame, text=f"{sheet.get('total_cost', 0):,.2f} PLN", font=ctk.CTkFont(size=11),
                         text_color=Theme.TEXT_PRIMARY).pack(side="right", padx=10)


# ============================================================
# GŁÓWNE OKNO ZAMÓWIENIA
# ============================================================

class OrderWindow(ctk.CTkToplevel):
    """Okno zarządzania zamówieniem z integracją Nesting"""

    def __init__(self, parent=None, order_id: str = None, order_data: Dict = None,
                 on_save_callback: Callable = None):
        super().__init__(parent)

        self.parent = parent
        self.order_id = order_id or str(uuid.uuid4())
        self.order_data = order_data or {}
        self.nesting_results = {}
        self.cost_result = None
        self.cost_service = None
        self.on_save_callback = on_save_callback

        # Wczytaj ustawienia UI
        self.ui_settings = load_ui_settings()
        self.show_nesting_panel_var = ctk.BooleanVar(value=self.ui_settings.get("show_nesting_panel", True))

        logger.info(f"[OrderWindow] Opening order: {self.order_id}")

        # Inicjalizacja CostService
        self._init_cost_service()

        # Konfiguracja okna
        self.title(f"Zamówienie {order_id or 'Nowe'} - NewERP")
        self.configure(fg_color=Theme.BG_DARK)
        self.geometry("1400x900")
        self.minsize(1200, 700)

        # Na pierwszym planie
        self._bring_to_front()

        self._setup_ui()

        # Wczytaj dane jeśli edycja
        if order_data:
            self._load_order_data()

    def _bring_to_front(self):
        """Wymuś pierwszy plan okna"""
        logger.debug("[OrderWindow] Bringing window to front")
        self.attributes('-topmost', True)
        self.lift()
        self.focus_force()
        self.after(200, lambda: self.attributes('-topmost', False))

    def _init_cost_service(self):
        """Inicjalizuj CostService"""
        try:
            from pricing.cost_service import create_cost_service
            self.cost_service = create_cost_service()
            logger.info("[OrderWindow] CostService initialized")
        except Exception as e:
            logger.warning(f"[OrderWindow] CostService not available: {e}")
            self.cost_service = None

    def _setup_ui(self):
        """Buduj interfejs - layout z nestingiem pod listą detali"""
        logger.debug("[OrderWindow] Setting up UI with improved layout")

        # === HEADER ===
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50)
        header.pack(fill="x", padx=10, pady=(10, 5))
        header.pack_propagate(False)

        title_text = f"Zamówienie: {self.order_id[:8]}..." if len(self.order_id) > 8 else f"Zamówienie: {self.order_id}"
        ctk.CTkLabel(header, text=title_text, font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Theme.ACCENT_PRIMARY).pack(side="left", padx=15, pady=10)

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=15)

        ctk.CTkButton(btn_frame, text="Zapisz", command=self._save_order,
                      fg_color=Theme.ACCENT_SUCCESS, width=90, height=32).pack(side="left", padx=3)

        # Checkbox "Wyświetaj panel nestingu"
        self.chk_show_nesting = ctk.CTkCheckBox(
            btn_frame, text="Panel nestingu",
            variable=self.show_nesting_panel_var,
            command=self._toggle_nesting_panel,
            font=ctk.CTkFont(size=11),
            width=130, height=32
        )
        self.chk_show_nesting.pack(side="left", padx=(10, 3))

        ctk.CTkButton(btn_frame, text="Nesting", command=self._run_nesting,
                      fg_color=Theme.ACCENT_WARNING, width=90, height=32).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="Przelicz", command=self._recalculate,
                      fg_color=Theme.ACCENT_INFO, width=90, height=32).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="Dokumenty", command=self._generate_documents,
                      fg_color=Theme.BG_INPUT, width=90, height=32).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="⚙️ Ustawienia", command=self._open_settings,
                      fg_color=Theme.BG_INPUT, width=100, height=32).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="Zamknij", command=self._close,
                      fg_color=Theme.ACCENT_DANGER, width=70, height=32).pack(side="left", padx=3)

        # === MAIN CONTENT - 2 kolumny ===
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=5)

        # Lewa strona: Info + Lista detali + Nesting (większość ekranu)
        # Prawa strona: Parametry + Koszty (węższy panel)
        main.grid_columnconfigure(0, weight=3)  # Lewa - 75%
        main.grid_columnconfigure(1, weight=1)  # Prawa - 25%
        main.grid_rowconfigure(0, weight=1)

        # === LEWA KOLUMNA z VERTICAL SPLITTER ===
        left_col = ctk.CTkFrame(main, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Użyj ttk.PanedWindow dla skalowalnego podziału
        style = ttk.Style()
        style.configure("Vertical.TPanedwindow", background=Theme.BG_DARK)

        self.left_paned = ttk.PanedWindow(left_col, orient="vertical")
        self.left_paned.pack(fill="both", expand=True)

        # === GÓRNY PANEL (lista pozycji zamówienia) ===
        top_frame = ctk.CTkFrame(self.left_paned, fg_color="transparent")

        from orders.gui.detailed_parts_panel import DetailedPartsPanel
        self.detailed_panel = DetailedPartsPanel(
            top_frame,
            on_parts_change=self._on_detailed_parts_change
        )
        self.detailed_panel.pack(fill="both", expand=True)

        self.left_paned.add(top_frame, weight=3)  # 60% domyślnie (zwiększone o 25%)

        # === DOLNY PANEL (info + lista detali + wyniki nestingu) ===
        bottom_frame = ctk.CTkFrame(self.left_paned, fg_color="transparent")

        # Środkowa część: Info + Lista detali (miniaturki) obok siebie
        middle_left = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        middle_left.pack(fill="both", expand=True, pady=(0, 5))
        middle_left.grid_columnconfigure(0, weight=1)  # Info - 40%
        middle_left.grid_columnconfigure(1, weight=2)  # Lista - 60%
        middle_left.grid_rowconfigure(0, weight=1)

        # Panel informacji (lewa)
        self.info_panel = OrderInfoPanel(middle_left)
        self.info_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Panel listy detali z miniaturkami (prawa)
        self.parts_panel = PartsListPanel(
            middle_left,
            on_parts_change=self._on_parts_change,
            on_loading_complete=self._on_loading_complete
        )
        self.parts_panel.grid(row=0, column=1, sticky="nsew")

        # Wyniki nestingu
        self.results_panel = NestingResultsPanel(bottom_frame, height=200)
        self.results_panel.pack(fill="x", pady=(0, 0))

        self.left_paned.add(bottom_frame, weight=2)  # 40%

        # Ustaw pozycję splittera po renderowaniu
        self.after(100, self._apply_splitter_position)

        # === PRAWA KOLUMNA ===
        right_col = ctk.CTkFrame(main, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_col.grid_rowconfigure(0, weight=0)
        right_col.grid_rowconfigure(1, weight=1)

        # Parametry kosztów (góra prawa)
        self.params_panel = CostParametersPanel(
            right_col,
            on_params_change=self._on_params_change,
            allocation_model_getter=lambda: self.detailed_panel.allocation_model_var.get()
        )
        self.params_panel.grid(row=0, column=0, sticky="new", pady=(0, 5))

        # Podsumowanie kosztów (dół prawa)
        self.summary_panel = CostSummaryPanel(right_col)
        self.summary_panel.grid(row=1, column=0, sticky="nsew")

        # === STATUSBAR ===
        statusbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=28)
        statusbar.pack(fill="x", padx=10, pady=(5, 10))
        statusbar.pack_propagate(False)

        self.lbl_status = ctk.CTkLabel(statusbar, text="Gotowy", font=ctk.CTkFont(size=10),
                                        text_color=Theme.TEXT_SECONDARY)
        self.lbl_status.pack(side="left", padx=15, pady=5)

        # Log file info
        log_info = ctk.CTkLabel(statusbar, text=f"Log: {LOG_FILE}", font=ctk.CTkFont(size=9),
                                 text_color=Theme.TEXT_MUTED)
        log_info.pack(side="right", padx=15, pady=5)

    def _apply_splitter_position(self):
        """Ustaw pozycję splittera z zapisanych ustawień"""
        try:
            self.update_idletasks()
            total_height = self.left_paned.winfo_height()
            if total_height > 100:  # Upewnij się, że okno jest wyrenderowane
                saved_position = self.ui_settings.get("splitter_position", 0.55)
                sash_y = int(total_height * saved_position)
                self.left_paned.sashpos(0, sash_y)
                logger.debug(f"[OrderWindow] Splitter position set to {sash_y}px ({saved_position:.0%})")
        except Exception as e:
            logger.warning(f"[OrderWindow] Could not set splitter position: {e}")

    def _save_splitter_position(self):
        """Zapisz aktualną pozycję splittera"""
        try:
            total_height = self.left_paned.winfo_height()
            if total_height > 100:
                sash_y = self.left_paned.sashpos(0)
                position = sash_y / total_height
                self.ui_settings["splitter_position"] = round(position, 3)
                self.ui_settings["show_nesting_panel"] = self.show_nesting_panel_var.get()
                save_ui_settings(self.ui_settings)
                logger.info(f"[OrderWindow] Saved splitter position: {position:.1%}")
        except Exception as e:
            logger.warning(f"[OrderWindow] Could not save splitter position: {e}")

    def _toggle_nesting_panel(self):
        """Przełącz widoczność panelu nestingu (info + lista detali)"""
        show = self.show_nesting_panel_var.get()
        logger.info(f"[OrderWindow] Toggle nesting panel: {show}")

        if show:
            # Pokaż dolny panel
            self.left_paned.pane(1, weight=2)
            self.after(50, self._apply_splitter_position)
        else:
            # Ukryj dolny panel (minimalizuj)
            try:
                total_height = self.left_paned.winfo_height()
                self.left_paned.sashpos(0, total_height - 50)  # Zostaw 50px na wyniki
            except:
                pass

        # Zapisz ustawienie
        self.ui_settings["show_nesting_panel"] = show
        save_ui_settings(self.ui_settings)

    def _on_parts_change(self, parts: List[Dict]):
        """Callback - zmiana listy detali (z panelu miniaturek)"""
        logger.info(f"[OrderWindow] Parts changed: {len(parts)} items")
        self.lbl_status.configure(text=f"Wczytano {len(parts)} detali")

        # Synchronizuj z panelem szczegolowym
        if hasattr(self, 'detailed_panel') and self.detailed_panel:
            self.detailed_panel.set_parts(parts)

    def _on_detailed_parts_change(self, parts: List[Dict]):
        """Callback - zmiana detali w panelu szczegolowym (edycja kosztow)"""
        logger.info(f"[OrderWindow] Detailed parts changed: {len(parts)} items")

        # Przelicz koszty z listy detali
        total_lm = 0.0
        total_bending = 0.0
        total_additional = 0.0
        total_weight = 0.0
        total_qty = 0

        for p in parts:
            qty = int(p.get('quantity', 1) or 1)
            total_qty += qty
            total_lm += float(p.get('lm_cost', 0) or 0) * qty
            total_bending += float(p.get('bending_cost', 0) or 0) * qty
            total_additional += float(p.get('additional', 0) or 0) * qty
            total_weight += float(p.get('weight', 0) or 0) * qty

        # Oblicz subtotal i total
        subtotal = total_lm + total_bending + total_additional

        # Pobierz parametry narzutu z params_panel jeśli dostępny
        markup_pct = 0.0
        if hasattr(self, 'params_panel'):
            try:
                markup_pct = float(self.params_panel.get_params().get('markup_percent', 0) or 0)
            except:
                pass

        markup_value = subtotal * (markup_pct / 100.0)
        total_cost = subtotal + markup_value

        # Aktualizuj summary panel
        cost_result = {
            'material_cost': total_lm * 0.6,  # Szacuj 60% L+M to materiał
            'cutting_cost': total_lm * 0.4,   # Szacuj 40% L+M to cięcie
            'foil_cost': 0.0,
            'piercing_cost': 0.0,
            'operational_cost': total_additional,
            'subtotal': subtotal,
            'technology_cost': total_bending,
            'packaging_cost': 0.0,
            'transport_cost': 0.0,
            'markup_percent': markup_pct,
            'markup_value': markup_value,
            'total_cost': total_cost,
            'total_sheets': self.nesting_results.get('total_sheets', 0),
            'average_efficiency': self.nesting_results.get('average_efficiency', 0),
            'total_weight_kg': total_weight,
        }

        if hasattr(self, 'summary_panel'):
            self.summary_panel.update_costs(cost_result)

        self.lbl_status.configure(
            text=f"Detali: {len(parts)} | Qty: {total_qty} | L+M: {total_lm:.2f} | Total: {total_cost:.2f} PLN"
        )

    def _on_loading_complete(self, count: int):
        """Callback - zakończenie ładowania plików"""
        logger.info(f"[OrderWindow] Loading complete: {count} parts loaded")
        self._bring_to_front()  # Przywróć focus po załadowaniu

    def _on_params_change(self, params: Dict):
        """Callback - zmiana parametrów - automatycznie przelicza koszty"""
        logger.debug(f"[OrderWindow] Params changed: {params}")
        # Automatyczne przeliczenie po zmianie parametrów (w tym narzutu)
        self._recalculate()

    def _run_nesting(self):
        """Uruchom nesting"""
        parts = self.parts_panel.get_parts()
        if not parts:
            self._show_message("warning", "Uwaga", "Dodaj detale przed uruchomieniem nestingu")
            return

        logger.info(f"[OrderWindow] Starting nesting with {len(parts)} parts")

        try:
            from nesting_window import NestingWindow

            nesting_win = NestingWindow(
                self,
                context_type="order",
                context_id=self.order_id,
                parts_data=parts,
                on_complete_callback=self._on_nesting_complete
            )
            nesting_win.state('zoomed')

            # Wymuszenie focusu na okno nesting
            nesting_win.after(100, lambda: self._focus_nesting_window(nesting_win))

        except ImportError as e:
            logger.error(f"[OrderWindow] Cannot import NestingWindow: {e}")
            messagebox.showerror("Błąd", f"Nie można uruchomić modułu Nesting: {e}")

    def _focus_nesting_window(self, nesting_win):
        """Wymuś focus na okno nesting"""
        try:
            nesting_win.attributes('-topmost', True)
            nesting_win.lift()
            nesting_win.focus_force()
            nesting_win.after(200, lambda: nesting_win.attributes('-topmost', False))
            logger.debug("[OrderWindow] Nesting window focused")
        except Exception as e:
            logger.error(f"[OrderWindow] Error focusing nesting window: {e}")

    def _on_nesting_complete(self, results: Dict):
        """Callback - zakończenie nestingu"""
        logger.info(f"[OrderWindow] Nesting complete, received results")

        self.nesting_results = results

        # Aktualizuj panel wyników
        if 'sheets' in results:
            sheets_data = []
            for i, sheet in enumerate(results['sheets']):
                sheets_data.append({
                    'material': results.get('material', '?'),
                    'thickness_mm': results.get('thickness', 0),
                    'efficiency': sheet.get('efficiency', 0),
                    'parts_count': sheet.get('parts_count', 0),
                    'total_cost': sheet.get('cost', 0)
                })
            self.results_panel.update_results(sheets_data)

        # Zapisz obrazy arkuszy (jako base64 do JSON)
        if 'sheet_images' in results and results['sheet_images']:
            import base64
            self.nesting_results['sheet_images_base64'] = []
            for img_data in results['sheet_images']:
                if img_data.get('image_bytes'):
                    b64 = base64.b64encode(img_data['image_bytes']).decode('utf-8')
                    self.nesting_results['sheet_images_base64'].append({
                        'tab_name': img_data.get('tab_name', ''),
                        'sheet_index': img_data.get('sheet_index', 0),
                        'image_base64': b64
                    })
            logger.info(f"[OrderWindow] Stored {len(self.nesting_results['sheet_images_base64'])} sheet images as base64")
            # Usun bytes z wynikow (nie serializuje sie do JSON)
            del self.nesting_results['sheet_images']

        # Przekaz wyniki do panelu (dla popup)
        self.results_panel.set_nesting_results(self.nesting_results)

        # Aktualizuj koszty
        if 'cost_result' in results:
            self.cost_result = results['cost_result']
            self.summary_panel.update_costs(self.cost_result)

        # Zmień status
        self.lbl_status.configure(text="Nesting zakończony - wyniki zaktualizowane")

        # Włącz dropdown alokacji w panelu detali (teraz dostępny po nestingu)
        if hasattr(self, 'detailed_panel') and self.detailed_panel:
            self.detailed_panel.enable_allocation_model()
            logger.info("[OrderWindow] Allocation model enabled after nesting")

        self._bring_to_front()

    def _recalculate(self):
        """Przelicz koszty"""
        parts = self.parts_panel.get_parts()
        if not parts:
            self._show_message("warning", "Uwaga", "Brak detali do przeliczenia")
            return

        logger.info(f"[CostCalc] ========== ROZPOCZECIE KALKULACJI ==========")
        logger.info(f"[CostCalc] Liczba detali: {len(parts)}")
        params = self.params_panel.get_params()

        # Sprawdź czy mamy wyniki nestingu z utylizacją
        has_nesting = bool(self.nesting_results and self.nesting_results.get('sheets'))
        allocation_model = params.get('allocation_model', 'PROPORTIONAL')

        logger.info(f"[CostCalc] Parametry: wariant={params.get('variant', 'A')}, alokacja={allocation_model}")
        logger.info(f"[CostCalc] Nesting: {has_nesting}, Narzut: {params.get('markup_percent', 0)}%")
        logger.info(f"[CostCalc] Wlaczone koszty: material={params.get('include_material')}, ciecie={params.get('include_cutting')}, folia={params.get('include_foil')}, piercing={params.get('include_piercing')}, operacyjne={params.get('include_operational')}")

        try:
            from quotations.pricing.cost_calculator import calculate_quick_estimate

            groups = self.parts_panel.get_parts_by_group()
            logger.info(f"[CostCalc] Grupy materialowe: {len(groups)}")

            # Pobierz utylizację z nestingu jeśli dostępna
            nesting_efficiency = 0.75  # Domyślna utylizacja
            nesting_sheets = 0
            if has_nesting:
                sheets = self.nesting_results.get('sheets', [])
                if sheets:
                    efficiencies = [s.get('efficiency', 0.75) for s in sheets if s.get('efficiency')]
                    if efficiencies:
                        nesting_efficiency = sum(efficiencies) / len(efficiencies)
                    nesting_sheets = len(sheets)
                    logger.info(f"[CostCalc] Utylizacja z nestingu: {nesting_efficiency*100:.1f}%, arkuszy: {nesting_sheets}")

            total_result = {
                'material_cost': 0, 'cutting_cost': 0, 'foil_cost': 0,
                'piercing_cost': 0, 'operational_cost': 0,
                'technology_cost': params.get('technology_cost', 0),
                'packaging_cost': params.get('packaging_cost', 0),
                'transport_cost': params.get('transport_cost', 0),
                'total_weight_kg': 0, 'total_sheets': nesting_sheets if nesting_sheets else 0,
                'average_efficiency': nesting_efficiency
            }

            for (material, thickness), group_parts in groups.items():
                logger.info(f"[CostCalc] --- Grupa: {material} {thickness}mm ({len(group_parts)} detali) ---")

                # Loguj szczegoly detali w grupie
                total_qty = sum(p.get('quantity', 1) for p in group_parts)
                total_area_mm2 = sum(p.get('width', 0) * p.get('height', 0) * p.get('quantity', 1) for p in group_parts)
                logger.info(f"[CostCalc]   Laczna ilosc: {total_qty}, Powierzchnia BB: {total_area_mm2/1e6:.3f} m2")

                estimate = calculate_quick_estimate(group_parts, material, thickness)

                logger.info(f"[CostCalc]   Szacunek kosztow:")
                logger.info(f"[CostCalc]     - Material:    {estimate.get('material_cost', 0):>10.2f} PLN")
                logger.info(f"[CostCalc]     - Ciecie:      {estimate.get('cutting_cost', 0):>10.2f} PLN")
                logger.info(f"[CostCalc]     - Folia:       {estimate.get('foil_cost', 0):>10.2f} PLN")
                logger.info(f"[CostCalc]     - Piercing:    {estimate.get('piercing_cost', 0):>10.2f} PLN")
                logger.info(f"[CostCalc]     - Operacyjne:  {estimate.get('operational_cost', 0):>10.2f} PLN")
                logger.info(f"[CostCalc]     - Waga:        {estimate.get('total_weight_kg', 0):>10.2f} kg")
                logger.info(f"[CostCalc]     - Arkusze:     {estimate.get('estimated_sheets', 0):>10}")

                foil_auto_enabled = False
                if self.cost_service:
                    try:
                        foil_auto_enabled = self.cost_service.repository.should_auto_enable_foil_removal(material, thickness)
                        if foil_auto_enabled:
                            logger.info(f"[CostCalc]   Auto-folia wlaczona dla {material} {thickness}mm")
                    except Exception as e:
                        logger.warning(f"[CostCalc]   Blad sprawdzania auto-folii: {e}")

                # Koszty materiału z uwzględnieniem utylizacji
                if params.get('include_material', True):
                    base_material_cost = estimate.get('material_cost', 0)

                    # Metoda alokacji kosztów materiału
                    if allocation_model == "UNIT" and nesting_efficiency > 0:
                        # Prostokąt otaczający: równy podział kosztów
                        material_cost = base_material_cost / nesting_efficiency
                        logger.info(f"[CostCalc]   Mat. (prostokąt otaczający): {base_material_cost:.2f} / {nesting_efficiency:.2f} = {material_cost:.2f} PLN")
                    elif allocation_model == "PER_SHEET" and nesting_efficiency > 0:
                        # Na arkusz: pełny koszt arkusza
                        material_cost = base_material_cost / nesting_efficiency
                        logger.info(f"[CostCalc]   Mat. (na arkusz): {base_material_cost:.2f} / {nesting_efficiency:.2f} = {material_cost:.2f} PLN")
                    else:
                        # Proporcjonalny: bez zmiany
                        material_cost = base_material_cost
                        logger.info(f"[CostCalc]   Mat. (proporcjonalny): {material_cost:.2f} PLN")

                    total_result['material_cost'] += material_cost

                if params.get('include_cutting', True):
                    total_result['cutting_cost'] += estimate.get('cutting_cost', 0)
                # Folia: tylko gdy checkbox włączony I materiał wymaga folii
                if params.get('include_foil', True) and foil_auto_enabled:
                    total_result['foil_cost'] += estimate.get('foil_cost', 0)
                if params.get('include_piercing', True):
                    total_result['piercing_cost'] += estimate.get('piercing_cost', 0)
                if params.get('include_operational', True):
                    total_result['operational_cost'] += estimate.get('operational_cost', 0)

                total_result['total_weight_kg'] += estimate.get('total_weight_kg', 0)
                if not nesting_sheets:
                    total_result['total_sheets'] += estimate.get('estimated_sheets', 0)

            total_result['subtotal'] = sum([
                total_result['material_cost'], total_result['cutting_cost'],
                total_result['foil_cost'], total_result['piercing_cost'],
                total_result['operational_cost']
            ])

            # Suma przed narzutem
            base_total = total_result['subtotal'] + sum([
                total_result['technology_cost'], total_result['packaging_cost'],
                total_result['transport_cost']
            ])

            # Narzut procentowy
            markup_pct = params.get('markup_percent', 0)
            markup_value = base_total * (markup_pct / 100.0)
            total_result['markup_percent'] = markup_pct
            total_result['markup_value'] = markup_value

            total_result['total_cost'] = base_total + markup_value

            # Podsumowanie
            logger.info(f"[CostCalc] ========== PODSUMOWANIE KALKULACJI ==========")
            logger.info(f"[CostCalc] KOSZTY PRODUKCYJNE:")
            logger.info(f"[CostCalc]   Material:      {total_result['material_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   Ciecie:        {total_result['cutting_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   Folia:         {total_result['foil_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   Piercing:      {total_result['piercing_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   Operacyjne:    {total_result['operational_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   -----------------------------------")
            logger.info(f"[CostCalc]   SUMA PRODUKCJI:{total_result['subtotal']:>12.2f} PLN")
            logger.info(f"[CostCalc] KOSZTY DODATKOWE:")
            logger.info(f"[CostCalc]   Technologia:   {total_result['technology_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   Opakowania:    {total_result['packaging_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   Transport:     {total_result['transport_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc]   -----------------------------------")
            logger.info(f"[CostCalc]   Narzut ({markup_pct:g}%): {markup_value:>12.2f} PLN")
            logger.info(f"[CostCalc]   ===================================")
            logger.info(f"[CostCalc]   RAZEM:         {total_result['total_cost']:>12.2f} PLN")
            logger.info(f"[CostCalc] STATYSTYKI:")
            logger.info(f"[CostCalc]   Arkuszy:       {total_result['total_sheets']:>12}")
            logger.info(f"[CostCalc]   Waga:          {total_result['total_weight_kg']:>12.2f} kg")
            logger.info(f"[CostCalc] ============================================")

            self.cost_result = total_result
            self.summary_panel.update_costs(total_result)

            if has_nesting:
                status_msg = f"Koszty z nestingu (utylizacja: {nesting_efficiency*100:.0f}%, arkuszy: {nesting_sheets})"
            else:
                status_msg = "Koszty przeliczone (szacunek bez nestingu)"
            if markup_pct != 0:
                status_msg += f" | Narzut: {markup_pct:+g}%"
            if self.cost_service:
                status_msg += " | CostService"
            self.lbl_status.configure(text=status_msg)

        except Exception as e:
            logger.error(f"[CostCalc] BLAD KALKULACJI: {e}", exc_info=True)
            self._show_message("error", "Błąd", f"Błąd kalkulacji: {e}")

    def _show_message(self, msg_type: str, title: str, message: str):
        """Pokaż MessageBox i przywróć focus"""
        logger.debug(f"[OrderWindow] Showing {msg_type}: {title}")
        if msg_type == "info":
            messagebox.showinfo(title, message, parent=self)
        elif msg_type == "warning":
            messagebox.showwarning(title, message, parent=self)
        elif msg_type == "error":
            messagebox.showerror(title, message, parent=self)

        # Przywróć focus po zamknięciu MessageBox
        self.after(50, self._bring_to_front)

    def _save_order(self):
        """Zapisz zamówienie"""
        logger.info(f"[OrderWindow] === SAVE ORDER START === {self.order_id}")

        parts = self.parts_panel.get_parts()
        info = self.info_panel.get_data()
        params = self.params_panel.get_params()

        logger.debug(f"[OrderWindow] Parts count: {len(parts)}")
        logger.debug(f"[OrderWindow] Order info: {info}")

        if not parts:
            logger.warning("[OrderWindow] No parts to save")
            self._show_message("warning", "Uwaga", "Dodaj detale przed zapisem")
            return

        if not info.get('name'):
            logger.warning("[OrderWindow] No order name")
            self._show_message("warning", "Uwaga", "Podaj nazwę zamówienia")
            return

        logger.info(f"[OrderWindow] Saving order: {self.order_id}")
        logger.debug(f"[OrderWindow] Order name: {info['name']}")
        logger.debug(f"[OrderWindow] Client: {info.get('client', 'BRAK')}")

        try:
            # Przygotuj dane zamówienia
            order_data = {
                'id': self.order_id,
                'name': info['name'],
                'client': info.get('client', ''),
                'customer_name': info.get('client', ''),  # alternatywna kolumna
                'date_in': info.get('date_in', date.today().isoformat()),
                'date_due': info.get('date_due'),
                'status': info.get('status', OrderStatus.DEFAULT),
                'priority': info.get('priority', 'Normalny'),
                'notes': info.get('notes', ''),
                'parts_count': len(parts),
                'items': parts,
                'cost_params': params,
                'cost_result': self.cost_result,
                'nesting_results': self.nesting_results,
                'updated_at': datetime.now().isoformat()
            }

            logger.debug(f"[OrderWindow] Order data prepared: {list(order_data.keys())}")

            # Zapisz do repozytorium
            success = self._save_to_repository(order_data)

            if success:
                logger.info(f"[OrderWindow] === ORDER SAVED SUCCESSFULLY === {self.order_id}")
                self._show_message("info", "Sukces", f"Zamówienie '{info['name']}' zapisane")
                self.lbl_status.configure(text=f"Zapisano: {info['name']}")

                # Callback do głównego okna
                if self.on_save_callback:
                    logger.debug("[OrderWindow] Calling on_save_callback")
                    self.on_save_callback(order_data)
            else:
                logger.error(f"[OrderWindow] === SAVE FAILED === {self.order_id}")
                self._show_message("error", "Błąd", "Nie udało się zapisać zamówienia. Sprawdź log.")

        except Exception as e:
            logger.error(f"[OrderWindow] === SAVE EXCEPTION === {e}", exc_info=True)
            self._show_message("error", "Błąd", f"Błąd zapisu: {e}")

    def _save_to_repository(self, order_data: Dict) -> bool:
        """Zapisz zamówienie do repozytorium"""
        try:
            from orders.repository import OrderRepository
            from core.supabase_client import get_supabase_client

            client = get_supabase_client()
            repo = OrderRepository(client)

            # Sprawdź czy istnieje
            existing = repo.get_by_id(order_data['id'])
            if existing:
                repo.update(order_data['id'], order_data)
            else:
                repo.create(order_data)

            return True

        except ImportError:
            # Fallback - zapisz lokalnie do JSON
            logger.warning("[OrderWindow] OrderRepository not available, saving to local JSON")
            return self._save_to_local_json(order_data)

        except Exception as e:
            logger.error(f"[OrderWindow] Repository error: {e}")
            return self._save_to_local_json(order_data)

    def _save_to_local_json(self, order_data: Dict) -> bool:
        """Zapisz zamówienie do lokalnego pliku JSON"""
        try:
            orders_dir = Path("data/orders")
            orders_dir.mkdir(parents=True, exist_ok=True)

            filepath = orders_dir / f"{order_data['id']}.json"

            # Usuń nietypowe obiekty przed zapisem
            save_data = self._prepare_for_json(order_data)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"[OrderWindow] Order saved to JSON: {filepath}")
            return True

        except Exception as e:
            logger.error(f"[OrderWindow] Error saving to JSON: {e}")
            return False

    def _prepare_for_json(self, data: Dict) -> Dict:
        """Przygotuj dane do serializacji JSON"""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._prepare_for_json(value)
            elif isinstance(value, list):
                result[key] = [
                    self._prepare_for_json(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif hasattr(value, '__dict__'):
                result[key] = str(value)
            else:
                result[key] = value
        return result

    def _generate_documents(self):
        """Generuj dokumenty"""
        logger.info("[OrderWindow] Document generation requested")
        self._show_message("info", "Dokumenty", "Generowanie dokumentów - w przygotowaniu")

    def _load_order_data(self):
        """Wczytaj dane zamówienia"""
        logger.info(f"[OrderWindow] Loading order data: {self.order_id}")
        logger.debug(f"[OrderWindow] Initial order_data keys: {list(self.order_data.keys())}")

        # Jeśli brak items w order_data, pobierz pełne dane z repozytorium
        if not self.order_data.get('items'):
            logger.info(f"[OrderWindow] No items in order_data, fetching from repository...")
            try:
                from orders.repository import OrderRepository
                from core.supabase_client import get_supabase_client

                client = get_supabase_client()
                repo = OrderRepository(client)
                full_data = repo.get_by_id(self.order_id)

                if full_data:
                    logger.info(f"[OrderWindow] Loaded full data from repository, items: {len(full_data.get('items', []))}")
                    # Zachowaj oryginalne dane i dodaj items
                    self.order_data.update(full_data)
                else:
                    logger.warning(f"[OrderWindow] Could not load order {self.order_id} from repository")

            except Exception as e:
                logger.error(f"[OrderWindow] Error loading from repository: {e}")

        # Załaduj items do listy
        items = self.order_data.get('items', [])
        if items:
            logger.info(f"[OrderWindow] Setting {len(items)} parts in parts_panel")
            self.parts_panel.set_parts(items)
            # Synchronizuj z panelem szczegolowym
            if hasattr(self, 'detailed_panel') and self.detailed_panel:
                self.detailed_panel.set_parts(items)
        else:
            logger.warning(f"[OrderWindow] No items to load for order {self.order_id}")

        # Załaduj dane zamówienia do panelu info
        self.info_panel.set_data(self.order_data)

        # Załaduj wyniki nestingu (jeśli są)
        nesting_results = self.order_data.get('nesting_results', {})
        if nesting_results:
            logger.info(f"[OrderWindow] Loading nesting results from saved data")
            self.nesting_results = nesting_results
            # TODO: Odtwórz wyświetlanie wyników nestingu w results_panel

        # Załaduj wyniki kosztów (jeśli są)
        cost_result = self.order_data.get('cost_result')
        if cost_result:
            logger.info(f"[OrderWindow] Loading cost result from saved data")
            self.cost_result = cost_result
            self.summary_panel.update_costs(cost_result)

    def _open_settings(self):
        """Otwórz dialog ustawień"""
        from orders.gui.settings_dialog import LayerSettingsDialog, CostSettingsDialog

        # Menu wyboru typu ustawień
        settings_menu = ctk.CTkToplevel(self)
        settings_menu.title("Ustawienia")
        settings_menu.geometry("300x200")
        settings_menu.configure(fg_color=Theme.BG_DARK)
        settings_menu.transient(self)
        settings_menu.grab_set()

        # Wyśrodkuj
        settings_menu.update_idletasks()
        x = (settings_menu.winfo_screenwidth() - 300) // 2
        y = (settings_menu.winfo_screenheight() - 200) // 2
        settings_menu.geometry(f"+{x}+{y}")

        ctk.CTkLabel(settings_menu, text="Wybierz typ ustawień",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(pady=20)

        def open_layers():
            settings_menu.destroy()
            LayerSettingsDialog(self, on_save=self._on_settings_saved)

        def open_costs():
            settings_menu.destroy()
            CostSettingsDialog(self, on_save=self._on_settings_saved)

        ctk.CTkButton(settings_menu, text="🔶 Warstwy i kolory DXF",
                     command=open_layers, width=200, height=40).pack(pady=5)
        ctk.CTkButton(settings_menu, text="💰 Parametry kosztów",
                     command=open_costs, width=200, height=40).pack(pady=5)
        ctk.CTkButton(settings_menu, text="Anuluj",
                     command=settings_menu.destroy, fg_color=Theme.BG_INPUT,
                     width=100, height=30).pack(pady=10)

    def _on_settings_saved(self, settings: dict):
        """Callback po zapisaniu ustawień"""
        logger.info(f"[OrderWindow] Settings saved: {list(settings.keys())}")
        self._update_status("Ustawienia zapisane")

    def _close(self):
        """Zamknij okno"""
        logger.info(f"[OrderWindow] Closing order window: {self.order_id}")

        # Zapisz pozycję splittera przed zamknięciem
        self._save_splitter_position()

        self.parts_panel.destroy()  # Cleanup thumbnail generator
        self.destroy()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    app = OrderWindow(root)
    app.mainloop()
