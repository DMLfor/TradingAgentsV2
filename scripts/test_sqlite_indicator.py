#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tdx_core.query import TdxQuery
from tdx_core.config import TdxConfig
from tdx_core.indicators import TdxIndicators

# SQLite配置
config = TdxConfig()
config.db_type = "sqlite"
config.db_path = "data/tdx_data_test.db"

q = TdxQuery(config=config)

# 查询515180
df = q.get_daily("515180")
print(f"原始数据: {len(df)} 行")

# 计算指标
df = TdxIndicators.compute(df)
base_cols = ["code", "trade_date", "open_val", "high_val", "low_val", "close_val",
             "volume", "amount", "adj_factor", "is_suspended", "created_at", "updated_at"]
indicator_cols = [c for c in df.columns if c not in base_cols]
print(f"指标列数: {len(indicator_cols)}")
print(f"指标列: {indicator_cols[:10]}...")

# 查看最新指标
latest = df[["trade_date", "close_val", "rsi_14", "macd", "macd_signal", "ma_5", "ma_20"]].tail(1)
print(f"\n最新一天指标:")
print(latest.to_string(index=False))

q.close()
print("\n[OK] 指标计算验证通过")
