# 分析脚本集合

基于 `tdx_core.analyzer` 的常用 CLI 分析工具，适合日常复盘和批量扫描。

---

## 脚本清单

| 脚本 | 用途 | 典型用法 |
|------|------|---------|
| `technical_master.py` | **技术分析大师全量指标面板**（37个指标分层输出 + 信号雷达 + 综合评分） | `python scripts/technical_master.py 688018` |
| `analyze_stock.py` | 单股深度分析（多指标扫描 + 信号检测 + 回测） | `python scripts/analyze_stock.py 688018 --save` |
| `scan_market.py` | 多股扫描：查看最新指标值或找信号 | `python scripts/scan_market.py 688018,688981 --indicator macd --signal golden_cross` |
| `backtest_signal.py` | 回测某信号的历史表现 | `python scripts/backtest_signal.py 688018,688981 --indicator rsi --signal oversold --hold 5` |
| `rank_stocks.py` | 按指标值对股票排名 | `python scripts/rank_stocks.py 688018,688981 --indicator rsi --ascending` |
| `list_indicators.py` | 列出所有支持的指标和信号 | `python scripts/list_indicators.py` |

---

## 快速开始

### 1. 查看支持的指标和信号

```bash
python scripts/list_indicators.py
python scripts/list_indicators.py --indicator macd
```

### 2. 技术分析大师全量指标面板

一次性输出 **37 个技术指标** 的完整解读，按大师分析优先级分为 5 层：
1. 趋势结构层（MACD、Supertrend、ADX、Ichimoku、均线系统等）
2. 动量与时机层（RSI、Stochastic、StochRSI、CCI、Williams %R 等）
3. 波动率与价格结构层（布林带、ATR、Keltner、Donchian 等）
4. 量价确认层（OBV、MFI、VWAP、CMF、Force Index 等）
5. 价格目标与特殊系统（枢纽点、斐波那契、TD 序列）

附带 **信号雷达**（最近5日显著信号）和 **多空综合评分**（趋势/动量/波动/量价四维打分）。

```bash
# 分析最近 250 根 K 线（默认）
python scripts/technical_master.py 688018

# 分析最近 120 根 K 线
python scripts/technical_master.py 688018 --bars 120

# 保存报告
python scripts/technical_master.py 688018 --save
```

### 3. 单股深度分析

```bash
# 默认分析 12 个指标
python scripts/analyze_stock.py 688018

# 指定指标
python scripts/analyze_stock.py 000001 --indicators rsi,macd,bollinger

# 保存报告到 logs/
python scripts/analyze_stock.py 688018 --save
```

### 4. 扫描市场信号

```bash
# 查看多只股票的最新 RSI
python scripts/scan_market.py 688018,688981,688111 --indicator rsi

# 找 MACD 金叉
python scripts/scan_market.py 688018,688981,688111 --indicator macd --signal golden_cross

# 找 RSI 超卖
python scripts/scan_market.py 000001,000002,600000 --indicator rsi --signal oversold
```

### 5. 回测信号

```bash
# MACD 金叉后持有 5 天
python scripts/backtest_signal.py 688018,688981 --indicator macd --signal golden_cross --hold 5

# RSI 超卖后持有 10 天
python scripts/backtest_signal.py 688018,688981 --indicator rsi --signal oversold --hold 10 --save
```

### 6. 排名

```bash
# RSI 从低到高（找超卖）
python scripts/rank_stocks.py 688018,688981,688111,688012 --indicator rsi --ascending

# MACD 柱状线从高到低
python scripts/rank_stocks.py 688018,688981,688111,688012 --indicator macd --column macd_hist
```

---

## 输出说明

- 所有脚本默认输出到终端
- 加 `--save` 会将完整报告保存到 `logs/` 目录，文件名带时间戳
- 报告为纯文本格式，可直接复制到笔记或 IM 发送

---

## 环境要求

### 股票代码 ↔ 名称兼容

所有接受股票代码的脚本都支持**直接输入中文名称**，系统会自动从 `config/stock_names.json` 中解析为6位数字代码。

```bash
# 用代码
python scripts/technical_master.py 688018

# 用中文名称（自动解析）
python scripts/technical_master.py 乐鑫科技

# 多股脚本同样支持混合输入
python scripts/scan_market.py 乐鑫科技,中芯国际 --indicator rsi
```

名称映射数据来源：
- 默认从通达信 `T0002/hq_cache/specgpext.txt` 提取（已内置 5500+ A股映射）
- 同时内置了 21 只常见白马股的兜底映射（茅台、宁德、平安等）
- 可通过 `tdx_core.names.reload()` 热重载映射文件

---

## 环境要求

这些脚本自动将项目根目录加入 `sys.path`，因此可以在项目根目录下直接运行，无需先 `pip install -e .`。

数据库配置读取 `config/tdx_config.yaml`，与 `TdxQuery` 保持一致。
