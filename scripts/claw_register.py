#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claw Windows Task Scheduler Register.

Register / update / remove TradingAgentsV2 scheduled tasks via Windows Task Scheduler.
Called when Claw wakes up; no manual Task Scheduler operation needed.

Usage:
    python scripts/claw_register.py --list
    python scripts/claw_register.py --register
    python scripts/claw_register.py --register ETFTracker-515180
    python scripts/claw_register.py --reload
    python scripts/claw_register.py --remove ETFTracker-515180
    python scripts/claw_register.py --remove-all
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import random
import yaml

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = str(Path(__file__).resolve().parent.parent)
CONFIG_PATH = Path(ROOT) / "config" / "claw_tasks.yaml"


def _powershell(cmd: str) -> tuple[int, str, str]:
    """Run PowerShell command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def _task_exists(name: str, folder: str = "TradingAgentsV2") -> bool:
    """Check if a scheduled task already exists."""
    ps = f"Get-ScheduledTask -TaskName '{name}' -TaskPath '\\{folder}\\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty TaskName"
    rc, out, _ = _powershell(ps)
    return rc == 0 and out.strip() == name


def _get_task_next_run(name: str, folder: str = "TradingAgentsV2") -> str:
    """Query Windows Task Scheduler for the task's next run time (HH:MM)."""
    ps = f"""
try {{
    $info = Get-ScheduledTask -TaskName '{name}' -TaskPath '\\{folder}\\' -ErrorAction Stop | Get-ScheduledTaskInfo
    $info.NextRunTime.ToString('HH:mm')
}} catch {{
    'N/A'
}}
"""
    rc, out, _ = _powershell(ps)
    if rc == 0:
        return out.strip()
    return "N/A"


def _delete_task(name: str, folder: str = "TradingAgentsV2") -> bool:
    """Delete a scheduled task."""
    ps = f"Unregister-ScheduledTask -TaskName '{name}' -TaskPath '\\{folder}\\' -Confirm:$false -ErrorAction SilentlyContinue"
    rc, _, _ = _powershell(ps)
    return rc == 0


def _register_task(
    name: str,
    command: str,
    workdir: str,
    at: str,
    days: list[str],
    folder: str = "TradingAgentsV2",
    time_limit: str = "PT30M",
    priority: int = 7,
) -> tuple[bool, str]:
    """Register a scheduled task (weekdays only via weekly trigger)."""
    day_map = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
               "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
    day_names = [day_map.get(d, d) for d in days]
    days_str = ",".join(day_names)

    ps = f"""
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument '/c cd /d "{workdir}" && {command}'
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {days_str} -At "{at}"
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -Priority {priority}
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings
Register-ScheduledTask -TaskName "{name}" -TaskPath "\\{folder}\\" -InputObject $Task -Force
"""
    rc, out, err = _powershell(ps)
    if rc != 0:
        err_msg = err.strip() or out.strip()
        # Sanitize for GBK console
        err_msg = err_msg.encode("ascii", "replace").decode("ascii")
        return False, f"PowerShell error (rc={rc}): {err_msg[:200]}"
    return True, out.strip()


def load_config() -> dict[str, Any]:
    """Load claw_tasks.yaml."""
    if not CONFIG_PATH.exists():
        print(f"[ERROR] Config not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_tasks() -> None:
    """List all tasks from config and their registration status."""
    cfg = load_config()
    folder = cfg.get("settings", {}).get("task_folder", "TradingAgentsV2")
    tasks = cfg.get("tasks", [])

    if not tasks:
        print("No tasks defined in config.")
        return

    print(f"{'Task':<25} {'Enabled':<8} {'Config':<16} {'Actual':<10} {'Registered':<12} {'Description'}")
    print("-" * 105)
    for t in tasks:
        name = t["name"]
        enabled = "YES" if t.get("enabled", False) else "NO"
        sched = t.get("schedule", {})
        at = sched.get("at", "?")
        days = sched.get("days", [])
        # Shorten days list: Mon,Tue,Wed,Thu,Fri -> Mon-Fri
        if len(days) == 5 and set(days) == {"Mon", "Tue", "Wed", "Thu", "Fri"}:
            days_str = "Mon-Fri"
        else:
            days_str = ",".join(days)
        config_str = f"{at} ({days_str})"
        exists = _task_exists(name, folder)
        registered = "YES" if exists else "NO"
        actual = _get_task_next_run(name, folder) if exists else "-"
        desc = t.get("description", "")
        print(f"{name:<25} {enabled:<8} {config_str:<16} {actual:<10} {registered:<12} {desc}")


def register_task(name: str | None = None) -> None:
    """Register one or all enabled tasks."""
    cfg = load_config()
    folder = cfg.get("settings", {}).get("task_folder", "TradingAgentsV2")
    time_limit = cfg.get("settings", {}).get("execution_time_limit", "PT30M")
    priority = cfg.get("settings", {}).get("priority", 7)
    tasks = cfg.get("tasks", [])

    to_register = []
    for t in tasks:
        if name is not None:
            if t["name"] == name:
                to_register.append(t)
                break
        elif t.get("enabled", False):
            to_register.append(t)

    if not to_register:
        print("No tasks to register.")
        return

    success_count = 0
    for t in to_register:
        n = t["name"]
        # Resolve {root} placeholder
        cmd = t["command"].replace("{root}", ROOT)
        wd = t["workdir"].replace("{root}", ROOT)
        sched = t.get("schedule", {})
        at = sched.get("at", "18:00")
        days = sched.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])

        # Apply random offset if configured: e.g. random_offset: [1, 15]
        random_offset = sched.get("random_offset")
        if random_offset and isinstance(random_offset, list) and len(random_offset) == 2:
            import random
            offset_min = random_offset[0]
            offset_max = random_offset[1]
            offset = random.randint(offset_min, offset_max)
            # Parse HH:MM and add offset minutes
            parts = at.split(":")
            if len(parts) == 2:
                h = int(parts[0])
                m = int(parts[1]) + offset
                h += m // 60
                m = m % 60
                at = f"{h:02d}:{m:02d}"

        # Delete existing first (to update)
        if _task_exists(n, folder):
            _delete_task(n, folder)

        ok, msg = _register_task(
            name=n,
            command=cmd,
            workdir=wd,
            at=at,
            days=days,
            folder=folder,
            time_limit=time_limit,
            priority=priority,
        )
        if ok:
            print(f"  [OK] Registered: {n} @ {at} ({','.join(days)})")
            success_count += 1
        else:
            print(f"  [FAIL] {n}: {msg}")

    print(f"\nRegistered {success_count}/{len(to_register)} task(s).")


def reload_tasks() -> None:
    """Reload all registered tasks from config (re-register all enabled)."""
    cfg = load_config()
    folder = cfg.get("settings", {}).get("task_folder", "TradingAgentsV2")
    tasks = cfg.get("tasks", [])

    # First remove all existing tasks in folder
    for t in tasks:
        if _task_exists(t["name"], folder):
            _delete_task(t["name"], folder)

    # Re-register enabled tasks
    register_task()


def remove_task(name: str) -> None:
    """Remove a specific task."""
    cfg = load_config()
    folder = cfg.get("settings", {}).get("task_folder", "TradingAgentsV2")
    if _task_exists(name, folder):
        if _delete_task(name, folder):
            print(f"[OK] Removed: {name}")
        else:
            print(f"[FAIL] Could not remove: {name}")
    else:
        print(f"[INFO] Task not found: {name}")


def remove_all() -> None:
    """Remove all TradingAgentsV2 tasks."""
    cfg = load_config()
    folder = cfg.get("settings", {}).get("task_folder", "TradingAgentsV2")

    ps = f"Get-ScheduledTask -TaskPath '\\{folder}\\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty TaskName"
    rc, out, _ = _powershell(ps)
    if rc != 0 or not out.strip():
        print("No tasks found to remove.")
        return

    names = [n.strip() for n in out.strip().split("\n") if n.strip()]
    for n in names:
        if _delete_task(n, folder):
            print(f"  [OK] Removed: {n}")
        else:
            print(f"  [FAIL] Could not remove: {n}")
    print(f"\nRemoved {len(names)} task(s).")


def main():
    parser = argparse.ArgumentParser(description="Claw Windows Task Scheduler Manager")
    parser.add_argument("--list", action="store_true", help="List all tasks and their status")
    parser.add_argument("--register", nargs="?", const="__all__", metavar="NAME",
                        help="Register task(s). Omit NAME to register all enabled.")
    parser.add_argument("--reload", action="store_true", help="Reload all enabled tasks from config")
    parser.add_argument("--remove", metavar="NAME", help="Remove a specific task")
    parser.add_argument("--remove-all", action="store_true", help="Remove all TradingAgentsV2 tasks")
    args = parser.parse_args()

    if not any([args.list, args.register, args.reload, args.remove, args.remove_all]):
        parser.print_help()
        sys.exit(0)

    if args.list:
        list_tasks()
    elif args.register:
        if args.register == "__all__":
            register_task()
        else:
            register_task(args.register)
    elif args.reload:
        reload_tasks()
    elif args.remove:
        remove_task(args.remove)
    elif args.remove_all:
        remove_all()


if __name__ == "__main__":
    main()
