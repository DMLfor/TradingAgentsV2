#!/usr/bin/env python3
"""Auto-update the trading-agents SKILL.md based on scripts/ directory contents.

Scans the TradingAgentsV2 scripts/ directory for Python scripts,
reads their docstrings and usage comments, and regenerates the SKILL.md.

Run manually or via Task Scheduler at 09:00 daily.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path("C:/Users/dblank/code/TradingAgentsV2")
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SKILL_DIR = PROJECT_ROOT / "skill"
SKILL_PATH = SKILL_DIR / "SKILL.md"
OPENCLAW_SKILL_DIR = Path("C:/Users/dblank/.kimi_openclaw/workspace/skills/trading-agents")
OPENCLAW_SKILL_PATH = OPENCLAW_SKILL_DIR / "SKILL.md"

def extract_script_info(script_path: Path) -> dict | None:
    """Extract script name, description, and usage from a Python file."""
    content = script_path.read_text(encoding="utf-8")
    name = script_path.stem

    # Try to find docstring
    docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
    if docstring_match:
        doc = docstring_match.group(1).strip()
        # Extract first line as description
        lines = [l.strip() for l in doc.split("\n") if l.strip()]
        description = lines[0] if lines else name
        # Extract Usage block
        usage_lines = []
        in_usage = False
        for line in doc.split("\n"):
            if "usage" in line.lower() or "typical" in line.lower() or "用法" in line:
                in_usage = True
            if in_usage:
                stripped = line.strip()
                if stripped.startswith("python ") or stripped.startswith("py "):
                    usage_lines.append(stripped)
                elif stripped.startswith("# ") and usage_lines:
                    break
        usage = usage_lines
    else:
        description = name.replace("_", " ")
        usage = []

    return {
        "name": name,
        "file": script_path.name,
        "description": description,
        "usage": usage,
    }

def scan_scripts() -> list[dict]:
    """Scan scripts/ directory and return info for all .py files."""
    scripts = []
    if not SCRIPTS_DIR.exists():
        print(f"Scripts directory not found: {SCRIPTS_DIR}")
        return scripts

    for f in sorted(SCRIPTS_DIR.glob("*.py")):
        if f.name.startswith("__") or f.name.startswith("."):
            continue
        info = extract_script_info(f)
        if info:
            scripts.append(info)
    return scripts

def generate_skill_md(scripts: list[dict]) -> str:
    """Generate SKILL.md content from scripts info."""

    core_scripts = []
    data_scripts = []
    etf_scripts = []
    other_scripts = []

    for s in scripts:
        name = s["name"]
        if name in ["technical_master", "analyze_stock", "scan_market",
                    "rank_stocks", "backtest_signal", "list_indicators",
                    "filter_stocks", "rank_growth_board"]:
            core_scripts.append(s)
        elif name in ["tdx_sync", "tdx_full_import", "tdx_init_db",
                      "update_stock_metadata", "update_stock_names"]:
            data_scripts.append(s)
        elif name in ["etf_longterm_tracker", "etf_volatility_strategy", "optimize_indexes"]:
            etf_scripts.append(s)
        else:
            other_scripts.append(s)

    def script_section(s: dict) -> str:
        lines = [f"### {s['name']}", f"{s['description']}", ""]
        if s["usage"]:
            lines.append("```powershell")
            for u in s["usage"]:
                lines.append(u)
            lines.append("```")
            lines.append("")
        return "\n".join(lines)

    lines = [
        "---",
        "name: trading-agents",
        "description: Run stock technical analysis and market scanning scripts from the TradingAgentsV2 project. Use when the user asks to analyze stocks, scan market signals, rank stocks by indicators, backtest signals, or run any investment/technical analysis script. Also use when the user mentions stock screening, market scanning, indicator ranking, batch analysis, or any TradingAgentsV2 script.",
        "---",
        "",
        "# TradingAgentsV2 - A-Stock Technical Analysis Scripts",
        "",
        f"_Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "All scripts use **通达信（TDX）local data** as the data source.",
        "",
        "## Before Running Any Script",
        "",
        "Always cd to the project root first:",
        "",
        "```powershell",
        "cd C:/Users/dblank/code/TradingAgentsV2",
        "```",
        "",
    ]

    if core_scripts:
        lines.extend(["## Core Analysis Scripts", ""])
        for s in core_scripts:
            lines.append(script_section(s))

    if data_scripts:
        lines.extend(["## Data Sync Scripts", ""])
        for s in data_scripts:
            lines.append(script_section(s))

    if etf_scripts:
        lines.extend(["## ETF Scripts", ""])
        for s in etf_scripts:
            lines.append(script_section(s))

    if other_scripts:
        lines.extend(["## Other Scripts", ""])
        for s in other_scripts:
            lines.append(script_section(s))

    lines.extend([
        "## Stock Name Mapping",
        "",
        "All scripts support **Chinese stock names** directly. The system auto-resolves names to 6-digit codes via config/stock_names.json (5500+ A-shares mapped from TDX).",
        "",
        "```powershell",
        "py scripts/technical_master.py 深信服",
        "py scripts/technical_master.py 中体产业",
        "py scripts/scan_market.py 乐鑫科技,中芯国际 --indicator rsi",
        "```",
        "",
        "## Output",
        "",
        "- All scripts print to terminal by default.",
        "- Add --save to write full reports to logs/ with timestamp filenames.",
        "- Reports are plain text, easy to copy or send via IM.",
        "",
        "## Batch Workflows",
        "",
        "Typical morning scan workflow:",
        "",
        "```powershell",
        "cd C:/Users/dblank/code/TradingAgentsV2",
        "",
        "# 1. Sync data",
        "py scripts/tdx_sync.py",
        "",
        "# 2. Growth board top 100",
        "py scripts/rank_growth_board.py",
        "",
        "# 3. Scan watchlist for signals",
        "py scripts/scan_market.py 300750,688981,600519 --indicator macd --signal golden_cross",
        "",
        "# 4. Rank by RSI to find oversold",
        "py scripts/rank_stocks.py 300750,688981,600519,000001 --indicator rsi --ascending",
        "```",
        "",
    ])

    return "\n".join(lines)

def main():
    print(f"[{datetime.now().isoformat()}] Scanning {SCRIPTS_DIR}...")
    scripts = scan_scripts()
    print(f"Found {len(scripts)} scripts.")

    if not scripts:
        print("No scripts found. Exiting.")
        sys.exit(1)

    new_md = generate_skill_md(scripts)

    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    OPENCLAW_SKILL_DIR.mkdir(parents=True, exist_ok=True)
    
    old_content = SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""

    if old_content == new_md:
        print("SKILL.md is up to date. No changes needed.")
    else:
        SKILL_PATH.write_text(new_md, encoding="utf-8")
        OPENCLAW_SKILL_PATH.write_text(new_md, encoding="utf-8")
        print(f"Updated SKILL.md ({len(new_md)} bytes) in both locations.")

if __name__ == "__main__":
    main()
