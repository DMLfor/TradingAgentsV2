#!/usr/bin/env python
"""初始化数据库：建库建表"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tdx_data.config import TdxConfig
from tdx_data.db import TdxDatabase


def main():
    config = TdxConfig()
    db = TdxDatabase(config)
    print(f"Database initialized: {config.db_path}")

    # 验证表是否创建
    registry = db.get_file_registry()
    print(f"File registry: {len(registry)} entries")

    count = db.get_record_count("tdx_daily")
    print(f"tdx_daily records: {count}")


if __name__ == "__main__":
    main()
