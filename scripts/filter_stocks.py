#!/usr/bin/env python3
"""Sector-based stock screener — 行业板块选股工具.

Usage:
    # List all industries
    python scripts/filter_stocks.py --list-level1
    python scripts/filter_stocks.py --list-level2 --level1 电子
    python scripts/filter_stocks.py --list-boards

    # Filter by single condition
    python scripts/filter_stocks.py --level1 电子
    python scripts/filter_stocks.py --level2 半导体
    python scripts/filter_stocks.py --level3 数字芯片设计
    python scripts/filter_stocks.py --board 科创板

    # Combined filter
    python scripts/filter_stocks.py --level1 电子 --board 科创板

    # Show stats only
    python scripts/filter_stocks.py --stats

    # Export to file
    python scripts/filter_stocks.py --level1 银行 --output bank_stocks.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from tdx_core import (
    filter_stocks,
    list_level1,
    list_level2,
    list_level3,
    list_boards,
    sector_stats,
    get_meta,
)


def _print_table(rows: list[list[str]], headers: list[str]) -> None:
    """Print a simple aligned table."""
    if not rows:
        print("  (无数据)")
        return
    col_widths = [max(len(str(r[i])) for r in rows + [headers]) + 2 for i in range(len(headers))]
    header_line = "".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
    print("  " + header_line)
    print("  " + "-" * sum(col_widths))
    for row in rows:
        print("  " + "".join(f"{str(v):<{w}}" for v, w in zip(row, col_widths)))


def main():
    parser = argparse.ArgumentParser(description="Sector-based stock screener")
    parser.add_argument("--list-level1", action="store_true", help="List all 一级行业")
    parser.add_argument("--list-level2", action="store_true", help="List all 二级行业 (optionally filtered by --level1)")
    parser.add_argument("--list-level3", action="store_true", help="List all 三级行业 (optionally filtered)")
    parser.add_argument("--list-boards", action="store_true", help="List all 所属板块")
    parser.add_argument("--stats", action="store_true", help="Show metadata statistics")
    parser.add_argument("--level1", type=str, default=None, help="Filter by 一级行业")
    parser.add_argument("--level2", type=str, default=None, help="Filter by 二级行业")
    parser.add_argument("--level3", type=str, default=None, help="Filter by 三级行业")
    parser.add_argument("--board", type=str, default=None, help="Filter by 所属板块")
    parser.add_argument("--limit", type=int, default=0, help="Max results to show (0=unlimited)")
    parser.add_argument("--output", type=str, default=None, help="Save results to file")
    args = parser.parse_args()

    # ── Discovery mode ──
    if args.stats:
        s = sector_stats()
        print("▌元数据统计")
        print(f"  总股票数: {s['total']}")
        print(f"  一级行业: {s['level1_count']} 个")
        print(f"  二级行业: {s['level2_count']} 个")
        print(f"  三级行业: {s['level3_count']} 个")
        print(f"  所属板块: {s['board_count']} 个")
        return

    if args.list_level1:
        industries = list_level1()
        print(f"▌一级行业 ({len(industries)}个)")
        for i, name in enumerate(industries, 1):
            print(f"  {i:2}. {name}")
        return

    if args.list_level2:
        industries = list_level2(args.level1)
        prefix = f" (under {args.level1})" if args.level1 else ""
        print(f"▌二级行业{prefix} ({len(industries)}个)")
        for i, name in enumerate(industries, 1):
            print(f"  {i:2}. {name}")
        return

    if args.list_level3:
        industries = list_level3(args.level1, args.level2)
        print(f"▌三级行业 ({len(industries)}个)")
        for i, name in enumerate(industries, 1):
            print(f"  {i:2}. {name}")
        return

    if args.list_boards:
        boards = list_boards()
        print(f"▌所属板块 ({len(boards)}个)")
        for i, name in enumerate(boards, 1):
            print(f"  {i:2}. {name}")
        return

    # ── Filter mode ──
    if not any((args.level1, args.level2, args.level3, args.board)):
        print("[ERROR] 请至少指定一个筛选条件，或使用 --list-level1 / --stats 查看概览")
        parser.print_help()
        sys.exit(1)

    results = filter_stocks(
        level1=args.level1,
        level2=args.level2,
        level3=args.level3,
        board=args.board,
    )

    # Build display rows
    rows = []
    for code in results:
        m = get_meta(code)
        if m:
            rows.append([
                code,
                m.get("name", ""),
                m.get("level1", ""),
                m.get("level2", ""),
                m.get("board", ""),
            ])

    # Summary
    filters = []
    if args.level1:
        filters.append(f"一级行业={args.level1}")
    if args.level2:
        filters.append(f"二级行业={args.level2}")
    if args.level3:
        filters.append(f"三级行业={args.level3}")
    if args.board:
        filters.append(f"板块={args.board}")

    print(f"▌选股结果: {' + '.join(filters)}")
    print(f"  共 {len(rows)} 只股票")
    print()

    # Display
    display_rows = rows[:args.limit] if args.limit > 0 else rows
    _print_table(display_rows, ["代码", "名称", "一级行业", "二级行业", "板块"])

    if args.limit > 0 and len(rows) > args.limit:
        print(f"\n  ... 还有 {len(rows) - args.limit} 只未显示 (使用 --limit 0 显示全部)")

    # Export
    if args.output:
        out_path = Path(args.output)
        lines = [f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]}" for r in rows]
        out_path.write_text("代码,名称,一级行业,二级行业,板块\n" + "\n".join(lines), encoding="utf-8")
        print(f"\n[Saved] {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
