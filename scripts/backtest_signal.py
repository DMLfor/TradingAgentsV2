#!/usr/bin/env python3
"""Backtest an indicator signal across a stock universe.

Usage:
    python scripts/backtest_signal.py 688018,688981,688111,688012 --indicator macd --signal golden_cross --hold 5
    python scripts/backtest_signal.py 000001,000002 --indicator rsi --signal oversold --hold 10
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicatorAnalyzer, TdxQuery, resolve_codes, get_name


def backtest(codes: list[str], indicator: str, signal_type: str, hold_days: int, save: bool):
    name_map = {c: get_name(c) for c in codes}
    code_lines = [f"  {c} ({n})" if n else f"  {c}" for c, n in name_map.items()]

    lines = []
    lines.append(f"Backtest Report: {indicator}.{signal_type}")
    lines.append("Codes:")
    lines.extend(code_lines)
    lines.append(f"Hold days: {hold_days}")
    lines.append(f"Time: {datetime.now().isoformat()}")
    lines.append("=" * 70)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        report = analyzer.backtest(
            codes, indicator=indicator, signal_type=signal_type,
            hold_days=hold_days, lookback=502,
        )

        s = report["summary"]
        lines.append(f"\nTotal signals : {s['total_signals']}")
        lines.append(f"Win rate      : {s['win_rate']}%")
        lines.append(f"Avg return    : {s['avg_return']}%")
        lines.append(f"Median return : {s['median_return']}%")
        lines.append(f"Max gain      : {s['max_gain']}%")
        lines.append(f"Max loss      : {s['max_loss']}%")
        lines.append(f"Profit factor : {s['profit_factor']}")
        lines.append(f"Sharpe (approx): {s['sharpe_approx']}")

        detail = report["detail"]
        if not detail.empty:
            lines.append("\n" + "-" * 70)
            lines.append("Trade Details")
            lines.append("-" * 70)
            lines.append(detail.to_string(index=False))
        else:
            lines.append("\nNo trades generated.")

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "reports" / "backtests"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"bt_{indicator}_{signal_type}_h{hold_days}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path = out_dir / fname
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Backtest indicator signals")
    parser.add_argument("codes", help="Comma-separated stock codes or names")
    parser.add_argument("--indicator", "-i", required=True, help="Indicator name")
    parser.add_argument("--signal", "-s", required=True, help="Signal type")
    parser.add_argument("--hold", "-d", type=int, default=5, help="Hold days (default: 5)")
    parser.add_argument("--save", action="store_true", help="Save report to reports/backtests/")
    args = parser.parse_args()

    try:
        codes = resolve_codes(args.codes)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    backtest(codes, args.indicator, args.signal, args.hold, save=args.save)


if __name__ == "__main__":
    main()
