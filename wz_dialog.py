#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WZ Dialog
Dialog do generowania dokumentów wydania zewnętrznego (WZ)
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
from datetime import datetime, date
import os

from wz_generator import WZGenerator, WZData, WZItem


class WZGeneratorDialog(ctk.CTkToplevel):
    """Dialog generowania dokumentu WZ dla zamówienia"""

    def __init__(self, parent, db_client, order_id: str):
        super().__init__(parent)

        self.db_client = db_client
        self.order_id = order_id
        self.wz_generator = WZGenerator(db_client)

        self.title("Generowanie dokumentu WZ")
        self.geometry("900x700")

        self.transient(parent)
        self.grab_set()

        # Załaduj dane zamówienia
        self.wz_data = self.wz_generator.get_order_data_for_wz(order_id)

        if not self.wz_data:
            messagebox.showerror("Błąd", "Nie udało się pobrać danych zamówienia")
            self.destroy()
            return

        self.setup_ui()

        # Wyśrodkuj okno
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 450
        y = (self.winfo_screenheight() // 2) - 350
        self.geometry(f"+{x}+{y}")

    def setup_ui(self):
        """Tworzy interfejs dialogu"""

        # Main scrollable frame
        main_frame = ctk.CTkScrollableFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Nagłówek
        header_frame = ctk.CTkFrame(main_frame)
        header_frame.pack(fill="x", pady=5)

        ctk.CTkLabel(
            header_frame,
            text="📦 Generowanie dokumentu WZ",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left", padx=10)

        # Informacje podstawowe
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            info_frame,
            text="Informacje podstawowe",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, pady=10, sticky="w", padx=10)

        # Nr WZ
        ctk.CTkLabel(info_frame, text="Nr WZ:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.wz_number_label = ctk.CTkLabel(
            info_frame,
            text=self.wz_data.wz_number,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.wz_number_label.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        # Zamówienie
        ctk.CTkLabel(info_frame, text="Zamówienie:").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        ctk.CTkLabel(info_frame, text=self.wz_data.process_no).grid(
            row=2, column=1, padx=10, pady=5, sticky="w"
        )

        # Data wystawienia
        ctk.CTkLabel(info_frame, text="Data wystawienia:").grid(
            row=3, column=0, padx=10, pady=5, sticky="e"
        )
        self.issue_date_entry = ctk.CTkEntry(info_frame, width=150)
        self.issue_date_entry.insert(0, self.wz_data.issue_date.strftime('%Y-%m-%d'))
        self.issue_date_entry.grid(row=3, column=1, padx=10, pady=5, sticky="w")

        # Dane odbiorcy
        recipient_frame = ctk.CTkFrame(main_frame)
        recipient_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            recipient_frame,
            text="Dane odbiorcy",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, pady=10, sticky="w", padx=10)

        # Nazwa odbiorcy
        ctk.CTkLabel(recipient_frame, text="Nazwa:").grid(
            row=1, column=0, padx=10, pady=5, sticky="e"
        )
        self.recipient_name_entry = ctk.CTkEntry(recipient_frame, width=400)
        self.recipient_name_entry.insert(0, self.wz_data.recipient_name)
        self.recipient_name_entry.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        # Adres
        ctk.CTkLabel(recipient_frame, text="Adres:").grid(
            row=2, column=0, padx=10, pady=5, sticky="e"
        )
        self.recipient_address_entry = ctk.CTkEntry(recipient_frame, width=400)
        self.recipient_address_entry.insert(0, self.wz_data.recipient_address)
        self.recipient_address_entry.grid(row=2, column=1, padx=10, pady=5, sticky="w")

        # Miasto i kod
        city_frame = ctk.CTkFrame(recipient_frame)
        city_frame.grid(row=3, column=1, padx=10, pady=5, sticky="w")

        self.recipient_postal_entry = ctk.CTkEntry(city_frame, width=100, placeholder_text="Kod")
        self.recipient_postal_entry.insert(0, self.wz_data.recipient_postal_code)
        self.recipient_postal_entry.pack(side="left", padx=5)

        self.recipient_city_entry = ctk.CTkEntry(city_frame, width=285, placeholder_text="Miasto")
        self.recipient_city_entry.insert(0, self.wz_data.recipient_city)
        self.recipient_city_entry.pack(side="left")

        # NIP
        ctk.CTkLabel(recipient_frame, text="NIP:").grid(
            row=4, column=0, padx=10, pady=5, sticky="e"
        )
        self.recipient_nip_entry = ctk.CTkEntry(recipient_frame, width=200)
        self.recipient_nip_entry.insert(0, self.wz_data.recipient_nip)
        self.recipient_nip_entry.grid(row=4, column=1, padx=10, pady=5, sticky="w")

        # Osoba kontaktowa
        ctk.CTkLabel(recipient_frame, text="Osoba kontaktowa:").grid(
            row=5, column=0, padx=10, pady=5, sticky="e"
        )
        self.recipient_contact_entry = ctk.CTkEntry(recipient_frame, width=300)
        self.recipient_contact_entry.insert(0, self.wz_data.recipient_contact_person)
        self.recipient_contact_entry.grid(row=5, column=1, padx=10, pady=5, sticky="w")

        # Pozycje WZ
        items_frame = ctk.CTkFrame(main_frame)
        items_frame.pack(fill="both", expand=True, pady=10)

        ctk.CTkLabel(
            items_frame,
            text=f"Pozycje WZ ({len(self.wz_data.items)} pozycji)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)

        # Lista pozycji (read-only)
        from tkinter import ttk

        self.items_tree = ttk.Treeview(
            items_frame,
            columns=('lp', 'name', 'qty', 'unit', 'notes'),
            show='headings',
            height=8
        )

        self.items_tree.heading('lp', text='Lp.')
        self.items_tree.heading('name', text='Nazwa')
        self.items_tree.heading('qty', text='Ilość')
        self.items_tree.heading('unit', text='Jedn.')
        self.items_tree.heading('notes', text='Uwagi')

        self.items_tree.column('lp', width=50)
        self.items_tree.column('name', width=300)
        self.items_tree.column('qty', width=80)
        self.items_tree.column('unit', width=80)
        self.items_tree.column('notes', width=200)

        # Dodaj pozycje
        for item in self.wz_data.items:
            self.items_tree.insert('', 'end', values=(
                item.lp,
                item.name,
                item.quantity,
                item.unit,
                item.notes
            ))

        self.items_tree.pack(fill="both", expand=True, padx=10, pady=5)

        # Uwagi
        notes_frame = ctk.CTkFrame(main_frame)
        notes_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(notes_frame, text="Uwagi:").pack(anchor="w", padx=10, pady=5)
        self.notes_text = ctk.CTkTextbox(notes_frame, height=80)
        self.notes_text.insert("1.0", self.wz_data.notes)
        self.notes_text.pack(fill="x", padx=10, pady=5)

        # Transport
        ctk.CTkLabel(notes_frame, text="Informacje o transporcie:").pack(
            anchor="w", padx=10, pady=5
        )
        self.transport_text = ctk.CTkTextbox(notes_frame, height=60)
        self.transport_text.insert("1.0", self.wz_data.transport_info)
        self.transport_text.pack(fill="x", padx=10, pady=5)

        # Przyciski generowania
        btn_frame = ctk.CTkFrame(main_frame)
        btn_frame.pack(fill="x", pady=20)

        ctk.CTkLabel(
            btn_frame,
            text="Wybierz format dokumentu do wygenerowania:",
            font=ctk.CTkFont(size=12)
        ).pack(pady=10)

        buttons_grid = ctk.CTkFrame(btn_frame)
        buttons_grid.pack()

        ctk.CTkButton(
            buttons_grid,
            text="📄 Generuj PDF",
            width=180,
            height=45,
            command=lambda: self.generate_document('pdf'),
            fg_color="#DC143C"
        ).grid(row=0, column=0, padx=10, pady=5)

        ctk.CTkButton(
            buttons_grid,
            text="📝 Generuj Word",
            width=180,
            height=45,
            command=lambda: self.generate_document('word'),
            fg_color="#2B579A"
        ).grid(row=0, column=1, padx=10, pady=5)

        ctk.CTkButton(
            buttons_grid,
            text="📊 Generuj Excel",
            width=180,
            height=45,
            command=lambda: self.generate_document('excel'),
            fg_color="#217346"
        ).grid(row=0, column=2, padx=10, pady=5)

        ctk.CTkButton(
            buttons_grid,
            text="📦 Generuj wszystkie",
            width=180,
            height=45,
            command=lambda: self.generate_document('all'),
            fg_color="#4CAF50",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=1, column=0, columnspan=3, padx=10, pady=10)

        # Przycisk zamknij
        ctk.CTkButton(
            btn_frame,
            text="Zamknij",
            width=150,
            command=self.destroy
        ).pack(pady=10)

    def get_wz_data_from_form(self) -> WZData:
        """Pobiera dane WZ z formularza"""
        # Aktualizuj dane z formularza
        self.wz_data.recipient_name = self.recipient_name_entry.get()
        self.wz_data.recipient_address = self.recipient_address_entry.get()
        self.wz_data.recipient_city = self.recipient_city_entry.get()
        self.wz_data.recipient_postal_code = self.recipient_postal_entry.get()
        self.wz_data.recipient_nip = self.recipient_nip_entry.get()
        self.wz_data.recipient_contact_person = self.recipient_contact_entry.get()
        self.wz_data.notes = self.notes_text.get("1.0", "end-1c")
        self.wz_data.transport_info = self.transport_text.get("1.0", "end-1c")

        # Parsuj datę
        try:
            date_str = self.issue_date_entry.get()
            self.wz_data.issue_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            self.wz_data.issue_date = date.today()

        return self.wz_data

    def generate_document(self, format_type: str):
        """
        Generuje dokument WZ w wybranym formacie

        Args:
            format_type: 'pdf', 'word', 'excel' lub 'all'
        """
        # Pobierz dane z formularza
        wz_data = self.get_wz_data_from_form()

        # Walidacja
        if not wz_data.recipient_name:
            messagebox.showwarning("Uwaga", "Podaj nazwę odbiorcy")
            return

        # Dialog wyboru lokalizacji
        if format_type == 'all':
            folder = filedialog.askdirectory(title="Wybierz folder do zapisania plików")
            if not folder:
                return

            base_name = f"WZ_{wz_data.wz_number.replace('/', '_')}"

            pdf_path = os.path.join(folder, f"{base_name}.pdf")
            word_path = os.path.join(folder, f"{base_name}.docx")
            excel_path = os.path.join(folder, f"{base_name}.xlsx")

            # Generuj wszystkie formaty
            success_count = 0

            if self.wz_generator.generate_pdf(wz_data, pdf_path):
                success_count += 1

            if self.wz_generator.generate_word(wz_data, word_path):
                success_count += 1

            if self.wz_generator.generate_excel(wz_data, excel_path):
                success_count += 1

            if success_count > 0:
                # Zapisz do bazy
                self.wz_generator.save_wz_to_db(wz_data)

                messagebox.showinfo(
                    "Sukces",
                    f"Wygenerowano {success_count}/3 dokumentów w folderze:\n{folder}"
                )
            else:
                messagebox.showerror("Błąd", "Nie udało się wygenerować żadnego dokumentu")

        else:
            # Generuj pojedynczy format
            extensions = {
                'pdf': '.pdf',
                'word': '.docx',
                'excel': '.xlsx'
            }

            file_path = filedialog.asksaveasfilename(
                defaultextension=extensions[format_type],
                initialfile=f"WZ_{wz_data.wz_number.replace('/', '_')}{extensions[format_type]}",
                filetypes=[
                    (format_type.upper(), f"*{extensions[format_type]}"),
                    ("Wszystkie pliki", "*.*")
                ],
                title=f"Zapisz dokument WZ jako {format_type.upper()}"
            )

            if not file_path:
                return

            # Generuj dokument
            success = False
            if format_type == 'pdf':
                success = self.wz_generator.generate_pdf(wz_data, file_path)
            elif format_type == 'word':
                success = self.wz_generator.generate_word(wz_data, file_path)
            elif format_type == 'excel':
                success = self.wz_generator.generate_excel(wz_data, file_path)

            if success:
                # Zapisz do bazy
                self.wz_generator.save_wz_to_db(wz_data)

                # Pytanie czy otworzyć dokument
                if messagebox.askyesno(
                    "Sukces",
                    f"Dokument WZ został wygenerowany:\n{file_path}\n\nCzy otworzyć dokument?"
                ):
                    import platform
                    import subprocess

                    if platform.system() == 'Windows':
                        os.startfile(file_path)
                    elif platform.system() == 'Darwin':  # macOS
                        subprocess.call(['open', file_path])
                    else:  # Linux
                        subprocess.call(['xdg-open', file_path])
            else:
                messagebox.showerror("Błąd", "Nie udało się wygenerować dokumentu")


# Przykład użycia
if __name__ == '__main__':
    print("WZDialog - Dialog generowania dokumentów WZ")
    print("=" * 50)
    print("Użycie:")
    print("""
    # W menu zamówień:
    dialog = WZGeneratorDialog(self, self.db.client, order_id)
    dialog.focus()
    """)
