"""
Launch Nesting Costing Window
=============================
Uruchom okno Nesting & Costing bezposrednio.

Usage:
    python launch_costing.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import customtkinter as ctk
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

from costing import launch_nesting_costing_window

if __name__ == "__main__":
    root = ctk.CTk()
    root.withdraw()

    window = launch_nesting_costing_window(root)
    window.mainloop()
