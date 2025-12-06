-- ============================================================
-- NewERP - Rozszerzone tabele kosztów
-- Migracja: 005_extended_cost_tables.sql
-- Data: 2025-12-03
--
-- Nowe tabele:
-- - foil_removal_rates: Koszty usuwania folii
-- - piercing_rates: Koszty przebicia (piercing)
-- - operational_costs: Koszty operacyjne
-- - cost_config: Konfiguracja globalna kosztów
-- - nesting_results: Wyniki nestingu
-- - order_costs: Koszty per zamówienie
-- ============================================================

-- ============================================================
-- 1. Tabela kosztów usuwania folii (foil_removal_rates)
-- ============================================================

CREATE TABLE IF NOT EXISTS foil_removal_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identyfikacja materiału
    material_type VARCHAR(50) NOT NULL,              -- np. 'stainless', 'aluminum', 'all'
    max_thickness DECIMAL(6,2) NOT NULL DEFAULT 5.0, -- max grubość dla auto-włączenia [mm]

    -- Parametry
    removal_speed_m_min DECIMAL(8,2) NOT NULL DEFAULT 15.0,  -- prędkość zdejmowania [m/min]
    hourly_rate DECIMAL(10,2) NOT NULL DEFAULT 120.0,        -- stawka godzinowa [PLN/h]

    -- Auto-włączenie
    auto_enable BOOLEAN DEFAULT TRUE,                -- czy włączać automatycznie

    -- Metadane
    note TEXT,
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_to DATE,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_foil_rate UNIQUE (material_type, max_thickness, valid_from)
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_foil_rates_material ON foil_removal_rates(material_type);

-- RLS
ALTER TABLE foil_removal_rates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON foil_removal_rates
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- Trigger updated_at
CREATE OR REPLACE FUNCTION update_foil_rates_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_foil_rates_updated
    BEFORE UPDATE ON foil_removal_rates
    FOR EACH ROW
    EXECUTE FUNCTION update_foil_rates_timestamp();

-- Domyślne dane
INSERT INTO foil_removal_rates (material_type, max_thickness, removal_speed_m_min, hourly_rate, auto_enable, note)
VALUES
    ('stainless', 5.0, 15.0, 120.0, TRUE, 'Stal nierdzewna do 5mm - automatycznie'),
    ('1.4301', 5.0, 15.0, 120.0, TRUE, 'INOX 304 do 5mm'),
    ('1.4404', 5.0, 15.0, 120.0, TRUE, 'INOX 316L do 5mm'),
    ('aluminum', 3.0, 20.0, 100.0, FALSE, 'Aluminium - opcjonalnie')
ON CONFLICT DO NOTHING;


-- ============================================================
-- 2. Tabela kosztów przebicia (piercing_rates)
-- ============================================================

CREATE TABLE IF NOT EXISTS piercing_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identyfikacja
    material_type VARCHAR(50) NOT NULL,              -- typ materiału
    thickness DECIMAL(6,2) NOT NULL,                 -- grubość [mm]

    -- Parametry
    pierce_time_s DECIMAL(6,2) NOT NULL,             -- czas przebicia [s]
    cost_per_pierce DECIMAL(10,4) NOT NULL,          -- koszt za przebicie [PLN]

    -- Metadane
    note TEXT,
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_to DATE,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_piercing_rate UNIQUE (material_type, thickness, valid_from)
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_piercing_rates_lookup ON piercing_rates(material_type, thickness);

-- RLS
ALTER TABLE piercing_rates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON piercing_rates
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- Trigger updated_at
CREATE OR REPLACE FUNCTION update_piercing_rates_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_piercing_rates_updated
    BEFORE UPDATE ON piercing_rates
    FOR EACH ROW
    EXECUTE FUNCTION update_piercing_rates_timestamp();

-- Domyślne dane - INOX (0.5-1.0s, rośnie z grubością)
INSERT INTO piercing_rates (material_type, thickness, pierce_time_s, cost_per_pierce)
VALUES
    ('stainless', 1.0, 0.5, 0.10),
    ('stainless', 2.0, 0.6, 0.12),
    ('stainless', 3.0, 0.7, 0.15),
    ('stainless', 4.0, 0.8, 0.18),
    ('stainless', 5.0, 0.9, 0.22),
    ('stainless', 6.0, 1.0, 0.28),
    ('stainless', 8.0, 1.2, 0.35),
    ('stainless', 10.0, 1.4, 0.45),
    -- Stal czarna (0.5-2.0s)
    ('steel', 1.0, 0.5, 0.08),
    ('steel', 2.0, 0.6, 0.10),
    ('steel', 3.0, 0.8, 0.12),
    ('steel', 4.0, 1.0, 0.15),
    ('steel', 5.0, 1.2, 0.18),
    ('steel', 6.0, 1.4, 0.22),
    ('steel', 8.0, 1.6, 0.30),
    ('steel', 10.0, 1.8, 0.40),
    ('steel', 12.0, 2.0, 0.55),
    ('steel', 15.0, 2.5, 0.75),
    ('steel', 20.0, 3.0, 1.00)
ON CONFLICT DO NOTHING;


-- ============================================================
-- 3. Tabela kosztów operacyjnych (operational_costs)
-- ============================================================

CREATE TABLE IF NOT EXISTS operational_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Typ kosztu
    cost_type VARCHAR(50) NOT NULL,                  -- 'sheet_handling', 'setup', 'programming'

    -- Wartość
    cost_value DECIMAL(10,2) NOT NULL,               -- wartość [PLN]
    cost_unit VARCHAR(20) NOT NULL DEFAULT 'per_item', -- 'per_item', 'per_hour', 'per_order'

    -- Opis
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Czy aktywny
    is_active BOOLEAN DEFAULT TRUE,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_operational_cost UNIQUE (cost_type)
);

-- RLS
ALTER TABLE operational_costs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON operational_costs
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- Domyślne dane
INSERT INTO operational_costs (cost_type, cost_value, cost_unit, name, description)
VALUES
    ('sheet_handling', 40.00, 'per_item', 'Obsługa arkusza', 'Koszt załadunku i rozładunku arkusza'),
    ('setup', 50.00, 'per_order', 'Przygotowanie', 'Koszt przygotowania zlecenia'),
    ('programming', 5.00, 'per_item', 'Programowanie', 'Koszt programowania per detal'),
    ('min_order', 100.00, 'per_order', 'Minimalne zlecenie', 'Minimalny koszt zlecenia')
ON CONFLICT DO NOTHING;


-- ============================================================
-- 4. Tabela konfiguracji kosztów (cost_config)
-- ============================================================

CREATE TABLE IF NOT EXISTS cost_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Klucz konfiguracji
    config_key VARCHAR(100) NOT NULL UNIQUE,

    -- Wartość (JSON dla elastyczności)
    config_value JSONB NOT NULL,

    -- Opis
    description TEXT,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE cost_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON cost_config
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- Domyślna konfiguracja
INSERT INTO cost_config (config_key, config_value, description)
VALUES
    ('time_buffer_percent', '25', 'Bufor czasowy dla wariantu B [%]'),
    ('default_allocation_model', '"bounding_box"', 'Domyślny model alokacji kosztu materiału'),
    ('laser_hourly_rate', '350', 'Domyślna stawka godzinowa lasera [PLN/h]'),
    ('bending_hourly_rate', '200', 'Domyślna stawka godzinowa gięcia [PLN/h]'),
    ('default_sheet_formats', '[[3000, 1500], [2500, 1250], [2000, 1000], [1500, 750]]', 'Dostępne formaty arkuszy [mm]'),
    ('material_densities', '{"S235": 7850, "S355": 7850, "DC01": 7850, "1.4301": 7900, "1.4404": 7950, "ALU": 2700}', 'Gęstości materiałów [kg/m³]'),
    ('foil_auto_materials', '["1.4301", "1.4404", "1.4571", "INOX"]', 'Materiały z auto-włączeniem folii')
ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value;


-- ============================================================
-- 5. Tabela wyników nestingu (nesting_results)
-- ============================================================

CREATE TABLE IF NOT EXISTS nesting_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Powiązanie z zamówieniem/ofertą
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    quotation_id UUID,  -- Będzie FK gdy tabela quotations będzie gotowa

    -- Parametry nestingu
    material VARCHAR(50) NOT NULL,
    thickness DECIMAL(6,2) NOT NULL,
    sheet_width DECIMAL(10,2) NOT NULL,
    sheet_height DECIMAL(10,2) NOT NULL,
    spacing DECIMAL(6,2) DEFAULT 5.0,

    -- Wyniki
    sheets_used INTEGER NOT NULL DEFAULT 0,
    total_parts INTEGER NOT NULL DEFAULT 0,
    total_efficiency DECIMAL(5,4) DEFAULT 0,         -- 0-1
    unplaced_count INTEGER DEFAULT 0,

    -- Koszty
    material_cost DECIMAL(12,2) DEFAULT 0,
    cutting_cost DECIMAL(12,2) DEFAULT 0,
    foil_cost DECIMAL(12,2) DEFAULT 0,
    piercing_cost DECIMAL(12,2) DEFAULT 0,
    operational_cost DECIMAL(12,2) DEFAULT 0,
    total_cost DECIMAL(12,2) DEFAULT 0,

    -- Parametry kalkulacji
    cost_variant VARCHAR(1) DEFAULT 'A',             -- 'A' lub 'B'
    allocation_model VARCHAR(50) DEFAULT 'bounding_box',

    -- Dane szczegółowe (JSON)
    sheets_data JSONB,                               -- Lista arkuszy z detalami
    parts_data JSONB,                                -- Lista detali z kosztami

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_nesting_results_order ON nesting_results(order_id);
CREATE INDEX IF NOT EXISTS idx_nesting_results_quotation ON nesting_results(quotation_id);
CREATE INDEX IF NOT EXISTS idx_nesting_results_material ON nesting_results(material, thickness);

-- RLS
ALTER TABLE nesting_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON nesting_results
    FOR ALL TO authenticated USING (true) WITH CHECK (true);


-- ============================================================
-- 6. Tabela kosztów per zamówienie (order_costs)
-- ============================================================

CREATE TABLE IF NOT EXISTS order_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Powiązanie
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    quotation_id UUID,

    -- Koszty produkcyjne
    material_cost DECIMAL(12,2) DEFAULT 0,
    cutting_cost DECIMAL(12,2) DEFAULT 0,
    foil_cost DECIMAL(12,2) DEFAULT 0,
    piercing_cost DECIMAL(12,2) DEFAULT 0,
    operational_cost DECIMAL(12,2) DEFAULT 0,
    setup_cost DECIMAL(12,2) DEFAULT 0,

    -- Koszty per zlecenie
    technology_cost DECIMAL(12,2) DEFAULT 0,
    packaging_cost DECIMAL(12,2) DEFAULT 0,
    transport_cost DECIMAL(12,2) DEFAULT 0,

    -- Sumy
    production_subtotal DECIMAL(12,2) DEFAULT 0,
    order_subtotal DECIMAL(12,2) DEFAULT 0,
    total_cost DECIMAL(12,2) DEFAULT 0,

    -- Parametry
    cost_variant VARCHAR(1) DEFAULT 'A',
    allocation_model VARCHAR(50) DEFAULT 'bounding_box',
    time_buffer_applied BOOLEAN DEFAULT FALSE,

    -- Statystyki
    total_sheets INTEGER DEFAULT 0,
    total_parts INTEGER DEFAULT 0,
    total_weight_kg DECIMAL(10,2) DEFAULT 0,
    total_cutting_length_m DECIMAL(10,2) DEFAULT 0,
    total_cutting_time_min DECIMAL(10,2) DEFAULT 0,
    average_efficiency DECIMAL(5,4) DEFAULT 0,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_order_cost UNIQUE (order_id)
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_order_costs_order ON order_costs(order_id);
CREATE INDEX IF NOT EXISTS idx_order_costs_quotation ON order_costs(quotation_id);

-- RLS
ALTER TABLE order_costs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON order_costs
    FOR ALL TO authenticated USING (true) WITH CHECK (true);


-- ============================================================
-- 7. Widoki pomocnicze
-- ============================================================

-- Aktualne stawki folii
CREATE OR REPLACE VIEW current_foil_rates AS
SELECT DISTINCT ON (material_type, max_thickness)
    id,
    material_type,
    max_thickness,
    removal_speed_m_min,
    hourly_rate,
    auto_enable,
    note,
    valid_from
FROM foil_removal_rates
WHERE (valid_to IS NULL OR valid_to >= CURRENT_DATE)
  AND valid_from <= CURRENT_DATE
ORDER BY material_type, max_thickness, valid_from DESC;

-- Aktualne stawki piercing
CREATE OR REPLACE VIEW current_piercing_rates AS
SELECT DISTINCT ON (material_type, thickness)
    id,
    material_type,
    thickness,
    pierce_time_s,
    cost_per_pierce,
    note,
    valid_from
FROM piercing_rates
WHERE (valid_to IS NULL OR valid_to >= CURRENT_DATE)
  AND valid_from <= CURRENT_DATE
ORDER BY material_type, thickness, valid_from DESC;


-- ============================================================
-- 8. Funkcje pomocnicze
-- ============================================================

-- Pobierz stawkę folii
CREATE OR REPLACE FUNCTION get_foil_rate(
    p_material_type VARCHAR,
    p_thickness DECIMAL
)
RETURNS TABLE (
    removal_speed_m_min DECIMAL,
    hourly_rate DECIMAL,
    auto_enable BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        f.removal_speed_m_min,
        f.hourly_rate,
        f.auto_enable
    FROM current_foil_rates f
    WHERE f.material_type = p_material_type
      AND f.max_thickness >= p_thickness
    ORDER BY f.max_thickness ASC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Pobierz stawkę piercing
CREATE OR REPLACE FUNCTION get_piercing_rate(
    p_material_type VARCHAR,
    p_thickness DECIMAL
)
RETURNS TABLE (
    pierce_time_s DECIMAL,
    cost_per_pierce DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.pierce_time_s,
        p.cost_per_pierce
    FROM current_piercing_rates p
    WHERE p.material_type = p_material_type
      AND p.thickness = p_thickness
    LIMIT 1;

    -- Jeśli brak dokładnego dopasowania, znajdź najbliższe
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            p.pierce_time_s,
            p.cost_per_pierce
        FROM current_piercing_rates p
        WHERE p.material_type = p_material_type
        ORDER BY ABS(p.thickness - p_thickness)
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Pobierz konfigurację
CREATE OR REPLACE FUNCTION get_cost_config(p_key VARCHAR)
RETURNS JSONB AS $$
DECLARE
    v_value JSONB;
BEGIN
    SELECT config_value INTO v_value
    FROM cost_config
    WHERE config_key = p_key;

    RETURN v_value;
END;
$$ LANGUAGE plpgsql;

-- Pobierz koszt operacyjny
CREATE OR REPLACE FUNCTION get_operational_cost(p_type VARCHAR)
RETURNS DECIMAL AS $$
DECLARE
    v_cost DECIMAL;
BEGIN
    SELECT cost_value INTO v_cost
    FROM operational_costs
    WHERE cost_type = p_type
      AND is_active = TRUE;

    RETURN COALESCE(v_cost, 0);
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 9. Komentarze
-- ============================================================

COMMENT ON TABLE foil_removal_rates IS 'Stawki za usuwanie folii ochronnej';
COMMENT ON TABLE piercing_rates IS 'Stawki za przebicia (piercing) przy cięciu laserowym';
COMMENT ON TABLE operational_costs IS 'Koszty operacyjne (obsługa, setup, programowanie)';
COMMENT ON TABLE cost_config IS 'Konfiguracja globalna kalkulacji kosztów';
COMMENT ON TABLE nesting_results IS 'Wyniki nestingu powiązane z zamówieniami/ofertami';
COMMENT ON TABLE order_costs IS 'Podsumowanie kosztów per zamówienie';

COMMENT ON COLUMN foil_removal_rates.material_type IS 'Typ materiału: stainless, aluminum, all';
COMMENT ON COLUMN foil_removal_rates.max_thickness IS 'Maksymalna grubość dla auto-włączenia [mm]';
COMMENT ON COLUMN foil_removal_rates.removal_speed_m_min IS 'Prędkość zdejmowania folii [m/min]';

COMMENT ON COLUMN piercing_rates.pierce_time_s IS 'Czas przebicia [sekundy]';
COMMENT ON COLUMN piercing_rates.cost_per_pierce IS 'Koszt za jedno przebicie [PLN]';

COMMENT ON COLUMN nesting_results.cost_variant IS 'Wariant kalkulacji: A=cennikowy, B=czasowy';
COMMENT ON COLUMN nesting_results.allocation_model IS 'Model alokacji: bounding_box, actual_area, full_sheet, legacy';


-- ============================================================
-- Koniec migracji
-- ============================================================
