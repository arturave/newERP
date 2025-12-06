-- ============================================================
-- NewERP - Orders Table Migration
-- ============================================================
-- Uruchom w Supabase SQL Editor
-- ============================================================

-- Dodaj brakujace kolumny do tabeli orders
ALTER TABLE orders ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS client VARCHAR(255);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS date_in DATE DEFAULT CURRENT_DATE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS date_due DATE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS priority VARCHAR(50) DEFAULT 'Normalny';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS parts_count INTEGER DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_cost DECIMAL(12,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS metadata JSONB;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_date_in ON orders(date_in);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);

-- ============================================================
-- Tabela order_items (pozycje zamowien)
-- ============================================================
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

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- ============================================================
-- Tabela customers (klienci)
-- ============================================================
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
CREATE INDEX IF NOT EXISTS idx_customers_is_active ON customers(is_active);
