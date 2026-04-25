#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TradingAgentsV2 统一 CLI 入口.

Usage:
    tdx --help
    tdx signal --code 515180 --save
    tdx analyze --code 688018 --bars 120
    tdx backtest --code 515180 --strategy rsi30_bounce
    tdx task register
    tdx task check --today
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent.parent


def _run_script(script_name: str, args: list[str]):
    """通过 subprocess 安全调用现有脚本."""
    cmd = [sys.executable, str(ROOT / "scripts" / script_name)] + args
    result = subprocess.run(cmd, capture_output=False, text=True)
    sys.exit(result.returncode)


# ═══════════════════════════════════════════════════════════════════════════
# 主命令组
# ═══════════════════════════════════════════════════════════════════════════

@click.group()
@click.version_option(version="0.2.0", prog_name="tdx")
def cli():
    """TradingAgentsV2 — A股技术分析与策略回测 CLI.

    支持信号跟踪、技术分析、策略回测、市场扫描、定时任务管理等功能。
    """
    pass


# ═══════════════════════════════════════════════════════════════════════════
# signal — 交易信号
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--code", "-c", required=True, help="股票/ETF 代码，如 515180")
@click.option("--strategy", "-s", default="rsi30_bounce",
              type=click.Choice(["rsi30_bounce", "macd_golden", "bollinger_bounce", "trend_follow"]),
              help="策略名称")
@click.option("--rsi-buy", type=float, default=30, help="RSI 买入阈值 (仅 RSI 策略)")
@click.option("--rsi-sell", type=float, default=70, help="RSI 卖出阈值 (仅 RSI 策略)")
@click.option("--save", is_flag=True, help="保存报告到 reports/")
def signal(code: str, strategy: str, rsi_buy: float, rsi_sell: float, save: bool):
    """生成交易信号报告 (BUY/SELL/HOLD + 强度分级 + 仓位建议)."""
    sys.path.insert(0, str(ROOT))
    from scripts.signal_tracker import build_report

    params = {}
    if strategy == "rsi30_bounce":
        params = {"rsi_buy": rsi_buy, "rsi_sell": rsi_sell}

    build_report(code, strategy, params, save=save)


# ═══════════════════════════════════════════════════════════════════════════
# analyze — 技术分析
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--code", "-c", required=True, help="股票代码，如 688018")
@click.option("--bars", "-b", default=60, help="分析周期（天数）")
@click.option("--save", is_flag=True, help="保存报告到 reports/")
def analyze(code: str, bars: int, save: bool):
    """37 指标全量技术分析大师报告."""
    args = [code, "--bars", str(bars)]
    if save:
        args.append("--save")
    _run_script("technical_master.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# backtest — 策略回测
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--strategy", "-s", required=True, help="策略 JSON 文件路径或内置模板名")
@click.option("--codes", help="逗号分隔的股票代码，覆盖策略中的标的")
@click.option("--start", default="2021-08-02", help="回测起始日期 (YYYY-MM-DD)")
@click.option("--end", help="回测结束日期，默认今天")
@click.option("--save", is_flag=True, help="保存报告")
def backtest(strategy: str, codes: str | None, start: str, end: str | None, save: bool):
    """策略回测 — 验证策略在历史数据上的表现."""
    args = ["--strategy", strategy, "--start", start]
    if codes:
        args.extend(["--codes", codes])
    if end:
        args.extend(["--end", end])
    if save:
        args.append("--save")
    _run_script("strategy_backtest.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# scan — 市场扫描
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--codes", "-c", required=True, help="逗号分隔的股票代码")
@click.option("--indicator", "-i", required=True, help="指标名，如 macd")
@click.option("--signal", "-s", help="信号类型，如 golden_cross")
@click.option("--save", is_flag=True, help="保存报告")
def scan(codes: str, indicator: str, signal: str | None, save: bool):
    """扫描多只股票的技术指标信号."""
    args = [codes, "--indicator", indicator]
    if signal:
        args.extend(["--signal", signal])
    if save:
        args.append("--save")
    _run_script("scan_market.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# rank — 板块排名
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--board", "-b", default="创业板", help="板块名称")
@click.option("--bars", default=120, help="分析窗口天数")
@click.option("--top", "-n", default=100, help="输出 Top N")
@click.option("--save", is_flag=True, help="保存报告")
def rank(board: str, bars: int, top: int, save: bool):
    """板块全量股票技术分析排名."""
    args = ["--bars", str(bars), "--top", str(top)]
    if save:
        args.append("--save")
    _run_script("rank_growth_board.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# etf — ETF 跟踪
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--code", "-c", default="515180", help="ETF 代码")
@click.option("--strategy", "-s", default="longterm",
              type=click.Choice(["longterm", "volatility"]),
              help="跟踪策略类型")
@click.option("--bars", default=120, help="分析周期")
@click.option("--save", is_flag=True, help="保存报告")
def etf(code: str, strategy: str, bars: int, save: bool):
    """ETF 长期跟踪策略报告."""
    if strategy == "longterm":
        args = ["--code", code, "--bars", str(bars)]
        if save:
            args.append("--save")
        _run_script("etf_longterm_tracker.py", args)
    else:
        args = ["--code", code, "--bars", str(bars)]
        if save:
            args.append("--save")
        _run_script("etf_volatility_strategy.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# task — 定时任务管理（子命令组）
# ═══════════════════════════════════════════════════════════════════════════

@cli.group()
def task():
    """Claw 定时任务管理."""
    pass


@task.command("register")
def task_register():
    """注册所有启用的定时任务到 Windows Task Scheduler."""
    _run_script("claw_register.py", ["--register"])


@task.command("list")
def task_list():
    """列出所有定时任务及其注册状态."""
    _run_script("claw_register.py", ["--list"])


@task.command("reload")
def task_reload():
    """重新加载配置并更新所有定时任务."""
    _run_script("claw_register.py", ["--reload"])


@task.command("remove")
@click.option("--name", "-n", required=True, help="任务名称")
def task_remove(name: str):
    """删除指定定时任务."""
    _run_script("claw_register.py", ["--remove", name])


@task.command("remove-all")
def task_remove_all():
    """删除所有 TradingAgentsV2 定时任务."""
    _run_script("claw_register.py", ["--remove-all"])


@task.command("check")
@click.option("--today", is_flag=True, help="查看今日所有报告")
@click.option("--task", "-t", help="查看指定任务的最近报告")
@click.option("--latest", "-n", type=int, help="查看最近 N 条报告")
def task_check(today: bool, task: str | None, latest: int | None):
    """查询定时任务执行结果和报告."""
    if today:
        _run_script("claw_check.py", ["--today"])
    elif task:
        args = ["--task", task]
        if today:
            args.append("--today")
        _run_script("claw_check.py", args)
    elif latest:
        _run_script("claw_check.py", ["--latest", str(latest)])
    else:
        click.echo("请指定 --today, --task 或 --latest")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# sync — 数据同步
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--full", is_flag=True, help="全量导入（默认增量）")
@click.option("--market", multiple=True, help="指定市场: sh sz bj ds")
@click.option("--force", is_flag=True, help="强制重跑，忽略变更检测")
@click.option("--workers", default=4, help="并行线程数")
def sync(full: bool, market: tuple[str, ...], force: bool, workers: int):
    """通达信数据同步到 MySQL."""
    args = ["--workers", str(workers)]
    if full:
        args.append("--full")
    if force:
        args.append("--force")
    if market:
        args.extend(["--market"] + list(market))
    _run_script("tdx_sync.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# export — MySQL → SQLite 导出
# ═══════════════════════════════════════════════════════════════════════════

@cli.command()
@click.option("--output", "-o", default="data/tdx_data.db", help="输出 SQLite 文件路径")
@click.option("--skip-verify", is_flag=True, help="跳过导出后验证")
def export(output: str, skip_verify: bool):
    """将 MySQL 全量数据导出为 SQLite 文件."""
    args = ["--output", output]
    if skip_verify:
        args.append("--skip-verify")
    _run_script("export_mysql_to_sqlite.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# sync-api — minishare API 同步到本地数据库
# ═══════════════════════════════════════════════════════════════════════════

@cli.command("sync-api")
@click.option("--codes", help="逗号分隔的股票代码")
@click.option("--watchlist", help="代码列表文件路径")
@click.option("--all-shsz", is_flag=True, help="同步本地数据库中全部沪深代码")
@click.option("--etf-only", is_flag=True, help="仅同步 ETF")
@click.option("--mode", default="daily", help="daily=rt_k_ms, intraday=rt_min_daily聚合")
@click.option("--dry-run", is_flag=True, help="预览不写入")
@click.option("--verbose", "-v", is_flag=True, help="详细日志")
def sync_api(codes: str | None, watchlist: str | None, all_shsz: bool,
             etf_only: bool, mode: str, dry_run: bool, verbose: bool):
    """从 minishare API 同步实时数据到本地数据库."""
    args = ["--mode", mode]
    if codes:
        args.extend(["--codes", codes])
    if watchlist:
        args.extend(["--watchlist", watchlist])
    if all_shsz:
        args.append("--all-shsz")
    if etf_only:
        args.append("--etf-only")
    if dry_run:
        args.append("--dry-run")
    if verbose:
        args.append("--verbose")
    _run_script("sync_minishare.py", args)


# ═══════════════════════════════════════════════════════════════════════════
# list-indicators / list-strategies
# ═══════════════════════════════════════════════════════════════════════════

@cli.command("list-indicators")
def list_indicators():
    """列出所有可用的技术指标."""
    _run_script("list_indicators.py", [])


@cli.command("list-strategies")
def list_strategies():
    """列出所有可用的策略模板."""
    from tdx_core.indicators import TdxIndicators
    indicators = TdxIndicators.available_indicators()
    click.echo(f"可用指标 ({len(indicators)} 个):")
    for i, name in enumerate(indicators, 1):
        click.echo(f"  {i:2d}. {name}")


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cli()
