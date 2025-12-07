"""
Settings Dialog - Formatki ustawień słowników warstw i kolorów
===============================================================
Pozwala na edycję mapowania warstw DXF do operacji technologicznych.
Ustawienia zapisywane lokalnie w JSON.
"""

import customtkinter as ctk
from tkinter import ttk, messagebox
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

# Ścieżka do pliku konfiguracji
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "layer_settings.json"


class Theme:
    """Paleta kolorów"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_INPUT = "#2d2d2d"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    ACCENT_PRIMARY = "#8b5cf6"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"


def load_layer_settings() -> Dict:
    """Wczytaj ustawienia warstw z pliku JSON"""
    default_settings = {
        "marking_keywords": ["grawer", "marking", "opis", "text", "engrave", "mark", "sign"],
        "bending_keywords": ["bend", "gięcie", "big", "inner_bend", "outer_bend", "k-factor", "folding"],
        "ignore_layers": ["RAMKA", "WYMIARY", "DIM", "TEXT", "TEKST", "OPIS", "DEFPOINTS",
                         "ASSEMBLY", "HIDDEN", "CENTER", "CUTLINE", "GRID", "TITLE",
                         "BLOCK", "LOGO", "INFO", "FRAME", "BORDER", "AM_", "NOTES", "KOTY", "ZAKRES"],
        "grawer_color_index": 2,
        "color_mappings": {
            "2": "marking",
            "1": "cutting",
            "3": "bending"
        }
    }

    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Merge z domyślnymi
                for key in default_settings:
                    if key not in settings:
                        settings[key] = default_settings[key]
                return settings
    except Exception as e:
        logger.error(f"Błąd wczytywania ustawień warstw: {e}")

    return default_settings


def save_layer_settings(settings: Dict) -> bool:
    """Zapisz ustawienia warstw do pliku JSON"""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        logger.info(f"Zapisano ustawienia warstw do {CONFIG_PATH}")
        return True
    except Exception as e:
        logger.error(f"Błąd zapisywania ustawień warstw: {e}")
        return False


class KeywordListEditor(ctk.CTkFrame):
    """Edytor listy słów kluczowych z możliwością dodawania/usuwania"""

    def __init__(self, parent, title: str, keywords: List[str], **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, **kwargs)

        self.keywords = list(keywords)

        # Tytuł
        lbl_title = ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=12, weight="bold"))
        lbl_title.pack(pady=(10, 5), padx=10, anchor="w")

        # Lista
        list_frame = ctk.CTkFrame(self, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.listbox = ctk.CTkTextbox(list_frame, height=120, fg_color=Theme.BG_INPUT)
        self.listbox.pack(fill="both", expand=True)
        self._refresh_list()

        # Przyciski
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.entry_new = ctk.CTkEntry(btn_frame, placeholder_text="Nowe słowo...", width=150)
        self.entry_new.pack(side="left", padx=(0, 5))

        btn_add = ctk.CTkButton(btn_frame, text="➕ Dodaj", width=70,
                               fg_color=Theme.ACCENT_SUCCESS, command=self._add_keyword)
        btn_add.pack(side="left", padx=2)

        btn_remove = ctk.CTkButton(btn_frame, text="➖ Usuń", width=70,
                                  fg_color=Theme.ACCENT_DANGER, command=self._remove_keyword)
        btn_remove.pack(side="left", padx=2)

    def _refresh_list(self):
        """Odśwież listę"""
        self.listbox.delete("1.0", "end")
        for kw in sorted(self.keywords):
            self.listbox.insert("end", f"{kw}\n")

    def _add_keyword(self):
        """Dodaj słowo kluczowe"""
        new_kw = self.entry_new.get().strip().lower()
        if new_kw and new_kw not in self.keywords:
            self.keywords.append(new_kw)
            self._refresh_list()
            self.entry_new.delete(0, "end")

    def _remove_keyword(self):
        """Usuń zaznaczone słowo"""
        try:
            # Pobierz aktualnie zaznaczony tekst
            selection = self.listbox.get("sel.first", "sel.last").strip()
            if selection and selection in self.keywords:
                self.keywords.remove(selection)
                self._refresh_list()
        except:
            # Jeśli nic nie zaznaczone, usuń ostatnie
            if self.keywords:
                self.keywords.pop()
                self._refresh_list()

    def get_keywords(self) -> List[str]:
        """Pobierz listę słów kluczowych"""
        return self.keywords


class ColorMappingEditor(ctk.CTkFrame):
    """Edytor mapowania kolorów AutoCAD na operacje"""

    AUTOCAD_COLORS = {
        "1": ("Czerwony", "#ff0000"),
        "2": ("Żółty", "#ffff00"),
        "3": ("Zielony", "#00ff00"),
        "4": ("Cyjan", "#00ffff"),
        "5": ("Niebieski", "#0000ff"),
        "6": ("Magenta", "#ff00ff"),
        "7": ("Biały", "#ffffff"),
    }

    OPERATIONS = ["cutting", "marking", "bending", "ignore"]

    def __init__(self, parent, color_mappings: Dict[str, str], **kwargs):
        super().__init__(parent, fg_color=Theme.BG_CARD, **kwargs)

        self.mappings = dict(color_mappings)

        # Tytuł
        lbl_title = ctk.CTkLabel(self, text="Mapowanie kolorów AutoCAD",
                                font=ctk.CTkFont(size=12, weight="bold"))
        lbl_title.pack(pady=(10, 5), padx=10, anchor="w")

        # Tabela mapowań
        self.mapping_vars: Dict[str, ctk.StringVar] = {}

        for color_idx, (color_name, color_hex) in self.AUTOCAD_COLORS.items():
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)

            # Kolor sample
            color_sample = ctk.CTkLabel(row, text="■", font=ctk.CTkFont(size=16),
                                       text_color=color_hex, width=25)
            color_sample.pack(side="left")

            # Nazwa koloru
            lbl_name = ctk.CTkLabel(row, text=f"{color_idx}: {color_name}", width=100)
            lbl_name.pack(side="left", padx=5)

            # Dropdown operacji
            var = ctk.StringVar(value=self.mappings.get(color_idx, "cutting"))
            self.mapping_vars[color_idx] = var

            combo = ctk.CTkComboBox(row, values=self.OPERATIONS, variable=var, width=120)
            combo.pack(side="left", padx=5)

    def get_mappings(self) -> Dict[str, str]:
        """Pobierz mapowania"""
        return {k: v.get() for k, v in self.mapping_vars.items()}


class LayerSettingsDialog(ctk.CTkToplevel):
    """Dialog ustawień warstw i kolorów DXF"""

    def __init__(self, parent, on_save: Optional[Callable] = None):
        super().__init__(parent)

        self.on_save = on_save
        self.settings = load_layer_settings()

        self.title("⚙️ Ustawienia warstw DXF")
        self.geometry("800x700")
        self.configure(fg_color=Theme.BG_DARK)

        # Wyśrodkuj
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 800) // 2
        y = (self.winfo_screenheight() - 700) // 2
        self.geometry(f"+{x}+{y}")

        self._setup_ui()

        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _setup_ui(self):
        """Buduj interfejs"""
        # Header
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        header.pack(fill="x", padx=10, pady=10)
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="⚙️ Ustawienia rozpoznawania operacji DXF",
                    font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=20, pady=15)

        # Main content - scrollable
        main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_scroll.pack(fill="both", expand=True, padx=10, pady=5)

        # Trzy kolumny
        cols = ctk.CTkFrame(main_scroll, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        cols.grid_columnconfigure((0, 1), weight=1)

        # === LEWY PANEL - Słowa kluczowe ===
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.marking_editor = KeywordListEditor(
            left, "🔶 Słowa kluczowe GRAWERU", self.settings.get("marking_keywords", []))
        self.marking_editor.pack(fill="x", pady=5)

        self.bending_editor = KeywordListEditor(
            left, "🔷 Słowa kluczowe GIĘCIA", self.settings.get("bending_keywords", []))
        self.bending_editor.pack(fill="x", pady=5)

        # === PRAWY PANEL - Kolory i ignorowane ===
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        self.color_editor = ColorMappingEditor(right, self.settings.get("color_mappings", {}))
        self.color_editor.pack(fill="x", pady=5)

        self.ignore_editor = KeywordListEditor(
            right, "🚫 Warstwy IGNOROWANE", self.settings.get("ignore_layers", []))
        self.ignore_editor.pack(fill="x", pady=5)

        # Kolor graweru (priorytet)
        color_frame = ctk.CTkFrame(right, fg_color=Theme.BG_CARD)
        color_frame.pack(fill="x", pady=5)

        ctk.CTkLabel(color_frame, text="Priorytetowy kolor graweru (AutoCAD Index):",
                    font=ctk.CTkFont(size=11)).pack(side="left", padx=10, pady=10)

        self.grawer_color_var = ctk.StringVar(value=str(self.settings.get("grawer_color_index", 2)))
        grawer_combo = ctk.CTkComboBox(color_frame, values=["1", "2", "3", "4", "5", "6", "7"],
                                       variable=self.grawer_color_var, width=80)
        grawer_combo.pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(color_frame, text="(2=Żółty)", text_color=Theme.TEXT_SECONDARY,
                    font=ctk.CTkFont(size=10)).pack(side="left")

        # === FOOTER - Przyciski ===
        footer = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        footer.pack(fill="x", padx=10, pady=10)
        footer.pack_propagate(False)

        btn_cancel = ctk.CTkButton(footer, text="Anuluj", width=100,
                                  fg_color=Theme.BG_INPUT, command=self.destroy)
        btn_cancel.pack(side="right", padx=10, pady=12)

        btn_save = ctk.CTkButton(footer, text="💾 Zapisz", width=120,
                                fg_color=Theme.ACCENT_SUCCESS, command=self._save)
        btn_save.pack(side="right", padx=5, pady=12)

        btn_reset = ctk.CTkButton(footer, text="🔄 Przywróć domyślne", width=150,
                                 fg_color=Theme.ACCENT_WARNING, command=self._reset_defaults)
        btn_reset.pack(side="left", padx=10, pady=12)

    def _save(self):
        """Zapisz ustawienia"""
        new_settings = {
            "marking_keywords": self.marking_editor.get_keywords(),
            "bending_keywords": self.bending_editor.get_keywords(),
            "ignore_layers": self.ignore_editor.get_keywords(),
            "grawer_color_index": int(self.grawer_color_var.get()),
            "color_mappings": self.color_editor.get_mappings()
        }

        if save_layer_settings(new_settings):
            messagebox.showinfo("Sukces", "Ustawienia zostały zapisane!", parent=self)
            if self.on_save:
                self.on_save(new_settings)
            self.destroy()
        else:
            messagebox.showerror("Błąd", "Nie udało się zapisać ustawień", parent=self)

    def _reset_defaults(self):
        """Przywróć domyślne ustawienia"""
        if messagebox.askyesno("Potwierdzenie", "Przywrócić domyślne ustawienia?", parent=self):
            self.settings = {
                "marking_keywords": ["grawer", "marking", "opis", "text", "engrave", "mark", "sign"],
                "bending_keywords": ["bend", "gięcie", "big", "inner_bend", "outer_bend", "k-factor", "folding"],
                "ignore_layers": ["RAMKA", "WYMIARY", "DIM", "TEXT", "TEKST", "OPIS", "DEFPOINTS",
                                 "ASSEMBLY", "HIDDEN", "CENTER", "CUTLINE", "GRID", "TITLE",
                                 "BLOCK", "LOGO", "INFO", "FRAME", "BORDER", "AM_", "NOTES", "KOTY", "ZAKRES"],
                "grawer_color_index": 2,
                "color_mappings": {"2": "marking", "1": "cutting", "3": "bending"}
            }
            self.destroy()
            LayerSettingsDialog(self.master, self.on_save)


# ============================================================
# Cost Settings Dialog
# ============================================================

class CostSettingsDialog(ctk.CTkToplevel):
    """Dialog ustawień kosztów operacyjnych"""

    def __init__(self, parent, on_save: Optional[Callable] = None):
        super().__init__(parent)

        self.on_save = on_save
        self.settings = self._load_cost_settings()

        self.title("💰 Ustawienia kosztów")
        self.geometry("600x700")
        self.configure(fg_color=Theme.BG_DARK)

        # Wyśrodkuj
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 600) // 2
        y = (self.winfo_screenheight() - 700) // 2
        self.geometry(f"+{x}+{y}")

        self._setup_ui()

        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _load_cost_settings(self) -> Dict:
        """Wczytaj ustawienia kosztów"""
        cost_path = CONFIG_PATH.parent / "cost_settings.json"
        default = {
            "sheet_handling_cost": 40.0,
            "foil_cost_per_meter": 0.20,
            "piercing_time_inox_base_s": 0.5,
            "piercing_time_inox_per_mm_s": 0.1,
            "piercing_time_steel_base_s": 0.5,
            "piercing_time_steel_per_mm_s": 0.3,
            "time_buffer_percent": 25.0,
            "default_markup_percent": 0.0,
            # Koszty per zlecenie
            "tech_cost_enabled": True,
            "tech_cost_value": 50.0,
            "packaging_cost_enabled": True,
            "packaging_cost_value": 100.0,
            "transport_cost_enabled": False,
            "transport_cost_value": 0.0
        }

        try:
            if cost_path.exists():
                with open(cost_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    for key in default:
                        if key not in settings:
                            settings[key] = default[key]
                    return settings
        except Exception as e:
            logger.error(f"Błąd wczytywania ustawień kosztów: {e}")

        return default

    def _save_cost_settings(self, settings: Dict) -> bool:
        """Zapisz ustawienia kosztów"""
        cost_path = CONFIG_PATH.parent / "cost_settings.json"
        try:
            cost_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cost_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Błąd zapisywania ustawień kosztów: {e}")
            return False

    def _setup_ui(self):
        """Buduj interfejs"""
        # Header
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        header.pack(fill="x", padx=10, pady=10)
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="💰 Ustawienia parametrów kosztowych",
                    font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=20, pady=15)

        # Main content
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=5)

        self.entries: Dict[str, ctk.CTkEntry] = {}

        # Grupa: Koszty operacyjne
        self._add_section(main, "📦 Koszty operacyjne")
        self._add_field(main, "sheet_handling_cost", "Koszt obsługi arkusza [PLN]:",
                       self.settings["sheet_handling_cost"])

        # Grupa: Folia
        self._add_section(main, "🎞️ Usuwanie folii")
        self._add_field(main, "foil_cost_per_meter", "Koszt usuwania folii [PLN/m]:",
                       self.settings["foil_cost_per_meter"])

        # Grupa: Koszty per zlecenie
        self._add_section(main, "📋 Koszty per zlecenie")
        self._add_checkbox_field(main, "tech_cost", "Technologia:",
                                self.settings.get("tech_cost_enabled", True),
                                self.settings.get("tech_cost_value", 50.0))
        self._add_checkbox_field(main, "packaging_cost", "Opakowania:",
                                self.settings.get("packaging_cost_enabled", True),
                                self.settings.get("packaging_cost_value", 100.0))
        self._add_checkbox_field(main, "transport_cost", "Transport:",
                                self.settings.get("transport_cost_enabled", False),
                                self.settings.get("transport_cost_value", 0.0))

        # Grupa: Przebicia
        self._add_section(main, "🔥 Przebicia (piercing)")
        self._add_field(main, "piercing_time_inox_base_s", "INOX - czas bazowy [s]:",
                       self.settings["piercing_time_inox_base_s"])
        self._add_field(main, "piercing_time_inox_per_mm_s", "INOX - czas per mm grub. [s]:",
                       self.settings["piercing_time_inox_per_mm_s"])
        self._add_field(main, "piercing_time_steel_base_s", "Stal - czas bazowy [s]:",
                       self.settings["piercing_time_steel_base_s"])
        self._add_field(main, "piercing_time_steel_per_mm_s", "Stal - czas per mm grub. [s]:",
                       self.settings["piercing_time_steel_per_mm_s"])

        # Grupa: Bufory
        self._add_section(main, "⏱️ Bufory czasowe")
        self._add_field(main, "time_buffer_percent", "Bufor niepewności [%]:",
                       self.settings["time_buffer_percent"])

        # Grupa: Narzut
        self._add_section(main, "📈 Domyślny narzut")
        self._add_field(main, "default_markup_percent", "Domyślny narzut [%]:",
                       self.settings["default_markup_percent"])

        # Footer
        footer = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        footer.pack(fill="x", padx=10, pady=10)
        footer.pack_propagate(False)

        btn_cancel = ctk.CTkButton(footer, text="Anuluj", width=100,
                                  fg_color=Theme.BG_INPUT, command=self.destroy)
        btn_cancel.pack(side="right", padx=10, pady=12)

        btn_save = ctk.CTkButton(footer, text="💾 Zapisz", width=120,
                                fg_color=Theme.ACCENT_SUCCESS, command=self._save)
        btn_save.pack(side="right", padx=5, pady=12)

    def _add_section(self, parent, title: str):
        """Dodaj nagłówek sekcji"""
        frame = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD, height=40)
        frame.pack(fill="x", pady=(15, 5))

        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=Theme.ACCENT_PRIMARY).pack(side="left", padx=15, pady=8)

    def _add_field(self, parent, key: str, label: str, value: float):
        """Dodaj pole edycji"""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3, padx=10)

        ctk.CTkLabel(row, text=label, width=250).pack(side="left")

        entry = ctk.CTkEntry(row, width=120)
        entry.insert(0, str(value))
        entry.pack(side="left", padx=10)

        self.entries[key] = entry

    def _add_checkbox_field(self, parent, key: str, label: str, enabled: bool, value: float):
        """Dodaj pole z checkboxem i wartością"""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3, padx=10)

        # Checkbox
        var_enabled = ctk.BooleanVar(value=enabled)
        checkbox = ctk.CTkCheckBox(
            row, text=label, variable=var_enabled,
            width=200, font=ctk.CTkFont(size=11)
        )
        checkbox.pack(side="left")

        # Wartość
        entry = ctk.CTkEntry(row, width=100)
        entry.insert(0, str(value))
        entry.pack(side="left", padx=10)

        ctk.CTkLabel(row, text="PLN", text_color=Theme.TEXT_SECONDARY,
                    font=ctk.CTkFont(size=10)).pack(side="left")

        # Zapisz referencje
        self.entries[f"{key}_enabled"] = var_enabled
        self.entries[f"{key}_value"] = entry

    def _save(self):
        """Zapisz ustawienia"""
        new_settings = {}
        for key, entry in self.entries.items():
            try:
                if isinstance(entry, ctk.BooleanVar):
                    # Checkbox - boolean
                    new_settings[key] = entry.get()
                elif isinstance(entry, ctk.CTkEntry):
                    # Entry - float
                    new_settings[key] = float(entry.get())
                else:
                    # Inny typ - spróbuj skonwertować
                    new_settings[key] = float(entry.get())
            except Exception as e:
                messagebox.showerror("Błąd", f"Nieprawidłowa wartość dla: {key}", parent=self)
                return

        if self._save_cost_settings(new_settings):
            # Zaktualizuj też Supabase jeśli dostępne
            self._sync_to_supabase(new_settings)
            messagebox.showinfo("Sukces", "Ustawienia kosztów zapisane!", parent=self)
            if self.on_save:
                self.on_save(new_settings)
            self.destroy()
        else:
            messagebox.showerror("Błąd", "Nie udało się zapisać ustawień", parent=self)

    def _sync_to_supabase(self, settings: Dict):
        """Synchronizuj kluczowe ustawienia z Supabase"""
        try:
            from core.supabase_client import get_supabase_client
            client = get_supabase_client()

            # Zaktualizuj foil_cost_per_meter w cost_config
            if 'foil_cost_per_meter' in settings:
                client.table('cost_config').upsert({
                    'config_key': 'foil_cost_per_meter',
                    'config_value': str(settings['foil_cost_per_meter']),
                    'description': 'Koszt usuwania folii [PLN/m]'
                }, on_conflict='config_key').execute()
                logger.info(f"[CostSettings] Synced foil_cost_per_meter to Supabase: {settings['foil_cost_per_meter']}")

        except ImportError:
            logger.warning("[CostSettings] Supabase client not available")
        except Exception as e:
            logger.warning(f"[CostSettings] Failed to sync to Supabase: {e}")


# Test
if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    root = ctk.CTk()
    root.title("Test")
    root.geometry("400x300")

    def open_layer():
        LayerSettingsDialog(root)

    def open_cost():
        CostSettingsDialog(root)

    ctk.CTkButton(root, text="Ustawienia warstw", command=open_layer).pack(pady=20)
    ctk.CTkButton(root, text="Ustawienia kosztów", command=open_cost).pack(pady=20)

    root.mainloop()
