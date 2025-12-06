-- ============================================================
-- MIGRACJA: audit_log - System logowania zmian
-- Autor: NewERP Team
-- Data: 2025-11-30
-- ============================================================

-- UWAGA: Wykonaj BACKUP przed migracją!

BEGIN;

-- 1. Tabela audit_log
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Co zostało zmienione
    entity_type TEXT NOT NULL,           -- 'product', 'order', 'customer', etc.
    entity_id TEXT NOT NULL,             -- UUID encji (TEXT dla elastyczności)
    action TEXT NOT NULL,                -- 'create', 'update', 'delete', 'restore', etc.
    
    -- Szczegóły zmian
    old_values JSONB,                    -- poprzedni stan (dla update/delete)
    new_values JSONB,                    -- nowy stan (dla create/update)
    changed_fields TEXT[],               -- lista zmienionych pól
    
    -- Kto i kiedy
    user_id UUID,                        -- ID użytkownika (może być NULL dla operacji systemowych)
    user_email TEXT,                     -- Email użytkownika (denormalizacja dla wygody)
    
    -- Dodatkowe info
    ip_address INET,                     -- IP użytkownika (opcjonalne)
    user_agent TEXT,                     -- User-Agent (opcjonalne)
    
    -- Powiązane operacje
    correlation_id UUID,                 -- do grupowania powiązanych zmian (np. transakcja)
    
    -- Dodatkowe metadane
    metadata JSONB,                      -- dowolne dodatkowe dane
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    
    -- Constraints
    CONSTRAINT valid_action CHECK (action IN (
        'create', 'update', 'delete', 'restore',
        'status_change', 'file_upload', 'file_delete',
        'login', 'logout', 'export', 'import'
    ))
);

-- 2. Indeksy dla szybkiego wyszukiwania
CREATE INDEX IF NOT EXISTS idx_audit_log_entity 
    ON audit_log(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_user 
    ON audit_log(user_id) 
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_audit_log_created 
    ON audit_log(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_correlation 
    ON audit_log(correlation_id) 
    WHERE correlation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_audit_log_action 
    ON audit_log(action);

-- 3. Indeks GIN dla wyszukiwania w JSONB
CREATE INDEX IF NOT EXISTS idx_audit_log_old_values 
    ON audit_log USING gin(old_values);

CREATE INDEX IF NOT EXISTS idx_audit_log_new_values 
    ON audit_log USING gin(new_values);

-- 4. Funkcja do automatycznego logowania zmian (opcjonalna)
-- Może być użyta jako trigger na innych tabelach
CREATE OR REPLACE FUNCTION log_table_changes()
RETURNS TRIGGER AS $$
DECLARE
    changed_cols TEXT[];
    col_name TEXT;
BEGIN
    -- Oblicz zmienione kolumny
    IF TG_OP = 'UPDATE' THEN
        FOR col_name IN SELECT column_name FROM information_schema.columns 
            WHERE table_name = TG_TABLE_NAME 
        LOOP
            IF NEW IS DISTINCT FROM OLD THEN
                -- Uproszczona logika - w praktyce porównujemy po kolumnach
                changed_cols := array_append(changed_cols, col_name);
            END IF;
        END LOOP;
    END IF;

    INSERT INTO audit_log (
        entity_type,
        entity_id,
        action,
        old_values,
        new_values,
        changed_fields
    ) VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id::text, OLD.id::text),
        LOWER(TG_OP),
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END,
        changed_cols
    );

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- 5. Widok dla ostatnich zmian (przydatny do dashboardu)
CREATE OR REPLACE VIEW recent_audit_entries AS
SELECT 
    id,
    entity_type,
    entity_id,
    action,
    changed_fields,
    user_email,
    created_at,
    -- Skrócona wersja zmian
    CASE 
        WHEN action = 'create' THEN 'Created new record'
        WHEN action = 'update' THEN 'Updated ' || array_to_string(changed_fields, ', ')
        WHEN action = 'delete' THEN 'Deleted record'
        WHEN action = 'restore' THEN 'Restored record'
        ELSE action
    END AS description
FROM audit_log
ORDER BY created_at DESC
LIMIT 100;

-- 6. Funkcja do czyszczenia starych wpisów (opcjonalna)
CREATE OR REPLACE FUNCTION cleanup_old_audit_entries(days_to_keep INTEGER DEFAULT 365)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audit_log 
    WHERE created_at < NOW() - (days_to_keep || ' days')::INTERVAL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 7. Polityka RLS (opcjonalna - jeśli używasz Row Level Security)
-- ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
-- 
-- CREATE POLICY audit_log_select_policy ON audit_log
--     FOR SELECT
--     USING (true);  -- Wszyscy mogą czytać (lub ograniczyć do adminów)
-- 
-- CREATE POLICY audit_log_insert_policy ON audit_log
--     FOR INSERT
--     WITH CHECK (true);  -- Aplikacja może wstawiać

-- 8. Komentarze
COMMENT ON TABLE audit_log IS 'System logowania wszystkich zmian w systemie (audit trail)';
COMMENT ON COLUMN audit_log.entity_type IS 'Typ encji (product, order, customer, etc.)';
COMMENT ON COLUMN audit_log.entity_id IS 'ID encji (UUID jako TEXT)';
COMMENT ON COLUMN audit_log.action IS 'Typ akcji (create, update, delete, etc.)';
COMMENT ON COLUMN audit_log.old_values IS 'Poprzedni stan encji (JSONB)';
COMMENT ON COLUMN audit_log.new_values IS 'Nowy stan encji (JSONB)';
COMMENT ON COLUMN audit_log.changed_fields IS 'Lista zmienionych pól';
COMMENT ON COLUMN audit_log.correlation_id IS 'ID do grupowania powiązanych operacji';

COMMIT;

-- ============================================================
-- Przykład użycia triggera (opcjonalnie, dla automatycznego audytu)
-- ============================================================
-- 
-- CREATE TRIGGER products_audit_trigger
-- AFTER INSERT OR UPDATE OR DELETE ON products_catalog
-- FOR EACH ROW EXECUTE FUNCTION log_table_changes();
