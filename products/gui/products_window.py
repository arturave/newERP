#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProductsWindow - Główne okno zarządzania katalogiem produktów

Funkcjonalności:
- Lista produktów z miniaturami (TreeView)
- Filtrowanie po kategorii, materiale, grubości
- Wyszukiwanie tekstowe
- Dodawanie, edycja, usuwanie produktów
- Lazy loading dla wydajności
- Podgląd produktu w panelu bocznym
"""

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, List, Callable
from pathlib import Path
from PIL import Image, ImageTk
import io
import threading
from datetime import datetime

from products import create_product_service, ProductService
from products.paths import StoragePaths
from config.settings import (
    CTK_APPEARANCE_MODE, CTK_COLOR_THEME,
    PRODUCTS_PAGE_SIZE, TREEVIEW_ROW_HEIGHT
)


class ProductsWindow(ctk.CTkToplevel):
    """
    Główne okno katalogu produktów.
    
    Wyświetla listę produktów z filtrami, wyszukiwaniem
    i panelem podglądu. Umożliwia CRUD na produktach.
    """
    
    def __init__(
        self, 
        parent=None, 
        service: ProductService = None,
        on_product_selected: Callable = None
    ):
        """
        Inicjalizacja okna produktów.
        
        Args:
            parent: Okno nadrzędne
            service: Instancja ProductService (opcjonalna - utworzy nową)
            on_product_selected: Callback wywoływany przy wyborze produktu
        """
        super().__init__(parent)
        
        # Serwis
        self.service = service or create_product_service()
        self.on_product_selected = on_product_selected
        
        # Stan
        self.products: List[Dict] = []
        self.selected_product: Optional[Dict] = None
        self.current_page = 0
        self.total_count = 0
        self.is_loading = False
        
        # Cache miniatur
        self.thumbnail_cache: Dict[str, ImageTk.PhotoImage] = {}
        self._preview_cache: Dict[str, bytes] = {}  # Cache dla preview (URL -> bytes)
        self.default_thumbnail: Optional[ImageTk.PhotoImage] = None
        
        # Konfiguracja okna
        self.title("Katalog Produktów")
        self.geometry("1400x800")
        self.minsize(1000, 600)
        
        # Buduj interfejs
        self._setup_ui()
        self._setup_bindings()
        
        # Załaduj produkty (z opóźnieniem aby UI się wyrenderowało)
        self.after(100, self._initial_load)
    
    def _safe_after(self, ms: int, func):
        """Bezpieczne wywołanie after - sprawdza czy okno istnieje"""
        def safe_call():
            if self.winfo_exists():
                try:
                    func()
                except Exception:
                    pass  # Widget mógł zostać zniszczony
        self.after(ms, safe_call)
    
    # =========================================================
    # UI SETUP
    # =========================================================
    
    def _setup_ui(self):
        """Zbuduj interfejs użytkownika"""
        
        # Główny kontener
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # === GÓRNY PASEK (filtry + wyszukiwanie) ===
        self._create_toolbar()
        
        # === GŁÓWNY OBSZAR ===
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        
        # Lista produktów (lewa strona)
        self._create_product_list(main_frame)
        
        # Panel podglądu (prawa strona)
        self._create_preview_panel(main_frame)
        
        # === DOLNY PASEK (paginacja + akcje) ===
        self._create_bottom_bar()
    
    def _create_toolbar(self):
        """Pasek narzędzi z filtrami"""
        toolbar = ctk.CTkFrame(self)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        # Wyszukiwanie
        ctk.CTkLabel(toolbar, text="🔍").pack(side="left", padx=(10, 5))
        
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            toolbar, 
            textvariable=self.search_var,
            placeholder_text="Szukaj (nazwa, kod, opis)...",
            width=250
        )
        self.search_entry.pack(side="left", padx=5)
        
        # Przycisk szukaj
        ctk.CTkButton(
            toolbar, 
            text="Szukaj", 
            width=80,
            command=self._on_search
        ).pack(side="left", padx=5)
        
        # Separator
        ctk.CTkLabel(toolbar, text="|").pack(side="left", padx=10)
        
        # Filtr kategorii
        ctk.CTkLabel(toolbar, text="Kategoria:").pack(side="left", padx=5)
        self.category_var = ctk.StringVar(value="Wszystkie")
        self.category_combo = ctk.CTkComboBox(
            toolbar,
            variable=self.category_var,
            values=["Wszystkie"],
            width=150,
            command=self._on_filter_change
        )
        self.category_combo.pack(side="left", padx=5)
        
        # Filtr materiału
        ctk.CTkLabel(toolbar, text="Materiał:").pack(side="left", padx=5)
        self.material_var = ctk.StringVar(value="Wszystkie")
        self.material_combo = ctk.CTkComboBox(
            toolbar,
            variable=self.material_var,
            values=["Wszystkie"],
            width=150,
            command=self._on_filter_change
        )
        self.material_combo.pack(side="left", padx=5)
        
        # Filtr grubości
        ctk.CTkLabel(toolbar, text="Grubość:").pack(side="left", padx=5)
        self.thickness_var = ctk.StringVar(value="Wszystkie")
        self.thickness_combo = ctk.CTkComboBox(
            toolbar,
            variable=self.thickness_var,
            values=["Wszystkie"],
            width=100,
            command=self._on_filter_change
        )
        self.thickness_combo.pack(side="left", padx=5)
        
        # Przycisk reset filtrów
        ctk.CTkButton(
            toolbar,
            text="✕ Reset",
            width=70,
            fg_color="gray",
            command=self._reset_filters
        ).pack(side="left", padx=10)
        
        # Przycisk dodaj (po prawej)
        ctk.CTkButton(
            toolbar,
            text="➕ Nowy produkt",
            width=130,
            fg_color="green",
            command=self._on_add_product
        ).pack(side="right", padx=10)
    
    def _create_product_list(self, parent):
        """Lista produktów (TreeView)"""
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Styl TreeView
        style = ttk.Style()
        style.configure(
            "Products.Treeview",
            rowheight=TREEVIEW_ROW_HEIGHT,
            font=('Segoe UI', 10)
        )
        style.configure(
            "Products.Treeview.Heading",
            font=('Segoe UI', 10, 'bold')
        )
        
        # TreeView z kolumnami
        columns = ("idx_code", "name", "category", "material", "thickness", "updated")
        
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="tree headings",
            style="Products.Treeview",
            selectmode="browse"
        )
        
        # Konfiguracja kolumn
        self.tree.column("#0", width=50, stretch=False)  # Miniatura
        self.tree.column("idx_code", width=130, anchor="w")
        self.tree.column("name", width=250, anchor="w")
        self.tree.column("category", width=120, anchor="w")
        self.tree.column("material", width=120, anchor="w")
        self.tree.column("thickness", width=80, anchor="center")
        self.tree.column("updated", width=100, anchor="center")
        
        # Nagłówki
        self.tree.heading("#0", text="")
        self.tree.heading("idx_code", text="Kod", command=lambda: self._sort_by("idx_code"))
        self.tree.heading("name", text="Nazwa", command=lambda: self._sort_by("name"))
        self.tree.heading("category", text="Kategoria", command=lambda: self._sort_by("category"))
        self.tree.heading("material", text="Materiał")
        self.tree.heading("thickness", text="Grubość", command=lambda: self._sort_by("thickness_mm"))
        self.tree.heading("updated", text="Aktualizacja", command=lambda: self._sort_by("updated_at"))
        
        # Scrollbary
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        # Binding
        self.tree.bind("<<TreeviewSelect>>", self._on_product_select)
        self.tree.bind("<Double-1>", self._on_product_double_click)
    
    def _create_preview_panel(self, parent):
        """Panel podglądu produktu"""
        preview_frame = ctk.CTkFrame(parent, width=350)
        preview_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        preview_frame.grid_propagate(False)
        
        # Tytuł
        ctk.CTkLabel(
            preview_frame, 
            text="Podgląd produktu",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)
        
        # Obraz podglądu
        self.preview_image_label = ctk.CTkLabel(
            preview_frame,
            text="Wybierz produkt",
            width=300,
            height=200
        )
        self.preview_image_label.pack(pady=10)
        
        # Separator
        ctk.CTkFrame(preview_frame, height=2, fg_color="gray").pack(fill="x", padx=10, pady=5)
        
        # Szczegóły
        self.details_frame = ctk.CTkScrollableFrame(preview_frame, height=300)
        self.details_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Placeholder dla szczegółów
        self.detail_labels = {}
        detail_fields = [
            ("Kod:", "idx_code"),
            ("Nazwa:", "name"),
            ("Kategoria:", "category"),
            ("Materiał:", "material_name"),
            ("Grubość:", "thickness_mm"),
            ("Wymiary:", "dimensions"),
            ("Koszty:", "costs"),
            ("Utworzono:", "created_at"),
            ("Aktualizacja:", "updated_at"),
        ]
        
        for label_text, field in detail_fields:
            row = ctk.CTkFrame(self.details_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=label_text, width=100, anchor="e").pack(side="left")
            value_label = ctk.CTkLabel(row, text="-", anchor="w")
            value_label.pack(side="left", padx=5)
            self.detail_labels[field] = value_label
        
        # Separator przed plikami
        ctk.CTkFrame(self.details_frame, height=1, fg_color="gray50").pack(fill="x", pady=8)
        
        # Sekcja plików
        files_header = ctk.CTkLabel(
            self.details_frame, 
            text="📁 Pliki:", 
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        files_header.pack(fill="x", pady=(5, 2))
        
        # Etykiety i przyciski dla plików
        file_fields = [
            ("CAD 2D:", "cad_2d"),
            ("CAD 3D:", "cad_3d"),
            ("Obraz:", "user_image"),
        ]
        
        self.download_buttons = {}
        
        for label_text, field in file_fields:
            row = ctk.CTkFrame(self.details_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            
            ctk.CTkLabel(row, text=label_text, width=60, anchor="e").pack(side="left")
            
            # Etykieta z nazwą pliku
            value_label = ctk.CTkLabel(row, text="—", anchor="w", text_color="gray60", width=150)
            value_label.pack(side="left", padx=5)
            self.detail_labels[f"file_{field}"] = value_label
            
            # Przycisk pobierania (ukryty domyślnie)
            download_btn = ctk.CTkButton(
                row,
                text="⬇",
                width=28,
                height=24,
                font=ctk.CTkFont(size=12),
                command=lambda ft=field: self._download_file(ft)
            )
            download_btn.pack(side="right", padx=2)
            download_btn.pack_forget()  # Ukryj na start
            self.download_buttons[field] = download_btn
        
        # Przyciski akcji
        actions_frame = ctk.CTkFrame(preview_frame, fg_color="transparent")
        actions_frame.pack(fill="x", padx=10, pady=10)
        
        self.edit_btn = ctk.CTkButton(
            actions_frame,
            text="✏️ Edytuj",
            width=100,
            command=self._on_edit_product,
            state="disabled"
        )
        self.edit_btn.pack(side="left", padx=5)
        
        self.delete_btn = ctk.CTkButton(
            actions_frame,
            text="🗑️ Usuń",
            width=100,
            fg_color="red",
            command=self._on_delete_product,
            state="disabled"
        )
        self.delete_btn.pack(side="left", padx=5)
        
        self.select_btn = ctk.CTkButton(
            actions_frame,
            text="✓ Wybierz",
            width=100,
            fg_color="green",
            command=self._on_select_product,
            state="disabled"
        )
        self.select_btn.pack(side="right", padx=5)
    
    def _create_bottom_bar(self):
        """Dolny pasek z paginacją i info"""
        bottom = ctk.CTkFrame(self)
        bottom.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        # Info o liczbie wyników
        self.info_label = ctk.CTkLabel(bottom, text="Ładowanie...")
        self.info_label.pack(side="left", padx=10)
        
        # Paginacja
        pagination = ctk.CTkFrame(bottom, fg_color="transparent")
        pagination.pack(side="right", padx=10)
        
        self.prev_btn = ctk.CTkButton(
            pagination,
            text="← Poprzednie",
            width=100,
            command=self._prev_page,
            state="disabled"
        )
        self.prev_btn.pack(side="left", padx=5)
        
        self.page_label = ctk.CTkLabel(pagination, text="Strona 1")
        self.page_label.pack(side="left", padx=10)
        
        self.next_btn = ctk.CTkButton(
            pagination,
            text="Następne →",
            width=100,
            command=self._next_page,
            state="disabled"
        )
        self.next_btn.pack(side="left", padx=5)
    
    def _setup_bindings(self):
        """Ustaw bindingi klawiaturowe"""
        self.search_entry.bind("<Return>", lambda e: self._on_search())
        self.bind("<F5>", lambda e: self._refresh())
        self.bind("<Escape>", lambda e: self.destroy())
    
    # =========================================================
    # DATA LOADING
    # =========================================================
    
    def _initial_load(self):
        """Początkowe ładowanie danych"""
        # Załaduj filtry
        self._load_filter_options()
        
        # Załaduj produkty
        self._load_products()
    
    def _load_filter_options(self):
        """Załaduj opcje filtrów z bazy"""
        try:
            # Kategorie
            categories = self.service.products.get_unique_categories()
            self.category_combo.configure(values=["Wszystkie"] + categories)
            
            # Materiały
            materials = self.service.products.get_unique_materials()
            material_names = ["Wszystkie"] + [m['name'] for m in materials]
            self.material_combo.configure(values=material_names)
            
            # Materiały - mapowanie ID
            self._material_map = {m['name']: m['id'] for m in materials}
            
            # Grubości
            thicknesses = self.service.products.get_unique_thicknesses()
            thickness_strs = ["Wszystkie"] + [f"{t} mm" for t in thicknesses]
            self.thickness_combo.configure(values=thickness_strs)
            
        except Exception as e:
            print(f"[GUI] Błąd ładowania filtrów: {e}")
    
    def _load_products(self):
        """Załaduj produkty z filtrami"""
        if self.is_loading:
            return
        
        self.is_loading = True
        self.info_label.configure(text="Ładowanie...")
        
        # Uruchom w wątku
        thread = threading.Thread(target=self._load_products_thread, daemon=True)
        thread.start()
    
    def _load_products_thread(self):
        """Wątek ładujący produkty"""
        try:
            # Zbuduj filtry
            filters = {}
            
            category = self.category_var.get()
            if category and category != "Wszystkie":
                filters['category'] = category
            
            material = self.material_var.get()
            if material and material != "Wszystkie":
                material_id = self._material_map.get(material)
                if material_id:
                    filters['material_id'] = material_id
            
            thickness = self.thickness_var.get()
            if thickness and thickness != "Wszystkie":
                try:
                    filters['thickness_mm'] = float(thickness.replace(" mm", ""))
                except ValueError:
                    pass
            
            # Wyszukiwanie
            search = self.search_var.get().strip() or None
            
            # Pobierz produkty
            offset = self.current_page * PRODUCTS_PAGE_SIZE
            
            products = self.service.list_products(
                filters=filters if filters else None,
                search=search,
                limit=PRODUCTS_PAGE_SIZE,
                offset=offset,
                include_urls=True  # Potrzebne dla miniatur
            )
            
            # Policz wszystkie
            count = self.service.count_products(
                filters=filters if filters else None,
                search=search
            )
            
            # Aktualizuj w głównym wątku
            self.after(0, lambda: self._update_product_list(products, count))
            
        except Exception as e:
            self.after(0, lambda: self._show_error(f"Błąd ładowania: {e}"))
        finally:
            self.is_loading = False
    
    def _update_product_list(self, products: List[Dict], total: int):
        """Aktualizuj listę produktów w UI"""
        # Sprawdź czy okno i widget istnieją
        if not self.winfo_exists():
            return
        try:
            if not self.tree.winfo_exists():
                return
        except:
            return
        
        self.products = products
        self.total_count = total
        
        # Wyczyść TreeView
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Dodaj produkty
        for product in products:
            self._add_product_to_tree(product)
        
        # Aktualizuj info
        start = self.current_page * PRODUCTS_PAGE_SIZE + 1
        end = min(start + len(products) - 1, total)
        
        if total > 0:
            self.info_label.configure(text=f"Wyświetlono {start}-{end} z {total} produktów")
        else:
            self.info_label.configure(text="Brak produktów")
        
        # Aktualizuj paginację
        total_pages = (total + PRODUCTS_PAGE_SIZE - 1) // PRODUCTS_PAGE_SIZE
        current = self.current_page + 1
        self.page_label.configure(text=f"Strona {current}/{max(1, total_pages)}")
        
        self.prev_btn.configure(state="normal" if self.current_page > 0 else "disabled")
        self.next_btn.configure(state="normal" if end < total else "disabled")
    
    def _add_product_to_tree(self, product: Dict):
        """Dodaj produkt do TreeView"""
        product_id = product.get('id', '')
        
        # Wartości kolumn
        values = (
            product.get('idx_code', '-'),
            product.get('name', '-'),
            product.get('category', '-') or '-',
            self._get_material_name(product),
            f"{product.get('thickness_mm', '-')} mm" if product.get('thickness_mm') else '-',
            self._format_date(product.get('updated_at')),
        )
        
        # Sprawdź czy mamy cached thumbnail
        cached_photo = self.thumbnail_cache.get(product_id)
        
        if cached_photo:
            # Użyj cached thumbnail
            self.tree.insert("", "end", iid=product_id, values=values, 
                           tags=(product_id,), image=cached_photo)
        else:
            # Dodaj wiersz bez miniatury
            self.tree.insert("", "end", iid=product_id, values=values, tags=(product_id,))
            
            # Pobierz URL miniatury - z produktu lub wygeneruj
            thumbnail_url = product.get('thumbnail_100_url')
            if not thumbnail_url and product.get('thumbnail_100_path'):
                thumbnail_url = self.service.storage.get_signed_url(product['thumbnail_100_path'])
                if thumbnail_url:
                    product['thumbnail_100_url'] = thumbnail_url
            
            # Załaduj miniaturę asynchronicznie
            if thumbnail_url:
                self._load_thumbnail_async(product_id, thumbnail_url)
    
    def _get_material_name(self, product: Dict) -> str:
        """Pobierz nazwę materiału z produktu"""
        # Sprawdź zagnieżdżony obiekt materials_dict
        materials = product.get('materials_dict')
        if materials and isinstance(materials, dict):
            return materials.get('name', '-')
        return product.get('material_name', '-') or '-'
    
    def _format_date(self, date_str: str) -> str:
        """Formatuj datę do wyświetlenia"""
        if not date_str:
            return '-'
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%d.%m.%Y')
        except Exception:
            return date_str[:10] if len(date_str) >= 10 else date_str
    
    def _load_thumbnail_async(self, product_id: str, url: str):
        """Załaduj miniaturę asynchronicznie"""
        if product_id in self.thumbnail_cache:
            return
        
        def load():
            try:
                # Sprawdź czy widget istnieje
                if not self.winfo_exists():
                    return
                    
                import requests
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    image = Image.open(io.BytesIO(response.content))
                    image.thumbnail((40, 40), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    
                    # Sprawdź ponownie przed after()
                    if self.winfo_exists():
                        self.after(0, lambda pid=product_id, p=photo: self._set_thumbnail(pid, p))
            except Exception:
                pass  # Cichy błąd - miniatura nie jest krytyczna
        
        thread = threading.Thread(target=load, daemon=True)
        thread.start()
    
    def _set_thumbnail(self, product_id: str, photo: ImageTk.PhotoImage):
        """Ustaw miniaturę w TreeView"""
        if not self.winfo_exists():
            return
        self.thumbnail_cache[product_id] = photo  # Zachowaj referencję!
        try:
            if self.tree.exists(product_id):
                self.tree.item(product_id, image=photo)
        except Exception:
            pass
    
    # =========================================================
    # EVENT HANDLERS
    # =========================================================
    
    def _on_search(self):
        """Obsługa wyszukiwania"""
        self.current_page = 0
        self._load_products()
    
    def _on_filter_change(self, value=None):
        """Obsługa zmiany filtra"""
        self.current_page = 0
        self._load_products()
    
    def _reset_filters(self):
        """Reset wszystkich filtrów"""
        self.search_var.set("")
        self.category_var.set("Wszystkie")
        self.material_var.set("Wszystkie")
        self.thickness_var.set("Wszystkie")
        self.current_page = 0
        self._load_products()
    
    def _prev_page(self):
        """Poprzednia strona"""
        if self.current_page > 0:
            self.current_page -= 1
            self._load_products()
    
    def _next_page(self):
        """Następna strona"""
        max_page = (self.total_count - 1) // PRODUCTS_PAGE_SIZE
        if self.current_page < max_page:
            self.current_page += 1
            self._load_products()
    
    def _sort_by(self, column: str):
        """Sortuj po kolumnie (TODO: implementacja)"""
        print(f"[GUI] Sort by: {column}")
        # TODO: Implementacja sortowania
    
    def _on_product_select(self, event):
        """Obsługa wyboru produktu"""
        selection = self.tree.selection()
        if not selection:
            self._clear_preview()
            return
        
        product_id = selection[0]
        
        # Znajdź produkt w liście
        product = next((p for p in self.products if p.get('id') == product_id), None)
        
        if product:
            # Jeśli brak URL ale jest PATH, wygeneruj URL
            if not product.get('preview_800_url') and product.get('preview_800_path'):
                url = self.service.storage.get_signed_url(product['preview_800_path'])
                if url:
                    product['preview_800_url'] = url
            
            if not product.get('thumbnail_100_url') and product.get('thumbnail_100_path'):
                url = self.service.storage.get_signed_url(product['thumbnail_100_path'])
                if url:
                    product['thumbnail_100_url'] = url
            
            self.selected_product = product
            self._update_preview(product)
            
            # Włącz przyciski
            self.edit_btn.configure(state="normal")
            self.delete_btn.configure(state="normal")
            self.select_btn.configure(state="normal")
    
    def _on_product_double_click(self, event):
        """Obsługa podwójnego kliknięcia - edycja"""
        self._on_edit_product()
    
    def _update_preview(self, product: Dict):
        """Aktualizuj panel podglądu"""
        # Obraz
        preview_url = product.get('preview_800_url') or product.get('thumbnail_100_url')
        if preview_url:
            self._load_preview_image(preview_url)
        else:
            self.preview_image_label.configure(text="Brak podglądu", image=None)
        
        # Szczegóły
        self.detail_labels['idx_code'].configure(text=product.get('idx_code', '-'))
        self.detail_labels['name'].configure(text=product.get('name', '-'))
        self.detail_labels['category'].configure(text=product.get('category', '-') or '-')
        self.detail_labels['material_name'].configure(text=self._get_material_name(product))
        
        thickness = product.get('thickness_mm')
        self.detail_labels['thickness_mm'].configure(
            text=f"{thickness} mm" if thickness else '-'
        )
        
        # Wymiary
        dims = []
        if product.get('width_mm'):
            dims.append(f"S:{product['width_mm']}")
        if product.get('height_mm'):
            dims.append(f"W:{product['height_mm']}")
        if product.get('length_mm'):
            dims.append(f"D:{product['length_mm']}")
        self.detail_labels['dimensions'].configure(text=" × ".join(dims) if dims else '-')
        
        # Koszty
        total_cost = sum([
            float(product.get('material_cost', 0) or 0),
            float(product.get('laser_cost', 0) or 0),
            float(product.get('bending_cost', 0) or 0),
            float(product.get('additional_costs', 0) or 0),
        ])
        self.detail_labels['costs'].configure(
            text=f"{total_cost:.2f} PLN" if total_cost > 0 else '-'
        )
        
        # Daty
        self.detail_labels['created_at'].configure(
            text=self._format_date(product.get('created_at'))
        )
        self.detail_labels['updated_at'].configure(
            text=self._format_date(product.get('updated_at'))
        )
        
        # Pliki
        for file_type in ['cad_2d', 'cad_3d', 'user_image']:
            label_key = f"file_{file_type}"
            if label_key in self.detail_labels:
                path = product.get(f'{file_type}_path')
                filename = product.get(f'{file_type}_filename')
                
                if path or filename:
                    display = filename or path.split('/')[-1] if path else "—"
                    # Skróć nazwę jeśli za długa
                    if len(display) > 25:
                        display = display[:22] + "..."
                    self.detail_labels[label_key].configure(
                        text=f"✓ {display}", 
                        text_color="green"
                    )
                    # Pokaż przycisk pobierania
                    if file_type in self.download_buttons:
                        self.download_buttons[file_type].pack(side="right", padx=2)
                else:
                    self.detail_labels[label_key].configure(
                        text="—", 
                        text_color="gray60"
                    )
                    # Ukryj przycisk pobierania
                    if file_type in self.download_buttons:
                        self.download_buttons[file_type].pack_forget()
    
    def _load_preview_image(self, url: str):
        """Załaduj obraz podglądu"""
        # Sprawdź cache
        if url in self._preview_cache:
            cached_data = self._preview_cache[url]
            self._create_and_set_preview(cached_data)
            return
        
        def load():
            try:
                # Sprawdź czy widget istnieje
                if not self.winfo_exists():
                    return
                    
                import requests
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    # Zapisz do cache
                    self._preview_cache[url] = response.content
                    # Przekaż surowe dane do głównego wątku
                    self.after(0, lambda data=response.content: self._create_and_set_preview(data))
            except Exception as e:
                if self.winfo_exists():
                    print(f"[PREVIEW] ❌ Error loading preview: {e}")
        
        thread = threading.Thread(target=load, daemon=True)
        thread.start()
    
    def _create_and_set_preview(self, image_data: bytes):
        """Stwórz CTkImage w głównym wątku i ustaw podgląd"""
        try:
            # Sprawdź czy widget istnieje
            if not self.winfo_exists():
                return
            
            image = Image.open(io.BytesIO(image_data))
            
            # Skaluj zachowując proporcje
            max_size = 280
            ratio = min(max_size / image.width, max_size / image.height)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            
            # Twórz CTkImage w głównym wątku
            self._preview_photo = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=new_size
            )
            
            # Sprawdź ponownie przed ustawieniem
            if self.winfo_exists() and self.preview_image_label.winfo_exists():
                self.preview_image_label.configure(image=self._preview_photo, text="")
        except Exception as e:
            if "doesn't exist" not in str(e):
                print(f"[PREVIEW] ❌ Error creating image: {e}")
    
    def _clear_preview(self):
        """Wyczyść panel podglądu"""
        self.selected_product = None
        self.preview_image_label.configure(text="Wybierz produkt", image=None)
        
        for key, label in self.detail_labels.items():
            if key.startswith('file_'):
                label.configure(text="—", text_color="gray60")
            else:
                label.configure(text="-")
        
        # Ukryj przyciski pobierania
        for btn in self.download_buttons.values():
            btn.pack_forget()
        
        self.edit_btn.configure(state="disabled")
        self.delete_btn.configure(state="disabled")
        self.select_btn.configure(state="disabled")
    
    # =========================================================
    # ACTIONS
    # =========================================================
    
    def _on_add_product(self):
        """Dodaj nowy produkt"""
        from products.gui.product_edit_dialog import ProductEditDialog
        
        dialog = ProductEditDialog(self, service=self.service)
        self.wait_window(dialog)
        
        if dialog.result:
            self._refresh()
    
    def _on_edit_product(self):
        """Edytuj wybrany produkt"""
        if not self.selected_product:
            return
        
        from products.gui.product_edit_dialog import ProductEditDialog
        
        dialog = ProductEditDialog(
            self, 
            service=self.service,
            product=self.selected_product
        )
        self.wait_window(dialog)
        
        if dialog.result:
            self._refresh()
    
    def _on_delete_product(self):
        """Usuń wybrany produkt"""
        if not self.selected_product:
            return
        
        name = self.selected_product.get('name', 'Produkt')
        
        if messagebox.askyesno(
            "Potwierdź usunięcie",
            f"Czy na pewno chcesz usunąć produkt:\n\n{name}?"
        ):
            product_id = self.selected_product['id']
            success, message = self.service.delete_product(product_id, hard=False)
            
            if success:
                messagebox.showinfo("Sukces", "Produkt został usunięty")
                self._refresh()
            else:
                messagebox.showerror("Błąd", f"Nie udało się usunąć produktu:\n{message}")
    
    def _on_select_product(self):
        """Wybierz produkt (callback)"""
        if self.selected_product and self.on_product_selected:
            self.on_product_selected(self.selected_product)
            self.destroy()
    
    def _download_file(self, file_type: str):
        """Pobierz plik i zapisz z oryginalną nazwą"""
        if not self.selected_product:
            return
        
        product_id = self.selected_product.get('id')
        original_filename = self.selected_product.get(f'{file_type}_filename')
        
        if not original_filename:
            # Fallback - użyj nazwy ze ścieżki
            path = self.selected_product.get(f'{file_type}_path')
            if path:
                original_filename = path.split('/')[-1]
            else:
                messagebox.showerror("Błąd", "Brak pliku do pobrania")
                return
        
        # Dialog wyboru miejsca zapisu
        from tkinter import filedialog
        
        # Rozszerzenie z oryginalnej nazwy
        ext = Path(original_filename).suffix
        
        save_path = filedialog.asksaveasfilename(
            initialfile=original_filename,
            defaultextension=ext,
            filetypes=[
                (f"Plik {ext.upper()}", f"*{ext}"),
                ("Wszystkie pliki", "*.*")
            ]
        )
        
        if not save_path:
            return  # Anulowano
        
        # Pobierz plik
        self.info_label.configure(text=f"Pobieranie {original_filename}...")
        
        def download_thread():
            try:
                success, data, filename = self.service.download_file(product_id, file_type)
                
                if success and data:
                    with open(save_path, 'wb') as f:
                        f.write(data)
                    self.after(0, lambda: self._download_complete(save_path))
                else:
                    error_msg = data if isinstance(data, str) else "Nie udało się pobrać pliku"
                    self.after(0, lambda: self._download_error(error_msg))
                    
            except Exception as e:
                self.after(0, lambda: self._download_error(str(e)))
        
        import threading
        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()
    
    def _download_complete(self, save_path: str):
        """Zakończono pobieranie"""
        if not self.winfo_exists():
            return
        filename = Path(save_path).name
        try:
            self.info_label.configure(text=f"✅ Zapisano: {filename}")
        except:
            pass
        messagebox.showinfo("Sukces", f"Plik zapisany:\n{save_path}")
    
    def _download_error(self, error: str):
        """Błąd pobierania"""
        if not self.winfo_exists():
            return
        try:
            self.info_label.configure(text=f"❌ Błąd pobierania")
        except:
            pass
        messagebox.showerror("Błąd", f"Nie udało się pobrać pliku:\n{error}")
    
    def _refresh(self):
        """Odśwież listę produktów"""
        self._clear_preview()
        self._load_products()
    
    def _show_error(self, message: str):
        """Pokaż komunikat błędu"""
        if not self.winfo_exists():
            return
        try:
            self.info_label.configure(text=f"❌ {message}")
        except:
            pass
        messagebox.showerror("Błąd", message)


# =========================================================
# STANDALONE TEST
# =========================================================

if __name__ == "__main__":
    ctk.set_appearance_mode(CTK_APPEARANCE_MODE)
    ctk.set_default_color_theme(CTK_COLOR_THEME)
    
    # Test jako samodzielne okno
    root = ctk.CTk()
    root.withdraw()  # Ukryj główne okno
    
    window = ProductsWindow()
    window.mainloop()
