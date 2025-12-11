"""
Document Service
================
Glowny serwis do generowania dokumentow PDF.
Integruje buildery kontekstu, renderer i storage.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Type

from supabase import Client

from core.base_service import BaseService
from core.events import EventBus, EventType
from core.audit import AuditService, AuditAction

from .constants import (
    DocumentType, DBTables, STORAGE_BUCKET, STORAGE_BASE_PATH,
    DOCUMENT_LABELS, TEMPLATE_FILES
)
from .models import DocumentContext, DocumentMetadata
from .repository import DocumentRepository
from .renderer import DocumentRenderer
from .builders.base import BaseContextBuilder
from .utils import generate_document_path, sanitize_filename

logger = logging.getLogger(__name__)


class DocumentService(BaseService):
    """
    Serwis do generowania dokumentow PDF.

    Uzycie:
        from documents.service import DocumentService
        from documents.constants import DocumentType
        from core.supabase_client import get_supabase_client

        client = get_supabase_client()
        service = DocumentService(client)

        # Wygeneruj PDF
        result = service.generate_document(
            doc_type=DocumentType.QUOTATION,
            entity_id="uuid-oferty",
            user_id="uuid-usera"
        )

        # Podglad HTML
        html = service.generate_document(
            doc_type=DocumentType.QUOTATION,
            entity_id="uuid-oferty",
            user_id="uuid-usera",
            preview=True
        )
    """

    ENTITY_NAME = "Document"

    # Pola walidacji dla metadanych
    REQUIRED_FIELDS = ["doc_type", "related_id"]
    OPTIONAL_FIELDS = ["customer_id", "notes"]

    def __init__(
        self,
        client: Client,
        event_bus: EventBus = None,
        audit_service: AuditService = None
    ):
        super().__init__(client, event_bus, audit_service)

        self.repository = DocumentRepository(client)
        self.renderer = DocumentRenderer()

        # Rejestr builderow kontekstu (lazy loading)
        self._builders: Dict[DocumentType, BaseContextBuilder] = {}
        self._register_default_builders()

    def _register_default_builders(self):
        """Rejestruje domyslne buildery kontekstu"""
        # Lazy import aby uniknac circular imports
        try:
            from .builders.quotation_builder import QuotationContextBuilder
            self._builders[DocumentType.QUOTATION] = QuotationContextBuilder(self.client)
        except ImportError as e:
            logger.debug(f"QuotationContextBuilder not available: {e}")

        try:
            from .builders.wz_builder import WZContextBuilder
            self._builders[DocumentType.WZ] = WZContextBuilder(self.client)
        except ImportError as e:
            logger.debug(f"WZContextBuilder not available: {e}")

        try:
            from .builders.cmr_builder import CMRContextBuilder
            self._builders[DocumentType.CMR] = CMRContextBuilder(self.client)
        except ImportError as e:
            logger.debug(f"CMRContextBuilder not available: {e}")

        try:
            from .builders.order_confirmation_builder import OrderConfirmationContextBuilder
            self._builders[DocumentType.ORDER_CONFIRMATION] = OrderConfirmationContextBuilder(self.client)
        except ImportError as e:
            logger.debug(f"OrderConfirmationContextBuilder not available: {e}")

        try:
            from .builders.packing_list_builder import PackingListContextBuilder
            self._builders[DocumentType.PACKING_LIST] = PackingListContextBuilder(self.client)
        except ImportError as e:
            logger.debug(f"PackingListContextBuilder not available: {e}")

        try:
            from .builders.cost_report_builder import CostReportContextBuilder
            self._builders[DocumentType.COST_REPORT] = CostReportContextBuilder(self.client)
        except ImportError as e:
            logger.debug(f"CostReportContextBuilder not available: {e}")

    def register_builder(self, doc_type: DocumentType, builder: BaseContextBuilder):
        """Zarejestruj customowy builder"""
        self._builders[doc_type] = builder
        logger.info(f"Registered builder for {doc_type}")

    # ============================================================
    # Glowne metody generowania
    # ============================================================

    def generate_document(
        self,
        doc_type: DocumentType,
        entity_id: str,
        user_id: str = None,
        preview: bool = False,
        custom_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generuje dokument PDF.

        Args:
            doc_type: Typ dokumentu (DocumentType enum)
            entity_id: ID encji (zamowienia, oferty, etc.)
            user_id: ID uzytkownika generujacego
            preview: True = zwroc tylko HTML, nie zapisuj
            custom_context: Opcjonalne dodatkowe dane do kontekstu

        Returns:
            {
                'success': bool,
                'doc_number': str,
                'storage_path': str,  # jesli nie preview
                'html': str,          # jesli preview
                'document_id': str,   # jesli nie preview
                'error': str          # jesli blad
            }
        """
        try:
            # 1. Pobierz builder
            builder = self._builders.get(doc_type)
            if not builder:
                return {
                    'success': False,
                    'error': f"Brak buildera dla typu: {doc_type}"
                }

            # 2. Wygeneruj numer dokumentu
            if preview:
                doc_number = "PODGLAD/0000"
                number_seq = 0
            else:
                number_seq, doc_number = self.repository.get_next_number(
                    doc_type.value,
                    datetime.now().year
                )

            # 3. Zbuduj kontekst
            context = builder.build(entity_id, doc_number, user_id)

            # Dodaj customowe dane
            if custom_context:
                context.extra_data.update(custom_context)

            # 4. Pobierz szablon
            template_name = self._get_template_name(doc_type)

            # 5. Sprawdz czy szablon istnieje
            if not self.renderer.template_exists(template_name):
                return {
                    'success': False,
                    'error': f"Szablon nie istnieje: {template_name}"
                }

            # 6. Renderuj HTML
            template_context = context.to_template_dict()
            html_content = self.renderer.render_html(template_name, template_context)

            # 7. Jesli preview - zwroc HTML
            if preview:
                return {
                    'success': True,
                    'doc_number': doc_number,
                    'html': html_content
                }

            # 8. Renderuj PDF
            pdf_bytes = self.renderer.render_pdf_bytes(html_content)

            # 9. Upload do Storage
            year = datetime.now().year
            storage_path = generate_document_path(doc_type.value, year, doc_number)

            upload_success = self._upload_to_storage(storage_path, pdf_bytes)
            if not upload_success:
                return {
                    'success': False,
                    'error': "Blad uploadu do storage"
                }

            # 10. Zapisz metadane
            metadata = {
                'doc_type': doc_type.value,
                'doc_number_full': doc_number,
                'year': year,
                'number_seq': number_seq,
                'related_table': self._get_related_table(doc_type),
                'related_id': entity_id,
                'storage_path': storage_path,
                'created_by': user_id,
                'is_deleted': False
            }

            # Dodaj customer_id jesli dostepny
            if hasattr(context, 'buyer') and context.buyer:
                # Trzeba by pobrac customer_id z kontekstu lub buildera
                pass

            success, document_id = self.repository.save_document_metadata(metadata)

            if not success:
                logger.warning("Document generated but metadata save failed")

            # 11. Audit
            if user_id:
                self.set_user(user_id)
                self.log_audit(
                    entity_id=document_id or entity_id,
                    action=AuditAction.CREATE,
                    new_values={'doc_number': doc_number, 'doc_type': doc_type.value}
                )

            logger.info(f"[Document] Generated: {doc_number}")

            return {
                'success': True,
                'doc_number': doc_number,
                'storage_path': storage_path,
                'document_id': document_id,
                'pdf_size': len(pdf_bytes)
            }

        except Exception as e:
            logger.error(f"Document generation failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    def get_document_preview(
        self,
        doc_type: DocumentType,
        entity_id: str,
        user_id: str = None
    ) -> str:
        """
        Zwraca podglad HTML dokumentu.

        Returns:
            HTML string lub pusty string jesli blad
        """
        result = self.generate_document(
            doc_type=doc_type,
            entity_id=entity_id,
            user_id=user_id,
            preview=True
        )

        return result.get('html', '') if result.get('success') else ''

    def regenerate_document(
        self,
        document_id: str,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Regeneruj istniejacy dokument (np. po zmianie szablonu).

        Uwaga: Tworzy nowa wersje, nie nadpisuje starej.
        """
        # Pobierz metadane starego dokumentu
        old_doc = self.repository.get_by_id(document_id)
        if not old_doc:
            return {'success': False, 'error': 'Dokument nie znaleziony'}

        doc_type = DocumentType(old_doc['doc_type'])
        entity_id = old_doc['related_id']

        # Wygeneruj nowy
        return self.generate_document(doc_type, entity_id, user_id)

    # ============================================================
    # Pobieranie dokumentow
    # ============================================================

    def get_document_url(self, document_id: str) -> Optional[str]:
        """
        Pobierz URL do pobrania dokumentu.

        Returns:
            URL lub None
        """
        doc = self.repository.get_by_id(document_id)
        if not doc:
            return None

        storage_path = doc.get('storage_path')
        if not storage_path:
            return None

        try:
            # Signed URL (wazny przez 1h)
            response = self.client.storage.from_(STORAGE_BUCKET)\
                .create_signed_url(storage_path, 3600)
            return response.get('signedURL')
        except Exception as e:
            logger.error(f"Failed to get signed URL: {e}")
            return None

    def download_document(self, document_id: str) -> Optional[bytes]:
        """
        Pobierz zawartosc PDF.

        Returns:
            PDF bytes lub None
        """
        doc = self.repository.get_by_id(document_id)
        if not doc:
            return None

        storage_path = doc.get('storage_path')
        if not storage_path:
            return None

        try:
            response = self.client.storage.from_(STORAGE_BUCKET)\
                .download(storage_path)
            return response
        except Exception as e:
            logger.error(f"Failed to download document: {e}")
            return None

    def get_documents_for_entity(
        self,
        entity_type: str,
        entity_id: str
    ) -> list:
        """Pobierz wszystkie dokumenty dla encji"""
        return self.repository.get_documents_for_entity(entity_type, entity_id)

    # ============================================================
    # Szablony
    # ============================================================

    def get_available_templates(self) -> list:
        """Zwraca liste dostepnych szablonow z dysku"""
        return self.renderer.get_available_templates()

    def get_template_from_db(self, doc_type: DocumentType) -> Optional[Dict]:
        """Pobierz szablon z bazy danych"""
        return self.repository.get_active_template(doc_type.value)

    def save_template(
        self,
        doc_type: DocumentType,
        name: str,
        content_html: str,
        styles_css: str = None,
        meta_json: dict = None
    ) -> bool:
        """Zapisz nowy szablon do bazy"""
        template_data = {
            'doc_type': doc_type.value,
            'name': name,
            'content_html': content_html,
            'styles_css': styles_css,
            'meta_json': meta_json
        }
        success, _ = self.repository.save_template(template_data)
        return success

    # ============================================================
    # Helper methods
    # ============================================================

    def _get_template_name(self, doc_type: DocumentType) -> str:
        """Zwraca nazwe pliku szablonu"""
        return TEMPLATE_FILES.get(doc_type, 'base.html')

    def _get_related_table(self, doc_type: DocumentType) -> str:
        """Zwraca nazwe tabeli powiazanej z typem dokumentu"""
        mapping = {
            DocumentType.QUOTATION: 'quotations',
            DocumentType.WZ: 'orders',
            DocumentType.CMR: 'delivery_notes',
            DocumentType.INVOICE: 'invoices',
            DocumentType.ORDER_CONFIRMATION: 'orders',
            DocumentType.DELIVERY_NOTE: 'delivery_notes',
            DocumentType.PACKING_LIST: 'orders',
            DocumentType.COST_REPORT: 'orders',  # Moze byc tez quotations
        }
        return mapping.get(doc_type, 'documents')

    def _upload_to_storage(self, path: str, content: bytes) -> bool:
        """Upload pliku do Supabase Storage"""
        try:
            self.client.storage.from_(STORAGE_BUCKET).upload(
                path=path,
                file=content,
                file_options={"content-type": "application/pdf"}
            )
            logger.debug(f"Uploaded to storage: {path}")
            return True
        except Exception as e:
            # Moze byc duplikat - sprobuj nadpisac
            if 'duplicate' in str(e).lower() or 'already exists' in str(e).lower():
                try:
                    self.client.storage.from_(STORAGE_BUCKET).update(
                        path=path,
                        file=content,
                        file_options={"content-type": "application/pdf"}
                    )
                    return True
                except Exception as e2:
                    logger.error(f"Failed to update in storage: {e2}")
                    return False
            logger.error(f"Failed to upload to storage: {e}")
            return False


# ============================================================
# Factory Function
# ============================================================

def create_document_service(supabase_client=None) -> DocumentService:
    """
    Factory function dla DocumentService.

    Args:
        supabase_client: Opcjonalny klient Supabase

    Returns:
        DocumentService instance
    """
    if supabase_client is None:
        try:
            from core.supabase_client import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Cannot create Supabase client: {e}")
            raise

    return DocumentService(supabase_client)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Testing DocumentService...")

    try:
        service = create_document_service()

        # Lista szablonow
        templates = service.get_available_templates()
        print(f"Available templates: {templates}")

        # Lista zarejestrowanych builderow
        print(f"Registered builders: {list(service._builders.keys())}")

        print("\nDocumentService test completed!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
