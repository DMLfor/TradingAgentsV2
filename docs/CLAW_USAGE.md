# Claw Cloud Deployment Guide (Linux)

This guide covers running TradingAgentsV2 on a Linux cloud instance (Claw / VPS / Container).

## Prerequisites

- Python 3.11+
- SQLite (bundled with Python, no MySQL required for cloud mode)
- `data/tdx_data_cloud.db` or `data/tdx_data_cloud.db.gz` (compressed)

## Installation

```bash
# Clone from GitHub
git clone https://github.com/DMLfor/TradingAgentsV2.git
cd TradingAgentsV2

# Install dependencies
pip install -e .

# If only .db.gz exists, decompress first
cd data
if [ ! -f tdx_data_cloud.db ] && [ -f tdx_data_cloud.db.gz ]; then
    gunzip -k tdx_data_cloud.db.gz
fi
cd ..
```

## Configuration

Cloud mode uses SQLite by default. Edit `config/tdx_config.yaml`:

```yaml
db_type: "sqlite"
db_path: "data/tdx_data_cloud.db"
```

No MySQL credentials needed.

## New Features

### 1. Pullback Stock Screener (`scripts/tech_screener.py`)

5-factor scoring system for "strong stock pullback" opportunities:
- **Trend** (25pts): Close > MA60, MA60 rising
- **Pullback** (25pts): 5-15% pullback from 20-day high
- **Oversold** (20pts): RSI(14) in 30-50 range
- **Volume** (15pts): Shrinking volume during pullback
- **Momentum** (15pts): MACD still above zero

```bash
# Screen top 20 stocks from 创业板
python scripts/tech_screener.py --board 创业板 --min-score 55 --min-rr 0.5 --top 20

# Screen specific codes
python scripts/tech_screener.py --codes 300750,300059,300033 --min-score 55

# Save report
python scripts/tech_screener.py --board 创业板 --top 20 --save
```

Reports saved to `reports/picks/tech_screener_YYYYMMDD_HHMMSS.txt`.

### 2. CLI Pick Command

```bash
# Via tdx CLI
tdx pick --board 创业板 --min-score 55 --top 20 --save
```

### 3. Strategy Backtest (`scripts/backtest_screener.py`)

Simulate the screener strategy historically:
- Buy at next-day open (T+1)
- Stop loss: Close < MA60
- Take profit: Close >= recent 20-day high
- Max hold: 5 days

```bash
# Backtest full 创业板 for 20 weeks, hold 5 days
python scripts/backtest_screener.py --board 创业板 --weeks 20 --future-days 5 --min-score 55 --top 20 --save

# Backtest specific stocks
python scripts/backtest_screener.py --codes 300750,300059 --weeks 10 --future-days 5
```

Reports saved to `reports/backtests/screener_bt_YYYYMMDD_HHMMSS.txt`.

### 4. Baseline Comparison (`scripts/baseline_screener.py`)

Compare strategy against random-buy baseline:

```bash
python scripts/baseline_screener.py
```

Outputs:
- Baseline 1: All创业板 stocks (next-day open, hold 5 days)
- Baseline 2: Equal-weight index
- Strategy stats (from previous backtest)

### 5. Ablation Study (`scripts/ablation_screener.py`)

Batch test multiple filter combinations:

```bash
python scripts/ablation_screener.py
```

Experiments tested:
- Baseline (no filters)
- Exclude ST stocks
- Exclude suspended stocks
- Relative strength filter (5d return >= sector avg)
- Volume confirmation filter
- Combo C (all filters combined)
- Longer hold periods (10d, 20d)

**Key finding**: Relative strength filter improves win rate from 43.5% to 50.7% and avg return from +0.35% to +1.03%.

### 6. Metadata JSON Export (`config/metadata_export/`)

Pre-exported stock classification data for fast lookup without database queries:

| File | Purpose |
|:---|:---|
| `stock_dict.json` | `code -> {name, board, level1, level2, level3}` |
| `boards.json` | `board -> [codes]` |
| `industries_level1.json` | `industry -> [codes]` (31 industries) |
| `industries_level2.json` | `sub-industry -> [codes]` (90 sub-industries) |
| `industries_level3.json` | `sub-sub-industry -> [codes]` (257) |
| `board_industry_matrix.json` | `board -> {industry -> [codes]}` |
| `summary.json` | Aggregate counts and name lists |

Usage in scripts:

```python
import json

with open("config/metadata_export/stock_dict.json", "r", encoding="utf-8") as f:
    stocks = json.load(f)

# Get all 创业板 codes
with open("config/metadata_export/boards.json", "r", encoding="utf-8") as f:
    boards = json.load(f)
growth_codes = boards["创业板"]  # 1398 codes

# Get all 电子 industry codes
with open("config/metadata_export/industries_level1.json", "r", encoding="utf-8") as f:
    industries = json.load(f)
elec_codes = industries["电子"]  # 521 codes
```

See `config/metadata_export/README.md` for sector strength filter code.

## Scheduled Tasks (Cron)

Replace Windows Task Scheduler with cron:

```bash
# Edit crontab
crontab -e

# Daily market close sync (15:30 Beijing time = 07:30 UTC)
30 7 * * 1-5 cd /path/to/TradingAgentsV2 && python scripts/tdx_sync.py --market sh sz >> logs/cron_sync.log 2>&1

# Weekly Friday evening screening
0 20 * * 5 cd /path/to/TradingAgentsV2 && python scripts/tech_screener.py --board 创业板 --top 20 --save >> logs/cron_screener.log 2>&1

# Monthly ablation study report (1st of month)
0 2 1 * * cd /path/to/TradingAgentsV2 && python scripts/ablation_screener.py >> logs/cron_ablation.log 2>&1
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_tech_screener.py -v
pytest tests/test_backtest_screener.py -v
```

17 tests cover: pullback scoring, chasing penalty, downtrend filtering, entry/stop/target relationships, position sizing, open-price buy, MA60 stop loss, target profit, data anomaly filtering.

## Linux-Specific Notes

| Item | Windows (Local) | Linux (Cloud) |
|:---|:---|:---|
| Database | MySQL + SQLite | SQLite only |
| Scheduler | Task Scheduler | cron |
| Paths | `C:\Users\...` | `/home/user/...` |
| Encoding | GBK terminal issues | UTF-8 native |
| Data file | `tdx_data.db` (5GB) | `tdx_data_cloud.db` (250MB) |
| Emoji in output | Avoid (GBK) | Safe |

## Security Checklist

- [ ] `.env` is in `.gitignore` (contains API tokens)
- [ ] `config/tdx_config.yaml` is in `.gitignore` (contains passwords)
- [ ] `data/*.db` is in `.gitignore` (large database files)
- [ ] `claw_ready/` is in `.gitignore` (deployment bundle)
- [ ] No hardcoded credentials in source code
