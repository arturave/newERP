"""
NewERP - Customer Edit Dialog
=============================
Dialog do dodawania i edycji klientów.
"""

import customtkinter as ctk
from tkinter import messagebox
from typing import Dict, Optional, Any
import logging

from customers.service import CustomerService

logger = logging.getLogger(__name__)


class CustomerEditDialog(ctk.CTkToplevel):
    """
    Dialog do dodawania/edycji klienta.
    
    Atrybuty:
        result: Wynik operacji (utworzony/zaktualizowany klient) lub None
    """
    
    def __init__(
        self, 
        parent, 
        service: CustomerService,
        customer: Dict = None
    ):
        super().__init__(parent)
        
        self.service = service
        self.customer = customer
        self.is_edit_mode = customer is not None
        self.result: Optional[Dict] = None
        
        # Konfiguracja okna
        title = "Edycja klienta" if self.is_edit_mode else "Nowy klient"
        self.title(title)
        self.geometry("700x750")
        self.minsize(600, 600)
        self.resizable(True, True)
        
        # Modal
        self.transient(parent)
        self.grab_set()
        
        # Wyśrodkowanie
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 750) // 2
        self.geometry(f"+{x}+{y}")
        
        # Setup UI
        self._setup_ui()
        
        # Wypełnij danymi jeśli edycja
        if self.is_edit_mode:
            self._load_customer_data()
        
        # Focus
        self.name_entry.focus()
    
    def _setup_ui(self):
        """Buduj interfejs"""
        
        # Main scrollable frame
        self.main_frame = ctk.CTkScrollableFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=(20, 10))
        
        # === SEKCJA: Dane podstawowe ===
        self._create_section("📋 Dane podstawowe")
        
        # Nazwa (wymagana)
        self._create_label("Nazwa firmy / Imię i nazwisko *")
        self.name_entry = ctk.CTkEntry(self.main_frame, width=400)
        self.name_entry.pack(anchor="w", pady=(0, 10))
        
        # Nazwa skrócona
        self._create_label("Nazwa skrócona")
        self.short_name_entry = ctk.CTkEntry(self.main_frame, width=200)
        self.short_name_entry.pack(anchor="w", pady=(0, 10))
        
        # Kod klienta
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Kod klienta:").pack(side="left")
        self.code_entry = ctk.CTkEntry(row, width=150)
        self.code_entry.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(row, text="(automatyczny jeśli puste)", text_color="gray").pack(side="left", padx=10)
        
        # Typ klienta
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Typ:").pack(side="left")
        self.type_var = ctk.StringVar(value="company")
        ctk.CTkRadioButton(row, text="Firma", variable=self.type_var, value="company").pack(side="left", padx=(20, 10))
        ctk.CTkRadioButton(row, text="Osoba fizyczna", variable=self.type_var, value="individual").pack(side="left")
        
        # === SEKCJA: Dane firmowe ===
        self._create_section("🏢 Dane firmowe")
        
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        # NIP
        ctk.CTkLabel(row, text="NIP:").pack(side="left")
        self.nip_entry = ctk.CTkEntry(row, width=150, placeholder_text="1234567890")
        self.nip_entry.pack(side="left", padx=(10, 10))
        
        # Przycisk pobierania z GUS
        gus_btn = ctk.CTkButton(
            row,
            text="📥 Pobierz z GUS",
            command=self._fetch_from_gus,
            width=120,
            height=28,
            fg_color="#28a745",
            hover_color="#218838"
        )
        gus_btn.pack(side="left", padx=(0, 20))
        
        # REGON
        ctk.CTkLabel(row, text="REGON:").pack(side="left")
        self.regon_entry = ctk.CTkEntry(row, width=150)
        self.regon_entry.pack(side="left", padx=(10, 0))
        
        # KRS
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="KRS:").pack(side="left")
        self.krs_entry = ctk.CTkEntry(row, width=150)
        self.krs_entry.pack(side="left", padx=(10, 0))
        
        # === SEKCJA: Adres ===
        self._create_section("📍 Adres siedziby")
        
        # Ulica
        self._create_label("Ulica")
        self.street_entry = ctk.CTkEntry(self.main_frame, width=300)
        self.street_entry.pack(anchor="w", pady=(0, 10))
        
        # Numer budynku / lokalu
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Nr budynku:").pack(side="left")
        self.building_entry = ctk.CTkEntry(row, width=80)
        self.building_entry.pack(side="left", padx=(10, 20))
        
        ctk.CTkLabel(row, text="Nr lokalu:").pack(side="left")
        self.apartment_entry = ctk.CTkEntry(row, width=80)
        self.apartment_entry.pack(side="left", padx=(10, 0))
        
        # Kod pocztowy / miasto
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Kod pocztowy:").pack(side="left")
        self.postal_entry = ctk.CTkEntry(row, width=100, placeholder_text="00-000")
        self.postal_entry.pack(side="left", padx=(10, 20))
        
        ctk.CTkLabel(row, text="Miasto:").pack(side="left")
        self.city_entry = ctk.CTkEntry(row, width=200)
        self.city_entry.pack(side="left", padx=(10, 0))
        
        # Kraj
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Kraj:").pack(side="left")
        self.country_entry = ctk.CTkEntry(row, width=150)
        self.country_entry.insert(0, "Polska")
        self.country_entry.pack(side="left", padx=(10, 0))
        
        # === SEKCJA: Kontakt ===
        self._create_section("📧 Dane kontaktowe")
        
        # Email
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Email:").pack(side="left")
        self.email_entry = ctk.CTkEntry(row, width=250, placeholder_text="kontakt@firma.pl")
        self.email_entry.pack(side="left", padx=(10, 0))
        
        # Telefony
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Telefon:").pack(side="left")
        self.phone_entry = ctk.CTkEntry(row, width=150, placeholder_text="+48 123 456 789")
        self.phone_entry.pack(side="left", padx=(10, 20))
        
        ctk.CTkLabel(row, text="Komórka:").pack(side="left")
        self.mobile_entry = ctk.CTkEntry(row, width=150)
        self.mobile_entry.pack(side="left", padx=(10, 0))
        
        # WWW
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Strona WWW:").pack(side="left")
        self.website_entry = ctk.CTkEntry(row, width=250, placeholder_text="https://")
        self.website_entry.pack(side="left", padx=(10, 0))
        
        # === SEKCJA: Warunki handlowe ===
        self._create_section("💰 Warunki handlowe")
        
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        # Termin płatności
        ctk.CTkLabel(row, text="Termin płatności (dni):").pack(side="left")
        self.payment_days_entry = ctk.CTkEntry(row, width=80)
        self.payment_days_entry.insert(0, "14")
        self.payment_days_entry.pack(side="left", padx=(10, 20))
        
        # Rabat
        ctk.CTkLabel(row, text="Rabat (%):").pack(side="left")
        self.discount_entry = ctk.CTkEntry(row, width=80)
        self.discount_entry.insert(0, "0")
        self.discount_entry.pack(side="left", padx=(10, 0))
        
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        # Limit kredytowy
        ctk.CTkLabel(row, text="Limit kredytowy (PLN):").pack(side="left")
        self.credit_limit_entry = ctk.CTkEntry(row, width=120)
        self.credit_limit_entry.pack(side="left", padx=(10, 20))
        
        # Cennik
        ctk.CTkLabel(row, text="Cennik:").pack(side="left")
        self.price_list_var = ctk.StringVar(value="standard")
        self.price_list_combo = ctk.CTkComboBox(
            row,
            values=["standard", "vip", "wholesale"],
            variable=self.price_list_var,
            width=120
        )
        self.price_list_combo.pack(side="left", padx=(10, 0))
        
        # === SEKCJA: Kategoria i notatki ===
        self._create_section("📝 Inne")
        
        # Kategoria
        row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(row, text="Kategoria:").pack(side="left")
        self.category_entry = ctk.CTkEntry(row, width=150)
        self.category_entry.pack(side="left", padx=(10, 20))
        
        ctk.CTkLabel(row, text="Tagi (przecinki):").pack(side="left")
        self.tags_entry = ctk.CTkEntry(row, width=200, placeholder_text="vip, produkcja")
        self.tags_entry.pack(side="left", padx=(10, 0))
        
        # Notatki
        self._create_label("Notatki wewnętrzne")
        self.notes_text = ctk.CTkTextbox(self.main_frame, width=400, height=80)
        self.notes_text.pack(anchor="w", pady=(0, 10))
        
        # === PRZYCISKI ===
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 20))
        
        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Anuluj",
            command=self.destroy,
            width=120,
            fg_color="gray"
        )
        cancel_btn.pack(side="right", padx=(10, 0))
        
        save_btn = ctk.CTkButton(
            btn_frame,
            text="💾 Zapisz",
            command=self._save,
            width=120
        )
        save_btn.pack(side="right")
        
        # Bindingi
        self.bind('<Return>', lambda e: self._save())
        self.bind('<Escape>', lambda e: self.destroy())
    
    def _create_section(self, title: str):
        """Utwórz nagłówek sekcji"""
        label = ctk.CTkLabel(
            self.main_frame,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        label.pack(anchor="w", pady=(20, 10))
        
        sep = ctk.CTkFrame(self.main_frame, height=2)
        sep.pack(fill="x", pady=(0, 10))
    
    def _create_label(self, text: str):
        """Utwórz etykietę pola"""
        label = ctk.CTkLabel(
            self.main_frame,
            text=text,
            font=ctk.CTkFont(size=12)
        )
        label.pack(anchor="w", pady=(5, 2))
    
    def _load_customer_data(self):
        """Wypełnij formularz danymi klienta"""
        c = self.customer
        
        # Podstawowe
        self._set_entry(self.name_entry, c.get('name', ''))
        self._set_entry(self.short_name_entry, c.get('short_name', ''))
        self._set_entry(self.code_entry, c.get('code', ''))
        self.type_var.set(c.get('type', 'company'))
        
        # Dane firmowe
        self._set_entry(self.nip_entry, c.get('nip', ''))
        self._set_entry(self.regon_entry, c.get('regon', ''))
        self._set_entry(self.krs_entry, c.get('krs', ''))
        
        # Adres
        self._set_entry(self.street_entry, c.get('address_street', ''))
        self._set_entry(self.building_entry, c.get('address_building', ''))
        self._set_entry(self.apartment_entry, c.get('address_apartment', ''))
        self._set_entry(self.postal_entry, c.get('address_postal_code', ''))
        self._set_entry(self.city_entry, c.get('address_city', ''))
        self._set_entry(self.country_entry, c.get('address_country', 'Polska'))
        
        # Kontakt
        self._set_entry(self.email_entry, c.get('email', ''))
        self._set_entry(self.phone_entry, c.get('phone', ''))
        self._set_entry(self.mobile_entry, c.get('phone_mobile', ''))
        self._set_entry(self.website_entry, c.get('website', ''))
        
        # Warunki handlowe
        self._set_entry(self.payment_days_entry, str(c.get('payment_days', 14)))
        self._set_entry(self.discount_entry, str(c.get('discount_percent', 0)))
        self._set_entry(self.credit_limit_entry, str(c.get('credit_limit', '')) if c.get('credit_limit') else '')
        self.price_list_var.set(c.get('price_list', 'standard'))
        
        # Kategoria i notatki
        self._set_entry(self.category_entry, c.get('category', ''))
        tags = c.get('tags', [])
        if tags:
            self._set_entry(self.tags_entry, ', '.join(tags))
        
        if c.get('notes'):
            self.notes_text.delete("1.0", "end")
            self.notes_text.insert("1.0", c['notes'])
    
    def _set_entry(self, entry, value: str):
        """Ustaw wartość w Entry"""
        entry.delete(0, "end")
        if value:
            entry.insert(0, value)
    
    def _fetch_from_gus(self):
        """Pobierz dane firmy z GUS na podstawie NIP"""
        nip = self.nip_entry.get().strip().replace('-', '').replace(' ', '')
        
        if not nip:
            messagebox.showwarning("Uwaga", "Wprowadź NIP aby pobrać dane z GUS")
            return
        
        if len(nip) != 10 or not nip.isdigit():
            messagebox.showerror("Błąd", "NIP musi składać się z 10 cyfr")
            return
        
        # Pokaż status
        self.title("Pobieranie danych z GUS...")
        self.update()
        
        try:
            from customers.gus_api import fetch_company_by_nip, GUSApiError
            
            company = fetch_company_by_nip(nip)
            
            if company:
                # Pytanie czy nadpisać
                if self.name_entry.get().strip():
                    if not messagebox.askyesno(
                        "Potwierdzenie",
                        f"Znaleziono: {company.name}\n\n"
                        "Czy chcesz nadpisać aktualne dane?"
                    ):
                        self.title("Edycja klienta" if self.is_edit_mode else "Nowy klient")
                        return
                
                # Wypełnij formularz
                self._set_entry(self.name_entry, company.name)
                self._set_entry(self.short_name_entry, company.short_name or '')
                self._set_entry(self.nip_entry, company.nip)
                self._set_entry(self.regon_entry, company.regon or '')
                self._set_entry(self.krs_entry, company.krs or '')
                self._set_entry(self.street_entry, company.street or '')
                self._set_entry(self.building_entry, company.building_number or '')
                self._set_entry(self.apartment_entry, company.apartment_number or '')
                self._set_entry(self.postal_entry, company.postal_code or '')
                self._set_entry(self.city_entry, company.city or '')
                
                # Ustaw typ na firmę
                self.type_var.set("company")
                
                messagebox.showinfo(
                    "Sukces", 
                    f"Pobrano dane firmy:\n{company.name}\n{company.city}"
                )
            else:
                messagebox.showwarning(
                    "Nie znaleziono",
                    f"Nie znaleziono firmy o NIP: {nip}\n\n"
                    "Sprawdź poprawność numeru NIP."
                )
                
        except ImportError:
            messagebox.showerror(
                "Błąd",
                "Brak modułu gus_api.\n"
                "Upewnij się że plik customers/gus_api.py istnieje."
            )
        except Exception as e:
            logger.error(f"[GUS] Fetch error: {e}")
            messagebox.showerror("Błąd GUS", f"Nie udało się pobrać danych:\n{e}")
        
        finally:
            self.title("Edycja klienta" if self.is_edit_mode else "Nowy klient")
    
    def _collect_data(self) -> Dict[str, Any]:
        """Zbierz dane z formularza"""
        data = {}
        
        # Podstawowe (wymagane)
        name = self.name_entry.get().strip()
        if not name:
            raise ValueError("Nazwa jest wymagana")
        data['name'] = name
        
        # Opcjonalne tekstowe
        if self.short_name_entry.get().strip():
            data['short_name'] = self.short_name_entry.get().strip()
        
        if self.code_entry.get().strip():
            data['code'] = self.code_entry.get().strip()
        
        data['type'] = self.type_var.get()
        
        # Dane firmowe
        if self.nip_entry.get().strip():
            data['nip'] = self.nip_entry.get().strip().replace('-', '').replace(' ', '')
        
        if self.regon_entry.get().strip():
            data['regon'] = self.regon_entry.get().strip()
        
        if self.krs_entry.get().strip():
            data['krs'] = self.krs_entry.get().strip()
        
        # Adres
        if self.street_entry.get().strip():
            data['address_street'] = self.street_entry.get().strip()
        
        if self.building_entry.get().strip():
            data['address_building'] = self.building_entry.get().strip()
        
        if self.apartment_entry.get().strip():
            data['address_apartment'] = self.apartment_entry.get().strip()
        
        if self.postal_entry.get().strip():
            data['address_postal_code'] = self.postal_entry.get().strip()
        
        if self.city_entry.get().strip():
            data['address_city'] = self.city_entry.get().strip()
        
        if self.country_entry.get().strip():
            data['address_country'] = self.country_entry.get().strip()
        
        # Kontakt
        if self.email_entry.get().strip():
            data['email'] = self.email_entry.get().strip()
        
        if self.phone_entry.get().strip():
            data['phone'] = self.phone_entry.get().strip()
        
        if self.mobile_entry.get().strip():
            data['phone_mobile'] = self.mobile_entry.get().strip()
        
        if self.website_entry.get().strip():
            data['website'] = self.website_entry.get().strip()
        
        # Warunki handlowe
        try:
            payment_days = int(self.payment_days_entry.get() or '14')
            data['payment_days'] = payment_days
        except ValueError:
            raise ValueError("Termin płatności musi być liczbą")
        
        try:
            discount = float(self.discount_entry.get() or '0')
            data['discount_percent'] = discount
        except ValueError:
            raise ValueError("Rabat musi być liczbą")
        
        credit_limit = self.credit_limit_entry.get().strip()
        if credit_limit:
            try:
                data['credit_limit'] = float(credit_limit.replace(',', '.'))
            except ValueError:
                raise ValueError("Limit kredytowy musi być liczbą")
        
        data['price_list'] = self.price_list_var.get()
        
        # Kategoria i tagi
        if self.category_entry.get().strip():
            data['category'] = self.category_entry.get().strip()
        
        tags_str = self.tags_entry.get().strip()
        if tags_str:
            data['tags'] = [t.strip() for t in tags_str.split(',') if t.strip()]
        
        # Notatki
        notes = self.notes_text.get("1.0", "end").strip()
        if notes:
            data['notes'] = notes
        
        return data
    
    def _save(self):
        """Zapisz klienta"""
        try:
            data = self._collect_data()
            
            if self.is_edit_mode:
                # Aktualizacja
                self.result = self.service.update(
                    self.customer['id'],
                    data,
                    expected_version=self.customer.get('version')
                )
                messagebox.showinfo("Sukces", "Klient został zaktualizowany")
            else:
                # Tworzenie
                self.result = self.service.create(data)
                messagebox.showinfo("Sukces", f"Klient {self.result['code']} został utworzony")
            
            self.destroy()
            
        except ValueError as e:
            messagebox.showerror("Błąd walidacji", str(e))
        except Exception as e:
            logger.error(f"[CustomerEditDialog] Save failed: {e}")
            messagebox.showerror("Błąd", f"Nie udało się zapisać:\n{e}")
