"""
NewERP - Customer Service
=========================
Serwis z logiką biznesową dla klientów.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
import re

from supabase import Client

from core.base_service import BaseService
from core.events import EventType, EventBus
from core.audit import AuditService, AuditAction
from core.exceptions import (
    ValidationError,
    RequiredFieldError,
    InvalidFieldValueError,
    BusinessRuleError,
    RecordNotFoundError
)
from core.filters import QueryParams, Filter, FilterOperator

from customers.repository import CustomerRepository

logger = logging.getLogger(__name__)


class CustomerService(BaseService):
    """
    Serwis do zarządzania klientami.
    
    Odpowiada za:
    - Walidację danych
    - Generowanie kodów klientów
    - Logikę biznesową (limity, blokady)
    - Audyt zmian
    - Emitowanie eventów
    """
    
    ENTITY_NAME = "Customer"
    
    # Pola wymagane przy tworzeniu
    REQUIRED_FIELDS = ["name"]
    
    # Pola opcjonalne
    OPTIONAL_FIELDS = [
        "code", "short_name", "type",
        "nip", "regon", "krs",
        "address_street", "address_building", "address_apartment",
        "address_postal_code", "address_city", "address_country",
        "shipping_address",
        "email", "phone", "phone_mobile", "fax", "website",
        "contacts",
        "payment_days", "credit_limit", "discount_percent", "price_list", "currency",
        "bank_name", "bank_account",
        "notes", "tags", "category",
        "sales_rep_id", "acquisition_source"
    ]
    
    # Typy pól
    FIELD_TYPES = {
        "payment_days": int,
        "credit_limit": float,
        "discount_percent": float,
    }
    
    # Eventy
    EVENT_CREATE = EventType.CUSTOMER_CREATED
    EVENT_UPDATE = EventType.CUSTOMER_UPDATED
    EVENT_DELETE = EventType.CUSTOMER_DELETED
    
    def __init__(
        self, 
        client: Client,
        event_bus: EventBus = None,
        audit_service: AuditService = None
    ):
        super().__init__(client, event_bus, audit_service)
        self.repository = CustomerRepository(client)
    
    # ============================================================
    # Validation
    # ============================================================
    
    def _validate_business_rules(self, data: Dict[str, Any], is_update: bool):
        """Walidacja reguł biznesowych"""
        
        # Walidacja NIP
        if data.get('nip'):
            if not self._validate_nip(data['nip']):
                raise InvalidFieldValueError('nip', data['nip'], 'Invalid NIP format')
        
        # Walidacja email
        if data.get('email'):
            if not self._validate_email(data['email']):
                raise InvalidFieldValueError('email', data['email'], 'Invalid email format')
        
        # Walidacja rabatu
        if data.get('discount_percent') is not None:
            discount = data['discount_percent']
            if discount < 0 or discount > 100:
                raise InvalidFieldValueError(
                    'discount_percent', discount, 
                    'Discount must be between 0 and 100'
                )
        
        # Walidacja terminu płatności
        if data.get('payment_days') is not None:
            days = data['payment_days']
            if days < 0 or days > 365:
                raise InvalidFieldValueError(
                    'payment_days', days,
                    'Payment days must be between 0 and 365'
                )
        
        # Walidacja limitu kredytowego
        if data.get('credit_limit') is not None:
            limit = data['credit_limit']
            if limit < 0:
                raise InvalidFieldValueError(
                    'credit_limit', limit,
                    'Credit limit cannot be negative'
                )
    
    def _validate_nip(self, nip: str) -> bool:
        """Walidacja polskiego NIP"""
        # Usuń myślniki i spacje
        nip = re.sub(r'[\s\-]', '', nip)
        
        # Sprawdź długość
        if len(nip) != 10:
            return False
        
        # Sprawdź czy same cyfry
        if not nip.isdigit():
            return False
        
        # Walidacja sumy kontrolnej
        weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
        checksum = sum(int(nip[i]) * weights[i] for i in range(9))
        checksum = checksum % 11
        
        return checksum == int(nip[9])
    
    def _validate_email(self, email: str) -> bool:
        """Prosta walidacja email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    # ============================================================
    # CRUD Operations
    # ============================================================
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Utwórz nowego klienta.
        
        Args:
            data: Dane klienta (name wymagane)
        
        Returns:
            Utworzony klient z ID i kodem
        """
        # Walidacja
        validated = self.validate(data)
        
        # Generuj kod jeśli nie podany
        if not validated.get('code'):
            validated['code'] = self.repository.generate_code()
        
        # Generuj short_name z name jeśli nie podany
        if not validated.get('short_name'):
            validated['short_name'] = self._generate_short_name(validated['name'])
        
        # Sprawdź unikalność NIP
        if validated.get('nip'):
            existing = self.repository.get_by_nip(validated['nip'])
            if existing:
                raise BusinessRuleError(
                    f"Customer with NIP {validated['nip']} already exists",
                    {"existing_id": existing['id'], "existing_name": existing['name']}
                )
        
        # Utwórz
        customer = self.repository.create(validated)
        customer_id = customer['id']
        
        # Audit
        self.log_audit(customer_id, AuditAction.CREATE, new_values=validated)
        
        # Event
        self.emit_create_event(customer_id, customer)
        
        logger.info(f"[Customer] Created: {customer['code']} - {customer['name']}")
        return customer
    
    def update(
        self, 
        id: str, 
        data: Dict[str, Any],
        expected_version: int = None
    ) -> Dict[str, Any]:
        """
        Aktualizuj klienta.
        
        Args:
            id: ID klienta
            data: Dane do aktualizacji
            expected_version: Oczekiwana wersja (optimistic locking)
        
        Returns:
            Zaktualizowany klient
        """
        # Pobierz stary stan
        old_customer = self.repository.get_by_id_or_raise(id)
        
        # Walidacja
        validated = self.validate(data, is_update=True)
        
        # Sprawdź unikalność NIP (jeśli zmieniony)
        if validated.get('nip') and validated['nip'] != old_customer.get('nip'):
            existing = self.repository.get_by_nip(validated['nip'])
            if existing and existing['id'] != id:
                raise BusinessRuleError(
                    f"Customer with NIP {validated['nip']} already exists",
                    {"existing_id": existing['id']}
                )
        
        # Aktualizuj
        customer = self.repository.update(id, validated, expected_version)
        
        # Audit
        self.log_audit(
            id, 
            AuditAction.UPDATE,
            old_values=old_customer,
            new_values=customer
        )
        
        # Event
        self.emit_update_event(id, old_customer, customer)
        
        logger.info(f"[Customer] Updated: {customer['code']}")
        return customer
    
    def delete(self, id: str, hard: bool = False) -> bool:
        """
        Usuń klienta (domyślnie soft delete).
        
        Args:
            id: ID klienta
            hard: True = fizyczne usunięcie
        
        Returns:
            True jeśli usunięto
        """
        # Pobierz dane przed usunięciem
        customer = self.repository.get_by_id_or_raise(id)
        
        # Sprawdź czy można usunąć
        # TODO: Sprawdź powiązane zamówienia
        # if self._has_orders(id):
        #     raise BusinessRuleError("Cannot delete customer with orders")
        
        # Usuń
        result = self.repository.delete(id, hard=hard)
        
        # Audit
        self.log_audit(id, AuditAction.DELETE, old_values=customer)
        
        # Event
        self.emit_delete_event(id, customer)
        
        logger.info(f"[Customer] Deleted: {customer['code']} (hard={hard})")
        return result
    
    def restore(self, id: str) -> Dict[str, Any]:
        """Przywróć usuniętego klienta"""
        customer = self.repository.restore(id)
        
        # Audit
        self.log_audit(id, AuditAction.RESTORE)
        
        # Event
        self.emit_event(EventType.CUSTOMER_RESTORED, {"id": id})
        
        logger.info(f"[Customer] Restored: {customer['code']}")
        return customer
    
    # ============================================================
    # Query Operations
    # ============================================================
    
    def get(self, id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """Pobierz klienta po ID"""
        return self.repository.get_by_id(id, include_deleted)
    
    def get_or_raise(self, id: str) -> Dict[str, Any]:
        """Pobierz klienta po ID lub rzuć wyjątek"""
        return self.repository.get_by_id_or_raise(id)
    
    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Pobierz klienta po kodzie"""
        return self.repository.get_by_code(code)
    
    def get_by_nip(self, nip: str) -> Optional[Dict[str, Any]]:
        """Pobierz klienta po NIP"""
        return self.repository.get_by_nip(nip)
    
    def list(
        self,
        params: QueryParams = None,
        include_deleted: bool = False
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Pobierz listę klientów z filtrami.
        
        Returns:
            Tuple[List[dict], int]: (klienci, total_count)
        """
        return self.repository.list(params, include_deleted)
    
    def search(
        self, 
        query: str, 
        limit: int = 20,
        include_blocked: bool = False
    ) -> List[Dict[str, Any]]:
        """Szybkie wyszukiwanie klientów"""
        return self.repository.search(query, limit, include_blocked)
    
    # ============================================================
    # Business Operations
    # ============================================================
    
    def block(self, id: str, reason: str = None) -> Dict[str, Any]:
        """
        Zablokuj klienta.
        
        Args:
            id: ID klienta
            reason: Powód blokady
        
        Returns:
            Zaktualizowany klient
        """
        customer = self.repository.get_by_id_or_raise(id)
        
        if customer.get('is_blocked'):
            raise BusinessRuleError("Customer is already blocked")
        
        self.repository.block(id, reason)
        
        # Audit
        self.log_audit(
            id,
            AuditAction.STATUS_CHANGE,
            old_values={"is_blocked": False},
            new_values={"is_blocked": True, "blocked_reason": reason}
        )
        
        logger.info(f"[Customer] Blocked: {customer['code']} - {reason}")
        return self.repository.get_by_id(id)
    
    def unblock(self, id: str) -> Dict[str, Any]:
        """
        Odblokuj klienta.
        
        Returns:
            Zaktualizowany klient
        """
        customer = self.repository.get_by_id_or_raise(id)
        
        if not customer.get('is_blocked'):
            raise BusinessRuleError("Customer is not blocked")
        
        self.repository.unblock(id)
        
        # Audit
        self.log_audit(
            id,
            AuditAction.STATUS_CHANGE,
            old_values={"is_blocked": True},
            new_values={"is_blocked": False}
        )
        
        logger.info(f"[Customer] Unblocked: {customer['code']}")
        return self.repository.get_by_id(id)
    
    def check_credit_limit(self, id: str, order_value: float) -> Dict[str, Any]:
        """
        Sprawdź czy zamówienie mieści się w limicie kredytowym.
        
        Returns:
            {
                "allowed": bool,
                "credit_limit": float,
                "current_debt": float,  # TODO: z modułu faktur
                "available": float,
                "order_value": float
            }
        """
        customer = self.repository.get_by_id_or_raise(id)
        
        credit_limit = customer.get('credit_limit') or 0
        
        # TODO: Pobierz aktualny dług z modułu faktur
        current_debt = 0
        
        available = credit_limit - current_debt
        allowed = order_value <= available or credit_limit == 0
        
        return {
            "allowed": allowed,
            "credit_limit": credit_limit,
            "current_debt": current_debt,
            "available": max(0, available),
            "order_value": order_value
        }
    
    def update_after_order(
        self, 
        id: str, 
        order_value: float,
        order_date: str = None
    ) -> bool:
        """
        Aktualizuj statystyki klienta po zamówieniu.
        
        Args:
            id: ID klienta
            order_value: Wartość zamówienia (netto)
            order_date: Data zamówienia (domyślnie dziś)
        """
        if order_date is None:
            order_date = datetime.now().date().isoformat()
        
        return self.repository.update_sales_stats(id, order_value, order_date)
    
    # ============================================================
    # Statistics
    # ============================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Pobierz statystyki klientów"""
        return self.repository.get_statistics()
    
    def get_top_customers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Pobierz top klientów wg obrotów"""
        return self.repository.list_top_customers(limit)
    
    def get_inactive_customers(self, days: int = 180) -> List[Dict[str, Any]]:
        """Pobierz klientów bez zamówień od X dni"""
        return self.repository.list_inactive(days)
    
    # ============================================================
    # Helper Methods
    # ============================================================
    
    def _generate_short_name(self, name: str, max_length: int = 20) -> str:
        """
        Generuj krótką nazwę z pełnej nazwy.
        
        Usuwa typowe przyrostki firm (Sp. z o.o., S.A., itp.)
        i skraca do max_length znaków.
        """
        # Usuń typowe przyrostki
        suffixes = [
            r'\s+sp\.?\s*z\s*o\.?o\.?',
            r'\s+sp\.?\s*j\.?',
            r'\s+s\.?a\.?',
            r'\s+s\.?c\.?',
            r'\s+spółka\s+z\s+o\.?o\.?',
            r'\s+spółka\s+akcyjna',
            r'\s+sp\.?\s*k\.?',
            r'\s+limited',
            r'\s+ltd\.?',
            r'\s+gmbh',
            r'\s+inc\.?',
        ]
        
        short = name
        for suffix in suffixes:
            short = re.sub(suffix, '', short, flags=re.IGNORECASE)
        
        # Trim i ogranicz długość
        short = short.strip()
        if len(short) > max_length:
            # Znajdź ostatnią spację przed limitem
            space_pos = short.rfind(' ', 0, max_length)
            if space_pos > 10:
                short = short[:space_pos]
            else:
                short = short[:max_length]
        
        return short.strip()
    
    def duplicate(self, id: str, new_code: str = None) -> Dict[str, Any]:
        """
        Zduplikuj klienta (np. dla nowego oddziału).
        
        Args:
            id: ID klienta źródłowego
            new_code: Nowy kod (opcjonalny)
        
        Returns:
            Nowy klient
        """
        source = self.repository.get_by_id_or_raise(id)
        
        # Przygotuj dane do kopiowania
        copy_data = {
            'name': source['name'] + ' (kopia)',
            'short_name': source.get('short_name'),
            'type': source.get('type'),
            'address_street': source.get('address_street'),
            'address_building': source.get('address_building'),
            'address_apartment': source.get('address_apartment'),
            'address_postal_code': source.get('address_postal_code'),
            'address_city': source.get('address_city'),
            'address_country': source.get('address_country'),
            'email': source.get('email'),
            'phone': source.get('phone'),
            'payment_days': source.get('payment_days'),
            'discount_percent': source.get('discount_percent'),
            'price_list': source.get('price_list'),
            'category': source.get('category'),
            'tags': source.get('tags'),
        }
        
        # Ustaw nowy kod jeśli podany
        if new_code:
            copy_data['code'] = new_code
        
        # Usuń NIP (musi być unikalny)
        # Usuń statystyki sprzedażowe
        
        return self.create(copy_data)
