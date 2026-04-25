#!/usr/bin/env python3
"""Single-stock deep indicator analysis.

Usage:
    python scripts/analyze_stock.py 688018
    python scripts/analyze_stock.py 000001 --indicators rsi,macd,bollinger
    python scripts/analyze_stock.py 688018 --save
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicatorAnalyzer, TdxQuery, resolve_code, get_name

DEFAULT_INDICATORS = [
    "rsi", "macd", "bollinger", "supertrend", "ma", "stochastic",
    "williams_r", "cci", "adx", "atr", "obv", "mfi",
]


def analyze(code: str, indicators: list[str], save: bool = False):
    name = get_name(code)
    display = f"{code} ({name})" if name else code

    lines = []
    lines.append(f"Stock Analysis Report: {display}")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("=" * 70)

    with TdxQuery() as q:
        # Basic info
        df = q.get_daily(code)
        if df.empty:
            print(f"No data found for {display}")
            sys.exit(1)

        lines.append(f"\nTotal history bars: {len(df)}")
        lines.append(f"Date range: {df['trade_date'].iloc[0]} ~ {df['trade_date'].iloc[-1]}")
        lines.append(f"Latest close: {df['close_val'].iloc[-1]}")

        analyzer = TdxIndicatorAnalyzer(q)

        # Scan each indicator
        for ind in indicators:
            lines.append(f"\n--- {ind.upper()} ---")
            try:
                result = analyzer.scan([code], indicator=ind, lookback=252)
                if result.empty:
                    lines.append("(no data)")
                else:
                    lines.append(result.to_string(index=False))
            except Exception as exc:
                lines.append(f"Error: {exc}")

        # Recent signals (last 30 days)
        lines.append("\n" + "=" * 70)
        lines.append("Recent Signals (last 120 bars)")
        lines.append("=" * 70)

        signal_pairs = [
            ("macd", "golden_cross"), ("macd", "death_cross"),
            ("rsi", "oversold"), ("rsi", "overbought"),
            ("supertrend", "buy"), ("supertrend", "sell"),
            ("bollinger", "touch_lower"), ("bollinger", "touch_upper"),
            ("stochastic", "golden_cross"), ("stochastic", "death_cross"),
        ]

        for ind, sig in signal_pairs:
            try:
                sig_df = analyzer.find_signals([code], indicator=ind, signal_type=sig, lookback=120)
                if not sig_df.empty:
                    lines.append(f"\n{ind}.{sig}: {sig_df.iloc[0]['signal_date']}")
            except Exception:
                pass

        # Backtest major signals
        lines.append("\n" + "=" * 70)
        lines.append("Signal Backtest (hold 5 days)")
        lines.append("=" * 70)

        for ind, sig in [("macd", "golden_cross"), ("rsi", "oversold"), ("supertrend", "buy")]:
            try:
                report = analyzer.backtest([code], indicator=ind, signal_type=sig, hold_days=5, lookback=502)
                s = report["summary"]
                lines.append(f"\n{ind}.{sig}:")
                lines.append(f"  Signals: {s['total_signals']}  WinRate: {s['win_rate']}%  AvgReturn: {s['avg_return']}%")
            except Exception as exc:
                lines.append(f"\n{ind}.{sig}: Error - {exc}")

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "reports" / "analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"analysis_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Single-stock indicator analysis")
    parser.add_argument("code", help="Stock code or name, e.g. 688018 or 乐鑫科技")
    parser.add_argument(
        "--indicators", "-i",
        default=",".join(DEFAULT_INDICATORS),
        help="Comma-separated indicator names",
    )
    parser.add_argument("--save", "-s", action="store_true", help="Save report to reports/analysis/")
    args = parser.parse_args()

    try:
        resolved = resolve_code(args.code)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    indicators = [x.strip() for x in args.indicators.split(",") if x.strip()]
    analyze(resolved, indicators, save=args.save)


if __name__ == "__main__":
    main()
