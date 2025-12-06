"""
NewERP - Customers Window
=========================
Główne okno listy klientów z filtrowaniem i wyszukiwaniem.
"""

import customtkinter as ctk
from tkinter import ttk, Menu, messagebox
from typing import Dict, List, Optional, Any
import threading
import logging

from customers.service import CustomerService
from customers.gui.customer_edit_dialog import CustomerEditDialog
from core.filters import QueryParams, Filter, FilterOperator, Sort

logger = logging.getLogger(__name__)


class CustomersWindow(ctk.CTkToplevel):
    """
    Okno zarządzania klientami.
    
    Funkcje:
    - Lista klientów z miniaturą danych
    - Filtrowanie po mieście, kategorii, statusie
    - Wyszukiwanie pełnotekstowe
    - Dodawanie, edycja, usuwanie klientów
    - Blokowanie/odblokowywanie
    - Podgląd szczegółów
    """
    
    def __init__(self, parent, service: CustomerService):
        super().__init__(parent)
        
        self.service = service
        self.customers: List[Dict] = []
        self.selected_customer: Optional[Dict] = None
        
        # Konfiguracja okna
        self.title("Klienci - NewERP")
        self.geometry("1400x800")
        self.minsize(1000, 600)
        
        # Wyśrodkowanie
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 1400) // 2
        y = (self.winfo_screenheight() - 800) // 2
        self.geometry(f"+{x}+{y}")
        
        # Setup
        self._setup_ui()
        self._setup_bindings()
        
        # Załaduj dane
        self.after(100, self._load_customers)
    
    # ============================================================
    # UI Setup
    # ============================================================
    
    def _setup_ui(self):
        """Buduj interfejs użytkownika"""
        
        # Main frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Grid layout
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        
        # === LEFT PANEL: Filters ===
        self._setup_filters_panel(main_frame)
        
        # === TOP: Toolbar ===
        self._setup_toolbar(main_frame)
        
        # === CENTER: Customer list ===
        self._setup_customer_list(main_frame)
        
        # === RIGHT PANEL: Details ===
        self._setup_details_panel(main_frame)
        
        # === BOTTOM: Status bar ===
        self._setup_statusbar(main_frame)
    
    def _setup_filters_panel(self, parent):
        """Panel filtrów po lewej stronie"""
        filters_frame = ctk.CTkFrame(parent, width=220)
        filters_frame.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, 10))
        filters_frame.grid_propagate(False)
        
        # Tytuł
        title_label = ctk.CTkLabel(
            filters_frame, 
            text="🔍 Filtry", 
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(15, 10), padx=10)
        
        # === Wyszukiwanie ===
        search_label = ctk.CTkLabel(filters_frame, text="Szukaj:")
        search_label.pack(pady=(10, 5), padx=10, anchor="w")
        
        self.search_entry = ctk.CTkEntry(
            filters_frame, 
            placeholder_text="Nazwa, kod, NIP..."
        )
        self.search_entry.pack(pady=(0, 10), padx=10, fill="x")
        self.search_entry.bind('<KeyRelease>', self._on_search)
        
        # === Miasto ===
        city_label = ctk.CTkLabel(filters_frame, text="Miasto:")
        city_label.pack(pady=(10, 5), padx=10, anchor="w")
        
        self.city_var = ctk.StringVar(value="Wszystkie")
        self.city_combo = ctk.CTkComboBox(
            filters_frame,
            values=["Wszystkie"],
            variable=self.city_var,
            command=self._on_filter_change
        )
        self.city_combo.pack(pady=(0, 10), padx=10, fill="x")
        
        # === Kategoria ===
        category_label = ctk.CTkLabel(filters_frame, text="Kategoria:")
        category_label.pack(pady=(10, 5), padx=10, anchor="w")
        
        self.category_var = ctk.StringVar(value="Wszystkie")
        self.category_combo = ctk.CTkComboBox(
            filters_frame,
            values=["Wszystkie"],
            variable=self.category_var,
            command=self._on_filter_change
        )
        self.category_combo.pack(pady=(0, 10), padx=10, fill="x")
        
        # === Typ ===
        type_label = ctk.CTkLabel(filters_frame, text="Typ:")
        type_label.pack(pady=(10, 5), padx=10, anchor="w")
        
        self.type_var = ctk.StringVar(value="Wszystkie")
        self.type_combo = ctk.CTkComboBox(
            filters_frame,
            values=["Wszystkie", "Firma", "Osoba fizyczna"],
            variable=self.type_var,
            command=self._on_filter_change
        )
        self.type_combo.pack(pady=(0, 10), padx=10, fill="x")
        
        # === Status ===
        status_label = ctk.CTkLabel(filters_frame, text="Status:")
        status_label.pack(pady=(10, 5), padx=10, anchor="w")
        
        self.status_var = ctk.StringVar(value="Aktywni")
        self.status_combo = ctk.CTkComboBox(
            filters_frame,
            values=["Aktywni", "Zablokowani", "Usunięci", "Wszyscy"],
            variable=self.status_var,
            command=self._on_filter_change
        )
        self.status_combo.pack(pady=(0, 10), padx=10, fill="x")
        
        # === Przyciski filtrów ===
        btn_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        btn_frame.pack(pady=20, padx=10, fill="x")
        
        reset_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 Reset filtrów",
            command=self._reset_filters,
            width=180,
            height=32
        )
        reset_btn.pack()
        
        # === Statystyki ===
        stats_frame = ctk.CTkFrame(filters_frame)
        stats_frame.pack(pady=20, padx=10, fill="x")
        
        stats_title = ctk.CTkLabel(
            stats_frame, 
            text="📊 Statystyki",
            font=ctk.CTkFont(weight="bold")
        )
        stats_title.pack(pady=(10, 5))
        
        self.stats_label = ctk.CTkLabel(
            stats_frame,
            text="Ładowanie...",
            font=ctk.CTkFont(size=12)
        )
        self.stats_label.pack(pady=(5, 10))
    
    def _setup_toolbar(self, parent):
        """Pasek narzędzi"""
        toolbar = ctk.CTkFrame(parent, height=50)
        toolbar.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Przyciski
        add_btn = ctk.CTkButton(
            toolbar,
            text="➕ Dodaj klienta",
            command=self._add_customer,
            width=140,
            height=35
        )
        add_btn.pack(side="left", padx=5, pady=8)
        
        edit_btn = ctk.CTkButton(
            toolbar,
            text="✏️ Edytuj",
            command=self._edit_customer,
            width=100,
            height=35
        )
        edit_btn.pack(side="left", padx=5, pady=8)
        
        delete_btn = ctk.CTkButton(
            toolbar,
            text="🗑️ Usuń",
            command=self._delete_customer,
            width=100,
            height=35,
            fg_color="#dc3545",
            hover_color="#c82333"
        )
        delete_btn.pack(side="left", padx=5, pady=8)
        
        # Separator
        sep = ctk.CTkFrame(toolbar, width=2, height=30)
        sep.pack(side="left", padx=15, pady=10)
        
        block_btn = ctk.CTkButton(
            toolbar,
            text="🚫 Zablokuj",
            command=self._block_customer,
            width=110,
            height=35,
            fg_color="#ffc107",
            hover_color="#e0a800",
            text_color="black"
        )
        block_btn.pack(side="left", padx=5, pady=8)
        
        unblock_btn = ctk.CTkButton(
            toolbar,
            text="✅ Odblokuj",
            command=self._unblock_customer,
            width=110,
            height=35
        )
        unblock_btn.pack(side="left", padx=5, pady=8)
        
        # Refresh po prawej
        refresh_btn = ctk.CTkButton(
            toolbar,
            text="🔄 Odśwież",
            command=self._load_customers,
            width=100,
            height=35
        )
        refresh_btn.pack(side="right", padx=5, pady=8)
    
    def _setup_customer_list(self, parent):
        """Lista klientów (Treeview)"""
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=1, column=1, sticky="nsew")
        
        # Kolumny
        columns = ('code', 'name', 'city', 'nip', 'phone', 'orders', 'revenue')
        
        self.tree = ttk.Treeview(
            list_frame, 
            columns=columns, 
            show='headings',
            selectmode='browse'
        )
        
        # Nagłówki
        self.tree.heading('code', text='Kod', anchor='w')
        self.tree.heading('name', text='Nazwa', anchor='w')
        self.tree.heading('city', text='Miasto', anchor='w')
        self.tree.heading('nip', text='NIP', anchor='w')
        self.tree.heading('phone', text='Telefon', anchor='w')
        self.tree.heading('orders', text='Zamówienia', anchor='center')
        self.tree.heading('revenue', text='Obroty', anchor='e')
        
        # Szerokości kolumn
        self.tree.column('code', width=100, minwidth=80)
        self.tree.column('name', width=250, minwidth=150)
        self.tree.column('city', width=120, minwidth=80)
        self.tree.column('nip', width=120, minwidth=100)
        self.tree.column('phone', width=130, minwidth=100)
        self.tree.column('orders', width=90, minwidth=70)
        self.tree.column('revenue', width=120, minwidth=100)
        
        # Style
        self.tree.tag_configure('blocked', background='#ffcccc')
        self.tree.tag_configure('vip', background='#ffffcc')
        self.tree.tag_configure('odd', background='#f5f5f5')
        self.tree.tag_configure('even', background='white')
        
        # Scrollbary
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid
        self.tree.grid(column=0, row=0, sticky='nsew')
        vsb.grid(column=1, row=0, sticky='ns')
        hsb.grid(column=0, row=1, sticky='ew')
        
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # Context menu
        self._setup_context_menu()
    
    def _setup_details_panel(self, parent):
        """Panel szczegółów po prawej stronie"""
        details_frame = ctk.CTkFrame(parent, width=300)
        details_frame.grid(row=1, column=2, sticky="nsew", padx=(10, 0))
        details_frame.grid_propagate(False)
        
        # Tytuł
        title_label = ctk.CTkLabel(
            details_frame, 
            text="📋 Szczegóły", 
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(15, 10), padx=10)
        
        # Scrollable frame dla szczegółów
        self.details_scroll = ctk.CTkScrollableFrame(details_frame)
        self.details_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Placeholder
        self.details_placeholder = ctk.CTkLabel(
            self.details_scroll,
            text="Wybierz klienta\naby zobaczyć szczegóły",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.details_placeholder.pack(pady=50)
        
        # Kontener na szczegóły (ukryty na start)
        self.details_content = ctk.CTkFrame(self.details_scroll, fg_color="transparent")
    
    def _setup_statusbar(self, parent):
        """Pasek statusu na dole"""
        statusbar = ctk.CTkFrame(parent, height=30)
        statusbar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        
        self.status_label = ctk.CTkLabel(
            statusbar,
            text="Gotowy",
            font=ctk.CTkFont(size=11)
        )
        self.status_label.pack(side="left", padx=10)
        
        self.count_label = ctk.CTkLabel(
            statusbar,
            text="0 klientów",
            font=ctk.CTkFont(size=11)
        )
        self.count_label.pack(side="right", padx=10)
    
    def _setup_context_menu(self):
        """Menu kontekstowe (prawy klik)"""
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(label="✏️ Edytuj", command=self._edit_customer)
        self.context_menu.add_command(label="📋 Duplikuj", command=self._duplicate_customer)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📧 Wyślij email", command=self._send_email)
        self.context_menu.add_command(label="📞 Zadzwoń", command=self._call_customer)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📜 Historia zmian", command=self._show_history)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️ Usuń", command=self._delete_customer)
    
    def _setup_bindings(self):
        """Ustaw bindowania zdarzeń"""
        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        self.tree.bind('<Double-Button-1>', lambda e: self._edit_customer())
        self.tree.bind('<Button-3>', self._show_context_menu)
        self.tree.bind('<Return>', lambda e: self._edit_customer())
        self.tree.bind('<Delete>', lambda e: self._delete_customer())
        
        # Skróty klawiszowe
        self.bind('<Control-n>', lambda e: self._add_customer())
        self.bind('<Control-f>', lambda e: self.search_entry.focus())
        self.bind('<F5>', lambda e: self._load_customers())
        self.bind('<Escape>', lambda e: self.destroy())
    
    # ============================================================
    # Data Loading
    # ============================================================
    
    def _load_customers(self):
        """Załaduj klientów z filtrowaniem"""
        self._set_status("Ładowanie...")
        
        def load():
            try:
                params = self._build_query_params()
                customers, total = self.service.list(params)
                
                # Aktualizuj filtr miast i kategorii
                self._update_filter_options(customers)
                
                self.after(0, lambda: self._display_customers(customers, total))
                self.after(0, self._load_statistics)
                
            except Exception as e:
                logger.error(f"[CustomersWindow] Load failed: {e}")
                self.after(0, lambda: self._set_status(f"Błąd: {e}"))
        
        threading.Thread(target=load, daemon=True).start()
    
    def _build_query_params(self) -> QueryParams:
        """Zbuduj parametry zapytania z filtrów"""
        params = QueryParams()
        
        # Wyszukiwanie
        search = self.search_entry.get().strip()
        if search:
            params.search = search
            params.search_fields = ["name", "short_name", "code", "nip", "email"]
        
        # Filtr miasta
        city = self.city_var.get()
        if city != "Wszystkie":
            params.filters.append(Filter("address_city", FilterOperator.EQ, city))
        
        # Filtr kategorii
        category = self.category_var.get()
        if category != "Wszystkie":
            params.filters.append(Filter("category", FilterOperator.EQ, category))
        
        # Filtr typu
        type_val = self.type_var.get()
        if type_val == "Firma":
            params.filters.append(Filter("type", FilterOperator.EQ, "company"))
        elif type_val == "Osoba fizyczna":
            params.filters.append(Filter("type", FilterOperator.EQ, "individual"))
        
        # Filtr statusu
        status = self.status_var.get()
        if status == "Aktywni":
            params.filters.append(Filter("is_blocked", FilterOperator.EQ, False))
            params.include_deleted = False
        elif status == "Zablokowani":
            params.filters.append(Filter("is_blocked", FilterOperator.EQ, True))
        elif status == "Usunięci":
            params.include_deleted = True
            params.filters.append(Filter("is_active", FilterOperator.EQ, False))
        else:  # Wszyscy
            params.include_deleted = True
        
        # Sortowanie
        params.sorts.append(Sort("name"))
        
        # Limit
        params.pagination.limit = 500
        
        return params
    
    def _display_customers(self, customers: List[Dict], total: int):
        """Wyświetl klientów w tabeli"""
        # Sprawdź czy okno i widget istnieją
        if not self.winfo_exists():
            return
        try:
            if not self.tree.winfo_exists():
                return
        except:
            return
        
        # Wyczyść tabelę
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.customers = customers
        
        # Dodaj wiersze
        for idx, customer in enumerate(customers):
            # Formatowanie
            revenue = customer.get('total_revenue') or 0
            revenue_str = f"{revenue:,.2f} PLN"
            orders = customer.get('total_orders') or 0
            
            # Tag (styl wiersza)
            tags = []
            if customer.get('is_blocked'):
                tags.append('blocked')
            elif customer.get('price_list') == 'vip':
                tags.append('vip')
            else:
                tags.append('odd' if idx % 2 else 'even')
            
            self.tree.insert('', 'end',
                iid=customer['id'],
                values=(
                    customer.get('code', ''),
                    customer.get('name', ''),
                    customer.get('address_city', ''),
                    customer.get('nip', ''),
                    customer.get('phone', ''),
                    orders,
                    revenue_str
                ),
                tags=tags
            )
        
        # Aktualizuj status
        self.count_label.configure(text=f"{len(customers)} klientów")
        self._set_status("Gotowy")
    
    def _update_filter_options(self, customers: List[Dict]):
        """Aktualizuj opcje filtrów na podstawie danych"""
        cities = set()
        categories = set()
        
        for c in customers:
            if c.get('address_city'):
                cities.add(c['address_city'])
            if c.get('category'):
                categories.add(c['category'])
        
        self.city_combo.configure(values=["Wszystkie"] + sorted(cities))
        self.category_combo.configure(values=["Wszystkie"] + sorted(categories))
    
    def _load_statistics(self):
        """Załaduj statystyki"""
        if not self.winfo_exists():
            return
        try:
            stats = self.service.get_statistics()
            
            text = (
                f"Aktywnych: {stats.get('total_active', 0)}\n"
                f"Firm: {stats.get('companies', 0)}\n"
                f"Osób: {stats.get('individuals', 0)}\n"
                f"Zablokowanych: {stats.get('blocked', 0)}"
            )
            
            if self.winfo_exists():
                self.stats_label.configure(text=text)
            
        except Exception as e:
            logger.error(f"[CustomersWindow] Load stats failed: {e}")
    
    # ============================================================
    # Event Handlers
    # ============================================================
    
    def _on_select(self, event):
        """Obsługa wyboru klienta"""
        selection = self.tree.selection()
        if not selection:
            self.selected_customer = None
            self._show_details_placeholder()
            return
        
        customer_id = selection[0]
        
        # Znajdź klienta w liście
        for c in self.customers:
            if c['id'] == customer_id:
                self.selected_customer = c
                self._show_customer_details(c)
                break
    
    def _on_search(self, event):
        """Obsługa wyszukiwania (debounced)"""
        # Anuluj poprzedni timer
        if hasattr(self, '_search_timer'):
            self.after_cancel(self._search_timer)
        
        # Ustaw nowy timer (300ms debounce)
        self._search_timer = self.after(300, self._load_customers)
    
    def _on_filter_change(self, value=None):
        """Obsługa zmiany filtra"""
        self._load_customers()
    
    def _reset_filters(self):
        """Resetuj filtry do domyślnych"""
        self.search_entry.delete(0, 'end')
        self.city_var.set("Wszystkie")
        self.category_var.set("Wszystkie")
        self.type_var.set("Wszystkie")
        self.status_var.set("Aktywni")
        self._load_customers()
    
    def _show_context_menu(self, event):
        """Pokaż menu kontekstowe"""
        item = self.tree.identify('item', event.x, event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    # ============================================================
    # Details Panel
    # ============================================================
    
    def _show_details_placeholder(self):
        """Pokaż placeholder w panelu szczegółów"""
        self.details_content.pack_forget()
        self.details_placeholder.pack(pady=50)
    
    def _show_customer_details(self, customer: Dict):
        """Pokaż szczegóły klienta"""
        self.details_placeholder.pack_forget()
        
        # Wyczyść poprzednie szczegóły
        for widget in self.details_content.winfo_children():
            widget.destroy()
        
        self.details_content.pack(fill="both", expand=True)
        
        # Nazwa i kod
        name_label = ctk.CTkLabel(
            self.details_content,
            text=customer.get('name', ''),
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=260
        )
        name_label.pack(pady=(10, 5), anchor="w")
        
        code_label = ctk.CTkLabel(
            self.details_content,
            text=f"Kod: {customer.get('code', '')}",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        code_label.pack(anchor="w")
        
        # Status
        if customer.get('is_blocked'):
            status_label = ctk.CTkLabel(
                self.details_content,
                text="🚫 ZABLOKOWANY",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="red"
            )
            status_label.pack(pady=(5, 0), anchor="w")
        
        # Separator
        sep = ctk.CTkFrame(self.details_content, height=2)
        sep.pack(fill="x", pady=15)
        
        # Dane kontaktowe
        self._add_detail_section(self.details_content, "📧 Kontakt")
        self._add_detail_row(self.details_content, "Email:", customer.get('email', '-'))
        self._add_detail_row(self.details_content, "Telefon:", customer.get('phone', '-'))
        
        # Adres
        self._add_detail_section(self.details_content, "📍 Adres")
        address_parts = [
            customer.get('address_street', ''),
            customer.get('address_building', ''),
        ]
        if customer.get('address_apartment'):
            address_parts.append(f"/{customer['address_apartment']}")
        address_line1 = ' '.join(filter(None, address_parts))
        address_line2 = f"{customer.get('address_postal_code', '')} {customer.get('address_city', '')}"
        
        self._add_detail_row(self.details_content, "", address_line1 or '-')
        self._add_detail_row(self.details_content, "", address_line2.strip() or '-')
        
        # Dane firmowe
        if customer.get('nip'):
            self._add_detail_section(self.details_content, "🏢 Dane firmy")
            self._add_detail_row(self.details_content, "NIP:", customer.get('nip', '-'))
            if customer.get('regon'):
                self._add_detail_row(self.details_content, "REGON:", customer.get('regon'))
        
        # Warunki handlowe
        self._add_detail_section(self.details_content, "💰 Warunki")
        self._add_detail_row(
            self.details_content, 
            "Płatność:", 
            f"{customer.get('payment_days', 14)} dni"
        )
        if customer.get('discount_percent'):
            self._add_detail_row(
                self.details_content, 
                "Rabat:", 
                f"{customer['discount_percent']:.1f}%"
            )
        if customer.get('credit_limit'):
            self._add_detail_row(
                self.details_content, 
                "Limit:", 
                f"{customer['credit_limit']:,.2f} PLN"
            )
        
        # Statystyki
        self._add_detail_section(self.details_content, "📊 Statystyki")
        self._add_detail_row(
            self.details_content, 
            "Zamówienia:", 
            str(customer.get('total_orders', 0))
        )
        self._add_detail_row(
            self.details_content, 
            "Obroty:", 
            f"{customer.get('total_revenue', 0):,.2f} PLN"
        )
        if customer.get('last_order_date'):
            self._add_detail_row(
                self.details_content, 
                "Ostatnie:", 
                customer['last_order_date'][:10]
            )
    
    def _add_detail_section(self, parent, title: str):
        """Dodaj sekcję w szczegółach"""
        label = ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        label.pack(pady=(15, 5), anchor="w")
    
    def _add_detail_row(self, parent, label: str, value: str):
        """Dodaj wiersz w szczegółach"""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        
        if label:
            lbl = ctk.CTkLabel(row, text=label, width=80, anchor="w", text_color="gray")
            lbl.pack(side="left")
        
        val = ctk.CTkLabel(row, text=value, anchor="w", wraplength=180)
        val.pack(side="left", fill="x", expand=True)
    
    # ============================================================
    # Actions
    # ============================================================
    
    def _add_customer(self):
        """Dodaj nowego klienta"""
        dialog = CustomerEditDialog(self, self.service)
        self.wait_window(dialog)
        
        if dialog.result:
            self._load_customers()
            # Zaznacz nowego klienta
            self.after(100, lambda: self._select_customer(dialog.result['id']))
    
    def _edit_customer(self):
        """Edytuj wybranego klienta"""
        if not self.selected_customer:
            messagebox.showwarning("Uwaga", "Wybierz klienta do edycji")
            return
        
        dialog = CustomerEditDialog(self, self.service, self.selected_customer)
        self.wait_window(dialog)
        
        if dialog.result:
            self._load_customers()
            self.after(100, lambda: self._select_customer(dialog.result['id']))
    
    def _delete_customer(self):
        """Usuń wybranego klienta"""
        if not self.selected_customer:
            messagebox.showwarning("Uwaga", "Wybierz klienta do usunięcia")
            return
        
        name = self.selected_customer.get('name', '')
        if not messagebox.askyesno(
            "Potwierdzenie",
            f"Czy na pewno chcesz usunąć klienta:\n{name}?"
        ):
            return
        
        try:
            self.service.delete(self.selected_customer['id'])
            messagebox.showinfo("Sukces", "Klient został usunięty")
            self._load_customers()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się usunąć klienta:\n{e}")
    
    def _block_customer(self):
        """Zablokuj klienta"""
        if not self.selected_customer:
            messagebox.showwarning("Uwaga", "Wybierz klienta")
            return
        
        if self.selected_customer.get('is_blocked'):
            messagebox.showinfo("Info", "Klient jest już zablokowany")
            return
        
        reason = ctk.CTkInputDialog(
            text="Podaj powód blokady:",
            title="Blokada klienta"
        ).get_input()
        
        if reason is None:
            return
        
        try:
            self.service.block(self.selected_customer['id'], reason)
            messagebox.showinfo("Sukces", "Klient został zablokowany")
            self._load_customers()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się zablokować:\n{e}")
    
    def _unblock_customer(self):
        """Odblokuj klienta"""
        if not self.selected_customer:
            messagebox.showwarning("Uwaga", "Wybierz klienta")
            return
        
        if not self.selected_customer.get('is_blocked'):
            messagebox.showinfo("Info", "Klient nie jest zablokowany")
            return
        
        try:
            self.service.unblock(self.selected_customer['id'])
            messagebox.showinfo("Sukces", "Klient został odblokowany")
            self._load_customers()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się odblokować:\n{e}")
    
    def _duplicate_customer(self):
        """Duplikuj klienta"""
        if not self.selected_customer:
            return
        
        try:
            new_customer = self.service.duplicate(self.selected_customer['id'])
            messagebox.showinfo("Sukces", f"Utworzono kopię: {new_customer['code']}")
            self._load_customers()
            self.after(100, lambda: self._select_customer(new_customer['id']))
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się zduplikować:\n{e}")
    
    def _send_email(self):
        """Otwórz klienta email"""
        if not self.selected_customer or not self.selected_customer.get('email'):
            return
        
        import webbrowser
        webbrowser.open(f"mailto:{self.selected_customer['email']}")
    
    def _call_customer(self):
        """Otwórz link tel:"""
        if not self.selected_customer or not self.selected_customer.get('phone'):
            return
        
        import webbrowser
        phone = self.selected_customer['phone'].replace(' ', '')
        webbrowser.open(f"tel:{phone}")
    
    def _show_history(self):
        """Pokaż historię zmian"""
        if not self.selected_customer:
            return
        
        try:
            history = self.service.get_history(self.selected_customer['id'])
            
            if not history:
                messagebox.showinfo("Historia", "Brak wpisów w historii")
                return
            
            # Proste okno z historią
            history_text = "\n".join([
                f"{h['created_at'][:19]} | {h['action']} | {h.get('user_email', 'system')}"
                for h in history[:20]
            ])
            
            messagebox.showinfo("Historia zmian", history_text)
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się pobrać historii:\n{e}")
    
    # ============================================================
    # Helpers
    # ============================================================
    
    def _select_customer(self, customer_id: str):
        """Zaznacz klienta w tabeli"""
        if not self.winfo_exists():
            return
        try:
            self.tree.selection_set(customer_id)
            self.tree.see(customer_id)
        except Exception:
            pass
    
    def _set_status(self, text: str):
        """Ustaw tekst statusu"""
        if not self.winfo_exists():
            return
        try:
            self.status_label.configure(text=text)
        except:
            pass
