-- ============================================================
-- NewERP - Tabele cenników materiałów i cięcia
-- Migracja: 004_pricing_tables.sql
-- Data: 2025-12-02
-- ============================================================

-- ============================================================
-- 1. Tabela cen materiałów (material_prices)
-- ============================================================
-- Przechowuje ceny materiałów per format/materiał/grubość

CREATE TABLE IF NOT EXISTS material_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identyfikacja materiału
    format VARCHAR(50) NOT NULL DEFAULT '1500x3000',  -- np. '1500x3000', '2000x1000'
    material VARCHAR(50) NOT NULL,                     -- np. 'DC01', 'INOX', '1.4301'
    thickness DECIMAL(6,2) NOT NULL,                   -- grubość [mm]
    
    -- Cena
    price_per_kg DECIMAL(10,2) NOT NULL,              -- cena [PLN/kg]
    
    -- Metadane
    source VARCHAR(100),                               -- źródło ceny (dostawca)
    note TEXT,                                         -- uwagi
    valid_from DATE DEFAULT CURRENT_DATE,              -- od kiedy obowiązuje
    valid_to DATE,                                     -- do kiedy (NULL = bezterminowo)
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES auth.users(id),
    
    -- Constraint: unikalna kombinacja
    CONSTRAINT uq_material_price UNIQUE (format, material, thickness, valid_from)
);

-- Indeksy dla szybkiego wyszukiwania
CREATE INDEX IF NOT EXISTS idx_material_prices_material ON material_prices(material);
CREATE INDEX IF NOT EXISTS idx_material_prices_thickness ON material_prices(thickness);
CREATE INDEX IF NOT EXISTS idx_material_prices_lookup ON material_prices(material, thickness, valid_from);

-- RLS (Row Level Security)
ALTER TABLE material_prices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow read for authenticated" ON material_prices
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow insert for authenticated" ON material_prices
    FOR INSERT TO authenticated WITH CHECK (true);

CREATE POLICY "Allow update for authenticated" ON material_prices
    FOR UPDATE TO authenticated USING (true);

CREATE POLICY "Allow delete for authenticated" ON material_prices
    FOR DELETE TO authenticated USING (true);

-- Trigger do aktualizacji updated_at
CREATE OR REPLACE FUNCTION update_material_prices_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_material_prices_updated
    BEFORE UPDATE ON material_prices
    FOR EACH ROW
    EXECUTE FUNCTION update_material_prices_timestamp();


-- ============================================================
-- 2. Tabela cen cięcia (cutting_prices)
-- ============================================================
-- Przechowuje parametry i ceny cięcia laserowego

CREATE TABLE IF NOT EXISTS cutting_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identyfikacja
    material VARCHAR(50) NOT NULL,                     -- materiał
    thickness DECIMAL(6,2) NOT NULL,                   -- grubość [mm]
    gas VARCHAR(10) NOT NULL DEFAULT 'N',              -- gaz: N (azot), O (tlen), A (mieszanka)
    
    -- Parametry cięcia
    cutting_speed DECIMAL(8,2),                        -- prędkość cięcia [m/min]
    hour_price DECIMAL(10,2) NOT NULL DEFAULT 750,     -- cena godziny maszyny [PLN/h]
    utilization DECIMAL(4,2) DEFAULT 0.65,             -- współczynnik wykorzystania (0-1)
    
    -- Cena obliczona
    price_per_meter DECIMAL(10,4),                     -- cena za metr [PLN/m] (obliczona lub ręczna)
    price_manual BOOLEAN DEFAULT FALSE,                -- czy cena ręczna (nie z formuły)
    
    -- Metadane
    note TEXT,
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_to DATE,
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES auth.users(id),
    
    -- Constraint: unikalna kombinacja
    CONSTRAINT uq_cutting_price UNIQUE (material, thickness, gas, valid_from)
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_cutting_prices_material ON cutting_prices(material);
CREATE INDEX IF NOT EXISTS idx_cutting_prices_thickness ON cutting_prices(thickness);
CREATE INDEX IF NOT EXISTS idx_cutting_prices_lookup ON cutting_prices(material, thickness, gas, valid_from);

-- RLS
ALTER TABLE cutting_prices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow read for authenticated" ON cutting_prices
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow insert for authenticated" ON cutting_prices
    FOR INSERT TO authenticated WITH CHECK (true);

CREATE POLICY "Allow update for authenticated" ON cutting_prices
    FOR UPDATE TO authenticated USING (true);

CREATE POLICY "Allow delete for authenticated" ON cutting_prices
    FOR DELETE TO authenticated USING (true);

-- Trigger do aktualizacji updated_at
CREATE OR REPLACE FUNCTION update_cutting_prices_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_cutting_prices_updated
    BEFORE UPDATE ON cutting_prices
    FOR EACH ROW
    EXECUTE FUNCTION update_cutting_prices_timestamp();

-- Trigger do obliczania ceny za metr
CREATE OR REPLACE FUNCTION calculate_cutting_price()
RETURNS TRIGGER AS $$
BEGIN
    -- Oblicz cenę za metr jeśli nie jest ręczna
    IF NOT NEW.price_manual AND NEW.cutting_speed > 0 AND NEW.utilization > 0 THEN
        -- Formuła: price = hour_price / (speed * 60 * utilization)
        NEW.price_per_meter = NEW.hour_price / (NEW.cutting_speed * 60 * NEW.utilization);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_calculate_cutting_price
    BEFORE INSERT OR UPDATE ON cutting_prices
    FOR EACH ROW
    EXECUTE FUNCTION calculate_cutting_price();


-- ============================================================
-- 3. Tabela historii importów (pricing_imports)
-- ============================================================
-- Log importów z plików Excel

CREATE TABLE IF NOT EXISTS pricing_imports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    import_type VARCHAR(20) NOT NULL,                  -- 'materials' lub 'cutting'
    filename VARCHAR(255),
    records_imported INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending',              -- pending, success, partial, failed
    error_message TEXT,
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES auth.users(id)
);

-- RLS
ALTER TABLE pricing_imports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON pricing_imports
    FOR ALL TO authenticated USING (true) WITH CHECK (true);


-- ============================================================
-- 4. Widoki pomocnicze
-- ============================================================

-- Aktualnie obowiązujące ceny materiałów
CREATE OR REPLACE VIEW current_material_prices AS
SELECT DISTINCT ON (material, thickness, format)
    id,
    format,
    material,
    thickness,
    price_per_kg,
    source,
    note,
    valid_from,
    created_at,
    updated_at
FROM material_prices
WHERE (valid_to IS NULL OR valid_to >= CURRENT_DATE)
  AND valid_from <= CURRENT_DATE
ORDER BY material, thickness, format, valid_from DESC;

-- Aktualnie obowiązujące ceny cięcia
CREATE OR REPLACE VIEW current_cutting_prices AS
SELECT DISTINCT ON (material, thickness, gas)
    id,
    material,
    thickness,
    gas,
    cutting_speed,
    hour_price,
    utilization,
    price_per_meter,
    price_manual,
    note,
    valid_from,
    created_at,
    updated_at
FROM cutting_prices
WHERE (valid_to IS NULL OR valid_to >= CURRENT_DATE)
  AND valid_from <= CURRENT_DATE
ORDER BY material, thickness, gas, valid_from DESC;


-- ============================================================
-- 5. Funkcje pomocnicze
-- ============================================================

-- Pobierz cenę materiału
CREATE OR REPLACE FUNCTION get_material_price(
    p_material VARCHAR,
    p_thickness DECIMAL,
    p_format VARCHAR DEFAULT '1500x3000'
)
RETURNS DECIMAL AS $$
DECLARE
    v_price DECIMAL;
BEGIN
    SELECT price_per_kg INTO v_price
    FROM current_material_prices
    WHERE material = p_material
      AND thickness = p_thickness
      AND format = p_format
    LIMIT 1;
    
    RETURN COALESCE(v_price, 0);
END;
$$ LANGUAGE plpgsql;

-- Pobierz cenę cięcia
CREATE OR REPLACE FUNCTION get_cutting_price(
    p_material VARCHAR,
    p_thickness DECIMAL,
    p_gas VARCHAR DEFAULT 'N'
)
RETURNS DECIMAL AS $$
DECLARE
    v_price DECIMAL;
BEGIN
    SELECT price_per_meter INTO v_price
    FROM current_cutting_prices
    WHERE material = p_material
      AND thickness = p_thickness
      AND gas = p_gas
    LIMIT 1;
    
    RETURN COALESCE(v_price, 0);
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 6. Komentarze
-- ============================================================

COMMENT ON TABLE material_prices IS 'Cennik materiałów (blachy) - ceny za kg';
COMMENT ON TABLE cutting_prices IS 'Cennik cięcia laserowego - ceny za metr';
COMMENT ON TABLE pricing_imports IS 'Historia importów cenników z Excel';

COMMENT ON COLUMN material_prices.format IS 'Format arkusza, np. 1500x3000';
COMMENT ON COLUMN material_prices.material IS 'Symbol materiału, np. DC01, INOX, 1.4301';
COMMENT ON COLUMN material_prices.thickness IS 'Grubość blachy w mm';
COMMENT ON COLUMN material_prices.price_per_kg IS 'Cena za kilogram w PLN';

COMMENT ON COLUMN cutting_prices.gas IS 'Gaz cięcia: N=azot, O=tlen, A=mieszanka';
COMMENT ON COLUMN cutting_prices.cutting_speed IS 'Prędkość cięcia w m/min';
COMMENT ON COLUMN cutting_prices.hour_price IS 'Cena godziny maszyny w PLN';
COMMENT ON COLUMN cutting_prices.utilization IS 'Współczynnik wykorzystania 0-1';
COMMENT ON COLUMN cutting_prices.price_per_meter IS 'Cena za metr cięcia w PLN';

-- ============================================================
-- Koniec migracji
-- ============================================================
