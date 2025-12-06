"""
NewERP Pricing Module
=====================
Zarządzanie cennikami materiałów i cięcia laserowego.

Funkcje:
- Import/export cenników z Excel
- Przechowywanie w Supabase
- GUI do zarządzania cenami
- Obliczanie kosztów materiału i cięcia
- Rozszerzone tabele kosztów (folia, piercing, operacyjne)
"""

from .repository import PricingRepository
from .cost_repository import CostRepository
from .service import PricingService, create_pricing_service
from .cost_service import CostService, create_cost_service
from .xlsx_importer import ExcelPriceImporter, PriceExporter, ImportResult

__all__ = [
    'PricingRepository',
    'CostRepository',
    'PricingService',
    'CostService',
    'create_pricing_service',
    'create_cost_service',
    'ExcelPriceImporter',
    'PriceExporter',
    'ImportResult',
]
