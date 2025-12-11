"""
Document Repository
===================
Repozytorium do zarzadzania dokumentami w bazie danych.
Dziedziczy po BaseRepository dla standardowych operacji CRUD.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from supabase import Client

from core.base_repository import BaseRepository
from core.exceptions import DatabaseError, RecordNotFoundError

from .constants import DBTables, DocumentType, STORAGE_BUCKET

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository):
    """
    Repozytorium dokumentow.

    Zarzadza:
    - documents_registry: Metadane wygenerowanych dokumentow
    - document_counters: Numeracja dokumentow
    - document_templates: Szablony dokumentow
    """

    TABLE_NAME = DBTables.REGISTRY
    ENTITY_NAME = "Document"

    SEARCH_FIELDS = ["doc_number_full", "doc_type"]
    UNIQUE_FIELDS = ["doc_number_full"]

    def __init__(self, client: Client):
        super().__init__(client)
        self._counters_table = DBTables.COUNTERS
        self._templates_table = DBTables.TEMPLATES

    # ============================================================
    # Numeracja dokumentow
    # ============================================================

    def get_next_number(self, doc_type: str, year: int = None) -> Tuple[int, str]:
        """
        Pobierz nastepny numer dokumentu (atomowo).

        Wywoluje funkcje SQL get_next_document_number dla zapewnienia
        unikalnosci przy wspolbieznosci.

        Args:
            doc_type: Typ dokumentu (np. 'WZ', 'QUOTATION')
            year: Rok (domyslnie biezacy)

        Returns:
            Tuple[int, str]: (numer_sekwencyjny, pelny_numer)
            np. (123, 'WZ/2025/000123')
        """
        if year is None:
            year = datetime.now().year

        try:
            # Wywolaj funkcje RPC w bazie
            response = self.client.rpc(
                'get_next_document_number',
                {'p_doc_type': doc_type, 'p_year': year}
            ).execute()

            seq = response.data
            if seq is None:
                # Fallback - uzyj lokalnego countera
                seq = self._get_next_number_fallback(doc_type, year)

            full_number = f"{doc_type}/{year}/{seq:06d}"
            logger.info(f"[Document] Generated number: {full_number}")

            return seq, full_number

        except Exception as e:
            logger.warning(f"RPC get_next_document_number failed: {e}")
            # Fallback
            seq = self._get_next_number_fallback(doc_type, year)
            full_number = f"{doc_type}/{year}/{seq:06d}"
            return seq, full_number

    def _get_next_number_fallback(self, doc_type: str, year: int) -> int:
        """
        Fallback dla numeracji gdy RPC nie dziala.
        Uzywa UPDATE ... RETURNING dla atomowosci.
        """
        try:
            # Probuj aktualizowac istniejacy rekord
            response = self.client.table(self._counters_table)\
                .select('last_number')\
                .eq('doc_type', doc_type)\
                .eq('year', year)\
                .single()\
                .execute()

            if response.data:
                new_number = response.data['last_number'] + 1
                self.client.table(self._counters_table)\
                    .update({
                        'last_number': new_number,
                        'updated_at': datetime.now().isoformat()
                    })\
                    .eq('doc_type', doc_type)\
                    .eq('year', year)\
                    .execute()
                return new_number
            else:
                # Stworz nowy rekord
                self.client.table(self._counters_table)\
                    .insert({
                        'doc_type': doc_type,
                        'year': year,
                        'last_number': 1
                    })\
                    .execute()
                return 1

        except Exception as e:
            logger.error(f"Fallback numbering failed: {e}")
            # Ostateczny fallback - zwroc timestamp jako numer
            return int(datetime.now().timestamp()) % 1000000

    def get_current_counter(self, doc_type: str, year: int = None) -> int:
        """Pobierz aktualny stan licznika (bez inkrementacji)"""
        if year is None:
            year = datetime.now().year

        try:
            response = self.client.table(self._counters_table)\
                .select('last_number')\
                .eq('doc_type', doc_type)\
                .eq('year', year)\
                .single()\
                .execute()

            return response.data.get('last_number', 0) if response.data else 0
        except:
            return 0

    # ============================================================
    # Szablony dokumentow
    # ============================================================

    def get_active_template(self, doc_type: str) -> Optional[Dict[str, Any]]:
        """
        Pobierz aktywny szablon dla typu dokumentu.

        Args:
            doc_type: Typ dokumentu

        Returns:
            Slownik z szablonem lub None
        """
        try:
            response = self.client.table(self._templates_table)\
                .select('*')\
                .eq('doc_type', doc_type)\
                .eq('is_active', True)\
                .order('version', desc=True)\
                .limit(1)\
                .execute()

            return response.data[0] if response.data else None

        except Exception as e:
            logger.warning(f"Failed to get template for {doc_type}: {e}")
            return None

    def get_all_templates(self, doc_type: str = None) -> List[Dict[str, Any]]:
        """Pobierz wszystkie szablony (opcjonalnie dla typu)"""
        try:
            query = self.client.table(self._templates_table).select('*')
            if doc_type:
                query = query.eq('doc_type', doc_type)

            response = query.order('doc_type').order('version', desc=True).execute()
            return response.data or []

        except Exception as e:
            logger.error(f"Failed to get templates: {e}")
            return []

    def save_template(self, template_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Zapisz nowy szablon (jako nowa wersja).

        Args:
            template_data: Dane szablonu (doc_type, name, content_html, styles_css, meta_json)

        Returns:
            Tuple[success, template_id]
        """
        try:
            doc_type = template_data.get('doc_type')

            # Pobierz aktualna wersje
            current = self.get_active_template(doc_type)
            new_version = (current.get('version', 0) + 1) if current else 1

            # Dezaktywuj stare
            if current:
                self.client.table(self._templates_table)\
                    .update({'is_active': False})\
                    .eq('doc_type', doc_type)\
                    .execute()

            # Zapisz nowy
            template_data['version'] = new_version
            template_data['is_active'] = True

            response = self.client.table(self._templates_table)\
                .insert(template_data)\
                .execute()

            if response.data:
                return True, response.data[0].get('id')

            return False, None

        except Exception as e:
            logger.error(f"Failed to save template: {e}")
            return False, None

    # ============================================================
    # Metadane dokumentow
    # ============================================================

    def save_document_metadata(self, metadata: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Zapisz metadane wygenerowanego dokumentu.

        Args:
            metadata: Slownik z polami documents_registry

        Returns:
            Tuple[success, document_id]
        """
        try:
            response = self.client.table(self.TABLE_NAME)\
                .insert(metadata)\
                .execute()

            if response.data:
                doc_id = response.data[0].get('id')
                logger.info(f"[Document] Saved metadata: {doc_id}")
                return True, doc_id

            return False, None

        except Exception as e:
            logger.error(f"Failed to save document metadata: {e}")
            return False, None

    def get_documents_for_entity(
        self,
        related_table: str,
        related_id: str,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Pobierz wszystkie dokumenty powiazane z encja.

        Args:
            related_table: Nazwa tabeli (np. 'orders', 'quotations')
            related_id: ID encji
            include_deleted: Czy wlaczac usuniete

        Returns:
            Lista dokumentow
        """
        try:
            query = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('related_table', related_table)\
                .eq('related_id', related_id)

            if not include_deleted:
                query = query.eq('is_deleted', False)

            response = query.order('created_at', desc=True).execute()
            return response.data or []

        except Exception as e:
            logger.error(f"Failed to get documents for entity: {e}")
            return []

    def get_documents_by_type(
        self,
        doc_type: str,
        year: int = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Pobierz dokumenty danego typu"""
        try:
            query = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('doc_type', doc_type)\
                .eq('is_deleted', False)

            if year:
                query = query.eq('year', year)

            response = query.order('created_at', desc=True).limit(limit).execute()
            return response.data or []

        except Exception as e:
            logger.error(f"Failed to get documents by type: {e}")
            return []

    def get_document_by_number(self, doc_number: str) -> Optional[Dict[str, Any]]:
        """Pobierz dokument po numerze"""
        try:
            response = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('doc_number_full', doc_number)\
                .single()\
                .execute()

            return response.data

        except Exception as e:
            if "No rows" not in str(e):
                logger.error(f"Failed to get document by number: {e}")
            return None

    def mark_as_deleted(self, document_id: str) -> bool:
        """Oznacz dokument jako usuniety (soft delete)"""
        try:
            self.client.table(self.TABLE_NAME)\
                .update({'is_deleted': True})\
                .eq('id', document_id)\
                .execute()

            logger.info(f"[Document] Marked as deleted: {document_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to mark document as deleted: {e}")
            return False


# ============================================================
# Factory Function
# ============================================================

def create_document_repository(supabase_client=None) -> DocumentRepository:
    """
    Factory function dla DocumentRepository.

    Args:
        supabase_client: Opcjonalny klient Supabase

    Returns:
        DocumentRepository instance
    """
    if supabase_client is None:
        try:
            from core.supabase_client import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Cannot create Supabase client: {e}")
            raise

    return DocumentRepository(supabase_client)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Testing DocumentRepository...")

    try:
        repo = create_document_repository()

        # Test numeracji
        seq, full_number = repo.get_next_number('TEST', 2025)
        print(f"Generated number: {full_number}")

        # Test pobierania szablonow
        templates = repo.get_all_templates()
        print(f"Templates count: {len(templates)}")

        print("\nDocumentRepository test completed!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
