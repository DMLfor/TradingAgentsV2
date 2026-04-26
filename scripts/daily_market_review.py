#!/usr/bin/env python3
"""每日市场技术复盘 — 一键生成结构化复盘报告.

Usage:
    python scripts/daily_market_review.py --save
    python scripts/daily_market_review.py --date 2026-04-25 --save
    python scripts/daily_market_review.py --board 创业板 --min-score 55 --top-n 20 --save
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Auto-detect project root
_p = Path(__file__).resolve()
ROOT = str(_p.parent.parent)
for i in range(2, min(8, len(_p.parents))):
    _ancestor = _p.parents[i]
    if (_ancestor / "tdx_core").exists() or (_ancestor / "pyproject.toml").exists():
        ROOT = str(_ancestor)
        break
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxQuery
from tdx_core.review_engine import DailyReviewEngine
from tdx_core.reporting import ReportManager


def main():
    parser = argparse.ArgumentParser(description="A股每日技术复盘")
    parser.add_argument("--date", "-d", help="复盘日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--board", "-b", help="指定板块扫描，如 创业板")
    parser.add_argument("--min-score", type=float, default=60, help="回撤选股最低分 (default: 60)")
    parser.add_argument("--top-n", type=int, default=15, help="输出个股数量 (default: 15)")
    parser.add_argument("--workers", type=int, default=12, help="并行线程数 (default: 12)")
    parser.add_argument("--save", "-s", action="store_true", help="保存报告到 results/review/")
    parser.add_argument("--skip-picks", action="store_true", help="跳过回撤选股（全市场MySQL环境下较慢）")
    parser.add_argument("--skip-signals", action="store_true", help="跳过信号雷达")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    print(f"=" * 70)
    print(f"A股每日技术复盘 — {date_str}")
    print(f"=" * 70)
    print("数据加载中，请稍候...")

    with TdxQuery() as q:
        engine = DailyReviewEngine(q, date=date_str)
        effective_date = engine._resolve_effective_date()
        if effective_date != date_str:
            print(f"  [提示] 指定日期 {date_str} 数据不足，自动回退到最近有效交易日 {effective_date}")

        # 1. 大盘环境
        print("\n[1/9] 分析大盘环境...")
        overview = engine.market_overview()
        print(f"  已分析 {len(overview)} 个宽基指数")

        # 2. 市场风格
        print("[2/9] 判断市场风格...")
        style = engine.market_style()
        print(f"  风格: {style.get('style', '未知')}")

        # 3. 板块热力
        print("[3/9] 计算板块热力...")
        top5, bottom5 = engine.sector_heatmap(level="level1")
        print(f"  领涨板块: {', '.join(top5['sector'].tolist()) if not top5.empty else '无'}")

        # 4. 市场情绪（已融合趋势评分+量价分析）
        print("[4/9] 统计市场情绪...")
        sentiment = engine.sentiment_gauge()
        if "error" not in sentiment:
            print(f"  涨跌比: {sentiment['up']}/{sentiment['down']}，"
                  f"涨停(近似): {sentiment['limit_up']}，"
                  f"情绪: {sentiment['sentiment']}")
            print(f"  趋势状态: {sentiment.get('trend_stage', '未知')} (评分: {sentiment.get('trend_score', 0)})")
            print(f"  量能: {sentiment.get('volume_state', '未知')} | 资金流向: {sentiment.get('money_flow', '未知')}")
            if sentiment.get('trend_notes') or sentiment.get('vp_notes'):
                notes = sentiment.get('trend_notes', []) + sentiment.get('vp_notes', [])
                print(f"  修正提示: {'；'.join(notes)}")

        # 5. ETF 跟踪
        print("[5/9] ETF 策略日报...")
        etf_list = engine.etf_tracker()
        for etf in etf_list:
            print(f"  {etf['code']}({etf['name']}): {etf['state_zh']}，评分{etf['trend_score']}/10")

        # 6. 信号雷达
        signals = []
        if not args.skip_signals:
            print("[6/9] 扫描技术信号...")
            signals = engine.signal_radar()
            for sig in signals:
                print(f"  {sig['signal']}: {sig['count']} 只")
        else:
            print("[6/9] 跳过信号雷达 (--skip-signals)")

        # 7. 回撤选股
        picks = []
        if not args.skip_picks:
            print(f"[7/9] 运行回撤选股 (min_score={args.min_score})...")
            picks = engine.pullback_picks(
                board=args.board,
                min_score=args.min_score,
                top_n=args.top_n,
                workers=args.workers,
            )
            print(f"  符合条件: {len(picks)} 只")
        else:
            print("[7/9] 跳过回撤选股 (--skip-picks)")

        # 8. 明日前瞻
        print("[8/9] 推演明日前瞻...")
        trend_score_data = engine._market_trend_score()
        vp_data = engine._volume_price_analysis()
        outlook = engine._next_day_outlook(sentiment, trend_score_data, vp_data)
        print(f"  关键位: 支撑{outlook.get('support', '未知')} / 压力{outlook.get('resistance', '未知')}")

        # 9. 交易计划
        print("[9/9] 生成交易计划...")
        plan_data = {
            "market_overview": overview,
            "market_style": style,
            "sentiment": sentiment,
            "etf_tracker": etf_list,
            "signals": signals,
            "pullback_picks": picks,
            "outlook": outlook,
        }
        action_plan = engine.generate_action_plan(plan_data)

    # 组装报告数据
    report_data = {
        "date": date_str,
        "overview": overview,
        "style": style,
        "top5": top5,
        "bottom5": bottom5,
        "sentiment": sentiment,
        "trend_score": trend_score_data,
        "volume_price": vp_data,
        "outlook": outlook,
        "etf": etf_list,
        "signals": signals,
        "picks": picks,
        "action_plan": action_plan,
    }

    # 控制台摘要输出（丰富版，供 prompt 分析使用）
    print("\n" + "=" * 70)
    print("复盘摘要")
    print("=" * 70)

    # 1. 大盘环境
    if overview:
        o = overview[0]
        change_str = f"{o['change_pct']:+.2f}%"
        if o.get('data_anomaly'):
            change_str += " [数据异常]"
        print(f"【大盘】{o['name']} 收{o['close']:.2f} {change_str} | 量比{o.get('vol_ratio_5', 0):.2f} | {o['ma_state']} | {o['macd_state']} | RSI={o.get('rsi', 0):.1f}")
        # 其他指数简况
        other_idx = [f"{x['name']}{x['change_pct']:+.2f}%" for x in overview[1:4] if not x.get('data_anomaly')]
        if other_idx:
            print(f"       其他: {' | '.join(other_idx)}")
    else:
        print("【大盘】N/A")

    # 2. 市场风格
    large = style.get('large_return')
    small = style.get('small_return')
    if large is not None and small is not None:
        print(f"【风格】{style.get('style', '未知')} | 大盘(沪深300) 20日收益 {large:+.2f}% | 小盘(中证1000) 20日收益 {small:+.2f}% | 差值 {style.get('diff', 0):+.2f}%")
    else:
        print(f"【风格】{style.get('style', '数据异常')}")

    # 3. 板块热力
    if not top5.empty:
        top3 = top5.head(3)
        top_str = ' | '.join([f"{r['sector']} {r['avg_change_pct']:+.2f}%" for _, r in top3.iterrows()])
        print(f"【领涨板块】{top_str}")
    if not bottom5.empty:
        bot3 = bottom5.tail(3)
        bot_str = ' | '.join([f"{r['sector']} {r['avg_change_pct']:+.2f}%" for _, r in bot3.iterrows()])
        print(f"【领跌板块】{bot_str}")

    # 4. 市场情绪（详细）
    print(f"【情绪】档位={sentiment.get('sentiment', '未知')} | 上涨{sentiment.get('up', 0)}/下跌{sentiment.get('down', 0)}/平盘{sentiment.get('flat', 0)} | 涨停≈{sentiment.get('limit_up', 0)}/跌停≈{sentiment.get('limit_down', 0)}")
    print(f"       趋势={sentiment.get('trend_stage', '未知')} (评分{sentiment.get('trend_score', 0)}) | 量能={sentiment.get('volume_state', '未知')} | 资金={sentiment.get('money_flow', '未知')}")
    notes = sentiment.get('trend_notes', []) + sentiment.get('vp_notes', [])
    if notes:
        print(f"       修正提示: {'；'.join(notes)}")
    history = sentiment.get('trend_history', [])
    if history:
        parts = [f"{str(h.get('date',''))[-5:]} {h.get('up_ratio',0):.1%}" for h in history]
        print(f"       5日轨迹: {' → '.join(parts)}")

    # 5. 量价分析
    vp = report_data.get('volume_price', {})
    print(f"【量价】成交额较5日均值 {vp.get('volume_change_pct', 0):+.2f}% | 上涨股成交{vp.get('up_amount', 0):.0f}亿 | 下跌股成交{vp.get('down_amount', 0):.0f}亿")
    div = vp.get('divergence', [])
    if div and div[0] != "无明显背离":
        print(f"       背离: {' | '.join(div[:2])}")

    # 6. 明日前瞻
    out = report_data.get('outlook', {})
    print(f"【前瞻】支撑={out.get('support', '未知')} | 压力={out.get('resistance', '未知')} | 关键位={out.get('key_level', '未知')}")
    scenarios = out.get('scenarios', [])
    if scenarios:
        sc = scenarios[0]
        print(f"       情景[{sc.get('label', '?')}] 概率{sc.get('prob', '?')} — {sc.get('condition', '')} → {sc.get('action', '')}")
    watch = out.get('watch_points', [])
    if watch:
        print(f"       观察: {' | '.join(watch[:2])}")

    # 7. ETF
    for etf in etf_list:
        print(f"【ETF】{etf['code']}({etf['name']}) {etf['state_zh']} 评分{etf['trend_score']}/10 RSI={etf['rsi']:.1f} BB%B={etf['bb_pctb']:.3f}")

    # 8. 信号雷达
    if signals:
        sig_str = ' | '.join([f"{s['signal']}={s['count']}只" for s in signals])
        print(f"【信号】{sig_str}")
    else:
        print("【信号】无触发")

    # 9. 回撤选股
    print(f"【选股】{len(picks)} 只符合条件")
    for p in picks[:5]:
        print(f"       {p['code']}({p['name']}) 评分{p['total_score']:.0f} 买入{p['entry_price']:.2f} 止损{p['stop_price']:.2f} 盈亏比{p['risk_reward']:.2f}")

    # 10. 交易计划核心
    print(f"【计划】方向={sentiment.get('trend_adjusted', '未知')} | 建议仓位见交易计划板块")
    print("=" * 70)

    # 保存报告
    if args.save:
        rm = ReportManager()
        path = rm.save_review_report(report_data)
        rm.update_index()
        print(f"\n[已保存报告] {path}")
    else:
        print("\n(使用 --save 保存报告到 results/review/)")


if __name__ == "__main__":
    main()
