"""Multi-factor strategy backtest engine.

Usage:
    from tdx_core.backtest import BacktestEngine, StrategyConfig

    config = StrategyConfig.from_json("strategies/trend_momentum.json")
    engine = BacktestEngine(config)
    result = engine.run(start_date="2024-01-01", end_date="2025-12-31")
    print(result.metrics.format_report())
"""

from __future__ import annotations

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

# Ensure project root is on path for importing scripts.technical_master
ROOT = str(Path(__file__).resolve().parent.parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicators, TdxQuery, get_name, get_meta
from tdx_core.metadata import by_board, by_level1, by_level2, filter_stocks

from .metrics import PerformanceMetrics, calculate_metrics
from .portfolio import Portfolio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indicator name -> column name mapping
# ---------------------------------------------------------------------------

_INDICATOR_COLUMN_MAP = {
    "rsi": "rsi_14",
    "macd": "macd",
    "macd_signal": "macd_signal",
    "macd_hist": "macd_hist",
    "bollinger": "bb_pctb",
    "atr": "atr_14",
    "adx": "adx",
    "cci": "cci_20",
    "stochastic": "stoch_k",
    "stochrsi": "stochrsi_k",
    "williams_r": "williams_r_14",
    "mfi": "mfi_14",
    "obv": "obv",
    "cmf": "cmf_20",
    "ema": "ema_12",
    "ma": "ma_5",
    "sar": "sar",
    "supertrend": "supertrend",
    "std_dev": "std_dev_20",
    "roc": "roc_12",
    "momentum": "momentum_10",
    "volume_roc": "volume_roc_12",
    "force_index": "force_index_13",
    "ease_of_movement": "eom_14",
    "ultimate_oscillator": "ultimate_oscillator",
    "awesome_oscillator": "awesome_oscillator",
    "trix": "trix",
    "aroon": "aroon_up",
    "vortex": "vortex_vi_plus",
    "donchian": "donchian_upper",
    "keltner": "keltner_upper",
    "ichimoku": "ichimoku_conversion",
    "pivot_points": "pivot_pp",
    "td_sequential": "td_setup",
    "chaikin_volatility": "chaikin_volatility",
    "nv_i": "nvi",
    "ad_line": "ad_line",
    "vw_ap": "vwap",
}


def _indicator_to_column(name: str) -> str:
    """Map indicator name to DataFrame column name."""
    return _INDICATOR_COLUMN_MAP.get(name, name)


# ---------------------------------------------------------------------------
# Strategy configuration
# ---------------------------------------------------------------------------


@dataclass
class StrategyConfig:
    """Parsed strategy configuration."""

    name: str = "Untitled Strategy"
    description: str = ""
    universe: dict = field(default_factory=dict)
    lookback: int = 120
    initial_capital: float = 1_000_000.0
    position: dict = field(default_factory=dict)
    entry: dict = field(default_factory=dict)
    exit: dict = field(default_factory=dict)
    rebalance: dict = field(default_factory=dict)
    costs: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> "StrategyConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**{k: data.get(k, v) for k, v in cls().__dict__.items()})

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyConfig":
        return cls(**{k: data.get(k, v) for k, v in cls().__dict__.items()})

    def __post_init__(self):
        # Defaults
        self.position = {**{"max_holding": 10, "per_position": 0.1, "weight_by": "equal"}, **self.position}
        self.costs = {
            **{"commission_buy": 0.00025, "commission_sell": 0.00025, "tax_sell": 0.001, "slippage": 0.0001},
            **self.costs,
        }
        self.rebalance = {**{"frequency": "daily"}, **self.rebalance}
        # Normalize entry/exit: accept list of conditions or dict
        if isinstance(self.entry, list):
            self.entry = {"conditions": self.entry, "rank_by": "composite_score", "direction": "desc"}
        if not self.entry:
            self.entry = {"conditions": [], "rank_by": "composite_score", "direction": "desc"}
        if isinstance(self.exit, list):
            self.exit = {"conditions": self.exit, "stop_loss": None, "take_profit": None, "max_hold_days": None}
        if not self.exit:
            self.exit = {"conditions": [], "stop_loss": None, "take_profit": None, "max_hold_days": None}


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Run a multi-factor strategy backtest."""

    def __init__(self, config: StrategyConfig, max_workers: int = 8):
        self.config = config
        self.max_workers = max_workers
        self.universe_codes: list[str] = []
        self.data_cache: dict[str, pd.DataFrame] = {}  # code -> full_df with indicators

    # ─── Universe selection ───

    def _get_universe(self) -> list[str]:
        """Get stock codes based on strategy universe config."""
        u = self.config.universe
        codes: set[str] = set()

        if u.get("board"):
            codes.update(by_board(u["board"]))
        if u.get("level1"):
            codes.update(by_level1(u["level1"]))
        if u.get("level2"):
            codes.update(by_level2(u["level2"]))
        if u.get("codes"):
            codes.update(str(c).strip() for c in u["codes"].split(",") if c.strip())

        if not codes:
            # Default: all available stocks from metadata
            from tdx_core.metadata import _load
            codes = set(_load().keys())

        # Apply filters
        min_price = u.get("min_price")
        max_price = u.get("max_price")
        exclude_st = u.get("exclude_st", False)

        result = []
        explicit_codes = u.get("codes")
        for code in sorted(codes):
            meta = get_meta(code)
            if not meta:
                # If codes are explicitly specified (e.g. ETF), keep them even without metadata
                if explicit_codes and code in str(explicit_codes):
                    result.append(code)
                continue
            if exclude_st and ("ST" in meta.get("name", "") or "*ST" in meta.get("name", "")):
                continue
            # Price filter will be applied later with data
            result.append(code)

        return result

    # ─── Data preloading ───

    def _preload_data(self, start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
        """Fetch and compute indicators for all universe stocks."""
        codes = self.universe_codes
        if not codes:
            return {}

        lookback = self.config.lookback
        # Need extra history for indicator warm-up (250 for long-term MA + buffer)
        warmup_days = max(lookback, 250) + 260

        cache: dict[str, pd.DataFrame] = {}

        def _fetch_one(code: str) -> tuple[str, Optional[pd.DataFrame]]:
            try:
                with TdxQuery() as q:
                    df = q.get_daily(code)
                    if df is None or df.empty:
                        return code, None
                    df = df.sort_values("trade_date").reset_index(drop=True)
                    # Ensure float
                    for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
                        if col in df.columns:
                            df[col] = df[col].astype(float)

                    # Ensure trade_date is string for comparison
                    df["trade_date"] = df["trade_date"].astype(str)

                    # Calculate the earliest date we need (start_date - warmup buffer)
                    from datetime import datetime, timedelta
                    try:
                        start_dt = datetime.strptime(str(start_date), "%Y-%m-%d")
                        earliest_needed = (start_dt - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
                    except Exception:
                        earliest_needed = None

                    # Trim to needed range + warm-up, instead of just last N days
                    if earliest_needed:
                        df = df[df["trade_date"] >= earliest_needed].copy()
                    if len(df) < lookback + 10:
                        return code, None

                    # Compute all indicators
                    df = TdxIndicators.compute(df, indicators=None)  # all
                    # Ensure trade_date stays as string after compute
                    df["trade_date"] = df["trade_date"].astype(str)
                    return code, df
            except Exception as exc:
                logger.debug("Failed to fetch %s: %s", code, exc)
                return code, None

        print(f"数据预加载: {len(codes)} 只股票 (lookback={lookback}, workers={self.max_workers})...")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_fetch_one, c): c for c in codes}
            done = 0
            for future in as_completed(futures):
                code, df = future.result()
                done += 1
                if df is not None:
                    cache[code] = df
                if done % 100 == 0 or done == len(codes):
                    print(f"  {done}/{len(codes)} 已加载, {len(cache)} 成功")

        print(f"数据预加载完成: {len(cache)}/{len(codes)} 只股票")
        return cache

    # ─── Scoring ───

    def _calc_score(self, code: str, df_window: pd.DataFrame) -> dict[str, float]:
        """Calculate composite score for a stock window."""
        try:
            # Import here to avoid circular issues
            from scripts.technical_master import calc_period_scores

            scores, _ = calc_period_scores(df_window)
            return scores
        except Exception as exc:
            logger.debug("Score calc failed for %s: %s", code, exc)
            return {}

    # ─── Condition evaluation ───

    def _eval_conditions(self, conditions: list[dict], df: pd.DataFrame, scores: dict) -> bool:
        """Evaluate if all entry/exit conditions are met."""
        if not conditions:
            return True

        for cond in conditions:
            indicator = cond.get("indicator", "")
            op = cond.get("op", "==")
            value = cond.get("value")
            signal_type = cond.get("signal")

            # Special: composite_score comes from scores dict
            if indicator == "composite_score":
                actual = scores.get("composite", scores.get("total", scores.get("overall", None)))
                if actual is None:
                    return False
            elif indicator == "trend_score":
                actual = scores.get("trend", None)
                if actual is None:
                    return False
            elif indicator == "momentum_score":
                actual = scores.get("momentum", None)
                if actual is None:
                    return False
            elif indicator == "volatility_score":
                actual = scores.get("volatility", None)
                if actual is None:
                    return False
            elif indicator == "volume_score":
                actual = scores.get("volume", None)
                if actual is None:
                    return False
            else:
                # Raw indicator column — map common indicator names to column names
                col = _indicator_to_column(indicator)
                if col not in df.columns:
                    return False
                actual = df[col].iloc[-1]

            # Signal-based condition (e.g. macd golden_cross)
            if signal_type:
                try:
                    from tdx_core.analyzer import INDICATOR_PROFILES
                    profile = INDICATOR_PROFILES.get(indicator)
                    if profile and signal_type in profile.signals:
                        detector = profile.signals[signal_type]
                        mask = detector(df, {})
                        if not mask.iloc[-1]:
                            return False
                        continue
                except Exception:
                    return False

            # Value comparison
            if actual is None or pd.isna(actual):
                return False

            # Support column-to-column comparison (e.g. ma_20 > ma_60)
            if isinstance(value, str) and value in df.columns:
                value = df[value].iloc[-1]
                if pd.isna(value):
                    return False

            if op == ">=" and not (actual >= value):
                return False
            elif op == ">" and not (actual > value):
                return False
            elif op == "<=" and not (actual <= value):
                return False
            elif op == "<" and not (actual < value):
                return False
            elif op == "==" and not (actual == value):
                return False
            elif op == "!=" and not (actual != value):
                return False

        return True

    # ─── Main loop ───

    def run(self, start_date: str, end_date: str, benchmark_code: str | None = None) -> "BacktestResult":
        """Run the backtest with optional benchmark."""
        config = self.config

        # 1. Universe
        self.universe_codes = self._get_universe()
        print(f"股票池: {len(self.universe_codes)} 只股票")

        # 2. Preload data
        self.data_cache = self._preload_data(start_date, end_date)
        if not self.data_cache:
            raise RuntimeError("回测数据加载失败")

        # 2.5 Preload benchmark
        benchmark_prices: dict[str, float] = {}
        if benchmark_code:
            try:
                with TdxQuery() as q:
                    df_bench = q.get_daily(benchmark_code)
                    if df_bench is not None and not df_bench.empty:
                        df_bench = df_bench.sort_values("trade_date").reset_index(drop=True)
                        df_bench["trade_date"] = df_bench["trade_date"].astype(str)
                        df_bench["close_val"] = df_bench["close_val"].astype(float)
                        mask = (df_bench["trade_date"] >= start_date) & (df_bench["trade_date"] <= end_date)
                        sub = df_bench[mask]
                        if not sub.empty:
                            first_price = float(sub["close_val"].iloc[0])
                            for _, row in sub.iterrows():
                                benchmark_prices[str(row["trade_date"])] = float(row["close_val"]) / first_price * config.initial_capital
                            print(f"基准指数: {benchmark_code} ({len(benchmark_prices)} 天)")
            except Exception as exc:
                print(f"基准数据加载失败 ({benchmark_code}): {exc}")
                benchmark_prices = {}

        # 3. Build trading calendar from data
        all_dates = set()
        for df in self.data_cache.values():
            mask = (df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)
            all_dates.update(df.loc[mask, "trade_date"].tolist())
        trading_days = sorted(all_dates)
        if not trading_days:
            raise RuntimeError(f"{start_date} 到 {end_date} 之间没有交易日")
        print(f"交易日: {len(trading_days)} 天 ({trading_days[0]} ~ {trading_days[-1]})")

        # 4. Initialize portfolio
        portfolio = Portfolio(initial_capital=config.initial_capital)
        lookback = config.lookback
        max_holding = config.position["max_holding"]
        per_position = config.position["per_position"]

        costs = config.costs
        commission_buy = costs["commission_buy"]
        commission_sell = costs["commission_sell"]
        tax_sell = costs["tax_sell"]
        slippage = costs["slippage"]

        exit_cfg = config.exit
        stop_loss = exit_cfg.get("stop_loss")
        take_profit = exit_cfg.get("take_profit")
        max_hold_days = exit_cfg.get("max_hold_days")
        trailing_stop = exit_cfg.get("trailing_stop")

        # 5. Day-by-day simulation
        print("开始回测...")
        for idx, date in enumerate(trading_days):
            # --- Update prices ---
            prices = {}
            for code, df in self.data_cache.items():
                row = df[df["trade_date"] == date]
                if not row.empty:
                    prices[code] = float(row["close_val"].iloc[-1])
            portfolio.update_prices(prices, date)

            # --- Check exits (stop loss, take profit, trailing stop, max hold) ---
            sell_codes = set()
            if stop_loss is not None:
                sell_codes.update(portfolio.check_stop_loss(stop_loss))
            if take_profit is not None:
                sell_codes.update(portfolio.check_take_profit(take_profit))
            if trailing_stop is not None:
                sell_codes.update(portfolio.check_trailing_stop(trailing_stop))
            if max_hold_days is not None:
                sell_codes.update(portfolio.check_max_hold_days(max_hold_days, date))

            # Exit conditions from signals
            for code in list(portfolio.positions.keys()):
                if code in sell_codes:
                    continue
                df_full = self.data_cache.get(code)
                if df_full is None:
                    continue
                # Get window up to current date
                window_mask = df_full["trade_date"] <= date
                df_window = df_full[window_mask]
                if len(df_window) < lookback:
                    continue
                df_window = df_window.iloc[-lookback:].copy()
                scores = self._calc_score(code, df_window)
                exit_conds = config.exit.get("conditions", [])
                if exit_conds and self._eval_conditions(exit_conds, df_window, scores):
                    sell_codes.add(code)

            # Execute sells (T+1: cannot sell same-day purchases)
            for code in sell_codes:
                if code not in prices:
                    continue
                pos = portfolio.positions.get(code)
                if pos is None:
                    continue
                if pos.entry_date == date:
                    continue  # T+1 rule
                reason = "signal"
                if code in portfolio.check_stop_loss(stop_loss or -1):
                    reason = "stop_loss"
                elif code in portfolio.check_take_profit(take_profit or 0):
                    reason = "take_profit"
                elif code in portfolio.check_trailing_stop(trailing_stop or 0):
                    reason = "trailing_stop"
                elif code in portfolio.check_max_hold_days(max_hold_days or 9999, date):
                    reason = "max_hold"
                portfolio.sell(
                    code, prices[code], date,
                    commission_rate=commission_sell,
                    tax_rate=tax_sell,
                    slippage_rate=slippage,
                    reason=reason,
                )

            # --- Select new entries ---
            candidates = []
            for code, df_full in self.data_cache.items():
                # Skip if already held
                if code in portfolio.positions:
                    continue
                # Skip if no price today
                if code not in prices:
                    continue
                # Price filter
                price = prices[code]
                u = config.universe
                if u.get("min_price") and price < u["min_price"]:
                    continue
                if u.get("max_price") and price > u["max_price"]:
                    continue

                # Get window
                window_mask = df_full["trade_date"] <= date
                df_window = df_full[window_mask]
                if len(df_window) < lookback:
                    continue
                df_window = df_window.iloc[-lookback:].copy()

                scores = self._calc_score(code, df_window)
                if self._eval_conditions(config.entry.get("conditions", []), df_window, scores):
                    # Determine ranking value
                    rank_by = config.entry.get("rank_by", "composite_score")
                    rank_value = 0.0
                    if rank_by == "composite_score":
                        rank_value = scores.get("composite", scores.get("total", 0))
                    elif rank_by in scores:
                        rank_value = scores[rank_by]
                    elif rank_by in df_window.columns:
                        rank_value = df_window[rank_by].iloc[-1]
                    candidates.append((code, rank_value, scores, price))

            # Sort and select top N
            direction = config.entry.get("direction", "desc")
            reverse = direction == "desc"
            candidates.sort(key=lambda x: x[1], reverse=reverse)
            limit = config.entry.get("limit", max_holding)

            # Calculate target number of positions
            current_count = len(portfolio.positions)
            slots = max_holding - current_count
            if slots <= 0:
                pass  # No room
            else:
                to_buy = candidates[:slots]
                # Allocate cash
                total_cash_for_new = portfolio.cash * 0.99  # Reserve some cash
                per_alloc = min(
                    total_cash_for_new / max(len(to_buy), 1),
                    portfolio.total_value() * per_position,
                )
                for code, rank_val, scores, price in to_buy:
                    if per_alloc <= 0:
                        break
                    name = get_name(code) or code
                    success = portfolio.buy(
                        code, name, price, per_alloc, date,
                        commission_rate=commission_buy,
                        slippage_rate=slippage,
                        reason="entry",
                    )
                    if not success:
                        continue

            # --- Record NAV ---
            bench_val = benchmark_prices.get(date, 0.0)
            portfolio.record_nav(date, benchmark_value=bench_val)

            if (idx + 1) % 50 == 0 or idx == len(trading_days) - 1:
                print(f"  第 {idx+1}/{len(trading_days)} 天 | 净值: {portfolio.total_value():,.0f} | 持仓: {len(portfolio.positions)}")

        # 6. Calculate metrics
        metrics = calculate_metrics(
            portfolio.daily_records,
            portfolio.trades,
            config.initial_capital,
        )

        return BacktestResult(
            config=config,
            metrics=metrics,
            portfolio=portfolio,
            trading_days=trading_days,
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    """Result of a backtest run."""

    config: StrategyConfig
    metrics: PerformanceMetrics
    portfolio: Portfolio
    trading_days: list[str]

    def summary_text(self) -> str:
        lines = []
        lines.append(f"策略名称: {self.config.name}")
        lines.append(f"策略描述: {self.config.description}")
        lines.append("")
        lines.append(self.metrics.format_report())
        lines.append("")
        lines.append(f"完整交易次数 (买卖各算一笔): {len(self.portfolio.trades)}")
        lines.append(f"每日净值记录: {len(self.portfolio.daily_records)} 条")
        return "\n".join(lines)

    def trade_log(self) -> pd.DataFrame:
        """Return trade log as DataFrame."""
        rows = []
        for t in self.portfolio.trades:
            rows.append({
                "code": t.code,
                "name": t.name,
                "direction": t.direction,
                "date": t.date,
                "price": t.price,
                "shares": t.shares,
                "amount": t.amount,
                "commission": t.commission,
                "tax": t.tax,
                "reason": t.reason,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "hold_days": t.hold_days,
            })
        return pd.DataFrame(rows)

    def nav_df(self) -> pd.DataFrame:
        """Return daily NAV as DataFrame."""
        return pd.DataFrame(self.portfolio.daily_records)
