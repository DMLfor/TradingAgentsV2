CREATE INDEX IF NOT EXISTS idx_daily_date ON tdx_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_code_date ON tdx_daily(code, trade_date);
CREATE INDEX IF NOT EXISTS idx_min5_date ON tdx_minute_5(trade_date);
CREATE INDEX IF NOT EXISTS idx_min5_code ON tdx_minute_5(code);
CREATE INDEX IF NOT EXISTS idx_min1_date ON tdx_minute_1(trade_date);
CREATE INDEX IF NOT EXISTS idx_min1_code ON tdx_minute_1(code);
CREATE INDEX IF NOT EXISTS idx_registry_mtime ON tdx_file_registry(file_mtime);
CREATE INDEX IF NOT EXISTS idx_registry_symbol ON tdx_file_registry(symbol);
CREATE INDEX IF NOT EXISTS idx_synclog_date ON tdx_sync_log(sync_date);
