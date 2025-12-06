"""
NewERP - Customer Repository
============================
Repozytorium do operacji na klientach (kontrahentach).
"""

from typing import Dict, List, Optional, Any
import logging

from supabase import Client

from core.base_repository import BaseRepository
from core.filters import QueryParams, Filter, FilterOperator

logger = logging.getLogger(__name__)


class CustomerRepository(BaseRepository):
    """
    Repozytorium klientów.
    
    Rozszerza BaseRepository o specyficzne metody dla klientów.
    """
    
    TABLE_NAME = "customers"
    ENTITY_NAME = "Customer"
    
    # Pola do wyszukiwania pełnotekstowego
    SEARCH_FIELDS = ["name", "short_name", "code", "nip", "email", "address_city"]
    
    # Pola z unique constraint
    UNIQUE_FIELDS = ["code", "nip"]
    
    def __init__(self, client: Client):
        super().__init__(client)
    
    # ============================================================
    # Specialized Queries
    # ============================================================
    
    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Pobierz klienta po kodzie (np. KL-00001)"""
        return self.find_one(code=code)
    
    def get_by_nip(self, nip: str) -> Optional[Dict[str, Any]]:
        """Pobierz klienta po NIP"""
        # Normalizuj NIP (usuń myślniki)
        nip_clean = nip.replace("-", "").strip()
        
        try:
            response = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('is_active', True)\
                .ilike('nip', f'%{nip_clean}%')\
                .limit(1)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[Customer] Get by NIP failed: {e}")
            return None
    
    def search(
        self, 
        query: str, 
        limit: int = 20,
        include_blocked: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Szybkie wyszukiwanie klientów.
        
        Args:
            query: Fraza do wyszukania (nazwa, kod, NIP, email)
            limit: Maksymalna liczba wyników
            include_blocked: Czy włączyć zablokowanych klientów
        """
        try:
            # Użyj funkcji SQL search_customers (jeśli istnieje)
            # lub standardowego wyszukiwania
            
            q = self.client.table(self.TABLE_NAME)\
                .select('id, code, name, short_name, nip, address_city, email, phone')\
                .eq('is_active', True)
            
            if not include_blocked:
                q = q.eq('is_blocked', False)
            
            # Szukaj w wielu polach
            search_conditions = []
            for field in ['name', 'short_name', 'code', 'nip', 'email']:
                search_conditions.append(f"{field}.ilike.%{query}%")
            
            q = q.or_(','.join(search_conditions))
            q = q.limit(limit)
            q = q.order('name')
            
            response = q.execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"[Customer] Search failed: {e}")
            return []
    
    def list_by_city(self, city: str) -> List[Dict[str, Any]]:
        """Pobierz klientów z danego miasta"""
        return self.find_many(address_city=city, is_active=True)
    
    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Pobierz klientów z danej kategorii"""
        return self.find_many(category=category, is_active=True)
    
    def list_with_overdue_payments(self) -> List[Dict[str, Any]]:
        """Pobierz klientów z przeterminowanymi płatnościami"""
        # TODO: Wymaga integracji z modułem faktur/płatności
        return self.find_many(is_blocked=True, is_active=True)
    
    def list_top_customers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Pobierz top klientów wg obrotów"""
        try:
            response = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('is_active', True)\
                .order('total_revenue', desc=True)\
                .limit(limit)\
                .execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"[Customer] Get top customers failed: {e}")
            return []
    
    def list_inactive(self, days: int = 180) -> List[Dict[str, Any]]:
        """Pobierz klientów bez zamówień od X dni"""
        try:
            from datetime import datetime, timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).date().isoformat()
            
            response = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('is_active', True)\
                .lt('last_order_date', cutoff_date)\
                .order('last_order_date')\
                .execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"[Customer] Get inactive customers failed: {e}")
            return []
    
    # ============================================================
    # Statistics
    # ============================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Pobierz statystyki klientów"""
        try:
            # Wszystkich aktywnych
            active_response = self.client.table(self.TABLE_NAME)\
                .select('id', count='exact')\
                .eq('is_active', True)\
                .execute()
            
            # Zablokowanych
            blocked_response = self.client.table(self.TABLE_NAME)\
                .select('id', count='exact')\
                .eq('is_active', True)\
                .eq('is_blocked', True)\
                .execute()
            
            # Firm vs osób fizycznych
            companies_response = self.client.table(self.TABLE_NAME)\
                .select('id', count='exact')\
                .eq('is_active', True)\
                .eq('type', 'company')\
                .execute()
            
            return {
                'total_active': active_response.count or 0,
                'blocked': blocked_response.count or 0,
                'companies': companies_response.count or 0,
                'individuals': (active_response.count or 0) - (companies_response.count or 0)
            }
        except Exception as e:
            logger.error(f"[Customer] Get statistics failed: {e}")
            return {'total_active': 0, 'blocked': 0, 'companies': 0, 'individuals': 0}
    
    # ============================================================
    # Code Generation
    # ============================================================
    
    def generate_code(self, prefix: str = "KL") -> str:
        """
        Wygeneruj następny kod klienta.
        
        Format: PREFIX-NNNNN (np. KL-00001)
        """
        try:
            # Znajdź najwyższy numer
            response = self.client.table(self.TABLE_NAME)\
                .select('code')\
                .ilike('code', f'{prefix}-%')\
                .order('code', desc=True)\
                .limit(1)\
                .execute()
            
            if response.data:
                last_code = response.data[0]['code']
                # Wyciągnij numer
                try:
                    last_num = int(last_code.split('-')[1])
                    next_num = last_num + 1
                except (IndexError, ValueError):
                    next_num = 1
            else:
                next_num = 1
            
            return f"{prefix}-{str(next_num).zfill(5)}"
            
        except Exception as e:
            logger.error(f"[Customer] Generate code failed: {e}")
            # Fallback - użyj timestamp
            import time
            return f"{prefix}-{int(time.time()) % 100000:05d}"
    
    # ============================================================
    # Blocking
    # ============================================================
    
    def block(self, id: str, reason: str = None) -> bool:
        """Zablokuj klienta"""
        try:
            from datetime import datetime
            
            response = self.client.table(self.TABLE_NAME)\
                .update({
                    'is_blocked': True,
                    'blocked_reason': reason,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', id)\
                .execute()
            
            if response.data:
                logger.info(f"[Customer] Blocked: {id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"[Customer] Block failed: {e}")
            return False
    
    def unblock(self, id: str) -> bool:
        """Odblokuj klienta"""
        try:
            from datetime import datetime
            
            response = self.client.table(self.TABLE_NAME)\
                .update({
                    'is_blocked': False,
                    'blocked_reason': None,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', id)\
                .execute()
            
            if response.data:
                logger.info(f"[Customer] Unblocked: {id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"[Customer] Unblock failed: {e}")
            return False
    
    # ============================================================
    # Sales Statistics Update
    # ============================================================
    
    def update_sales_stats(
        self, 
        id: str, 
        order_value: float,
        order_date: str
    ) -> bool:
        """
        Aktualizuj statystyki sprzedażowe klienta po zamówieniu.
        
        Args:
            id: ID klienta
            order_value: Wartość zamówienia
            order_date: Data zamówienia (ISO format)
        """
        try:
            # Pobierz aktualne dane
            customer = self.get_by_id(id)
            if not customer:
                return False
            
            # Oblicz nowe wartości
            total_orders = (customer.get('total_orders') or 0) + 1
            total_revenue = (customer.get('total_revenue') or 0) + order_value
            
            # Aktualizuj pierwszy/ostatni zamówienie
            updates = {
                'total_orders': total_orders,
                'total_revenue': total_revenue,
                'last_order_date': order_date
            }
            
            if not customer.get('first_order_date'):
                updates['first_order_date'] = order_date
            
            response = self.client.table(self.TABLE_NAME)\
                .update(updates)\
                .eq('id', id)\
                .execute()
            
            return bool(response.data)
            
        except Exception as e:
            logger.error(f"[Customer] Update sales stats failed: {e}")
            return False
