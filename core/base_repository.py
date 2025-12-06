"""
NewERP - Base Repository
========================
Bazowa klasa repozytorium z CRUD, soft delete, optimistic locking.
Wszystkie repozytoria dziedziczą po tej klasie.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
import logging

from supabase import Client

from core.exceptions import (
    RecordNotFoundError,
    DuplicateRecordError,
    OptimisticLockError,
    DatabaseError
)
from core.filters import QueryParams, QueryBuilder, Filter, FilterOperator

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='BaseRepository')


class BaseRepository(ABC):
    """
    Bazowa klasa repozytorium.
    
    Zapewnia:
    - CRUD operations
    - Soft delete (is_active + deleted_at)
    - Optimistic locking (version)
    - Bulk operations
    - Query builder integration
    
    Usage:
        class ProductRepository(BaseRepository):
            TABLE_NAME = "products_catalog"
            ENTITY_NAME = "Product"
            
            # Opcjonalnie - pola do wyszukiwania
            SEARCH_FIELDS = ["name", "idx_code", "description"]
    """
    
    # Subklasy muszą zdefiniować
    TABLE_NAME: str = None
    ENTITY_NAME: str = None
    
    # Opcjonalne konfiguracje
    SEARCH_FIELDS: List[str] = []
    UNIQUE_FIELDS: List[str] = []  # Pola z unique constraint
    
    # Domyślne kolumny
    ID_COLUMN = "id"
    VERSION_COLUMN = "version"
    IS_ACTIVE_COLUMN = "is_active"
    DELETED_AT_COLUMN = "deleted_at"
    CREATED_AT_COLUMN = "created_at"
    UPDATED_AT_COLUMN = "updated_at"
    
    def __init__(self, client: Client):
        self.client = client
        
        # Walidacja
        if not self.TABLE_NAME:
            raise ValueError(f"{self.__class__.__name__} must define TABLE_NAME")
        if not self.ENTITY_NAME:
            self.ENTITY_NAME = self.TABLE_NAME
    
    # ============================================================
    # Core CRUD Operations
    # ============================================================
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Utwórz nowy rekord.
        
        Args:
            data: Dane do zapisania (bez id, created_at, itp.)
        
        Returns:
            Utworzony rekord z id
        
        Raises:
            DuplicateRecordError: Jeśli narusza unique constraint
            DatabaseError: Inne błędy bazy
        """
        try:
            # Dodaj domyślne wartości
            data.setdefault(self.IS_ACTIVE_COLUMN, True)
            data.setdefault(self.VERSION_COLUMN, 1)
            
            response = self.client.table(self.TABLE_NAME)\
                .insert(data)\
                .execute()
            
            if response.data:
                record = response.data[0]
                logger.info(f"[{self.ENTITY_NAME}] Created: {record.get(self.ID_COLUMN)}")
                return record
            
            raise DatabaseError(f"Failed to create {self.ENTITY_NAME}")
            
        except Exception as e:
            error_msg = str(e)
            
            # Sprawdź unique constraint violation
            if "duplicate key" in error_msg or "unique constraint" in error_msg.lower():
                # Spróbuj wykryć które pole
                for field in self.UNIQUE_FIELDS:
                    if field in error_msg:
                        raise DuplicateRecordError(
                            self.ENTITY_NAME, 
                            field, 
                            str(data.get(field, ''))
                        )
                raise DuplicateRecordError(self.ENTITY_NAME, "unknown", "")
            
            logger.error(f"[{self.ENTITY_NAME}] Create failed: {e}")
            raise DatabaseError(f"Failed to create {self.ENTITY_NAME}: {e}")
    
    def get_by_id(
        self, 
        id: str, 
        include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Pobierz rekord po ID.
        
        Args:
            id: ID rekordu
            include_deleted: Czy włączyć soft-deleted
        
        Returns:
            Rekord lub None jeśli nie znaleziono
        """
        try:
            query = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq(self.ID_COLUMN, id)
            
            if not include_deleted:
                query = query.eq(self.IS_ACTIVE_COLUMN, True)
            
            response = query.single().execute()
            return response.data
            
        except Exception as e:
            if "No rows" in str(e) or "0 rows" in str(e):
                return None
            logger.error(f"[{self.ENTITY_NAME}] Get by ID failed: {e}")
            return None
    
    def get_by_id_or_raise(
        self, 
        id: str, 
        include_deleted: bool = False
    ) -> Dict[str, Any]:
        """
        Pobierz rekord po ID lub rzuć wyjątek.
        
        Raises:
            RecordNotFoundError: Jeśli nie znaleziono
        """
        record = self.get_by_id(id, include_deleted)
        if not record:
            raise RecordNotFoundError(self.ENTITY_NAME, id)
        return record
    
    def update(
        self, 
        id: str, 
        data: Dict[str, Any],
        expected_version: int = None
    ) -> Dict[str, Any]:
        """
        Aktualizuj rekord.
        
        Args:
            id: ID rekordu
            data: Dane do aktualizacji
            expected_version: Oczekiwana wersja (optimistic locking)
        
        Returns:
            Zaktualizowany rekord
        
        Raises:
            RecordNotFoundError: Jeśli nie znaleziono
            OptimisticLockError: Jeśli wersja się nie zgadza
        """
        try:
            # Pobierz aktualny rekord
            current = self.get_by_id_or_raise(id)
            
            # Sprawdź wersję (optimistic locking)
            if expected_version is not None:
                current_version = current.get(self.VERSION_COLUMN, 1)
                if current_version != expected_version:
                    raise OptimisticLockError(
                        self.ENTITY_NAME, id, expected_version
                    )
            
            # Przygotuj dane
            data[self.UPDATED_AT_COLUMN] = datetime.now().isoformat()
            data[self.VERSION_COLUMN] = current.get(self.VERSION_COLUMN, 1) + 1
            
            # Usuń pola których nie można aktualizować
            data.pop(self.ID_COLUMN, None)
            data.pop(self.CREATED_AT_COLUMN, None)
            
            response = self.client.table(self.TABLE_NAME)\
                .update(data)\
                .eq(self.ID_COLUMN, id)\
                .execute()
            
            if response.data:
                logger.info(f"[{self.ENTITY_NAME}] Updated: {id}")
                return response.data[0]
            
            raise DatabaseError(f"Failed to update {self.ENTITY_NAME}")
            
        except (RecordNotFoundError, OptimisticLockError):
            raise
        except Exception as e:
            logger.error(f"[{self.ENTITY_NAME}] Update failed: {e}")
            raise DatabaseError(f"Failed to update {self.ENTITY_NAME}: {e}")
    
    def delete(self, id: str, hard: bool = False) -> bool:
        """
        Usuń rekord (domyślnie soft delete).
        
        Args:
            id: ID rekordu
            hard: True = fizyczne usunięcie, False = soft delete
        
        Returns:
            True jeśli usunięto
        
        Raises:
            RecordNotFoundError: Jeśli nie znaleziono
        """
        try:
            # Sprawdź czy istnieje
            self.get_by_id_or_raise(id)
            
            if hard:
                # Hard delete
                self.client.table(self.TABLE_NAME)\
                    .delete()\
                    .eq(self.ID_COLUMN, id)\
                    .execute()
                logger.info(f"[{self.ENTITY_NAME}] Hard deleted: {id}")
            else:
                # Soft delete
                self.client.table(self.TABLE_NAME)\
                    .update({
                        self.IS_ACTIVE_COLUMN: False,
                        self.DELETED_AT_COLUMN: datetime.now().isoformat(),
                        self.UPDATED_AT_COLUMN: datetime.now().isoformat()
                    })\
                    .eq(self.ID_COLUMN, id)\
                    .execute()
                logger.info(f"[{self.ENTITY_NAME}] Soft deleted: {id}")
            
            return True
            
        except RecordNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[{self.ENTITY_NAME}] Delete failed: {e}")
            raise DatabaseError(f"Failed to delete {self.ENTITY_NAME}: {e}")
    
    def restore(self, id: str) -> Dict[str, Any]:
        """
        Przywróć soft-deleted rekord.
        
        Returns:
            Przywrócony rekord
        """
        try:
            # Pobierz (włącznie z deleted)
            record = self.get_by_id(id, include_deleted=True)
            if not record:
                raise RecordNotFoundError(self.ENTITY_NAME, id)
            
            if record.get(self.IS_ACTIVE_COLUMN):
                return record  # Już aktywny
            
            response = self.client.table(self.TABLE_NAME)\
                .update({
                    self.IS_ACTIVE_COLUMN: True,
                    self.DELETED_AT_COLUMN: None,
                    self.UPDATED_AT_COLUMN: datetime.now().isoformat()
                })\
                .eq(self.ID_COLUMN, id)\
                .execute()
            
            if response.data:
                logger.info(f"[{self.ENTITY_NAME}] Restored: {id}")
                return response.data[0]
            
            raise DatabaseError(f"Failed to restore {self.ENTITY_NAME}")
            
        except RecordNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[{self.ENTITY_NAME}] Restore failed: {e}")
            raise DatabaseError(f"Failed to restore {self.ENTITY_NAME}: {e}")
    
    # ============================================================
    # Query Methods
    # ============================================================
    
    def list(
        self,
        params: QueryParams = None,
        include_deleted: bool = False
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Pobierz listę rekordów z filtrami.
        
        Args:
            params: Parametry zapytania
            include_deleted: Czy włączyć soft-deleted
        
        Returns:
            Tuple[List[dict], int]: (rekordy, total_count)
        """
        if params is None:
            params = QueryParams()
        
        params.include_deleted = include_deleted
        
        # Użyj search_fields z klasy jeśli nie podano
        if params.search and not params.search_fields:
            params.search_fields = self.SEARCH_FIELDS
        
        builder = QueryBuilder(self.client, self.TABLE_NAME)
        return builder.apply(params).execute()
    
    def find_one(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Znajdź jeden rekord po polach.
        
        Usage:
            product = repo.find_one(idx_code="ABC123")
        """
        params = QueryParams()
        for field, value in kwargs.items():
            params.filters.append(Filter(field, FilterOperator.EQ, value))
        params.pagination.limit = 1
        
        records, _ = self.list(params)
        return records[0] if records else None
    
    def find_many(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Znajdź wiele rekordów po polach.
        
        Usage:
            products = repo.find_many(category="laser", is_active=True)
        """
        params = QueryParams()
        for field, value in kwargs.items():
            params.filters.append(Filter(field, FilterOperator.EQ, value))
        
        records, _ = self.list(params)
        return records
    
    def exists(self, id: str) -> bool:
        """Sprawdź czy rekord istnieje"""
        return self.get_by_id(id) is not None
    
    def count(self, params: QueryParams = None) -> int:
        """Policz rekordy spełniające kryteria"""
        _, count = self.list(params)
        return count
    
    # ============================================================
    # Bulk Operations
    # ============================================================
    
    def create_many(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Utwórz wiele rekordów jednocześnie.
        
        Args:
            records: Lista rekordów do utworzenia
        
        Returns:
            Lista utworzonych rekordów
        """
        if not records:
            return []
        
        try:
            # Dodaj domyślne wartości
            for data in records:
                data.setdefault(self.IS_ACTIVE_COLUMN, True)
                data.setdefault(self.VERSION_COLUMN, 1)
            
            response = self.client.table(self.TABLE_NAME)\
                .insert(records)\
                .execute()
            
            if response.data:
                logger.info(f"[{self.ENTITY_NAME}] Bulk created: {len(response.data)} records")
                return response.data
            
            return []
            
        except Exception as e:
            logger.error(f"[{self.ENTITY_NAME}] Bulk create failed: {e}")
            raise DatabaseError(f"Failed to bulk create {self.ENTITY_NAME}: {e}")
    
    def update_many(
        self, 
        ids: List[str], 
        data: Dict[str, Any]
    ) -> int:
        """
        Aktualizuj wiele rekordów.
        
        Args:
            ids: Lista ID do aktualizacji
            data: Dane do ustawienia
        
        Returns:
            Liczba zaktualizowanych rekordów
        """
        if not ids:
            return 0
        
        try:
            data[self.UPDATED_AT_COLUMN] = datetime.now().isoformat()
            
            response = self.client.table(self.TABLE_NAME)\
                .update(data)\
                .in_(self.ID_COLUMN, ids)\
                .execute()
            
            count = len(response.data) if response.data else 0
            logger.info(f"[{self.ENTITY_NAME}] Bulk updated: {count} records")
            return count
            
        except Exception as e:
            logger.error(f"[{self.ENTITY_NAME}] Bulk update failed: {e}")
            raise DatabaseError(f"Failed to bulk update {self.ENTITY_NAME}: {e}")
    
    def delete_many(self, ids: List[str], hard: bool = False) -> int:
        """
        Usuń wiele rekordów.
        
        Args:
            ids: Lista ID do usunięcia
            hard: True = fizyczne usunięcie
        
        Returns:
            Liczba usuniętych rekordów
        """
        if not ids:
            return 0
        
        try:
            if hard:
                response = self.client.table(self.TABLE_NAME)\
                    .delete()\
                    .in_(self.ID_COLUMN, ids)\
                    .execute()
                logger.info(f"[{self.ENTITY_NAME}] Bulk hard deleted: {len(ids)} records")
            else:
                response = self.client.table(self.TABLE_NAME)\
                    .update({
                        self.IS_ACTIVE_COLUMN: False,
                        self.DELETED_AT_COLUMN: datetime.now().isoformat()
                    })\
                    .in_(self.ID_COLUMN, ids)\
                    .execute()
                logger.info(f"[{self.ENTITY_NAME}] Bulk soft deleted: {len(ids)} records")
            
            return len(response.data) if response.data else 0
            
        except Exception as e:
            logger.error(f"[{self.ENTITY_NAME}] Bulk delete failed: {e}")
            raise DatabaseError(f"Failed to bulk delete {self.ENTITY_NAME}: {e}")
    
    # ============================================================
    # Utility Methods
    # ============================================================
    
    def get_all_ids(self, include_deleted: bool = False) -> List[str]:
        """Pobierz wszystkie ID"""
        query = self.client.table(self.TABLE_NAME)\
            .select(self.ID_COLUMN)
        
        if not include_deleted:
            query = query.eq(self.IS_ACTIVE_COLUMN, True)
        
        response = query.execute()
        return [r[self.ID_COLUMN] for r in (response.data or [])]
    
    def get_deleted(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Pobierz usunięte rekordy (do przywrócenia)"""
        response = self.client.table(self.TABLE_NAME)\
            .select('*')\
            .eq(self.IS_ACTIVE_COLUMN, False)\
            .not_.is_(self.DELETED_AT_COLUMN, 'null')\
            .order(self.DELETED_AT_COLUMN, desc=True)\
            .limit(limit)\
            .execute()
        
        return response.data or []
    
    def raw_query(self, query_builder_func) -> Any:
        """
        Wykonaj surowe zapytanie (dla zaawansowanych przypadków).
        
        Usage:
            def custom_query(table):
                return table.select('id, name').eq('status', 'active')
            
            result = repo.raw_query(custom_query)
        """
        table = self.client.table(self.TABLE_NAME)
        query = query_builder_func(table)
        return query.execute()
