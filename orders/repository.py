"""
Order Repository
================
Operacje na bazie danych dla zamówień w Supabase.

Tabele:
- orders (główna tabela zamówień)
- order_items (pozycje zamówień - detale)
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
import uuid
import json

logger = logging.getLogger(__name__)


class OrderRepository:
    """Repository do operacji na zamówieniach w Supabase"""

    def __init__(self, supabase_client):
        self.client = supabase_client
        self._available_columns = None  # Cache dla dostępnych kolumn

    def _get_available_columns(self) -> set:
        """Pobierz dostępne kolumny tabeli orders"""
        if self._available_columns is not None:
            return self._available_columns

        logger.debug("[OrderRepository] Checking available columns...")

        # Próba pobrania rekordu żeby zobaczyć kolumny
        try:
            response = self.client.table('orders').select('*').limit(1).execute()
            if response.data:
                self._available_columns = set(response.data[0].keys())
                logger.info(f"[OrderRepository] Available columns from data: {self._available_columns}")
                return self._available_columns
        except Exception as e:
            logger.warning(f"[OrderRepository] Cannot detect columns from data: {e}")

        # Wszystkie kolumny po migracji (znane z migrate_orders.sql + title z oryginalnej tabeli)
        self._available_columns = {
            'id', 'title', 'name', 'client', 'customer_name', 'date_in', 'date_due',
            'status', 'priority', 'notes', 'parts_count', 'total_cost',
            'metadata', 'created_at', 'updated_at'
        }
        logger.info(f"[OrderRepository] Using default columns: {self._available_columns}")
        return self._available_columns

    # Statusy zgodne z ENUM order_status w Supabase
    VALID_STATUSES = ['RECEIVED', 'CONFIRMED', 'PLANNED', 'IN_PROGRESS', 'DONE', 'INVOICED']
    DEFAULT_STATUS = 'RECEIVED'

    def _prepare_record(self, order_data: Dict, for_update: bool = False) -> Dict:
        """Przygotuj rekord do zapisu, uwzględniając dostępne kolumny"""
        available = self._get_available_columns()
        logger.debug(f"[OrderRepository] Available columns: {available}")

        # Mapowanie pól - obsługa różnych nazw kolumn
        client_value = order_data.get('client', '') or order_data.get('customer_name', '')

        # Walidacja statusu - musi być zgodny z ENUM
        status = order_data.get('status', self.DEFAULT_STATUS)
        if status not in self.VALID_STATUSES:
            logger.warning(f"[OrderRepository] Invalid status '{status}', using default '{self.DEFAULT_STATUS}'")
            status = self.DEFAULT_STATUS

        record = {}

        # Podstawowe pola
        if not for_update:
            record['id'] = order_data.get('id', str(uuid.uuid4()))
            record['created_at'] = datetime.now().isoformat()

        # Nazwa zamówienia - używamy 'title' (główne pole w bazie) i 'name' (alternatywne)
        order_name = order_data.get('name', '') or order_data.get('title', '')
        record['title'] = order_name  # Główne pole NOT NULL w bazie
        record['name'] = order_name   # Alternatywne pole
        record['status'] = status
        record['updated_at'] = datetime.now().isoformat()

        # Pola opcjonalne - dodaj tylko jeśli kolumna istnieje
        optional_fields = {
            'client': client_value,
            'customer_name': client_value,  # alternatywna nazwa
            'date_in': order_data.get('date_in') or datetime.now().date().isoformat(),
            'date_due': order_data.get('date_due'),
            'priority': order_data.get('priority', 'Normalny'),
            'notes': order_data.get('notes', ''),
            'parts_count': order_data.get('parts_count', 0),
            'total_cost': order_data.get('cost_result', {}).get('total_cost', 0) if order_data.get('cost_result') else 0,
            'metadata': json.dumps({
                'cost_params': order_data.get('cost_params', {}),
                'cost_result': order_data.get('cost_result', {}),
                'nesting_results': self._serialize_nesting_results(order_data.get('nesting_results', {})),
                'client': client_value  # Zapisz klienta w metadata jako fallback
            })
        }

        for field, value in optional_fields.items():
            if field in available or not available:  # Jeśli nie znamy kolumn, spróbuj wszystkie
                record[field] = value
                logger.debug(f"[OrderRepository] Adding field '{field}' = '{value}'")
            else:
                logger.debug(f"[OrderRepository] Skipping field '{field}' (not in schema)")

        return record

    # ============================================================
    # CRUD Operations
    # ============================================================

    def create(self, order_data: Dict) -> Optional[str]:
        """
        Stwórz nowe zamówienie.

        Args:
            order_data: Dane zamówienia

        Returns:
            ID zamówienia lub None
        """
        order_id = order_data.get('id', str(uuid.uuid4()))
        logger.info(f"[OrderRepository] === CREATE ORDER START === {order_id}")

        try:
            record = self._prepare_record(order_data, for_update=False)
            record['id'] = order_id

            logger.info(f"[OrderRepository] Inserting record with columns: {list(record.keys())}")
            logger.debug(f"[OrderRepository] Record data: {record}")

            response = self.client.table('orders').insert(record).execute()

            if response.data:
                logger.info(f"[OrderRepository] Order inserted successfully: {order_id}")

                # Zapisz pozycje zamówienia
                items = order_data.get('items', [])
                if items:
                    logger.info(f"[OrderRepository] Saving {len(items)} order items")
                    self._save_order_items(order_id, items)

                logger.info(f"[OrderRepository] === CREATE ORDER SUCCESS === {order_id}")
                return order_id
            else:
                logger.error(f"[OrderRepository] Insert returned no data for {order_id}")
                return None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[OrderRepository] === CREATE ORDER FAILED === {order_id}")
            logger.error(f"[OrderRepository] Error: {error_msg}")

            # Sprawdź czy to błąd brakującej kolumny
            if "Could not find" in error_msg and "column" in error_msg:
                logger.warning("[OrderRepository] Column missing - attempting with minimal columns")
                # Wyczyść cache i spróbuj ponownie z minimalnymi kolumnami
                self._available_columns = {'id', 'title', 'name', 'status', 'created_at', 'updated_at', 'metadata'}
                try:
                    minimal_record = self._prepare_record(order_data, for_update=False)
                    minimal_record['id'] = order_id
                    response = self.client.table('orders').insert(minimal_record).execute()
                    if response.data:
                        logger.info(f"[OrderRepository] Order created with minimal columns: {order_id}")
                        return order_id
                except Exception as e2:
                    logger.error(f"[OrderRepository] Minimal insert also failed: {e2}")

            return None

    def get_by_id(self, order_id: str) -> Optional[Dict]:
        """
        Pobierz zamówienie po ID.

        Args:
            order_id: ID zamówienia

        Returns:
            Dane zamówienia lub None
        """
        try:
            response = self.client.table('orders').select('*').eq('id', order_id).limit(1).execute()

            if response.data:
                order = response.data[0]

                # Mapowanie title → name (dla kompatybilności)
                if 'title' in order and not order.get('name'):
                    order['name'] = order['title']
                if 'name' in order and not order.get('title'):
                    order['title'] = order['name']

                # Deserializuj metadata
                if order.get('metadata'):
                    try:
                        if isinstance(order['metadata'], str):
                            metadata = json.loads(order['metadata'])
                        else:
                            metadata = order['metadata']
                        order['cost_params'] = metadata.get('cost_params', {})
                        order['nesting_results'] = metadata.get('nesting_results', {})
                        order['cost_result'] = metadata.get('cost_result', {})
                        # Odzyskaj klienta z metadata jeśli brak w głównych polach
                        if not order.get('client') and metadata.get('client'):
                            order['client'] = metadata['client']
                    except Exception as e:
                        logger.warning(f"[OrderRepository] Error parsing metadata: {e}")

                # Pobierz pozycje
                order['items'] = self._get_order_items(order_id)

                logger.debug(f"[OrderRepository] Found order: {order_id}")
                return order

            return None

        except Exception as e:
            logger.error(f"[OrderRepository] Error getting order {order_id}: {e}")
            return None

    def update(self, order_id: str, order_data: Dict) -> bool:
        """
        Zaktualizuj zamówienie.

        Args:
            order_id: ID zamówienia
            order_data: Nowe dane

        Returns:
            True jeśli sukces
        """
        logger.info(f"[OrderRepository] === UPDATE ORDER START === {order_id}")

        try:
            record = self._prepare_record(order_data, for_update=True)

            logger.info(f"[OrderRepository] Updating record with columns: {list(record.keys())}")
            logger.debug(f"[OrderRepository] Update data: {record}")

            response = self.client.table('orders').update(record).eq('id', order_id).execute()

            if not response.data:
                logger.warning(f"[OrderRepository] Update returned no data for {order_id}")

            # Aktualizuj pozycje
            items = order_data.get('items', [])
            if items:
                logger.info(f"[OrderRepository] Updating {len(items)} order items")
                # Usuń stare pozycje
                try:
                    self.client.table('order_items').delete().eq('order_id', order_id).execute()
                except Exception as e:
                    logger.warning(f"[OrderRepository] Error deleting old items: {e}")

                # Dodaj nowe
                self._save_order_items(order_id, items)

            logger.info(f"[OrderRepository] === UPDATE ORDER SUCCESS === {order_id}")
            return True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[OrderRepository] === UPDATE ORDER FAILED === {order_id}")
            logger.error(f"[OrderRepository] Error: {error_msg}")

            # Sprawdź czy to błąd brakującej kolumny
            if "Could not find" in error_msg and "column" in error_msg:
                logger.warning("[OrderRepository] Column missing - attempting with minimal columns")
                self._available_columns = {'id', 'name', 'status', 'updated_at', 'metadata'}
                try:
                    minimal_record = self._prepare_record(order_data, for_update=True)
                    self.client.table('orders').update(minimal_record).eq('id', order_id).execute()
                    logger.info(f"[OrderRepository] Order updated with minimal columns: {order_id}")
                    return True
                except Exception as e2:
                    logger.error(f"[OrderRepository] Minimal update also failed: {e2}")

            return False

    def delete(self, order_id: str) -> bool:
        """Usuń zamówienie"""
        try:
            # Usuń pozycje
            self.client.table('order_items').delete().eq('order_id', order_id).execute()
            # Usuń zamówienie
            self.client.table('orders').delete().eq('id', order_id).execute()

            logger.info(f"[OrderRepository] Order deleted: {order_id}")
            return True

        except Exception as e:
            logger.error(f"[OrderRepository] Error deleting order {order_id}: {e}")
            return False

    # ============================================================
    # List & Search
    # ============================================================

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Pobierz listę zamówień"""
        try:
            response = self.client.table('orders').select('*').order(
                'created_at', desc=True
            ).range(offset, offset + limit - 1).execute()

            orders = response.data or []
            logger.debug(f"[OrderRepository] Found {len(orders)} orders")
            return orders

        except Exception as e:
            logger.error(f"[OrderRepository] Error getting orders: {e}")
            return []

    def get_by_status(self, status: str, limit: int = 100) -> List[Dict]:
        """Pobierz zamówienia o danym statusie"""
        try:
            response = self.client.table('orders').select('*').eq(
                'status', status
            ).order('created_at', desc=True).limit(limit).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"[OrderRepository] Error getting orders by status: {e}")
            return []

    def get_by_client(self, client: str, limit: int = 100) -> List[Dict]:
        """Pobierz zamówienia dla klienta"""
        try:
            response = self.client.table('orders').select('*').ilike(
                'client', f'%{client}%'
            ).order('created_at', desc=True).limit(limit).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"[OrderRepository] Error getting orders by client: {e}")
            return []

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        """Wyszukaj zamówienia"""
        try:
            response = self.client.table('orders').select('*').or_(
                f"name.ilike.%{query}%,client.ilike.%{query}%,notes.ilike.%{query}%"
            ).order('created_at', desc=True).limit(limit).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"[OrderRepository] Error searching orders: {e}")
            return []

    def get_status_counts(self) -> Dict[str, int]:
        """Pobierz liczby zamówień per status"""
        try:
            # Pobierz wszystkie zamówienia i policz statusy
            response = self.client.table('orders').select('status').execute()

            counts = {}
            for row in (response.data or []):
                status = row.get('status', 'unknown')
                counts[status] = counts.get(status, 0) + 1

            return counts

        except Exception as e:
            logger.error(f"[OrderRepository] Error getting status counts: {e}")
            return {}

    # ============================================================
    # Order Items (pozycje zamówienia)
    # ============================================================

    _order_items_columns = None  # Cache dla kolumn order_items

    def _get_order_items_columns(self) -> set:
        """Pobierz dostępne kolumny tabeli order_items"""
        if self._order_items_columns is not None:
            return self._order_items_columns

        try:
            response = self.client.table('order_items').select('*').limit(1).execute()
            if response.data:
                self._order_items_columns = set(response.data[0].keys())
                logger.info(f"[OrderRepository] order_items columns: {self._order_items_columns}")
                return self._order_items_columns
        except Exception as e:
            logger.warning(f"[OrderRepository] Cannot detect order_items columns: {e}")

        # Minimalne kolumny
        self._order_items_columns = {'id', 'order_id', 'name', 'quantity', 'created_at'}
        return self._order_items_columns

    def _save_order_items(self, order_id: str, items: List[Dict]):
        """Zapisz pozycje zamówienia - mapowanie do schematu Supabase"""
        try:
            records = []
            for i, item in enumerate(items):
                # Mapowanie pól aplikacji → kolumny bazy danych
                # Schemat bazy: id, order_id, custom_name, qty, thickness_mm,
                #               unit_price, total_price, documentation_path, notes,
                #               product_snapshot, created_at, updated_at

                # Snapshot produktu - wszystkie dane detalu w JSON
                product_snapshot = {
                    'name': item.get('name', ''),
                    'material': item.get('material', ''),
                    'thickness_mm': item.get('thickness_mm', 0),
                    'width': item.get('width', 0),
                    'height': item.get('height', 0),
                    'weight_kg': item.get('weight_kg', 0),
                    'filepath': item.get('filepath', ''),
                    'contour': item.get('contour', []),
                    'holes': item.get('holes', []),
                }

                record = {
                    'id': str(uuid.uuid4()),
                    'order_id': order_id,
                    'custom_name': item.get('name', ''),
                    'qty': int(item.get('quantity', 1)),
                    'thickness_mm': float(item.get('thickness_mm', 0)),
                    'unit_price': float(item.get('unit_cost', 0)),
                    'total_price': float(item.get('total_cost', 0)),
                    'documentation_path': item.get('filepath', ''),
                    'notes': f"Materiał: {item.get('material', '')} | {item.get('width', 0):.0f}x{item.get('height', 0):.0f}mm",
                    'product_snapshot': json.dumps(product_snapshot),
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                records.append(record)

            if records:
                logger.info(f"[OrderRepository] Inserting {len(records)} order items")
                logger.debug(f"[OrderRepository] First record keys: {list(records[0].keys())}")
                self.client.table('order_items').insert(records).execute()
                logger.info(f"[OrderRepository] Saved {len(records)} order items successfully")

        except Exception as e:
            logger.error(f"[OrderRepository] Error saving order items: {e}")

    def _get_order_items(self, order_id: str) -> List[Dict]:
        """Pobierz pozycje zamówienia - mapowanie z bazy do formatu aplikacji"""
        try:
            response = self.client.table('order_items').select('*').eq(
                'order_id', order_id
            ).order('created_at').execute()

            items = []
            for row in (response.data or []):
                # Spróbuj odczytać dane z product_snapshot
                snapshot = {}
                if row.get('product_snapshot'):
                    try:
                        if isinstance(row['product_snapshot'], str):
                            snapshot = json.loads(row['product_snapshot'])
                        else:
                            snapshot = row['product_snapshot']
                    except:
                        pass

                # Mapowanie kolumn bazy → pola aplikacji
                item = {
                    'id': row.get('id', ''),
                    'name': row.get('custom_name', '') or snapshot.get('name', ''),
                    'material': snapshot.get('material', ''),
                    'thickness_mm': row.get('thickness_mm', 0) or snapshot.get('thickness_mm', 0),
                    'quantity': row.get('qty', 1),
                    'width': snapshot.get('width', 0),
                    'height': snapshot.get('height', 0),
                    'weight_kg': snapshot.get('weight_kg', 0),
                    'unit_cost': row.get('unit_price', 0),
                    'total_cost': row.get('total_price', 0),
                    'filepath': row.get('documentation_path', '') or snapshot.get('filepath', ''),
                    'contour': snapshot.get('contour', []),
                    'holes': snapshot.get('holes', []),
                }
                items.append(item)

            logger.debug(f"[OrderRepository] Loaded {len(items)} order items for {order_id}")
            return items

        except Exception as e:
            logger.error(f"[OrderRepository] Error getting order items: {e}")
            return []

    def _serialize_nesting_results(self, results: Dict) -> Dict:
        """Serializuj wyniki nestingu do formatu zapisywalnego"""
        if not results:
            return {}

        serialized = {}
        for key, value in results.items():
            if hasattr(value, '__dict__'):
                serialized[str(key)] = {
                    'sheets_used': getattr(value, 'sheets_used', 0),
                    'efficiency': getattr(value, 'total_efficiency', 0),
                    'placed_parts': len(getattr(value, 'placed_parts', [])),
                    'total_cost': getattr(value, 'total_cost', 0)
                }
            elif isinstance(value, dict):
                serialized[str(key)] = value
            else:
                serialized[str(key)] = str(value)

        return serialized


# ============================================================
# SQL Migration for orders table
# ============================================================

ORDERS_TABLE_SQL = """
-- Tabela zamówień
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    client VARCHAR(255),
    date_in DATE DEFAULT CURRENT_DATE,
    date_due DATE,
    status VARCHAR(50) DEFAULT 'new',
    priority VARCHAR(50) DEFAULT 'Normalny',
    notes TEXT,
    parts_count INTEGER DEFAULT 0,
    total_cost DECIMAL(12,2) DEFAULT 0,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client);
CREATE INDEX IF NOT EXISTS idx_orders_date_in ON orders(date_in);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);

-- Tabela pozycji zamówień
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 1,
    name VARCHAR(255) NOT NULL,
    material VARCHAR(50),
    thickness_mm DECIMAL(6,2),
    quantity INTEGER DEFAULT 1,
    width DECIMAL(10,2),
    height DECIMAL(10,2),
    weight_kg DECIMAL(10,3),
    unit_cost DECIMAL(12,2) DEFAULT 0,
    total_cost DECIMAL(12,2) DEFAULT 0,
    filepath TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- RLS (Row Level Security) - opcjonalnie
-- ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;
"""
