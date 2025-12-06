"""
Report Generation Dialog
========================
Dialog do wyboru formatu i generowania raportów.
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
from pathlib import Path
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable
import threading

logger = logging.getLogger(__name__)


class Theme:
    """Kolory"""
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


class ReportDialog(ctk.CTkToplevel):
    """Dialog generowania raportów"""
    
    def __init__(
        self, 
        parent,
        quotation_report: 'QuotationReport',
        on_complete: Callable[[str], None] = None
    ):
        super().__init__(parent)
        
        self.quotation_report = quotation_report
        self.on_complete = on_complete
        
        # Konfiguracja okna
        self.title("📄 Generuj raport")
        self.geometry("500x600")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)
        
        # Wycentruj
        self.transient(parent)
        self.grab_set()
        
        self._setup_ui()
        
        # Focus
        self.lift()
        self.focus_force()
    
    def _setup_ui(self):
        """Buduj interfejs"""
        # Nagłówek
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        
        ctk.CTkLabel(
            header,
            text="📄 GENERUJ RAPORT",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        ).pack(pady=15)
        
        # Główna zawartość
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=10)
        
        # === SEKCJA: METADANE ===
        self._add_section(content, "📋 Dane wyceny")
        
        # Nr wyceny
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=5)
        ctk.CTkLabel(row, text="Nr wyceny:", width=120, anchor="w").pack(side="left")
        self.quotation_id_entry = ctk.CTkEntry(row, width=200, placeholder_text="AUTO")
        self.quotation_id_entry.pack(side="left")
        
        # Ustal domyślny numer
        default_id = f"WYC/{datetime.now().strftime('%Y%m%d')}/{datetime.now().strftime('%H%M')}"
        self.quotation_id_entry.insert(0, default_id)
        
        # Data ważności
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=5)
        ctk.CTkLabel(row, text="Ważna do:", width=120, anchor="w").pack(side="left")
        self.valid_days_entry = ctk.CTkEntry(row, width=80, placeholder_text="14")
        self.valid_days_entry.insert(0, "14")
        self.valid_days_entry.pack(side="left")
        ctk.CTkLabel(row, text="dni", text_color=Theme.TEXT_MUTED).pack(side="left", padx=5)
        
        # === SEKCJA: KLIENT ===
        self._add_section(content, "👤 Dane klienta")
        
        # Firma
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Firma:", width=120, anchor="w").pack(side="left")
        self.customer_company = ctk.CTkEntry(row, width=280)
        self.customer_company.pack(side="left")
        
        # Osoba
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Osoba:", width=120, anchor="w").pack(side="left")
        self.customer_name = ctk.CTkEntry(row, width=280)
        self.customer_name.pack(side="left")
        
        # Email
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Email:", width=120, anchor="w").pack(side="left")
        self.customer_email = ctk.CTkEntry(row, width=280)
        self.customer_email.pack(side="left")
        
        # Telefon
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Telefon:", width=120, anchor="w").pack(side="left")
        self.customer_phone = ctk.CTkEntry(row, width=280)
        self.customer_phone.pack(side="left")
        
        # NIP
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="NIP:", width=120, anchor="w").pack(side="left")
        self.customer_nip = ctk.CTkEntry(row, width=280)
        self.customer_nip.pack(side="left")
        
        # Wczytaj dane klienta jeśli są
        if self.quotation_report.customer_company:
            self.customer_company.insert(0, self.quotation_report.customer_company)
        if self.quotation_report.customer_name:
            self.customer_name.insert(0, self.quotation_report.customer_name)
        if self.quotation_report.customer_email:
            self.customer_email.insert(0, self.quotation_report.customer_email)
        if self.quotation_report.customer_phone:
            self.customer_phone.insert(0, self.quotation_report.customer_phone)
        if self.quotation_report.customer_nip:
            self.customer_nip.insert(0, self.quotation_report.customer_nip)
        
        # === SEKCJA: FORMAT ===
        self._add_section(content, "📁 Format raportu")
        
        # Checkboxy formatów
        self.format_pdf_var = ctk.BooleanVar(value=True)
        self.format_excel_var = ctk.BooleanVar(value=True)
        self.format_dxf_var = ctk.BooleanVar(value=False)
        
        formats_frame = ctk.CTkFrame(content, fg_color="transparent")
        formats_frame.pack(fill="x", pady=5)
        
        ctk.CTkCheckBox(
            formats_frame, text="📄 PDF (raport dla klienta)",
            variable=self.format_pdf_var,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=2)
        
        ctk.CTkCheckBox(
            formats_frame, text="📊 Excel (szczegółowe dane)",
            variable=self.format_excel_var,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=2)
        
        ctk.CTkCheckBox(
            formats_frame, text="📐 DXF (pliki dla CNC)",
            variable=self.format_dxf_var,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=2)
        
        # Info o dostępności
        self._check_libraries(formats_frame)
        
        # === SEKCJA: UWAGI ===
        self._add_section(content, "📝 Uwagi")
        
        self.notes_text = ctk.CTkTextbox(content, height=80)
        self.notes_text.pack(fill="x", pady=5)
        
        # === PRZYCISKI ===
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkButton(
            buttons_frame,
            text="❌ Anuluj",
            width=120,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_CARD,
            command=self.destroy
        ).pack(side="left")
        
        self.btn_generate = ctk.CTkButton(
            buttons_frame,
            text="✅ Generuj",
            width=150,
            fg_color=Theme.ACCENT_SUCCESS,
            hover_color="#1ea54d",
            command=self._generate
        )
        self.btn_generate.pack(side="right")
        
        # Status
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_MUTED
        )
        self.status_label.pack(pady=(0, 10))
    
    def _add_section(self, parent, title: str):
        """Dodaj nagłówek sekcji"""
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        ).pack(anchor="w", pady=(15, 5))
    
    def _check_libraries(self, parent):
        """Sprawdź dostępność bibliotek"""
        missing = []
        
        try:
            import reportlab
        except ImportError:
            missing.append("reportlab (PDF)")
            self.format_pdf_var.set(False)
        
        try:
            import openpyxl
        except ImportError:
            missing.append("openpyxl (Excel)")
            self.format_excel_var.set(False)
        
        try:
            import ezdxf
        except ImportError:
            missing.append("ezdxf (DXF)")
            self.format_dxf_var.set(False)
        
        if missing:
            ctk.CTkLabel(
                parent,
                text=f"⚠️ Brak: {', '.join(missing)}",
                font=ctk.CTkFont(size=10),
                text_color=Theme.ACCENT_WARNING
            ).pack(anchor="w", pady=2)
    
    def _generate(self):
        """Generuj raporty"""
        # Walidacja
        if not any([self.format_pdf_var.get(), 
                    self.format_excel_var.get(), 
                    self.format_dxf_var.get()]):
            messagebox.showwarning("Uwaga", "Wybierz przynajmniej jeden format")
            return
        
        # Wybierz katalog
        output_dir = filedialog.askdirectory(
            title="Wybierz katalog dla raportów"
        )
        
        if not output_dir:
            return
        
        # Aktualizuj dane raportu
        self._update_report_data()
        
        # Generuj w tle
        self.btn_generate.configure(state="disabled")
        self.status_label.configure(text="Generowanie raportów...")
        
        def generate():
            try:
                generated = []
                errors = []
                
                base_name = self.quotation_report.quotation_id.replace("/", "_").replace(" ", "_")
                
                # PDF
                if self.format_pdf_var.get():
                    try:
                        from quotations.reports.pdf_report import generate_pdf_report
                        
                        pdf_path = Path(output_dir) / f"{base_name}.pdf"
                        if generate_pdf_report(self.quotation_report, str(pdf_path)):
                            generated.append(f"PDF: {pdf_path.name}")
                        else:
                            errors.append("PDF: błąd generowania")
                    except ImportError:
                        errors.append("PDF: brak biblioteki reportlab")
                    except Exception as e:
                        errors.append(f"PDF: {e}")
                
                # Excel
                if self.format_excel_var.get():
                    try:
                        from quotations.reports.excel_report import generate_excel_report
                        
                        xlsx_path = Path(output_dir) / f"{base_name}.xlsx"
                        if generate_excel_report(self.quotation_report, str(xlsx_path)):
                            generated.append(f"Excel: {xlsx_path.name}")
                        else:
                            errors.append("Excel: błąd generowania")
                    except ImportError:
                        errors.append("Excel: brak biblioteki openpyxl")
                    except Exception as e:
                        errors.append(f"Excel: {e}")
                
                # DXF
                if self.format_dxf_var.get():
                    try:
                        from quotations.reports.dxf_export import export_nesting_to_dxf
                        
                        dxf_dir = Path(output_dir) / "dxf"
                        files = export_nesting_to_dxf(
                            self.quotation_report, 
                            str(dxf_dir),
                            base_name
                        )
                        if files:
                            generated.append(f"DXF: {len(files)} plików")
                        else:
                            errors.append("DXF: brak danych nestingu")
                    except ImportError:
                        errors.append("DXF: brak biblioteki ezdxf")
                    except Exception as e:
                        errors.append(f"DXF: {e}")
                
                # Pokaż wynik
                self.after(0, lambda: self._show_result(generated, errors, output_dir))
                
            except Exception as e:
                logger.error(f"Report generation error: {e}")
                import traceback
                traceback.print_exc()
                self.after(0, lambda: messagebox.showerror("Błąd", f"Błąd generowania:\n{e}"))
            
            finally:
                self.after(0, lambda: self.btn_generate.configure(state="normal"))
        
        threading.Thread(target=generate, daemon=True).start()
    
    def _update_report_data(self):
        """Aktualizuj dane raportu z formularza"""
        # Metadane
        self.quotation_report.quotation_id = self.quotation_id_entry.get() or "DRAFT"
        
        try:
            days = int(self.valid_days_entry.get())
            self.quotation_report.valid_until = datetime.now() + timedelta(days=days)
        except:
            self.quotation_report.valid_until = datetime.now() + timedelta(days=14)
        
        # Klient
        self.quotation_report.customer_company = self.customer_company.get()
        self.quotation_report.customer_name = self.customer_name.get()
        self.quotation_report.customer_email = self.customer_email.get()
        self.quotation_report.customer_phone = self.customer_phone.get()
        self.quotation_report.customer_nip = self.customer_nip.get()
        
        # Uwagi
        self.quotation_report.notes = self.notes_text.get("1.0", "end-1c")
    
    def _show_result(self, generated: list, errors: list, output_dir: str):
        """Pokaż wynik generowania"""
        self.status_label.configure(text="")
        
        if generated:
            msg = "✅ Wygenerowano:\n" + "\n".join(f"  • {g}" for g in generated)
            
            if errors:
                msg += "\n\n⚠️ Błędy:\n" + "\n".join(f"  • {e}" for e in errors)
            
            msg += f"\n\nLokalizacja: {output_dir}"
            
            messagebox.showinfo("Sukces", msg)
            
            if self.on_complete:
                self.on_complete(output_dir)
            
            self.destroy()
        else:
            messagebox.showerror(
                "Błąd",
                "Nie udało się wygenerować żadnego raportu:\n" + 
                "\n".join(f"  • {e}" for e in errors)
            )


def show_report_dialog(parent, quotation_report: 'QuotationReport', on_complete=None):
    """Pokaż dialog generowania raportów"""
    dialog = ReportDialog(parent, quotation_report, on_complete)
    return dialog
