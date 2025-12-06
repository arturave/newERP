"""
NewERP - Base Service
=====================
Bazowa klasa serwisu z logiką biznesową, transakcjami i eventami.
Wszystkie serwisy dziedziczą po tej klasie.
"""

from abc import ABC
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
from contextlib import contextmanager
import uuid
import logging

from supabase import Client

from core.base_repository import BaseRepository
from core.events import EventBus, Event, EventType, create_event
from core.audit import AuditService, AuditAction
from core.exceptions import (
    ValidationError,
    RequiredFieldError,
    InvalidFieldValueError,
    BusinessRuleError
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseService(ABC):
    """
    Bazowa klasa serwisu.
    
    Zapewnia:
    - Transakcje (DB + Storage jako jedna operacja)
    - Walidację danych
    - Emitowanie eventów
    - Audit trail
    - Logowanie
    
    Usage:
        class ProductService(BaseService):
            ENTITY_NAME = "Product"
            
            REQUIRED_FIELDS = ["name", "idx_code"]
            OPTIONAL_FIELDS = ["description", "category"]
            
            def __init__(self, client):
                super().__init__(client)
                self.repository = ProductRepository(client)
                self.storage = ProductStorageRepository(client)
    """
    
    # Subklasy powinny zdefiniować
    ENTITY_NAME: str = None
    
    # Pola do walidacji
    REQUIRED_FIELDS: List[str] = []
    OPTIONAL_FIELDS: List[str] = []
    
    # Mapowanie pól na typy (do walidacji)
    FIELD_TYPES: Dict[str, type] = {}
    
    # Mapowanie eventów
    EVENT_CREATE: EventType = None
    EVENT_UPDATE: EventType = None
    EVENT_DELETE: EventType = None
    
    def __init__(
        self, 
        client: Client,
        event_bus: EventBus = None,
        audit_service: AuditService = None
    ):
        self.client = client
        self.event_bus = event_bus or EventBus()
        self.audit = audit_service or AuditService(client)
        
        # Aktualny użytkownik (ustawiany przez aplikację)
        self._current_user_id: Optional[str] = None
        self._current_user_email: Optional[str] = None
        
        # Correlation ID dla grupowania operacji
        self._correlation_id: Optional[str] = None
    
    # ============================================================
    # User Context
    # ============================================================
    
    def set_user(self, user_id: str, user_email: str = None):
        """Ustaw aktualnego użytkownika (dla audytu)"""
        self._current_user_id = user_id
        self._current_user_email = user_email
    
    def clear_user(self):
        """Wyczyść użytkownika"""
        self._current_user_id = None
        self._current_user_email = None
    
    @contextmanager
    def user_context(self, user_id: str, user_email: str = None):
        """Context manager dla operacji użytkownika"""
        old_user = self._current_user_id
        old_email = self._current_user_email
        self.set_user(user_id, user_email)
        try:
            yield
        finally:
            self._current_user_id = old_user
            self._current_user_email = old_email
    
    # ============================================================
    # Correlation (Transaction Grouping)
    # ============================================================
    
    def start_correlation(self, correlation_id: str = None) -> str:
        """
        Rozpocznij grupę operacji (np. transakcję).
        Wszystkie eventy i audyt będą miały ten sam correlation_id.
        """
        self._correlation_id = correlation_id or str(uuid.uuid4())
        return self._correlation_id
    
    def end_correlation(self):
        """Zakończ grupę operacji"""
        self._correlation_id = None
    
    @contextmanager
    def correlation_context(self, correlation_id: str = None):
        """Context manager dla grupy operacji"""
        cid = self.start_correlation(correlation_id)
        try:
            yield cid
        finally:
            self.end_correlation()
    
    # ============================================================
    # Validation
    # ============================================================
    
    def validate(self, data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """
        Waliduj dane wejściowe.
        
        Args:
            data: Dane do walidacji
            is_update: True jeśli aktualizacja (nie wymaga wszystkich pól)
        
        Returns:
            Zwalidowane dane (mogą być zmodyfikowane)
        
        Raises:
            RequiredFieldError: Brak wymaganego pola
            InvalidFieldValueError: Nieprawidłowa wartość
        """
        validated = {}
        
        # Sprawdź wymagane pola
        if not is_update:
            for field in self.REQUIRED_FIELDS:
                if field not in data or data[field] is None:
                    raise RequiredFieldError(field, self.ENTITY_NAME)
        
        # Waliduj typy i kopiuj dozwolone pola
        allowed_fields = set(self.REQUIRED_FIELDS) | set(self.OPTIONAL_FIELDS)
        
        for field, value in data.items():
            # Sprawdź czy pole jest dozwolone
            if field not in allowed_fields:
                logger.warning(f"[{self.ENTITY_NAME}] Ignoring unknown field: {field}")
                continue
            
            # Sprawdź typ jeśli zdefiniowany
            if field in self.FIELD_TYPES and value is not None:
                expected_type = self.FIELD_TYPES[field]
                if not isinstance(value, expected_type):
                    try:
                        # Spróbuj skonwertować
                        value = expected_type(value)
                    except (ValueError, TypeError):
                        raise InvalidFieldValueError(
                            field, value, 
                            f"Expected {expected_type.__name__}"
                        )
            
            validated[field] = value
        
        # Wywołaj custom walidację (do nadpisania w subklasach)
        self._validate_business_rules(validated, is_update)
        
        return validated
    
    def _validate_business_rules(self, data: Dict[str, Any], is_update: bool):
        """
        Hook do walidacji reguł biznesowych.
        Subklasy mogą nadpisać.
        
        Raises:
            BusinessRuleError: Jeśli reguła naruszona
        """
        pass
    
    # ============================================================
    # Events
    # ============================================================
    
    def emit_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        **kwargs
    ):
        """Wyemituj event"""
        event = create_event(
            event_type=event_type,
            data=data,
            user_id=self._current_user_id,
            source=self.ENTITY_NAME,
            correlation_id=self._correlation_id,
            **kwargs
        )
        self.event_bus.publish(event)
    
    def emit_create_event(self, entity_id: str, data: Dict[str, Any]):
        """Wyemituj event utworzenia"""
        if self.EVENT_CREATE:
            self.emit_event(self.EVENT_CREATE, {
                "id": entity_id,
                **data
            })
    
    def emit_update_event(
        self, 
        entity_id: str, 
        old_data: Dict[str, Any], 
        new_data: Dict[str, Any]
    ):
        """Wyemituj event aktualizacji"""
        if self.EVENT_UPDATE:
            self.emit_event(self.EVENT_UPDATE, {
                "id": entity_id,
                "old": old_data,
                "new": new_data
            })
    
    def emit_delete_event(self, entity_id: str, data: Dict[str, Any]):
        """Wyemituj event usunięcia"""
        if self.EVENT_DELETE:
            self.emit_event(self.EVENT_DELETE, {
                "id": entity_id,
                **data
            })
    
    # ============================================================
    # Audit
    # ============================================================
    
    def log_audit(
        self,
        entity_id: str,
        action: AuditAction,
        old_values: dict = None,
        new_values: dict = None,
        **kwargs
    ):
        """Zapisz wpis audytu"""
        self.audit.log(
            entity_type=self.ENTITY_NAME.lower(),
            entity_id=entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            user_id=self._current_user_id,
            user_email=self._current_user_email,
            correlation_id=self._correlation_id,
            **kwargs
        )
    
    # ============================================================
    # Transaction-like Operations
    # ============================================================
    
    @contextmanager
    def transaction(self, correlation_id: str = None):
        """
        Context manager dla pseudo-transakcji.
        
        Uwaga: Supabase nie obsługuje prawdziwych transakcji przez REST API.
        Ten context manager:
        - Ustawia correlation_id
        - Loguje początek/koniec operacji
        - W razie błędu loguje rollback (ale nie cofa zmian!)
        
        Usage:
            with service.transaction() as txn_id:
                # operacje...
                pass
        """
        cid = self.start_correlation(correlation_id)
        logger.info(f"[{self.ENTITY_NAME}] Transaction started: {cid[:8]}")
        
        try:
            yield cid
            logger.info(f"[{self.ENTITY_NAME}] Transaction completed: {cid[:8]}")
        except Exception as e:
            logger.error(
                f"[{self.ENTITY_NAME}] Transaction failed: {cid[:8]} - {e}"
            )
            # Tutaj można dodać logikę rollback jeśli potrzebna
            raise
        finally:
            self.end_correlation()
    
    # ============================================================
    # Common Operations (Template Methods)
    # ============================================================
    
    def _create_with_audit(
        self,
        repository: BaseRepository,
        data: Dict[str, Any],
        event_type: EventType = None
    ) -> Dict[str, Any]:
        """
        Template method dla create z audytem i eventami.
        """
        # Walidacja
        validated = self.validate(data)
        
        # Utwórz
        record = repository.create(validated)
        entity_id = record.get('id')
        
        # Audit
        self.log_audit(entity_id, AuditAction.CREATE, new_values=validated)
        
        # Event
        if event_type:
            self.emit_event(event_type, {"id": entity_id, **record})
        
        return record
    
    def _update_with_audit(
        self,
        repository: BaseRepository,
        entity_id: str,
        data: Dict[str, Any],
        expected_version: int = None,
        event_type: EventType = None
    ) -> Dict[str, Any]:
        """
        Template method dla update z audytem i eventami.
        """
        # Pobierz stary stan
        old_record = repository.get_by_id_or_raise(entity_id)
        
        # Walidacja
        validated = self.validate(data, is_update=True)
        
        # Aktualizuj
        new_record = repository.update(entity_id, validated, expected_version)
        
        # Audit
        self.log_audit(
            entity_id, 
            AuditAction.UPDATE,
            old_values=old_record,
            new_values=new_record
        )
        
        # Event
        if event_type:
            self.emit_event(event_type, {
                "id": entity_id,
                "old": old_record,
                "new": new_record
            })
        
        return new_record
    
    def _delete_with_audit(
        self,
        repository: BaseRepository,
        entity_id: str,
        hard: bool = False,
        event_type: EventType = None
    ) -> bool:
        """
        Template method dla delete z audytem i eventami.
        """
        # Pobierz dane przed usunięciem
        record = repository.get_by_id_or_raise(entity_id)
        
        # Usuń
        result = repository.delete(entity_id, hard=hard)
        
        # Audit
        self.log_audit(entity_id, AuditAction.DELETE, old_values=record)
        
        # Event
        if event_type:
            self.emit_event(event_type, {"id": entity_id, **record})
        
        return result
    
    # ============================================================
    # Utility Methods
    # ============================================================
    
    def get_history(self, entity_id: str) -> List[dict]:
        """Pobierz historię zmian encji"""
        return self.audit.get_history(
            self.ENTITY_NAME.lower(), 
            entity_id
        )
    
    @staticmethod
    def generate_code(prefix: str, sequence: int, width: int = 6) -> str:
        """
        Generuj kod/numer z prefiksem i sekwencją.
        
        Examples:
            generate_code("PRD", 1) -> "PRD000001"
            generate_code("ZP/2025", 123, 4) -> "ZP/2025/0123"
        """
        return f"{prefix}{str(sequence).zfill(width)}"


class ServiceRegistry:
    """
    Rejestr serwisów - singleton do zarządzania wszystkimi serwisami.
    
    Usage:
        registry = ServiceRegistry.get_instance()
        registry.register("products", ProductService(client))
        
        products = registry.get("products")
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._services: Dict[str, BaseService] = {}
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'ServiceRegistry':
        return cls()
    
    @classmethod
    def reset(cls):
        """Reset (do testów)"""
        cls._instance = None
    
    def register(self, name: str, service: BaseService):
        """Zarejestruj serwis"""
        self._services[name] = service
        logger.debug(f"[ServiceRegistry] Registered: {name}")
    
    def get(self, name: str) -> Optional[BaseService]:
        """Pobierz serwis po nazwie"""
        return self._services.get(name)
    
    def get_all(self) -> Dict[str, BaseService]:
        """Pobierz wszystkie serwisy"""
        return self._services.copy()
    
    def set_user_for_all(self, user_id: str, user_email: str = None):
        """Ustaw użytkownika we wszystkich serwisach"""
        for service in self._services.values():
            service.set_user(user_id, user_email)
    
    def clear_user_for_all(self):
        """Wyczyść użytkownika we wszystkich serwisach"""
        for service in self._services.values():
            service.clear_user()
