"""示例5：指标分析 — 扫描、选股、回测、排名

用法:
    cd TradingAgentsV2
    python -m examples.05_indicator_analysis
"""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicatorAnalyzer, TdxQuery


SAMPLE_CODES = ["000001", "000002", "600000", "000333", "002594"]


def demo_scan():
    """扫描多只股票当前指标状态"""
    print("=" * 60)
    print("Demo 1: 扫描 RSI 当前值")
    print("=" * 60)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        df = analyzer.scan(SAMPLE_CODES, indicator="rsi", params={"period": 14})
        print(df.to_string(index=False))
        print()


def demo_find_signals():
    """找出出现特定信号的股票"""
    print("=" * 60)
    print("Demo 2: 查找 MACD 金叉信号")
    print("=" * 60)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        signals = analyzer.find_signals(
            SAMPLE_CODES,
            indicator="macd",
            signal_type="golden_cross",
        )
        if signals.empty:
            print("未找到近期 MACD 金叉信号")
        else:
            print(signals.to_string(index=False))
        print()


def demo_backtest():
    """回测指标信号历史表现"""
    print("=" * 60)
    print("Demo 3: 回测 RSI 超卖后5日收益")
    print("=" * 60)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        report = analyzer.backtest(
            SAMPLE_CODES,
            indicator="rsi",
            signal_type="oversold",
            hold_days=5,
            params={"period": 14},
        )

        summary = report["summary"]
        print(f"总信号数 : {summary['total_signals']}")
        print(f"胜率     : {summary['win_rate']}%")
        print(f"平均收益 : {summary['avg_return']}%")
        print(f"中位数   : {summary['median_return']}%")
        print(f"最大盈利 : {summary['max_gain']}%")
        print(f"最大亏损 : {summary['max_loss']}%")
        print(f"盈亏比   : {summary['profit_factor']}")
        print()

        if not report["detail"].empty:
            print("最近5笔交易明细:")
            print(report["detail"].tail(5).to_string(index=False))
        print()


def demo_rank():
    """按指标值排名"""
    print("=" * 60)
    print("Demo 4: 按 RSI 从低到高排名（找超卖）")
    print("=" * 60)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        ranked = analyzer.rank(
            SAMPLE_CODES,
            indicator="rsi",
            params={"period": 14},
            ascending=True,
        )
        print(ranked.to_string(index=False))
        print()


def demo_list_signals():
    """查看某个指标支持的所有信号"""
    print("=" * 60)
    print("Demo 5: MACD 支持的分析信号")
    print("=" * 60)

    with TdxQuery() as q:
        analyzer = TdxIndicatorAnalyzer(q)
        signals = analyzer.available_signals("macd")
        print(", ".join(signals))
        print()


if __name__ == "__main__":
    demo_list_signals()
    demo_scan()
    demo_find_signals()
    demo_backtest()
    demo_rank()
