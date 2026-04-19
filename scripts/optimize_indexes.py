"""导入后索引优化脚本

用法：
    python scripts/optimize_indexes.py --drop   # 导入前：删除非主键索引加速写入
    python scripts/optimize_indexes.py --create # 导入后：重建索引优化查询
"""
import argparse
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from tdx_core.config import TdxConfig
from tdx_core.db import TdxDatabase


INDEXES = {
    "tdx_daily": [
        "idx_daily_date ON tdx_daily(trade_date)",
    ],
    "tdx_minute_5": [
        "idx_min5_date ON tdx_minute_5(trade_date)",
        "idx_min5_code ON tdx_minute_5(code)",
    ],
    "tdx_minute_1": [
        "idx_min1_date ON tdx_minute_1(trade_date)",
        "idx_min1_code ON tdx_minute_1(code)",
    ],
}


def drop_indexes(db: TdxDatabase):
    with db._connect() as conn:
        with conn.cursor() as cur:
            for table, idx_list in INDEXES.items():
                for idx_def in idx_list:
                    idx_name = idx_def.split(" ON ")[0].strip()
                    try:
                        cur.execute(f"ALTER TABLE {table} DROP INDEX {idx_name}")
                        print(f"  Dropped: {table}.{idx_name}")
                    except Exception as e:
                        if "check that column/key exists" in str(e).lower():
                            print(f"  Skip (not exists): {table}.{idx_name}")
                        else:
                            print(f"  Error: {table}.{idx_name}: {e}")
        print("Done: non-PK indexes dropped")


def create_indexes(db: TdxDatabase):
    with db._connect() as conn:
        with conn.cursor() as cur:
            for table, idx_list in INDEXES.items():
                for idx_def in idx_list:
                    idx_name = idx_def.split(" ON ")[0].strip()
                    start = time.time()
                    try:
                        cur.execute(f"ALTER TABLE {table} ADD INDEX {idx_def}")
                        elapsed = time.time() - start
                        print(f"  Created: {table}.{idx_name} ({elapsed:.1f}s)")
                    except Exception as e:
                        if "duplicate key name" in str(e).lower():
                            print(f"  Skip (exists): {table}.{idx_name}")
                        else:
                            print(f"  Error: {table}.{idx_name}: {e}")
        print("Done: indexes created")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--drop", action="store_true", help="Drop non-PK indexes")
    group.add_argument("--create", action="store_true", help="Re-create indexes")
    args = parser.parse_args()

    config = TdxConfig()
    if config.db_type != "mysql":
        print("This script only works with MySQL")
        sys.exit(1)

    db = TdxDatabase(config)
    if args.drop:
        drop_indexes(db)
    else:
        create_indexes(db)


if __name__ == "__main__":
    main()
