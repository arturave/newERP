#!/usr/bin/env python3
"""
Test integracji modułu nestingu
===============================
Demonstracja nowego systemu nestingu z:
- Parsowaniem nazw plików (materiał, grubość, ilość)
- Wczytywaniem DXF
- Grupowaniem per materiał+grubość
- Zakładkami nestingu
- Obliczaniem kosztów

Uruchomienie:
    python test_nesting_integration.py [folder_z_dxf]
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Dodaj ścieżkę do projektu
sys.path.insert(0, str(Path(__file__).parent))

import customtkinter as ctk
from tkinter import filedialog, messagebox
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Import modułów
try:
    from quotations.utils.dxf_loader import load_dxf, DXFPart
    from quotations.utils.name_parser import parse_filename_with_folder_context, reload_rules
    from quotations.gui.nesting_tabs_panel import NestingTabsPanel, Theme
    from quotations.gui.regex_editor_panel import RegexEditorWindow
    HAS_MODULES = True
except ImportError as e:
    logger.error(f"Import error: {e}")
    HAS_MODULES = False


class NestingIntegrationApp(ctk.CTk):
    """Aplikacja testowa integracji nestingu"""
    
    def __init__(self):
        super().__init__()
        
        self.title("🔧 Nesting Integration Test - NewERP")
        self.geometry("1500x900")
        self.configure(fg_color="#0f0f0f")
        
        self.loaded_parts: list = []
        self.parts_by_group: dict = {}
        self.nesting_panel: Optional[NestingTabsPanel] = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Buduj interfejs"""
        # Header
        header = ctk.CTkFrame(self, fg_color="#1a1a1a", height=70)
        header.pack(fill="x", padx=10, pady=10)
        header.pack_propagate(False)
        
        title = ctk.CTkLabel(
            header,
            text="🔧 Test Integracji Nestingu",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#8b5cf6"
        )
        title.pack(side="left", padx=20, pady=15)
        
        # Przyciski
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=20)
        
        btn_load = ctk.CTkButton(
            btn_frame,
            text="📁 Wczytaj folder DXF",
            command=self.load_folder,
            fg_color="#22c55e",
            width=180,
            height=40
        )
        btn_load.pack(side="left", padx=5)
        
        self.btn_nest_all = ctk.CTkButton(
            btn_frame,
            text="▶ Nestuj wszystko",
            command=self.nest_all,
            fg_color="#f59e0b",
            hover_color="#d97706",
            width=150,
            height=40,
            state="disabled"
        )
        self.btn_nest_all.pack(side="left", padx=5)
        
        btn_clear = ctk.CTkButton(
            btn_frame,
            text="🗑️ Wyczyść",
            command=self.clear_all,
            fg_color="#ef4444",
            hover_color="#dc2626",
            width=100,
            height=40
        )
        btn_clear.pack(side="left", padx=5)
        
        btn_regex = ctk.CTkButton(
            btn_frame,
            text="🔧 Edytor Regex",
            command=self.open_regex_editor,
            fg_color="#06b6d4",
            width=140,
            height=40
        )
        btn_regex.pack(side="left", padx=5)
        
        # Main content
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Placeholder
        self.placeholder = ctk.CTkLabel(
            self.main_frame,
            text="Wczytaj folder z plikami DXF aby rozpocząć nesting.\n\n"
                 "Pliki zostaną automatycznie pogrupowane według:\n"
                 "• Materiału (wykrytego z nazwy pliku)\n"
                 "• Grubości (wykrytej z nazwy pliku)\n\n"
                 "Każda grupa otrzyma własną zakładkę z nestingiem.\n\n"
                 "Możesz wczytać wiele folderów - detale będą dodawane do istniejących grup.",
            font=ctk.CTkFont(size=14),
            text_color="#666"
        )
        self.placeholder.pack(expand=True)
        
        # Statusbar
        self.statusbar = ctk.CTkFrame(self, fg_color="#1a1a1a", height=35)
        self.statusbar.pack(fill="x", padx=10, pady=(0, 10))
        self.statusbar.pack_propagate(False)
        
        self.lbl_status = ctk.CTkLabel(
            self.statusbar,
            text="Gotowy",
            font=ctk.CTkFont(size=11),
            text_color="#888"
        )
        self.lbl_status.pack(side="left", padx=15, pady=8)
    
    def clear_all(self):
        """Wyczyść wszystkie wczytane dane"""
        self.loaded_parts.clear()
        self.parts_by_group.clear()
        
        # Usuń panel nestingu jeśli istnieje
        if self.nesting_panel:
            self.nesting_panel.destroy()
            self.nesting_panel = None
        
        # Przywróć placeholder
        self.placeholder = ctk.CTkLabel(
            self.main_frame,
            text="Wczytaj folder z plikami DXF aby rozpocząć nesting.\n\n"
                 "Pliki zostaną automatycznie pogrupowane według:\n"
                 "• Materiału (wykrytego z nazwy pliku)\n"
                 "• Grubości (wykrytej z nazwy pliku)\n\n"
                 "Każda grupa otrzyma własną zakładkę z nestingiem.\n\n"
                 "Możesz wczytać wiele folderów - detale będą dodawane do istniejących grup.",
            font=ctk.CTkFont(size=14),
            text_color="#666"
        )
        self.placeholder.pack(expand=True)
        
        self.btn_nest_all.configure(state="disabled")
        self.lbl_status.configure(text="Wyczyszczono")
    
    def nest_all(self):
        """Uruchom nesting na wszystkich zakładkach"""
        if self.nesting_panel:
            self.nesting_panel.start_all_nesting()
            self.lbl_status.configure(text="Uruchomiono nesting na wszystkich zakładkach...")
    
    def load_folder(self):
        """Wczytaj folder z plikami DXF"""
        folder = filedialog.askdirectory(title="Wybierz folder z plikami DXF")
        if not folder:
            return
        
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
            summary += f"• {mat} {th}mm: {len(parts)} typów, {total_qty} szt\n"
        
        logger.info(summary)
    
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
            on_all_complete=self._on_all_nesting_complete
        )
        self.nesting_panel.pack(fill="both", expand=True)
        
        # Włącz przycisk "Nestuj wszystko"
        self.btn_nest_all.configure(state="normal")
    
    def _on_all_nesting_complete(self, results: dict):
        """Callback gdy wszystkie nestingi zakończone"""
        total_parts = sum(len(r.placed_parts) for r in results.values())
        total_sheets = sum(r.sheets_used for r in results.values())
        total_unplaced = sum(r.unplaced_count for r in results.values())
        total_cost = sum(r.total_cost for r in results.values())
        
        status_text = f"✓ Wszystkie nestingi zakończone! {total_parts} detali na {total_sheets} arkuszach"
        if total_unplaced > 0:
            status_text += f" | ⚠️ {total_unplaced} nieznestowanych"
        if total_cost > 0:
            status_text += f" | Koszt: {total_cost:.2f} PLN"
        
        self.lbl_status.configure(text=status_text)
        
        # Wyświetl podsumowanie
        summary = "=== PODSUMOWANIE NESTINGU ===\n\n"
        
        for (mat, th), result in results.items():
            summary += f"{mat} {th}mm:\n"
            summary += f"  Detali umieszczonych: {len(result.placed_parts)}\n"
            summary += f"  Arkuszy użytych: {result.sheets_used}\n"
            summary += f"  Efektywność: {result.total_efficiency:.1%}\n"
            
            if result.unplaced_count > 0:
                summary += f"  ⚠️ Nieumieszczonych: {result.unplaced_count}\n"
                for up in result.unplaced_parts[:3]:  # Pokaż max 3
                    summary += f"    - {up.name}: {up.reason}\n"
                if result.unplaced_count > 3:
                    summary += f"    ... i {result.unplaced_count - 3} więcej\n"
            
            if result.total_cost > 0:
                summary += f"  Koszt materiału: {result.total_cost:.2f} PLN\n"
            summary += "\n"
        
        logger.info(summary)
    
    def open_regex_editor(self):
        """Otwórz edytor regex"""
        def on_save():
            reload_rules()
            logger.info("Reguły regex zaktualizowane")
        
        editor = RegexEditorWindow(self, on_save=on_save)


def main():
    """Punkt wejścia"""
    if not HAS_MODULES:
        print("ERROR: Brak wymaganych modułów. Sprawdź import errors powyżej.")
        return
    
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    app = NestingIntegrationApp()
    
    # Jeśli podano folder jako argument
    if len(sys.argv) > 1:
        folder = sys.argv[1]
        if os.path.isdir(folder):
            app.after(100, lambda: app.load_folder_path(folder))
    
    app.mainloop()


if __name__ == "__main__":
    main()
