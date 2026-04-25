#!/usr/bin/env python3
"""Scan a list of stocks for indicator signals.

Usage:
    python scripts/scan_market.py 688018,688981,688111,688012 --indicator macd --signal golden_cross
    python scripts/scan_market.py 000001,000002,600000 --indicator rsi --signal oversold
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicatorAnalyzer, TdxQuery, resolve_codes, get_name


def scan(codes: list[str], indicator: str, signal_type: str | None, save: bool):
    name_map = {c: get_name(c) for c in codes}
    code_lines = [f"  {c} ({n})" if n else f"  {c}" for c, n in name_map.items()]

    lines = []
    lines.append(f"Market Scan: {indicator}")
    lines.append("Codes:")
    lines.extend(code_lines)
    lines.append(f"Time: {datetime.now().isoformat()}")
    lines.append("=" * 70)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)

        if signal_type:
            lines.append(f"\nSearching for signal: {signal_type}")
            df = analyzer.find_signals(codes, indicator=indicator, signal_type=signal_type, lookback=120)
        else:
            lines.append("\nScanning latest indicator values")
            df = analyzer.scan(codes, indicator=indicator, lookback=120)

        if df.empty:
            lines.append("\nNo results found.")
        else:
            lines.append("")
            lines.append(df.to_string(index=False))

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "reports" / "scans"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"scan_{indicator}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path = out_dir / fname
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Scan stocks for indicator signals")
    parser.add_argument("codes", help="Comma-separated stock codes or names")
    parser.add_argument("--indicator", "-i", required=True, help="Indicator name, e.g. macd")
    parser.add_argument("--signal", "-s", default=None, help="Signal type, e.g. golden_cross")
    parser.add_argument("--save", action="store_true", help="Save report to reports/scans/")
    args = parser.parse_args()

    try:
        codes = resolve_codes(args.codes)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    scan(codes, args.indicator, args.signal, save=args.save)


if __name__ == "__main__":
    main()
