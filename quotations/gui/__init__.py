"""
Quotations GUI
==============
Komponenty GUI dla modułu wycen.

Główne komponenty:
- NestingTabsPanel: Panel z zakładkami nestingu per materiał+grubość
- RegexEditorPanel: Edytor reguł regex dla parsera nazw
- NestingCanvas: Canvas z interaktywną wizualizacją nestingu
- PartPreviewCanvas: Podgląd pojedynczego detalu
"""

from .nesting_tabs_panel import (
    NestingTabsPanel,
    NestingTab,
    NestingCanvas,
    PartPreviewCanvas,
    PART_COLORS,
)

from .regex_editor_panel import (
    RegexEditorPanel,
    RegexEditorWindow,
)

__all__ = [
    'NestingTabsPanel',
    'NestingTab', 
    'NestingCanvas',
    'PartPreviewCanvas',
    'PART_COLORS',
    'RegexEditorPanel',
    'RegexEditorWindow',
]
