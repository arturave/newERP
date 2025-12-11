-- ============================================================
-- Documents Module - Database Migrations
-- ============================================================
-- Ten plik zawiera SQL do utworzenia tabel w Supabase.
-- Wykonaj w Supabase SQL Editor.
-- ============================================================

-- 1. Tabela licznikow dokumentow
-- Zapewnia ciaglosc numeracji przy wspolbieznosci

CREATE TABLE IF NOT EXISTS document_counters (
    doc_type VARCHAR(20) NOT NULL,
    year INTEGER NOT NULL,
    last_number INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (doc_type, year)
);

-- Indeks dla szybkiego wyszukiwania
CREATE INDEX IF NOT EXISTS idx_document_counters_type_year
ON document_counters(doc_type, year);


-- 2. Tabela rejestru dokumentow
-- Przechowuje metadane wygenerowanych plikow

CREATE TABLE IF NOT EXISTS documents_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_type VARCHAR(20) NOT NULL,
    doc_number_full VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    number_seq INTEGER NOT NULL,

    -- Powiazania
    customer_id UUID REFERENCES customers(id),
    related_table VARCHAR(50),
    related_id UUID,

    -- Plik
    storage_path VARCHAR(255) NOT NULL,
    file_size INTEGER,
    content_type VARCHAR(50) DEFAULT 'application/pdf',

    -- Meta
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    template_version_id UUID,

    -- Wersjonowanie
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_documents_registry_type
ON documents_registry(doc_type);

CREATE INDEX IF NOT EXISTS idx_documents_registry_number
ON documents_registry(doc_number_full);

CREATE INDEX IF NOT EXISTS idx_documents_registry_related
ON documents_registry(related_table, related_id);

CREATE INDEX IF NOT EXISTS idx_documents_registry_customer
ON documents_registry(customer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_registry_number_unique
ON documents_registry(doc_number_full) WHERE is_deleted = FALSE;


-- 3. Tabela szablonow dokumentow
-- Pozwala na wersjonowanie i edycje szablonow

CREATE TABLE IF NOT EXISTS document_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_type VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,

    content_html TEXT NOT NULL,
    styles_css TEXT,
    meta_json JSONB,

    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID
);

-- Indeks
CREATE INDEX IF NOT EXISTS idx_document_templates_type
ON document_templates(doc_type);

CREATE INDEX IF NOT EXISTS idx_document_templates_active
ON document_templates(doc_type, is_active) WHERE is_active = TRUE;


-- 4. Funkcja atomowego generowania numeru dokumentu
-- Gwarantuje brak duplikatow przy wspolbieznosci

CREATE OR REPLACE FUNCTION get_next_document_number(p_doc_type VARCHAR, p_year INTEGER)
RETURNS INTEGER AS $$
DECLARE
    next_val INTEGER;
BEGIN
    -- Upsert z RETURNING dla atomowosci
    INSERT INTO document_counters (doc_type, year, last_number, updated_at)
    VALUES (p_doc_type, p_year, 1, NOW())
    ON CONFLICT (doc_type, year)
    DO UPDATE SET
        last_number = document_counters.last_number + 1,
        updated_at = NOW()
    RETURNING last_number INTO next_val;

    RETURN next_val;
END;
$$ LANGUAGE plpgsql;


-- 5. Row Level Security (opcjonalnie)
-- Odkomentuj jesli chcesz ograniczyc dostep

-- ALTER TABLE documents_registry ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE document_templates ENABLE ROW LEVEL SECURITY;

-- Polityka dla documents_registry - dostep dla uwierzytelnionych
-- CREATE POLICY "Users can view documents" ON documents_registry
--     FOR SELECT USING (auth.role() = 'authenticated');

-- CREATE POLICY "Users can insert documents" ON documents_registry
--     FOR INSERT WITH CHECK (auth.role() = 'authenticated');


-- 6. Bucket w Supabase Storage
-- Utworz recznie w Supabase Dashboard: Storage > New Bucket > "documents"
-- Lub uzyj API:
-- INSERT INTO storage.buckets (id, name, public) VALUES ('documents', 'documents', false);


-- 7. Przykladowe dane testowe (opcjonalnie)

-- INSERT INTO document_templates (doc_type, name, content_html, is_active)
-- VALUES
--     ('QUOTATION', 'Oferta Standard 2025', '<html>...</html>', true),
--     ('WZ', 'WZ Standard', '<html>...</html>', true),
--     ('CMR', 'CMR Miedzynarodowy', '<html>...</html>', true);


-- ============================================================
-- Gotowe! Modul dokumentow jest skonfigurowany.
-- ============================================================
