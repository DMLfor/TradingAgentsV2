#!/usr/bin/env python
"""通信达数据同步主脚本

Usage:
    python tdx_sync.py                          # 增量同步（默认沪深）
    python tdx_sync.py --full                   # 全量导入
    python tdx_sync.py --market sh sz           # 指定市场增量同步
    python tdx_sync.py --market sh --full       # 仅沪市全量导入
    python tdx_sync.py --force                  # 忽略变更检测，强制重跑
    python tdx_sync.py --config my.yaml         # 自定义配置
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tdx_data.config import TdxConfig
from tdx_data.sync import TdxSyncEngine
from tdx_data.models import SyncResult
from tdx_data.notify import send_notification


def setup_logging(config: TdxConfig):
    log_dir = Path(config.log_dir)
    log_dir.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # 按日期分文件
    fh = logging.FileHandler(
        log_dir / f"tdx_sync_{time.strftime('%Y%m%d')}.log",
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # 控制台输出
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def main():
    parser = argparse.ArgumentParser(description="TDX Data Sync")
    parser.add_argument("--full", action="store_true", help="全量导入")
    parser.add_argument("--market", nargs="+", default=None,
                        help="指定市场 (sh sz bj ds)，默认 sh sz")
    parser.add_argument("--force", action="store_true", help="强制重跑")
    parser.add_argument("--workers", type=int, default=4, help="并行线程数（默认4）")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    args = parser.parse_args()

    config = TdxConfig()
    if args.config:
        config = TdxConfig.from_yaml(args.config)

    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info(
        "Sync started: full=%s, market=%s, force=%s",
        args.full, args.market, args.force
    )

    engine = TdxSyncEngine(config)
    start = time.time()

    try:
        if args.full or args.force:
            if args.market:
                # 按指定市场全量导入
                total = SyncResult()
                for m in args.market:
                    r = engine.sync_by_market(m, max_workers=args.workers)
                    total.rows_read += r.rows_read
                    total.rows_written += r.rows_written
                    total.rows_failed += r.rows_failed
                    total.failed_files.extend(r.failed_files)
                result = total if total.rows_read > 0 else None
            else:
                result = engine.full_import(max_workers=args.workers)
        else:
            result = engine.incremental_sync(markets=args.market)

        duration = time.time() - start

        if result is None:
            logger.info("No changes detected, sync completed in %.1fs", duration)
        else:
            logger.info(
                "Sync completed: read=%d, written=%d, failed=%d, duration=%.1fs",
                result.rows_read, result.rows_written,
                result.rows_failed, duration
            )

        send_notification(result, duration, config)

        if result and result.rows_failed > 0:
            sys.exit(1)

    except Exception as exc:
        logger.exception("Sync failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
