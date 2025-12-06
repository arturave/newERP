"""
Pricing Window
==============
Główne okno do zarządzania cennikami materiałów i cięcia.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class Theme:
    """Kolory motywu"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_INPUT = "#2d2d2d"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#666666"
    ACCENT_PRIMARY = "#8b5cf6"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"
    ACCENT_INFO = "#06b6d4"


class PricingWindow(ctk.CTkToplevel):
    """Główne okno zarządzania cennikami"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.title("💰 Zarządzanie cennikami")
        self.geometry("1400x800")
        self.configure(fg_color=Theme.BG_DARK)
        
        # Serwis
        self.service = None
        self._init_service()
        
        # Dane
        self.material_prices = []
        self.cutting_prices = []
        self.selected_material_id = None
        self.selected_cutting_id = None
        
        self._setup_ui()
        self._load_data()
    
    def _init_service(self):
        """Inicjalizuj serwis"""
        try:
            from pricing import create_pricing_service
            self.service = create_pricing_service()
        except Exception as e:
            logger.error(f"Error initializing service: {e}")
            self.service = None
    
    def _setup_ui(self):
        """Buduj interfejs"""
        # Nagłówek
        self._create_header()
        
        # Tabview z zakładkami
        self.tabview = ctk.CTkTabview(self, fg_color=Theme.BG_DARK)
        self.tabview.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Zakładki
        self.tab_materials = self.tabview.add("📦 Ceny materiałów")
        self.tab_cutting = self.tabview.add("✂️ Ceny cięcia")
        self.tab_import = self.tabview.add("📥 Import / Export")
        self.tab_history = self.tabview.add("📋 Historia")
        
        self._setup_materials_tab()
        self._setup_cutting_tab()
        self._setup_import_tab()
        self._setup_history_tab()
    
    def _create_header(self):
        """Nagłówek okna"""
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60)
        header.pack(fill='x', padx=10, pady=(10, 0))
        header.pack_propagate(False)
        
        ctk.CTkLabel(
            header,
            text="💰 Zarządzanie cennikami",
            font=ctk.CTkFont(size=20, weight='bold')
        ).pack(side='left', padx=20, pady=15)
        
        # Statystyki
        self.stats_frame = ctk.CTkFrame(header, fg_color="transparent")
        self.stats_frame.pack(side='right', padx=20)
        
        self.lbl_stats = ctk.CTkLabel(
            self.stats_frame,
            text="Ładowanie...",
            text_color=Theme.TEXT_SECONDARY
        )
        self.lbl_stats.pack()
        
        # Przycisk odświeżania
        ctk.CTkButton(
            header,
            text="🔄",
            width=40,
            command=self._load_data
        ).pack(side='right', padx=5)
    
    # ============================================================
    # Zakładka: Ceny materiałów
    # ============================================================
    
    def _setup_materials_tab(self):
        """Zakładka cen materiałów"""
        # Lewy panel - filtry i akcje
        left = ctk.CTkFrame(self.tab_materials, fg_color=Theme.BG_CARD, width=280)
        left.pack(side='left', fill='y', padx=5, pady=5)
        left.pack_propagate(False)
        
        ctk.CTkLabel(
            left, text="🔍 Filtry",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(pady=10)
        
        # Filtr materiału
        ctk.CTkLabel(left, text="Materiał:").pack(anchor='w', padx=10)
        self.mat_filter_material = ctk.CTkComboBox(
            left, values=["-- Wszystkie --"], width=200,
            command=self._filter_materials
        )
        self.mat_filter_material.pack(padx=10, pady=5)
        
        # Filtr grubości
        ctk.CTkLabel(left, text="Grubość [mm]:").pack(anchor='w', padx=10, pady=(10, 0))
        self.mat_filter_thickness = ctk.CTkEntry(left, width=200, placeholder_text="np. 2")
        self.mat_filter_thickness.pack(padx=10, pady=5)
        self.mat_filter_thickness.bind('<Return>', lambda e: self._filter_materials())
        
        ctk.CTkButton(
            left, text="🔍 Filtruj", command=self._filter_materials, width=200
        ).pack(padx=10, pady=10)
        
        # Separator
        ctk.CTkFrame(left, height=2, fg_color=Theme.BG_INPUT).pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            left, text="⚡ Akcje",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(pady=10)
        
        ctk.CTkButton(
            left, text="➕ Dodaj cenę", command=self._add_material_price,
            fg_color=Theme.ACCENT_SUCCESS, width=200
        ).pack(padx=10, pady=5)
        
        ctk.CTkButton(
            left, text="✏️ Edytuj wybrany", command=self._edit_material_price,
            fg_color=Theme.ACCENT_INFO, width=200
        ).pack(padx=10, pady=5)
        
        ctk.CTkButton(
            left, text="🗑️ Usuń wybrany", command=self._delete_material_price,
            fg_color=Theme.ACCENT_DANGER, width=200
        ).pack(padx=10, pady=5)
        
        # Prawy panel - tabela
        right = ctk.CTkFrame(self.tab_materials, fg_color=Theme.BG_CARD)
        right.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        # Treeview
        columns = ('material', 'thickness', 'price', 'format', 'source', 'date')
        self.mat_tree = ttk.Treeview(right, columns=columns, show='headings', height=25)
        
        self.mat_tree.heading('material', text='Materiał')
        self.mat_tree.heading('thickness', text='Grubość [mm]')
        self.mat_tree.heading('price', text='Cena [PLN/kg]')
        self.mat_tree.heading('format', text='Format')
        self.mat_tree.heading('source', text='Źródło')
        self.mat_tree.heading('date', text='Data')
        
        self.mat_tree.column('material', width=120)
        self.mat_tree.column('thickness', width=100)
        self.mat_tree.column('price', width=100)
        self.mat_tree.column('format', width=100)
        self.mat_tree.column('source', width=150)
        self.mat_tree.column('date', width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(right, orient='vertical', command=self.mat_tree.yview)
        self.mat_tree.configure(yscrollcommand=scrollbar.set)
        
        self.mat_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar.pack(side='right', fill='y')
        
        self.mat_tree.bind('<<TreeviewSelect>>', self._on_material_select)
        self.mat_tree.bind('<Double-1>', lambda e: self._edit_material_price())
        
        self._style_treeview()
    
    # ============================================================
    # Zakładka: Ceny cięcia
    # ============================================================
    
    def _setup_cutting_tab(self):
        """Zakładka cen cięcia"""
        # Lewy panel
        left = ctk.CTkFrame(self.tab_cutting, fg_color=Theme.BG_CARD, width=280)
        left.pack(side='left', fill='y', padx=5, pady=5)
        left.pack_propagate(False)
        
        ctk.CTkLabel(
            left, text="🔍 Filtry",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(pady=10)
        
        # Filtr materiału
        ctk.CTkLabel(left, text="Materiał:").pack(anchor='w', padx=10)
        self.cut_filter_material = ctk.CTkComboBox(
            left, values=["-- Wszystkie --"], width=200,
            command=self._filter_cutting
        )
        self.cut_filter_material.pack(padx=10, pady=5)
        
        # Filtr gazu
        ctk.CTkLabel(left, text="Gaz:").pack(anchor='w', padx=10, pady=(10, 0))
        self.cut_filter_gas = ctk.CTkComboBox(
            left, values=["-- Wszystkie --", "N", "O", "A"], width=200,
            command=self._filter_cutting
        )
        self.cut_filter_gas.pack(padx=10, pady=5)
        
        ctk.CTkButton(
            left, text="🔍 Filtruj", command=self._filter_cutting, width=200
        ).pack(padx=10, pady=10)
        
        # Separator
        ctk.CTkFrame(left, height=2, fg_color=Theme.BG_INPUT).pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            left, text="⚡ Akcje",
            font=ctk.CTkFont(size=14, weight='bold')
        ).pack(pady=10)
        
        ctk.CTkButton(
            left, text="➕ Dodaj cenę", command=self._add_cutting_price,
            fg_color=Theme.ACCENT_SUCCESS, width=200
        ).pack(padx=10, pady=5)
        
        ctk.CTkButton(
            left, text="✏️ Edytuj wybrany", command=self._edit_cutting_price,
            fg_color=Theme.ACCENT_INFO, width=200
        ).pack(padx=10, pady=5)
        
        ctk.CTkButton(
            left, text="🗑️ Usuń wybrany", command=self._delete_cutting_price,
            fg_color=Theme.ACCENT_DANGER, width=200
        ).pack(padx=10, pady=5)
        
        # Prawy panel - tabela
        right = ctk.CTkFrame(self.tab_cutting, fg_color=Theme.BG_CARD)
        right.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        columns = ('material', 'thickness', 'gas', 'speed', 'hour_price', 'util', 'price_m')
        self.cut_tree = ttk.Treeview(right, columns=columns, show='headings', height=25)
        
        self.cut_tree.heading('material', text='Materiał')
        self.cut_tree.heading('thickness', text='Grubość [mm]')
        self.cut_tree.heading('gas', text='Gaz')
        self.cut_tree.heading('speed', text='Prędkość [m/min]')
        self.cut_tree.heading('hour_price', text='Cena/h [PLN]')
        self.cut_tree.heading('util', text='Wykorzystanie')
        self.cut_tree.heading('price_m', text='Cena/m [PLN]')
        
        self.cut_tree.column('material', width=120)
        self.cut_tree.column('thickness', width=100)
        self.cut_tree.column('gas', width=60)
        self.cut_tree.column('speed', width=120)
        self.cut_tree.column('hour_price', width=100)
        self.cut_tree.column('util', width=100)
        self.cut_tree.column('price_m', width=100)
        
        scrollbar = ttk.Scrollbar(right, orient='vertical', command=self.cut_tree.yview)
        self.cut_tree.configure(yscrollcommand=scrollbar.set)
        
        self.cut_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar.pack(side='right', fill='y')
        
        self.cut_tree.bind('<<TreeviewSelect>>', self._on_cutting_select)
        self.cut_tree.bind('<Double-1>', lambda e: self._edit_cutting_price())
    
    # ============================================================
    # Zakładka: Import / Export
    # ============================================================
    
    def _setup_import_tab(self):
        """Zakładka importu/eksportu"""
        # Import
        import_frame = ctk.CTkFrame(self.tab_import, fg_color=Theme.BG_CARD)
        import_frame.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            import_frame, text="📥 Import z Excel",
            font=ctk.CTkFont(size=16, weight='bold')
        ).pack(pady=15)
        
        info = ctk.CTkLabel(
            import_frame,
            text="Wybierz plik .xlsx z cennikiem. Program automatycznie wykryje typ (materiały/cięcie).\n"
                 "Istniejące rekordy zostaną zaktualizowane, nowe - dodane.",
            text_color=Theme.TEXT_SECONDARY,
            justify='left'
        )
        info.pack(padx=20, pady=5)
        
        btn_frame = ctk.CTkFrame(import_frame, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        ctk.CTkButton(
            btn_frame, text="📦 Import cen materiałów",
            command=lambda: self._import_excel('materials'),
            fg_color=Theme.ACCENT_SUCCESS, width=200
        ).pack(side='left', padx=10)
        
        ctk.CTkButton(
            btn_frame, text="✂️ Import cen cięcia",
            command=lambda: self._import_excel('cutting'),
            fg_color=Theme.ACCENT_INFO, width=200
        ).pack(side='left', padx=10)
        
        ctk.CTkButton(
            btn_frame, text="🔄 Auto-wykryj typ",
            command=lambda: self._import_excel(None),
            fg_color=Theme.ACCENT_PRIMARY, width=200
        ).pack(side='left', padx=10)
        
        # Export
        export_frame = ctk.CTkFrame(self.tab_import, fg_color=Theme.BG_CARD)
        export_frame.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            export_frame, text="📤 Eksport do Excel",
            font=ctk.CTkFont(size=16, weight='bold')
        ).pack(pady=15)
        
        btn_frame2 = ctk.CTkFrame(export_frame, fg_color="transparent")
        btn_frame2.pack(pady=15)
        
        ctk.CTkButton(
            btn_frame2, text="📦 Eksport cen materiałów",
            command=lambda: self._export_excel('materials'),
            fg_color=Theme.ACCENT_WARNING, width=200
        ).pack(side='left', padx=10)
        
        ctk.CTkButton(
            btn_frame2, text="✂️ Eksport cen cięcia",
            command=lambda: self._export_excel('cutting'),
            fg_color=Theme.ACCENT_WARNING, width=200
        ).pack(side='left', padx=10)
        
        # Status importu
        self.import_status = ctk.CTkLabel(
            self.tab_import,
            text="",
            text_color=Theme.TEXT_SECONDARY
        )
        self.import_status.pack(pady=20)
    
    # ============================================================
    # Zakładka: Historia
    # ============================================================
    
    def _setup_history_tab(self):
        """Zakładka historii importów"""
        ctk.CTkLabel(
            self.tab_history, text="📋 Historia importów",
            font=ctk.CTkFont(size=16, weight='bold')
        ).pack(pady=15)
        
        # Tabela historii
        columns = ('date', 'type', 'filename', 'imported', 'updated', 'failed', 'status')
        self.history_tree = ttk.Treeview(self.tab_history, columns=columns, show='headings', height=20)
        
        self.history_tree.heading('date', text='Data')
        self.history_tree.heading('type', text='Typ')
        self.history_tree.heading('filename', text='Plik')
        self.history_tree.heading('imported', text='Dodano')
        self.history_tree.heading('updated', text='Zaktualizowano')
        self.history_tree.heading('failed', text='Błędy')
        self.history_tree.heading('status', text='Status')
        
        self.history_tree.column('date', width=150)
        self.history_tree.column('type', width=100)
        self.history_tree.column('filename', width=250)
        self.history_tree.column('imported', width=80)
        self.history_tree.column('updated', width=100)
        self.history_tree.column('failed', width=80)
        self.history_tree.column('status', width=100)
        
        scrollbar = ttk.Scrollbar(self.tab_history, orient='vertical', command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        self.history_tree.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        scrollbar.pack(side='right', fill='y', pady=10)
    
    def _style_treeview(self):
        """Stylizuj Treeview na dark mode"""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure(
            "Treeview",
            background="#2d2d2d",
            foreground="white",
            fieldbackground="#2d2d2d",
            rowheight=28
        )
        style.configure(
            "Treeview.Heading",
            background="#1a1a1a",
            foreground="white",
            font=('Arial', 10, 'bold')
        )
        style.map("Treeview", background=[('selected', '#3b82f6')])
    
    # ============================================================
    # Ładowanie danych
    # ============================================================
    
    def _load_data(self):
        """Załaduj wszystkie dane"""
        if not self.service:
            messagebox.showerror("Błąd", "Brak połączenia z bazą danych")
            return
        
        def load():
            try:
                # Statystyki
                stats = self.service.get_statistics()
                self.after(0, lambda: self._update_stats(stats))
                
                # Ceny materiałów
                materials = self.service.get_material_prices()
                self.after(0, lambda: self._populate_materials(materials))
                
                # Ceny cięcia
                cutting = self.service.get_cutting_prices()
                self.after(0, lambda: self._populate_cutting(cutting))
                
                # Historia
                history = self.service.get_import_history()
                self.after(0, lambda: self._populate_history(history))
                
                # Aktualizuj filtry
                materials_list = stats.get('materials', [])
                self.after(0, lambda: self._update_filters(materials_list))
                
            except Exception as e:
                logger.error(f"Error loading data: {e}")
                self.after(0, lambda: messagebox.showerror("Błąd", f"Błąd ładowania: {e}"))
        
        threading.Thread(target=load, daemon=True).start()
    
    def _update_stats(self, stats: Dict):
        """Aktualizuj statystyki w nagłówku"""
        text = (f"📦 Ceny materiałów: {stats.get('material_prices_count', 0)} | "
                f"✂️ Ceny cięcia: {stats.get('cutting_prices_count', 0)} | "
                f"🧱 Materiałów: {stats.get('materials_count', 0)}")
        self.lbl_stats.configure(text=text)
    
    def _update_filters(self, materials: List[str]):
        """Aktualizuj filtry"""
        values = ["-- Wszystkie --"] + materials
        self.mat_filter_material.configure(values=values)
        self.cut_filter_material.configure(values=values)
    
    def _populate_materials(self, records: List[Dict]):
        """Wypełnij tabelę cen materiałów"""
        self.material_prices = records
        
        # Wyczyść
        for item in self.mat_tree.get_children():
            self.mat_tree.delete(item)
        
        # Dodaj
        for r in records:
            values = (
                r.get('material', ''),
                f"{r.get('thickness', 0):.1f}",
                f"{r.get('price_per_kg', 0):.2f}",
                r.get('format', '1500x3000'),
                r.get('source', '') or '',
                r.get('valid_from', '')[:10] if r.get('valid_from') else ''
            )
            self.mat_tree.insert('', 'end', iid=r.get('id'), values=values)
    
    def _populate_cutting(self, records: List[Dict]):
        """Wypełnij tabelę cen cięcia"""
        self.cutting_prices = records
        
        for item in self.cut_tree.get_children():
            self.cut_tree.delete(item)
        
        for r in records:
            values = (
                r.get('material', ''),
                f"{r.get('thickness', 0):.1f}",
                r.get('gas', 'N'),
                f"{r.get('cutting_speed', 0):.1f}" if r.get('cutting_speed') else '',
                f"{r.get('hour_price', 0):.0f}",
                f"{r.get('utilization', 0):.2f}",
                f"{r.get('price_per_meter', 0):.4f}" if r.get('price_per_meter') else ''
            )
            self.cut_tree.insert('', 'end', iid=r.get('id'), values=values)
    
    def _populate_history(self, records: List[Dict]):
        """Wypełnij historię importów"""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        for r in records:
            created = r.get('created_at', '')
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    created = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            
            values = (
                created,
                r.get('import_type', ''),
                r.get('filename', ''),
                r.get('records_imported', 0),
                r.get('records_updated', 0),
                r.get('records_failed', 0),
                r.get('status', '')
            )
            self.history_tree.insert('', 'end', values=values)
    
    # ============================================================
    # Filtry
    # ============================================================
    
    def _filter_materials(self, *args):
        """Filtruj ceny materiałów"""
        material = self.mat_filter_material.get()
        thickness_str = self.mat_filter_thickness.get().strip()
        
        material = None if material.startswith('--') else material
        thickness = None
        if thickness_str:
            try:
                thickness = float(thickness_str)
            except ValueError:
                pass
        
        if self.service:
            records = self.service.get_material_prices(material=material, thickness=thickness)
            self._populate_materials(records)
    
    def _filter_cutting(self, *args):
        """Filtruj ceny cięcia"""
        material = self.cut_filter_material.get()
        gas = self.cut_filter_gas.get()
        
        material = None if material.startswith('--') else material
        gas = None if gas.startswith('--') else gas
        
        if self.service:
            records = self.service.get_cutting_prices(material=material, gas=gas)
            self._populate_cutting(records)
    
    # ============================================================
    # Akcje na cenach materiałów
    # ============================================================
    
    def _on_material_select(self, event):
        """Wybór w tabeli materiałów"""
        selection = self.mat_tree.selection()
        self.selected_material_id = selection[0] if selection else None
    
    def _add_material_price(self):
        """Dodaj nową cenę materiału"""
        dialog = MaterialPriceDialog(self, "Dodaj cenę materiału")
        self.wait_window(dialog)
        
        if dialog.result:
            success, msg = self.service.add_material_price(dialog.result)
            if success:
                messagebox.showinfo("Sukces", msg)
                self._load_data()
            else:
                messagebox.showerror("Błąd", msg)
    
    def _edit_material_price(self):
        """Edytuj cenę materiału"""
        if not self.selected_material_id:
            messagebox.showwarning("Uwaga", "Wybierz rekord do edycji")
            return
        
        # Znajdź rekord
        record = next((r for r in self.material_prices if r.get('id') == self.selected_material_id), None)
        if not record:
            return
        
        dialog = MaterialPriceDialog(self, "Edytuj cenę materiału", record)
        self.wait_window(dialog)
        
        if dialog.result:
            success, msg = self.service.update_material_price(self.selected_material_id, dialog.result)
            if success:
                messagebox.showinfo("Sukces", msg)
                self._load_data()
            else:
                messagebox.showerror("Błąd", msg)
    
    def _delete_material_price(self):
        """Usuń cenę materiału"""
        if not self.selected_material_id:
            messagebox.showwarning("Uwaga", "Wybierz rekord do usunięcia")
            return
        
        if messagebox.askyesno("Potwierdzenie", "Czy na pewno usunąć ten rekord?"):
            success, msg = self.service.delete_material_price(self.selected_material_id)
            if success:
                messagebox.showinfo("Sukces", msg)
                self._load_data()
            else:
                messagebox.showerror("Błąd", msg)
    
    # ============================================================
    # Akcje na cenach cięcia
    # ============================================================
    
    def _on_cutting_select(self, event):
        """Wybór w tabeli cięcia"""
        selection = self.cut_tree.selection()
        self.selected_cutting_id = selection[0] if selection else None
    
    def _add_cutting_price(self):
        """Dodaj cenę cięcia"""
        dialog = CuttingPriceDialog(self, "Dodaj cenę cięcia")
        self.wait_window(dialog)
        
        if dialog.result:
            success, msg = self.service.add_cutting_price(dialog.result)
            if success:
                messagebox.showinfo("Sukces", msg)
                self._load_data()
            else:
                messagebox.showerror("Błąd", msg)
    
    def _edit_cutting_price(self):
        """Edytuj cenę cięcia"""
        if not self.selected_cutting_id:
            messagebox.showwarning("Uwaga", "Wybierz rekord do edycji")
            return
        
        record = next((r for r in self.cutting_prices if r.get('id') == self.selected_cutting_id), None)
        if not record:
            return
        
        dialog = CuttingPriceDialog(self, "Edytuj cenę cięcia", record)
        self.wait_window(dialog)
        
        if dialog.result:
            success, msg = self.service.update_cutting_price(self.selected_cutting_id, dialog.result)
            if success:
                messagebox.showinfo("Sukces", msg)
                self._load_data()
            else:
                messagebox.showerror("Błąd", msg)
    
    def _delete_cutting_price(self):
        """Usuń cenę cięcia"""
        if not self.selected_cutting_id:
            messagebox.showwarning("Uwaga", "Wybierz rekord do usunięcia")
            return
        
        if messagebox.askyesno("Potwierdzenie", "Czy na pewno usunąć ten rekord?"):
            success, msg = self.service.delete_cutting_price(self.selected_cutting_id)
            if success:
                messagebox.showinfo("Sukces", msg)
                self._load_data()
            else:
                messagebox.showerror("Błąd", msg)
    
    # ============================================================
    # Import / Export
    # ============================================================
    
    def _import_excel(self, price_type: Optional[str]):
        """Importuj z Excel"""
        filepath = filedialog.askopenfilename(
            title="Wybierz plik Excel",
            filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        self.import_status.configure(text="⏳ Importowanie...", text_color=Theme.ACCENT_WARNING)
        
        def do_import():
            try:
                result = self.service.import_from_excel(filepath, price_type)
                
                if result.success:
                    msg = f"✅ Import zakończony!\nDodano: {result.imported}, Zaktualizowano: {result.updated}"
                    if result.failed > 0:
                        msg += f", Błędy: {result.failed}"
                    self.after(0, lambda: self.import_status.configure(text=msg, text_color=Theme.ACCENT_SUCCESS))
                    self.after(0, self._load_data)
                else:
                    msg = f"❌ Import nieudany: {', '.join(result.errors)}"
                    self.after(0, lambda: self.import_status.configure(text=msg, text_color=Theme.ACCENT_DANGER))
                    
            except Exception as e:
                self.after(0, lambda: self.import_status.configure(text=f"❌ Błąd: {e}", text_color=Theme.ACCENT_DANGER))
        
        threading.Thread(target=do_import, daemon=True).start()
    
    def _export_excel(self, price_type: str):
        """Eksportuj do Excel"""
        default_name = f"cennik_{price_type}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        filepath = filedialog.asksaveasfilename(
            title="Zapisz jako",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel Files", "*.xlsx")]
        )
        
        if not filepath:
            return
        
        success, msg = self.service.export_to_excel(filepath, price_type)
        if success:
            messagebox.showinfo("Sukces", msg)
        else:
            messagebox.showerror("Błąd", msg)


# ============================================================
# Dialogi edycji
# ============================================================

class MaterialPriceDialog(ctk.CTkToplevel):
    """Dialog edycji ceny materiału"""
    
    def __init__(self, parent, title: str, data: Dict = None):
        super().__init__(parent)
        
        self.title(title)
        self.geometry("400x450")
        self.configure(fg_color=Theme.BG_DARK)
        self.resizable(False, False)
        
        self.data = data or {}
        self.result = None
        
        self._setup_ui()
        self._populate()
        
        self.grab_set()
        self.focus_force()
    
    def _setup_ui(self):
        """Buduj UI"""
        frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Materiał
        ctk.CTkLabel(frame, text="Materiał *:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_material = ctk.CTkEntry(frame, width=300)
        self.entry_material.pack(padx=10, pady=5)
        
        # Grubość
        ctk.CTkLabel(frame, text="Grubość [mm] *:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_thickness = ctk.CTkEntry(frame, width=300)
        self.entry_thickness.pack(padx=10, pady=5)
        
        # Cena
        ctk.CTkLabel(frame, text="Cena [PLN/kg] *:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_price = ctk.CTkEntry(frame, width=300)
        self.entry_price.pack(padx=10, pady=5)
        
        # Format
        ctk.CTkLabel(frame, text="Format arkusza:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_format = ctk.CTkComboBox(
            frame, values=['1500x3000', '2000x1000', '2500x1250', '3000x1500'], width=300
        )
        self.entry_format.pack(padx=10, pady=5)
        
        # Źródło
        ctk.CTkLabel(frame, text="Źródło / Dostawca:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_source = ctk.CTkEntry(frame, width=300)
        self.entry_source.pack(padx=10, pady=5)
        
        # Uwagi
        ctk.CTkLabel(frame, text="Uwagi:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_note = ctk.CTkEntry(frame, width=300)
        self.entry_note.pack(padx=10, pady=5)
        
        # Przyciski
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(
            btn_frame, text="💾 Zapisz", command=self._save,
            fg_color=Theme.ACCENT_SUCCESS, width=120
        ).pack(side='left', padx=10)
        
        ctk.CTkButton(
            btn_frame, text="❌ Anuluj", command=self.destroy,
            fg_color=Theme.ACCENT_DANGER, width=120
        ).pack(side='left', padx=10)
    
    def _populate(self):
        """Wypełnij danymi"""
        if self.data:
            self.entry_material.insert(0, self.data.get('material', ''))
            self.entry_thickness.insert(0, str(self.data.get('thickness', '')))
            self.entry_price.insert(0, str(self.data.get('price_per_kg', '')))
            self.entry_format.set(self.data.get('format', '1500x3000'))
            self.entry_source.insert(0, self.data.get('source', '') or '')
            self.entry_note.insert(0, self.data.get('note', '') or '')
    
    def _save(self):
        """Zapisz"""
        material = self.entry_material.get().strip()
        thickness_str = self.entry_thickness.get().strip()
        price_str = self.entry_price.get().strip()
        
        if not material or not thickness_str or not price_str:
            messagebox.showwarning("Uwaga", "Wypełnij wymagane pola (*)") 
            return
        
        try:
            thickness = float(thickness_str)
            price = float(price_str)
        except ValueError:
            messagebox.showwarning("Uwaga", "Nieprawidłowe wartości liczbowe")
            return
        
        self.result = {
            'material': material.upper(),
            'thickness': thickness,
            'price_per_kg': price,
            'format': self.entry_format.get(),
            'source': self.entry_source.get().strip() or None,
            'note': self.entry_note.get().strip() or None
        }
        
        self.destroy()


class CuttingPriceDialog(ctk.CTkToplevel):
    """Dialog edycji ceny cięcia"""
    
    def __init__(self, parent, title: str, data: Dict = None):
        super().__init__(parent)
        
        self.title(title)
        self.geometry("400x550")
        self.configure(fg_color=Theme.BG_DARK)
        self.resizable(False, False)
        
        self.data = data or {}
        self.result = None
        
        self._setup_ui()
        self._populate()
        
        self.grab_set()
        self.focus_force()
    
    def _setup_ui(self):
        """Buduj UI"""
        frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD)
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Materiał
        ctk.CTkLabel(frame, text="Materiał *:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_material = ctk.CTkEntry(frame, width=300)
        self.entry_material.pack(padx=10, pady=5)
        
        # Grubość
        ctk.CTkLabel(frame, text="Grubość [mm] *:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_thickness = ctk.CTkEntry(frame, width=300)
        self.entry_thickness.pack(padx=10, pady=5)
        
        # Gaz
        ctk.CTkLabel(frame, text="Gaz:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_gas = ctk.CTkComboBox(frame, values=['N', 'O', 'A'], width=300)
        self.entry_gas.pack(padx=10, pady=5)
        
        # Prędkość
        ctk.CTkLabel(frame, text="Prędkość cięcia [m/min]:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_speed = ctk.CTkEntry(frame, width=300)
        self.entry_speed.pack(padx=10, pady=5)
        
        # Cena godziny
        ctk.CTkLabel(frame, text="Cena godziny [PLN/h]:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_hour_price = ctk.CTkEntry(frame, width=300)
        self.entry_hour_price.pack(padx=10, pady=5)
        self.entry_hour_price.insert(0, "750")
        
        # Wykorzystanie
        ctk.CTkLabel(frame, text="Współczynnik wykorzystania:").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_util = ctk.CTkEntry(frame, width=300)
        self.entry_util.pack(padx=10, pady=5)
        self.entry_util.insert(0, "0.65")
        
        # Cena ręczna
        ctk.CTkLabel(frame, text="Cena za metr [PLN/m] (opcjonalnie):").pack(anchor='w', padx=10, pady=(10, 0))
        self.entry_price_m = ctk.CTkEntry(frame, width=300)
        self.entry_price_m.pack(padx=10, pady=5)
        
        # Info
        ctk.CTkLabel(
            frame, 
            text="Jeśli nie podasz ceny/m, zostanie obliczona automatycznie",
            text_color=Theme.TEXT_MUTED,
            font=ctk.CTkFont(size=11)
        ).pack(padx=10, pady=5)
        
        # Przyciski
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        ctk.CTkButton(
            btn_frame, text="💾 Zapisz", command=self._save,
            fg_color=Theme.ACCENT_SUCCESS, width=120
        ).pack(side='left', padx=10)
        
        ctk.CTkButton(
            btn_frame, text="❌ Anuluj", command=self.destroy,
            fg_color=Theme.ACCENT_DANGER, width=120
        ).pack(side='left', padx=10)
    
    def _populate(self):
        """Wypełnij danymi"""
        if self.data:
            self.entry_material.insert(0, self.data.get('material', ''))
            self.entry_thickness.insert(0, str(self.data.get('thickness', '')))
            self.entry_gas.set(self.data.get('gas', 'N'))
            if self.data.get('cutting_speed'):
                self.entry_speed.insert(0, str(self.data.get('cutting_speed')))
            self.entry_hour_price.delete(0, 'end')
            self.entry_hour_price.insert(0, str(self.data.get('hour_price', 750)))
            self.entry_util.delete(0, 'end')
            self.entry_util.insert(0, str(self.data.get('utilization', 0.65)))
            if self.data.get('price_per_meter'):
                self.entry_price_m.insert(0, str(self.data.get('price_per_meter')))
    
    def _save(self):
        """Zapisz"""
        material = self.entry_material.get().strip()
        thickness_str = self.entry_thickness.get().strip()
        
        if not material or not thickness_str:
            messagebox.showwarning("Uwaga", "Wypełnij wymagane pola (*)")
            return
        
        try:
            thickness = float(thickness_str)
        except ValueError:
            messagebox.showwarning("Uwaga", "Nieprawidłowa grubość")
            return
        
        self.result = {
            'material': material.upper(),
            'thickness': thickness,
            'gas': self.entry_gas.get()
        }
        
        # Opcjonalne
        speed_str = self.entry_speed.get().strip()
        if speed_str:
            try:
                self.result['cutting_speed'] = float(speed_str)
            except ValueError:
                pass
        
        hour_price_str = self.entry_hour_price.get().strip()
        if hour_price_str:
            try:
                self.result['hour_price'] = float(hour_price_str)
            except ValueError:
                pass
        
        util_str = self.entry_util.get().strip()
        if util_str:
            try:
                self.result['utilization'] = float(util_str)
            except ValueError:
                pass
        
        price_m_str = self.entry_price_m.get().strip()
        if price_m_str:
            try:
                self.result['price_per_meter'] = float(price_m_str)
                self.result['price_manual'] = True
            except ValueError:
                pass
        
        self.destroy()


# ============================================================
# Export dla modułu
# ============================================================

__all__ = ['PricingWindow', 'MaterialPriceDialog', 'CuttingPriceDialog']
