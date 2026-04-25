#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tdx_core.query import TdxQuery
from tdx_core.config import TdxConfig

db_path = "data/tdx_data_test.db"

# 1. 直接查 SQLite
print("=== 直接查 SQLite ===")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("表:", [r[0] for r in cur.fetchall()])

cur.execute("PRAGMA table_info(tdx_daily)")
print("tdx_daily列:", [r[1] for r in cur.fetchall()])

cur.execute("SELECT COUNT(*) FROM tdx_daily")
print("总行数:", cur.fetchone()[0])

cur.execute("SELECT DISTINCT code FROM tdx_daily LIMIT 10")
print("代码:", [r[0] for r in cur.fetchall()])
conn.close()

# 2. 通过 TdxQuery 查（使用自定义配置，指向测试数据库）
print("\n=== 通过 TdxQuery 查 ===")
config = TdxConfig()
config.db_type = "sqlite"
config.db_path = db_path

q = TdxQuery(config=config)

df = q.get_daily("515180")
print(f"515180 行数: {len(df)}")
print(f"列: {list(df.columns)}")
if len(df) > 0:
    print(f"最近3天:\n{df.tail(3)}")

codes = q.get_stock_list()
print(f"\n总代码数: {len(codes)}")

max_date = q.get_max_date("515180")
print(f"515180 最新日期: {max_date}")

q.close()
print("\n[OK] SQLite 链路验证通过")
