#!/usr/bin/env python3
"""Rank stocks by an indicator column.

Usage:
    python scripts/rank_stocks.py 688018,688981,688111,688012 --indicator rsi --ascending
    python scripts/rank_stocks.py 000001,000002,600000 --indicator macd --column macd_hist
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicatorAnalyzer, TdxQuery, resolve_codes, get_name


def rank(codes: list[str], indicator: str, column: str | None, ascending: bool, save: bool):
    name_map = {c: get_name(c) for c in codes}
    code_lines = [f"  {c} ({n})" if n else f"  {c}" for c, n in name_map.items()]

    lines = []
    lines.append(f"Ranking: {indicator}")
    lines.append("Codes:")
    lines.extend(code_lines)
    lines.append(f"Order: {'ascending' if ascending else 'descending'}")
    lines.append(f"Time: {datetime.now().isoformat()}")
    lines.append("=" * 70)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        df = analyzer.rank(codes, indicator=indicator, column=column, ascending=ascending)

        if df.empty:
            lines.append("\nNo results.")
        else:
            lines.append("")
            lines.append(df.to_string(index=False))

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "reports" / "rankings"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"rank_{indicator}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path = out_dir / fname
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Rank stocks by indicator")
    parser.add_argument("codes", help="Comma-separated stock codes or names")
    parser.add_argument("--indicator", "-i", required=True, help="Indicator name")
    parser.add_argument("--column", "-c", default=None, help="Specific column to rank by")
    parser.add_argument("--ascending", "-a", action="store_true", help="Sort ascending")
    parser.add_argument("--save", action="store_true", help="Save report to reports/rankings/")
    args = parser.parse_args()

    try:
        codes = resolve_codes(args.codes)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    rank(codes, args.indicator, args.column, args.ascending, save=args.save)


if __name__ == "__main__":
    main()
