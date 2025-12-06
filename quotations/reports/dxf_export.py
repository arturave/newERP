"""
DXF Nesting Export
==================
Eksport wyników nestingu do plików DXF dla maszyn CNC.

Wymaga: pip install ezdxf
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

# Sprawdź dostępność ezdxf
try:
    import ezdxf
    from ezdxf import units
    from ezdxf.enums import TextEntityAlignment
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.warning("ezdxf not installed. DXF export unavailable. Run: pip install ezdxf")

from . import QuotationReport, NestingReport, SheetReport


class DXFNestingExporter:
    """Eksporter nestingu do DXF"""
    
    # Kolory warstw (indeksy AutoCAD)
    COLOR_SHEET = 8       # Szary - arkusz
    COLOR_MARGIN = 9      # Szary jasny - margines
    COLOR_PARTS = 3       # Zielony - detale
    COLOR_HOLES = 1       # Czerwony - otwory
    COLOR_LABELS = 7      # Biały - etykiety
    COLOR_DIMENSIONS = 4  # Cyan - wymiary
    
    def __init__(self, report: QuotationReport = None):
        self.report = report
        self.doc = None
        self.msp = None
    
    def export_all_sheets(self, output_dir: str, prefix: str = "nesting") -> List[str]:
        """
        Eksportuj wszystkie arkusze do oddzielnych plików DXF.
        
        Args:
            output_dir: Katalog wyjściowy
            prefix: Prefiks nazwy pliku
            
        Returns:
            Lista ścieżek do wygenerowanych plików
        """
        if not HAS_EZDXF:
            logger.error("ezdxf not installed")
            return []
        
        if not self.report or not self.report.nesting:
            logger.error("No nesting data to export")
            return []
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        generated_files = []
        
        for sheet in self.report.nesting.sheets:
            filename = f"{prefix}_sheet_{sheet.index:03d}.dxf"
            filepath = output_path / filename
            
            if self.export_sheet(sheet, str(filepath)):
                generated_files.append(str(filepath))
        
        logger.info(f"Exported {len(generated_files)} DXF files to {output_dir}")
        return generated_files
    
    def export_sheet(self, sheet: SheetReport, output_path: str) -> bool:
        """
        Eksportuj pojedynczy arkusz do DXF.
        
        Args:
            sheet: Dane arkusza
            output_path: Ścieżka do pliku
            
        Returns:
            True jeśli sukces
        """
        if not HAS_EZDXF:
            return False
        
        try:
            # Utwórz nowy dokument
            self.doc = ezdxf.new('R2010')
            self.doc.units = units.MM
            self.msp = self.doc.modelspace()
            
            # Utwórz warstwy
            self._create_layers()
            
            # Rysuj arkusz
            self._draw_sheet_outline(sheet)
            
            # Rysuj margines (jeśli dostępny)
            if self.report:
                self._draw_margin(sheet, self.report.sheet_margin)
            
            # Rysuj detale
            self._draw_parts(sheet)
            
            # Dodaj informacje
            self._add_sheet_info(sheet)
            
            # Zapisz
            self.doc.saveas(output_path)
            
            logger.info(f"Exported sheet {sheet.index} to: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"DXF export error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_layers(self):
        """Utwórz warstwy w dokumencie"""
        layers = [
            ('SHEET', self.COLOR_SHEET, 'Continuous'),
            ('MARGIN', self.COLOR_MARGIN, 'DASHED'),
            ('PARTS', self.COLOR_PARTS, 'Continuous'),
            ('HOLES', self.COLOR_HOLES, 'Continuous'),
            ('LABELS', self.COLOR_LABELS, 'Continuous'),
            ('DIMENSIONS', self.COLOR_DIMENSIONS, 'Continuous'),
            ('INFO', self.COLOR_LABELS, 'Continuous'),
        ]
        
        for name, color, linetype in layers:
            self.doc.layers.add(name, color=color)
    
    def _draw_sheet_outline(self, sheet: SheetReport):
        """Rysuj kontur arkusza"""
        w, h = sheet.width_mm, sheet.height_mm
        
        # Prostokąt arkusza
        self.msp.add_lwpolyline(
            [(0, 0), (w, 0), (w, h), (0, h)],
            close=True,
            dxfattribs={'layer': 'SHEET', 'lineweight': 50}
        )
    
    def _draw_margin(self, sheet: SheetReport, margin: float):
        """Rysuj margines roboczy"""
        if margin <= 0:
            return
        
        w, h = sheet.width_mm, sheet.height_mm
        
        # Prostokąt marginesu (wewnętrzny)
        self.msp.add_lwpolyline(
            [(margin, margin), (w - margin, margin), 
             (w - margin, h - margin), (margin, h - margin)],
            close=True,
            dxfattribs={'layer': 'MARGIN'}
        )
    
    def _draw_parts(self, sheet: SheetReport):
        """Rysuj umieszczone detale"""
        for placed in sheet.placed_parts:
            self._draw_single_part(placed)
    
    def _draw_single_part(self, placed: Dict):
        """Rysuj pojedynczy detal"""
        x = placed.get('x', 0)
        y = placed.get('y', 0)
        width = placed.get('width', 0)
        height = placed.get('height', 0)
        rotated = placed.get('rotated', False)
        rotation = placed.get('rotation', 0)
        name = placed.get('name', 'Part')
        polygon_coords = placed.get('polygon_coords', None)
        holes = placed.get('holes', [])
        
        # Jeśli mamy współrzędne wielokąta - użyj ich
        if polygon_coords:
            # Transformuj współrzędne
            transformed = self._transform_coords(polygon_coords, x, y, rotation)
            
            self.msp.add_lwpolyline(
                transformed,
                close=True,
                dxfattribs={'layer': 'PARTS', 'lineweight': 25}
            )
            
            # Rysuj otwory
            for hole in holes:
                hole_transformed = self._transform_coords(hole, x, y, rotation)
                self.msp.add_lwpolyline(
                    hole_transformed,
                    close=True,
                    dxfattribs={'layer': 'HOLES', 'lineweight': 18}
                )
        else:
            # Prostokąt
            if rotated or rotation in [90, 270]:
                w, h = height, width
            else:
                w, h = width, height
            
            self.msp.add_lwpolyline(
                [(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                close=True,
                dxfattribs={'layer': 'PARTS', 'lineweight': 25}
            )
        
        # Etykieta (nazwa detalu)
        if name:
            label_x = x + (width / 2 if not rotated else height / 2)
            label_y = y + (height / 2 if not rotated else width / 2)
            
            # Skróć długie nazwy
            short_name = name[:15] + '...' if len(name) > 15 else name
            
            self.msp.add_text(
                short_name,
                dxfattribs={
                    'layer': 'LABELS',
                    'height': min(width, height) / 10,  # Proporcjonalna wysokość
                    'rotation': rotation
                }
            ).set_placement((label_x, label_y), align=TextEntityAlignment.MIDDLE_CENTER)
    
    def _transform_coords(
        self, 
        coords: List[Tuple[float, float]], 
        offset_x: float, 
        offset_y: float, 
        rotation: float
    ) -> List[Tuple[float, float]]:
        """Transformuj współrzędne (offset + rotacja)"""
        import math
        
        result = []
        angle_rad = math.radians(rotation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        
        for px, py in coords:
            # Rotacja
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            
            # Offset
            result.append((rx + offset_x, ry + offset_y))
        
        return result
    
    def _add_sheet_info(self, sheet: SheetReport):
        """Dodaj informacje o arkuszu"""
        w, h = sheet.width_mm, sheet.height_mm
        
        # Informacje w lewym górnym rogu (poza arkuszem)
        info_lines = [
            f"Arkusz {sheet.index}: {sheet.format_name}",
            f"Materiał: {sheet.material} {sheet.thickness_mm}mm",
            f"Detali: {sheet.parts_count}",
            f"Wykorzystanie: {sheet.utilization * 100:.1f}%",
        ]
        
        if self.report:
            info_lines.append(f"Data: {self.report.quotation_date.strftime('%Y-%m-%d')}")
        
        y_pos = h + 20  # 20mm nad arkuszem
        
        for line in info_lines:
            self.msp.add_text(
                line,
                dxfattribs={
                    'layer': 'INFO',
                    'height': 5
                }
            ).set_placement((0, y_pos), align=TextEntityAlignment.LEFT)
            y_pos -= 8
        
        # Wymiary arkusza
        self._add_dimension(0, -15, w, -15, f"{w:.0f}")  # Szerokość na dole
        self._add_dimension(-15, 0, -15, h, f"{h:.0f}")  # Wysokość z lewej
    
    def _add_dimension(self, x1: float, y1: float, x2: float, y2: float, text: str):
        """Dodaj wymiar"""
        import math
        
        # Linia wymiaru
        self.msp.add_line(
            (x1, y1), (x2, y2),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        
        # Strzałki
        arrow_size = 3
        
        # Środek
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        
        # Tekst wymiaru
        self.msp.add_text(
            text,
            dxfattribs={
                'layer': 'DIMENSIONS',
                'height': 4
            }
        ).set_placement((mid_x, mid_y - 5), align=TextEntityAlignment.MIDDLE_CENTER)


def export_nesting_to_dxf(
    report: QuotationReport,
    output_dir: str,
    prefix: str = "nesting"
) -> List[str]:
    """
    Eksportuj nesting do plików DXF.
    
    Args:
        report: Raport wyceny z nestingiem
        output_dir: Katalog wyjściowy
        prefix: Prefiks nazwy plików
        
    Returns:
        Lista wygenerowanych plików
    """
    exporter = DXFNestingExporter(report)
    return exporter.export_all_sheets(output_dir, prefix)


def export_single_sheet_dxf(
    sheet: SheetReport,
    output_path: str,
    margin: float = 10.0
) -> bool:
    """
    Eksportuj pojedynczy arkusz do DXF.
    
    Args:
        sheet: Dane arkusza
        output_path: Ścieżka do pliku
        margin: Margines arkusza
        
    Returns:
        True jeśli sukces
    """
    # Utwórz tymczasowy raport
    from . import QuotationReport
    
    report = QuotationReport(sheet_margin=margin)
    
    exporter = DXFNestingExporter(report)
    return exporter.export_sheet(sheet, output_path)
