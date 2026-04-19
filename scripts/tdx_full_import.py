#!/usr/bin/env python
"""首次全量导入脚本

Usage:
    python tdx_full_import.py
    python tdx_full_import.py --config my.yaml
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tdx_core.config import TdxConfig
from tdx_core.sync import TdxSyncEngine
from tdx_core.notify import send_notification


def main():
    parser = argparse.ArgumentParser(description="TDX Full Import")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    args = parser.parse_args()

    config = TdxConfig()
    if args.config:
        config = TdxConfig.from_yaml(args.config)

    engine = TdxSyncEngine(config)
    start = time.time()

    print("Starting full import...")
    result = engine.full_import()
    duration = time.time() - start

    print(f"Full import completed in {duration:.1f}s")
    print(f"  Rows read:    {result.rows_read}")
    print(f"  Rows written: {result.rows_written}")
    print(f"  Rows failed:  {result.rows_failed}")
    print(f"  Status:       {result.status.value}")

    if result.failed_files:
        print(f"  Failed files (first 10):")
        for f in result.failed_files[:10]:
            print(f"    - {f}")

    send_notification(result, duration, config)

    if result.rows_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
