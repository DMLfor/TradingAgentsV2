# Claw 定时任务速查

本文档供 Claw 被唤醒时快速查阅，帮助用户管理 TradingAgentsV2 的定时任务。

## 快速查看所有结果（推荐）

一键检查任务状态 + 今日报告 + 各任务最新摘要：

```bash
claw\check_results.bat
```

或等效的 tdx 命令：
```bash
tdx task list
tdx task check --today
tdx task check --task ETFTracker-515180
```

## Heartbeat 自动检查

Claw 被唤醒时（包括 Heartbeat），执行：
```bash
claw\check_results.bat
```

配置参考 `claw/HEARTBEAT.md`。

---

## 注册任务

首次部署或修改配置后执行：

```bash
tdx task register
```

注册所有 `config/claw_tasks.yaml` 中 `enabled: true` 的任务。

## 查看任务列表

```bash
tdx task list
```

输出每个任务的：名称、是否启用、配置时间、实际注册时间（含 random_offset）、是否在 Windows Task Scheduler 中已注册。

## 查看今日结果

```bash
tdx task check --today
```

列出今天所有已生成的报告文件及其生成时间。

## 查看某任务最新报告

```bash
tdx task check --task ETFTracker-515180
```

显示该任务最近的报告文件列表，并输出最新一份报告的前 20 行摘要。

## 查看今日某任务报告

```bash
tdx task check --task ETFTracker-515180 --today
```

只查看今天是否有该任务的报告。

## 重新加载任务（修改时间/命令后）

编辑 `config/claw_tasks.yaml` 后：

```bash
tdx task reload
```

这会先删除所有旧任务，再根据最新配置重新注册。

## 删除任务

```bash
tdx task remove --name ETFTracker-515180
```

## 删除所有任务

```bash
tdx task remove-all
```

## 手动执行策略

如果 Windows 定时任务还没触发，可以手动运行：

```bash
# 515180 信号跟踪（RSI30 策略）
tdx signal -c 515180 -s rsi30_bounce --save

# 159545 信号跟踪（MACD 金叉策略）
tdx signal -c 159545 -s macd_golden --save

# 创业板排名
tdx rank --bars 120 --top 100 --save
```

报告会自动保存到 `logs/` 目录。

## 常见问题

### 任务没执行？

1. 打开 Windows Task Scheduler（任务计划程序）
2. 导航到 `Task Scheduler Library > TradingAgentsV2`
3. 检查任务状态是否为 "Ready"
4. 右键任务 → "Run" 手动测试
5. 查看 `logs/` 目录是否有新文件生成

### 想改执行时间？

1. 编辑 `config/claw_tasks.yaml`，修改 `at` 字段
2. 运行 `tdx task reload`

### 想添加新策略？

1. 编辑 `config/claw_tasks.yaml`，在 `tasks:` 下新增条目
2. 确保 `command` 使用 `tdx <cmd>` 形式（如 `tdx signal -c XXX -s XXX --save`）
3. 运行 `tdx task register`

### 报告在哪里？

所有报告保存在项目根目录的 `logs/` 下，按日期自动归档。文件名格式：
- `signal_515180_rsi30_bounce_20260425_090000.txt`
- `signal_159545_macd_golden_20260425_090500.txt`
- `growth_board_rank_20260425_190000.txt`
