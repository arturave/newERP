"""
Documents Constants
===================
Definicje typow dokumentow i nazw tabel bazy danych.
"""

from enum import Enum


class DocumentType(str, Enum):
    """Typy dokumentow obslugiwane przez system"""
    WZ = "WZ"                           # Wydanie Zewnetrzne
    QUOTATION = "QUOTATION"             # Oferta handlowa
    INVOICE = "INVOICE"                 # Faktura
    DELIVERY_NOTE = "DELIVERY_NOTE"     # List przewozowy
    CMR = "CMR"                         # Miedzynarodowy list przewozowy
    ORDER_CONFIRMATION = "ORDER_CONFIRMATION"  # Potwierdzenie zamowienia
    PACKING_LIST = "PACKING_LIST"       # Lista pakunkowa
    COST_REPORT = "COST_REPORT"         # Raport kosztowy


class DBTables:
    """Nazwy tabel w bazie danych"""
    COUNTERS = "document_counters"
    REGISTRY = "documents_registry"
    TEMPLATES = "document_templates"
    CUSTOMERS = "customers"
    QUOTATIONS = "quotations"
    QUOTATION_ITEMS = "quotation_items"
    ORDERS = "orders"
    ORDER_ITEMS = "order_items"
    DELIVERY_NOTES = "delivery_notes"
    DELIVERY_NOTE_ITEMS = "delivery_note_items"


# Domyslna waluta
DEFAULT_CURRENCY = "PLN"

# Bucket w Supabase Storage
STORAGE_BUCKET = "documents"

# Sciezka bazowa w storage
STORAGE_BASE_PATH = "documents"

# Mapowanie typow dokumentow na etykiety
DOCUMENT_LABELS = {
    DocumentType.WZ: "WYDANIE ZEWNETRZNE",
    DocumentType.QUOTATION: "OFERTA HANDLOWA",
    DocumentType.INVOICE: "FAKTURA VAT",
    DocumentType.DELIVERY_NOTE: "LIST PRZEWOZOWY",
    DocumentType.CMR: "CMR - MIEDZYNARODOWY LIST PRZEWOZOWY",
    DocumentType.ORDER_CONFIRMATION: "POTWIERDZENIE ZAMOWIENIA",
    DocumentType.PACKING_LIST: "LISTA PAKUNKOWA",
    DocumentType.COST_REPORT: "RAPORT KOSZTOWY",
}

# Mapowanie typow dokumentow na nazwy plikow szablonow
TEMPLATE_FILES = {
    DocumentType.WZ: "wz.html",
    DocumentType.QUOTATION: "quotation.html",
    DocumentType.INVOICE: "invoice.html",
    DocumentType.DELIVERY_NOTE: "delivery_note.html",
    DocumentType.CMR: "cmr.html",
    DocumentType.ORDER_CONFIRMATION: "order_confirmation.html",
    DocumentType.PACKING_LIST: "packing_list.html",
    DocumentType.COST_REPORT: "cost_report.html",
}

# Stawki VAT
VAT_RATES = {
    'standard': 23,
    'reduced': 8,
    'super_reduced': 5,
    'zero': 0
}
