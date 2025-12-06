"""
NewERP Nesting Module
=====================
Moduły nestingu dla cięcia laserowego.

Główny algorytm: FastNester (rectpack)
- Szybki tryb: 3 próby, ~1s
- Głęboka analiza: setki prób z różnymi algorytmami

Funkcje:
- Pakowanie bounding box z prawdziwymi kształtami
- Obliczanie kosztów materiału
- Podział kosztów per detal (proporcjonalnie do pola)
"""

from .fast_nester import (
    FastNester,
    NestedPart,
    NestingResult,
    PartCostBreakdown,
    HAS_RECTPACK,
    SCALE,
)

__all__ = [
    'FastNester',
    'NestedPart',
    'NestingResult',
    'PartCostBreakdown',
    'HAS_RECTPACK',
    'SCALE',
]
