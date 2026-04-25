---
name: trading-agents
description: Run stock technical analysis and market scanning scripts from the TradingAgentsV2 project. Use when the user asks to analyze stocks, scan market signals, rank stocks by indicators, backtest signals, or run any investment/technical analysis script. Also use when the user mentions stock screening, market scanning, indicator ranking, batch analysis, or any TradingAgentsV2 script.
---

# TradingAgentsV2 - A-Stock Technical Analysis Scripts

_Auto-generated on 2026-04-25 11:56_

All scripts use **通达信（TDX）local data** as the data source.

## Before Running Any Script

Always cd to the project root first:

```powershell
cd C:/Users/dblank/code/TradingAgentsV2
```

## Core Analysis Scripts

### analyze_stock
Single-stock deep indicator analysis.

```powershell
python scripts/analyze_stock.py 688018
python scripts/analyze_stock.py 000001 --indicators rsi,macd,bollinger
python scripts/analyze_stock.py 688018 --save
```

### backtest_signal
Backtest an indicator signal across a stock universe.

```powershell
python scripts/backtest_signal.py 688018,688981,688111,688012 --indicator macd --signal golden_cross --hold 5
python scripts/backtest_signal.py 000001,000002 --indicator rsi --signal oversold --hold 10
```

### filter_stocks
Sector-based stock screener — 行业板块选股工具.

```powershell
python scripts/filter_stocks.py --list-level1
python scripts/filter_stocks.py --list-level2 --level1 电子
python scripts/filter_stocks.py --list-boards
```

### list_indicators
List all available indicators and their signals.

```powershell
python scripts/list_indicators.py
python scripts/list_indicators.py --indicator macd
```

### rank_growth_board
创业板全量股票技术分析排名 — 120日数据批量评分.

```powershell
python scripts/rank_growth_board.py
python scripts/rank_growth_board.py --bars 120 --top 100
python scripts/rank_growth_board.py --save
```

### rank_stocks
Rank stocks by an indicator column.

```powershell
python scripts/rank_stocks.py 688018,688981,688111,688012 --indicator rsi --ascending
python scripts/rank_stocks.py 000001,000002,600000 --indicator macd --column macd_hist
```

### scan_market
Scan a list of stocks for indicator signals.

```powershell
python scripts/scan_market.py 688018,688981,688111,688012 --indicator macd --signal golden_cross
python scripts/scan_market.py 000001,000002,600000 --indicator rsi --signal oversold
```

### technical_master
Technical Analysis Master Panel — 全量指标深度解析.

```powershell
python scripts/technical_master.py 688018
python scripts/technical_master.py 688018 --bars 120
python scripts/technical_master.py 688018 --save
```

## Data Sync Scripts

### tdx_full_import
首次全量导入脚本

```powershell
python tdx_full_import.py
python tdx_full_import.py --config my.yaml
```

### tdx_init_db
初始化数据库：建库建表

### tdx_sync
通信达数据同步主脚本

```powershell
python tdx_sync.py                          # 增量同步（默认沪深）
python tdx_sync.py --full                   # 全量导入
python tdx_sync.py --market sh sz           # 指定市场增量同步
python tdx_sync.py --market sh --full       # 仅沪市全量导入
python tdx_sync.py --force                  # 忽略变更检测，强制重跑
python tdx_sync.py --config my.yaml         # 自定义配置
```

### update_stock_metadata
Update stock metadata from CSV → config/stock_metadata.json.

```powershell
python scripts/update_stock_metadata.py
python scripts/update_stock_metadata.py --csv D:\\new_metadata.csv
```

### update_stock_names
Update stock name mapping from a CSV file.

```powershell
python scripts/update_stock_names.py
python scripts/update_stock_names.py --csv C:\path\to\mapping.csv
```

## ETF Scripts

### etf_longterm_tracker
红利ETF (515180) 长期跟踪策略 —— 核心仓位 + 动态网格

```powershell
python scripts/etf_longterm_tracker.py              # 默认 515180
python scripts/etf_longterm_tracker.py --code 510880 --save
```

### etf_volatility_strategy
红利ETF (515180) 波动率自适应网格策略

```powershell
python scripts/etf_volatility_strategy.py          # 默认分析 515180
python scripts/etf_volatility_strategy.py --code 510880 --bars 120
python scripts/etf_volatility_strategy.py --grid 3 --step 0.8 --save
```

### optimize_indexes
导入后索引优化脚本

```powershell
python scripts/optimize_indexes.py --drop   # 导入前：删除非主键索引加速写入
python scripts/optimize_indexes.py --create # 导入后：重建索引优化查询
```

## Other Scripts

### strategy_backtest
Multi-factor strategy backtest CLI.

```powershell
python scripts/strategy_backtest.py --strategy strategies/trend_momentum.json --start 2024-01-01 --end 2025-12-31 --save
```

## Stock Name Mapping

All scripts support **Chinese stock names** directly. The system auto-resolves names to 6-digit codes via config/stock_names.json (5500+ A-shares mapped from TDX).

```powershell
py scripts/technical_master.py 深信服
py scripts/technical_master.py 中体产业
py scripts/scan_market.py 乐鑫科技,中芯国际 --indicator rsi
```

## Output

- All scripts print to terminal by default.
- Add --save to write full reports to logs/ with timestamp filenames.
- Reports are plain text, easy to copy or send via IM.

## Batch Workflows

Typical morning scan workflow:

```powershell
cd C:/Users/dblank/code/TradingAgentsV2

# 1. Sync data
py scripts/tdx_sync.py

# 2. Growth board top 100
py scripts/rank_growth_board.py

# 3. Scan watchlist for signals
py scripts/scan_market.py 300750,688981,600519 --indicator macd --signal golden_cross

# 4. Rank by RSI to find oversold
py scripts/rank_stocks.py 300750,688981,600519,000001 --indicator rsi --ascending
```
