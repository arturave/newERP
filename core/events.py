"""
NewERP - Event Bus
==================
Prosty event bus dla komunikacji między modułami.
Umożliwia loose coupling - moduły nie znają się nawzajem.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
import uuid
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Typy zdarzeń w systemie"""
    
    # ========== Product Events ==========
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_DELETED = "product.deleted"
    PRODUCT_RESTORED = "product.restored"
    PRODUCT_FILE_UPLOADED = "product.file_uploaded"
    PRODUCT_FILE_DELETED = "product.file_deleted"
    
    # ========== Customer Events ==========
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    CUSTOMER_DELETED = "customer.deleted"
    CUSTOMER_RESTORED = "customer.restored"
    
    # ========== Order Events ==========
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_PRODUCTION_STARTED = "order.production_started"
    ORDER_PRODUCTION_COMPLETED = "order.production_completed"
    ORDER_SHIPPED = "order.shipped"
    ORDER_INVOICED = "order.invoiced"
    ORDER_PAID = "order.paid"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_DELETED = "order.deleted"
    
    # ========== Order Item Events ==========
    ORDER_ITEM_ADDED = "order_item.added"
    ORDER_ITEM_UPDATED = "order_item.updated"
    ORDER_ITEM_REMOVED = "order_item.removed"
    ORDER_ITEM_PRODUCED = "order_item.produced"
    
    # ========== Quotation Events ==========
    QUOTATION_CREATED = "quotation.created"
    QUOTATION_UPDATED = "quotation.updated"
    QUOTATION_SENT = "quotation.sent"
    QUOTATION_ACCEPTED = "quotation.accepted"
    QUOTATION_REJECTED = "quotation.rejected"
    QUOTATION_EXPIRED = "quotation.expired"
    QUOTATION_CONVERTED = "quotation.converted_to_order"
    
    # ========== Material Events ==========
    MATERIAL_CREATED = "material.created"
    MATERIAL_UPDATED = "material.updated"
    MATERIAL_PRICE_CHANGED = "material.price_changed"
    
    # ========== Attachment Events ==========
    ATTACHMENT_UPLOADED = "attachment.uploaded"
    ATTACHMENT_DELETED = "attachment.deleted"
    
    # ========== Document Events ==========
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_GENERATED = "document.generated"
    DOCUMENT_ARCHIVED = "document.archived"
    DOCUMENT_DELETED = "document.deleted"
    WZ_GENERATED = "document.wz_generated"
    INVOICE_GENERATED = "document.invoice_generated"
    QUOTATION_PDF_GENERATED = "document.quotation_generated"
    CMR_GENERATED = "document.cmr_generated"
    PACKING_LIST_GENERATED = "document.packing_list_generated"
    
    # ========== System Events ==========
    USER_LOGGED_IN = "system.user_logged_in"
    USER_LOGGED_OUT = "system.user_logged_out"
    SETTINGS_CHANGED = "system.settings_changed"
    ERROR_OCCURRED = "system.error_occurred"


@dataclass
class Event:
    """
    Zdarzenie w systemie.
    
    Attributes:
        type: Typ zdarzenia
        data: Dane zdarzenia (payload)
        timestamp: Czas wystąpienia
        event_id: Unikalny identyfikator zdarzenia
        correlation_id: ID do grupowania powiązanych zdarzeń
        user_id: ID użytkownika który wywołał zdarzenie
        source: Moduł źródłowy
    """
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    source: Optional[str] = None
    
    def __post_init__(self):
        # Jeśli correlation_id nie podany, użyj event_id
        if self.correlation_id is None:
            self.correlation_id = self.event_id
    
    def to_dict(self) -> dict:
        """Konwersja do słownika (np. do logowania)"""
        return {
            "event_id": self.event_id,
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "source": self.source
        }


# Type alias dla handlera
EventHandler = Callable[[Event], None]


class EventBus:
    """
    Singleton Event Bus dla komunikacji między modułami.
    
    Użycie:
        # Subskrypcja
        event_bus = EventBus()
        event_bus.subscribe(EventType.ORDER_CREATED, handle_new_order)
        
        # Publikacja
        event_bus.publish(Event(
            type=EventType.ORDER_CREATED,
            data={"order_id": "123", "customer_id": "456"}
        ))
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers: Dict[EventType, List[EventHandler]] = {}
            cls._instance._global_handlers: List[EventHandler] = []
            cls._instance._enabled = True
        return cls._instance
    
    @classmethod
    def reset(cls):
        """Reset singletona (głównie do testów)"""
        cls._instance = None
    
    def subscribe(
        self, 
        event_type: EventType, 
        handler: EventHandler,
        priority: int = 0
    ) -> None:
        """
        Subskrybuj handler na konkretny typ zdarzenia.
        
        Args:
            event_type: Typ zdarzenia do nasłuchiwania
            handler: Funkcja obsługująca zdarzenie
            priority: Priorytet (wyższy = wcześniej wywołany)
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        # Dodaj z priorytetem
        self._handlers[event_type].append((priority, handler))
        # Sortuj po priorytecie (malejąco)
        self._handlers[event_type].sort(key=lambda x: x[0], reverse=True)
        
        logger.debug(f"[EventBus] Subscribed handler to {event_type.value}")
    
    def subscribe_all(self, handler: EventHandler) -> None:
        """
        Subskrybuj handler na WSZYSTKIE zdarzenia.
        Przydatne do logowania, audytu, debugowania.
        """
        self._global_handlers.append(handler)
        logger.debug("[EventBus] Subscribed global handler")
    
    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> bool:
        """
        Odsubskrybuj handler.
        
        Returns:
            True jeśli handler został usunięty, False jeśli nie znaleziono
        """
        if event_type not in self._handlers:
            return False
        
        original_count = len(self._handlers[event_type])
        self._handlers[event_type] = [
            (p, h) for p, h in self._handlers[event_type] 
            if h != handler
        ]
        
        removed = len(self._handlers[event_type]) < original_count
        if removed:
            logger.debug(f"[EventBus] Unsubscribed handler from {event_type.value}")
        return removed
    
    def publish(self, event: Event) -> None:
        """
        Opublikuj zdarzenie.
        
        Wszystkie handlery są wywoływane synchronicznie.
        Błąd w jednym handlerze nie blokuje pozostałych.
        """
        if not self._enabled:
            logger.debug(f"[EventBus] Disabled, skipping {event.type.value}")
            return
        
        logger.info(f"[EventBus] Publishing: {event.type.value} | ID: {event.event_id[:8]}")
        
        # Wywołaj handlery specyficzne dla typu
        handlers = self._handlers.get(event.type, [])
        for priority, handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"[EventBus] Handler error for {event.type.value}: {e}",
                    exc_info=True
                )
        
        # Wywołaj globalne handlery
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"[EventBus] Global handler error: {e}", exc_info=True)
    
    def publish_many(self, events: List[Event]) -> None:
        """Opublikuj wiele zdarzeń"""
        for event in events:
            self.publish(event)
    
    def enable(self) -> None:
        """Włącz event bus"""
        self._enabled = True
        logger.info("[EventBus] Enabled")
    
    def disable(self) -> None:
        """Wyłącz event bus (zdarzenia nie będą publikowane)"""
        self._enabled = False
        logger.info("[EventBus] Disabled")
    
    def clear(self) -> None:
        """Usuń wszystkie handlery"""
        self._handlers.clear()
        self._global_handlers.clear()
        logger.info("[EventBus] Cleared all handlers")
    
    def get_handler_count(self, event_type: EventType = None) -> int:
        """Zwróć liczbę handlerów"""
        if event_type:
            return len(self._handlers.get(event_type, []))
        return sum(len(h) for h in self._handlers.values()) + len(self._global_handlers)


# ============================================================
# Helper Functions
# ============================================================

def create_event(
    event_type: EventType,
    data: Dict[str, Any],
    user_id: str = None,
    source: str = None,
    correlation_id: str = None
) -> Event:
    """
    Helper do tworzenia zdarzeń.
    
    Usage:
        event = create_event(
            EventType.ORDER_CREATED,
            {"order_id": "123"},
            user_id="user_456"
        )
    """
    return Event(
        type=event_type,
        data=data,
        user_id=user_id,
        source=source,
        correlation_id=correlation_id
    )


def get_event_bus() -> EventBus:
    """Pobierz instancję Event Bus"""
    return EventBus()


# ============================================================
# Decorators
# ============================================================

def on_event(event_type: EventType, priority: int = 0):
    """
    Dekorator do rejestracji handlerów.
    
    Usage:
        @on_event(EventType.ORDER_CREATED)
        def handle_new_order(event: Event):
            print(f"New order: {event.data['order_id']}")
    """
    def decorator(func):
        EventBus().subscribe(event_type, func, priority)
        return func
    return decorator


def on_all_events():
    """
    Dekorator do rejestracji globalnego handlera.
    
    Usage:
        @on_all_events()
        def log_all_events(event: Event):
            print(f"Event: {event.type.value}")
    """
    def decorator(func):
        EventBus().subscribe_all(func)
        return func
    return decorator


# ============================================================
# Built-in Handlers
# ============================================================

def logging_handler(event: Event) -> None:
    """Handler logujący wszystkie zdarzenia"""
    logger.info(
        f"[EVENT] {event.type.value} | "
        f"ID: {event.event_id[:8]} | "
        f"User: {event.user_id or 'system'} | "
        f"Data: {event.data}"
    )


def setup_event_logging():
    """Włącz logowanie wszystkich zdarzeń"""
    EventBus().subscribe_all(logging_handler)
