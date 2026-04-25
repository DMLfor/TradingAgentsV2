#!/usr/bin/env python3
"""List all available indicators and their signals.

Usage:
    python scripts/list_indicators.py
    python scripts/list_indicators.py --indicator macd
"""

import argparse
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicatorAnalyzer, TdxQuery


def list_all():
    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        indicators = analyzer.available_indicators()

        print(f"Available indicators: {len(indicators)}")
        print("=" * 60)

        for ind in indicators:
            signals = analyzer.available_signals(ind)
            sig_str = ", ".join(signals) if signals else "(no signals)"
            print(f"{ind:20s} -> {sig_str}")


def list_one(indicator: str):
    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        signals = analyzer.available_signals(indicator)
        print(f"Indicator: {indicator}")
        print("Signals:")
        for s in signals:
            print(f"  - {s}")


def main():
    parser = argparse.ArgumentParser(description="List available indicators")
    parser.add_argument("--indicator", "-i", default=None, help="Show details for one indicator")
    args = parser.parse_args()

    if args.indicator:
        list_one(args.indicator)
    else:
        list_all()


if __name__ == "__main__":
    main()
