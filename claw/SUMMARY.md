# TradingAgentsV2 本地 Claw 定时任务系统 — 长期记忆

> 生成时间: 2026-04-25
> 适用场景: 本地 Kimi Claw Desktop + Windows Task Scheduler + 本地 MySQL

---

## 1. 项目概况

- **项目路径**: `C:\path\to\TradingAgentsV2`
- **核心功能**: A股/ETF 技术分析（37指标）、策略回测、定时任务自动执行
- **数据源**: 本地 MySQL `tdx_data`（38,450,565 行，57,875 代码，通达信同步）
- **定时任务平台**: Kimi Claw Desktop（本地部署）→ 注册到 Windows Task Scheduler
- **Claw 工作模式**: Claw 是"临时工"，负责注册任务和查询结果，实际执行由 Windows 完成

---

## 2. 定时任务清单

| # | 任务名 | 配置时间 | 实际时间 | 命令 | 策略 |
|---|--------|----------|----------|------|------|
| 1 | ETFTracker-515180 | 09:00 | 09:00 + 1~15min 随机偏移 | `tdx signal -c 515180 -s rsi30_bounce --save` | RSI30 反弹信号 |
| 2 | ETFTracker-159545 | 09:00 | 09:00 + 1~15min 随机偏移 | `tdx signal -c 159545 -s macd_golden --save` | MACD 金叉信号 |
| 3 | GrowthBoardRank | 19:00 | 19:00 (无偏移) | `tdx rank --bars 120 --top 100 --save` | 创业板全量排名 |
| 4 | DailyMarketReview | 19:30 | 19:30 (无偏移) | `tdx review --save` | 每日技术复盘（十一维报告） |
| 5 | WatchlistScan-default | 20:00 | 20:00 (无偏移) | `tdx watchlist scan --pool default --save` | 关注池每日扫描（默认池） |
| 6 | WatchlistReview-default | 20:30 | 20:30 (无偏移) | `tdx watchlist review --pool default --save` | 关注池每日复盘（默认池） |
| 4 | DailyMarketReview | 19:30 | 19:30 (无偏移) | `tdx review --save` | 每日技术复盘（大盘/板块/情绪/趋势/量价/前瞻/ETF/信号/选股/计划） |

配置位置: `config/claw_tasks.yaml`
注册命令: `tdx task register`
重载命令: `tdx task reload`
查询命令: `tdx task check --today`
一键检查: `claw\check_results.bat`

---

## 3. 核心标的策略对比

### 515180（红利ETF）
- **特性**: 震荡慢牛，均值回归特征明显
- **最优策略**: RSI30 反弹（RSI<30 买入，RSI>70 卖出）
- **回测结果**: +71.38%，Sharpe 1.48，最大回撤 -7.35%，胜率 80%
- **策略文件**: `strategies/515180_rsi30_bounce.json`
- **当前定时脚本**: `etf_volatility_strategy.py`（RSI30/70 参数）

### 159545（恒生港股通高股息低波动ETF）
- **特性**: 港股红利，趋势性强于 A 股红利，2024-04-15 上市（仅 492 天数据）
- **最优策略**: MACD 金叉趋势跟踪（+26.32%，Sharpe 1.26）
- **RSI 策略效果差**: 趋势性强，超跌反弹机会少
- **当前定时脚本**: `etf_longterm_tracker.py`（MA+MACD+ADX 趋势状态机）

### 结论
**515180 的 RSI30 策略明显更优**（收益更高、回撤更小、胜率更高）。两标的策略流派互补：515180 均值回归，159545 趋势跟踪。

---

## 4. 文件结构速查

```
TradingAgentsV2/
├── config/
│   ├── tdx_config.yaml           # MySQL 配置（本地主配置）
│   ├── claw_tasks.yaml           # 定时任务配置
│   └── stock_metadata.json       # 股票元数据（~2MB）
├── scripts/
│   ├── claw_register.py          # 任务注册器（核心工具）
│   ├── claw_check.py             # 结果查询器（核心工具）
│   ├── etf_longterm_tracker.py   # ETF 趋势跟踪
│   ├── etf_volatility_strategy.py# ETF RSI 波动率策略
│   ├── technical_master.py       # 37指标全量分析
│   ├── rank_growth_board.py      # 创业板排名
│   ├── scan_market.py            # 市场扫描
│   ├── strategy_backtest.py      # 策略回测
│   ├── daily_market_review.py    # 每日技术复盘（十一维报告）
│   ├── watchlist_manager.py      # 关注池管理（CRUD）
│   ├── watchlist_scan.py         # 关注池每日扫描
│   └── watchlist_review.py       # 关注池每日复盘（信号+操作建议）
├── strategies/                   # 策略 JSON 配置（24+ 种）
│   └── 515180_rsi30_bounce.json  # 515180 最优策略
├── claw/
│   ├── README.md                 # Claw 速查手册
│   └── SUMMARY.md                # 本文档
├── reports/                      # 结构化报告输出目录（signals/rankings/scans/analysis/backtests/etf）
│   ├── tracker_515180_*.txt
│   ├── tracker_159545_*.txt
│   ├── growth_board_rank_*.txt
│   └── etf_grid_*.txt
└── results/
    └── backtest/                 # 回测报告目录
```

---

## 5. 常用命令

### 任务管理
```bash
# 查看任务列表
python scripts/claw_register.py --list

# 注册所有启用任务
python scripts/claw_register.py --register

# 重新加载（修改配置后）
python scripts/claw_register.py --reload

# 删除所有任务
python scripts/claw_register.py --remove-all
```

### 结果查询
```bash
# 查看今日所有报告
python scripts/claw_check.py --today

# 查看指定任务最新报告（带摘要）
python scripts/claw_check.py --task ETFTracker-515180

# 查看指定任务今日报告
python scripts/claw_check.py --task ETFTracker-515180 --today
```

### 手动执行策略
```bash
# 515180 RSI 策略
python scripts/etf_volatility_strategy.py --code 515180 --rsi-buy 30 --rsi-sell 70 --save

# 159545 趋势跟踪
python scripts/etf_longterm_tracker.py --code 159545 --save

# 单股全量分析
python scripts/technical_master.py 515180 --bars 60 --save

# 创业板排名
python scripts/rank_growth_board.py --bars 120 --top 100 --save

# 每日技术复盘
python scripts/daily_market_review.py --save
python scripts/daily_market_review.py --date 2026-04-25 --save
```

### 策略回测
```bash
# 515180 RSI30 回测
python scripts/strategy_backtest.py --strategy strategies/515180_rsi30_bounce.json --start 2021-08-02 --end 2026-04-25 --save

# 批量回测
python scripts/batch_backtest.py
```

---

## 6. 关键认知

### Kimi Claw Desktop 的工作模式
- Claw 是"临时工"：被唤醒 → 执行命令 → 休眠
- 定时任务由 **Windows Task Scheduler** 实际执行
- Claw **无法主动通知**用户任务完成
- 所有结果必须**写入本地文件**，Claw 被唤醒时才能"考古"

### 数据流
- 本地通达信 → MySQL（每日盘后同步）
- 分析脚本 → 直接查询本地 MySQL
- 报告输出 → `reports/` 目录（按类型分子目录）
- 回测报告 → `results/backtest/` 目录

### 混合模式决策
- **本地**: MySQL + 通达信同步（数据源）
- **Claw**: 只读分析，定时执行策略脚本
- **不上传数据库**: 5.6GB SQLite 太大，Claw 直接连本地 MySQL

---

## 7. 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| PowerShell GBK 编码 | 存在 | 中文输出偶尔乱码，不影响功能 |
| 159545 历史数据短 | 存在 | 2024-04-15 上市，仅 492 天，回测样本少 |
| WinError 32 on repack | 已规避 | 打包时旧文件锁定，用新目录或手动删除 |

---

## 8. 扩展指南

### 添加新定时任务
1. 编辑 `config/claw_tasks.yaml`，新增 `tasks:` 条目
2. 确保 `command` 指向正确脚本，`{root}` 会自动替换为项目路径
3. 运行 `python scripts/claw_register.py --reload`

### 修改任务时间
1. 编辑 `config/claw_tasks.yaml`，修改 `at` 字段
2. 运行 `python scripts/claw_register.py --reload`

### 添加新 ETF/个股分析
- 趋势型标的 → `etf_longterm_tracker.py`
- 震荡型标的 → `etf_volatility_strategy.py`（调 RSI 阈值）
- 单股深度分析 → `technical_master.py`

---

## 9. 核心文件修改记录

| 时间 | 文件 | 操作 | 说明 |
|------|------|------|------|
| 2026-04-25 | `config/claw_tasks.yaml` | 新增 | 定时任务配置 |
| 2026-04-25 | `scripts/claw_register.py` | 新增 | Windows 任务注册器 |
| 2026-04-25 | `scripts/claw_check.py` | 新增 | 结果查询器 |
| 2026-04-25 | `claw/README.md` | 新增 | Claw 速查手册 |
| 2026-04-25 | `scripts/pack_for_claw.py` | 修改 | 本地部署包（0.4MB） |
| 2026-04-25 | `config/tdx_config_claw.yaml` | 删除 | 不再需要 |
| 2026-04-25 | `tdx_core/cli.py` | 新增 | 统一 CLI 入口（Click） |
| 2026-04-25 | `claw/check_results.bat` | 新增 | 一键检查所有任务结果 |
| 2026-04-25 | `claw/HEARTBEAT.md` | 新增 | Claw Heartbeat 配置 |
| 2026-04-25 | `config/claw_tasks.yaml` | 修改 | 命令改为 `tdx signal ...` 形式 |
| 2026-04-25 | `scripts/claw_register.py` | 修改 | `list` 显示实际注册时间（含 random_offset） |
| 2026-04-25 | `scripts/claw_register.py` | 修改 | 中文注释英文化（修复 Claw 编辑编码错误） |
| 2026-04-26 | `tdx_core/watchlist.py` | 新增 | 关注池核心模块（多池CRUD+元数据展示） |
| 2026-04-26 | `scripts/watchlist_manager.py` | 新增 | 关注池CLI管理脚本 |
| 2026-04-26 | `scripts/watchlist_scan.py` | 新增 | 关注池每日技术面扫描 |
| 2026-04-26 | `tdx_core/cli.py` | 修改 | 注册 `watchlist` 子命令组（add/remove/list/clear/pools/scan/review） |
| 2026-04-26 | `scripts/watchlist_review.py` | 新增 | 关注池每日复盘（技术面+信号+操作建议） |
| 2026-04-26 | `config/claw_tasks.yaml` | 修改 | 新增 WatchlistReview-default 定时任务 |
| 2026-04-26 | `tdx_core/review_engine.py` | 新增 | 复盘核心引擎（趋势评分+量价分析+明日前瞻） |
| 2026-04-26 | `scripts/daily_market_review.py` | 新增 | 每日技术复盘 CLI（十一维报告） |
| 2026-04-26 | `tdx_core/reporting.py` | 修改 | 新增趋势评分/量价分析/明日前瞻报告板块 |
| 2026-04-26 | `tdx_core/cli.py` | 修改 | 注册 `review` 子命令 |
