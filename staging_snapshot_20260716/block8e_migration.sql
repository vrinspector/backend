-- ============================================================
-- VR Inspector — Block 8E DB Migration
-- Adds page_number to inspection_pins
-- Run once on the live DB: psql -h <host> -U <user> -d <db> -f block8e_migration.sql
-- ============================================================

ALTER TABLE inspection_pins
  ADD COLUMN IF NOT EXISTS page_number INTEGER NOT NULL DEFAULT 1;

COMMENT ON COLUMN inspection_pins.page_number IS
  'PDF page number (1-indexed). Always 1 for raster images. Added in Block 8E.';

-- Verify
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'inspection_pins' AND column_name = 'page_number';

-- R6: Capture PDF MediaBox dimensions for future coordinate-space migration
ALTER TABLE drawings ADD COLUMN IF NOT EXISTS page_width_pts NUMERIC;
ALTER TABLE drawings ADD COLUMN IF NOT EXISTS page_height_pts NUMERIC;
