# Stock Metadata Export — Usage Guide

These JSON files contain the static classification data for all 5516 A-share stocks (as of 2026-04-25). They are exported from `config/stock_metadata.json` for easy consumption in cloud/claw environments where the full metadata module may not be available.

## Files

| File | Size | Content |
|:---|:---|:---|
| `stock_dict.json` | ~1.2 MB | `code -> {name, board, level1, level2, level3, thx_industry}` |
| `boards.json` | ~80 KB | `board_name -> [code, ...]` |
| `industries_level1.json` | ~80 KB | `level1_name -> [code, ...]` (31 industries) |
| `industries_level2.json` | ~83 KB | `level2_name -> [code, ...]` (90 sub-industries) |
| `industries_level3.json` | ~87 KB | `level3_name -> [code, ...]` (257 sub-sub-industries) |
| `board_industry_matrix.json` | ~95 KB | `board -> {level1 -> [code, ...]}` cross matrix |
| `summary.json` | ~8 KB | Aggregate counts and name lists |

## Quick Start

```python
import json
from pathlib import Path

BASE = Path(__file__).parent

# Load all stocks with their classifications
with open(BASE / "stock_dict.json", "r", encoding="utf-8") as f:
    stock_dict = json.load(f)

# Get a stock's info
print(stock_dict["300750"])
# {"name": "宁德时代", "board": "创业板", "level1": "电力设备", ...}

# Load board mappings
with open(BASE / "boards.json", "r", encoding="utf-8") as f:
    boards = json.load(f)

growth_board_codes = boards["创业板"]  # 1398 codes

# Load industry mappings
with open(BASE / "industries_level1.json", "r", encoding="utf-8") as f:
    industries = json.load(f)

power_codes = industries["电力设备"]  # 407 codes

# Filter: 创业板 + 电力设备
growth_power = [c for c in boards["创业板"] if c in set(industries["电力设备"])]
print(f"创业板电力设备: {len(growth_power)} stocks")
```

## Use Case: Sector Strength Filter (in Screener)

A proven improvement to the pullback screener: only select stocks whose
recent return is >= the sector average. This filters out "fake pullbacks"
(stocks falling because the whole sector is crashing).

```python
def get_sector_avg_return(codes, db_query_func, signal_date, lookback=5):
    """
    Compute the average return of a group of stocks over `lookback` days.
    db_query_func: function(code, start_date) -> DataFrame with close_val
    """
    returns = []
    for code in codes:
        df = db_query_func(code, start_date=signal_date)  # fetch recent data
        if df is None or len(df) < lookback + 1:
            continue
        start_price = df.iloc[0]["close_val"]
        end_price = df.iloc[lookback]["close_val"]
        if start_price > 0:
            returns.append((end_price - start_price) / start_price * 100)
    return sum(returns) / len(returns) if returns else 0.0


# Example: in a screener, only keep stocks beating their sector
def filter_relative_strength(
    candidate_codes, board_codes, db_query_func, signal_date, lookback=5
):
    sector_avg = get_sector_avg_return(board_codes, db_query_func, signal_date, lookback)
    strong_codes = []
    for code in candidate_codes:
        df = db_query_func(code, start_date=signal_date)
        if df is None or len(df) < lookback + 1:
            continue
        start_price = df.iloc[0]["close_val"]
        end_price = df.iloc[lookback]["close_val"]
        if start_price > 0:
            stock_ret = (end_price - start_price) / start_price * 100
            if stock_ret >= sector_avg:
                strong_codes.append(code)
    return strong_codes
```

## Summary Reference

```python
import json

with open("summary.json", "r", encoding="utf-8") as f:
    summary = json.load(f)

print(summary["total_stocks"])      # 5516
print(summary["boards"])            # {"沪市主板": 1704, ...}
print(summary["level1_names"])      # ["交通运输", "传媒", ...] (31 items)
```

## Data Freshness

These files are a **static snapshot**. If you need real-time stock list updates
(e.g., new IPOs, delistings), re-run:

```bash
python scripts/update_stock_metadata.py
python scripts/export_metadata.py
```
