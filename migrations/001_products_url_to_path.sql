-- ============================================================
-- MIGRACJA BAZY DANYCH: products_catalog
-- NewERP Manufacturing System
-- 
-- Data: 2025-11-28
-- Wersja: 1.0
-- 
-- UWAGA: Wykonaj pełny BACKUP przed uruchomieniem!
-- ============================================================

-- ============================================================
-- CZĘŚĆ 1: SPRAWDZENIE OBECNEGO STANU
-- ============================================================

-- Sprawdź strukturę tabeli przed migracją
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'products_catalog'
-- ORDER BY ordinal_position;

-- ============================================================
-- CZĘŚĆ 2: ZMIANA NAZW KOLUMN URL → PATH
-- ============================================================
-- UWAGA: Wykonaj tylko jeśli kolumny mają nazwy *_url
-- Jeśli już mają *_path - pomiń tę sekcję!

BEGIN;

-- 2.1 CAD 2D
ALTER TABLE public.products_catalog 
  RENAME COLUMN cad_2d_url TO cad_2d_path;

-- 2.2 CAD 3D  
ALTER TABLE public.products_catalog 
  RENAME COLUMN cad_3d_url TO cad_3d_path;

-- 2.3 User Image
ALTER TABLE public.products_catalog 
  RENAME COLUMN user_image_url TO user_image_path;

-- 2.4 Thumbnail 100
ALTER TABLE public.products_catalog 
  RENAME COLUMN thumbnail_100_url TO thumbnail_100_path;

-- 2.5 Preview 800
ALTER TABLE public.products_catalog 
  RENAME COLUMN preview_800_url TO preview_800_path;

-- 2.6 Preview 4K
ALTER TABLE public.products_catalog 
  RENAME COLUMN preview_4k_url TO preview_4k_path;

-- 2.7 Documentation
ALTER TABLE public.products_catalog 
  RENAME COLUMN additional_documentation_url TO additional_documentation_path;

COMMIT;

-- ============================================================
-- CZĘŚĆ 3: NOWE INDEKSY DLA WYDAJNOŚCI
-- ============================================================

BEGIN;

-- Indeks na kategorię (filtrowanie w GUI)
CREATE INDEX IF NOT EXISTS idx_products_catalog_category 
  ON public.products_catalog(category) 
  WHERE is_active = true;

-- Indeks na materiał (filtrowanie w GUI)
CREATE INDEX IF NOT EXISTS idx_products_catalog_material 
  ON public.products_catalog(material_id) 
  WHERE is_active = true;

-- Indeks na klienta (filtrowanie w GUI)
CREATE INDEX IF NOT EXISTS idx_products_catalog_customer 
  ON public.products_catalog(customer_id) 
  WHERE is_active = true;

-- Indeks na datę utworzenia (sortowanie)
CREATE INDEX IF NOT EXISTS idx_products_catalog_created 
  ON public.products_catalog(created_at DESC);

-- Indeks na datę ostatniego użycia (sortowanie)
CREATE INDEX IF NOT EXISTS idx_products_catalog_last_used 
  ON public.products_catalog(last_used_at DESC NULLS LAST);

-- Indeks na aktywność + idx_code (wyszukiwanie)
CREATE INDEX IF NOT EXISTS idx_products_catalog_active_idx 
  ON public.products_catalog(idx_code) 
  WHERE is_active = true;

-- Full-text search na nazwę i opis
CREATE INDEX IF NOT EXISTS idx_products_catalog_fts 
  ON public.products_catalog 
  USING gin(to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(description, '')));

COMMIT;

-- ============================================================
-- CZĘŚĆ 4: FUNKCJA GENEROWANIA URL Z PATH
-- ============================================================

-- Funkcja do generowania publicznego URL ze ścieżki Storage
CREATE OR REPLACE FUNCTION generate_storage_url(
  bucket_name TEXT,
  file_path TEXT
) RETURNS TEXT AS $$
BEGIN
  IF file_path IS NULL OR file_path = '' THEN
    RETURN NULL;
  END IF;
  
  -- Format URL dla Supabase Storage
  -- ZMIEŃ NA SWÓJ URL PROJEKTU!
  RETURN 'https://xcehmhxaoqfpehrfofbu.supabase.co/storage/v1/object/public/' 
         || bucket_name || '/' || file_path;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Test:
-- SELECT generate_storage_url('product_files', 'products/abc123/cad/2d/cad_2d.dxf');

-- ============================================================
-- CZĘŚĆ 5: WIDOK Z URL (KOMPATYBILNOŚĆ WSTECZNA)
-- ============================================================

-- Widok automatycznie generujący URL z ścieżek
-- Użyj tego widoku jeśli stary kod wymaga kolumn *_url

CREATE OR REPLACE VIEW products_catalog_with_urls AS
SELECT 
  pc.*,
  -- Generowane URL
  generate_storage_url('product_files', cad_2d_path) AS cad_2d_url,
  generate_storage_url('product_files', cad_3d_path) AS cad_3d_url,
  generate_storage_url('product_files', user_image_path) AS user_image_url,
  generate_storage_url('product_files', thumbnail_100_path) AS thumbnail_100_url,
  generate_storage_url('product_files', preview_800_path) AS preview_800_url,
  generate_storage_url('product_files', preview_4k_path) AS preview_4k_url,
  generate_storage_url('product_files', additional_documentation_path) AS additional_documentation_url,
  -- Nazwa materiału (JOIN)
  md.name AS material_name
FROM 
  public.products_catalog pc
LEFT JOIN 
  public.materials_dict md ON pc.material_id = md.id;

-- ============================================================
-- CZĘŚĆ 6: TABELA ZAŁĄCZNIKÓW (jeśli nie istnieje)
-- ============================================================

-- Sprawdź czy tabela istnieje
-- SELECT EXISTS (
--   SELECT FROM information_schema.tables 
--   WHERE table_schema = 'public' 
--   AND table_name = 'product_attachments'
-- );

-- Utwórz jeśli nie istnieje
CREATE TABLE IF NOT EXISTS public.product_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES public.products_catalog(id) ON DELETE CASCADE,
  original_filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  filesize BIGINT,
  mimetype TEXT,
  sha256 TEXT,
  note TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Indeksy dla załączników
CREATE INDEX IF NOT EXISTS idx_product_attachments_product 
  ON public.product_attachments(product_id);

CREATE INDEX IF NOT EXISTS idx_product_attachments_active 
  ON public.product_attachments(product_id, is_active);

CREATE INDEX IF NOT EXISTS idx_product_attachments_created 
  ON public.product_attachments(created_at DESC);

-- ============================================================
-- CZĘŚĆ 7: FUNKCJA GENEROWANIA idx_code
-- ============================================================

-- Funkcja do generowania następnego kodu indeksowego
CREATE OR REPLACE FUNCTION generate_next_idx_code(
  prefix TEXT DEFAULT 'PC'
) RETURNS TEXT AS $$
DECLARE
  year_month TEXT;
  last_code TEXT;
  last_number INTEGER;
  next_number INTEGER;
BEGIN
  year_month := to_char(CURRENT_DATE, 'YYYYMM');
  
  SELECT idx_code INTO last_code
  FROM public.products_catalog
  WHERE idx_code LIKE prefix || '-' || year_month || '-%'
  ORDER BY idx_code DESC
  LIMIT 1;
  
  IF last_code IS NOT NULL THEN
    last_number := CAST(split_part(last_code, '-', 3) AS INTEGER);
    next_number := last_number + 1;
  ELSE
    next_number := 1;
  END IF;
  
  RETURN prefix || '-' || year_month || '-' || LPAD(next_number::TEXT, 4, '0');
END;
$$ LANGUAGE plpgsql;

-- Test:
-- SELECT generate_next_idx_code('PC');
-- Wynik: PC-202411-0001

-- ============================================================
-- CZĘŚĆ 8: TRIGGER updated_at
-- ============================================================

-- Funkcja trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger dla products_catalog
DROP TRIGGER IF EXISTS trg_products_catalog_updated_at ON public.products_catalog;
CREATE TRIGGER trg_products_catalog_updated_at
  BEFORE UPDATE ON public.products_catalog
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- CZĘŚĆ 9: WERYFIKACJA
-- ============================================================

-- Sprawdź strukturę po migracji
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'products_catalog'
  AND column_name LIKE '%_path'
ORDER BY column_name;

-- Sprawdź liczbę produktów
SELECT 
  COUNT(*) AS total_products,
  COUNT(*) FILTER (WHERE is_active = true) AS active_products,
  COUNT(*) FILTER (WHERE cad_2d_path IS NOT NULL) AS with_cad_2d,
  COUNT(*) FILTER (WHERE thumbnail_100_path IS NOT NULL) AS with_thumbnail
FROM public.products_catalog;

-- ============================================================
-- ROLLBACK (w razie problemów)
-- ============================================================
/*
-- Cofnij zmianę nazw kolumn:
ALTER TABLE public.products_catalog RENAME COLUMN cad_2d_path TO cad_2d_url;
ALTER TABLE public.products_catalog RENAME COLUMN cad_3d_path TO cad_3d_url;
ALTER TABLE public.products_catalog RENAME COLUMN user_image_path TO user_image_url;
ALTER TABLE public.products_catalog RENAME COLUMN thumbnail_100_path TO thumbnail_100_url;
ALTER TABLE public.products_catalog RENAME COLUMN preview_800_path TO preview_800_url;
ALTER TABLE public.products_catalog RENAME COLUMN preview_4k_path TO preview_4k_url;
ALTER TABLE public.products_catalog RENAME COLUMN additional_documentation_path TO additional_documentation_url;
*/

-- ============================================================
-- KONIEC MIGRACJI
-- ============================================================
-- Po wykonaniu:
-- 1. Zweryfikuj strukturę: \d products_catalog
-- 2. Test widoku: SELECT * FROM products_catalog_with_urls LIMIT 3;
-- 3. Test funkcji: SELECT generate_next_idx_code('PC');
