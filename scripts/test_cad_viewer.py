#!/usr/bin/env python3
"""
Test skrypt dla CAD 2D Viewer
=============================
Uruchom: python scripts/test_cad_viewer.py [ścieżka_do_dxf]
"""

import sys
import os

# Dodaj ścieżkę projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from core.dxf import UnifiedDXFReader
from cad import open_cad_viewer


def main():
    # Domyślny plik testowy
    default_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "temp", "Test1", "11-063143_2mm_INOX_9szt.dxf"
    )

    # Użyj argumentu lub domyślnego pliku
    filepath = sys.argv[1] if len(sys.argv) > 1 else default_file

    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        print(f"Usage: python {sys.argv[0]} [path_to_dxf]")
        return

    print(f"Opening: {filepath}")

    # Utwórz główne okno
    if HAS_CTK:
        root = ctk.CTk()
        root.withdraw()  # Ukryj główne okno
    else:
        root = tk.Tk()
        root.withdraw()

    # Otwórz viewer
    viewer = open_cad_viewer(root, filepath=filepath)

    # Ustaw zamknięcie aplikacji przy zamknięciu viewera
    def on_close():
        root.quit()
        root.destroy()

    viewer._on_close = on_close

    # Uruchom główną pętlę
    root.mainloop()


if __name__ == "__main__":
    main()
