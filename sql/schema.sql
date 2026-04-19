-- 日线主表
CREATE TABLE IF NOT EXISTS tdx_daily (
    code        TEXT    NOT NULL,
    trade_date  DATE    NOT NULL,
    open_val    REAL    NOT NULL,
    high_val    REAL    NOT NULL,
    low_val     REAL    NOT NULL,
    close_val   REAL    NOT NULL,
    volume      REAL    NOT NULL,
    amount      REAL    NOT NULL,
    adj_factor  REAL    DEFAULT 1.0,
    is_suspended INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (code, trade_date)
) WITHOUT ROWID;

-- 5分钟线
CREATE TABLE IF NOT EXISTS tdx_minute_5 (
    code        TEXT    NOT NULL,
    trade_date  DATETIME NOT NULL,
    open_val    REAL    NOT NULL,
    high_val    REAL    NOT NULL,
    low_val     REAL    NOT NULL,
    close_val   REAL    NOT NULL,
    volume      REAL    NOT NULL,
    amount      REAL    NOT NULL,
    adj_factor  REAL    DEFAULT 1.0,
    is_suspended INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (code, trade_date)
) WITHOUT ROWID;

-- 1分钟线
CREATE TABLE IF NOT EXISTS tdx_minute_1 (
    code        TEXT    NOT NULL,
    trade_date  DATETIME NOT NULL,
    open_val    REAL    NOT NULL,
    high_val    REAL    NOT NULL,
    low_val     REAL    NOT NULL,
    close_val   REAL    NOT NULL,
    volume      REAL    NOT NULL,
    amount      REAL    NOT NULL,
    adj_factor  REAL    DEFAULT 1.0,
    is_suspended INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (code, trade_date)
) WITHOUT ROWID;

-- 文件注册表（增量更新依据）
CREATE TABLE IF NOT EXISTS tdx_file_registry (
    file_path   TEXT    PRIMARY KEY,
    market      TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    data_type   TEXT    NOT NULL,
    file_size   INTEGER NOT NULL,
    file_mtime  TEXT    NOT NULL,
    record_count INTEGER DEFAULT 0,
    last_synced TEXT,
    md5_hash    TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);

-- 同步日志
CREATE TABLE IF NOT EXISTS tdx_sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_date   TEXT    NOT NULL,
    market      TEXT,
    data_type   TEXT,
    rows_read   INTEGER DEFAULT 0,
    rows_written INTEGER DEFAULT 0,
    rows_failed INTEGER DEFAULT 0,
    duration_sec REAL   DEFAULT 0.0,
    status      TEXT    NOT NULL,
    error_msg   TEXT,
    created_at  TEXT    DEFAULT (datetime('now'))
);
