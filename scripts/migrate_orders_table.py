"""
Migrate Orders Table
====================
Skrypt migracji tabeli orders - dodaje brakujące kolumny.

Użycie:
    python scripts/migrate_orders_table.py [--check] [--execute]

Opcje:
    --check    Sprawdź aktualny schemat
    --execute  Wykonaj migrację
"""

import sys
import os

# Dodaj ścieżkę główną projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Kolumny wymagane w tabeli orders
REQUIRED_COLUMNS = {
    'id': 'UUID PRIMARY KEY',
    'name': 'VARCHAR(255) NOT NULL',
    'client': 'VARCHAR(255)',
    'customer_name': 'VARCHAR(255)',  # alternatywna nazwa
    'date_in': 'DATE DEFAULT CURRENT_DATE',
    'date_due': 'DATE',
    'status': "VARCHAR(50) DEFAULT 'new'",
    'priority': "VARCHAR(50) DEFAULT 'Normalny'",
    'notes': 'TEXT',
    'parts_count': 'INTEGER DEFAULT 0',
    'total_cost': 'DECIMAL(12,2) DEFAULT 0',
    'metadata': 'JSONB',
    'created_at': 'TIMESTAMP WITH TIME ZONE DEFAULT NOW()',
    'updated_at': 'TIMESTAMP WITH TIME ZONE DEFAULT NOW()'
}

# SQL do dodania brakujących kolumn
ALTER_TABLE_SQL = """
-- Dodaj brakujące kolumny do tabeli orders
-- Uruchom te komendy w Supabase SQL Editor

-- Kolumna client (nazwa klienta)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS client VARCHAR(255);

-- Kolumna customer_name (alternatywna)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255);

-- Upewnij się, że wszystkie kolumny istnieją
ALTER TABLE orders ADD COLUMN IF NOT EXISTS date_in DATE DEFAULT CURRENT_DATE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS date_due DATE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'new';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS priority VARCHAR(50) DEFAULT 'Normalny';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS parts_count INTEGER DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_cost DECIMAL(12,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_date_in ON orders(date_in);
"""


def check_table_schema():
    """Sprawdź aktualny schemat tabeli orders"""
    try:
        from core.supabase_client import get_supabase_client

        client = get_supabase_client()

        print("\n" + "=" * 60)
        print("Checking orders table schema")
        print("=" * 60)

        # Próba pobrania rekordu żeby zobaczyć jakie kolumny są dostępne
        try:
            response = client.table('orders').select('*').limit(1).execute()

            if response.data:
                print("\nAvailable columns (from sample record):")
                for col in response.data[0].keys():
                    print(f"  - {col}")
            else:
                print("\nTable exists but is empty")
                print("Cannot determine column structure without data")

        except Exception as e:
            error_msg = str(e)
            if "Could not find" in error_msg and "column" in error_msg:
                print(f"\nColumn error detected: {error_msg}")
            else:
                print(f"\nError querying table: {e}")

        # Próba INSERT z testowymi danymi
        print("\n" + "-" * 40)
        print("Testing column availability:")

        test_columns = ['id', 'name', 'client', 'customer_name', 'date_in',
                        'date_due', 'status', 'priority', 'notes',
                        'parts_count', 'total_cost', 'metadata']

        for col in test_columns:
            try:
                # Próba select pojedynczej kolumny
                client.table('orders').select(col).limit(1).execute()
                print(f"  ✓ {col}")
            except Exception as e:
                if "Could not find" in str(e):
                    print(f"  ✗ {col} - MISSING")
                else:
                    print(f"  ? {col} - {e}")

        return True

    except Exception as e:
        print(f"\nError: {e}")
        return False


def show_migration_sql():
    """Pokaż SQL do migracji"""
    print("\n" + "=" * 60)
    print("SQL Migration Script")
    print("=" * 60)
    print("\nCopy and run this in Supabase SQL Editor:")
    print("-" * 60)
    print(ALTER_TABLE_SQL)
    print("-" * 60)


def execute_migration():
    """Wykonaj migrację (jeśli możliwe)"""
    try:
        from core.supabase_client import get_supabase_client

        client = get_supabase_client()

        print("\n" + "=" * 60)
        print("Executing Migration")
        print("=" * 60)

        # Supabase nie pozwala na DDL przez REST API
        # Musimy użyć RPC lub SQL Editor
        print("\n⚠ Supabase REST API does not support DDL operations")
        print("  You need to run the SQL manually in Supabase SQL Editor")

        show_migration_sql()

        return False

    except Exception as e:
        print(f"\nError: {e}")
        return False


def create_table_if_not_exists():
    """Utwórz tabelę orders jeśli nie istnieje"""
    sql = """
-- Utwórz tabelę orders (jeśli nie istnieje)
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    client VARCHAR(255),
    customer_name VARCHAR(255),
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

-- Utwórz tabelę order_items (jeśli nie istnieje)
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
CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_date_in ON orders(date_in);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- Tabela klientów
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    short_name VARCHAR(50),
    nip VARCHAR(20),
    email VARCHAR(255),
    phone VARCHAR(50),
    address TEXT,
    notes TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_customers_nip ON customers(nip);
"""
    print("\n" + "=" * 60)
    print("Full Table Creation SQL")
    print("=" * 60)
    print(sql)
    return sql


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Migrate orders table')
    parser.add_argument('--check', action='store_true', help='Check current schema')
    parser.add_argument('--execute', action='store_true', help='Execute migration')
    parser.add_argument('--show-sql', action='store_true', help='Show migration SQL')
    parser.add_argument('--create', action='store_true', help='Show full CREATE TABLE SQL')
    args = parser.parse_args()

    print("=" * 60)
    print("NewERP - Orders Table Migration")
    print("=" * 60)

    if args.check:
        check_table_schema()
    elif args.execute:
        execute_migration()
    elif args.show_sql:
        show_migration_sql()
    elif args.create:
        create_table_if_not_exists()
    else:
        # Default: check and show SQL
        check_table_schema()
        show_migration_sql()

    return 0


if __name__ == "__main__":
    sys.exit(main())
