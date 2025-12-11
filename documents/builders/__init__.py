"""
Document Context Builders
=========================
Buildery odpowiedzialne za pobieranie danych i tworzenie kontekstu dla szablonow.

Kazdy builder:
- Pobiera dane z bazy danych (zamowienia, wyceny, klienci, produkty)
- Transformuje dane do modelu DocumentContext
- Obsluguje thumbnails dla identyfikacji wizualnej detali
"""

from .base import BaseContextBuilder
from .quotation_builder import QuotationContextBuilder
from .wz_builder import WZContextBuilder
from .cmr_builder import CMRContextBuilder
from .order_confirmation_builder import OrderConfirmationContextBuilder
from .packing_list_builder import PackingListContextBuilder
from .cost_report_builder import CostReportContextBuilder

__all__ = [
    'BaseContextBuilder',
    'QuotationContextBuilder',
    'WZContextBuilder',
    'CMRContextBuilder',
    'OrderConfirmationContextBuilder',
    'PackingListContextBuilder',
    'CostReportContextBuilder'
]
