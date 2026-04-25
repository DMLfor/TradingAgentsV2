# TradingAgentsV2 云端使用手册（OpenClaw）

> 适用场景：Linux 云端 / OpenClaw / 无 MySQL / 内置 SQLite 数据

---

## 1. 环境准备（已完成的）

```bash
# 进入项目目录
cd TradingAgentsV2

# 激活虚拟环境
source venv/bin/activate

# 验证安装
tdx --help
```

**关键区别**：云端无 MySQL，首次运行任意 `tdx` 命令时，会自动将 `data/tdx_data_cloud.db.gz` 解压为 SQLite 数据库，无需手动操作。

---

## 2. 核心命令速查

### 信号跟踪（最常用）

```bash
# 515180 红利ETF — RSI30反弹策略（回测最优: +71.38%, Sharpe 1.48）
tdx signal -c 515180 -s rsi30_bounce --save

# 159545 港股红利ETF — MACD金叉策略（回测: +26.32%, Sharpe 1.26）
tdx signal -c 159545 -s macd_golden --save
```

### 板块排名

```bash
# 创业板 Top 100 技术分析排名（遍历约1400只股票，耗时较长）
tdx rank --bars 120 --top 100 --save
```

### 技术分析

```bash
# 单股 37 指标全量分析（约 8-10 分钟）
tdx analyze -c 688018 -b 120 --save
```

### 市场扫描

```bash
# 扫描 MACD 金叉
tdx scan -c 000001,000002,600000 -i macd -s golden_cross --save

# 扫描 RSI 超卖
tdx scan -c 000001,000002 -i rsi -s oversold --save
```

### 策略回测

```bash
# 回测 515180 RSI30 策略
tdx backtest -s strategies/515180_rsi30_bounce.json --codes 515180 --save
```

### 辅助命令

```bash
# 列出 41 种可用策略
tdx list-strategies

# 列出 32 种可用指标
tdx list-indicators

# ETF 长期跟踪
tdx etf -c 515180 -s longterm --save
```

---

## 3. 云端定时任务（Claw 调度）

**注意**：云端没有 Windows Task Scheduler，定时任务由 Claw 自己的调度机制触发。

配置位置：`config/claw_tasks.yaml`

当前启用的任务：

| 任务名 | 时间 | 命令 |
|:---|:---|:---|
| ETFTracker-515180 | 工作日 09:00 | `tdx signal -c 515180 -s rsi30_bounce --save` |
| ETFTracker-159545 | 工作日 09:00 | `tdx signal -c 159545 -s macd_golden --save` |
| GrowthBoardRank | 工作日 19:00 | `tdx rank --bars 120 --top 100 --save` |

### 手动执行（测试用）

```bash
# 直接运行任务命令即可
tdx signal -c 515180 -s rsi30_bounce --save
tdx signal -c 159545 -s macd_golden --save
tdx rank --bars 120 --top 100 --save
```

### 查看报告

```bash
# 列出 reports/ 目录下今天的所有报告
find reports/ -type f -name "*$(date +%Y%m%d)*" | sort

# 查看指定报告内容
cat reports/signals/signal_515180_rsi30_bounce_*.txt
```

---

## 4. Heartbeat 自动检查

Claw 被唤醒时（Heartbeat），执行以下检查流程：

```bash
# 1. 检查任务状态
tdx task list

# 2. 查看今日报告
tdx task check --today

# 3. 查看最新信号
ls -lt reports/signals/signal_515180_*.txt | head -1 | xargs cat
ls -lt reports/signals/signal_159545_*.txt | head -1 | xargs cat
```

**汇报规则**：
- 如果有新报告 → 汇总关键信号/排名摘要告知用户
- 如果无新报告 → 静默或简单汇报"暂无新报告"

配置参考：`claw/HEARTBEAT.md`

---

## 5. 数据结构说明

云端 SQLite 包含：
- **市场**：sz + sh（沪深主板、科创板、创业板）
- **时间**：近 1 年日线数据（~250 交易日）
- **股票数**：6,395 只
- **表**：`tdx_daily`（日线行情）

**不包含**：
- 北交所（数据缺失）
- 分钟线（数据量太大）
- 历史超过 1 年的数据

---

## 6. 常见问题

### Q: 首次运行慢？
A: 正常。首次会解压 `data/tdx_data_cloud.db.gz`（45MB → 241MB），后续直接读 `.db`，速度正常。

### Q: 想分析的股票不在数据库里？
A: 云端只保留 sz + sh 近1年数据。如需全量数据，请在本地 Windows 机器重新导出并上传。

### Q: 报告保存在哪里？
A: `reports/` 目录下，按类型分子目录：
- `reports/signals/signal_515180_rsi30_bounce_YYYYMMDD_HHMMSS.txt`
- `reports/signals/signal_159545_macd_golden_YYYYMMDD_HHMMSS.txt`
- `reports/rankings/growth_board_rank_YYYYMMDD_HHMMSS.txt`

### Q: 如何更新云端数据？
A: 在本地运行 `python scripts/export_cloud_sqlite.py`，生成新的 `.gz`，重新 push 到 GitHub，Claw 重新 clone。

---

## 7. 关键记忆锚点

- **CLI 输出全中文**：所有终端输出使用中文
- **SQLite 自动切换**：`data/tdx_data_cloud.db/.gz` 存在时自动走 SQLite，无需配置 MySQL
- **虚拟环境**：每次进入项目先 `source venv/bin/activate`
- **定时任务**：云端无 Windows Task Scheduler，由 Claw 自己调度执行
