#!/usr/bin/env python3
"""Update stock metadata from CSV → config/stock_metadata.json.

Usage:
    python scripts/update_stock_metadata.py
    python scripts/update_stock_metadata.py --csv D:\\new_metadata.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
METADATA_PATH = CONFIG_DIR / "stock_metadata.json"


def build_metadata(csv_path: Path) -> dict:
    """Read CSV and build stock metadata with inverted indexes."""
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            df = pd.read_csv(csv_path, encoding=enc, dtype=str)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"Cannot decode {csv_path} with any known encoding")

    # Normalize column names
    rename_map = {}
    for col in df.columns:
        c = col.strip()
        if c == "代码":
            rename_map[col] = "code"
        elif c == "名称":
            rename_map[col] = "name"
        elif c == "一级行业":
            rename_map[col] = "level1"
        elif c == "二级行业":
            rename_map[col] = "level2"
        elif c == "三级行业":
            rename_map[col] = "level3"
        elif c == "所属板块":
            rename_map[col] = "board"
        elif c == "同花顺行业(完整)":
            rename_map[col] = "thx_industry"
    df = df.rename(columns=rename_map)

    stocks: dict[str, dict] = {}
    idx_level1: dict[str, list[str]] = defaultdict(list)
    idx_level2: dict[str, list[str]] = defaultdict(list)
    idx_level3: dict[str, list[str]] = defaultdict(list)
    idx_board: dict[str, list[str]] = defaultdict(list)
    idx_name: dict[str, list[str]] = defaultdict(list)

    for _, row in df.iterrows():
        raw_code = str(row.get("code", "")).strip()
        # Strip .SH / .SZ / .BJ / .NE suffixes
        code = raw_code.split(".")[0] if "." in raw_code else raw_code
        if not code.isdigit() or len(code) != 6:
            continue

        name = str(row.get("name", "")).strip()
        level1 = str(row.get("level1", "")).strip()
        level2 = str(row.get("level2", "")).strip()
        level3 = str(row.get("level3", "")).strip()
        board = str(row.get("board", "")).strip()
        thx = str(row.get("thx_industry", "")).strip()

        stocks[code] = {
            "name": name,
            "level1": level1,
            "level2": level2,
            "level3": level3,
            "board": board,
            "thx_industry": thx,
        }

        if level1:
            idx_level1[level1].append(code)
        if level2:
            idx_level2[level2].append(code)
        if level3:
            idx_level3[level3].append(code)
        if board:
            idx_board[board].append(code)
        if name:
            idx_name[name].append(code)

    # Sort codes in each index for determinism
    for d in (idx_level1, idx_level2, idx_level3, idx_board, idx_name):
        for k in d:
            d[k] = sorted(set(d[k]))

    return {
        "meta": {
            "source": str(csv_path),
            "total": len(stocks),
            "level1_count": len(idx_level1),
            "level2_count": len(idx_level2),
            "level3_count": len(idx_level3),
            "board_count": len(idx_board),
        },
        "stocks": stocks,
        "index": {
            "by_level1": dict(idx_level1),
            "by_level2": dict(idx_level2),
            "by_level3": dict(idx_level3),
            "by_board": dict(idx_board),
            "by_name": dict(idx_name),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Update stock metadata JSON from CSV")
    parser.add_argument("--csv", type=str, default="", help="Path to metadata CSV (overrides config)")
    args = parser.parse_args()

    # Try to get default CSV path from config
    csv_path = None
    if args.csv:
        csv_path = Path(args.csv)
    else:
        try:
            sys.path.insert(0, str(ROOT))
            from tdx_core.config import TdxConfig
            cfg = TdxConfig()
            if cfg.metadata_source:
                csv_path = Path(cfg.metadata_source)
        except Exception:
            pass

    if not csv_path or not csv_path.exists():
        print("[ERROR] CSV not found.")
        print("  Option 1: python scripts/update_stock_metadata.py --csv /path/to/metadata.csv")
        print("  Option 2: Set metadata_source in config/tdx_config.yaml")
        sys.exit(1)

    data = build_metadata(csv_path)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    m = data["meta"]
    print(f"[OK] Saved {METADATA_PATH}")
    print(f"     Stocks: {m['total']}  |  一级行业: {m['level1_count']}  |  二级行业: {m['level2_count']}")
    print(f"     三级行业: {m['level3_count']}  |  板块: {m['board_count']}")


if __name__ == "__main__":
    main()
