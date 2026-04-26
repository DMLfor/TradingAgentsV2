"""股票关注池管理 CLI.

Usage:
    python scripts/watchlist_manager.py add 000001,600519,688018 --pool default
    python scripts/watchlist_manager.py remove 000001 --pool default
    python scripts/watchlist_manager.py list --pool default
    python scripts/watchlist_manager.py clear --pool default
    python scripts/watchlist_manager.py pools
"""

from __future__ import annotations

import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core.watchlist import WatchlistManager


def _parse_codes(val: str) -> list[str]:
    """解析股票代码，自动补齐6位数字（处理PowerShell截断前导零的问题）."""
    codes = []
    for c in val.replace("，", ",").split(","):
        c = c.strip()
        if not c:
            continue
        # 纯数字代码补齐到6位（如 1 → 000001）
        if c.isdigit():
            c = c.zfill(6)
        codes.append(c)
    return codes


def cmd_add(args) -> None:
    wm = WatchlistManager()
    codes = _parse_codes(args.codes)
    if not codes:
        print("[错误] 未提供有效股票代码")
        sys.exit(1)
    added = wm.add(codes, pool=args.pool)
    if added:
        print(f"[已添加] 关注池 '{args.pool}' 新增 {len(added)} 只: {', '.join(added)}")
    else:
        print(f"[提示] 所有股票已在关注池 '{args.pool}' 中")


def cmd_remove(args) -> None:
    wm = WatchlistManager()
    codes = _parse_codes(args.codes)
    if not codes:
        print("[错误] 未提供有效股票代码")
        sys.exit(1)
    removed = wm.remove(codes, pool=args.pool)
    if removed:
        print(f"[已删除] 关注池 '{args.pool}' 移除 {len(removed)} 只: {', '.join(removed)}")
    else:
        print(f"[提示] 指定股票不在关注池 '{args.pool}' 中")


def cmd_list(args) -> None:
    wm = WatchlistManager()
    items = wm.list_items(pool=args.pool)
    info = wm.info(args.pool)
    if not items:
        print(f"关注池 '{args.pool}' 为空 (共 0 只)")
        return
    print(f"\n关注池: {args.pool} (共 {info['count']} 只)")
    print(f"创建: {info['created_at']} | 更新: {info['updated_at']}")
    print("")
    header = f"{'代码':<10}{'名称':<12}{'板块':<10}{'一级行业':<12}{'二级行业':<12}"
    print(header)
    print("-" * len(header))
    for item in items:
        print(
            f"{item['code']:<10}{item['name']:<12}{item['board']:<10}"
            f"{item['level1']:<12}{item['level2']:<12}"
        )
    print("")


def cmd_clear(args) -> None:
    wm = WatchlistManager()
    count = wm.clear(pool=args.pool)
    print(f"[已清空] 关注池 '{args.pool}' 清除了 {count} 只股票")


def cmd_pools(_args) -> None:
    wm = WatchlistManager()
    pools = wm.pools()
    if not pools:
        print("当前没有任何关注池")
        return
    print("\n所有关注池:")
    for p in pools:
        info = wm.info(p)
        print(f"  {p}: {info['count']} 只 (更新于 {info['updated_at']})")
    print("")


def main():
    parser = argparse.ArgumentParser(description="股票关注池管理")
    sub = parser.add_subparsers(dest="action", required=True)

    # add
    p_add = sub.add_parser("add", help="添加股票到关注池")
    p_add.add_argument("codes", help="逗号分隔的股票代码")
    p_add.add_argument("--pool", default="default", help="目标池名称 (default: default)")

    # remove
    p_remove = sub.add_parser("remove", help="从关注池删除股票")
    p_remove.add_argument("codes", help="逗号分隔的股票代码")
    p_remove.add_argument("--pool", default="default", help="目标池名称")

    # list
    p_list = sub.add_parser("list", help="列出关注池股票")
    p_list.add_argument("--pool", default="default", help="目标池名称")

    # clear
    p_clear = sub.add_parser("clear", help="清空关注池")
    p_clear.add_argument("--pool", default="default", help="目标池名称")

    # pools
    sub.add_parser("pools", help="列出所有关注池")

    args = parser.parse_args()

    actions = {
        "add": cmd_add,
        "remove": cmd_remove,
        "list": cmd_list,
        "clear": cmd_clear,
        "pools": cmd_pools,
    }
    actions[args.action](args)


if __name__ == "__main__":
    main()
