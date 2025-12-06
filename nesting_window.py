"""
NewERP - Nesting Window
========================
Pełnoekranowy moduł nestingu z możliwością:
- Wczytywania plików DXF z folderu
- Grupowania po materiale i grubości
- Wizualizacji rozkroju na arkuszach
- Przesyłania wyników do Oferty lub Zamówienia

Konteksty:
- Test: niezależny nesting bez zapisu
- Oferta: powiązany z quotation_id
- Zamówienie: powiązany z order_id
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass

import customtkinter as ctk
from tkinter import filedialog, messagebox
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Import modułów projektu
try:
    from quotations.utils.dxf_loader import load_dxf, DXFPart
    from quotations.utils.name_parser import parse_filename_with_folder_context, reload_rules
    from quotations.gui.nesting_tabs_panel import NestingTabsPanel, Theme
    from quotations.gui.regex_editor_panel import RegexEditorWindow
    HAS_MODULES = True
except ImportError as e:
    logger.error(f"Import error: {e}")
    HAS_MODULES = False

# Import motion dynamics modules
try:
    from costing.motion.motion_planner import MachineProfile, estimate_motion_time, m_min_to_mm_s
    from costing.toolpath.dxf_extractor import extract_motion_segments
    HAS_MOTION_DYNAMICS = True
except ImportError as e:
    logger.warning(f"Motion dynamics not available: {e}")
    HAS_MOTION_DYNAMICS = False


@dataclass
class MachineDynamicsSettings:
    """Machine dynamics settings for time calculation."""
    use_dynamic_method: bool = True  # True = dynamic, False = classic
    max_accel_mm_s2: float = 2000.0
    square_corner_velocity_mm_s: float = 50.0
    max_rapid_mm_s: float = 500.0
    junction_deviation_mm: float = 0.05
    use_junction_deviation: bool = False


class Theme:
    """Paleta kolorów"""
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


class MachineDynamicsDialog(ctk.CTkToplevel):
    """Dialog ustawień dynamiki maszyny dla obliczeń czasu cięcia."""

    def __init__(self, parent, settings: MachineDynamicsSettings = None,
                 on_settings_change=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.on_settings_change = on_settings_change
        self.settings = settings or MachineDynamicsSettings()

        # Konfiguracja okna
        self.title("Ustawienia dynamiki maszyny")
        self.configure(fg_color=Theme.BG_DARK)
        self.geometry("450x550")
        self.resizable(False, False)

        # Wycentruj okno
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 450) // 2
        y = (self.winfo_screenheight() - 550) // 2
        self.geometry(f"+{x}+{y}")

        # Modal
        self.transient(parent)
        self.grab_set()

        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        """Buduj interfejs dialogu."""
        # Header
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        header.pack(fill="x", padx=15, pady=(15, 10))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="⚙️ PARAMETRY DYNAMIKI MASZYNY",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.ACCENT_INFO
        ).pack(side="left", padx=15, pady=15)

        # Main content
        content = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        content.pack(fill="both", expand=True, padx=15, pady=10)

        # === METODA OBLICZANIA ===
        method_frame = ctk.CTkFrame(content, fg_color="transparent")
        method_frame.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(method_frame, text="Metoda obliczania czasu:",
                    font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")

        self.method_var = ctk.StringVar(value="dynamic")

        rb_frame = ctk.CTkFrame(method_frame, fg_color="transparent")
        rb_frame.pack(fill="x", pady=5)

        self.rb_dynamic = ctk.CTkRadioButton(
            rb_frame, text="Dynamiczna (Motion Planning)",
            variable=self.method_var, value="dynamic",
            font=ctk.CTkFont(size=11)
        )
        self.rb_dynamic.pack(side="left", padx=(0, 20))

        self.rb_classic = ctk.CTkRadioButton(
            rb_frame, text="Klasyczna (L/V)",
            variable=self.method_var, value="classic",
            font=ctk.CTkFont(size=11)
        )
        self.rb_classic.pack(side="left")

        # Separator
        ctk.CTkFrame(content, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=20, pady=10)

        # === PARAMETRY KINEMATYKI ===
        ctk.CTkLabel(content, text="Parametry kinematyki maszyny:",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=Theme.ACCENT_WARNING).pack(anchor="w", padx=20, pady=(5, 10))

        params_frame = ctk.CTkFrame(content, fg_color="transparent")
        params_frame.pack(fill="x", padx=20)

        # Przyspieszenie
        row1 = ctk.CTkFrame(params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=3)
        ctk.CTkLabel(row1, text="Przyspieszenie max:", width=160, anchor="w",
                    font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_accel = ctk.CTkEntry(row1, width=80, font=ctk.CTkFont(size=11))
        self.entry_accel.pack(side="left", padx=5)
        ctk.CTkLabel(row1, text="mm/s²", font=ctk.CTkFont(size=10),
                    text_color=Theme.TEXT_MUTED).pack(side="left")

        # V narożnik
        row2 = ctk.CTkFrame(params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=3)
        ctk.CTkLabel(row2, text="Prędkość w narożniku 90°:", width=160, anchor="w",
                    font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_corner = ctk.CTkEntry(row2, width=80, font=ctk.CTkFont(size=11))
        self.entry_corner.pack(side="left", padx=5)
        ctk.CTkLabel(row2, text="mm/s", font=ctk.CTkFont(size=10),
                    text_color=Theme.TEXT_MUTED).pack(side="left")

        # V rapid
        row3 = ctk.CTkFrame(params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=3)
        ctk.CTkLabel(row3, text="Prędkość szybka (rapid):", width=160, anchor="w",
                    font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_rapid = ctk.CTkEntry(row3, width=80, font=ctk.CTkFont(size=11))
        self.entry_rapid.pack(side="left", padx=5)
        ctk.CTkLabel(row3, text="mm/s", font=ctk.CTkFont(size=10),
                    text_color=Theme.TEXT_MUTED).pack(side="left")

        # Junction deviation
        row4 = ctk.CTkFrame(params_frame, fg_color="transparent")
        row4.pack(fill="x", pady=3)
        ctk.CTkLabel(row4, text="Junction deviation:", width=160, anchor="w",
                    font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_junction = ctk.CTkEntry(row4, width=80, font=ctk.CTkFont(size=11))
        self.entry_junction.pack(side="left", padx=5)
        ctk.CTkLabel(row4, text="mm", font=ctk.CTkFont(size=10),
                    text_color=Theme.TEXT_MUTED).pack(side="left")

        # Checkbox Junction Deviation
        self.use_junction_var = ctk.BooleanVar(value=False)
        self.cb_junction = ctk.CTkCheckBox(
            params_frame,
            text="Użyj modelu Junction Deviation (Klipper/Marlin)",
            variable=self.use_junction_var,
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY
        )
        self.cb_junction.pack(anchor="w", pady=(10, 5))

        # Separator
        ctk.CTkFrame(content, height=1, fg_color=Theme.BG_INPUT).pack(fill="x", padx=20, pady=10)

        # === PRESETY ===
        ctk.CTkLabel(content, text="Presety maszyn:",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=Theme.ACCENT_SUCCESS).pack(anchor="w", padx=20, pady=(5, 10))

        presets_frame = ctk.CTkFrame(content, fg_color="transparent")
        presets_frame.pack(fill="x", padx=20)

        btn_fiber = ctk.CTkButton(
            presets_frame, text="🔵 Fiber 3kW", width=100, height=35,
            fg_color="#3b82f6", hover_color="#2563eb",
            command=lambda: self._load_preset("fiber_3kw")
        )
        btn_fiber.pack(side="left", padx=5)

        btn_fiber6 = ctk.CTkButton(
            presets_frame, text="🔷 Fiber 6kW", width=100, height=35,
            fg_color="#06b6d4", hover_color="#0891b2",
            command=lambda: self._load_preset("fiber_6kw")
        )
        btn_fiber6.pack(side="left", padx=5)

        btn_co2 = ctk.CTkButton(
            presets_frame, text="🟠 CO₂", width=80, height=35,
            fg_color="#f59e0b", hover_color="#d97706",
            command=lambda: self._load_preset("co2")
        )
        btn_co2.pack(side="left", padx=5)

        btn_plasma = ctk.CTkButton(
            presets_frame, text="🔴 Plazma", width=80, height=35,
            fg_color="#ef4444", hover_color="#dc2626",
            command=lambda: self._load_preset("plasma")
        )
        btn_plasma.pack(side="left", padx=5)

        # Info o presetach
        info_text = ctk.CTkLabel(
            content,
            text="Fiber 3kW: 2000 mm/s², 50 mm/s corner, 500 mm/s rapid\n"
                 "Fiber 6kW: 3000 mm/s², 60 mm/s corner, 600 mm/s rapid\n"
                 "CO₂: 1200 mm/s², 40 mm/s corner, 300 mm/s rapid\n"
                 "Plazma: 1500 mm/s², 30 mm/s corner, 400 mm/s rapid",
            font=ctk.CTkFont(size=9),
            text_color=Theme.TEXT_MUTED,
            justify="left"
        )
        info_text.pack(anchor="w", padx=20, pady=(10, 5))

        # === PRZYCISKI ===
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=15)

        btn_cancel = ctk.CTkButton(
            btn_frame, text="Anuluj", width=100, height=35,
            fg_color=Theme.BG_INPUT, hover_color=Theme.BG_CARD_HOVER,
            command=self.destroy
        )
        btn_cancel.pack(side="right", padx=5)

        btn_apply = ctk.CTkButton(
            btn_frame, text="Zastosuj", width=100, height=35,
            fg_color=Theme.ACCENT_SUCCESS, hover_color="#16a34a",
            command=self._apply_settings
        )
        btn_apply.pack(side="right", padx=5)

    def _load_current_settings(self):
        """Załaduj aktualne ustawienia do formularza."""
        self.method_var.set("dynamic" if self.settings.use_dynamic_method else "classic")

        self.entry_accel.delete(0, "end")
        self.entry_accel.insert(0, str(int(self.settings.max_accel_mm_s2)))

        self.entry_corner.delete(0, "end")
        self.entry_corner.insert(0, str(int(self.settings.square_corner_velocity_mm_s)))

        self.entry_rapid.delete(0, "end")
        self.entry_rapid.insert(0, str(int(self.settings.max_rapid_mm_s)))

        self.entry_junction.delete(0, "end")
        self.entry_junction.insert(0, str(self.settings.junction_deviation_mm))

        self.use_junction_var.set(self.settings.use_junction_deviation)

    def _load_preset(self, preset_name: str):
        """Załaduj preset maszyny."""
        presets = {
            "fiber_3kw": (2000.0, 50.0, 500.0, 0.05),
            "fiber_6kw": (3000.0, 60.0, 600.0, 0.03),
            "co2": (1200.0, 40.0, 300.0, 0.1),
            "plasma": (1500.0, 30.0, 400.0, 0.08),
        }

        if preset_name in presets:
            accel, corner, rapid, jd = presets[preset_name]

            self.entry_accel.delete(0, "end")
            self.entry_accel.insert(0, str(int(accel)))

            self.entry_corner.delete(0, "end")
            self.entry_corner.insert(0, str(int(corner)))

            self.entry_rapid.delete(0, "end")
            self.entry_rapid.insert(0, str(int(rapid)))

            self.entry_junction.delete(0, "end")
            self.entry_junction.insert(0, str(jd))

    def _apply_settings(self):
        """Zastosuj ustawienia i zamknij dialog."""
        try:
            self.settings.use_dynamic_method = (self.method_var.get() == "dynamic")
            self.settings.max_accel_mm_s2 = float(self.entry_accel.get())
            self.settings.square_corner_velocity_mm_s = float(self.entry_corner.get())
            self.settings.max_rapid_mm_s = float(self.entry_rapid.get())
            self.settings.junction_deviation_mm = float(self.entry_junction.get())
            self.settings.use_junction_deviation = self.use_junction_var.get()

            if self.on_settings_change:
                self.on_settings_change(self.settings)

            self.destroy()

        except ValueError as e:
            from tkinter import messagebox
            messagebox.showerror("Błąd", f"Nieprawidłowa wartość: {e}")

    def get_settings(self) -> MachineDynamicsSettings:
        """Pobierz aktualne ustawienia."""
        return self.settings

    def get_machine_profile(self) -> 'MachineProfile':
        """Pobierz MachineProfile dla motion plannera."""
        if HAS_MOTION_DYNAMICS:
            return MachineProfile(
                max_accel_mm_s2=self.settings.max_accel_mm_s2,
                max_rapid_mm_s=self.settings.max_rapid_mm_s,
                square_corner_velocity_mm_s=self.settings.square_corner_velocity_mm_s,
                junction_deviation_mm=self.settings.junction_deviation_mm,
                use_junction_deviation=self.settings.use_junction_deviation
            )
        return None


class ContextSelector(ctk.CTkFrame):
    """Wybór kontekstu: Test / Oferta / Zamówienie"""

    def __init__(self, parent, on_context_change=None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, corner_radius=8, **kwargs)

        self.on_context_change = on_context_change
        self.context_type = ctk.StringVar(value="test")
        self.context_id = None

        self._setup_ui()

    def _setup_ui(self):
        # Tytuł
        title = ctk.CTkLabel(
            self,
            text="Kontekst",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_SECONDARY
        )
        title.pack(pady=(10, 5), padx=15, anchor="w")

        # Radio buttons
        radio_frame = ctk.CTkFrame(self, fg_color="transparent")
        radio_frame.pack(fill="x", padx=15, pady=5)

        self.rb_test = ctk.CTkRadioButton(
            radio_frame,
            text="Test",
            variable=self.context_type,
            value="test",
            command=self._on_change,
            font=ctk.CTkFont(size=11)
        )
        self.rb_test.pack(side="left", padx=(0, 15))

        self.rb_quotation = ctk.CTkRadioButton(
            radio_frame,
            text="Oferta",
            variable=self.context_type,
            value="quotation",
            command=self._on_change,
            font=ctk.CTkFont(size=11)
        )
        self.rb_quotation.pack(side="left", padx=15)

        self.rb_order = ctk.CTkRadioButton(
            radio_frame,
            text="Zamówienie",
            variable=self.context_type,
            value="order",
            command=self._on_change,
            font=ctk.CTkFont(size=11)
        )
        self.rb_order.pack(side="left", padx=15)

        # Wybór ID (ukryty dla Test)
        self.id_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.id_frame.pack(fill="x", padx=15, pady=(5, 10))

        self.id_label = ctk.CTkLabel(
            self.id_frame,
            text="ID:",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.id_label.pack(side="left")

        self.id_combo = ctk.CTkComboBox(
            self.id_frame,
            values=["Nowy..."],
            width=200,
            command=self._on_id_change
        )
        self.id_combo.set("Nowy...")
        self.id_combo.pack(side="left", padx=10)

        self.btn_load = ctk.CTkButton(
            self.id_frame,
            text="Wczytaj",
            width=80,
            height=28,
            fg_color=Theme.ACCENT_PRIMARY,
            command=self._load_context
        )
        self.btn_load.pack(side="left")

        # Ukryj ID frame dla Test
        self.id_frame.pack_forget()

    def _on_change(self):
        context = self.context_type.get()

        if context == "test":
            self.id_frame.pack_forget()
            self.context_id = None
        else:
            self.id_frame.pack(fill="x", padx=15, pady=(5, 10))
            self._load_available_ids()

        if self.on_context_change:
            self.on_context_change(context, self.context_id)

    def _on_id_change(self, value):
        if value != "Nowy...":
            self.context_id = value
        else:
            self.context_id = None

    def _load_available_ids(self):
        """Załaduj dostępne ID ofert/zamówień"""
        context = self.context_type.get()
        # TODO: Pobierz z bazy danych
        if context == "quotation":
            self.id_combo.configure(values=["Nowy...", "QUO-001", "QUO-002"])
        elif context == "order":
            self.id_combo.configure(values=["Nowy...", "ORD-001", "ORD-002"])

    def _load_context(self):
        """Wczytaj dane z wybranego kontekstu"""
        if self.context_id:
            logger.info(f"Loading context: {self.context_type.get()} / {self.context_id}")
            # TODO: Wczytaj detale z oferty/zamówienia

    def get_context(self) -> Tuple[str, Optional[str]]:
        """Zwróć aktualny kontekst"""
        return self.context_type.get(), self.context_id

    def set_context(self, context_type: str, context_id: Optional[str] = None):
        """Ustaw kontekst (np. gdy okno otwarte z zamówienia)"""
        self.context_type.set(context_type)
        self.context_id = context_id

        if context_type != "test":
            self.id_frame.pack(fill="x", padx=15, pady=(5, 10))
            if context_id:
                self.id_combo.set(context_id)
                # Zablokuj zmianę jeśli kontekst jest ustalony
                self.rb_test.configure(state="disabled")
                self.rb_quotation.configure(state="disabled" if context_type != "quotation" else "normal")
                self.rb_order.configure(state="disabled" if context_type != "order" else "normal")
                self.id_combo.configure(state="disabled")


class NestingWindow(ctk.CTkToplevel):
    """
    Pełnoekranowe okno modułu Nesting.

    Funkcjonalności:
    - Wczytywanie plików DXF
    - Parsowanie nazw (materiał, grubość, ilość)
    - Grupowanie per materiał+grubość
    - Zakładki nestingu
    - Obliczanie kosztów
    - Przesyłanie wyników do Oferty/Zamówienia
    """

    def __init__(self, parent=None, context_type: str = "test",
                 context_id: str = None, parts_data: List[Dict] = None,
                 on_complete_callback=None):
        super().__init__(parent)

        self.parent_window = parent
        self.context_type = context_type
        self.context_id = context_id
        self.initial_parts = parts_data or []
        self.on_complete_callback = on_complete_callback

        self.loaded_parts: list = []
        self.parts_by_group: dict = {}
        self.nesting_panel: Optional[NestingTabsPanel] = None
        self.nesting_results: Dict = {}

        logger.info(f"[NestingWindow] Opening with context: {context_type}, id: {context_id}")
        logger.info(f"[NestingWindow] Initial parts: {len(self.initial_parts)}")

        # Konfiguracja okna
        self.title("Nesting - NewERP")
        self.configure(fg_color=Theme.BG_DARK)

        # Pełny ekran
        self.state('zoomed')
        self.minsize(1200, 800)

        self._setup_ui()

        # Na pierwszym planie
        self._bring_to_front()

        # Jeśli przekazano detale, załaduj je
        if self.initial_parts:
            self.after(100, self._load_initial_parts)

    def _bring_to_front(self):
        """Wymuś pierwszy plan okna"""
        logger.debug("[NestingWindow] Bringing window to front")
        self.attributes('-topmost', True)
        self.lift()
        self.focus_force()
        self.after(200, lambda: self.attributes('-topmost', False))

    def _setup_ui(self):
        """Buduj interfejs"""

        # === HEADER ===
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=70)
        header.pack(fill="x", padx=10, pady=10)
        header.pack_propagate(False)

        # Tytuł
        title = ctk.CTkLabel(
            header,
            text="Nesting",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        )
        title.pack(side="left", padx=20, pady=15)

        # Kontekst selector
        self.context_selector = ContextSelector(
            header,
            on_context_change=self._on_context_change
        )
        self.context_selector.pack(side="left", padx=20, pady=10)

        # Ustaw kontekst jeśli przekazany
        if self.context_type != "test":
            self.context_selector.set_context(self.context_type, self.context_id)

        # Store dynamics settings
        self.dynamics_settings = MachineDynamicsSettings()

        # Przycisk ustawień dynamiki maszyny
        self.btn_dynamics = ctk.CTkButton(
            header,
            text="⚙️ Ustawienia dynamiki",
            command=self._open_dynamics_dialog,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            width=150,
            height=35
        )
        self.btn_dynamics.pack(side="left", padx=10, pady=10)

        # Label pokazujący aktualną metodę
        self.lbl_dynamics_info = ctk.CTkLabel(
            header,
            text="Metoda: Dynamiczna",
            font=ctk.CTkFont(size=10),
            text_color=Theme.ACCENT_INFO
        )
        self.lbl_dynamics_info.pack(side="left", padx=5)

        # Przyciski (prawa strona)
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=20)

        # Wczytaj folder
        btn_load = ctk.CTkButton(
            btn_frame,
            text="Wczytaj folder DXF",
            command=self.load_folder,
            fg_color=Theme.ACCENT_SUCCESS,
            width=160,
            height=40
        )
        btn_load.pack(side="left", padx=5)

        # Nestuj wszystko
        self.btn_nest_all = ctk.CTkButton(
            btn_frame,
            text="Nestuj wszystko",
            command=self.nest_all,
            fg_color=Theme.ACCENT_WARNING,
            hover_color="#d97706",
            width=140,
            height=40,
            state="disabled"
        )
        self.btn_nest_all.pack(side="left", padx=5)

        # Wyczyść
        btn_clear = ctk.CTkButton(
            btn_frame,
            text="Wyczyść",
            command=self.clear_all,
            fg_color=Theme.ACCENT_DANGER,
            hover_color="#dc2626",
            width=100,
            height=40
        )
        btn_clear.pack(side="left", padx=5)

        # Edytor Regex
        btn_regex = ctk.CTkButton(
            btn_frame,
            text="Edytor Regex",
            command=self.open_regex_editor,
            fg_color=Theme.ACCENT_INFO,
            width=120,
            height=40
        )
        btn_regex.pack(side="left", padx=5)

        # Separator
        sep = ctk.CTkFrame(btn_frame, width=2, height=30, fg_color=Theme.TEXT_MUTED)
        sep.pack(side="left", padx=15, pady=5)

        # Prześlij (aktywny tylko gdy jest kontekst)
        self.btn_submit = ctk.CTkButton(
            btn_frame,
            text="Prześlij wyniki",
            command=self._submit_results,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color="#7c3aed",
            width=130,
            height=40,
            state="disabled"
        )
        self.btn_submit.pack(side="left", padx=5)

        # Anuluj
        btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Zamknij",
            command=self._close,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD_HOVER,
            width=100,
            height=40
        )
        btn_cancel.pack(side="left", padx=5)

        # === MAIN CONTENT ===
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Placeholder
        self.placeholder = ctk.CTkLabel(
            self.main_frame,
            text="Wczytaj folder z plikami DXF aby rozpocząć nesting.\n\n"
                 "Pliki zostaną automatycznie pogrupowane według:\n"
                 "  - Materiału (wykrytego z nazwy pliku)\n"
                 "  - Grubości (wykrytej z nazwy pliku)\n\n"
                 "Każda grupa otrzyma własną zakładkę z nestingiem.\n\n"
                 "Możesz wczytać wiele folderów - detale będą dodawane do istniejących grup.",
            font=ctk.CTkFont(size=14),
            text_color=Theme.TEXT_MUTED
        )
        self.placeholder.pack(expand=True)

        # === STATUSBAR ===
        self.statusbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=35)
        self.statusbar.pack(fill="x", padx=10, pady=(0, 10))
        self.statusbar.pack_propagate(False)

        self.lbl_status = ctk.CTkLabel(
            self.statusbar,
            text="Gotowy",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_status.pack(side="left", padx=15, pady=8)

        # Info o kosztach
        self.lbl_cost = ctk.CTkLabel(
            self.statusbar,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.lbl_cost.pack(side="right", padx=15, pady=8)

    def _on_context_change(self, context: str, context_id: Optional[str]):
        """Obsługa zmiany kontekstu"""
        self.context_type = context
        self.context_id = context_id

        # Aktywuj przycisk Prześlij tylko dla kontekstu != test
        if context != "test":
            # Przycisk aktywny tylko gdy są wyniki nestingu
            if self.nesting_results:
                self.btn_submit.configure(state="normal")
        else:
            self.btn_submit.configure(state="disabled")

    def _open_dynamics_dialog(self):
        """Otwórz dialog ustawień dynamiki maszyny."""
        dialog = MachineDynamicsDialog(
            self,
            settings=self.dynamics_settings,
            on_settings_change=self._on_dynamics_change
        )
        # Dialog jest modalny, więc poczeka na zamknięcie

    def _on_dynamics_change(self, settings: MachineDynamicsSettings):
        """Obsługa zmiany ustawień dynamiki maszyny."""
        self.dynamics_settings = settings
        logger.info(f"[NestingWindow] Dynamics settings changed: method={'dynamic' if settings.use_dynamic_method else 'classic'}, accel={settings.max_accel_mm_s2}")

        # Aktualizuj label z informacją o metodzie
        method_name = "Dynamiczna" if settings.use_dynamic_method else "Klasyczna"
        self.lbl_dynamics_info.configure(
            text=f"Metoda: {method_name} | a={int(settings.max_accel_mm_s2)} mm/s²"
        )

        # Przekaż ustawienia do panelu nestingu jeśli istnieje
        if self.nesting_panel:
            self.nesting_panel.set_dynamics_settings(settings)

    def load_folder(self):
        """Wczytaj folder z plikami DXF"""
        if not HAS_MODULES:
            messagebox.showerror("Błąd", "Brak wymaganych modułów. Sprawdź instalację.")
            return

        folder = filedialog.askdirectory(title="Wybierz folder z plikami DXF")
        if not folder:
            return

        self._load_folder_path(folder)

    def _load_folder_path(self, folder: str):
        """Wczytaj folder podany jako ścieżka"""
        folder_path = Path(folder)

        # Znajdź pliki DXF
        dxf_files = list(folder_path.rglob("*.dxf")) + list(folder_path.rglob("*.DXF"))

        if not dxf_files:
            messagebox.showwarning("Uwaga", "Nie znaleziono plików DXF w wybranym folderze")
            return

        self.lbl_status.configure(text=f"Wczytywanie {len(dxf_files)} plików...")
        self.update()

        new_parts_count = 0

        for dxf_path in dxf_files:
            try:
                # Wczytaj geometrię
                part = load_dxf(str(dxf_path))
                if not part:
                    logger.warning(f"Nie udało się wczytać: {dxf_path.name}")
                    continue

                # Parsuj nazwę
                parsed = parse_filename_with_folder_context(dxf_path, stop_at=folder_path)

                material = parsed.get('material', '') or 'NIEZNANY'
                thickness = parsed.get('thickness_mm') or 0.0
                quantity = parsed.get('quantity') or 1

                # Uzupełnij dane
                part.material = material
                part.thickness = thickness
                part.quantity = quantity

                self.loaded_parts.append(part)

                # Grupuj
                key = (material, thickness)
                if key not in self.parts_by_group:
                    self.parts_by_group[key] = []

                # Konwertuj DXFPart na dict dla NestingTabsPanel
                part_dict = {
                    'name': part.name,
                    'width': part.width,
                    'height': part.height,
                    'quantity': quantity,
                    'contour': part.get_normalized_contour(),
                    'holes': [[(x - part.min_x, y - part.min_y) for x, y in hole] for hole in part.holes],
                    'contour_area': part.contour_area,
                    'weight_kg': part.weight_kg if part.thickness else 0,
                    'filepath': part.filepath,
                }
                self.parts_by_group[key].append(part_dict)
                new_parts_count += 1

            except Exception as e:
                logger.error(f"Błąd wczytywania {dxf_path.name}: {e}")

        # Podsumowanie
        total_parts = len(self.loaded_parts)
        total_groups = len(self.parts_by_group)

        if new_parts_count == 0:
            messagebox.showerror("Błąd", "Nie udało się wczytać żadnego pliku DXF")
            return

        # Aktualizuj lub utwórz panel zakładek
        self._update_nesting_panel()

        self.lbl_status.configure(
            text=f"Wczytano {new_parts_count} nowych detali | Łącznie: {total_parts} detali w {total_groups} grupach"
        )

        # Pokaż podsumowanie
        summary = "Wczytane grupy:\n\n"
        for (mat, th), parts in sorted(self.parts_by_group.items()):
            total_qty = sum(p.get('quantity', 1) for p in parts)
            summary += f"  - {mat} {th}mm: {len(parts)} typów, {total_qty} szt\n"

        logger.info(summary)

    def _load_initial_parts(self):
        """Wczytaj detale przekazane przy tworzeniu okna"""
        for part_data in self.initial_parts:
            material = part_data.get('material', 'NIEZNANY')
            thickness = part_data.get('thickness_mm', 0.0)

            key = (material, thickness)
            if key not in self.parts_by_group:
                self.parts_by_group[key] = []

            self.parts_by_group[key].append(part_data)

        if self.parts_by_group:
            self._update_nesting_panel()
            self.lbl_status.configure(
                text=f"Wczytano {len(self.initial_parts)} detali z kontekstu"
            )

    def _update_nesting_panel(self):
        """Aktualizuj lub utwórz panel z zakładkami nestingu"""
        # Usuń placeholder jeśli istnieje
        if hasattr(self, 'placeholder') and self.placeholder.winfo_exists():
            self.placeholder.destroy()

        # Usuń stary panel jeśli istnieje
        if self.nesting_panel:
            self.nesting_panel.destroy()
            self.nesting_panel = None

        # Pobierz dostępne formaty arkuszy
        sheet_formats = [
            (3000, 1500),
            (2500, 1250),
            (2000, 1000),
            (1500, 750),
            (1000, 500),
        ]

        # Utwórz nowy panel z aktualnymi danymi
        self.nesting_panel = NestingTabsPanel(
            self.main_frame,
            parts_by_group=self.parts_by_group,
            sheet_formats=sheet_formats,
            on_all_complete=self._on_all_nesting_complete,
            dynamics_settings=self.dynamics_settings
        )
        self.nesting_panel.pack(fill="both", expand=True)

        # Włącz przycisk "Nestuj wszystko"
        self.btn_nest_all.configure(state="normal")

    def clear_all(self):
        """Wyczyść wszystkie wczytane dane"""
        if self.loaded_parts or self.parts_by_group:
            if not messagebox.askyesno("Potwierdzenie", "Czy na pewno wyczyścić wszystkie dane?"):
                return

        self.loaded_parts.clear()
        self.parts_by_group.clear()
        self.nesting_results.clear()

        # Usuń panel nestingu jeśli istnieje
        if self.nesting_panel:
            self.nesting_panel.destroy()
            self.nesting_panel = None

        # Przywróć placeholder
        self.placeholder = ctk.CTkLabel(
            self.main_frame,
            text="Wczytaj folder z plikami DXF aby rozpocząć nesting.\n\n"
                 "Pliki zostaną automatycznie pogrupowane według:\n"
                 "  - Materiału (wykrytego z nazwy pliku)\n"
                 "  - Grubości (wykrytej z nazwy pliku)\n\n"
                 "Każda grupa otrzyma własną zakładkę z nestingiem.\n\n"
                 "Możesz wczytać wiele folderów - detale będą dodawane do istniejących grup.",
            font=ctk.CTkFont(size=14),
            text_color=Theme.TEXT_MUTED
        )
        self.placeholder.pack(expand=True)

        self.btn_nest_all.configure(state="disabled")
        self.btn_submit.configure(state="disabled")
        self.lbl_status.configure(text="Wyczyszczono")
        self.lbl_cost.configure(text="")

    def nest_all(self):
        """Uruchom nesting na wszystkich zakładkach"""
        if self.nesting_panel:
            self.nesting_panel.start_all_nesting()
            self.lbl_status.configure(text="Uruchomiono nesting na wszystkich zakładkach...")

    def _on_all_nesting_complete(self, results: dict):
        """Callback gdy wszystkie nestingi zakończone"""
        self.nesting_results = results

        total_parts = sum(len(r.placed_parts) for r in results.values())
        total_sheets = sum(r.sheets_used for r in results.values())
        total_unplaced = sum(r.unplaced_count for r in results.values())
        total_cost = sum(r.total_cost for r in results.values())

        # Aggregate cutting times
        total_time_classic = sum(getattr(r, 'cut_time_classic_s', 0) for r in results.values())
        total_time_dynamic = sum(getattr(r, 'cut_time_dynamic_s', 0) for r in results.values())

        status_text = f"Wszystkie nestingi zakończone! {total_parts} detali na {total_sheets} arkuszach"
        if total_unplaced > 0:
            status_text += f" | {total_unplaced} nieznestowanych"

        self.lbl_status.configure(text=status_text)

        if total_cost > 0:
            self.lbl_cost.configure(text=f"Szacowany koszt: {total_cost:,.2f} PLN")

        # Aktywuj przycisk Prześlij jeśli kontekst != test
        if self.context_type != "test":
            self.btn_submit.configure(state="normal")

        # Wyświetl podsumowanie
        summary = "=== PODSUMOWANIE NESTINGU ===\n\n"

        for (mat, th), result in results.items():
            summary += f"{mat} {th}mm:\n"
            summary += f"  Detali umieszczonych: {len(result.placed_parts)}\n"
            summary += f"  Arkuszy użytych: {result.sheets_used}\n"
            summary += f"  Efektywność: {result.total_efficiency:.1%}\n"

            # Cutting times
            classic_s = getattr(result, 'cut_time_classic_s', 0)
            dynamic_s = getattr(result, 'cut_time_dynamic_s', 0)
            if classic_s > 0 or dynamic_s > 0:
                summary += f"  Czas cięcia (klasyczny): {classic_s/60:.1f} min\n"
                summary += f"  Czas cięcia (dynamiczny): {dynamic_s/60:.1f} min\n"

            if result.unplaced_count > 0:
                summary += f"  Nieumieszczonych: {result.unplaced_count}\n"
                for up in result.unplaced_parts[:3]:
                    summary += f"    - {up.name}: {up.reason}\n"
                if result.unplaced_count > 3:
                    summary += f"    ... i {result.unplaced_count - 3} więcej\n"

            if result.total_cost > 0:
                summary += f"  Koszt materiału: {result.total_cost:.2f} PLN\n"
            summary += "\n"

        # Total cutting times
        if total_time_classic > 0 or total_time_dynamic > 0:
            summary += f"=== ŁĄCZNE CZASY CIĘCIA ===\n"
            summary += f"  Klasyczny: {total_time_classic/60:.1f} min\n"
            summary += f"  Dynamiczny: {total_time_dynamic/60:.1f} min\n"
            if total_time_classic > 0:
                diff_pct = ((total_time_dynamic - total_time_classic) / total_time_classic) * 100
                summary += f"  Różnica: {diff_pct:+.0f}%\n"

        logger.info(summary)

    def _submit_results(self):
        """Prześlij wyniki do Oferty/Zamówienia"""
        if not self.nesting_results:
            messagebox.showwarning("Uwaga", "Brak wyników nestingu do przesłania")
            return

        context, context_id = self.context_selector.get_context()

        if context == "test":
            messagebox.showinfo("Info", "Wybierz kontekst Oferta lub Zamówienie aby przesłać wyniki")
            return

        # Potwierdzenie
        total_parts = sum(len(r.placed_parts) for r in self.nesting_results.values())
        total_sheets = sum(r.sheets_used for r in self.nesting_results.values())
        total_cost = sum(r.total_cost for r in self.nesting_results.values())

        msg = f"Przesłać wyniki nestingu?\n\n"
        msg += f"Kontekst: {context.upper()}\n"
        if context_id:
            msg += f"ID: {context_id}\n"
        else:
            msg += f"ID: Nowy\n"
        msg += f"\nDetali: {total_parts}\n"
        msg += f"Arkuszy: {total_sheets}\n"
        if total_cost > 0:
            msg += f"Szacowany koszt: {total_cost:,.2f} PLN\n"

        if not messagebox.askyesno("Potwierdzenie", msg):
            return

        logger.info(f"[NestingWindow] Submitting results to {context} / {context_id or 'NEW'}")

        # Calculate total cutting times
        total_time_classic = sum(getattr(r, 'cut_time_classic_s', 0) for r in self.nesting_results.values())
        total_time_dynamic = sum(getattr(r, 'cut_time_dynamic_s', 0) for r in self.nesting_results.values())

        # Przygotuj dane do przekazania
        callback_data = {
            'context_type': context,
            'context_id': context_id,
            'total_parts': total_parts,
            'total_sheets': total_sheets,
            'total_cost': total_cost,
            'sheets': [],
            'cutting_times': {
                'classic_total_s': total_time_classic,
                'dynamic_total_s': total_time_dynamic,
            },
            'cost_result': {
                'material_cost': 0,
                'cutting_cost': 0,
                'foil_cost': 0,
                'piercing_cost': 0,
                'operational_cost': total_sheets * 40,  # 40 PLN/arkusz
                'subtotal': total_cost,
                'total_cost': total_cost,
                'total_sheets': total_sheets,
                'average_efficiency': 0,
                'total_weight_kg': 0
            }
        }

        total_efficiency = 0
        for (mat, th), result in self.nesting_results.items():
            callback_data['material'] = mat
            callback_data['thickness'] = th

            # Zbierz dane o arkuszach
            for i in range(result.sheets_used):
                sheet_data = {
                    'material': mat,
                    'thickness_mm': th,
                    'efficiency': result.total_efficiency,
                    'parts_count': len(result.placed_parts) // max(1, result.sheets_used),
                    'cost': result.total_cost / max(1, result.sheets_used)
                }
                callback_data['sheets'].append(sheet_data)

            total_efficiency += result.total_efficiency * result.sheets_used
            callback_data['cost_result']['material_cost'] += result.total_cost

        if total_sheets > 0:
            callback_data['cost_result']['average_efficiency'] = total_efficiency / total_sheets

        # Eksportuj obrazy arkuszy
        callback_data['sheet_images'] = []
        if self.nesting_panel:
            try:
                all_images = self.nesting_panel.export_all_images(width=800, height=600)
                for tab_name, images in all_images.items():
                    for idx, img_bytes in enumerate(images):
                        callback_data['sheet_images'].append({
                            'tab_name': tab_name,
                            'sheet_index': idx,
                            'image_bytes': img_bytes
                        })
                logger.info(f"[NestingWindow] Exported {len(callback_data['sheet_images'])} sheet images")
            except Exception as e:
                logger.error(f"[NestingWindow] Error exporting images: {e}")

        # Wywołaj callback jeśli istnieje
        if self.on_complete_callback:
            logger.info(f"[NestingWindow] Calling on_complete_callback with data")
            self.on_complete_callback(callback_data)

        messagebox.showinfo("Sukces", f"Wyniki przesłane do {context.upper()}")

        # Zamknij okno
        self.destroy()

    def _close(self):
        """Zamknij okno"""
        if self.nesting_results:
            if not messagebox.askyesno("Potwierdzenie",
                                        "Masz niezapisane wyniki nestingu. Czy na pewno zamknąć?"):
                return
        self.destroy()

    def open_regex_editor(self):
        """Otwórz edytor regex"""
        def on_save():
            reload_rules()
            logger.info("Reguły regex zaktualizowane")

        try:
            editor = RegexEditorWindow(self, on_save=on_save)
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się otworzyć edytora regex: {e}")


# ============================================================
# ENTRY POINT
# ============================================================

def run_nesting_standalone():
    """Uruchom Nesting jako samodzielną aplikację"""
    if not HAS_MODULES:
        print("ERROR: Brak wymaganych modułów. Sprawdź import errors powyżej.")
        return

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    app = NestingWindow(root)

    # Jeśli podano folder jako argument
    if len(sys.argv) > 1:
        folder = sys.argv[1]
        if os.path.isdir(folder):
            app.after(100, lambda: app._load_folder_path(folder))

    app.mainloop()


if __name__ == "__main__":
    run_nesting_standalone()
