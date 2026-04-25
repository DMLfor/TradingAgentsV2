#!/usr/bin/env python3
"""Simple cron test - writes timestamp to log file."""

import os
from datetime import datetime

LOG_FILE = r"C:\Users\dblank\code\TradingAgentsV2\logs\cron_test.log"

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

with open(LOG_FILE, "a", encoding="utf-8") as f:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"[{now}] 定时任务测试成功！这是5分钟前创建的任务，已按计划执行。\n")
    f.write(f"[{now}] 任务类型: Windows Task Scheduler (schtasks)\n")
    f.write(f"[{now}] 触发方式: 一次性定时触发\n")
    f.write("-" * 50 + "\n")

print(f"[{now}] 任务执行完成，日志已写入: {LOG_FILE}")
