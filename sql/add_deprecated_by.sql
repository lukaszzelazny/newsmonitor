-- Migration: add deprecated_by column to tickers table
-- Run once against the stock schema

ALTER TABLE stock.tickers
    ADD COLUMN IF NOT EXISTS deprecated_by VARCHAR(32)
        REFERENCES stock.tickers(ticker) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tickers_deprecated_by ON stock.tickers(deprecated_by);

-- ============================================================
-- USAGE: When a ticker changes (e.g. CCC -> MDV/Modivo):
--
-- 1. Make sure the new ticker exists first:
--    INSERT INTO stock.tickers (ticker, company_name, sector, in_portfolio, is_favorite)
--    VALUES ('MDV', 'Modivo S.A.', 'Handel', 0, false)
--    ON CONFLICT (ticker) DO NOTHING;
--
-- 2. Mark the old ticker as deprecated:
--    UPDATE stock.tickers SET deprecated_by = 'MDV' WHERE ticker = 'CCC';
--
-- After this:
--   - All historical analyses/sentiments under 'CCC' are preserved
--   - resolve_db_ticker('CCC') will automatically return 'MDV'
--   - 'CCC' will be hidden from dropdown lists
--   - 'CCC' will be hidden from ticker list (unless in_portfolio=1 or is_favorite=true)
-- ============================================================
