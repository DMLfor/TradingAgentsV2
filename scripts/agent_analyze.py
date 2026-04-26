#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent multi-dimensional analysis CLI (ai-hedge-fund style).

Usage:
    python scripts/agent_analyze.py 688018 --bars 120 --save
    python scripts/agent_analyze.py 688018 --no-llm

Workflow: 5 specialists (parallel) → risk_manager → portfolio_manager
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# UTF-8 for Windows GBK terminals
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env before importing any module that reads env vars
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from colorama import Fore, Style, init

from langchain_core.messages import HumanMessage

from tdx_core.agent.data_helper import AgentDataHelper
from tdx_core.agent.graph.workflow import create_workflow

init(autoreset=True)


AGENT_LABELS = {
    "trend_follower": "趋势跟踪者",
    "mean_reversion_trader": "均值回归者",
    "momentum_hunter": "动量猎人",
    "volatility_trader": "波动率交易者",
    "volume_analyst": "量价分析师",
}

SIGNAL_CN = {
    "bullish": ("偏多", Fore.GREEN),
    "bearish": ("偏空", Fore.RED),
    "neutral": ("中性", Fore.YELLOW),
}

RISK_LEVEL_CN = {
    "low": ("低风险", Fore.GREEN),
    "medium": ("中风险", Fore.YELLOW),
    "high": ("高风险", Fore.RED),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent 多维度技术分析")
    parser.add_argument("code", help="股票代码，如 688018")
    parser.add_argument("--bars", type=int, default=120, help="分析窗口天数")
    parser.add_argument("--save", action="store_true", help="保存报告到 results/analysis/")
    parser.add_argument("--no-llm", action="store_true", help="禁用 LLM，使用纯算法综合")
    parser.add_argument("--model", default=None, help="LLM 模型名称，如 kimi-k2.6, moonshot-v1-8k")
    return parser.parse_args()


def print_agent_brief(agent_id: str, sig: dict) -> None:
    """Print a concise single-agent result block."""
    label = AGENT_LABELS.get(agent_id, agent_id)
    s = sig.get("signal", "neutral")
    c = sig.get("confidence", 0)
    reasoning = sig.get("reasoning", "")
    metrics = sig.get("metrics", {})

    s_cn, color = SIGNAL_CN.get(s, (s, Fore.WHITE))

    print(f"      -> {label:<12} [{color}{s_cn}{Style.RESET_ALL}] confidence: {c}%")

    if metrics:
        parts = []
        for k, v in list(metrics.items())[:6]:
            if isinstance(v, float):
                parts.append(f"{k}={v:.2f}")
            else:
                parts.append(f"{k}={v}")
        print(f"         {', '.join(parts)}")

    if reasoning:
        print(f"         {reasoning}")


def print_risk_manager(risk: dict) -> None:
    """Print risk manager output block."""
    level = risk.get("risk_level", "medium")
    stop_loss = risk.get("stop_loss", 0)
    pos_size = risk.get("position_size_pct", 50)
    notes = risk.get("risk_notes", "")
    max_dd = risk.get("max_drawdown_20d", 0)

    level_cn, color = RISK_LEVEL_CN.get(level, (level, Fore.WHITE))
    print(f"\n      -> 风险控制官     [{color}{level_cn}{Style.RESET_ALL}] 建议仓位: {pos_size}%")
    print(f"         止损位: {stop_loss:.2f}, 近20日最大回撤: {max_dd:.1f}%")
    if notes:
        print(f"         {notes}")


def print_header(code: str, name: str) -> None:
    width = 60
    title = f" Agent 多维度分析报告: {code} ({name}) "
    pad = (width - len(title)) // 2
    header = "=" * pad + title + "=" * (width - pad - len(title))
    print(f"\n{Fore.WHITE}{Style.BRIGHT}{header}{Style.RESET_ALL}")


def print_composite(composite: dict) -> None:
    comp_signal = composite.get("signal", "中性")
    comp_conf = composite.get("confidence", 0)
    comp_score = composite.get("composite_score", 0)

    signal_color = Fore.GREEN if comp_score >= 6 else (Fore.RED if comp_score < 5 else Fore.YELLOW)
    print(f"\n{Fore.WHITE}{Style.BRIGHT}[投资总监综合判断]{Style.RESET_ALL} {comp_score:.1f}/10 [{signal_color}{comp_signal}{Style.RESET_ALL}]  confidence: {comp_conf}%")

    reasoning = composite.get("reasoning", "")
    if reasoning:
        print(f"\n reasoning:\n  {reasoning}")

    action = composite.get("action_plan", "")
    if action:
        print(f"\n action_plan: {action}")

    risk = composite.get("risk_notes", "")
    if risk:
        print(f" risk_notes: {risk}")


def print_summary_table(signals: dict, composite: dict, risk: dict, code: str) -> None:
    comp_signal = composite.get("signal", "中性")
    comp_conf = composite.get("confidence", 0)
    comp_score = composite.get("composite_score", 0)
    signal_color = Fore.GREEN if comp_score >= 6 else (Fore.RED if comp_score < 5 else Fore.YELLOW)

    print("\n" + "-" * 60)
    print(f"\n{Fore.WHITE}{Style.BRIGHT}综合信号汇总表:{Style.RESET_ALL}")
    print(f"{'Agent':<12} | {'Signal':<8} | {'Confidence':<10} | {'权重':<6}")
    print("-" * 45)

    weights = {
        "trend_follower": 0.25,
        "mean_reversion_trader": 0.20,
        "momentum_hunter": 0.20,
        "volatility_trader": 0.15,
        "volume_analyst": 0.20,
    }

    for agent_id, label in AGENT_LABELS.items():
        sig = signals.get(agent_id, {}).get(code, {})
        if not sig:
            sig = signals.get(agent_id, {})
        s = sig.get("signal", "neutral")
        c = sig.get("confidence", 0)
        s_cn, color = SIGNAL_CN.get(s, (s, Fore.WHITE))
        w = weights.get(agent_id, 0)
        print(f"{label:<12} | {color}{s_cn:<8}{Style.RESET_ALL} | {c:<10} | {w:<6.2f}")

    print("-" * 45)
    print(f"{'加权综合':<12} | {signal_color}{comp_signal:<8}{Style.RESET_ALL} | {comp_conf:<10} | {'1.00':<6}")

    # Risk manager row
    if risk:
        level = risk.get("risk_level", "medium")
        level_cn, color = RISK_LEVEL_CN.get(level, (level, Fore.WHITE))
        pos = risk.get("position_size_pct", 50)
        print(f"{'风险控制':<12} | {color}{level_cn:<8}{Style.RESET_ALL} | 仓位{pos:<4} | {'-':<6}")


def save_report(code: str, name: str, signals: dict, composite: dict, risk: dict) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = ROOT / "results" / "analysis" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / f"{code}_agent_analysis.md"
    json_path = out_dir / f"{code}_agent_metrics.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"code": code, "name": name, "signals": signals, "composite": composite, "risk": risk},
            f, ensure_ascii=False, indent=2
        )

    lines = [
        f"# Agent 多维度分析报告: {code} ({name})",
        f"",
        f"**分析日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## 综合评分",
        f"",
        f"| 项目 | 值 |",
        f"|:---|:---|",
        f"| 综合评分 | {composite.get('composite_score', 0):.1f} / 10 |",
        f"| 信号 | {composite.get('signal', '中性')} |",
        f"| 置信度 | {composite.get('confidence', 0)}% |",
        f"| 操作建议 | {composite.get('action_plan', '')} |",
        f"| 风险提示 | {composite.get('risk_notes', '')} |",
        f"",
        f"** reasoning **: {composite.get('reasoning', '')}",
        f"",
    ]

    if risk:
        lines.extend([
            f"## 风险控制",
            f"",
            f"| 项目 | 值 |",
            f"|:---|:---|",
            f"| 风险等级 | {risk.get('risk_level', 'medium')} |",
            f"| 止损位 | {risk.get('stop_loss', 0):.2f} |",
            f"| 建议仓位 | {risk.get('position_size_pct', 50)}% |",
            f"| 近20日最大回撤 | {risk.get('max_drawdown_20d', 0):.1f}% |",
            f"| 风险提示 | {risk.get('risk_notes', '')} |",
            f"",
        ])

    lines.append(f"## 各维度分析")
    lines.append(f"")

    for agent_id, label in AGENT_LABELS.items():
        sig = signals.get(agent_id, {}).get(code, {})
        if not sig:
            sig = signals.get(agent_id, {})
        lines.extend([
            f"### {label}",
            f"",
            f"| 项目 | 值 |",
            f"|:---|:---|",
            f"| signal | {sig.get('signal', 'neutral')} |",
            f"| confidence | {sig.get('confidence', 0)}% |",
            f"| reasoning | {sig.get('reasoning', '')} |",
            f"",
            f"**metrics**:",
            f"",
            "```json",
            json.dumps(sig.get("metrics", {}), ensure_ascii=False, indent=2),
            "```",
            f"",
        ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


def main() -> None:
    args = parse_args()
    code = args.code

    # Step 1: Data loading
    print(f"[1/7] 数据加载 ................ 计算中")
    helper = AgentDataHelper()
    df = helper.fetch(code, bars=args.bars)
    if df is None or df.empty:
        print(f"[错误] 无法获取 {code} 的数据")
        sys.exit(1)

    name = helper.get_name(code)
    n_indicators = len([c for c in df.columns if c not in [
        'code', 'trade_date', 'open_val', 'high_val', 'low_val',
        'close_val', 'volume', 'amount', 'adj_factor',
        'is_suspended', 'created_at', 'updated_at'
    ]])
    print(f"[1/7] 数据加载 ................ 完成 ({len(df)}条K线, {n_indicators}个指标)")

    # Step 2-6: Workflow execution with stream
    workflow = create_workflow()
    app = workflow.compile()

    initial_state = {
        "messages": [HumanMessage(content="开始多维度技术分析")],
        "data": {
            "code": code,
            "name": name,
            "df": df,
            "analyst_signals": {},
            "use_llm": not args.no_llm,
            "model": args.model,
        },
        "metadata": {},
    }

    print(f"\n[2/7] Specialist Agents 并行计算中 ...")

    accumulated = {}
    composite = {}
    all_signals = {}
    risk_output = {}

    for step in app.stream(initial_state, stream_mode="updates"):
        for node_name, update in step.items():
            if node_name == "start_node":
                continue

            elif node_name == "portfolio_manager":
                composite = update.get("data", {}).get("composite_result", {}).get(code, {})
                if not args.no_llm and composite.get("reasoning") != "LLM调用失败，使用默认分析":
                    print(f"\n[6/7] 投资总监综合判断 ....... LLM推理完成")
                else:
                    print(f"\n[6/7] 投资总监综合判断 ....... 算法聚合完成")
                print(f"[7/7] 结果生成 ............... 完成")

            elif node_name == "risk_manager":
                risk_output = update.get("data", {}).get("risk_manager_output", {})
                print(f"\n[5/7] 风险控制评估 ........... 完成")
                print_risk_manager(risk_output)

            else:
                # Specialist agent completed
                signals = update.get("data", {}).get("analyst_signals", {})
                for agent_id, payload in list(signals.items()):
                    if agent_id not in accumulated and code in payload:
                        accumulated[agent_id] = True
                        all_signals.setdefault(agent_id, payload)
                        print_agent_brief(agent_id, payload[code])

    # Step 7: Final report
    print_header(code, name)
    print_composite(composite)
    print_summary_table(all_signals, composite, risk_output, code)

    if args.save:
        md_path = save_report(code, name, all_signals, composite, risk_output)
        print(f"\n[已保存报告] {md_path}")

    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":
    main()
