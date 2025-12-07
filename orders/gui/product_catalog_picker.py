"""
ProductCatalogPicker - Okno wyboru produktów z katalogu
=======================================================

Pozwala wyszukać i wybrać produkty z bazy products_catalog
do dodania do zamówienia.
"""

import logging
from typing import Callable, List, Dict, Optional
import customtkinter as ctk
from tkinter import ttk

logger = logging.getLogger(__name__)


class Theme:
    """Kolory motywu"""
    BG_DARK = "#1a1a2e"
    BG_CARD = "#252540"
    BG_INPUT = "#2d2d4a"
    TEXT_PRIMARY = "#e0e0e0"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#707090"
    ACCENT_PRIMARY = "#9b4dff"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_INFO = "#06b6d4"


class ProductCatalogPicker(ctk.CTkToplevel):
    """
    Okno dialogowe do wyboru produktów z katalogu.

    Funkcjonalności:
    - Wyszukiwanie po nazwie, materiale, grubości
    - Lista produktów z checkbox
    - Wybór wielu produktów jednocześnie
    - Callback z listą wybranych ID
    """

    def __init__(self, parent, on_select_callback: Callable[[List[str]], None] = None):
        super().__init__(parent)

        self.on_select_callback = on_select_callback
        self.products: List[Dict] = []
        self.selected_ids: List[str] = []
        self.check_vars: Dict[str, ctk.BooleanVar] = {}

        self.title("Wybierz produkty z katalogu")
        self.geometry("900x600")
        self.transient(parent)
        self.grab_set()

        self._create_ui()
        self._load_products()

        # Pozycjonuj na środku
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_ui(self):
        """Utwórz interfejs użytkownika"""
        # Header z wyszukiwarką
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        header.pack(fill="x", padx=10, pady=(10, 5))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="Wyszukaj produkty:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=10, pady=10)

        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            header, textvariable=self.search_var,
            placeholder_text="Nazwa, materiał...",
            width=250
        )
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<Return>", lambda e: self._search())

        ctk.CTkButton(
            header, text="Szukaj", width=80,
            command=self._search
        ).pack(side="left", padx=5)

        # Filtr grubości
        ctk.CTkLabel(header, text="Grubość:").pack(side="left", padx=(20, 5))
        self.thickness_var = ctk.StringVar(value="Wszystkie")
        self.thickness_combo = ctk.CTkComboBox(
            header,
            values=["Wszystkie", "1", "1.5", "2", "3", "4", "5", "6", "8", "10", "12", "15", "20"],
            variable=self.thickness_var,
            width=100,
            command=lambda _: self._search()
        )
        self.thickness_combo.pack(side="left", padx=5)

        ctk.CTkButton(
            header, text="Odśwież", width=80,
            fg_color=Theme.ACCENT_INFO,
            command=self._load_products
        ).pack(side="right", padx=10)

        # Tabela produktów
        table_frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Style dla Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "CatalogPicker.Treeview",
            background=Theme.BG_DARK,
            foreground=Theme.TEXT_PRIMARY,
            fieldbackground=Theme.BG_DARK,
            rowheight=28
        )
        style.configure(
            "CatalogPicker.Treeview.Heading",
            background=Theme.BG_INPUT,
            foreground=Theme.TEXT_PRIMARY
        )

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        # Treeview
        columns = ("select", "name", "material", "thickness", "weight", "cutting", "bends")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            style="CatalogPicker.Treeview",
            yscrollcommand=scrollbar.set,
            selectmode="extended"
        )
        scrollbar.config(command=self.tree.yview)

        # Konfiguracja kolumn
        self.tree.heading("select", text="✓")
        self.tree.heading("name", text="Nazwa")
        self.tree.heading("material", text="Materiał")
        self.tree.heading("thickness", text="Grubość")
        self.tree.heading("weight", text="Waga [kg]")
        self.tree.heading("cutting", text="Cięcie [mm]")
        self.tree.heading("bends", text="Gięcia")

        self.tree.column("select", width=40, anchor="center")
        self.tree.column("name", width=250)
        self.tree.column("material", width=100)
        self.tree.column("thickness", width=80, anchor="center")
        self.tree.column("weight", width=80, anchor="center")
        self.tree.column("cutting", width=100, anchor="center")
        self.tree.column("bends", width=60, anchor="center")

        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # Obsługa kliknięcia - toggle selection
        self.tree.bind("<ButtonRelease-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double_click)

        # Footer z przyciskami
        footer = ctk.CTkFrame(self, fg_color="transparent", height=50)
        footer.pack(fill="x", padx=10, pady=10)
        footer.pack_propagate(False)

        self.lbl_selected = ctk.CTkLabel(
            footer, text="Wybrano: 0 produktów",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_selected.pack(side="left", padx=10)

        ctk.CTkButton(
            footer, text="Anuluj", width=100,
            fg_color=Theme.BG_INPUT,
            command=self.destroy
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            footer, text="Dodaj wybrane", width=120,
            fg_color=Theme.ACCENT_SUCCESS,
            command=self._add_selected
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            footer, text="Zaznacz wszystkie", width=120,
            fg_color=Theme.ACCENT_INFO,
            command=self._select_all
        ).pack(side="right", padx=5)

    def _load_products(self):
        """Załaduj produkty z bazy"""
        try:
            from core.supabase_client import get_supabase_client
            from products.repository import ProductRepository

            client = get_supabase_client()
            repo = ProductRepository(client)

            # Pobierz produkty z filtrami
            search = self.search_var.get().strip() if hasattr(self, 'search_var') else None
            thickness = self.thickness_var.get() if hasattr(self, 'thickness_var') else None

            filters = {}
            if thickness and thickness != "Wszystkie":
                filters['thickness_mm'] = float(thickness)

            self.products = repo.list(
                filters=filters,
                search=search if search else None,
                limit=200,
                order_by="name",
                ascending=True
            )

            self._refresh_table()
            logger.info(f"[CatalogPicker] Loaded {len(self.products)} products")

        except Exception as e:
            logger.error(f"[CatalogPicker] Error loading products: {e}")
            self.products = []
            self._refresh_table()

    def _search(self):
        """Wyszukaj produkty"""
        self._load_products()

    def _refresh_table(self):
        """Odśwież tabelę produktów"""
        # Wyczyść tabelę
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.check_vars.clear()

        # Dodaj produkty
        for product in self.products:
            product_id = product.get('id', '')

            # Nazwa materiału
            material_name = '?'
            if product.get('materials_dict'):
                material_name = product['materials_dict'].get('name', '?')

            # Sprawdź czy był zaznaczony
            is_selected = product_id in self.selected_ids
            check_mark = "☑" if is_selected else "☐"

            values = (
                check_mark,
                product.get('name', ''),
                material_name,
                f"{product.get('thickness_mm', 0):.1f}",
                f"{product.get('weight_kg', 0):.2f}" if product.get('weight_kg') else "-",
                f"{product.get('cutting_length_mm', 0):.0f}" if product.get('cutting_length_mm') else "-",
                product.get('bends_count', '-')
            )

            item_id = self.tree.insert("", "end", values=values, tags=(product_id,))

            # Zapisz mapowanie
            self.check_vars[item_id] = product_id

        self._update_selected_count()

    def _on_click(self, event):
        """Obsłuż kliknięcie w wiersz"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item:
            return

        # Toggle zaznaczenia
        product_id = self.check_vars.get(item)
        if product_id:
            if product_id in self.selected_ids:
                self.selected_ids.remove(product_id)
            else:
                self.selected_ids.append(product_id)

            # Aktualizuj checkbox w tabeli
            current_values = list(self.tree.item(item, "values"))
            current_values[0] = "☑" if product_id in self.selected_ids else "☐"
            self.tree.item(item, values=current_values)

            self._update_selected_count()

    def _on_double_click(self, event):
        """Obsłuż podwójne kliknięcie - dodaj i zamknij"""
        item = self.tree.identify_row(event.y)
        if not item:
            return

        product_id = self.check_vars.get(item)
        if product_id and product_id not in self.selected_ids:
            self.selected_ids.append(product_id)

        self._add_selected()

    def _select_all(self):
        """Zaznacz wszystkie produkty"""
        self.selected_ids = [p['id'] for p in self.products if p.get('id')]
        self._refresh_table()

    def _update_selected_count(self):
        """Aktualizuj licznik zaznaczonych"""
        count = len(self.selected_ids)
        self.lbl_selected.configure(text=f"Wybrano: {count} produktów")

    def _add_selected(self):
        """Dodaj wybrane produkty"""
        if not self.selected_ids:
            return

        if self.on_select_callback:
            self.on_select_callback(self.selected_ids.copy())

        self.destroy()


# === TEST ===
if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")

    root = ctk.CTk()
    root.title("Test ProductCatalogPicker")
    root.geometry("400x200")

    def on_select(ids):
        print(f"Selected: {ids}")

    def open_picker():
        ProductCatalogPicker(root, on_select_callback=on_select)

    ctk.CTkButton(root, text="Open Picker", command=open_picker).pack(pady=50)

    root.mainloop()
