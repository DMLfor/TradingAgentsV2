# TradingAgentsV2 Agent Instructions

## 红线：CLI 输出必须中文

**所有 CLI 脚本的终端输出必须使用中文。没有例外。**

包括：状态提示、报告标题、数据标签、保存确认、错误信息。日志文件内部可用英文，但面向用户的终端输出必须是中文。

适用：`scripts/` 下所有脚本、`tdx_core/backtest/` 下所有模块。**新增脚本默认中文输出。**

---

## Project Overview

Chinese A-share stock technical analysis system. Supports single-stock deep analysis (37 indicators), batch ranking, industry screening, ETF grid strategies, and multi-factor strategy backtesting.

- **Language**: Python 3.11
- **Database**: MySQL `tdx_data` (local 127.0.0.1:3306)
- **Data Source**: TongDaXin (TDX) daily/minute OHLCV data
- **OS**: Windows (PowerShell, GBK terminal encoding issues with emoji)

---

## Core Conventions

### 1. CLI Output Language (RED LINE)

**ALL CLI script terminal output MUST be in Chinese. NO EXCEPTIONS.**

| 类型 | 示例 |
|:---|:---|
| 状态提示 | "数据预加载中...", "回测完成", "第 50/83 天" |
| 报告标题 | "策略回测绩效报告", "收益指标", "风险指标", "交易统计" |
| 数据标签 | "初始资金", "夏普比率", "胜率", "最大回撤" |
| 保存确认 | "[已保存报告]", "[已保存指标]", "[已保存交易明细]" |
| 错误信息 | "[错误] 策略文件未找到", "回测数据加载失败" |

Log files may use English for programmatic parsing, but user-facing terminal output is **Chinese-only**.

Applies to: all scripts in `scripts/`, all modules in `tdx_core/backtest/`. **Default to Chinese for any new CLI script.**

### 2. Scripts / Skill Sync

`scripts/` directory is the physical implementation of the `stock-technical-analysis` skill.

| Scenario | Action |
|:---|:---|
| Modify `scripts/*.py` | Also copy to `.kimi/skills/stock-technical-analysis/scripts/` |
| Modify skill docs | Also update `SKILL.md` and `scripts/` |
| Add new script | Develop in `scripts/`, test, then copy to skill/scripts/ and update SKILL.md |

### 3. JSON Serialization Safety

Any `to_dict()` / `to_json()` / `json.dump()` data export MUST convert numpy types to native Python types BEFORE serialization.

```python
def _cast(v):
    if isinstance(v, (np.integer, np.int64, np.int32)):
        return int(v)
    if isinstance(v, (np.floating, np.float64, np.float32)):
        return float(v)
    return v
```

pandas Series/DataFrame aggregations (`.iloc[]`, `.sum()`, `.mean()`, `.std()`, `.shape`) return numpy scalars. Always test `json.dumps(obj)` before claiming JSON export works.

### 4. Decimal Type Fix

Database returns `decimal.Decimal`. `tdx_core.indicators.normalize_ohlcv` does NOT convert it to float. **Workaround**: Explicitly cast after fetching data:

```python
df = df[["open_val", "high_val", "low_val", "close_val", "volume", "amount"]].astype(float)
```

Do NOT modify `tdx_core` itself unless necessary (minimal intrusion principle).

---

## Architecture

```
scripts/                         # CLI scripts (canonical source)
  Data Pipeline (6):
    tdx_init_db.py               # Database init
    tdx_sync.py                  # Incremental/full data sync
    tdx_full_import.py           # One-time full import
    update_stock_metadata.py     # Build metadata JSON
    update_stock_names.py        # Build names JSON
    optimize_indexes.py          # MySQL index management
  Single Stock Analysis (3):
    technical_master.py          # 37-indicator deep analysis
    analyze_stock.py             # Single-stock indicator scan
    list_indicators.py           # List available indicators
  Batch Analysis (6):
    filter_stocks.py             # Industry/board screener
    scan_market.py               # Signal scanner
    rank_stocks.py               # Indicator-based ranking
    backtest_signal.py           # Signal backtester
    rank_growth_board.py         # Full-board batch ranking
    batch_analyze.py             # Custom batch analyzer
  ETF Strategy (2):
    etf_volatility_strategy.py   # ETF grid strategy
    etf_longterm_tracker.py      # ETF long-term tracker
  Strategy Backtest (1):
    strategy_backtest.py         # Multi-factor strategy backtest engine
  Pullback Screener (4):
    tech_screener.py             # 5-factor pullback stock picker + trade plan
    backtest_screener.py         # Historical backtest for screener strategy
    ablation_screener.py         # Batch ablation study (parallel)
    baseline_screener.py         # Random-buy baseline comparison
  Daily Market Review (1):
    daily_market_review.py       # Daily technical review: market/style/sector/sentiment/trend/volume-price/outlook/ETF/signals/picks/plan

tdx_core/                        # Python package
  cli.py                         # Unified CLI entry (Click, 14 subcommands incl. pick, review)
  backtest/                      # Backtest engine, portfolio sim, metrics
  indicators/                    # 37 technical indicators
  analyzer.py                    # Signal detection, single-signal backtest
  query.py                       # Database query interface
  metadata.py                    # Stock screening API

config/
  stock_metadata.json            # 5516 stocks with industry/board index
  stock_names.json               # Code-to-name mapping
  tdx_config.yaml                # MySQL connection, TDX path

strategies/                      # Strategy templates (JSON)
```

---

## Key Commands

### Unified CLI (`tdx`)

```bash
# 信号跟踪
tdx signal -c 515180 -s rsi30_bounce --save
tdx signal -c 159545 -s macd_golden --save

# 技术分析
tdx analyze -c 688018 -b 120 --save

# 板块排名
tdx rank --top 100 --save

# 市场扫描
tdx scan -c 000001,000002 -i macd -s golden_cross --save

# 策略回测
tdx backtest -s strategies/515180_rsi30_bounce.json --codes 515180 --save

# 数据同步
tdx sync
tdx sync --full --force --workers 8

# 定时任务
tdx task list
tdx task check --today
tdx task reload

# 形态选股
tdx pick --board 创业板 --min-score 55 --top 20 --save
tdx pick --codes 300750,300059 --min-score 55

# 辅助
tdx list-indicators
tdx list-strategies
tdx etf -c 515180 -s longterm --save
```

### Legacy Scripts (100% compatible)

```bash
# Data init (one-time)
python scripts/tdx_init_db.py
python scripts/update_stock_metadata.py
python scripts/tdx_sync.py --market sh sz

# Single stock analysis
python scripts/technical_master.py 688018 --bars 120 --save

# Batch ranking
python scripts/rank_growth_board.py --bars 120 --top 100 --save

# Strategy backtest
python scripts/strategy_backtest.py --template trend_momentum --board 创业板 --start 2024-01-01 --end 2025-12-31 --benchmark 399006 --plot --save

# ETF strategy
python scripts/etf_volatility_strategy.py --code 515180 --save
python scripts/etf_longterm_tracker.py --code 515180 --save

# Clear cache after modifying technical_master.py
Get-ChildItem -Path . -Filter __pycache__ -Recurse | Remove-Item -Recurse -Force
```

---

## Known Issues

| Issue | Status | Workaround |
|:---|:---:|:---|
| 北交所数据缺失 | Open | 920/83/87 codes not in `tdx_daily` |
| `batch_analyze.py` filename conflict | Open | Does not distinguish boards in output filenames |
| Single-stock vs batch scoring inconsistency | Open | `technical_master.py` uses absolute volatility; batch uses peer-relative |
| `scripts/` import from `tdx_core` | Fixed | `scripts/__init__.py` + smart ROOT detection |
| numpy JSON serialization | Fixed | Explicit `_cast()` in `to_dict()` |
| PowerShell profile errors | Ignored | Non-critical `Set-PSReadLineOption` errors on every command |

---

## Scoring Formula

```python
# Composite score = trend*0.35 + momentum*0.25 + (10-volatility)*0.15 + volume*0.25
# Volatility (batch mode) = peer percentile * 10.0
# Volatility (single mode) = 2.5 + abs(drawdown)/10 + ATR%*0.8 + BB bandwidth change*15
```

Score thresholds (recalibrated 2026-04-25):
- >= 7.8: 强烈偏多
- >= 7.0: 谨慎偏多
- >= 6.0: 中性偏强
- >= 5.0: 中性
- >= 4.0: 中性偏弱
- < 4.0: 谨慎偏空

---

## 515180 Strategy (Current State)

- **Score**: 5.8/10 [中性偏强]
- **Trend**: WEAK_UP (weak uptrend)
- **ATR percentile**: 8.5% (historically low, good for grid)
- **Price**: %B = 0.862, near upper Bollinger band
- **Grid**: Buy 14.150/14.019/13.887, Sell 14.414/14.545/14.677
- **Allocation**: Core 70% hold, Band 30% grid

**最优回测策略**: RSI30 反弹（RSI<30 买入，RSI>70 或持仓40天卖出），+71.38%，夏普1.48，最大回撤-7.35%，胜率80%（10笔交易）。

---

## 159545 策略分析 (2026-04-25)

- **标的**: 159545（恒生港股通高股息低波动ETF），2024-04-15上市，仅492天数据
- **趋势特征**: 港股红利，趋势性强于A股红利，MACD金叉策略最优
- **最优回测策略**: MACD金叉（+26.32%，夏普1.26），买入持有+18.98%
- **RSI均值回归策略效果差**: 因为趋势性强，超跌反弹机会少
- **RSI+威廉复合策略**: 条件太苛刻（RSI<35且威廉<-80），0交易，已淘汰

**当前矛盾信号**: MACD仍多头（-0.0342 > Signal -0.0857），但RSI=73.2已进入超买区。
**操作建议**: 趋势风格继续持有等MACD死叉；稳健风格可减仓一半。趋势型品种MACD权重更高。

---

## Strategy Matrix (24 Strategies)

`strategies/515180_*.json` 包含24种策略，按标的属性选择流派：

| 流派 | 适用标的 | 代表策略 | 原理 |
|:---|:---|:---|:---|
| 均值回归 | 震荡慢牛（515180） | RSI30反弹、布林带下轨 | 超跌买入，超买卖出 |
| 趋势跟踪 | 趋势性强（159545） | MACD金叉、均线多头 | 顺势买入，死叉离场 |
| 动量策略 | 活跃品种 | 20日动量突破 | 强者恒强 |
| 复合策略 | 待验证 | RSI+威廉、多因子 | 多条件共振 |

**max_hold_days Sweet Spot（515180）**:
| 天数 | 收益 | 夏普 | 建议 |
|:---:|:---:|:---:|:---|
| 40 | +71.38% | 1.48 | 夏普最优，推荐 |
| 80 | +77.73% | 1.26 | 收益最高，但持有期长 |
| 20 | +45.23% | 1.05 | 交易频率高，适合短线 |

---

## Output Management

项目级报告目录 `results/`，自动按日期分桶：

```
results/
  backtest/YYYY-MM-DD/
    batch_summary.md
    <strategy_id>/report.md
  analysis/YYYY-MM-DD/
    <code>_analysis.md
  ranking/YYYY-MM-DD/
    <board>_ranking.md
  tracker/YYYY-MM-DD/
    <code>_tracker.md
```

`tdx_core/reporting.py` - `ReportManager` 自动生成 Markdown 报告 + ASCII 资金曲线 + 交易明细 + 自动索引。

---

## Engine Fixes (2026-04-25)

1. **预热数据截断**: `_preload_data()` 从 `start_date` 往前预留 `max(lookback, 250) + 260` 天数据，解决区间开头指标为 NaN 问题
2. **日期格式统一**: `df["trade_date"] = df["trade_date"].astype(str)` 避免 `Timestamp` JSON 序列化失败
3. **None 保护**: batch summary 中 `total_return_pct` 可能为 None 时显示 "N/A"
4. **列间比较**: `_eval_conditions()` 支持 `{"indicator": "ma_5", "op": ">", "value": "ma_20"}` 形式

---

## Pullback Screener Strategy (2026-04-25)

5-factor scoring for "strong stock pullback" buy opportunities:

| Factor | Weight | Key Rule |
|:---|:---:|:---|
| Trend | 25 | Close > MA60 (15pt) + MA60 rising (10pt) |
| Pullback | 25 | 5-15% below 20-day high = 25pt (ideal zone) |
| Oversold | 20 | RSI(14) 30-50 = 20pt |
| Volume | 15 | Volume < 70% of 20-day avg = 15pt |
| Momentum | 15 | MACD > 0 = 15pt |

**Trade plan**: Entry = next-day open, Stop = MA60, Target = recent 20-day high, Max hold = 5 days.

**Ablation study finding**: Relative-strength filter (5d return >= sector average) is the ONLY effective improvement:
- Baseline: 43.5% win rate, +0.35% avg return, -0.93% median
- +Relative strength: 50.7% win rate, +1.03% avg return, +0.21% median
- +Combo C (all filters): 51.5% win rate, +1.13% avg return, +0.30% median

Baseline comparison: Random buy-hold on 创业板 = +0.60% avg, 50.3% win rate. Strategy without relative strength UNDERPERFORMS random buying. WITH relative strength it OUTPERFORMS.

**Key scripts**: `scripts/tech_screener.py` (scoring), `scripts/backtest_screener.py` (backtest), `scripts/ablation_screener.py` (batch experiments), `scripts/baseline_screener.py` (baseline).

**Metadata JSON export**: `config/metadata_export/` contains 7 JSON files (stock_dict, boards, industries L1/L2/L3, matrix, summary) for fast cloud usage without database queries. See `config/metadata_export/README.md` for sector-strength filter code.

## When Working on This Project

1. **Ask "which layer?"** before adding a new script: Data Pipeline / Single Stock / Batch / ETF Strategy / Backtest / Pullback Screener / Daily Market Review
2. **Test with real data** before claiming something works
3. **Run `json.dumps(obj)`** after any `to_dict()` implementation
4. **Output in Chinese** for all CLI-facing `print()` and reports
5. **Sync both sides** when modifying scripts or skill docs
6. **Provide CLI commands** after every code update — user needs runnable `python scripts/xxx.py --args` commands to self-test
7. **Different ETFs need different strategies** —震荡型用均值回归，趋势型用MACD跟踪
8. **GBK encoding** — Windows PowerShell 中文输出避免 emoji 和特殊符号
9. **CLI entry** — `tdx_core/cli.py` is the unified Click CLI. Add new subcommands via `@cli.command()`. Subcommands can either import script functions directly (for fast ones like `signal`) or delegate to `_run_script()` (for heavy ones like `analyze`). Both `tdx <cmd>` and `python scripts/xxx.py` must work.
10. **PowerShell encoding fix** — ALL new CLI scripts MUST add `sys.stdout.reconfigure(encoding='utf-8')` at startup to prevent UnicodeEncodeError on Chinese output in GBK terminals.
11. **Pullback screener rule**: Buy at next-day OPEN (not limit price). Stop = MA60 (not recent low - 3%). Filter out "fake pullbacks" with relative-strength check (stock 5d return >= sector average).
12. **Data anomaly filter**: In backtest, `abs(return_pct) > 1000` marks data_error and excludes from stats (e.g., 平安银行 2026-04-21 spurious 4085 price).
13. **Ablation precompute**: `ablation_screener.py` builds a cache of 27,740 (stock × date) metric tuples first, then runs experiments in parallel. This avoids re-computing the same metrics 8 times.
14. **Metadata export sync**: After `export_metadata.py`, copy `config/metadata_export/` to `claw_ready/config/metadata_export/` because `claw_ready/` is gitignored.
15. **DO NOT DELETE `data/tdx_data_cloud.db.gz`**: This compressed SQLite DB is tracked by git and used for cloud deployment. It must remain in the repository. Do not add it to `.gitignore` and do not delete it.
