"""
NewERP - Cost Events
====================
System eventów dla automatycznego przeliczania kosztów.

Każda zmiana parametru kosztowego emituje event, który wywołuje
przeliczenie kosztów w czasie < 0.1s.

Obsługiwane eventy:
- PARAM_CHANGED: zmiana parametru (markup, allocation model, checkboxes)
- PART_ADDED: dodanie części
- PART_REMOVED: usunięcie części
- PART_EDITED: edycja części (qty, bends, manual L+M)
- NESTING_COMPLETED: zakończenie nestingu
- RECALC_REQUEST: żądanie ręcznego przeliczenia
"""

import time
import logging
import threading
from enum import Enum
from typing import Callable, List, Dict, Any, Optional
from dataclasses import dataclass, field
from queue import Queue
from functools import wraps

logger = logging.getLogger(__name__)


class CostEventType(Enum):
    """Typy eventów kosztowych"""
    PARAM_CHANGED = "param_changed"        # Zmiana parametru kosztowego
    ALLOCATION_CHANGED = "allocation_changed"  # Zmiana modelu alokacji
    PART_ADDED = "part_added"              # Dodanie części
    PART_REMOVED = "part_removed"          # Usunięcie części
    PART_EDITED = "part_edited"            # Edycja części
    NESTING_COMPLETED = "nesting_completed"  # Zakończenie nestingu
    RECALC_REQUEST = "recalc_request"      # Żądanie przeliczenia
    SHEET_CHANGED = "sheet_changed"        # Zmiana danych arkusza


@dataclass
class CostEvent:
    """Event kosztowy"""
    event_type: CostEventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: str = ""

    def __repr__(self):
        return f"CostEvent({self.event_type.value}, source={self.source}, data_keys={list(self.data.keys())})"


class CostEventBus:
    """
    Magistrala eventów kosztowych.

    Zapewnia:
    - Publikowanie eventów
    - Subskrypcja na typy eventów
    - Debouncing (grupowanie szybkich zmian)
    - Async processing (opcjonalnie)

    Wymaganie: obsługa eventu < 0.1s
    """

    def __init__(self, debounce_ms: int = 50):
        """
        Args:
            debounce_ms: Czas debounce w ms (grupowanie szybkich zmian)
        """
        self._subscribers: Dict[CostEventType, List[Callable]] = {}
        self._global_subscribers: List[Callable] = []
        self._debounce_ms = debounce_ms
        self._pending_events: Queue = Queue()
        self._debounce_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._processing = False

        # Statystyki
        self._event_count = 0
        self._total_processing_time_ms = 0.0

    def subscribe(self, event_type: CostEventType, callback: Callable[[CostEvent], None]):
        """
        Subskrybuj na określony typ eventu.

        Args:
            event_type: Typ eventu
            callback: Funkcja wywoływana z CostEvent
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.debug(f"[EventBus] Subscribed to {event_type.value}: {callback.__name__}")

    def subscribe_all(self, callback: Callable[[CostEvent], None]):
        """Subskrybuj na wszystkie eventy"""
        self._global_subscribers.append(callback)
        logger.debug(f"[EventBus] Global subscriber added: {callback.__name__}")

    def unsubscribe(self, event_type: CostEventType, callback: Callable):
        """Anuluj subskrypcję"""
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)

    def emit(self, event_type: CostEventType, data: Dict = None, source: str = ""):
        """
        Emituj event kosztowy.

        Event jest debounce'owany - jeśli w krótkim czasie przyjdzie
        wiele eventów, zostaną zgrupowane.

        Args:
            event_type: Typ eventu
            data: Dane eventu
            source: Źródło eventu (dla debugowania)
        """
        event = CostEvent(
            event_type=event_type,
            data=data or {},
            source=source
        )

        logger.debug(f"[EventBus] Event emitted: {event}")

        with self._lock:
            self._pending_events.put(event)

            # Restart debounce timer
            if self._debounce_timer:
                self._debounce_timer.cancel()

            self._debounce_timer = threading.Timer(
                self._debounce_ms / 1000.0,
                self._process_pending
            )
            self._debounce_timer.start()

    def emit_immediate(self, event_type: CostEventType, data: Dict = None, source: str = ""):
        """Emituj event bez debounce (natychmiastowe przetworzenie)"""
        event = CostEvent(
            event_type=event_type,
            data=data or {},
            source=source
        )
        self._dispatch(event)

    def _process_pending(self):
        """Przetwórz oczekujące eventy"""
        if self._processing:
            return

        self._processing = True
        start_time = time.perf_counter()

        try:
            # Zbierz wszystkie oczekujące eventy
            events = []
            while not self._pending_events.empty():
                events.append(self._pending_events.get_nowait())

            if not events:
                return

            # Deduplikacja: jeśli jest RECALC_REQUEST, wystarczy jeden
            has_recalc = any(e.event_type == CostEventType.RECALC_REQUEST for e in events)

            if has_recalc:
                # Jeden event przeliczenia zastępuje wszystkie
                self._dispatch(CostEvent(
                    event_type=CostEventType.RECALC_REQUEST,
                    data={'merged_events': len(events)},
                    source='debounce'
                ))
            else:
                # Dispatch wszystkich unikalnych eventów
                seen = set()
                for event in events:
                    key = (event.event_type, str(event.data))
                    if key not in seen:
                        seen.add(key)
                        self._dispatch(event)

            # Statystyki
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._event_count += len(events)
            self._total_processing_time_ms += elapsed_ms

            if elapsed_ms > 100:
                logger.warning(f"[EventBus] Slow processing: {elapsed_ms:.1f}ms for {len(events)} events")
            else:
                logger.debug(f"[EventBus] Processed {len(events)} events in {elapsed_ms:.1f}ms")

        finally:
            self._processing = False

    def _dispatch(self, event: CostEvent):
        """Wyślij event do subskrybentów"""
        # Subskrybenci dla konkretnego typu
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"[EventBus] Callback error: {e}", exc_info=True)

        # Globalni subskrybenci
        for callback in self._global_subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"[EventBus] Global callback error: {e}", exc_info=True)

    def get_stats(self) -> Dict:
        """Pobierz statystyki"""
        avg_time = (
            self._total_processing_time_ms / self._event_count
            if self._event_count > 0 else 0
        )
        return {
            'event_count': self._event_count,
            'total_processing_time_ms': self._total_processing_time_ms,
            'avg_processing_time_ms': avg_time,
        }


# ============================================================
# DECORATORS
# ============================================================

def triggers_recalc(event_type: CostEventType = CostEventType.PART_EDITED):
    """
    Dekorator: metoda wywołuje przeliczenie kosztów.

    Użycie:
        @triggers_recalc(CostEventType.PART_EDITED)
        def _on_cell_edit(self, row, col, value):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)

            # Emituj event jeśli obiekt ma event_bus
            if hasattr(self, 'cost_event_bus') and self.cost_event_bus:
                self.cost_event_bus.emit(
                    event_type,
                    data={'method': func.__name__, 'args': str(args)[:100]},
                    source=self.__class__.__name__
                )

            return result
        return wrapper
    return decorator


def debounced(delay_ms: int = 100):
    """
    Dekorator: debounce wywołań metody.

    Użycie:
        @debounced(delay_ms=100)
        def _recalculate(self):
            ...
    """
    def decorator(func):
        timer = [None]  # Mutable container

        @wraps(func)
        def wrapper(*args, **kwargs):
            def call():
                timer[0] = None
                func(*args, **kwargs)

            if timer[0]:
                timer[0].cancel()

            timer[0] = threading.Timer(delay_ms / 1000.0, call)
            timer[0].start()

        return wrapper
    return decorator


# ============================================================
# RECALC HANDLER
# ============================================================

class RecalcHandler:
    """
    Handler przeliczania kosztów.

    Łączy EventBus z CostEngine i GUI.
    """

    def __init__(self, cost_engine=None, event_bus: CostEventBus = None):
        self.cost_engine = cost_engine
        self.event_bus = event_bus or CostEventBus()

        # Callbacki do aktualizacji GUI
        self._on_parts_updated: Optional[Callable] = None
        self._on_summary_updated: Optional[Callable] = None

        # Subskrybuj na eventy
        self.event_bus.subscribe_all(self._on_event)

    def set_cost_engine(self, engine):
        """Ustaw silnik kosztów"""
        self.cost_engine = engine

    def on_parts_updated(self, callback: Callable[[List[Dict]], None]):
        """Ustaw callback dla aktualizacji części"""
        self._on_parts_updated = callback

    def on_summary_updated(self, callback: Callable[[Dict], None]):
        """Ustaw callback dla aktualizacji podsumowania"""
        self._on_summary_updated = callback

    def _on_event(self, event: CostEvent):
        """Handler wszystkich eventów"""
        logger.debug(f"[RecalcHandler] Received: {event}")

        # Wszystkie eventy wyzwalają przeliczenie
        if self.cost_engine:
            # Tu byłoby wywołanie przeliczenia
            # self.cost_engine.recalculate_all(...)
            pass

    def request_recalc(self):
        """Żądaj przeliczenia"""
        self.event_bus.emit_immediate(
            CostEventType.RECALC_REQUEST,
            source='RecalcHandler'
        )


# ============================================================
# SINGLETON
# ============================================================

_cost_event_bus: Optional[CostEventBus] = None


def get_cost_event_bus() -> CostEventBus:
    """Pobierz globalną instancję EventBus"""
    global _cost_event_bus
    if _cost_event_bus is None:
        _cost_event_bus = CostEventBus(debounce_ms=50)
    return _cost_event_bus


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    bus = CostEventBus(debounce_ms=100)

    def on_recalc(event):
        print(f"RECALC triggered: {event}")

    def on_part_edit(event):
        print(f"Part edited: {event.data}")

    bus.subscribe(CostEventType.RECALC_REQUEST, on_recalc)
    bus.subscribe(CostEventType.PART_EDITED, on_part_edit)

    # Symulacja szybkich edycji
    print("Emitting 10 rapid events...")
    for i in range(10):
        bus.emit(CostEventType.PART_EDITED, {'row': i, 'value': i * 10})
        time.sleep(0.01)  # 10ms między eventami

    # Poczekaj na debounce
    time.sleep(0.2)

    print("\nStats:", bus.get_stats())
