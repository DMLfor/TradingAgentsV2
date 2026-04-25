#!/usr/bin/env python3
"""Claw 定时任务结果查询器.

读取 reports/ 目录，汇总和展示定时任务的执行结果.
Claw 被唤醒时调用，方便用户查看报告.

Usage:
    python scripts/claw_check.py --today
    python scripts/claw_check.py --latest 5
    python scripts/claw_check.py --task ETFTracker-515180
    python scripts/claw_check.py --task ETFTracker-515180 --today
    python scripts/claw_check.py --since 2026-04-20
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = str(Path(__file__).resolve().parent.parent)
REPORTS_DIR = Path(ROOT) / "reports"
LOGS_DIR = Path(ROOT) / "logs"  # backward compatibility

# 任务名称到文件前缀的映射（支持模糊匹配）
TASK_PREFIXES = {
    "etftracker-515180": ["signal_515180", "tracker_515180", "etf_grid_515180"],
    "etftracker-159545": ["signal_159545", "tracker_159545", "etf_grid_159545"],
    "growthboardrank": ["growth_board_rank"],
    "marketscan-macd": ["scan_macd", "scan_"],
    "technicalmaster": ["analysis_", "technical_"],
}


def _parse_date(s: str) -> date:
    """Parse YYYY-MM-DD or YYYYMMDD."""
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {s}")


def _find_files(
    task_hint: Optional[str] = None,
    since: Optional[date] = None,
    until: Optional[date] = None,
) -> list[Path]:
    """Find report files matching criteria in reports/ and legacy logs/."""
    candidates = []

    # Search reports/ subdirectories
    search_dirs = []
    if REPORTS_DIR.exists():
        search_dirs.extend([d for d in REPORTS_DIR.iterdir() if d.is_dir()])
    # Also check legacy logs/
    if LOGS_DIR.exists():
        search_dirs.append(LOGS_DIR)

    if not search_dirs:
        return []

    for directory in search_dirs:
        for f in directory.iterdir():
            if not f.is_file() or not f.suffix == ".txt":
                continue

            # Try to extract date from filename (common patterns)
            # Patterns: tracker_515180_20260425_183012.txt, growth_board_rank_20260425_190000.txt
            m = re.search(r"_(\d{8})_\d{6}\.txt$", f.name)
            if m:
                file_date = datetime.strptime(m.group(1), "%Y%m%d").date()
            else:
                # Fallback to modification time
                file_date = datetime.fromtimestamp(f.stat().st_mtime).date()

            if since and file_date < since:
                continue
            if until and file_date > until:
                continue

            # Task filter
            if task_hint:
                hint_lower = task_hint.lower().replace("-", "").replace("_", "")
                matched = False
                for key, prefixes in TASK_PREFIXES.items():
                    key_clean = key.lower().replace("-", "").replace("_", "")
                    if hint_lower in key_clean or key_clean in hint_lower:
                        if any(f.name.startswith(p) for p in prefixes):
                            matched = True
                            break
                if not matched:
                    # Also try direct substring match on filename
                    if hint_lower not in f.name.lower().replace("-", "").replace("_", ""):
                        continue

            candidates.append(f)

    # Sort by modification time descending
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates


def _file_summary(f: Path, max_lines: int = 5) -> str:
    """Read first N lines of a report file."""
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        header = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            header += f"\n... ({len(lines)} lines total)"
        return header
    except Exception as e:
        return f"[Error reading file: {e}]"


def _format_size(size: int) -> str:
    """Format file size human-readable."""
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def show_today() -> None:
    """Show all reports from today."""
    today = date.today()
    files = _find_files(since=today, until=today)

    if not files:
        print(f"No reports found for today ({today}).")
        return

    print(f"Reports for today ({today}):")
    print("-" * 70)
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size = _format_size(f.stat().st_size)
        print(f"  {mtime.strftime('%H:%M:%S')}  {size:>8}  {f.name}")


def show_latest(n: int = 5, task_hint: Optional[str] = None) -> None:
    """Show latest N reports."""
    files = _find_files(task_hint=task_hint)
    if not files:
        hint = f" matching '{task_hint}'" if task_hint else ""
        print(f"No reports found{hint}.")
        return

    show_files = files[:n]
    print(f"Latest {len(show_files)} report(s){' (filtered)' if task_hint else ''}:")
    print("-" * 70)
    for f in show_files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size = _format_size(f.stat().st_size)
        print(f"  {mtime.strftime('%Y-%m-%d %H:%M:%S')}  {size:>8}  {f.name}")


def show_task(task_hint: str, today_only: bool = False) -> None:
    """Show reports for a specific task."""
    since = date.today() if today_only else None
    until = date.today() if today_only else None

    files = _find_files(task_hint=task_hint, since=since, until=until)
    if not files:
        scope = "today" if today_only else "all time"
        print(f"No reports for '{task_hint}' ({scope}).")
        return

    scope = f"today ({date.today()})" if today_only else "all time"
    print(f"Reports for '{task_hint}' ({scope}):")
    print("-" * 70)
    for f in files[:5]:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size = _format_size(f.stat().st_size)
        print(f"  {mtime.strftime('%Y-%m-%d %H:%M:%S')}  {size:>8}  {f.name}")

    # Show summary of the most recent one
    if files:
        print()
        print(f"Latest report summary ({files[0].name}):")
        print("=" * 70)
        print(_file_summary(files[0], max_lines=20))


def show_since(since_str: str) -> None:
    """Show reports since a date."""
    since = _parse_date(since_str)
    files = _find_files(since=since)

    if not files:
        print(f"No reports found since {since}.")
        return

    print(f"Reports since {since} ({len(files)} total):")
    print("-" * 70)
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size = _format_size(f.stat().st_size)
        print(f"  {mtime.strftime('%Y-%m-%d %H:%M:%S')}  {size:>8}  {f.name}")


def main():
    parser = argparse.ArgumentParser(description="Claw Task Result Checker")
    parser.add_argument("--today", action="store_true", help="Show today's reports")
    parser.add_argument("--latest", type=int, nargs="?", const=5, metavar="N",
                        help="Show latest N reports (default: 5)")
    parser.add_argument("--task", metavar="NAME", help="Filter by task name")
    parser.add_argument("--since", metavar="DATE", help="Show reports since YYYY-MM-DD")
    args = parser.parse_args()

    if not any([args.today, args.latest is not None, args.task, args.since]):
        parser.print_help()
        sys.exit(0)

    if args.task and args.today:
        show_task(args.task, today_only=True)
    elif args.task:
        show_task(args.task, today_only=False)
    elif args.today:
        show_today()
    elif args.since:
        show_since(args.since)
    elif args.latest is not None:
        show_latest(args.latest, task_hint=args.task)


if __name__ == "__main__":
    main()
