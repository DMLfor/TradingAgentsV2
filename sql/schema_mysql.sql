-- MySQL DDL for TDX Data
-- Database: tdx_data

CREATE DATABASE IF NOT EXISTS tdx_data
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE tdx_data;

-- 日线主表
CREATE TABLE IF NOT EXISTS tdx_daily (
    code        VARCHAR(10) NOT NULL,
    trade_date  DATE        NOT NULL,
    open_val    DECIMAL(12,2) NOT NULL COMMENT '开盘价',
    high_val    DECIMAL(12,2) NOT NULL COMMENT '最高价',
    low_val     DECIMAL(12,2) NOT NULL COMMENT '最低价',
    close_val   DECIMAL(12,2) NOT NULL COMMENT '收盘价',
    volume      BIGINT      NOT NULL COMMENT '成交量',
    amount      BIGINT      NOT NULL COMMENT '成交额',
    adj_factor  DECIMAL(10,4) DEFAULT 1.0 COMMENT '复权因子',
    is_suspended TINYINT    DEFAULT 0 COMMENT '停牌标记',
    created_at  DATETIME    DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
) ENGINE=InnoDB ROW_FORMAT=COMPRESSED;

-- 5分钟线
CREATE TABLE IF NOT EXISTS tdx_minute_5 (
    code        VARCHAR(10) NOT NULL,
    trade_date  DATETIME    NOT NULL,
    open_val    DECIMAL(12,2) NOT NULL,
    high_val    DECIMAL(12,2) NOT NULL,
    low_val     DECIMAL(12,2) NOT NULL,
    close_val   DECIMAL(12,2) NOT NULL,
    volume      BIGINT      NOT NULL,
    amount      BIGINT      NOT NULL,
    adj_factor  DECIMAL(10,4) DEFAULT 1.0,
    is_suspended TINYINT    DEFAULT 0,
    created_at  DATETIME    DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
) ENGINE=InnoDB ROW_FORMAT=COMPRESSED;

-- 1分钟线
CREATE TABLE IF NOT EXISTS tdx_minute_1 (
    code        VARCHAR(10) NOT NULL,
    trade_date  DATETIME    NOT NULL,
    open_val    DECIMAL(12,2) NOT NULL,
    high_val    DECIMAL(12,2) NOT NULL,
    low_val     DECIMAL(12,2) NOT NULL,
    close_val   DECIMAL(12,2) NOT NULL,
    volume      BIGINT      NOT NULL,
    amount      BIGINT      NOT NULL,
    adj_factor  DECIMAL(10,4) DEFAULT 1.0,
    is_suspended TINYINT    DEFAULT 0,
    created_at  DATETIME    DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
) ENGINE=InnoDB ROW_FORMAT=COMPRESSED;

-- 文件注册表
CREATE TABLE IF NOT EXISTS tdx_file_registry (
    file_path   VARCHAR(500) PRIMARY KEY,
    market      VARCHAR(10) NOT NULL,
    symbol      VARCHAR(20) NOT NULL,
    data_type   VARCHAR(20) NOT NULL,
    file_size   BIGINT      NOT NULL,
    file_mtime  VARCHAR(30) NOT NULL,
    record_count INT        DEFAULT 0,
    last_synced DATETIME    NULL,
    md5_hash    VARCHAR(32) NULL,
    created_at  DATETIME    DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_registry_symbol (symbol),
    INDEX idx_registry_mtime (file_mtime)
) ENGINE=InnoDB;

-- 同步日志
CREATE TABLE IF NOT EXISTS tdx_sync_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_date   DATE        NOT NULL,
    market      VARCHAR(20) NULL,
    data_type   VARCHAR(20) NULL,
    rows_read   INT         DEFAULT 0,
    rows_written INT        DEFAULT 0,
    rows_failed INT         DEFAULT 0,
    duration_sec DECIMAL(10,2) DEFAULT 0.0,
    status      VARCHAR(20) NOT NULL,
    error_msg   TEXT        NULL,
    created_at  DATETIME    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_synclog_date (sync_date)
) ENGINE=InnoDB;

-- 索引
CREATE INDEX IF NOT EXISTS idx_daily_date ON tdx_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_min5_date ON tdx_minute_5(trade_date);
CREATE INDEX IF NOT EXISTS idx_min5_code ON tdx_minute_5(code);
CREATE INDEX IF NOT EXISTS idx_min1_date ON tdx_minute_1(trade_date);
CREATE INDEX IF NOT EXISTS idx_min1_code ON tdx_minute_1(code);
