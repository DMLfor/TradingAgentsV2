"""Performance metrics calculation for backtest results."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a backtest."""

    # Basic
    initial_capital: float = 0.0
    final_value: float = 0.0
    total_return: float = 0.0
    total_return_pct: float = 0.0
    annualized_return: float = 0.0

    # Risk
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_start: Optional[str] = None
    max_drawdown_end: Optional[str] = None
    volatility_annual: float = 0.0

    # Ratios
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Trades
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    avg_return_per_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Duration
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    trading_days: int = 0

    # Benchmark
    benchmark_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0

    # Series
    nav_series: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    trade_returns: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Export metrics as a flat dictionary (JSON-safe)."""
        def _cast(v):
            if isinstance(v, (np.integer, np.int64, np.int32)):
                return int(v)
            if isinstance(v, (np.floating, np.float64, np.float32)):
                return float(v)
            return v
        return {
            "initial_capital": _cast(self.initial_capital),
            "final_value": _cast(self.final_value),
            "total_return_pct": round(float(self.total_return_pct), 2),
            "annualized_return": round(float(self.annualized_return), 2),
            "max_drawdown_pct": round(float(self.max_drawdown_pct), 2),
            "volatility_annual": round(float(self.volatility_annual), 2),
            "sharpe_ratio": round(float(self.sharpe_ratio), 2),
            "sortino_ratio": round(float(self.sortino_ratio), 2),
            "calmar_ratio": round(float(self.calmar_ratio), 2),
            "total_trades": int(self.total_trades),
            "win_trades": int(self.win_trades),
            "loss_trades": int(self.loss_trades),
            "win_rate": round(float(self.win_rate), 2),
            "avg_return_per_trade": round(float(self.avg_return_per_trade), 2),
            "avg_win": round(float(self.avg_win), 2),
            "avg_loss": round(float(self.avg_loss), 2),
            "profit_factor": round(float(self.profit_factor), 2),
            "largest_win": round(float(self.largest_win), 2),
            "largest_loss": round(float(self.largest_loss), 2),
            "trading_days": int(self.trading_days),
            "benchmark_return": round(float(self.benchmark_return), 2),
            "alpha": round(float(self.alpha), 2),
            "beta": round(float(self.beta), 2),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "max_drawdown_start": self.max_drawdown_start,
            "max_drawdown_end": self.max_drawdown_end,
        }

    def format_report(self) -> str:
        """Format metrics as a human-readable report (Chinese)."""
        lines = []
        lines.append("=" * 70)
        lines.append("  策略回测绩效报告")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"  回测区间:         {self.start_date} ~ {self.end_date} ({self.trading_days} 个交易日)")
        lines.append(f"  初始资金:         {self.initial_capital:,.0f}")
        lines.append(f"  期末净值:         {self.final_value:,.0f}")
        lines.append("")
        lines.append("  收益指标")
        lines.append(f"    总收益率:       {self.total_return_pct:+.2f}%")
        lines.append(f"    年化收益率:     {self.annualized_return:+.2f}%")
        lines.append(f"    基准收益率:     {self.benchmark_return:+.2f}%")
        lines.append("")
        lines.append("  风险指标")
        lines.append(f"    最大回撤:       {self.max_drawdown_pct:.2f}% ({self.max_drawdown_start} ~ {self.max_drawdown_end})")
        lines.append(f"    年化波动率:     {self.volatility_annual:.2f}%")
        lines.append("")
        lines.append("  风险调整收益")
        lines.append(f"    夏普比率:       {self.sharpe_ratio:.2f}")
        lines.append(f"    索提诺比率:     {self.sortino_ratio:.2f}")
        lines.append(f"    卡玛比率:       {self.calmar_ratio:.2f}")
        lines.append(f"    Alpha:          {self.alpha:.2f}")
        lines.append(f"    Beta:           {self.beta:.2f}")
        lines.append("")
        lines.append("  交易统计")
        lines.append(f"    总交易次数:     {self.total_trades}")
        lines.append(f"    盈利 / 亏损:    {self.win_trades} / {self.loss_trades}")
        lines.append(f"    胜率:           {self.win_rate:.1f}%")
        lines.append(f"    平均收益:       {self.avg_return_per_trade:+.2f}%")
        lines.append(f"    平均盈利:       {self.avg_win:+.2f}%")
        lines.append(f"    平均亏损:       {self.avg_loss:+.2f}%")
        lines.append(f"    盈亏比:         {self.profit_factor:.2f}")
        lines.append(f"    最大单笔盈利:   {self.largest_win:+.2f}%")
        lines.append(f"    最大单笔亏损:   {self.largest_loss:+.2f}%")
        lines.append("=" * 70)
        return "\n".join(lines)


def calculate_metrics(
    daily_records: list[dict],
    trades: list,
    initial_capital: float,
    risk_free_rate: float = 0.02,
) -> PerformanceMetrics:
    """Calculate all performance metrics from backtest results."""
    if not daily_records:
        return PerformanceMetrics()

    df = pd.DataFrame(daily_records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # NAV series
    nav = df["total_value"]
    returns = nav.pct_change().dropna()

    m = PerformanceMetrics()
    m.initial_capital = initial_capital
    m.final_value = nav.iloc[-1]
    m.total_return = m.final_value - m.initial_capital
    m.total_return_pct = (m.final_value / m.initial_capital - 1) * 100
    m.start_date = str(df["date"].iloc[0].date())
    m.end_date = str(df["date"].iloc[-1].date())
    m.trading_days = len(df)

    # Annualized return (trading days ≈ 252/year)
    years = m.trading_days / 252.0
    if years > 0 and m.initial_capital > 0:
        m.annualized_return = ((m.final_value / m.initial_capital) ** (1 / years) - 1) * 100

    # Max drawdown
    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax
    m.max_drawdown = drawdown.min()
    m.max_drawdown_pct = m.max_drawdown * 100
    dd_end_idx = drawdown.idxmin()
    if dd_end_idx is not None and dd_end_idx > 0:
        peak_before = cummax.iloc[: dd_end_idx + 1].idxmax()
        m.max_drawdown_start = str(df.loc[peak_before, "date"].date())
        m.max_drawdown_end = str(df.loc[dd_end_idx, "date"].date())

    # Volatility (annualized)
    if len(returns) > 1:
        m.volatility_annual = returns.std() * math.sqrt(252) * 100

    # Sharpe ratio
    excess_returns = returns - risk_free_rate / 252
    if m.volatility_annual > 0:
        m.sharpe_ratio = (excess_returns.mean() / returns.std()) * math.sqrt(252)

    # Sortino ratio
    downside = returns[returns < 0]
    downside_std = downside.std() if len(downside) > 0 else 0
    if downside_std > 0:
        m.sortino_ratio = (returns.mean() - risk_free_rate / 252) / downside_std * math.sqrt(252)

    # Calmar ratio
    if abs(m.max_drawdown_pct) > 0.01:
        m.calmar_ratio = m.annualized_return / abs(m.max_drawdown_pct)

    # Trade metrics
    trade_returns = []
    wins = []
    losses = []
    total_pnl = 0
    total_win_pnl = 0
    total_loss_pnl = 0

    for t in trades:
        if t.direction == "SELL" and t.pnl_pct is not None:
            trade_returns.append(t.pnl_pct)
            total_pnl += t.pnl_pct
            if t.pnl_pct > 0:
                wins.append(t.pnl_pct)
                total_win_pnl += t.pnl_pct
            else:
                losses.append(t.pnl_pct)
                total_loss_pnl += abs(t.pnl_pct)

    m.total_trades = len(trade_returns)
    m.win_trades = len(wins)
    m.loss_trades = len(losses)
    if m.total_trades > 0:
        m.win_rate = m.win_trades / m.total_trades * 100
        m.avg_return_per_trade = total_pnl / m.total_trades
    if wins:
        m.avg_win = sum(wins) / len(wins)
        m.largest_win = max(wins)
    if losses:
        m.avg_loss = sum(losses) / len(losses)
        m.largest_loss = min(losses)
    if total_loss_pnl > 0:
        m.profit_factor = total_win_pnl / total_loss_pnl

    m.trade_returns = trade_returns
    m.nav_series = nav

    # Benchmark (simple: if benchmark column exists)
    if "benchmark" in df.columns and df["benchmark"].notna().any():
        bench = df["benchmark"].dropna()
        if len(bench) > 1:
            m.benchmark_return = (bench.iloc[-1] / bench.iloc[0] - 1) * 100
            # Beta
            bench_returns = bench.pct_change().dropna()
            if len(returns) == len(bench_returns) and returns.std() > 0 and bench_returns.std() > 0:
                m.beta = returns.corr(bench_returns) * (returns.std() / bench_returns.std())
                # Alpha
                m.alpha = (
                    returns.mean() * 252 - risk_free_rate
                    - m.beta * (bench_returns.mean() * 252 - risk_free_rate)
                ) * 100

    return m
