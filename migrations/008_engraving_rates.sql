-- ============================================================
-- NewERP - Tabela kosztów grawerowania (engraving_rates)
-- Migracja: 008_engraving_rates.sql
-- Data: 2025-12-12
--
-- Tabela przechowuje stawki za grawerowanie laserowe.
-- Cena za metr obliczana automatycznie z: hour_price / (speed * 60)
-- ============================================================

-- Tabela stawek grawerowania
CREATE TABLE IF NOT EXISTS engraving_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identyfikacja
    name VARCHAR(100) NOT NULL,                         -- nazwa profilu (np. "Standard", "Szybkie", "Głębokie")
    gas VARCHAR(10) NOT NULL DEFAULT 'N',               -- gaz: N (azot), O (tlen), A (mieszanka/powietrze)
    power_percent DECIMAL(5,2) DEFAULT 30.0,            -- moc lasera [%] (typowo 20-50% dla grawerowania)

    -- Parametry grawerowania
    engraving_speed DECIMAL(8,2) NOT NULL,              -- prędkość grawerowania [m/min]
    hour_price DECIMAL(10,2) NOT NULL DEFAULT 200,      -- cena godziny maszyny [PLN/h]

    -- Cena obliczona
    price_per_meter DECIMAL(10,4),                      -- cena za metr [PLN/m] (obliczona automatycznie)

    -- Metadane
    description TEXT,                                    -- opis zastosowania
    is_default BOOLEAN DEFAULT FALSE,                   -- czy domyślny profil
    is_active BOOLEAN DEFAULT TRUE,                     -- czy aktywny
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_to DATE,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_engraving_rates_gas ON engraving_rates(gas);
CREATE INDEX IF NOT EXISTS idx_engraving_rates_active ON engraving_rates(is_active);
CREATE INDEX IF NOT EXISTS idx_engraving_rates_lookup ON engraving_rates(gas, is_active, valid_from);

-- RLS (Row Level Security)
ALTER TABLE engraving_rates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow read for authenticated" ON engraving_rates
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow insert for authenticated" ON engraving_rates
    FOR INSERT TO authenticated WITH CHECK (true);

CREATE POLICY "Allow update for authenticated" ON engraving_rates
    FOR UPDATE TO authenticated USING (true);

CREATE POLICY "Allow delete for authenticated" ON engraving_rates
    FOR DELETE TO authenticated USING (true);

-- Trigger do aktualizacji updated_at
CREATE OR REPLACE FUNCTION update_engraving_rates_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_engraving_rates_updated
    BEFORE UPDATE ON engraving_rates
    FOR EACH ROW
    EXECUTE FUNCTION update_engraving_rates_timestamp();

-- Trigger do obliczania ceny za metr
-- Formuła: price_per_meter = hour_price / (engraving_speed * 60)
CREATE OR REPLACE FUNCTION calculate_engraving_price()
RETURNS TRIGGER AS $$
BEGIN
    -- Oblicz cenę za metr: stawka_godzinowa / (prędkość_m_min * 60)
    IF NEW.engraving_speed > 0 THEN
        NEW.price_per_meter = NEW.hour_price / (NEW.engraving_speed * 60);
    ELSE
        NEW.price_per_meter = 0;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_calculate_engraving_price
    BEFORE INSERT OR UPDATE ON engraving_rates
    FOR EACH ROW
    EXECUTE FUNCTION calculate_engraving_price();

-- ============================================================
-- Widok aktualnych stawek grawerowania
-- ============================================================
CREATE OR REPLACE VIEW current_engraving_rates AS
SELECT DISTINCT ON (gas, power_percent)
    id,
    name,
    gas,
    power_percent,
    engraving_speed,
    hour_price,
    price_per_meter,
    description,
    is_default,
    valid_from
FROM engraving_rates
WHERE is_active = TRUE
  AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
  AND valid_from <= CURRENT_DATE
ORDER BY gas, power_percent, valid_from DESC;

-- Komentarze
COMMENT ON TABLE engraving_rates IS 'Cennik grawerowania laserowego - stawki za metr';
COMMENT ON COLUMN engraving_rates.name IS 'Nazwa profilu grawerowania';
COMMENT ON COLUMN engraving_rates.gas IS 'Gaz: N=azot, O=tlen, A=powietrze/mieszanka';
COMMENT ON COLUMN engraving_rates.power_percent IS 'Moc lasera w procentach (typowo 20-50%)';
COMMENT ON COLUMN engraving_rates.engraving_speed IS 'Prędkość grawerowania w m/min';
COMMENT ON COLUMN engraving_rates.hour_price IS 'Cena godziny maszyny w PLN';
COMMENT ON COLUMN engraving_rates.price_per_meter IS 'Cena za metr grawerowania w PLN (obliczona automatycznie)';

COMMENT ON VIEW current_engraving_rates IS 'Aktualne stawki grawerowania';

-- ============================================================
-- Dane początkowe - domyślne profile grawerowania
-- ============================================================
INSERT INTO engraving_rates (name, gas, power_percent, engraving_speed, hour_price, description, is_default) VALUES
    ('Standard', 'N', 30.0, 1.5, 200.00, 'Standardowe grawerowanie - dobry kompromis jakość/prędkość', TRUE),
    ('Szybkie', 'A', 25.0, 2.5, 180.00, 'Szybkie grawerowanie - cieńsze linie, niższa głębokość', FALSE),
    ('Głębokie', 'N', 50.0, 0.8, 250.00, 'Głębokie grawerowanie - wolniejsze, lepiej widoczne', FALSE),
    ('Precyzyjne', 'N', 20.0, 1.0, 220.00, 'Precyzyjne grawerowanie - cienkie detale, tekst', FALSE)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Koniec migracji
-- ============================================================
