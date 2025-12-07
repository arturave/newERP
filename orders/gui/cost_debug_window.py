"""
Cost Debug Window - Okno GUI z logami obliczen kosztow
======================================================
Wyswietla na zywo logi z kalkulacji kosztow.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from typing import Optional
from datetime import datetime
import threading


class Theme:
    """Paleta kolorow"""
    BG_DARK = "#0f0f0f"
    BG_CARD = "#1a1a1a"
    BG_INPUT = "#2d2d2d"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_LOG = "#00ff00"  # Zielony terminal
    ACCENT_PRIMARY = "#8b5cf6"
    ACCENT_SUCCESS = "#22c55e"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_DANGER = "#ef4444"


class CostDebugWindow(ctk.CTkToplevel):
    """
    Okno wyswietlajace logi obliczen kosztow na zywo.

    Uzycie:
        from orders.cost_debug_logger import get_cost_debug_logger

        logger = get_cost_debug_logger()
        window = CostDebugWindow(parent)
        logger.register_callback(window.append_log)
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.title("Log Obliczen Kosztow")
        self.geometry("800x600")
        self.configure(fg_color=Theme.BG_DARK)

        # Wycentruj
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 800) // 2
        y = (self.winfo_screenheight() - 600) // 2
        self.geometry(f"+{x}+{y}")

        # Stan
        self._auto_scroll = ctk.BooleanVar(value=True)
        self._paused = ctk.BooleanVar(value=False)
        self._log_buffer: list = []
        self._update_scheduled = False

        self._setup_ui()
        self._connect_logger()

        # Focus - wymuszenie widoczności okna
        self.transient(parent)  # Powiąż z oknem rodzica
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)  # Na wierzchu
        self.after(100, lambda: self.attributes("-topmost", False))  # Potem normalne

    def _setup_ui(self):
        """Zbuduj interfejs"""
        # === HEADER ===
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50)
        header.pack(fill="x", padx=10, pady=(10, 5))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="Log Obliczen Kosztow",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left", padx=15, pady=10)

        # Status
        self.status_label = ctk.CTkLabel(
            header,
            text="Aktywny",
            font=ctk.CTkFont(size=11),
            text_color=Theme.ACCENT_SUCCESS
        )
        self.status_label.pack(side="right", padx=15)

        # === TOOLBAR ===
        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=40)
        toolbar.pack(fill="x", padx=10, pady=5)

        # Przyciski
        btn_clear = ctk.CTkButton(
            toolbar, text="Wyczysc", width=80,
            fg_color=Theme.BG_INPUT, hover_color=Theme.BG_CARD,
            command=self._clear_log
        )
        btn_clear.pack(side="left", padx=2)

        btn_export = ctk.CTkButton(
            toolbar, text="Eksport", width=80,
            fg_color=Theme.BG_INPUT, hover_color=Theme.BG_CARD,
            command=self._export_log
        )
        btn_export.pack(side="left", padx=2)

        self.btn_pause = ctk.CTkButton(
            toolbar, text="Pauza", width=80,
            fg_color=Theme.ACCENT_WARNING, hover_color="#d97706",
            command=self._toggle_pause
        )
        self.btn_pause.pack(side="left", padx=2)

        btn_open_file = ctk.CTkButton(
            toolbar, text="Otworz plik", width=100,
            fg_color=Theme.BG_INPUT, hover_color=Theme.BG_CARD,
            command=self._open_log_file
        )
        btn_open_file.pack(side="left", padx=10)

        # Auto-scroll checkbox
        auto_scroll_cb = ctk.CTkCheckBox(
            toolbar, text="Auto-scroll",
            variable=self._auto_scroll,
            font=ctk.CTkFont(size=11),
            checkbox_width=18, checkbox_height=18
        )
        auto_scroll_cb.pack(side="right", padx=10)

        # === LOG AREA ===
        log_frame = ctk.CTkFrame(self, fg_color=Theme.BG_INPUT)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0a0a0a",
            text_color=Theme.TEXT_LOG,
            wrap="none"
        )
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

        # Tekst poczatkowy
        self._append_initial_message()

        # === FOOTER ===
        footer = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=30)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        footer.pack_propagate(False)

        self.lines_label = ctk.CTkLabel(
            footer,
            text="Linii: 0",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY
        )
        self.lines_label.pack(side="left", padx=10, pady=5)

        self.file_label = ctk.CTkLabel(
            footer,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_SECONDARY
        )
        self.file_label.pack(side="right", padx=10, pady=5)

    def _append_initial_message(self):
        """Dodaj poczatkowa wiadomosc"""
        msg = (
            "=" * 60 + "\n"
            "  Cost Debug Logger - NewERP\n"
            f"  Uruchomiono: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "  \n"
            "  Logi obliczen kosztow beda wyswietlane ponizej.\n"
            "  Wczytaj pliki DXF aby zobaczyc obliczenia.\n"
            "=" * 60 + "\n\n"
        )
        self.log_text.insert("end", msg)

    def _connect_logger(self):
        """Polacz z CostDebugLogger"""
        try:
            from orders.cost_debug_logger import get_cost_debug_logger

            logger = get_cost_debug_logger()
            logger.register_callback(self.append_log)

            # Pokaz sciezke pliku
            log_path = logger.get_log_file_path()
            self.file_label.configure(text=f"Plik: {log_path}")

        except ImportError as e:
            self.append_log(f"[ERROR] Nie mozna zaimportowac loggera: {e}")

    def append_log(self, message: str):
        """
        Dodaj wiadomosc do logu.
        Bezpieczne do wywolania z dowolnego watku.
        """
        self._log_buffer.append(message)

        # Zaplanuj aktualizacje GUI (batching)
        if not self._update_scheduled:
            self._update_scheduled = True
            self.after(50, self._flush_buffer)

    def _flush_buffer(self):
        """Oproznij bufor i zaktualizuj GUI"""
        self._update_scheduled = False

        if not self._log_buffer:
            return

        # Pobierz wszystkie wiadomosci
        messages = self._log_buffer.copy()
        self._log_buffer.clear()

        # Dodaj do textbox
        for msg in messages:
            timestamp = datetime.now().strftime("%H:%M:%S")
            line = f"{timestamp} {msg}\n"
            self.log_text.insert("end", line)

        # Auto-scroll
        if self._auto_scroll.get():
            self.log_text.see("end")

        # Aktualizuj licznik linii
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        self.lines_label.configure(text=f"Linii: {line_count}")

    def _clear_log(self):
        """Wyczysc log"""
        self.log_text.delete("1.0", "end")
        self._append_initial_message()
        self.lines_label.configure(text="Linii: 0")

    def _toggle_pause(self):
        """Przelacz pauze"""
        try:
            from orders.cost_debug_logger import get_cost_debug_logger
            logger = get_cost_debug_logger()

            if self._paused.get():
                self._paused.set(False)
                logger.resume()
                self.btn_pause.configure(text="Pauza", fg_color=Theme.ACCENT_WARNING)
                self.status_label.configure(text="Aktywny", text_color=Theme.ACCENT_SUCCESS)
            else:
                self._paused.set(True)
                logger.pause()
                self.btn_pause.configure(text="Wznow", fg_color=Theme.ACCENT_SUCCESS)
                self.status_label.configure(text="Wstrzymany", text_color=Theme.ACCENT_WARNING)

        except ImportError:
            pass

    def _export_log(self):
        """Eksportuj log do pliku"""
        filepath = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            initialfile=f"cost_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        if filepath:
            try:
                content = self.log_text.get("1.0", "end")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("Sukces", f"Log wyeksportowany do:\n{filepath}", parent=self)
            except Exception as e:
                messagebox.showerror("Blad", f"Nie mozna zapisac pliku:\n{e}", parent=self)

    def _open_log_file(self):
        """Otworz plik logu w domyslnym edytorze"""
        try:
            from orders.cost_debug_logger import get_cost_debug_logger
            import os
            import subprocess

            logger = get_cost_debug_logger()
            log_path = logger.get_log_file_path()

            if log_path.exists():
                # Windows
                os.startfile(str(log_path))
            else:
                messagebox.showinfo("Info", f"Plik logu nie istnieje:\n{log_path}", parent=self)

        except Exception as e:
            messagebox.showerror("Blad", f"Nie mozna otworzyc pliku:\n{e}", parent=self)

    def destroy(self):
        """Wyrejestruj callback przy zamykaniu"""
        try:
            from orders.cost_debug_logger import get_cost_debug_logger
            logger = get_cost_debug_logger()
            logger.unregister_callback(self.append_log)
        except ImportError:
            pass

        super().destroy()


# Helper function do otwierania okna
def show_cost_debug_window(parent) -> CostDebugWindow:
    """Otworz okno logu kosztow"""
    return CostDebugWindow(parent)


# Test
if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    root = ctk.CTk()
    root.title("Test")
    root.geometry("400x200")

    def open_debug():
        win = CostDebugWindow(root)

        # Test logowania
        from orders.cost_debug_logger import get_cost_debug_logger
        logger = get_cost_debug_logger()

        logger.start_part("Test_Part_001", qty=2, material="1.4301", thickness=3.0, width=120, height=80)
        logger.log_material(weight_kg=0.227, price_per_kg=18.0, cost=4.09, density=7900)
        logger.log_cutting(length_mm=400, price_per_m=2.8, cost=1.12)
        logger.log_engraving(length_mm=50, price_per_m=2.5, cost=0.125)
        logger.log_foil(area_m2=0.45, price=0.20, cost=0.09, applicable=True)
        logger.end_part(total_lm=5.42, bending_cost=0, additional=0)

    ctk.CTkButton(root, text="Otworz Log", command=open_debug).pack(pady=50)

    root.mainloop()
