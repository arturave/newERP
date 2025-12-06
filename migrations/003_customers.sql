-- ============================================================
-- MIGRACJA: customers - Kartoteka klientów
-- Autor: NewERP Team
-- Data: 2025-11-30
-- ============================================================

-- UWAGA: Wykonaj BACKUP przed migracją!

BEGIN;

-- 0. Usuń poprzednią wersję tabeli (jeśli istnieje z błędną strukturą)
DROP TABLE IF EXISTS customers CASCADE;
DROP VIEW IF EXISTS customers_active CASCADE;
DROP VIEW IF EXISTS customers_full CASCADE;
DROP FUNCTION IF EXISTS search_customers(TEXT, INTEGER);
DROP FUNCTION IF EXISTS update_customers_timestamp();
DROP FUNCTION IF EXISTS generate_customer_code(TEXT);

-- 1. Rozszerzenie do wyszukiwania pełnotekstowego (jeśli nie istnieje)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. Typ klienta (enum)
DO $$ BEGIN
    CREATE TYPE customer_type AS ENUM ('company', 'individual');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 3. Tabela customers
CREATE TABLE IF NOT EXISTS customers (
    -- Identyfikacja
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT UNIQUE NOT NULL,              -- Kod klienta np. "ABC001", "KL-0001"
    
    -- Podstawowe dane
    name TEXT NOT NULL,                     -- Pełna nazwa firmy / imię i nazwisko
    short_name TEXT,                        -- Skrót nazwy (do list, wyszukiwania)
    
    -- Typ klienta
    type customer_type DEFAULT 'company',
    
    -- Dane firmowe (dla firm)
    nip TEXT,                               -- NIP (może być NULL dla osób fizycznych)
    regon TEXT,                             -- REGON
    krs TEXT,                               -- KRS (dla spółek)
    
    -- Adres główny (siedziby)
    address_street TEXT,
    address_building TEXT,                  -- Numer budynku
    address_apartment TEXT,                 -- Numer lokalu
    address_postal_code TEXT,
    address_city TEXT,
    address_country TEXT DEFAULT 'Polska',
    
    -- Adres dostawy (jeśli inny niż siedziby)
    shipping_address JSONB,                 -- {street, building, postal_code, city, country}
    
    -- Kontakt główny
    email TEXT,
    phone TEXT,
    phone_mobile TEXT,
    fax TEXT,
    website TEXT,
    
    -- Osoby kontaktowe (array)
    contacts JSONB DEFAULT '[]'::jsonb,     -- [{name, role, email, phone, is_primary}]
    
    -- Warunki handlowe
    payment_days INTEGER DEFAULT 14,        -- Termin płatności (dni)
    credit_limit NUMERIC(12,2),             -- Limit kredytowy (PLN)
    discount_percent NUMERIC(5,2) DEFAULT 0, -- Rabat stały (%)
    price_list TEXT DEFAULT 'standard',     -- Cennik: 'standard', 'vip', 'wholesale'
    currency TEXT DEFAULT 'PLN',            -- Waluta
    
    -- Konto bankowe klienta (dla zwrotów)
    bank_name TEXT,
    bank_account TEXT,                      -- IBAN
    
    -- Notatki i kategoryzacja
    notes TEXT,                             -- Notatki wewnętrzne
    tags TEXT[],                            -- Tagi do kategoryzacji
    category TEXT,                          -- Kategoria klienta
    
    -- Dane sprzedażowe
    sales_rep_id UUID,                      -- Przypisany handlowiec
    acquisition_source TEXT,                -- Źródło pozyskania
    first_order_date DATE,                  -- Data pierwszego zamówienia
    last_order_date DATE,                   -- Data ostatniego zamówienia
    total_orders INTEGER DEFAULT 0,         -- Liczba zamówień
    total_revenue NUMERIC(14,2) DEFAULT 0,  -- Suma obrotów
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,      -- Czy dane zweryfikowane
    is_blocked BOOLEAN DEFAULT FALSE,       -- Czy zablokowany (np. za nieopłacone faktury)
    blocked_reason TEXT,
    
    -- Metadane
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    updated_by UUID,
    version INTEGER DEFAULT 1,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID,
    
    -- Constraints
    CONSTRAINT valid_nip CHECK (
        nip IS NULL OR 
        (LENGTH(REPLACE(nip, '-', '')) = 10 AND nip ~ '^[0-9\-]+$')
    ),
    CONSTRAINT valid_payment_days CHECK (payment_days >= 0 AND payment_days <= 365),
    CONSTRAINT valid_discount CHECK (discount_percent >= 0 AND discount_percent <= 100)
);

-- 4. Indeksy
-- Podstawowe wyszukiwanie
CREATE INDEX IF NOT EXISTS idx_customers_code ON customers(code);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_customers_short_name ON customers USING gin(short_name gin_trgm_ops);

-- Wyszukiwanie po NIP
CREATE INDEX IF NOT EXISTS idx_customers_nip ON customers(nip) WHERE nip IS NOT NULL;

-- Wyszukiwanie po mieście
CREATE INDEX IF NOT EXISTS idx_customers_city ON customers(address_city);

-- Filtrowanie aktywnych
CREATE INDEX IF NOT EXISTS idx_customers_active ON customers(is_active) WHERE is_active = TRUE;

-- Sortowanie po dacie
CREATE INDEX IF NOT EXISTS idx_customers_created ON customers(created_at DESC);

-- Wyszukiwanie po tagach
CREATE INDEX IF NOT EXISTS idx_customers_tags ON customers USING gin(tags);

-- 5. Trigger do aktualizacji updated_at
CREATE OR REPLACE FUNCTION update_customers_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS customers_update_timestamp ON customers;
CREATE TRIGGER customers_update_timestamp
    BEFORE UPDATE ON customers
    FOR EACH ROW
    EXECUTE FUNCTION update_customers_timestamp();

-- 6. Widok dla aktywnych klientów
CREATE OR REPLACE VIEW customers_active AS
SELECT 
    id,
    code,
    name,
    short_name,
    type,
    nip,
    address_city,
    email,
    phone,
    payment_days,
    discount_percent,
    category,
    tags,
    total_orders,
    total_revenue,
    last_order_date,
    created_at
FROM customers
WHERE is_active = TRUE 
  AND deleted_at IS NULL
  AND is_blocked = FALSE;

-- 7. Widok dla pełnych danych (z obliczeniami)
CREATE OR REPLACE VIEW customers_full AS
SELECT 
    c.*,
    -- Pełny adres jako tekst
    CONCAT_WS(', ',
        NULLIF(CONCAT_WS(' ', c.address_street, c.address_building, 
               CASE WHEN c.address_apartment IS NOT NULL 
                    THEN '/' || c.address_apartment END), ''),
        c.address_postal_code || ' ' || c.address_city,
        CASE WHEN c.address_country != 'Polska' THEN c.address_country END
    ) AS full_address,
    
    -- Średnia wartość zamówienia
    CASE WHEN c.total_orders > 0 
         THEN ROUND(c.total_revenue / c.total_orders, 2) 
         ELSE 0 END AS avg_order_value,
    
    -- Dni od ostatniego zamówienia
    CASE WHEN c.last_order_date IS NOT NULL 
         THEN CURRENT_DATE - c.last_order_date 
         ELSE NULL END AS days_since_last_order
FROM customers c;

-- 8. Funkcja generowania kodu klienta
CREATE OR REPLACE FUNCTION generate_customer_code(prefix TEXT DEFAULT 'KL')
RETURNS TEXT AS $$
DECLARE
    next_num INTEGER;
    new_code TEXT;
BEGIN
    -- Znajdź najwyższy numer dla danego prefixu
    SELECT COALESCE(MAX(
        CAST(SUBSTRING(code FROM LENGTH(prefix) + 2) AS INTEGER)
    ), 0) + 1
    INTO next_num
    FROM customers
    WHERE code LIKE prefix || '-%';
    
    -- Generuj kod
    new_code := prefix || '-' || LPAD(next_num::TEXT, 5, '0');
    
    RETURN new_code;
END;
$$ LANGUAGE plpgsql;

-- 10. Funkcja do wyszukiwania klientów
CREATE OR REPLACE FUNCTION search_customers(
    search_query TEXT,
    limit_count INTEGER DEFAULT 20
)
RETURNS TABLE (
    id UUID,
    code TEXT,
    name TEXT,
    nip TEXT,
    city TEXT,
    relevance REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.code,
        c.name,
        c.nip,
        c.address_city,
        GREATEST(
            similarity(c.name, search_query),
            similarity(COALESCE(c.short_name, ''), search_query),
            similarity(COALESCE(c.code, ''), search_query),
            similarity(COALESCE(c.nip, ''), search_query)
        ) AS relevance
    FROM customers c
    WHERE c.is_active = TRUE
      AND c.deleted_at IS NULL
      AND (
          c.name ILIKE '%' || search_query || '%'
          OR c.short_name ILIKE '%' || search_query || '%'
          OR c.code ILIKE '%' || search_query || '%'
          OR c.nip ILIKE '%' || search_query || '%'
          OR c.email ILIKE '%' || search_query || '%'
      )
    ORDER BY relevance DESC, c.name
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- 11. Komentarze
COMMENT ON TABLE customers IS 'Kartoteka klientów (kontrahentów)';
COMMENT ON COLUMN customers.code IS 'Unikalny kod klienta (np. KL-00001)';
COMMENT ON COLUMN customers.type IS 'Typ: company (firma) lub individual (osoba fizyczna)';
COMMENT ON COLUMN customers.contacts IS 'Lista osób kontaktowych jako JSON array';
COMMENT ON COLUMN customers.shipping_address IS 'Adres dostawy (jeśli inny niż siedziby)';
COMMENT ON COLUMN customers.payment_days IS 'Termin płatności w dniach';
COMMENT ON COLUMN customers.credit_limit IS 'Limit kredytowy w PLN';
COMMENT ON COLUMN customers.price_list IS 'Przypisany cennik: standard, vip, wholesale';
COMMENT ON COLUMN customers.tags IS 'Tagi do kategoryzacji (array)';
COMMENT ON COLUMN customers.is_blocked IS 'Czy klient zablokowany (np. za zaległości)';

-- 12. Przykładowe dane testowe (opcjonalnie - do usunięcia w produkcji)
-- INSERT INTO customers (code, name, short_name, type, nip, address_city, email, phone)
-- VALUES 
--     ('KL-00001', 'Przykładowa Firma Sp. z o.o.', 'Przykładowa', 'company', '1234567890', 'Warszawa', 'kontakt@przykladowa.pl', '+48 22 123 45 67'),
--     ('KL-00002', 'Test Manufacturing S.A.', 'TestMfg', 'company', '9876543210', 'Kraków', 'info@testmfg.pl', '+48 12 987 65 43');

COMMIT;

-- ============================================================
-- Przykłady użycia:
-- ============================================================
-- 
-- -- Wygeneruj nowy kod klienta
-- SELECT generate_customer_code('KL');  -- Zwróci np. 'KL-00001'
-- 
-- -- Wyszukaj klientów
-- SELECT * FROM search_customers('przykład');
-- 
-- -- Pobierz aktywnych klientów z miasta
-- SELECT * FROM customers_active WHERE address_city = 'Warszawa';
-- 
-- -- Pobierz pełne dane z obliczeniami
-- SELECT * FROM customers_full WHERE id = 'uuid-here';
