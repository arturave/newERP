# 🏭 NewERP - Architektura Systemu
## Manufacturing ERP dla Produkcji Laserowej

**Wersja:** 2.0  
**Data:** 2025-11-30  
**Status:** Dokument projektowy

---

## 1. WIZJA I CELE

### 1.1 Cel systemu

NewERP to specjalizowany system ERP dla firm zajmujących się cięciem laserowym blach. System obsługuje pełen cykl:

```
[ZAPYTANIE] → [WYCENA] → [ZAMÓWIENIE] → [PRODUKCJA] → [WYDANIE] → [FAKTURA]
```

### 1.2 Kluczowe wymagania

| Wymaganie | Opis | Priorytet |
|-----------|------|-----------|
| **Szybka wycena** | Kalkulacja kosztów na podstawie plików CAD | Krytyczny |
| **Zarządzanie produktami** | Katalog części z plikami CAD/3D | Krytyczny |
| **Obsługa zamówień** | Od oferty do WZ | Krytyczny |
| **Integracja plików** | DXF, STEP, IGES + podglądy | Wysoki |
| **Raportowanie** | Statystyki, marże, wydajność | Średni |
| **Offline-first** | Praca bez stałego połączenia | Niski |

### 1.3 Ograniczenia technologiczne

- **Backend:** Supabase (PostgreSQL + Storage + Auth)
- **Frontend:** Python + CustomTkinter (desktop)
- **Pliki CAD:** DXF (2D), STEP/IGES (3D)
- **Deployment:** Standalone .exe (PyInstaller)

---

## 2. ARCHITEKTURA WYSOKOPOZIOMOWA

### 2.1 Diagram modułów

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            NewERP APPLICATION                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │  PRODUKTY   │  │   KLIENCI   │  │  ZAMÓWIENIA │  │   WYCENY    │   │
│  │  (Products) │  │ (Customers) │  │  (Orders)   │  │ (Quotations)│   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
│         │                │                │                │          │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐   │
│  │ MATERIAŁY   │  │  ZAŁĄCZNIKI │  │  DOKUMENTY  │  │  RAPORTY    │   │
│  │ (Materials) │  │(Attachments)│  │ (Documents) │  │ (Reports)   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┴──────┘   │
│         │                │                │                           │
│  ═══════╪════════════════╪════════════════╪═══════════════════════════│
│         │                │                │                           │
│  ┌──────┴────────────────┴────────────────┴──────────────────────────┐│
│  │                         CORE LAYER                                 ││
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ││
│  │  │ EventBus   │  │ BaseRepo   │  │BaseService │  │ AuditLog   │  ││
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘  ││
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ││
│  │  │ Supabase   │  │ Storage    │  │  Config    │  │  Logging   │  ││
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘  ││
│  └───────────────────────────────────────────────────────────────────┘│
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            SUPABASE CLOUD                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ PostgreSQL  │  │   Storage   │  │    Auth     │  │  Realtime   │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Warstwy aplikacji (Clean Architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│                         GUI LAYER                                │
│  ProductsWindow, OrdersWindow, CustomersWindow, QuotationsWindow │
│  - Prezentacja danych                                            │
│  - Obsługa zdarzeń użytkownika                                   │
│  - ZERO logiki biznesowej                                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ calls
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                              │
│  ProductService, OrderService, CustomerService, QuotationService │
│  - Logika biznesowa                                              │
│  - Walidacja                                                     │
│  - Transakcje (DB + Storage)                                     │
│  - Emitowanie eventów                                            │
└───────────────────────────────┬─────────────────────────────────┘
                                │ uses
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     REPOSITORY LAYER                             │
│  ProductRepository, OrderRepository, CustomerRepository          │
│  StorageRepository (Supabase Storage)                            │
│  - CRUD operations                                               │
│  - Queries                                                       │
│  - Brak logiki biznesowej                                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ connects
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       DATA LAYER                                 │
│  Supabase Client, PostgreSQL, Storage Bucket                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. WZORCE ARCHITEKTONICZNE

### 3.1 Event-Driven Architecture (EDA)

**Dlaczego?** Moduły muszą reagować na zmiany w innych modułach bez tight coupling.

```python
# core/events.py
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List
from enum import Enum

class EventType(Enum):
    # Product events
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_DELETED = "product.deleted"
    
    # Order events
    ORDER_CREATED = "order.created"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_COMPLETED = "order.completed"
    
    # Customer events
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    
    # Quotation events
    QUOTATION_CREATED = "quotation.created"
    QUOTATION_ACCEPTED = "quotation.accepted"
    QUOTATION_REJECTED = "quotation.rejected"

@dataclass
class Event:
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime
    user_id: str = None
    correlation_id: str = None

class EventBus:
    """Prosty event bus dla komunikacji między modułami"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers: Dict[EventType, List[Callable]] = {}
        return cls._instance
    
    def subscribe(self, event_type: EventType, handler: Callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def publish(self, event: Event):
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus] Handler error: {e}")

# Użycie:
# event_bus = EventBus()
# event_bus.subscribe(EventType.ORDER_CREATED, notify_production)
# event_bus.publish(Event(EventType.ORDER_CREATED, {"order_id": "123"}))
```

### 3.2 Audit Trail

**Dlaczego?** Pełna historia zmian - kto, kiedy, co zmienił.

```sql
-- migrations/002_audit_log.sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Co
    entity_type TEXT NOT NULL,        -- 'product', 'order', 'customer'
    entity_id UUID NOT NULL,
    action TEXT NOT NULL,             -- 'create', 'update', 'delete'
    
    -- Szczegóły
    old_values JSONB,                 -- poprzedni stan
    new_values JSONB,                 -- nowy stan
    changed_fields TEXT[],            -- lista zmienionych pól
    
    -- Kto i kiedy
    user_id UUID REFERENCES auth.users(id),
    user_email TEXT,
    ip_address INET,
    user_agent TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    correlation_id UUID,              -- do grupowania powiązanych zmian
    
    -- Indeksy dla szybkiego wyszukiwania
    CONSTRAINT valid_action CHECK (action IN ('create', 'update', 'delete', 'restore'))
);

CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_correlation ON audit_log(correlation_id);
```

```python
# core/audit.py
class AuditService:
    """Serwis do logowania zmian"""
    
    def __init__(self, client: Client):
        self.client = client
    
    def log(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        old_values: dict = None,
        new_values: dict = None,
        user_id: str = None,
        correlation_id: str = None
    ):
        # Oblicz zmienione pola
        changed_fields = []
        if old_values and new_values:
            for key in set(old_values.keys()) | set(new_values.keys()):
                if old_values.get(key) != new_values.get(key):
                    changed_fields.append(key)
        
        self.client.table('audit_log').insert({
            'entity_type': entity_type,
            'entity_id': entity_id,
            'action': action,
            'old_values': old_values,
            'new_values': new_values,
            'changed_fields': changed_fields,
            'user_id': user_id,
            'correlation_id': correlation_id
        }).execute()
    
    def get_history(self, entity_type: str, entity_id: str) -> List[dict]:
        """Pobierz historię zmian dla encji"""
        response = self.client.table('audit_log')\
            .select('*')\
            .eq('entity_type', entity_type)\
            .eq('entity_id', entity_id)\
            .order('created_at', desc=True)\
            .execute()
        return response.data
```

### 3.3 Soft Delete + Optimistic Locking

**Dlaczego?** Nigdy nie tracimy danych, a wersjonowanie zapobiega konfliktom.

```sql
-- Wspólne kolumny dla wszystkich tabel
-- (dodać do każdej głównej tabeli)

ALTER TABLE products_catalog ADD COLUMN IF NOT EXISTS
    version INTEGER DEFAULT 1;

ALTER TABLE products_catalog ADD COLUMN IF NOT EXISTS
    deleted_at TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE products_catalog ADD COLUMN IF NOT EXISTS
    deleted_by UUID REFERENCES auth.users(id);

-- Funkcja do soft delete
CREATE OR REPLACE FUNCTION soft_delete()
RETURNS TRIGGER AS $$
BEGIN
    NEW.deleted_at = NOW();
    NEW.is_active = FALSE;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- View dla aktywnych rekordów
CREATE OR REPLACE VIEW products_active AS
SELECT * FROM products_catalog 
WHERE is_active = TRUE AND deleted_at IS NULL;
```

```python
# Optimistic locking w repository
class BaseRepository:
    def update_with_version(self, id: str, data: dict, expected_version: int) -> bool:
        """Update z optimistic locking"""
        data['version'] = expected_version + 1
        
        response = self.client.table(self.table_name)\
            .update(data)\
            .eq('id', id)\
            .eq('version', expected_version)\
            .execute()
        
        if not response.data:
            raise OptimisticLockError(
                f"Record {id} was modified by another user. "
                f"Expected version {expected_version}, current version is different."
            )
        
        return True
```

### 3.4 Uniwersalny system filtrowania

**Dlaczego?** Spójne filtrowanie we wszystkich modułach.

```python
# core/filters.py
from dataclasses import dataclass
from typing import Any, List, Optional
from enum import Enum

class FilterOperator(Enum):
    EQ = "eq"           # równe
    NEQ = "neq"         # różne
    GT = "gt"           # większe
    GTE = "gte"         # większe lub równe
    LT = "lt"           # mniejsze
    LTE = "lte"         # mniejsze lub równe
    LIKE = "like"       # zawiera (case-insensitive)
    IN = "in"           # w zbiorze
    NOT_IN = "not_in"   # nie w zbiorze
    IS_NULL = "is_null" # jest NULL
    NOT_NULL = "not_null"  # nie jest NULL
    BETWEEN = "between"    # między

@dataclass
class Filter:
    field: str
    operator: FilterOperator
    value: Any

@dataclass
class Sort:
    field: str
    desc: bool = False

@dataclass
class QueryParams:
    filters: List[Filter] = None
    sorts: List[Sort] = None
    limit: int = 100
    offset: int = 0
    search: str = None
    search_fields: List[str] = None

class QueryBuilder:
    """Buduje zapytania Supabase z QueryParams"""
    
    def __init__(self, client, table_name: str):
        self.query = client.table(table_name).select('*')
    
    def apply_filters(self, params: QueryParams):
        if not params.filters:
            return self
        
        for f in params.filters:
            if f.operator == FilterOperator.EQ:
                self.query = self.query.eq(f.field, f.value)
            elif f.operator == FilterOperator.NEQ:
                self.query = self.query.neq(f.field, f.value)
            elif f.operator == FilterOperator.GT:
                self.query = self.query.gt(f.field, f.value)
            elif f.operator == FilterOperator.GTE:
                self.query = self.query.gte(f.field, f.value)
            elif f.operator == FilterOperator.LT:
                self.query = self.query.lt(f.field, f.value)
            elif f.operator == FilterOperator.LTE:
                self.query = self.query.lte(f.field, f.value)
            elif f.operator == FilterOperator.LIKE:
                self.query = self.query.ilike(f.field, f'%{f.value}%')
            elif f.operator == FilterOperator.IN:
                self.query = self.query.in_(f.field, f.value)
            elif f.operator == FilterOperator.IS_NULL:
                self.query = self.query.is_(f.field, 'null')
            elif f.operator == FilterOperator.NOT_NULL:
                self.query = self.query.not_.is_(f.field, 'null')
        
        return self
    
    def apply_search(self, params: QueryParams):
        """Full-text search po wielu polach"""
        if not params.search or not params.search_fields:
            return self
        
        # Supabase: or filter
        conditions = []
        for field in params.search_fields:
            conditions.append(f"{field}.ilike.%{params.search}%")
        
        self.query = self.query.or_(','.join(conditions))
        return self
    
    def apply_sorting(self, params: QueryParams):
        if not params.sorts:
            return self
        
        for sort in params.sorts:
            self.query = self.query.order(sort.field, desc=sort.desc)
        
        return self
    
    def apply_pagination(self, params: QueryParams):
        self.query = self.query.range(
            params.offset, 
            params.offset + params.limit - 1
        )
        return self
    
    def execute(self):
        return self.query.execute()
```

---

## 4. MODUŁY SYSTEMU

### 4.1 Status implementacji

| Moduł | Status | Opis |
|-------|--------|------|
| **products** | ✅ 90% | Katalog produktów, CAD, miniatury, kompresja |
| **materials** | 🟡 50% | Słownik materiałów (do integracji) |
| **customers** | ⬜ 0% | Kartoteka klientów |
| **orders** | ⬜ 0% | Zamówienia produkcyjne |
| **order_items** | ⬜ 0% | Pozycje zamówień |
| **quotations** | ⬜ 0% | Wyceny i oferty |
| **attachments** | ⬜ 0% | Uniwersalny system załączników |
| **documents** | ⬜ 0% | Generowanie dokumentów (WZ, faktura) |
| **reports** | ⬜ 0% | Raporty i analizy |

### 4.2 Szczegóły modułów

#### 4.2.1 CUSTOMERS (Klienci)

```
customers/
├── __init__.py
├── repository.py      # CustomerRepository
├── service.py         # CustomerService
├── models.py          # Dataclasses
└── gui/
    ├── __init__.py
    ├── customers_window.py
    └── customer_edit_dialog.py
```

**Tabela SQL:**
```sql
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Podstawowe dane
    code TEXT UNIQUE NOT NULL,         -- np. "ABC001"
    name TEXT NOT NULL,
    short_name TEXT,                   -- skrót dla szybkiego wyboru
    
    -- Typ klienta
    customer_type TEXT DEFAULT 'company',  -- 'company', 'individual'
    
    -- Dane firmowe
    nip TEXT,
    regon TEXT,
    krs TEXT,
    
    -- Adresy (JSONB dla elastyczności)
    address_main JSONB,                -- {street, city, postal_code, country}
    address_shipping JSONB,            -- adres dostawy (opcjonalny)
    
    -- Kontakt
    email TEXT,
    phone TEXT,
    website TEXT,
    
    -- Osoby kontaktowe (array)
    contacts JSONB DEFAULT '[]',       -- [{name, role, email, phone}]
    
    -- Warunki handlowe
    payment_days INTEGER DEFAULT 14,   -- termin płatności
    credit_limit NUMERIC(12,2),        -- limit kredytowy
    discount_percent NUMERIC(5,2) DEFAULT 0,
    price_list TEXT DEFAULT 'standard',
    
    -- Notatki
    notes TEXT,
    tags TEXT[],
    
    -- Metadane
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    version INTEGER DEFAULT 1,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_customers_code ON customers(code);
CREATE INDEX idx_customers_nip ON customers(nip) WHERE nip IS NOT NULL;
CREATE INDEX idx_customers_name ON customers USING gin(name gin_trgm_ops);
```

#### 4.2.2 ORDERS (Zamówienia)

```
orders/
├── __init__.py
├── repository.py      # OrderRepository
├── service.py         # OrderService  
├── models.py          # Order, OrderStatus
├── workflows.py       # StatusWorkflow, OrderStateMachine
└── gui/
    ├── __init__.py
    ├── orders_window.py
    ├── order_edit_dialog.py
    └── order_items_widget.py
```

**Diagram stanów zamówienia:**
```
    ┌─────────┐
    │  DRAFT  │ ← Nowe zamówienie
    └────┬────┘
         │ confirm()
         ▼
    ┌─────────┐
    │CONFIRMED│ ← Zatwierdzone
    └────┬────┘
         │ start_production()
         ▼
    ┌─────────┐
    │IN_PROD  │ ← W produkcji
    └────┬────┘
         │ complete_production()
         ▼
    ┌─────────┐
    │ READY   │ ← Gotowe do odbioru
    └────┬────┘
         │ ship()
         ▼
    ┌─────────┐
    │ SHIPPED │ ← Wysłane
    └────┬────┘
         │ invoice()
         ▼
    ┌─────────┐
    │INVOICED │ ← Zafakturowane
    └────┬────┘
         │ pay()
         ▼
    ┌─────────┐
    │  PAID   │ ← Opłacone
    └─────────┘
    
    (Z każdego stanu można przejść do CANCELLED)
```

**Tabela SQL:**
```sql
CREATE TYPE order_status AS ENUM (
    'draft',
    'confirmed', 
    'in_production',
    'ready',
    'shipped',
    'invoiced',
    'paid',
    'cancelled'
);

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identyfikacja
    order_number TEXT UNIQUE NOT NULL,    -- np. "ZP/2025/001234"
    
    -- Powiązania
    customer_id UUID NOT NULL REFERENCES customers(id),
    quotation_id UUID REFERENCES quotations(id),  -- opcjonalna wycena źródłowa
    
    -- Status
    status order_status DEFAULT 'draft',
    status_changed_at TIMESTAMPTZ DEFAULT NOW(),
    status_changed_by UUID,
    
    -- Daty
    order_date DATE DEFAULT CURRENT_DATE,
    required_date DATE,                   -- wymagany termin
    promised_date DATE,                   -- obiecany termin
    shipped_date DATE,
    
    -- Wartości (obliczane z pozycji)
    total_net NUMERIC(12,2) DEFAULT 0,
    total_vat NUMERIC(12,2) DEFAULT 0,
    total_gross NUMERIC(12,2) DEFAULT 0,
    
    -- Warunki
    payment_days INTEGER,
    delivery_method TEXT,
    delivery_address JSONB,
    
    -- Notatki
    notes_internal TEXT,                  -- wewnętrzne
    notes_production TEXT,                -- dla produkcji
    notes_delivery TEXT,                  -- dla dostawy
    
    -- Dokumenty powiązane
    wz_number TEXT,                       -- numer WZ
    invoice_number TEXT,                  -- numer faktury
    
    -- Metadane
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    version INTEGER DEFAULT 1,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_orders_number ON orders(order_number);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status) WHERE is_active = TRUE;
CREATE INDEX idx_orders_dates ON orders(order_date, required_date);
```

#### 4.2.3 ORDER_ITEMS (Pozycje zamówień)

```sql
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Powiązania
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products_catalog(id),
    
    -- Pozycja
    position INTEGER NOT NULL,           -- kolejność na zamówieniu
    
    -- Dane produktu (snapshot - kopia w momencie zamówienia)
    product_code TEXT,
    product_name TEXT NOT NULL,
    
    -- Parametry materiałowe
    material_id UUID REFERENCES materials_dict(id),
    material_name TEXT,
    thickness_mm NUMERIC(6,2),
    
    -- Ilości
    quantity INTEGER NOT NULL DEFAULT 1,
    quantity_produced INTEGER DEFAULT 0,
    quantity_shipped INTEGER DEFAULT 0,
    
    -- Wymiary (dla kalkulacji)
    width_mm NUMERIC(10,2),
    height_mm NUMERIC(10,2),
    area_m2 NUMERIC(10,4),              -- obliczona powierzchnia
    cutting_length_mm NUMERIC(12,2),    -- długość cięcia
    
    -- Ceny
    unit_price_net NUMERIC(12,4),
    discount_percent NUMERIC(5,2) DEFAULT 0,
    total_net NUMERIC(12,2),
    vat_rate NUMERIC(4,2) DEFAULT 23,
    total_gross NUMERIC(12,2),
    
    -- Koszt własny
    material_cost NUMERIC(12,4),
    cutting_cost NUMERIC(12,4),
    total_cost NUMERIC(12,4),
    margin_percent NUMERIC(6,2),
    
    -- Pliki CAD (ścieżki w storage)
    cad_2d_path TEXT,
    cad_3d_path TEXT,
    
    -- Notatki
    notes TEXT,
    
    -- Status pozycji
    status TEXT DEFAULT 'pending',       -- 'pending', 'in_production', 'completed'
    
    -- Metadane
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
```

#### 4.2.4 QUOTATIONS (Wyceny)

```
quotations/
├── __init__.py
├── repository.py
├── service.py
├── calculator.py      # Kalkulator kosztów cięcia
├── models.py
└── gui/
    ├── __init__.py
    ├── quotations_window.py
    ├── quotation_edit_dialog.py
    └── cost_calculator_widget.py
```

**Kalkulator kosztów:**
```python
# quotations/calculator.py
@dataclass
class CuttingCost:
    """Wynik kalkulacji kosztów cięcia"""
    material_cost: float      # koszt materiału
    cutting_cost: float       # koszt cięcia
    setup_cost: float         # koszt przygotowania
    total_cost: float         # suma kosztów
    suggested_price: float    # sugerowana cena (z marżą)
    margin_percent: float     # marża %
    
    # Szczegóły
    sheet_area_m2: float
    cutting_length_mm: float
    cutting_time_min: float
    
class CostCalculator:
    """Kalkulator kosztów cięcia laserowego"""
    
    def __init__(self, materials_service, settings):
        self.materials = materials_service
        self.settings = settings
    
    def calculate(
        self,
        material_id: str,
        thickness_mm: float,
        width_mm: float,
        height_mm: float,
        cutting_length_mm: float,
        quantity: int = 1,
        margin_percent: float = None
    ) -> CuttingCost:
        """
        Kalkulacja kosztów cięcia:
        1. Koszt materiału = powierzchnia × cena/m² × (1 + odpad%)
        2. Koszt cięcia = długość cięcia × stawka/mm × współczynnik grubości
        3. Koszt przygotowania = stała + (czas przygotowania × stawka/h)
        """
        
        # Pobierz parametry materiału
        material = self.materials.get(material_id)
        
        # Powierzchnia arkusza
        sheet_area_m2 = (width_mm * height_mm) / 1_000_000
        
        # Koszt materiału
        material_price_m2 = material['price_per_m2']
        waste_factor = 1 + (material.get('waste_percent', 15) / 100)
        material_cost = sheet_area_m2 * material_price_m2 * waste_factor * quantity
        
        # Koszt cięcia
        cutting_rate = self._get_cutting_rate(material, thickness_mm)
        cutting_cost = (cutting_length_mm / 1000) * cutting_rate * quantity
        
        # Koszt przygotowania (jednorazowy)
        setup_cost = self.settings.get('setup_cost_base', 50)
        
        # Suma
        total_cost = material_cost + cutting_cost + setup_cost
        
        # Marża
        if margin_percent is None:
            margin_percent = self.settings.get('default_margin', 30)
        
        suggested_price = total_cost * (1 + margin_percent / 100)
        
        # Czas cięcia (dla informacji)
        cutting_speed = self._get_cutting_speed(material, thickness_mm)
        cutting_time_min = cutting_length_mm / cutting_speed if cutting_speed > 0 else 0
        
        return CuttingCost(
            material_cost=round(material_cost, 2),
            cutting_cost=round(cutting_cost, 2),
            setup_cost=round(setup_cost, 2),
            total_cost=round(total_cost, 2),
            suggested_price=round(suggested_price, 2),
            margin_percent=margin_percent,
            sheet_area_m2=round(sheet_area_m2, 4),
            cutting_length_mm=cutting_length_mm,
            cutting_time_min=round(cutting_time_min, 1)
        )
    
    def _get_cutting_rate(self, material: dict, thickness: float) -> float:
        """Stawka cięcia zależna od materiału i grubości"""
        base_rate = material.get('cutting_rate_base', 0.5)  # PLN/mm
        thickness_factor = 1 + (thickness / 10) * 0.3  # +30% za każde 10mm
        return base_rate * thickness_factor
    
    def _get_cutting_speed(self, material: dict, thickness: float) -> float:
        """Prędkość cięcia mm/min"""
        base_speed = material.get('cutting_speed_base', 5000)
        # Prędkość maleje z grubością
        return base_speed / (1 + thickness / 5)
```

---

## 5. STRUKTURA KATALOGÓW

```
NewERP/
├── main.py                      # Entry point
├── requirements.txt
├── setup.bat / setup.sh
├── run.bat / run.sh
├── .env.example
├── .gitignore
│
├── config/
│   ├── __init__.py
│   └── settings.py              # Konfiguracja aplikacji
│
├── core/                        # Wspólne komponenty
│   ├── __init__.py
│   ├── supabase_client.py       # Singleton klienta Supabase
│   ├── base_repository.py       # Bazowa klasa repozytorium
│   ├── base_service.py          # Bazowa klasa serwisu
│   ├── events.py                # Event bus
│   ├── audit.py                 # Audit trail
│   ├── filters.py               # Query builder
│   ├── exceptions.py            # Własne wyjątki
│   └── utils.py                 # Pomocnicze funkcje
│
├── products/                    # ✅ Moduł produktów (GOTOWY)
│   ├── __init__.py
│   ├── repository.py
│   ├── service.py
│   ├── storage.py
│   ├── paths.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── compression.py
│   │   └── thumbnail_generator.py
│   └── gui/
│       ├── __init__.py
│       ├── products_window.py
│       └── product_edit_dialog.py
│
├── customers/                   # ⬜ Moduł klientów
│   ├── __init__.py
│   ├── repository.py
│   ├── service.py
│   └── gui/
│       ├── __init__.py
│       ├── customers_window.py
│       └── customer_edit_dialog.py
│
├── orders/                      # ⬜ Moduł zamówień
│   ├── __init__.py
│   ├── repository.py
│   ├── service.py
│   ├── workflows.py             # State machine
│   └── gui/
│       ├── __init__.py
│       ├── orders_window.py
│       ├── order_edit_dialog.py
│       └── order_items_widget.py
│
├── quotations/                  # ⬜ Moduł wycen
│   ├── __init__.py
│   ├── repository.py
│   ├── service.py
│   ├── calculator.py
│   └── gui/
│       ├── __init__.py
│       ├── quotations_window.py
│       └── quotation_edit_dialog.py
│
├── materials/                   # 🟡 Moduł materiałów
│   ├── __init__.py
│   ├── repository.py
│   ├── service.py
│   └── gui/
│       └── materials_dialog.py
│
├── attachments/                 # ⬜ System załączników
│   ├── __init__.py
│   ├── repository.py
│   ├── service.py
│   └── gui/
│       └── attachments_widget.py
│
├── documents/                   # ⬜ Generowanie dokumentów
│   ├── __init__.py
│   ├── generators/
│   │   ├── wz_generator.py
│   │   ├── invoice_generator.py
│   │   └── quotation_pdf.py
│   └── templates/
│
├── reports/                     # ⬜ Raporty
│   ├── __init__.py
│   ├── service.py
│   └── gui/
│       └── reports_window.py
│
├── migrations/                  # Migracje SQL
│   ├── 001_products_url_to_path.sql
│   ├── 002_audit_log.sql
│   ├── 003_customers.sql
│   ├── 004_orders.sql
│   └── 005_quotations.sql
│
├── docs/                        # Dokumentacja
│   ├── ARCHITECTURE.md          # Ten dokument
│   ├── API.md
│   ├── DEPLOYMENT.md
│   └── USER_GUIDE.md
│
└── tests/                       # Testy
    ├── __init__.py
    ├── test_products.py
    ├── test_customers.py
    ├── test_orders.py
    └── test_integration.py
```

---

## 6. PLAN IMPLEMENTACJI

### Faza 1: Core Layer (3-4 dni)
1. ⬜ `core/base_repository.py` - bazowa klasa z CRUD, soft delete, versioning
2. ⬜ `core/base_service.py` - bazowa klasa z transakcjami i eventami
3. ⬜ `core/events.py` - event bus
4. ⬜ `core/audit.py` - audit trail
5. ⬜ `core/filters.py` - query builder
6. ⬜ `core/exceptions.py` - własne wyjątki

### Faza 2: Customers (2-3 dni)
1. ⬜ Migracja SQL `003_customers.sql`
2. ⬜ `customers/repository.py`
3. ⬜ `customers/service.py`
4. ⬜ `customers/gui/customers_window.py`
5. ⬜ `customers/gui/customer_edit_dialog.py`

### Faza 3: Materials (1-2 dni)
1. ⬜ Integracja z istniejącą tabelą `materials_dict`
2. ⬜ `materials/repository.py`
3. ⬜ `materials/service.py`
4. ⬜ `materials/gui/materials_dialog.py`

### Faza 4: Orders (4-5 dni)
1. ⬜ Migracja SQL `004_orders.sql`
2. ⬜ `orders/repository.py`
3. ⬜ `orders/service.py`
4. ⬜ `orders/workflows.py` - state machine
5. ⬜ `orders/gui/orders_window.py`
6. ⬜ `orders/gui/order_edit_dialog.py`
7. ⬜ `orders/gui/order_items_widget.py`

### Faza 5: Quotations (3-4 dni)
1. ⬜ Migracja SQL `005_quotations.sql`
2. ⬜ `quotations/calculator.py`
3. ⬜ `quotations/repository.py`
4. ⬜ `quotations/service.py`
5. ⬜ `quotations/gui/quotations_window.py`
6. ⬜ `quotations/gui/quotation_edit_dialog.py`

### Faza 6: Integration (2-3 dni)
1. ⬜ Integracja modułów w main.py
2. ⬜ Menu główne z nawigacją
3. ⬜ Event handlers między modułami
4. ⬜ Testy integracyjne

### Faza 7: Documents & Reports (3-4 dni)
1. ⬜ Generator WZ
2. ⬜ Generator oferty PDF
3. ⬜ Podstawowe raporty

**Szacowany czas: 18-25 dni roboczych**

---

## 7. MOJE PRZEMYŚLENIA I REKOMENDACJE

### 7.1 Co zrobiliśmy dobrze

1. **Clean Architecture** - separacja warstw działa świetnie w module produktów
2. **Deterministic paths** - przewidywalne ścieżki w Storage upraszczają debugowanie
3. **Kompresja CAD** - 85% oszczędności transferu to znaczące usprawnienie
4. **Signed URLs** - bezpieczny dostęp do plików

### 7.2 Co możemy ulepszyć

1. **Lazy Loading** - obecnie ładujemy wszystkie produkty na raz
   - Rozwiązanie: Paginacja + infinite scroll

2. **Brak cache'a** - każde odświeżenie = request do DB
   - Rozwiązanie: In-memory cache z TTL

3. **Brak offline mode** - aplikacja wymaga połączenia
   - Rozwiązanie: SQLite jako local cache (przyszłość)

4. **Monolityczne GUI** - products_window.py ma 1000+ linii
   - Rozwiązanie: Wydzielenie komponentów (FilterPanel, ProductList, PreviewPanel)

### 7.3 Kluczowe decyzje projektowe

| Decyzja | Wybór | Uzasadnienie |
|---------|-------|--------------|
| Event Bus | Synchroniczny | Prostota, brak potrzeby async |
| Audit | Tabela SQL | Queryable, standardowe backup |
| Soft Delete | Wszędzie | Bezpieczeństwo danych |
| Filtrowanie | Query Builder | Spójność, testowalność |
| Status Orders | State Machine | Walidacja przejść |
| Wyceny | Calculator | Separacja logiki |

### 7.4 Na co uważać

1. **N+1 queries** - używaj JOIN gdzie możliwe
2. **Transaction boundaries** - DB + Storage razem
3. **Memory leaks w GUI** - `after_cancel`, `destroy()` obrazków
4. **Thread safety** - Tkinter wymaga main thread dla GUI

---

## 8. NASTĘPNE KROKI

**Natychmiastowe:**
1. Stworzenie `core/base_repository.py` i `core/base_service.py`
2. Refaktoryzacja `products/` do użycia bazowych klas
3. Implementacja `customers/` jako wzorca dla kolejnych modułów

**Ten tydzień:**
1. Moduł klientów (customers)
2. Migracje SQL
3. Integracja z menu głównym

**Przyszły tydzień:**
1. Moduł zamówień (orders)
2. State machine dla statusów
3. Powiązanie orders ↔ customers ↔ products

---

*Dokument architektury NewERP v2.0*
*Ostatnia aktualizacja: 2025-11-30*
