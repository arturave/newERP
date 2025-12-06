"""
NewERP - Query Builder / Filter System
======================================
Uniwersalny system filtrowania i wyszukiwania dla wszystkich modułów.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple, Union
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class FilterOperator(Enum):
    """Operatory filtrowania"""
    
    # Porównania
    EQ = "eq"           # równe (=)
    NEQ = "neq"         # różne (!=)
    GT = "gt"           # większe (>)
    GTE = "gte"         # większe lub równe (>=)
    LT = "lt"           # mniejsze (<)
    LTE = "lte"         # mniejsze lub równe (<=)
    
    # Tekst
    LIKE = "like"       # zawiera (case-insensitive)
    ILIKE = "ilike"     # zawiera (case-insensitive, alias)
    STARTS_WITH = "starts_with"  # zaczyna się od
    ENDS_WITH = "ends_with"      # kończy się na
    
    # Zbiory
    IN = "in"           # wartość w zbiorze
    NOT_IN = "not_in"   # wartość nie w zbiorze
    
    # NULL
    IS_NULL = "is_null"     # jest NULL
    NOT_NULL = "not_null"   # nie jest NULL
    
    # Zakresy
    BETWEEN = "between"     # między (inclusive)
    
    # Tablice (PostgreSQL)
    CONTAINS = "contains"   # tablica zawiera element
    CONTAINED_BY = "contained_by"  # tablica jest podzbiorem
    OVERLAPS = "overlaps"   # tablice mają wspólne elementy


@dataclass
class Filter:
    """
    Pojedynczy filtr.
    
    Examples:
        Filter("status", FilterOperator.EQ, "active")
        Filter("price", FilterOperator.GTE, 100)
        Filter("category", FilterOperator.IN, ["A", "B", "C"])
        Filter("deleted_at", FilterOperator.IS_NULL)
        Filter("created_at", FilterOperator.BETWEEN, ("2025-01-01", "2025-12-31"))
    """
    field: str
    operator: FilterOperator
    value: Any = None
    
    def __post_init__(self):
        # Walidacja
        if self.operator in (FilterOperator.IS_NULL, FilterOperator.NOT_NULL):
            self.value = None
        elif self.operator == FilterOperator.BETWEEN:
            if not isinstance(self.value, (tuple, list)) or len(self.value) != 2:
                raise ValueError("BETWEEN requires a tuple/list of (start, end)")
        elif self.operator in (FilterOperator.IN, FilterOperator.NOT_IN):
            if not isinstance(self.value, (list, tuple, set)):
                self.value = [self.value]


@dataclass
class Sort:
    """
    Kryterium sortowania.
    
    Examples:
        Sort("created_at", desc=True)
        Sort("name")  # ascending by default
    """
    field: str
    desc: bool = False
    nulls_first: bool = False  # PostgreSQL: NULLS FIRST/LAST


@dataclass
class Pagination:
    """Parametry paginacji"""
    limit: int = 100
    offset: int = 0
    
    @property
    def page(self) -> int:
        """Numer strony (1-indexed)"""
        return (self.offset // self.limit) + 1 if self.limit > 0 else 1
    
    @classmethod
    def from_page(cls, page: int, page_size: int = 100) -> 'Pagination':
        """Utwórz z numeru strony"""
        return cls(limit=page_size, offset=(page - 1) * page_size)


@dataclass
class QueryParams:
    """
    Kompletne parametry zapytania.
    
    Examples:
        params = QueryParams(
            filters=[
                Filter("is_active", FilterOperator.EQ, True),
                Filter("category", FilterOperator.IN, ["laser", "cnc"])
            ],
            sorts=[Sort("created_at", desc=True)],
            search="motor",
            search_fields=["name", "idx_code", "description"],
            pagination=Pagination(limit=50, offset=0)
        )
    """
    filters: List[Filter] = field(default_factory=list)
    sorts: List[Sort] = field(default_factory=list)
    search: Optional[str] = None
    search_fields: List[str] = field(default_factory=list)
    pagination: Pagination = field(default_factory=Pagination)
    
    # Dodatkowe opcje
    include_deleted: bool = False  # czy włączyć soft-deleted
    select_fields: List[str] = field(default_factory=list)  # konkretne kolumny
    
    def add_filter(
        self, 
        field: str, 
        operator: Union[FilterOperator, str], 
        value: Any = None
    ) -> 'QueryParams':
        """Dodaj filtr (fluent API)"""
        if isinstance(operator, str):
            operator = FilterOperator(operator)
        self.filters.append(Filter(field, operator, value))
        return self
    
    def add_sort(self, field: str, desc: bool = False) -> 'QueryParams':
        """Dodaj sortowanie (fluent API)"""
        self.sorts.append(Sort(field, desc))
        return self
    
    def set_search(self, query: str, fields: List[str]) -> 'QueryParams':
        """Ustaw wyszukiwanie (fluent API)"""
        self.search = query
        self.search_fields = fields
        return self
    
    def set_page(self, page: int, page_size: int = 100) -> 'QueryParams':
        """Ustaw stronę (fluent API)"""
        self.pagination = Pagination.from_page(page, page_size)
        return self


class QueryBuilder:
    """
    Buduje zapytania Supabase z QueryParams.
    
    Usage:
        builder = QueryBuilder(client, "products_catalog")
        results = builder.apply(params).execute()
    """
    
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.query = None
        self._reset()
    
    def _reset(self):
        """Reset query do stanu początkowego"""
        self.query = self.client.table(self.table_name).select('*')
    
    def select(self, columns: Union[str, List[str]] = '*') -> 'QueryBuilder':
        """Ustaw kolumny do pobrania"""
        if isinstance(columns, list):
            columns = ', '.join(columns)
        self.query = self.client.table(self.table_name).select(columns)
        return self
    
    def apply(self, params: QueryParams) -> 'QueryBuilder':
        """Zastosuj wszystkie parametry"""
        self.apply_filters(params)
        self.apply_search(params)
        self.apply_sorting(params)
        self.apply_pagination(params)
        return self
    
    def apply_filters(self, params: QueryParams) -> 'QueryBuilder':
        """Zastosuj filtry"""
        if not params.filters:
            return self
        
        for f in params.filters:
            self._apply_filter(f)
        
        # Domyślnie ukryj soft-deleted
        if not params.include_deleted:
            self.query = self.query.eq('is_active', True)
        
        return self
    
    def _apply_filter(self, f: Filter) -> None:
        """Zastosuj pojedynczy filtr"""
        
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
        
        elif f.operator in (FilterOperator.LIKE, FilterOperator.ILIKE):
            self.query = self.query.ilike(f.field, f'%{f.value}%')
        
        elif f.operator == FilterOperator.STARTS_WITH:
            self.query = self.query.ilike(f.field, f'{f.value}%')
        
        elif f.operator == FilterOperator.ENDS_WITH:
            self.query = self.query.ilike(f.field, f'%{f.value}')
        
        elif f.operator == FilterOperator.IN:
            self.query = self.query.in_(f.field, list(f.value))
        
        elif f.operator == FilterOperator.NOT_IN:
            # Supabase nie ma not.in_ - użyj neq dla każdego
            for val in f.value:
                self.query = self.query.neq(f.field, val)
        
        elif f.operator == FilterOperator.IS_NULL:
            self.query = self.query.is_(f.field, 'null')
        
        elif f.operator == FilterOperator.NOT_NULL:
            self.query = self.query.not_.is_(f.field, 'null')
        
        elif f.operator == FilterOperator.BETWEEN:
            start, end = f.value
            self.query = self.query.gte(f.field, start).lte(f.field, end)
        
        elif f.operator == FilterOperator.CONTAINS:
            self.query = self.query.contains(f.field, f.value)
        
        elif f.operator == FilterOperator.CONTAINED_BY:
            self.query = self.query.contained_by(f.field, f.value)
        
        elif f.operator == FilterOperator.OVERLAPS:
            self.query = self.query.overlaps(f.field, f.value)
    
    def apply_search(self, params: QueryParams) -> 'QueryBuilder':
        """
        Zastosuj full-text search po wielu polach.
        Używa OR między polami.
        """
        if not params.search or not params.search_fields:
            return self
        
        # Buduj warunek OR
        conditions = []
        for field in params.search_fields:
            conditions.append(f"{field}.ilike.%{params.search}%")
        
        if conditions:
            self.query = self.query.or_(','.join(conditions))
        
        return self
    
    def apply_sorting(self, params: QueryParams) -> 'QueryBuilder':
        """Zastosuj sortowanie"""
        if not params.sorts:
            return self
        
        for sort in params.sorts:
            self.query = self.query.order(sort.field, desc=sort.desc)
        
        return self
    
    def apply_pagination(self, params: QueryParams) -> 'QueryBuilder':
        """Zastosuj paginację"""
        p = params.pagination
        self.query = self.query.range(p.offset, p.offset + p.limit - 1)
        return self
    
    def execute(self) -> Tuple[List[dict], int]:
        """
        Wykonaj zapytanie.
        
        Returns:
            Tuple[List[dict], int]: (dane, total_count)
        """
        try:
            # Pobierz dane
            response = self.query.execute()
            data = response.data or []
            
            # TODO: Supabase count wymaga osobnego zapytania
            # Na razie zwracamy len(data)
            count = len(data)
            
            return data, count
            
        except Exception as e:
            logger.error(f"[QueryBuilder] Query failed: {e}")
            raise
        finally:
            self._reset()
    
    def first(self) -> Optional[dict]:
        """Wykonaj i zwróć pierwszy wynik"""
        data, _ = self.execute()
        return data[0] if data else None
    
    def count(self) -> int:
        """Zwróć tylko liczbę wyników"""
        _, count = self.execute()
        return count


# ============================================================
# Helper Functions
# ============================================================

def create_query_params(
    search: str = None,
    search_fields: List[str] = None,
    page: int = 1,
    page_size: int = 100,
    sort_by: str = None,
    sort_desc: bool = False,
    **filters
) -> QueryParams:
    """
    Helper do szybkiego tworzenia QueryParams.
    
    Usage:
        params = create_query_params(
            search="motor",
            search_fields=["name", "description"],
            page=1,
            page_size=50,
            sort_by="created_at",
            sort_desc=True,
            category="laser",
            is_active=True
        )
    """
    params = QueryParams(
        pagination=Pagination.from_page(page, page_size)
    )
    
    if search and search_fields:
        params.search = search
        params.search_fields = search_fields
    
    if sort_by:
        params.sorts.append(Sort(sort_by, sort_desc))
    
    # Konwertuj kwargs na filtry
    for field, value in filters.items():
        if value is not None:
            params.filters.append(Filter(field, FilterOperator.EQ, value))
    
    return params


def parse_sort_string(sort_str: str) -> Sort:
    """
    Parsuj string sortowania (np. z URL).
    
    Examples:
        parse_sort_string("name")          -> Sort("name", desc=False)
        parse_sort_string("-created_at")   -> Sort("created_at", desc=True)
        parse_sort_string("+price")        -> Sort("price", desc=False)
    """
    if sort_str.startswith('-'):
        return Sort(sort_str[1:], desc=True)
    elif sort_str.startswith('+'):
        return Sort(sort_str[1:], desc=False)
    return Sort(sort_str, desc=False)


def parse_filter_string(filter_str: str) -> Filter:
    """
    Parsuj string filtra (np. z URL).
    
    Format: field__operator=value
    
    Examples:
        parse_filter_string("price__gte=100")     -> Filter("price", GTE, 100)
        parse_filter_string("category__in=A,B,C") -> Filter("category", IN, ["A","B","C"])
        parse_filter_string("name__like=motor")   -> Filter("name", LIKE, "motor")
    """
    if '__' in filter_str:
        field_op, value = filter_str.split('=', 1)
        field, op_str = field_op.rsplit('__', 1)
        
        try:
            operator = FilterOperator(op_str)
        except ValueError:
            operator = FilterOperator.EQ
            field = field_op.split('=')[0]
            value = filter_str.split('=')[1]
    else:
        field, value = filter_str.split('=', 1)
        operator = FilterOperator.EQ
    
    # Konwertuj wartość
    if operator in (FilterOperator.IN, FilterOperator.NOT_IN):
        value = value.split(',')
    elif value.lower() == 'true':
        value = True
    elif value.lower() == 'false':
        value = False
    elif value.lower() == 'null':
        value = None
    else:
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass  # zostaw jako string
    
    return Filter(field, operator, value)


# ============================================================
# Predefined Filters
# ============================================================

class CommonFilters:
    """Często używane filtry"""
    
    @staticmethod
    def active_only() -> Filter:
        return Filter("is_active", FilterOperator.EQ, True)
    
    @staticmethod
    def not_deleted() -> Filter:
        return Filter("deleted_at", FilterOperator.IS_NULL)
    
    @staticmethod
    def created_after(date: str) -> Filter:
        return Filter("created_at", FilterOperator.GTE, date)
    
    @staticmethod
    def created_before(date: str) -> Filter:
        return Filter("created_at", FilterOperator.LTE, date)
    
    @staticmethod
    def created_between(start: str, end: str) -> Filter:
        return Filter("created_at", FilterOperator.BETWEEN, (start, end))
    
    @staticmethod
    def by_customer(customer_id: str) -> Filter:
        return Filter("customer_id", FilterOperator.EQ, customer_id)
    
    @staticmethod
    def by_status(status: str) -> Filter:
        return Filter("status", FilterOperator.EQ, status)
    
    @staticmethod
    def by_statuses(statuses: List[str]) -> Filter:
        return Filter("status", FilterOperator.IN, statuses)
