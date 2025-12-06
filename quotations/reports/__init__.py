"""
NewERP - Reports Module
=======================
Generowanie raportów z nestingu i wycen.

Formaty:
- PDF - profesjonalny raport dla klienta
- Excel - szczegółowe dane do analizy
- DXF - rozkład do maszyny CNC
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import io

logger = logging.getLogger(__name__)

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PartReport:
    """Dane detalu do raportu"""
    id: str
    name: str
    material: str
    thickness_mm: float
    width_mm: float
    height_mm: float
    quantity: int
    area_mm2: float = 0
    perimeter_mm: float = 0
    has_bending: bool = False
    unit_cost: float = 0
    total_cost: float = 0
    file_2d: str = ""
    file_3d: str = ""
    
    def __post_init__(self):
        if self.area_mm2 == 0:
            self.area_mm2 = self.width_mm * self.height_mm
        if self.perimeter_mm == 0:
            self.perimeter_mm = 2 * (self.width_mm + self.height_mm)


@dataclass
class SheetReport:
    """Dane arkusza do raportu"""
    index: int
    width_mm: float
    height_mm: float
    format_name: str
    material: str
    thickness_mm: float
    parts_count: int
    utilization: float
    placed_parts: List[Dict] = field(default_factory=list)
    
    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.height_mm
    
    @property
    def used_area_mm2(self) -> float:
        return self.area_mm2 * self.utilization
    
    @property
    def waste_area_mm2(self) -> float:
        return self.area_mm2 * (1 - self.utilization)


@dataclass
class NestingReport:
    """Pełny raport nestingu"""
    sheets: List[SheetReport]
    total_sheets: int = 0
    total_parts: int = 0
    average_utilization: float = 0
    total_sheet_area_mm2: float = 0
    total_used_area_mm2: float = 0
    total_waste_area_mm2: float = 0
    
    def __post_init__(self):
        if self.sheets:
            self.total_sheets = len(self.sheets)
            self.total_parts = sum(s.parts_count for s in self.sheets)
            self.total_sheet_area_mm2 = sum(s.area_mm2 for s in self.sheets)
            self.total_used_area_mm2 = sum(s.used_area_mm2 for s in self.sheets)
            self.total_waste_area_mm2 = sum(s.waste_area_mm2 for s in self.sheets)
            if self.total_sheet_area_mm2 > 0:
                self.average_utilization = self.total_used_area_mm2 / self.total_sheet_area_mm2


@dataclass
class CostBreakdown:
    """Rozbicie kosztów"""
    material_cost: float = 0
    cutting_cost: float = 0
    bending_cost: float = 0
    setup_cost: float = 0
    programming_cost: float = 0
    other_cost: float = 0
    subtotal: float = 0
    margin_percent: float = 0
    margin_value: float = 0
    total: float = 0
    
    def calculate_total(self):
        self.subtotal = (
            self.material_cost + self.cutting_cost + self.bending_cost +
            self.setup_cost + self.programming_cost + self.other_cost
        )
        self.margin_value = self.subtotal * self.margin_percent
        self.total = self.subtotal + self.margin_value


@dataclass
class QuotationReport:
    """Pełny raport wyceny"""
    # Metadane
    quotation_id: str = ""
    quotation_date: datetime = field(default_factory=datetime.now)
    valid_until: datetime = None
    
    # Klient
    customer_name: str = ""
    customer_company: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    customer_address: str = ""
    customer_nip: str = ""
    
    # Detale
    parts: List[PartReport] = field(default_factory=list)
    
    # Nesting
    nesting: NestingReport = None
    
    # Koszty
    costs: CostBreakdown = field(default_factory=CostBreakdown)
    
    # Parametry
    algorithm: str = "FFDH"
    kerf_width: float = 0.2
    part_spacing: float = 3.0
    sheet_margin: float = 10.0
    
    # Notatki
    notes: str = ""
    terms: str = ""
    
    @property
    def total_parts_count(self) -> int:
        return sum(p.quantity for p in self.parts)
    
    @property
    def unique_materials(self) -> List[str]:
        return list(set(f"{p.material} {p.thickness_mm}mm" for p in self.parts))


# =============================================================================
# Report Generator Base
# =============================================================================

class ReportGenerator:
    """Bazowa klasa generatora raportów"""
    
    def __init__(self, report: QuotationReport):
        self.report = report
    
    def generate(self, output_path: str) -> bool:
        """Generuj raport - do nadpisania w podklasach"""
        raise NotImplementedError
    
    def _format_currency(self, value: float) -> str:
        """Formatuj walutę"""
        return f"{value:,.2f} PLN".replace(",", " ")
    
    def _format_percent(self, value: float) -> str:
        """Formatuj procent"""
        return f"{value * 100:.1f}%"
    
    def _format_area(self, value_mm2: float) -> str:
        """Formatuj powierzchnię"""
        if value_mm2 >= 1_000_000:
            return f"{value_mm2 / 1_000_000:.2f} m²"
        else:
            return f"{value_mm2 / 100:.1f} cm²"
    
    def _format_date(self, dt: datetime) -> str:
        """Formatuj datę"""
        if dt:
            return dt.strftime("%d.%m.%Y")
        return ""
