"""
CAD Module - Interaktywny viewer i edytor CAD 2D
================================================

Komponenty:
- CADCanvas: Interaktywny canvas z zoom/pan
- CAD2DViewer: Główne okno viewera

Użycie:
    from cad import open_cad_viewer

    # Otwórz plik DXF
    viewer = open_cad_viewer(filepath="path/to/file.dxf")

    # Lub z DXFPart
    from core.dxf import UnifiedDXFReader
    reader = UnifiedDXFReader()
    part = reader.read("path/to/file.dxf")
    viewer = open_cad_viewer(part=part)
"""

from .canvas import CADCanvas
from .viewer import CAD2DViewer, open_cad_viewer


__all__ = [
    'CADCanvas',
    'CAD2DViewer',
    'open_cad_viewer',
]
