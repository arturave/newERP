"""
Documents Module
================
Modul do generowania dokumentow PDF z pelna identyfikacja wizualna detali.

Obslugiwane typy dokumentow:
- WZ (Wydanie Zewnetrzne) - z thumbnailami detali
- Potwierdzenie zamowienia - z thumbnailami i cenami
- Lista pakunkowa - z thumbnailami i wagami
- CMR (Miedzynarodowy list przewozowy)
- Raport kosztowy - szczegolowa kalkulacja kosztow
- Oferta handlowa

Wykorzystuje WeasyPrint + Jinja2 dla renderowania HTML do PDF.

Uzycie:
    from documents import DocumentService, DocumentType
    from documents.gui import open_document_generator

    # Przez serwis
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    doc_service = DocumentService(client)

    result = doc_service.generate_document(
        doc_type=DocumentType.WZ,
        entity_id="uuid-zamowienia",
        user_id="uuid-usera"
    )

    # Przez GUI
    open_document_generator(
        parent=window,
        entity_id="uuid-zamowienia",
        entity_type="order",
        entity_name="ZAM/2025/001"
    )
"""

from .constants import DocumentType, DBTables, DOCUMENT_LABELS
from .models import DocumentContext, CompanyInfo, DocumentItem
from .service import DocumentService, create_document_service
from .renderer import DocumentRenderer

# GUI components (lazy import)
def get_document_generator_dialog():
    """Pobierz klase dialogu generowania dokumentow"""
    from .gui.document_generator_dialog import DocumentGeneratorDialog
    return DocumentGeneratorDialog

def open_document_generator(parent, entity_id, entity_type="order", entity_name="", on_generate=None):
    """Otworz dialog generowania dokumentow"""
    from .gui.document_generator_dialog import open_document_generator as _open
    return _open(parent, entity_id, entity_type, entity_name, on_generate)

__all__ = [
    # Constants
    'DocumentType',
    'DBTables',
    'DOCUMENT_LABELS',
    # Models
    'DocumentContext',
    'CompanyInfo',
    'DocumentItem',
    # Service
    'DocumentService',
    'create_document_service',
    'DocumentRenderer',
    # GUI
    'get_document_generator_dialog',
    'open_document_generator'
]
