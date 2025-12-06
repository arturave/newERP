"""
NewERP - Quotations Module
==========================
Moduł wycen z nestingiem i kalkulacją cen.
"""

# Lazy import - GUI wymaga customtkinter
def get_quotation_window():
    from quotations.gui.quotation_window import QuotationWindow
    return QuotationWindow

__all__ = ['get_quotation_window']
