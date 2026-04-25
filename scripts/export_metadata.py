#!/usr/bin/env python3
"""Export stock metadata into standalone JSON files for claw/cloud usage."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
META_PATH = ROOT / "config" / "stock_metadata.json"
OUT_DIR = ROOT / "config" / "metadata_export"


def main():
    print(f"Loading {META_PATH} ...")
    with open(META_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. stock_dict.json: code -> basic info (name + industries + board) ──
    stock_dict = {}
    for code, info in data["stocks"].items():
        stock_dict[code] = {
            "name": info["name"],
            "board": info["board"],
            "level1": info["level1"],
            "level2": info["level2"],
            "level3": info["level3"],
            "thx_industry": info.get("thx_industry", ""),
        }

    out_path = OUT_DIR / "stock_dict.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stock_dict, f, ensure_ascii=False, indent=2)
    print(f"  stock_dict.json       -> {len(stock_dict)} stocks  ({out_path.stat().st_size / 1024:.1f} KB)")

    # ── 2. boards.json: board name -> list of codes ──
    boards = {}
    for board_name, codes in data["index"]["by_board"].items():
        boards[board_name] = codes

    out_path = OUT_DIR / "boards.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(boards, f, ensure_ascii=False, indent=2)
    for name, codes in boards.items():
        print(f"  boards.json           -> {name}: {len(codes)} stocks")

    # ── 3. industries_level1.json: level1 -> list of codes ──
    level1 = {}
    for name, codes in data["index"]["by_level1"].items():
        level1[name] = codes

    out_path = OUT_DIR / "industries_level1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(level1, f, ensure_ascii=False, indent=2)
    for name, codes in level1.items():
        print(f"  industries_level1.json -> {name}: {len(codes)} stocks")

    # ── 4. industries_level2.json: level2 -> list of codes ──
    level2 = {}
    for name, codes in data["index"]["by_level2"].items():
        level2[name] = codes

    out_path = OUT_DIR / "industries_level2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(level2, f, ensure_ascii=False, indent=2)
    print(f"  industries_level2.json -> {len(level2)} sub-industries")

    # ── 5. industries_level3.json: level3 -> list of codes ──
    level3 = {}
    for name, codes in data["index"]["by_level3"].items():
        level3[name] = codes

    out_path = OUT_DIR / "industries_level3.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(level3, f, ensure_ascii=False, indent=2)
    print(f"  industries_level3.json -> {len(level3)} sub-sub-industries")

    # ── 6. board_industry_matrix.json: board x level1 count matrix ──
    # Useful for quick sector strength analysis
    matrix = {}
    for code, info in data["stocks"].items():
        board = info["board"]
        l1 = info["level1"]
        if board not in matrix:
            matrix[board] = {}
        if l1 not in matrix[board]:
            matrix[board][l1] = []
        matrix[board][l1].append(code)

    out_path = OUT_DIR / "board_industry_matrix.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    print(f"  board_industry_matrix.json -> {len(matrix)} boards")

    # ── 7. summary.json: lightweight metadata summary ──
    summary = {
        "total_stocks": data["meta"]["total"],
        "level1_count": data["meta"]["level1_count"],
        "level2_count": data["meta"]["level2_count"],
        "level3_count": data["meta"]["level3_count"],
        "board_count": data["meta"]["board_count"],
        "boards": {name: len(codes) for name, codes in boards.items()},
        "level1_names": sorted(level1.keys()),
        "level2_names": sorted(level2.keys()),
        "level3_names": sorted(level3.keys()),
        "export_time": "2026-04-25",
    }

    out_path = OUT_DIR / "summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  summary.json")

    print(f"\nAll files exported to: {OUT_DIR}")


if __name__ == "__main__":
    main()
