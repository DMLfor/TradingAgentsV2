#!/usr/bin/env python3
"""打包项目为本地 Claw 部署包.

本地 Claw 直接使用 MySQL，无需包含数据库文件.
打包后的内容仅包含代码 + 配置 + Claw 工具（< 5MB）.

Usage:
    python scripts/pack_for_claw.py
    python scripts/pack_for_claw.py --output claw_ready
    python scripts/pack_for_claw.py --zip
"""
import argparse
import logging
import shutil
import zipfile
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

# 需要打包的代码目录
INCLUDE_DIRS = [
    "tdx_core",
    "strategies",
    "sql",
    "config",
    "claw",
]

# 需要打包的脚本（分析类脚本全部包含）
INCLUDE_SCRIPTS = [
    "scripts/analyze_stock.py",
    "scripts/scan_market.py",
    "scripts/rank_stocks.py",
    "scripts/rank_growth_board.py",
    "scripts/technical_master.py",
    "scripts/etf_longterm_tracker.py",
    "scripts/etf_volatility_strategy.py",
    "scripts/strategy_backtest.py",
    "scripts/batch_backtest.py",
    "scripts/backtest_signal.py",
    "scripts/filter_stocks.py",
    "scripts/list_indicators.py",
    "scripts/show_kline.py",
    "scripts/generate_strategies.py",
    "scripts/claw_register.py",
    "scripts/claw_check.py",
]

INCLUDE_FILES = [
    "pyproject.toml",
    "requirements.txt",
    "README.md",
    "AGENTS.md",
]

EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    ".git",
    ".pytest_cache",
    ".coverage",
    "*.egg-info",
    ".claude",
    ".omc",
    ".kimi",
]


def copy_tree(src: Path, dst: Path):
    """递归复制目录，排除不需要的文件."""
    if not src.exists():
        logger.warning("[跳过] 源目录不存在: %s", src)
        return

    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        # 排除模式
        if any(p in str(item) for p in EXCLUDE_PATTERNS):
            continue
        if item.is_dir():
            copy_tree(item, dst / item.name)
        else:
            shutil.copy2(item, dst / item.name)


def main():
    parser = argparse.ArgumentParser(description="打包项目为本地 Claw 部署包")
    parser.add_argument("--output", "-o", default="claw_ready",
                        help="输出目录 (默认: claw_ready/)")
    parser.add_argument("--zip", action="store_true",
                        help="同时生成 ZIP 压缩包")
    args = parser.parse_args()

    output_dir = ROOT / args.output

    # 清理旧目录
    if output_dir.exists():
        logger.info("[清理] 删除旧目录: %s", output_dir)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[开始] 打包本地 Claw 部署包")
    logger.info("  输出目录: %s", output_dir)

    # 1. 复制代码目录
    for dname in INCLUDE_DIRS:
        src = ROOT / dname
        dst = output_dir / dname
        if src.exists():
            logger.info("[复制] %s/ → %s/", src.relative_to(ROOT), dst.relative_to(ROOT))
            copy_tree(src, dst)
        else:
            logger.warning("[跳过] 目录不存在: %s", dname)

    # 2. 复制脚本
    scripts_dst = output_dir / "scripts"
    scripts_dst.mkdir(exist_ok=True)
    for fpath in INCLUDE_SCRIPTS:
        src = ROOT / fpath
        if src.exists():
            dst = output_dir / fpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logger.info("[复制] %s", fpath)
        else:
            logger.warning("[跳过] 不存在: %s", fpath)

    # 3. 复制根目录文件
    for fname in INCLUDE_FILES:
        src = ROOT / fname
        if src.exists():
            shutil.copy2(src, output_dir / fname)
            logger.info("[复制] %s", fname)

    # 4. 计算总大小
    total_size = sum(
        f.stat().st_size
        for f in output_dir.rglob("*")
        if f.is_file()
    )
    total_size_mb = total_size / (1024 * 1024)

    logger.info("=" * 50)
    logger.info("[完成] 本地 Claw 部署包已生成")
    logger.info("  目录: %s", output_dir)
    logger.info("  总大小: %.1f MB", total_size_mb)
    logger.info("  文件数: %d", len(list(output_dir.rglob("*"))))
    logger.info("=" * 50)

    # 5. 生成 ZIP（如果需要）
    if args.zip:
        zip_path = output_dir.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in output_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(ROOT))
        zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
        logger.info("[完成] ZIP 包: %s (%.1f MB)", zip_path, zip_size_mb)

    logger.info("\n下一步:")
    logger.info("  1. 确保本地 MySQL 已启动 (127.0.0.1:3306)")
    logger.info("  2. 运行: python scripts/claw_register.py --register")
    logger.info("  3. Windows Task Scheduler 中将出现 TradingAgentsV2 任务组")


if __name__ == "__main__":
    main()
