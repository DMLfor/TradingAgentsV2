#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交易信号跟踪报告 — 输出明确的 BUY/SELL/HOLD 信号.

Usage:
    python scripts/signal_tracker.py --code 515180 --strategy rsi30_bounce --save
    python scripts/signal_tracker.py --code 159545 --strategy macd_golden --save
    python scripts/signal_tracker.py --code 515180 --strategy rsi30_bounce --rsi-buy 28 --rsi-sell 72 --save
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxQuery, get_name
from tdx_core.signals import SignalEngine


def _action_emoji(action: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "WATCH": "👀"}.get(action, "⚪")


def _action_zh(action: str) -> str:
    return {"BUY": "买入", "SELL": "卖出", "HOLD": "持有观望", "WATCH": "密切观察"}.get(action, action)


def _confidence_bar(conf: float, width: int = 20) -> str:
    filled = int(conf * width)
    return "█" * filled + "░" * (width - filled)


def build_report(code: str, strategy: str, params: dict, save: bool) -> str:
    """生成信号报告."""
    name = get_name(code) or code
    lines = []

    with TdxQuery() as q:
        engine = SignalEngine(q)
        signal = engine.generate(code, strategy, **params)
        stats = engine.get_stats(code, strategy)
        history = engine.get_history(code, strategy)

    # 如果有 BUY/SELL 信号，追加到历史
    engine.append_if_triggered(code, signal)

    # ── 标题 ──
    lines.append("╔" + "═" * 70 + "╗")
    lines.append(f"║  交易信号报告{' ' * 56}║")
    lines.append("╠" + "═" * 70 + "╣")
    lines.append(f"  标的: {code} ({name})")
    lines.append(f"  策略: {strategy}")
    lines.append(f"  日期: {signal.date}")
    lines.append("=" * 70)

    # ── 信号强度映射 ──
    strength_emoji = {"STRONG": "🔥", "NORMAL": "", "WEAK": "💧"}
    strength_zh = {"STRONG": "强烈", "NORMAL": "", "WEAK": "弱势"}
    se = strength_emoji.get(signal.strength, "")
    sz = strength_zh.get(signal.strength, "")

    # ── 今日信号 ──
    lines.append("")
    lines.append(f"【今日信号】{_action_emoji(signal.action)} {se} {sz}{_action_zh(signal.action)}")
    lines.append(f"  强度等级: {signal.strength}  |  置信度: {signal.confidence:.0%} {_confidence_bar(signal.confidence)}")
    lines.append(f"  风险等级: {signal.risk_level}")
    lines.append(f"  当前价格: {signal.price:.3f}")
    lines.append("")

    # ── 触发条件 ──
    if signal.triggers:
        lines.append("【触发条件】")
        for t in signal.triggers:
            lines.append(f"  • {t}")
        lines.append("")

    # ── 策略逻辑说明 ──
    lines.append(f"【策略状态】{signal.rationale}")
    lines.append("")

    # ── 持仓建议（基于信号强度分级）──
    lines.append("【操作建议】")
    if signal.action == "BUY" and signal.strength == "STRONG":
        lines.append("  🔥 强烈买入信号 — 多维度共振确认")
        lines.append("  空仓 → 建议建仓 70%~80%，可分 2 批入场")
        lines.append("  已有仓位 → 可加仓至 80%，或维持满仓")
        lines.append("  止损参考: 跌破信号日低点或亏损 -4%")
    elif signal.action == "BUY" and signal.strength == "NORMAL":
        lines.append("  🟢 标准买入信号 — 单一条件满足")
        lines.append("  空仓 → 建议建仓 40%~50%")
        lines.append("  已有仓位 → 可小幅加仓或持有")
        lines.append("  止损参考: 跌破近期低点或亏损 -5%")
    elif signal.action == "BUY" and signal.strength == "WEAK":
        lines.append("  💧 弱势买入信号 — 条件初步满足但不够强")
        lines.append("  空仓 → 建议小仓试探 10%~20%，或继续观望")
        lines.append("  已有仓位 → 不建议加仓，持有观察")
        lines.append("  止损参考: 跌破买入价 -3% 即止损")
    elif signal.action == "SELL" and signal.strength == "STRONG":
        lines.append("  🔥 强烈卖出信号 — 趋势反转确认")
        lines.append("  有持仓 → 建议减仓至 20% 以下或清仓")
        lines.append("  空仓 → 继续观望，不要抄底")
    elif signal.action == "SELL":
        lines.append("  🔴 卖出信号 — 止盈或止损触发")
        lines.append("  有持仓 → 建议减仓 50% 或清仓")
        lines.append("  空仓 → 继续观望，不要抄底")
    elif signal.action == "WATCH":
        lines.append("  👀 密切观察 — 接近交易条件但未触发")
        lines.append("  空仓 → 准备行动，设置价格提醒")
        lines.append("  有持仓 → 注意止盈/止损位")
    else:
        lines.append("  ➡️ 中性观望 — 无明确信号")
        lines.append("  空仓 → 继续等待，不要追高")
        lines.append("  有持仓 → 继续持有，设置好止损")
    lines.append("")

    # ── 历史信号表现 ──
    lines.append("【历史信号表现】")
    if stats and stats.get("closed_trades", 0) > 0:
        lines.append(f"  该策略在历史数据中发出 {stats['total_signals']} 次信号")
        lines.append(f"  已完成交易: {stats['closed_trades']} 笔")
        lines.append(f"  胜率: {stats['win_rate']:.1f}%")
        lines.append(f"  平均盈亏: {stats['avg_pnl_pct']:+.2f}%")
        lines.append(f"  平均盈利: +{stats['avg_win_pct']:.2f}%")
        lines.append(f"  平均亏损: {stats['avg_loss_pct']:.2f}%")
        lines.append(f"  平均持有期: {stats['avg_hold_days']:.0f} 天")
        lines.append(f"  累计收益: {stats['total_return_pct']:+.2f}%")
        if stats.get("last_trade"):
            lt = stats["last_trade"]
            lines.append("")
            lines.append(f"  最近一笔交易:")
            lines.append(f"    买入: {lt['buy_date']} @ {lt['buy_price']:.3f}")
            lines.append(f"    卖出: {lt['sell_date']} @ {lt['sell_price']:.3f}")
            lines.append(f"    盈亏: {lt['pnl_pct']:+.2f}%  (持有 {lt['hold_days']} 天)")
    elif history:
        lines.append(f"  历史信号数: {len(history)} 次")
        lines.append("  尚未有完整买卖闭环，无法统计胜率")
        last_h = history[-1]
        lines.append(f"  最近信号: {last_h['date']} {last_h['action']} @ {last_h.get('price', 'N/A')}")
    else:
        lines.append("  暂无历史信号记录")
    lines.append("")

    # ── 风险提示 ──
    lines.append("【风险提示】")
    if signal.risk_level == "HIGH":
        lines.append("  ⚠️ 当前趋势强度较高，信号可能滞后，注意止损")
    elif signal.risk_level == "LOW":
        lines.append("  ✅ 当前波动较低，信号可靠性较高")
    else:
        lines.append("  ➡️ 正常波动环境，按信号执行即可")

    if signal.action in ("BUY", "WATCH") and signal.extra.get("rsi") is not None:
        rsi = signal.extra["rsi"]
        if rsi < 30:
            lines.append(f"  RSI 处于极端超卖区 ({rsi:.1f})，反弹概率高但需防继续下跌")
        elif rsi < 40:
            lines.append(f"  RSI 偏弱 ({rsi:.1f})，买入后可能继续震荡")

    lines.append("")
    lines.append("【免责声明】")
    lines.append("  本信号仅基于历史数据的技术指标生成，不构成投资建议。")
    lines.append("  交易有风险，入市需谨慎。")
    lines.append("╚" + "═" * 70 + "╝")

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "reports" / "signals"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"signal_{code}_{strategy}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path = out_dir / fname
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")

    return text


def main():
    parser = argparse.ArgumentParser(description="Trading Signal Tracker")
    parser.add_argument("--code", required=True, help="Stock/ETF code")
    parser.add_argument("--strategy", required=True,
                        choices=["rsi30_bounce", "macd_golden", "bollinger_bounce", "trend_follow"],
                        help="Strategy name")
    parser.add_argument("--rsi-buy", type=float, default=30, help="RSI buy threshold")
    parser.add_argument("--rsi-sell", type=float, default=70, help="RSI sell threshold")
    parser.add_argument("--save", action="store_true", help="Save report to reports/signals/")
    args = parser.parse_args()

    params = {}
    if args.strategy == "rsi30_bounce":
        params = {"rsi_buy": args.rsi_buy, "rsi_sell": args.rsi_sell}

    build_report(args.code, args.strategy, params, save=args.save)


if __name__ == "__main__":
    main()
