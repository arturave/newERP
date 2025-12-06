"""
Run Motion Dynamics Test Window - standalone launcher.

This script launches the Motion Dynamics Test GUI for testing
machine dynamics costing model.

Usage:
    python run_motion_dynamics_test.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import customtkinter as ctk


def main():
    """Launch the motion dynamics test window."""
    # Set theme
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Create hidden root
    root = ctk.CTk()
    root.withdraw()

    # Import and launch
    from costing.gui.motion_dynamics_test_window import MotionDynamicsTestWindow

    window = MotionDynamicsTestWindow(root)

    # Handle close
    def on_close():
        window.destroy()
        root.quit()

    window.protocol("WM_DELETE_WINDOW", on_close)

    # Run
    root.mainloop()


if __name__ == "__main__":
    main()
