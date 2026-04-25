# OpenClaw Heartbeat — TradingAgentsV2

## Purpose
Automatically check定时任务 execution results when Claw wakes up via heartbeat.

## Interval
30 minutes (or on-demand when user asks)

## Execution Flow

1. **Run the check script:**
   ```bash
   claw\check_results.bat
   ```

2. **What it does:**
   - Lists all registered tasks and their actual next-run times
   - Checks `logs/` directory for today's new reports
   - Shows the latest report for each active task (515180, 159545, GrowthBoardRank)

3. **Report to user:**
   - If new reports found → summarize key signals / rankings
   - If no new reports → "No new reports since last check"

## Key Log File Patterns

| Task | Log File Pattern |
|:---|:---|
| ETFTracker-515180 | `logs/signal_515180_rsi30_bounce_YYYYMMDD_*.txt` |
| ETFTracker-159545 | `logs/signal_159545_macd_golden_YYYYMMDD_*.txt` |
| GrowthBoardRank | `logs/growth_board_rank_YYYYMMDD_*.txt` |

## Manual Trigger
User can also say: **"查一下定时任务结果"** and Claw should run the same check.
