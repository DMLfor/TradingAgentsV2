#!/usr/bin/env python3
"""Update stock name mapping from a CSV file.

Usage:
    python scripts/update_stock_names.py
    python scripts/update_stock_names.py --csv C:\path\to\mapping.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_CSV = Path.home() / "Downloads" / "A股全部上市公司代码名称映射表.csv"
OUT_JSON = Path(ROOT) / "config" / "stock_names.json"


def update_from_csv(csv_path: Path) -> int:
    if not csv_path.exists():
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)

    mapping: dict[str, str] = {}
    # Try encodings in order of likelihood
    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
    rows: list[list[str]] = []

    for enc in encodings:
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            print(f"[OK] Read CSV with encoding: {enc}")
            break
        except UnicodeDecodeError:
            continue
    else:
        print("[ERROR] Could not decode CSV with any known encoding")
        sys.exit(1)

    if not rows:
        print("[ERROR] CSV is empty")
        sys.exit(1)

    header = rows[0]
    print(f"[INFO] Header: {header}")

    for row in rows[1:]:
        if len(row) < 2:
            continue
        raw_code = row[0].strip()
        name = row[1].strip()
        # Strip exchange suffix: .SZ / .SH / .BJ / etc.
        code = re.sub(r"\.[A-Z]+$", "", raw_code)
        if re.fullmatch(r"\d{6}", code) and name:
            mapping[code] = name

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {len(mapping)} entries to {OUT_JSON}")
    return len(mapping)


def main():
    parser = argparse.ArgumentParser(description="Update stock name mapping from CSV")
    parser.add_argument("--csv", "-c", type=Path, default=DEFAULT_CSV, help="Path to CSV file")
    args = parser.parse_args()
    update_from_csv(args.csv)


if __name__ == "__main__":
    main()
