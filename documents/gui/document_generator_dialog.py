"""
Document Generator Dialog
=========================
Dialog do wyboru i generowania dokumentow dla zamowien/wycen.
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
import logging
from typing import Optional, Callable, List, Dict, Any
from pathlib import Path
import webbrowser
import tempfile

logger = logging.getLogger(__name__)


class DocumentGeneratorDialog(ctk.CTkToplevel):
    """
    Dialog do generowania dokumentow.

    Umozliwia:
    - Wybor typu dokumentu (WZ, CMR, Potwierdzenie zamowienia, etc.)
    - Podglad dokumentu przed generowaniem
    - Eksport do PDF
    - Zapis lokalny lub upload do storage
    """

    # Typy dokumentow dostepne dla zamowien
    ORDER_DOCUMENT_TYPES = [
        ("WZ (Wydanie Zewnetrzne)", "WZ"),
        ("Potwierdzenie zamowienia", "ORDER_CONFIRMATION"),
        ("Lista pakunkowa", "PACKING_LIST"),
        ("CMR", "CMR"),
        ("Raport kosztowy", "COST_REPORT"),
    ]

    # Typy dokumentow dostepne dla wycen
    QUOTATION_DOCUMENT_TYPES = [
        ("Oferta handlowa", "QUOTATION"),
        ("Raport kosztowy", "COST_REPORT"),
    ]

    def __init__(
        self,
        parent,
        entity_id: str,
        entity_type: str = "order",  # "order" lub "quotation"
        entity_name: str = "",
        on_generate: Optional[Callable] = None,
        **kwargs
    ):
        """
        Inicjalizacja dialogu.

        Args:
            parent: Okno rodzica
            entity_id: ID zamowienia/wyceny
            entity_type: Typ encji ("order" lub "quotation")
            entity_name: Nazwa/numer do wyswietlenia
            on_generate: Callback po wygenerowaniu dokumentu
        """
        super().__init__(parent, **kwargs)

        self.entity_id = entity_id
        self.entity_type = entity_type
        self.entity_name = entity_name
        self.on_generate = on_generate

        self._doc_service = None
        self._selected_doc_type = None
        self._preview_html = None

        # Konfiguracja okna
        self.title(f"Generuj dokument - {entity_name}")
        self.geometry("700x550")
        self.resizable(False, False)

        # Centruj okno
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

        self._setup_ui()

        # Modal
        self.transient(parent)
        self.grab_set()

    def _setup_ui(self):
        """Buduj interfejs uzytkownika"""
        # Naglowek
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="Generowanie dokumentu",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text=f"Dla: {self.entity_name}",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(anchor="w")

        # Separator
        ctk.CTkFrame(self, height=2, fg_color="gray70").pack(fill="x", padx=20, pady=10)

        # Wybor typu dokumentu
        type_frame = ctk.CTkFrame(self, fg_color="transparent")
        type_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            type_frame,
            text="Typ dokumentu:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w")

        # Radio buttons dla typow dokumentow
        self._doc_type_var = ctk.StringVar(value="")

        doc_types = (
            self.ORDER_DOCUMENT_TYPES
            if self.entity_type == "order"
            else self.QUOTATION_DOCUMENT_TYPES
        )

        radio_frame = ctk.CTkFrame(type_frame, fg_color="transparent")
        radio_frame.pack(fill="x", pady=10)

        for label, value in doc_types:
            rb = ctk.CTkRadioButton(
                radio_frame,
                text=label,
                variable=self._doc_type_var,
                value=value,
                command=self._on_type_selected
            )
            rb.pack(anchor="w", pady=3)

        # Opcje dodatkowe
        options_frame = ctk.CTkFrame(self, fg_color="transparent")
        options_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            options_frame,
            text="Opcje:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w")

        self._include_thumbnails_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            options_frame,
            text="Dolacz podglady detali (thumbnails)",
            variable=self._include_thumbnails_var
        ).pack(anchor="w", pady=3)

        self._group_by_material_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            options_frame,
            text="Grupuj po materiale",
            variable=self._group_by_material_var
        ).pack(anchor="w", pady=3)

        # Opis wybranego typu
        self._description_frame = ctk.CTkFrame(self, fg_color="#f0f0f0", corner_radius=8)
        self._description_frame.pack(fill="x", padx=20, pady=10)

        self._description_label = ctk.CTkLabel(
            self._description_frame,
            text="Wybierz typ dokumentu powyzej",
            font=ctk.CTkFont(size=11),
            text_color="gray40",
            wraplength=620,
            justify="left"
        )
        self._description_label.pack(padx=15, pady=15, anchor="w")

        # Informacja o thumbnails
        info_frame = ctk.CTkFrame(self, fg_color="#fff3cd", corner_radius=8)
        info_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            info_frame,
            text="Wszystkie dokumenty zawieraja podglady detali (thumbnails) dla latwej identyfikacji wizualnej.",
            font=ctk.CTkFont(size=11),
            text_color="#856404",
            wraplength=620,
            justify="left"
        ).pack(padx=15, pady=10, anchor="w")

        # Przyciski
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkButton(
            button_frame,
            text="Anuluj",
            width=100,
            fg_color="gray70",
            hover_color="gray60",
            command=self.destroy
        ).pack(side="left")

        self._preview_btn = ctk.CTkButton(
            button_frame,
            text="Podglad",
            width=100,
            fg_color="#6366f1",
            hover_color="#4f46e5",
            command=self._preview_document,
            state="disabled"
        )
        self._preview_btn.pack(side="right", padx=(10, 0))

        self._generate_btn = ctk.CTkButton(
            button_frame,
            text="Generuj PDF",
            width=120,
            fg_color="#059669",
            hover_color="#047857",
            command=self._generate_document,
            state="disabled"
        )
        self._generate_btn.pack(side="right")

    def _on_type_selected(self):
        """Obsluz wybor typu dokumentu"""
        doc_type = self._doc_type_var.get()
        self._selected_doc_type = doc_type

        # Wlacz przyciski
        self._preview_btn.configure(state="normal")
        self._generate_btn.configure(state="normal")

        # Aktualizuj opis
        descriptions = {
            "WZ": "Wydanie Zewnetrzne - dokument potwierdzajacy wydanie towaru z magazynu. "
                  "Zawiera liste detali z podgladami, materialami i wagami.",
            "ORDER_CONFIRMATION": "Potwierdzenie zamowienia - oficjalny dokument potwierdzajacy "
                                  "przyjecie zamowienia do realizacji z pelna specyfikacja i cenami.",
            "PACKING_LIST": "Lista pakunkowa - szczegolowa lista detali do pakowania/wysylki "
                           "z podgladami, wagami i informacjami o opakowaniach.",
            "CMR": "Miedzynarodowy list przewozowy CMR - dokument transportowy dla przewozow "
                   "miedzynarodowych zgodny z konwencja CMR.",
            "COST_REPORT": "Raport kosztowy - szczegolowa kalkulacja kosztow produkcji "
                          "z rozbiciem na material, ciecie, giecie i inne operacje.",
            "QUOTATION": "Oferta handlowa - profesjonalna wycena dla klienta z pelna "
                        "specyfikacja cenowa i warunkami realizacji."
        }

        self._description_label.configure(text=descriptions.get(doc_type, ""))

    def _get_document_service(self):
        """Pobierz instancje DocumentService"""
        if self._doc_service is None:
            try:
                from documents.service import create_document_service
                self._doc_service = create_document_service()
            except Exception as e:
                logger.error(f"Failed to create document service: {e}")
                messagebox.showerror(
                    "Blad",
                    f"Nie mozna utworzyc serwisu dokumentow:\n{e}"
                )
                return None
        return self._doc_service

    def _preview_document(self):
        """Pokaz podglad dokumentu w przegladarce"""
        if not self._selected_doc_type:
            messagebox.showwarning("Uwaga", "Wybierz typ dokumentu")
            return

        service = self._get_document_service()
        if not service:
            return

        try:
            from documents.constants import DocumentType
            doc_type = DocumentType(self._selected_doc_type)

            # Generuj podglad HTML
            result = service.generate_document(
                doc_type=doc_type,
                entity_id=self.entity_id,
                preview=True
            )

            if result.get('success'):
                html_content = result.get('html', '')

                # Zapisz do pliku tymczasowego
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.html',
                    delete=False,
                    encoding='utf-8'
                ) as f:
                    f.write(html_content)
                    temp_path = f.name

                # Otworz w przegladarce
                webbrowser.open(f'file://{temp_path}')

                self._preview_html = html_content
            else:
                error = result.get('error', 'Nieznany blad')
                messagebox.showerror("Blad podgladu", f"Nie mozna wygenerowac podgladu:\n{error}")

        except Exception as e:
            logger.error(f"Preview error: {e}")
            messagebox.showerror("Blad", f"Blad podczas generowania podgladu:\n{e}")

    def _generate_document(self):
        """Generuj dokument PDF"""
        if not self._selected_doc_type:
            messagebox.showwarning("Uwaga", "Wybierz typ dokumentu")
            return

        # Pytaj o lokalizacje zapisu
        default_filename = f"{self._selected_doc_type}_{self.entity_name}.pdf"
        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            initialfile=default_filename,
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            title="Zapisz dokument PDF"
        )

        if not file_path:
            return

        service = self._get_document_service()
        if not service:
            return

        try:
            from documents.constants import DocumentType
            doc_type = DocumentType(self._selected_doc_type)

            # Generuj dokument
            result = service.generate_document(
                doc_type=doc_type,
                entity_id=self.entity_id,
                preview=False
            )

            if result.get('success'):
                # Pobierz PDF i zapisz lokalnie
                doc_id = result.get('document_id')
                if doc_id:
                    pdf_bytes = service.download_document(doc_id)
                    if pdf_bytes:
                        with open(file_path, 'wb') as f:
                            f.write(pdf_bytes)

                        messagebox.showinfo(
                            "Sukces",
                            f"Dokument wygenerowany pomyslnie!\n\n"
                            f"Numer: {result.get('doc_number')}\n"
                            f"Zapisano: {file_path}"
                        )

                        # Callback
                        if self.on_generate:
                            self.on_generate(result)

                        # Zamknij dialog
                        self.destroy()
                    else:
                        messagebox.showwarning(
                            "Uwaga",
                            f"Dokument wygenerowany w storage, ale nie mozna pobrac lokalnie.\n"
                            f"Numer: {result.get('doc_number')}"
                        )
                else:
                    messagebox.showwarning("Uwaga", "Dokument wygenerowany, ale brak ID")
            else:
                error = result.get('error', 'Nieznany blad')
                messagebox.showerror("Blad", f"Nie mozna wygenerowac dokumentu:\n{error}")

        except Exception as e:
            logger.error(f"Document generation error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Blad", f"Blad podczas generowania dokumentu:\n{e}")


class QuickDocumentButton(ctk.CTkFrame):
    """
    Przycisk szybkiego generowania dokumentu.

    Moze byc uzyty w oknach zamowien/wycen do szybkiego dostepu
    do generowania dokumentow.
    """

    def __init__(
        self,
        parent,
        entity_id: str,
        entity_type: str = "order",
        entity_name: str = "",
        **kwargs
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.entity_id = entity_id
        self.entity_type = entity_type
        self.entity_name = entity_name

        self._setup_ui()

    def _setup_ui(self):
        """Buduj interfejs"""
        btn = ctk.CTkButton(
            self,
            text="Generuj dokument",
            width=140,
            height=32,
            fg_color="#6366f1",
            hover_color="#4f46e5",
            command=self._open_dialog
        )
        btn.pack()

    def _open_dialog(self):
        """Otworz dialog generowania dokumentu"""
        dialog = DocumentGeneratorDialog(
            self.winfo_toplevel(),
            entity_id=self.entity_id,
            entity_type=self.entity_type,
            entity_name=self.entity_name
        )
        dialog.focus()


def open_document_generator(
    parent,
    entity_id: str,
    entity_type: str = "order",
    entity_name: str = "",
    on_generate: Optional[Callable] = None
):
    """
    Funkcja pomocnicza do otwierania dialogu generowania dokumentow.

    Args:
        parent: Okno rodzica
        entity_id: ID zamowienia/wyceny
        entity_type: "order" lub "quotation"
        entity_name: Nazwa do wyswietlenia
        on_generate: Callback po wygenerowaniu

    Returns:
        DocumentGeneratorDialog instance
    """
    dialog = DocumentGeneratorDialog(
        parent,
        entity_id=entity_id,
        entity_type=entity_type,
        entity_name=entity_name,
        on_generate=on_generate
    )
    return dialog
