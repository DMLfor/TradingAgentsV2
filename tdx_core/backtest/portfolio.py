"""Portfolio simulation: positions, cash, and trade execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class Position:
    """A single stock position."""

    code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    current_price: float = 0.0
    highest_price: float = 0.0
    lowest_price_since_entry: float = 0.0

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.shares * (self.current_price - self.entry_price)

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

    def update_price(self, price: float):
        self.current_price = price
        if price > self.highest_price:
            self.highest_price = price
        if price < self.lowest_price_since_entry:
            self.lowest_price_since_entry = price


@dataclass
class Trade:
    """A completed trade record."""

    code: str
    name: str
    direction: str  # "BUY" or "SELL"
    date: str
    price: float
    shares: int
    amount: float
    commission: float
    tax: float = 0.0
    slippage: float = 0.0
    reason: str = ""  # e.g., "entry", "stop_loss", "take_profit", "max_hold", "signal"
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    hold_days: Optional[int] = None


@dataclass
class Portfolio:
    """Simulated portfolio with cash and stock positions."""

    initial_capital: float
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    daily_records: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.cash = self.initial_capital

    # ── Price updates ──

    def update_prices(self, prices: dict[str, float], date: str):
        """Update current prices for all positions."""
        for code, pos in self.positions.items():
            if code in prices:
                pos.update_price(prices[code])

    # ── Buy / Sell ──

    def buy(
        self,
        code: str,
        name: str,
        price: float,
        target_amount: float,
        date: str,
        commission_rate: float = 0.00025,
        slippage_rate: float = 0.0001,
        reason: str = "entry",
    ) -> bool:
        """Buy a stock. Returns True if successful."""
        if target_amount <= 0 or target_amount > self.cash:
            return False

        # A-shares: lot size = 100
        raw_shares = int(target_amount / price)
        shares = (raw_shares // 100) * 100
        if shares < 100:
            return False

        fill_price = price * (1 + slippage_rate)
        amount = shares * fill_price
        commission = max(5.0, amount * commission_rate)  # min commission 5 yuan
        total_cost = amount + commission

        if total_cost > self.cash:
            # Try to reduce shares
            max_shares = int(self.cash / fill_price / (1 + commission_rate))
            shares = (max_shares // 100) * 100
            if shares < 100:
                return False
            amount = shares * fill_price
            commission = max(5.0, amount * commission_rate)
            total_cost = amount + commission

        self.cash -= total_cost
        pos = Position(
            code=code,
            name=name,
            entry_date=date,
            entry_price=fill_price,
            shares=shares,
            current_price=fill_price,
            highest_price=fill_price,
            lowest_price_since_entry=fill_price,
        )
        self.positions[code] = pos

        self.trades.append(
            Trade(
                code=code,
                name=name,
                direction="BUY",
                date=date,
                price=round(fill_price, 3),
                shares=shares,
                amount=round(amount, 2),
                commission=round(commission, 2),
                slippage=round(amount * slippage_rate, 2),
                reason=reason,
            )
        )
        return True

    def sell(
        self,
        code: str,
        price: float,
        date: str,
        commission_rate: float = 0.00025,
        tax_rate: float = 0.001,
        slippage_rate: float = 0.0001,
        reason: str = "exit",
    ) -> Optional[Trade]:
        """Sell a position. Returns the Trade record if successful."""
        if code not in self.positions:
            return None

        pos = self.positions[code]
        fill_price = price * (1 - slippage_rate)
        amount = pos.shares * fill_price
        commission = max(5.0, amount * commission_rate)
        tax = amount * tax_rate
        net_proceeds = amount - commission - tax

        self.cash += net_proceeds

        pnl = pos.shares * (fill_price - pos.entry_price) - commission - tax - (
            pos.shares * pos.entry_price * commission_rate  # approx buy commission
        )
        pnl_pct = pnl / (pos.shares * pos.entry_price) if pos.entry_price > 0 else 0

        # Calculate hold days
        try:
            hold_days = (pd.to_datetime(date) - pd.to_datetime(pos.entry_date)).days
        except Exception:
            hold_days = 0

        trade = Trade(
            code=code,
            name=pos.name,
            direction="SELL",
            date=date,
            price=round(fill_price, 3),
            shares=pos.shares,
            amount=round(amount, 2),
            commission=round(commission, 2),
            tax=round(tax, 2),
            slippage=round(amount * slippage_rate, 2),
            reason=reason,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 4),
            hold_days=hold_days,
        )
        self.trades.append(trade)
        del self.positions[code]
        return trade

    # ── Checks ──

    def check_stop_loss(self, stop_loss_pct: float) -> list[str]:
        """Return codes that hit stop loss."""
        if stop_loss_pct is None or stop_loss_pct >= 0:
            return []
        codes = []
        for code, pos in self.positions.items():
            if pos.unrealized_pnl_pct <= stop_loss_pct:
                codes.append(code)
        return codes

    def check_take_profit(self, take_profit_pct: float) -> list[str]:
        """Return codes that hit take profit."""
        if take_profit_pct is None or take_profit_pct <= 0:
            return []
        codes = []
        for code, pos in self.positions.items():
            if pos.unrealized_pnl_pct >= take_profit_pct:
                codes.append(code)
        return codes

    def check_trailing_stop(self, trailing_pct: float) -> list[str]:
        """Return codes that hit trailing stop."""
        if trailing_pct is None or trailing_pct <= 0:
            return []
        codes = []
        for code, pos in self.positions.items():
            if pos.highest_price <= pos.entry_price:
                continue
            # Trailing stop = highest - trailing_pct * (highest - entry)
            threshold = pos.highest_price * (1 - trailing_pct)
            if pos.current_price <= threshold:
                codes.append(code)
        return codes

    def check_max_hold_days(self, max_days: int, current_date: str) -> list[str]:
        """Return codes held longer than max_days."""
        if max_days is None or max_days <= 0:
            return []
        codes = []
        current_dt = pd.to_datetime(current_date)
        for code, pos in self.positions.items():
            try:
                hold_days = (current_dt - pd.to_datetime(pos.entry_date)).days
                if hold_days >= max_days:
                    codes.append(code)
            except Exception:
                continue
        return codes

    # ── NAV ──

    def total_value(self) -> float:
        """Total portfolio value (cash + positions)."""
        pos_value = sum(p.market_value for p in self.positions.values())
        return self.cash + pos_value

    def record_nav(self, date: str, benchmark_value: float = 0.0):
        """Record daily NAV."""
        self.daily_records.append(
            {
                "date": date,
                "cash": round(self.cash, 2),
                "position_value": round(
                    sum(p.market_value for p in self.positions.values()), 2
                ),
                "total_value": round(self.total_value(), 2),
                "num_positions": len(self.positions),
                "benchmark": round(benchmark_value, 2) if benchmark_value else None,
            }
        )
