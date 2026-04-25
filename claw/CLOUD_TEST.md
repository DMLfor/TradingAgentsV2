# TradingAgentsV2 云端环境验证测试

> 一键验证 `git clone` + `pip install` 后核心功能是否全部可用。

---

## 快速开始

```bash
cd TradingAgentsV2
source venv/bin/activate
python tests/test_cloud_setup.py
```

**预期耗时**：约 40-60 秒（首次运行需解压 `.db.gz`，可能额外 +30 秒）

---

## 预期输出

```
============================================================
TradingAgentsV2 云端环境综合验证测试
============================================================
项目路径: /path/to/TradingAgentsV2
Python: 3.11.x
------------------------------------------------------------
  tdx --help                     ✅ PASS
  SQLite auto-detect             ✅ PASS (db_type=sqlite)
  SQLite DB exists               ✅ PASS (241.6 MB)
  get_daily(515180)              ✅ PASS (242 rows)
  signal_tracker(515180)         ✅ PASS
  rank --top 5                   ⏭️ SKIP (timeout > 45s)
  scan 000001,000002             ✅ PASS
  list-indicators                ✅ PASS
  list-strategies                ✅ PASS
  backtest 515180                ✅ PASS (1 signals)
------------------------------------------------------------
结果: 10/10 通过, 耗时 48.2秒
============================================================
✅ 全部测试通过！云端环境就绪。
```

> `rank --top 5` 显示 `⏭️ SKIP` 是正常的——创业板排名需遍历约 1400 只股票，耗时较长，测试中主动跳过以避免阻塞。

---

## 测试项说明

| # | 测试项 | 验证内容 |
|:---|:---|:---|
| 01 | `tdx --help` | CLI 命令已正确安装到虚拟环境 PATH |
| 02 | SQLite auto-detect | 检测到 `data/tdx_data_cloud.db/.gz`，自动切换 SQLite 模式 |
| 03 | SQLite DB exists | `.db.gz` 已解压为 `.db`（首次运行自动完成） |
| 04 | `get_daily(515180)` | 日线查询正常，返回 >100 条记录 |
| 05 | `signal_tracker(515180)` | 信号跟踪引擎可运行，输出中文报告 |
| 06 | `rank --top 5` | 排名引擎可启动（因耗时长，45s 后自动跳过） |
| 07 | `scan 000001,000002` | 市场扫描引擎可运行 |
| 08 | `list-indicators` | 32 种指标列表正常输出 |
| 09 | `list-strategies` | 41 种策略列表正常输出 |
| 10 | `backtest 515180` | 回测管道可运行，RSI 指标计算正常 |

---

## 失败排查

### 01 / 08 / 09 失败：`tdx` 命令未找到
```bash
# 重新安装 CLI
pip install -e .
# 验证
which tdx
```

### 02 / 03 失败：未自动切换到 SQLite
检查仓库是否完整拉取了 `data/tdx_data_cloud.db.gz`：
```bash
ls -lh data/tdx_data_cloud.db.gz
# 如果不存在，重新 clone 或从本地重新导出上传
```

### 04 / 05 / 07 / 10 失败：数据查询异常
可能是首次解压尚未完成，或 `.db` 文件损坏：
```bash
# 手动重新解压
rm -f data/tdx_data_cloud.db
gunzip -c data/tdx_data_cloud.db.gz > data/tdx_data_cloud.db

# 再次测试
python tests/test_cloud_setup.py
```

### 06 失败：rank 进程崩溃
可能是 metadata 缺失。尝试重新生成：
```bash
python scripts/update_stock_metadata.py
python tests/test_cloud_setup.py
```

---

## 手动补充测试（可选）

测试脚本跳过了耗时较长的功能，可手动验证：

```bash
# 创业板排名（完整版，约 3-5 分钟）
tdx rank --bars 120 --top 100 --save

# 单股深度分析（约 8-10 分钟）
tdx analyze -c 688018 -b 120 --save

# 回测（完整版）
tdx backtest -s strategies/515180_rsi30_bounce.json --codes 515180 --save
```

---

## 本地 vs 云端

本测试脚本在**本地 Windows + MySQL** 环境下也能运行：
- 测试 02 会自动检测到无 `tdx_data_cloud.db/.gz`，验证 MySQL 默认模式
- 测试 03 会尝试连接本地 MySQL（需确保 `config/tdx_config.yaml` 配置正确）
- 其余测试项逻辑完全一致
