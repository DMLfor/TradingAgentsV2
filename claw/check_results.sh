#!/bin/bash
# Cloud result checker for OpenClaw (Linux)
# Usage: bash claw/check_results.sh

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORTS_DIR="$ROOT/reports"

echo "========================================"
echo "TradingAgentsV2 Cloud Result Checker"
echo "========================================"
echo ""

# 1. Check report directories
echo "[Report Directories]"
for d in signals rankings scans analysis backtests etf; do
    dir="$REPORTS_DIR/$d"
    count=0
    if [ -d "$dir" ]; then
        count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l)
    fi
    printf "  %-12s : %3d files\n" "$d/" "$count"
done
echo ""

# 2. Latest signal reports
echo "[Latest Signal Reports]"
for code in 515180 159545; do
    latest=$(find "$REPORTS_DIR/signals" -maxdepth 1 -name "signal_${code}_*.txt" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
    if [ -n "$latest" ]; then
        mtime=$(stat -c '%Y' "$latest" 2>/dev/null || stat -f '%m' "$latest" 2>/dev/null)
        now=$(date +%s)
        age_h=$(( (now - mtime) / 3600 ))
        printf "  %-20s : %2d hours ago\n" "$(basename "$latest")" "$age_h"
    else
        printf "  signal_%s_*.txt      : not found\n" "$code"
    fi
done
echo ""

# 3. Latest ranking report
echo "[Latest Ranking Report]"
rank_latest=$(find "$REPORTS_DIR/rankings" -maxdepth 1 -name "growth_board_rank_*.txt" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
if [ -n "$rank_latest" ]; then
    mtime=$(stat -c '%Y' "$rank_latest" 2>/dev/null || stat -f '%m' "$rank_latest" 2>/dev/null)
    now=$(date +%s)
    age_h=$(( (now - mtime) / 3600 ))
    printf "  %-20s : %2d hours ago\n" "$(basename "$rank_latest")" "$age_h"
else
    printf "  growth_board_rank_*.txt : not found\n"
fi
echo ""

# 4. Summary of today's reports
echo "[Today's New Reports]"
today=$(date +%Y%m%d)
total=0
for d in signals rankings scans analysis backtests etf; do
    dir="$REPORTS_DIR/$d"
    if [ -d "$dir" ]; then
        n=$(find "$dir" -maxdepth 1 -name "*${today}*" -type f 2>/dev/null | wc -l)
        total=$((total + n))
        printf "  %-12s : %3d\n" "$d/" "$n"
    fi
done
printf "  %-12s : %3d\n" "TOTAL" "$total"
echo ""

echo "========================================"
echo "Done."
