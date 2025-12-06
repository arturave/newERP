"""
Regex Editor Panel - Edytor reguł materiałów zintegrowany z GUI
================================================================
Panel do zarządzania regułami regex dla parsera nazw plików.
Zintegrowany z stylem graficznym aplikacji NewERP.
"""

import customtkinter as ctk
from tkinter import messagebox
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Import parsera
try:
    from quotations.utils.name_parser import (
        get_rules_as_list, save_rules_to_json, reload_rules,
        parse_filename, get_rules_file_path
    )
    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False
    logger.warning("name_parser not available")


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


# Tekst pomocy
HELP_TEXT = """=== KRÓTKI PORADNIK REGEX ===

System ignoruje wielkość liter (A = a).

NAJCZĘSTSZE SYMBOLE:
-----------------------------------------
.   (Kropka) Oznacza "dowolny znak". 
    Jeśli szukasz kropki w gatunku (np. 1.4301), 
    napisz: 1\\.4301

?   (Pytajnik) Poprzedni znak jest opcjonalny.
    Np. "316L?" złapie zarówno "316" jak i "316L".

[]  (Nawias kw.) Jeden znak z podanych w środku.
    Np. "AISI[ _-]304" złapie "AISI 304", "AISI_304" i "AISI-304".

\\s  (Ukośnik s) Oznacza spację.
    Np. "Super\\sMirror" złapie "Super Mirror".

* (Gwiazdka) Dowolna ilość poprzedniego znaku (także 0).
    Np. "alu.*6060" złapie "alu 6060", "alu_6060", "alu6060".

PRZYKŁADY:
-----------------------------------------
1. Stal "S355" z różnymi końcówkami (J2, JR, J2+N):
   Wzorzec: s355.*

2. Format "1.4301" pisany też jako "14301":
   Wzorzec: 1[.,]?4301

3. Opcjonalne słowo "inox":
   Wzorzec: inox\\s*304

WSKAZÓWKA:
Zawsze wpisz przykładową nazwę pliku w polu 
"Testuj na żywo" po prawej stronie, aby sprawdzić 
czy Twój wzorzec działa!
"""


class MaterialCard(ctk.CTkFrame):
    """Karta materiału na liście"""
    
    def __init__(self, parent, data: dict, index: int,
                 on_select, on_move_up, on_move_down, is_selected=False):
        
        color = Theme.ACCENT_PRIMARY if is_selected else "transparent"
        super().__init__(parent, fg_color=color, corner_radius=6, 
                        border_width=1, border_color="#444")
        
        self.data = data
        self.index = index
        
        self.grid_columnconfigure(1, weight=1)
        
        # Przyciski przesuwania
        btn_frame = ctk.CTkFrame(self, fg_color="transparent", width=30)
        btn_frame.grid(row=0, column=0, rowspan=2, padx=2, pady=2)
        
        btn_up = ctk.CTkButton(
            btn_frame, text="▲", width=25, height=20,
            fg_color="transparent", text_color="#888",
            hover_color="#444",
            command=lambda: on_move_up(index)
        )
        btn_up.pack(pady=(2, 0))
        
        btn_down = ctk.CTkButton(
            btn_frame, text="▼", width=25, height=20,
            fg_color="transparent", text_color="#888",
            hover_color="#444",
            command=lambda: on_move_down(index)
        )
        btn_down.pack(pady=(0, 2))
        
        # Nazwa materiału
        name = data.get("name", "Bez nazwy")
        lbl_name = ctk.CTkLabel(
            self, text=name,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        lbl_name.grid(row=0, column=1, sticky="ew", padx=10, pady=(5, 0))
        lbl_name.bind("<Button-1>", lambda e: on_select(index))
        
        # Liczba aliasów
        aliases_count = len(data.get("aliases", []))
        lbl_count = ctk.CTkLabel(
            self, text=f"{aliases_count} wzorców",
            font=ctk.CTkFont(size=10),
            text_color="#888"
        )
        lbl_count.grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 5))
        lbl_count.bind("<Button-1>", lambda e: on_select(index))
        
        # Priorytet
        lbl_priority = ctk.CTkLabel(
            self, text=f"#{index + 1}",
            font=ctk.CTkFont(size=10),
            text_color="#666"
        )
        lbl_priority.grid(row=0, column=2, rowspan=2, padx=10)
        
        # Bind kliknięcia
        self.bind("<Button-1>", lambda e: on_select(index))


class RegexEditorPanel(ctk.CTkFrame):
    """Panel edytora reguł regex"""
    
    def __init__(self, parent, on_save: Optional[callable] = None):
        super().__init__(parent, fg_color=Theme.BG_DARK)
        
        self.on_save = on_save
        self.rules: List[Dict[str, Any]] = []
        self.selected_index: int = -1
        self.dirty = False
        
        self._load_rules()
        self._setup_ui()
        self._refresh_list()
    
    def _load_rules(self):
        """Załaduj reguły z pliku"""
        if HAS_PARSER:
            self.rules = get_rules_as_list()
        else:
            self.rules = []
    
    def _save_rules(self):
        """Zapisz reguły do pliku"""
        if not HAS_PARSER:
            return
        
        if save_rules_to_json(self.rules):
            reload_rules()
            self.dirty = False
            self.lbl_status.configure(text="✓ Zapisano pomyślnie", text_color=Theme.ACCENT_SUCCESS)
            self.after(2000, lambda: self.lbl_status.configure(text="", text_color=Theme.TEXT_MUTED))
            
            if self.on_save:
                self.on_save()
        else:
            messagebox.showerror("Błąd", "Nie udało się zapisać reguł")
    
    def _setup_ui(self):
        """Buduj interfejs"""
        self.grid_columnconfigure(0, weight=0)  # Lista materiałów
        self.grid_columnconfigure(1, weight=1)  # Edytor + test
        self.grid_rowconfigure(0, weight=1)
        
        # === LEWY PANEL - Lista materiałów ===
        left_panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, width=320)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_panel.grid_propagate(False)
        
        # Tytuł
        title = ctk.CTkLabel(
            left_panel,
            text="🔧 Grupy Materiałów",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title.pack(pady=(15, 5), padx=10)
        
        # Podtytuł
        subtitle = ctk.CTkLabel(
            left_panel,
            text="Kolejność = Priorytet",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_MUTED
        )
        subtitle.pack(pady=(0, 10))
        
        # Przycisk pomocy
        btn_help = ctk.CTkButton(
            left_panel,
            text="❓ Pomoc / Instrukcja",
            command=self._show_help,
            fg_color="#555",
            hover_color="#666",
            height=30
        )
        btn_help.pack(fill="x", padx=10, pady=(0, 10))
        
        # Scrollowalna lista
        self.scroll_list = ctk.CTkScrollableFrame(left_panel, fg_color="transparent")
        self.scroll_list.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Przycisk dodawania
        btn_add = ctk.CTkButton(
            left_panel,
            text="+ Nowa Grupa Materiałowa",
            command=self._add_group,
            fg_color=Theme.ACCENT_SUCCESS,
            hover_color="#1a9d4a",
            height=40
        )
        btn_add.pack(fill="x", padx=10, pady=10)
        
        # === PRAWY PANEL - Edytor ===
        right_panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        
        # Sekcja nazwy
        name_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        name_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(
            name_frame,
            text="Nazwa Materiału (Standard):",
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w")
        
        name_row = ctk.CTkFrame(name_frame, fg_color="transparent")
        name_row.pack(fill="x", pady=5)
        
        self.entry_name = ctk.CTkEntry(name_row, width=300, height=35)
        self.entry_name.pack(side="left", padx=(0, 10))
        self.entry_name.bind("<KeyRelease>", self._on_name_change)
        
        self.btn_delete = ctk.CTkButton(
            name_row,
            text="🗑️ Usuń Grupę",
            command=self._delete_group,
            fg_color=Theme.ACCENT_DANGER,
            hover_color="#c53030",
            width=120,
            height=35
        )
        self.btn_delete.pack(side="left")
        
        # Separator
        ctk.CTkFrame(right_panel, height=2, fg_color="#444").pack(fill="x", padx=15, pady=10)
        
        # Sekcja aliasów
        ctk.CTkLabel(
            right_panel,
            text="Aliasy / Wzorce RegEx:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15, pady=(5, 5))
        
        # Scrollowalna lista aliasów
        self.scroll_aliases = ctk.CTkScrollableFrame(right_panel, height=180, fg_color=Theme.BG_INPUT)
        self.scroll_aliases.pack(fill="x", padx=15, pady=5)
        
        # Dodawanie aliasu
        add_alias_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        add_alias_frame.pack(fill="x", padx=15, pady=10)
        
        self.entry_new_alias = ctk.CTkEntry(
            add_alias_frame,
            placeholder_text="Nowy wzorzec (np. 'inox\\s*304')",
            height=35
        )
        self.entry_new_alias.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_new_alias.bind("<Return>", lambda e: self._add_alias())
        
        btn_add_alias = ctk.CTkButton(
            add_alias_frame,
            text="+ Dodaj",
            command=self._add_alias,
            width=80,
            height=35
        )
        btn_add_alias.pack(side="left")
        
        # Separator
        ctk.CTkFrame(right_panel, height=2, fg_color="#444").pack(fill="x", padx=15, pady=15)
        
        # Sekcja testowania
        ctk.CTkLabel(
            right_panel,
            text="🧪 Testuj na żywo:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(0, 5))
        
        self.entry_test = ctk.CTkEntry(
            right_panel,
            placeholder_text="Wpisz nazwę pliku do przetestowania...",
            height=40
        )
        self.entry_test.pack(fill="x", padx=15, pady=5)
        self.entry_test.bind("<KeyRelease>", self._run_test)
        
        self.lbl_test_result = ctk.CTkLabel(
            right_panel,
            text="Wynik: ...",
            font=ctk.CTkFont(family="Consolas", size=13),
            anchor="w"
        )
        self.lbl_test_result.pack(fill="x", padx=15, pady=10)
        
        # Footer
        footer = ctk.CTkFrame(right_panel, fg_color="transparent", height=60)
        footer.pack(side="bottom", fill="x", padx=15, pady=15)
        
        self.lbl_status = ctk.CTkLabel(
            footer,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_MUTED
        )
        self.lbl_status.pack(side="left")
        
        btn_save = ctk.CTkButton(
            footer,
            text="💾 ZAPISZ ZMIANY",
            command=self._save_rules,
            width=180,
            height=45,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        btn_save.pack(side="right")
        
        # Domyślnie wyłącz edytor
        self._disable_editor()
    
    def _refresh_list(self):
        """Odśwież listę materiałów"""
        for widget in self.scroll_list.winfo_children():
            widget.destroy()
        
        for idx, rule in enumerate(self.rules):
            is_selected = (idx == self.selected_index)
            card = MaterialCard(
                self.scroll_list,
                data=rule,
                index=idx,
                on_select=self._select_group,
                on_move_up=self._move_up,
                on_move_down=self._move_down,
                is_selected=is_selected
            )
            card.pack(fill="x", pady=2, padx=2)
    
    def _select_group(self, index: int):
        """Wybierz grupę do edycji"""
        self.selected_index = index
        self._refresh_list()
        self._enable_editor()
        self._load_editor_values()
    
    def _load_editor_values(self):
        """Załaduj wartości do edytora"""
        if self.selected_index < 0 or self.selected_index >= len(self.rules):
            return
        
        rule = self.rules[self.selected_index]
        
        # Nazwa
        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, rule.get("name", ""))
        
        # Aliasy
        for widget in self.scroll_aliases.winfo_children():
            widget.destroy()
        
        for alias in rule.get("aliases", []):
            self._create_alias_row(alias)
    
    def _create_alias_row(self, alias_text: str):
        """Utwórz wiersz aliasu"""
        row = ctk.CTkFrame(self.scroll_aliases, fg_color="transparent")
        row.pack(fill="x", pady=2)
        
        entry = ctk.CTkEntry(row, height=30)
        entry.insert(0, alias_text)
        entry.configure(state="disabled")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_del = ctk.CTkButton(
            row,
            text="✕",
            width=30,
            height=30,
            fg_color=Theme.ACCENT_DANGER,
            hover_color="#c53030",
            command=lambda: self._delete_alias(alias_text)
        )
        btn_del.pack(side="right")
    
    def _on_name_change(self, event):
        """Obsłuż zmianę nazwy"""
        if self.selected_index >= 0:
            self.rules[self.selected_index]["name"] = self.entry_name.get()
            self.dirty = True
            self._refresh_list()
    
    def _move_up(self, index: int):
        """Przesuń w górę (wyższy priorytet)"""
        if index > 0:
            self.rules[index], self.rules[index - 1] = self.rules[index - 1], self.rules[index]
            self.selected_index = index - 1
            self.dirty = True
            self._refresh_list()
    
    def _move_down(self, index: int):
        """Przesuń w dół (niższy priorytet)"""
        if index < len(self.rules) - 1:
            self.rules[index], self.rules[index + 1] = self.rules[index + 1], self.rules[index]
            self.selected_index = index + 1
            self.dirty = True
            self._refresh_list()
    
    def _add_group(self):
        """Dodaj nową grupę"""
        new_rule = {"name": "NOWY MATERIAŁ", "aliases": []}
        self.rules.insert(0, new_rule)
        self.selected_index = 0
        self.dirty = True
        self._refresh_list()
        self._enable_editor()
        self._load_editor_values()
        self.entry_name.focus_set()
        self.entry_name.select_range(0, "end")
    
    def _delete_group(self):
        """Usuń grupę"""
        if self.selected_index >= 0:
            name = self.rules[self.selected_index].get("name", "")
            if messagebox.askyesno("Potwierdzenie", f"Czy na pewno usunąć grupę '{name}'?"):
                del self.rules[self.selected_index]
                self.selected_index = -1
                self.dirty = True
                self._refresh_list()
                self._disable_editor()
    
    def _add_alias(self):
        """Dodaj alias"""
        if self.selected_index < 0:
            return
        
        val = self.entry_new_alias.get().strip()
        if val:
            self.rules[self.selected_index]["aliases"].append(val)
            self.dirty = True
            self.entry_new_alias.delete(0, "end")
            self._load_editor_values()
    
    def _delete_alias(self, alias_val: str):
        """Usuń alias"""
        if self.selected_index < 0:
            return
        
        if alias_val in self.rules[self.selected_index]["aliases"]:
            self.rules[self.selected_index]["aliases"].remove(alias_val)
            self.dirty = True
            self._load_editor_values()
    
    def _disable_editor(self):
        """Wyłącz edytor"""
        self.entry_name.configure(state="disabled")
        self.entry_new_alias.configure(state="disabled")
        self.btn_delete.configure(state="disabled")
        self.entry_test.configure(state="disabled")
    
    def _enable_editor(self):
        """Włącz edytor"""
        self.entry_name.configure(state="normal")
        self.entry_new_alias.configure(state="normal")
        self.btn_delete.configure(state="normal")
        self.entry_test.configure(state="normal")
    
    def _run_test(self, event=None):
        """Testuj wzorce na żywo"""
        if not HAS_PARSER:
            return
        
        import re
        from quotations.utils.name_parser import MaterialPattern, MATERIAL_PATTERNS
        
        _TOKEN_LEFT = r"(?:^|[_\-\s\.,\(\)\[\]\{\}])"
        _TOKEN_RIGHT = r"(?:$|[_\-\s\.,\(\)\[\]\{\}])"
        
        try:
            # Tymczasowo załaduj bieżące reguły
            temp_patterns = []
            for priority, item in enumerate(self.rules):
                label = item.get("name", "Unknown")
                for alias in item.get("aliases", []):
                    clean_p = alias.replace(r"\b", "")
                    regex_str = f"{_TOKEN_LEFT}(?:{clean_p}){_TOKEN_RIGHT}"
                    try:
                        pat = MaterialPattern(
                            regex=re.compile(regex_str, re.IGNORECASE),
                            label=label,
                            priority=priority
                        )
                        temp_patterns.append(pat)
                    except:
                        pass
            
            # Podmień tymczasowo
            old_patterns = MATERIAL_PATTERNS.copy()
            MATERIAL_PATTERNS.clear()
            MATERIAL_PATTERNS.extend(temp_patterns)
            
            # Testuj
            fname = self.entry_test.get()
            if not fname:
                self.lbl_test_result.configure(text="Wynik: ...", text_color=Theme.TEXT_MUTED)
                MATERIAL_PATTERNS.clear()
                MATERIAL_PATTERNS.extend(old_patterns)
                return
            
            res = parse_filename(fname)
            
            mat = res.get("material") or "BRAK"
            th = res.get("thickness_mm")
            qty = res.get("quantity")
            
            th_str = f"{th} mm" if th else "BRAK"
            qty_str = f"{qty} szt" if qty else "BRAK"
            
            result_text = f"Materiał: {mat}  |  Grubość: {th_str}  |  Ilość: {qty_str}"
            color = Theme.ACCENT_SUCCESS if mat != "BRAK" else Theme.ACCENT_WARNING
            
            self.lbl_test_result.configure(text=result_text, text_color=color)
            
            # Przywróć oryginalne
            MATERIAL_PATTERNS.clear()
            MATERIAL_PATTERNS.extend(old_patterns)
            
        except Exception as e:
            self.lbl_test_result.configure(text=f"Błąd: {e}", text_color=Theme.ACCENT_DANGER)
    
    def _show_help(self):
        """Pokaż okno pomocy"""
        help_window = ctk.CTkToplevel(self)
        help_window.title("Instrukcja RegEx")
        help_window.geometry("550x650")
        help_window.configure(fg_color=Theme.BG_DARK)
        
        # Wycentruj
        help_window.update_idletasks()
        x = (help_window.winfo_screenwidth() - 550) // 2
        y = (help_window.winfo_screenheight() - 650) // 2
        help_window.geometry(f"+{x}+{y}")
        
        help_window.attributes("-topmost", True)
        
        # Tytuł
        ctk.CTkLabel(
            help_window,
            text="📚 Instrukcja RegEx",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=15)
        
        # Textbox
        textbox = ctk.CTkTextbox(
            help_window,
            font=("Consolas", 12),
            fg_color=Theme.BG_CARD
        )
        textbox.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        textbox.insert("0.0", HELP_TEXT)
        textbox.configure(state="disabled")
        
        # Przycisk zamknij
        ctk.CTkButton(
            help_window,
            text="Zamknij",
            command=help_window.destroy,
            width=120
        ).pack(pady=10)


# ============================================================
# Standalone window wrapper
# ============================================================

class RegexEditorWindow(ctk.CTkToplevel):
    """Okno edytora regex jako popup"""
    
    def __init__(self, parent=None, on_save: Optional[callable] = None):
        super().__init__(parent)
        
        self.title("🔧 Edytor Reguł Materiałów")
        self.geometry("1100x700")
        self.configure(fg_color=Theme.BG_DARK)
        
        # Wycentruj
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 1100) // 2
        y = (self.winfo_screenheight() - 700) // 2
        self.geometry(f"+{x}+{y}")
        
        self.panel = RegexEditorPanel(self, on_save=on_save)
        self.panel.pack(fill="both", expand=True)
        
        self.lift()
        self.focus_force()


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.title("Regex Editor Test")
    root.geometry("1100x700")
    
    panel = RegexEditorPanel(root)
    panel.pack(fill="both", expand=True)
    
    root.mainloop()
