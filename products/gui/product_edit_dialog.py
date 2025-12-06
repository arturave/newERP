#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProductEditDialog - Dialog dodawania/edycji produktu

Funkcjonalności:
- Formularz danych produktu
- Upload plików CAD (DXF, STEP)
- Upload obrazu użytkownika
- Podgląd plików
- Zarządzanie załącznikami
- Walidacja danych
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from typing import Optional, Dict, List
from pathlib import Path
import threading

from products import ProductService
from products.paths import StoragePaths
from config.settings import (
    ALLOWED_CAD_2D, ALLOWED_CAD_3D, ALLOWED_IMAGES, 
    MAX_FILE_SIZE_MB, get_mime_type
)


class ProductEditDialog(ctk.CTkToplevel):
    """
    Dialog edycji produktu.
    
    Używany zarówno do tworzenia nowych produktów jak i edycji istniejących.
    """
    
    def __init__(
        self, 
        parent, 
        service: ProductService,
        product: Dict = None
    ):
        """
        Inicjalizacja dialogu.
        
        Args:
            parent: Okno nadrzędne
            service: Instancja ProductService
            product: Dane produktu do edycji (None = nowy produkt)
        """
        super().__init__(parent)
        
        self.service = service
        self.product = product
        self.is_edit_mode = product is not None
        self.result = None
        
        # Pliki do uploadu
        self.files_to_upload: Dict[str, bytes] = {}
        self.file_extensions: Dict[str, str] = {}
        self.file_paths: Dict[str, str] = {}  # Ścieżki lokalne dla wyświetlenia
        
        # Konfiguracja okna
        title = f"Edycja: {product.get('name', '')}" if self.is_edit_mode else "Nowy produkt"
        self.title(title)
        self.geometry("800x700")
        self.minsize(700, 600)
        
        # Modal
        self.transient(parent)
        self.grab_set()
        
        # Buduj interfejs
        self._setup_ui()
        
        # Załaduj dane jeśli edycja
        if self.is_edit_mode:
            self._load_product_data()
    
    # =========================================================
    # UI SETUP
    # =========================================================
    
    def _setup_ui(self):
        """Zbuduj interfejs"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Scrollable main frame
        main_scroll = ctk.CTkScrollableFrame(self)
        main_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_scroll.grid_columnconfigure(1, weight=1)
        
        row = 0
        
        # === SEKCJA: DANE PODSTAWOWE ===
        row = self._create_section_header(main_scroll, "📋 Dane podstawowe", row)
        
        # Nazwa
        row = self._create_field(main_scroll, "Nazwa *", row)
        self.name_entry = ctk.CTkEntry(main_scroll, width=400)
        self.name_entry.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # Kod indeksowy
        row = self._create_field(main_scroll, "Kod indeksowy", row)
        self.idx_code_entry = ctk.CTkEntry(main_scroll, width=200)
        self.idx_code_entry.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        if not self.is_edit_mode:
            self.idx_code_entry.configure(placeholder_text="Auto-generowany")
        
        # Kategoria
        row = self._create_field(main_scroll, "Kategoria", row)
        categories = [""] + self.service.products.get_unique_categories()
        self.category_combo = ctk.CTkComboBox(main_scroll, values=categories, width=200)
        self.category_combo.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # === SEKCJA: MATERIAŁ ===
        row = self._create_section_header(main_scroll, "🔩 Materiał i wymiary", row)
        
        # Materiał
        row = self._create_field(main_scroll, "Materiał", row)
        materials = self.service.products.get_unique_materials()
        self._material_map = {m['name']: m['id'] for m in materials}
        self._material_map_rev = {m['id']: m['name'] for m in materials}
        material_names = [""] + list(self._material_map.keys())
        self.material_combo = ctk.CTkComboBox(main_scroll, values=material_names, width=250)
        self.material_combo.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # Grubość
        row = self._create_field(main_scroll, "Grubość [mm]", row)
        self.thickness_entry = ctk.CTkEntry(main_scroll, width=100)
        self.thickness_entry.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # Wymiary (w jednym wierszu)
        row = self._create_field(main_scroll, "Wymiary [mm]", row)
        dims_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        dims_frame.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        ctk.CTkLabel(dims_frame, text="S:").pack(side="left")
        self.width_entry = ctk.CTkEntry(dims_frame, width=70)
        self.width_entry.pack(side="left", padx=(2, 10))
        
        ctk.CTkLabel(dims_frame, text="W:").pack(side="left")
        self.height_entry = ctk.CTkEntry(dims_frame, width=70)
        self.height_entry.pack(side="left", padx=(2, 10))
        
        ctk.CTkLabel(dims_frame, text="D:").pack(side="left")
        self.length_entry = ctk.CTkEntry(dims_frame, width=70)
        self.length_entry.pack(side="left", padx=2)
        
        # === SEKCJA: KOSZTY ===
        row = self._create_section_header(main_scroll, "💰 Koszty [PLN]", row)
        
        costs_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        costs_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=5)
        row += 1
        
        # Koszty w jednym wierszu
        cost_fields = [
            ("Materiał:", "material_cost"),
            ("Laser:", "laser_cost"),
            ("Gięcie:", "bending_cost"),
            ("Dodatkowe:", "additional_costs"),
        ]
        
        self.cost_entries = {}
        for label, field in cost_fields:
            ctk.CTkLabel(costs_frame, text=label).pack(side="left", padx=(10, 2))
            entry = ctk.CTkEntry(costs_frame, width=80)
            entry.pack(side="left", padx=(0, 10))
            self.cost_entries[field] = entry
        
        # === SEKCJA: PLIKI ===
        row = self._create_section_header(main_scroll, "📁 Pliki", row)
        
        # CAD 2D
        row = self._create_file_field(main_scroll, "Plik CAD 2D", "cad_2d", 
                                       ALLOWED_CAD_2D, row)
        
        # CAD 3D
        row = self._create_file_field(main_scroll, "Plik CAD 3D", "cad_3d",
                                       ALLOWED_CAD_3D, row)
        
        # Obraz użytkownika
        row = self._create_file_field(main_scroll, "Obraz produktu", "user_image",
                                       ALLOWED_IMAGES, row)
        
        # Wybór źródła grafiki głównej
        row = self._create_field(main_scroll, "Źródło podglądu", row)
        self.graphic_source_var = ctk.StringVar(value="AUTO")
        self.graphic_source_combo = ctk.CTkComboBox(
            main_scroll,
            width=200,
            variable=self.graphic_source_var,
            values=["AUTO", "Obraz użytkownika", "CAD 2D", "CAD 3D"],
            state="readonly"
        )
        self.graphic_source_combo.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # Etykieta pomocy
        source_help = ctk.CTkLabel(
            main_scroll,
            text="AUTO = priorytet: Użytkownik > 2D > 3D",
            text_color="gray60",
            font=("", 10)
        )
        source_help.grid(row=row-1, column=2, sticky="w", padx=5)
        
        # === SEKCJA: OPIS ===
        row = self._create_section_header(main_scroll, "📝 Opis i uwagi", row)
        
        # Opis
        row = self._create_field(main_scroll, "Opis", row)
        self.description_text = ctk.CTkTextbox(main_scroll, width=400, height=80)
        self.description_text.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # Uwagi
        row = self._create_field(main_scroll, "Uwagi", row)
        self.notes_text = ctk.CTkTextbox(main_scroll, width=400, height=60)
        self.notes_text.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # === PRZYCISKI ===
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        
        ctk.CTkButton(
            buttons_frame,
            text="❌ Anuluj",
            width=100,
            fg_color="gray",
            command=self._on_cancel
        ).pack(side="left", padx=10)
        
        self.save_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 Zapisz",
            width=120,
            fg_color="green",
            command=self._on_save
        )
        self.save_btn.pack(side="right", padx=10)
        
        # Progress bar (ukryty domyślnie)
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="")
        self.progress_label.pack(side="left", padx=10)
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=200)
        self.progress_bar.pack(side="left", padx=5)
        self.progress_bar.set(0)
    
    def _create_section_header(self, parent, text: str, row: int) -> int:
        """Utwórz nagłówek sekcji"""
        header = ctk.CTkLabel(
            parent, 
            text=text, 
            font=ctk.CTkFont(size=14, weight="bold")
        )
        header.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=(15, 5))
        return row + 1
    
    def _create_field(self, parent, label: str, row: int) -> int:
        """Utwórz etykietę pola"""
        ctk.CTkLabel(parent, text=label, anchor="e", width=120).grid(
            row=row, column=0, sticky="e", padx=5, pady=3
        )
        return row + 1
    
    def _create_file_field(
        self, 
        parent, 
        label: str, 
        file_type: str,
        allowed_ext: set,
        row: int
    ) -> int:
        """Utwórz pole wyboru pliku"""
        row = self._create_field(parent, label, row)
        
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.grid(row=row-1, column=1, sticky="w", padx=5, pady=3)
        
        # Etykieta z nazwą pliku
        file_label = ctk.CTkLabel(file_frame, text="Nie wybrano", width=250, anchor="w")
        file_label.pack(side="left", padx=(0, 10))
        
        # Przycisk wyboru
        ext_str = ", ".join(e.upper() for e in allowed_ext)
        
        def browse():
            filetypes = [(f"Pliki {ext_str}", " ".join(f"*{e}" for e in allowed_ext))]
            filepath = filedialog.askopenfilename(filetypes=filetypes)
            if filepath:
                self._on_file_selected(file_type, filepath, file_label)
        
        ctk.CTkButton(
            file_frame,
            text="📂 Wybierz...",
            width=100,
            command=browse
        ).pack(side="left", padx=5)
        
        # Przycisk usuń
        def clear():
            self._on_file_cleared(file_type, file_label)
        
        ctk.CTkButton(
            file_frame,
            text="✕",
            width=30,
            fg_color="gray",
            command=clear
        ).pack(side="left", padx=5)
        
        # Zachowaj referencję do etykiety
        setattr(self, f"{file_type}_label", file_label)
        
        return row
    
    # =========================================================
    # DATA HANDLING
    # =========================================================
    
    def _load_product_data(self):
        """Załaduj dane produktu do formularza"""
        if not self.product:
            return
        
        # Dane podstawowe
        self.name_entry.insert(0, self.product.get('name', ''))
        self.idx_code_entry.insert(0, self.product.get('idx_code', ''))
        
        if self.product.get('category'):
            self.category_combo.set(self.product['category'])
        
        # Materiał
        material_id = self.product.get('material_id')
        if material_id and material_id in self._material_map_rev:
            self.material_combo.set(self._material_map_rev[material_id])
        
        # Wymiary
        if self.product.get('thickness_mm'):
            self.thickness_entry.insert(0, str(self.product['thickness_mm']))
        if self.product.get('width_mm'):
            self.width_entry.insert(0, str(self.product['width_mm']))
        if self.product.get('height_mm'):
            self.height_entry.insert(0, str(self.product['height_mm']))
        if self.product.get('length_mm'):
            self.length_entry.insert(0, str(self.product['length_mm']))
        
        # Koszty
        for field, entry in self.cost_entries.items():
            value = self.product.get(field)
            if value is not None:
                entry.insert(0, str(value))
        
        # Opisy
        if self.product.get('description'):
            self.description_text.insert("1.0", self.product['description'])
        if self.product.get('notes'):
            self.notes_text.insert("1.0", self.product['notes'])
        
        # Pliki (pokaż nazwy istniejących)
        for file_type in ['cad_2d', 'cad_3d', 'user_image']:
            filename = self.product.get(f'{file_type}_filename')
            if filename:
                label = getattr(self, f"{file_type}_label", None)
                if label:
                    label.configure(text=f"✓ {filename}")
        
        # Źródło grafiki
        graphic_source = self.product.get('primary_graphic_source', 'AUTO')
        source_map = {
            'USER': 'Obraz użytkownika',
            '2D': 'CAD 2D',
            '3D': 'CAD 3D',
            'AUTO': 'AUTO',
            None: 'AUTO'
        }
        self.graphic_source_var.set(source_map.get(graphic_source, 'AUTO'))
    
    def _on_file_selected(self, file_type: str, filepath: str, label):
        """Obsługa wyboru pliku"""
        try:
            # Sprawdź rozmiar
            file_size = Path(filepath).stat().st_size
            if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                messagebox.showerror(
                    "Błąd", 
                    f"Plik za duży! Max {MAX_FILE_SIZE_MB} MB"
                )
                return
            
            # Wczytaj dane
            with open(filepath, 'rb') as f:
                data = f.read()
            
            # Zapisz do uploadu
            self.files_to_upload[file_type] = data
            self.file_extensions[file_type] = Path(filepath).suffix.lstrip('.')
            self.file_paths[file_type] = filepath
            
            # Zapisz oryginalną nazwę pliku (dla metadanych w bazie)
            original_filename = Path(filepath).name
            self.file_extensions[f"{file_type}_original_name"] = original_filename
            
            # Aktualizuj etykietę
            size_mb = file_size / (1024 * 1024)
            label.configure(text=f"✓ {original_filename} ({size_mb:.1f} MB)")
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można wczytać pliku:\n{e}")
    
    def _on_file_cleared(self, file_type: str, label):
        """Obsługa usunięcia pliku"""
        self.files_to_upload.pop(file_type, None)
        self.file_extensions.pop(file_type, None)
        self.file_paths.pop(file_type, None)
        label.configure(text="Nie wybrano")
    
    def _collect_form_data(self) -> Dict:
        """Zbierz dane z formularza"""
        data = {}
        
        # Nazwa (wymagana)
        name = self.name_entry.get().strip()
        if not name:
            raise ValueError("Nazwa produktu jest wymagana")
        data['name'] = name
        
        # Kod indeksowy
        idx_code = self.idx_code_entry.get().strip()
        if idx_code:
            data['idx_code'] = idx_code
        
        # Kategoria
        category = self.category_combo.get()
        if category:
            data['category'] = category
        
        # Materiał
        material = self.material_combo.get()
        if material and material in self._material_map:
            data['material_id'] = self._material_map[material]
        
        # Wymiary (z walidacją)
        for field, entry in [
            ('thickness_mm', self.thickness_entry),
            ('width_mm', self.width_entry),
            ('height_mm', self.height_entry),
            ('length_mm', self.length_entry),
        ]:
            value = entry.get().strip()
            if value:
                try:
                    data[field] = float(value.replace(',', '.'))
                except ValueError:
                    raise ValueError(f"Nieprawidłowa wartość: {field}")
        
        # Koszty
        for field, entry in self.cost_entries.items():
            value = entry.get().strip()
            if value:
                try:
                    data[field] = float(value.replace(',', '.'))
                except ValueError:
                    raise ValueError(f"Nieprawidłowa wartość kosztu: {field}")
        
        # Opisy
        description = self.description_text.get("1.0", "end-1c").strip()
        if description:
            data['description'] = description
        
        notes = self.notes_text.get("1.0", "end-1c").strip()
        if notes:
            data['notes'] = notes
        
        # Źródło grafiki
        graphic_source = self.graphic_source_var.get()
        source_map = {
            'Obraz użytkownika': 'USER',
            'CAD 2D': '2D',
            'CAD 3D': '3D',
            'AUTO': None  # None = automatyczny wybór przy generowaniu
        }
        if graphic_source != 'AUTO':
            data['primary_graphic_source'] = source_map.get(graphic_source)
        
        return data
    
    # =========================================================
    # ACTIONS
    # =========================================================
    
    def _on_save(self):
        """Zapisz produkt"""
        try:
            # Zbierz dane
            data = self._collect_form_data()
        except ValueError as e:
            messagebox.showerror("Błąd walidacji", str(e))
            return
        
        # Pokaż progress
        self._show_progress("Zapisywanie...")
        self.save_btn.configure(state="disabled")
        
        # Uruchom w wątku
        thread = threading.Thread(
            target=self._save_thread, 
            args=(data,),
            daemon=True
        )
        thread.start()
    
    def _save_thread(self, data: Dict):
        """Wątek zapisujący produkt"""
        try:
            if self.is_edit_mode:
                # Aktualizacja
                product_id = self.product['id']
                
                self.after(0, lambda: self._update_progress("Aktualizacja danych...", 0.3))
                
                success, message = self.service.update_product(
                    product_id,
                    data=data,
                    files=self.files_to_upload if self.files_to_upload else None,
                    file_extensions=self.file_extensions if self.file_extensions else None
                )
            else:
                # Nowy produkt
                self.after(0, lambda: self._update_progress("Tworzenie produktu...", 0.3))
                
                success, result = self.service.create_product(
                    data=data,
                    files=self.files_to_upload if self.files_to_upload else None,
                    file_extensions=self.file_extensions if self.file_extensions else None
                )
                message = result if not success else "Produkt utworzony"
            
            self.after(0, lambda: self._update_progress("Zakończono", 1.0))
            
            if success:
                self.after(100, lambda: self._on_save_success(message))
            else:
                self.after(100, lambda: self._on_save_error(message))
                
        except Exception as e:
            self.after(0, lambda: self._on_save_error(str(e)))
    
    def _show_progress(self, text: str):
        """Pokaż pasek postępu"""
        self.progress_label.configure(text=text)
        self.progress_bar.set(0.1)
        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
    
    def _update_progress(self, text: str, value: float):
        """Aktualizuj pasek postępu"""
        self.progress_label.configure(text=text)
        self.progress_bar.set(value)
    
    def _hide_progress(self):
        """Ukryj pasek postępu"""
        self.progress_frame.grid_forget()
        self.save_btn.configure(state="normal")
    
    def _on_save_success(self, message: str):
        """Obsługa sukcesu zapisu"""
        self._hide_progress()
        self.result = True
        messagebox.showinfo("Sukces", message)
        self.destroy()
    
    def _on_save_error(self, message: str):
        """Obsługa błędu zapisu"""
        self._hide_progress()
        messagebox.showerror("Błąd", f"Nie udało się zapisać:\n{message}")
    
    def _on_cancel(self):
        """Anuluj i zamknij"""
        self.result = None
        self.destroy()


# =========================================================
# STANDALONE TEST
# =========================================================

if __name__ == "__main__":
    from products import create_product_service
    
    ctk.set_appearance_mode("dark")
    
    root = ctk.CTk()
    root.withdraw()
    
    service = create_product_service()
    dialog = ProductEditDialog(root, service=service)
    dialog.mainloop()
